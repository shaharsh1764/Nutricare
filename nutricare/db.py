"""SQLite persistence layer for NutriCare (schema v2: multi local-user).

Identity model (documented honestly in the UI and README):
  * Local user profiles selected via a switcher, stored in a session cookie.
  * There is NO authentication and NO encryption: this organises data on one
    device/browser, it does NOT protect records from someone else using the
    same browser. The UI states this limitation explicitly.
  * Every personal record (profile, meals, water, assessments, settings) is
    scoped by user_id so two local users never see each other's data by
    accident.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

from flask import g, current_app

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS profile (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    age INTEGER, sex TEXT, height_cm REAL, weight_kg REAL,
    activity TEXT DEFAULT 'moderate', goal TEXT DEFAULT 'maintain',
    macro_model TEXT DEFAULT 'balanced', units TEXT DEFAULT 'metric',
    dietary_prefs TEXT DEFAULT '[]', allergies TEXT DEFAULT '[]',
    medications TEXT DEFAULT '[]', medical_history TEXT DEFAULT '',
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS foods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL, grp TEXT, serving_desc TEXT, serving_g REAL,
    kcal REAL, protein_g REAL, carbs_g REAL, fat_g REAL, fiber_g REAL,
    sodium_mg REAL, potassium_mg REAL, calcium_mg REAL, iron_mg REAL,
    source TEXT, source_id TEXT, state TEXT, quality TEXT,
    dietary TEXT, allergens TEXT
);
CREATE TABLE IF NOT EXISTS meal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date TEXT NOT NULL, meal TEXT NOT NULL,
    food_id INTEGER REFERENCES foods(id) ON DELETE SET NULL,
    custom_name TEXT, quantity REAL NOT NULL, unit TEXT NOT NULL,
    custom_kcal REAL, custom_protein_g REAL, custom_carbs_g REAL, custom_fat_g REAL,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS water_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date TEXT NOT NULL, amount_ml INTEGER NOT NULL, created_at TEXT
);
CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT, emergency INTEGER, payload TEXT, result TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key TEXT NOT NULL, value TEXT,
    PRIMARY KEY (user_id, key)
);
CREATE INDEX IF NOT EXISTS idx_meals_user_date ON meal_entries (user_id, date);
CREATE INDEX IF NOT EXISTS idx_water_user_date ON water_logs (user_id, date);
"""

DEFAULT_SETTINGS = {
    "water_goal_ml": "2800",
    "privacy_research": "0",
    "privacy_ai": "1",
    "privacy_sync": "1",
    "demo_mode": "0",
}

MEALS = ("breakfast", "lunch", "dinner", "snacks")


def db_path() -> Path:
    raw = os.environ.get("NUTRICARE_DB")
    if raw:
        return Path(raw)
    return Path(current_app.root_path).parent / "instance" / "nutricare.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def today() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------- schema setup

def _ensure_food_columns(conn: sqlite3.Connection):
    cols = _columns(conn, "foods")
    for col, typ in [
        ("source_id", "TEXT"), ("state", "TEXT"), ("quality", "TEXT"),
        ("dietary", "TEXT"), ("allergens", "TEXT"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE foods ADD COLUMN {col} {typ}")
    conn.commit()

def init_db(conn: sqlite3.Connection):
    conn.executescript(SCHEMA)
    _ensure_food_columns(conn)
    conn.commit()


def _tables(conn) -> set:
    return {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(conn, table) -> set:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def migrate_legacy(conn: sqlite3.Connection) -> bool:
    """Upgrade a v1 single-user database (profile.id = 1, no users table) to v2
    by moving everything under local user #1. Returns True if migrated."""
    tables = _tables(conn)
    if "users" in tables or "profile" not in tables:
        return False
    if "user_id" in _columns(conn, "profile"):
        return False  # already v2
    conn.executescript("""
    ALTER TABLE profile RENAME TO leg_profile;
    ALTER TABLE meal_entries RENAME TO leg_meal_entries;
    ALTER TABLE water_logs RENAME TO leg_water_logs;
    ALTER TABLE assessments RENAME TO leg_assessments;
    ALTER TABLE settings RENAME TO leg_settings;
    """)
    init_db(conn)
    conn.execute(
        "INSERT INTO users (id, name, created_at) SELECT 1, "
        "CASE WHEN name IS NULL OR name = '' THEN 'Migrated local user' ELSE name END, "
        "created_at FROM leg_profile")
    conn.execute("""
        INSERT INTO profile (user_id, age, sex, height_cm, weight_kg, activity, goal,
            macro_model, units, dietary_prefs, allergies, medications,
            medical_history, updated_at)
        SELECT 1, age, sex, height_cm, weight_kg, activity, goal, macro_model, units,
            dietary_prefs, allergies, medications, medical_history, updated_at
        FROM leg_profile""")
    conn.execute("""
        INSERT INTO meal_entries (user_id, date, meal, food_id, custom_name, quantity,
            unit, custom_kcal, custom_protein_g, custom_carbs_g, custom_fat_g, created_at)
        SELECT 1, date, meal, food_id, custom_name, quantity, unit, custom_kcal,
            custom_protein_g, custom_carbs_g, custom_fat_g, created_at
        FROM leg_meal_entries""")
    conn.execute("""
        INSERT INTO water_logs (user_id, date, amount_ml, created_at)
        SELECT 1, date, amount_ml, created_at FROM leg_water_logs""")
    conn.execute("""
        INSERT INTO assessments (user_id, created_at, emergency, payload, result)
        SELECT 1, created_at, emergency, payload, result FROM leg_assessments""")
    conn.execute("""
        INSERT OR IGNORE INTO settings (user_id, key, value)
        SELECT 1, key, value FROM leg_settings""")
    conn.executescript("""
    DROP TABLE leg_profile; DROP TABLE leg_meal_entries; DROP TABLE leg_water_logs;
    DROP TABLE leg_assessments; DROP TABLE leg_settings;""")
    _ensure_default_settings(conn, 1)
    conn.commit()
    return True


# ---------------------------------------------------------------- users

def create_user(conn: sqlite3.Connection, name: str) -> int:
    cur = conn.execute("INSERT INTO users (name, created_at) VALUES (?, ?)",
                       (name.strip() or "Local user", now()))
    uid = cur.lastrowid
    conn.execute(
        "INSERT INTO profile (user_id, updated_at) VALUES (?, ?)", (uid, now()))
    _ensure_default_settings(conn, uid)
    conn.commit()
    return uid


def get_user(conn: sqlite3.Connection, uid: int) -> dict | None:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    return dict(row) if row else None


def list_users(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT id, name, created_at FROM users ORDER BY id")]


def delete_user(conn: sqlite3.Connection, uid: int) -> bool:
    cur = conn.execute("DELETE FROM users WHERE id = ?", (uid,))
    conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------- per-user data

def _ensure_default_settings(conn: sqlite3.Connection, uid: int):
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings (user_id, key, value) VALUES (?, ?, ?)",
                     (uid, key, value))


def get_profile(conn: sqlite3.Connection, uid: int) -> dict:
    row = conn.execute("SELECT * FROM profile WHERE user_id = ?", (uid,)).fetchone()
    if row is None:
        conn.execute("INSERT INTO profile (user_id, updated_at) VALUES (?, ?)",
                     (uid, now()))
        conn.commit()
        row = conn.execute("SELECT * FROM profile WHERE user_id = ?", (uid,)).fetchone()
    p = dict(row)
    p.pop("user_id", None)
    # normalise NULLs (e.g. rows migrated from v1) to safe defaults
    p["activity"] = p.get("activity") or "moderate"
    p["goal"] = p.get("goal") or "maintain"
    p["macro_model"] = p.get("macro_model") or "balanced"
    p["units"] = p.get("units") or "metric"
    for key in ("dietary_prefs", "allergies", "medications"):
        try:
            p[key] = json.loads(p.get(key) or "[]")
        except json.JSONDecodeError:
            p[key] = []
    return p


def get_settings(conn: sqlite3.Connection, uid: int) -> dict:
    _ensure_default_settings(conn, uid)
    out = dict(DEFAULT_SETTINGS)
    for row in conn.execute("SELECT key, value FROM settings WHERE user_id = ?", (uid,)):
        out[row["key"]] = row["value"]
    out["water_goal_ml"] = int(out["water_goal_ml"])
    for key in ("privacy_research", "privacy_ai", "privacy_sync", "demo_mode"):
        out[key] = out[key] == "1"
    return out


def set_setting(conn: sqlite3.Connection, uid: int, key: str, value: str):
    conn.execute("INSERT INTO settings (user_id, key, value) VALUES (?, ?, ?) "
                 "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
                 (uid, key, value))


def purge_user_data(conn: sqlite3.Connection, uid: int):
    """Delete everything this user generated; keep the account and food dataset."""
    conn.execute("DELETE FROM meal_entries WHERE user_id = ?", (uid,))
    conn.execute("DELETE FROM water_logs WHERE user_id = ?", (uid,))
    conn.execute("DELETE FROM assessments WHERE user_id = ?", (uid,))
    conn.execute(
        "UPDATE profile SET age=NULL, sex=NULL, height_cm=NULL, weight_kg=NULL, "
        "activity='moderate', goal='maintain', macro_model='balanced', units='metric', "
        "dietary_prefs='[]', allergies='[]', medications='[]', medical_history='', "
        "updated_at=? WHERE user_id=?", (now(), uid))
    set_setting(conn, uid, "demo_mode", "0")
    conn.commit()


# ---------------------------------------------------------------- demo mode (explicit)

DEMO_MEAL_PLAN = [
    ("breakfast", "Oatmeal (cooked in water)", 1.0, "serving"),
    ("breakfast", "Blueberries", 0.5, "serving"),
    ("breakfast", "Egg, whole (boiled)", 2.0, "serving"),
    ("lunch", "Chicken breast (grilled, skinless)", 1.0, "serving"),
    ("lunch", "Quinoa (cooked)", 1.0, "serving"),
    ("lunch", "Spinach / palak (cooked, no added salt)", 0.5, "serving"),
    ("snacks", "Curd / dahi (plain, whole milk)", 1.0, "serving"),
    ("snacks", "Walnuts", 0.5, "serving"),
]


def has_any_logs(conn: sqlite3.Connection, uid: int) -> bool:
    meal = conn.execute("SELECT 1 FROM meal_entries WHERE user_id = ? LIMIT 1",
                        (uid,)).fetchone()
    water = conn.execute("SELECT 1 FROM water_logs WHERE user_id = ? LIMIT 1",
                         (uid,)).fetchone()
    return bool(meal or water)


def load_demo_data(conn: sqlite3.Connection, uid: int) -> bool:
    """Explicitly-labelled fictional sample day. Refuses to mix with real logs."""
    if has_any_logs(conn, uid):
        return False
    d = today()
    for meal, name, qty, unit in DEMO_MEAL_PLAN:
        row = conn.execute("SELECT id FROM foods WHERE name = ?", (name,)).fetchone()
        if row:
            conn.execute(
                "INSERT INTO meal_entries (user_id, date, meal, food_id, quantity, unit,"
                " created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (uid, d, meal, row["id"], qty, unit, now()))
    for ml in (500, 500, 500, 300):
        conn.execute("INSERT INTO water_logs (user_id, date, amount_ml, created_at) "
                     "VALUES (?, ?, ?, ?)", (uid, d, ml, now()))
    set_setting(conn, uid, "demo_mode", "1")
    conn.commit()
    return True


def clear_demo_data(conn: sqlite3.Connection, uid: int):
    """Removes the demo day (which is all the user's logs, by load_demo_data rules)."""
    conn.execute("DELETE FROM meal_entries WHERE user_id = ?", (uid,))
    conn.execute("DELETE FROM water_logs WHERE user_id = ?", (uid,))
    set_setting(conn, uid, "demo_mode", "0")
    conn.commit()


def seed_foods(conn: sqlite3.Connection, json_path: Path | None = None):
    json_path = json_path or Path(__file__).parent.parent / "data" / "foods.json"
    payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
    _ensure_food_columns(conn)
    base_cols = ("name", "grp", "serving_desc", "serving_g", "kcal", "protein_g",
                 "carbs_g", "fat_g", "fiber_g", "sodium_mg", "potassium_mg",
                 "calcium_mg", "iron_mg", "source", "source_id", "state", "quality",
                 "dietary", "allergens")
    added = 0
    updated = 0
    for food in payload["foods"]:
        # Prepare JSON fields
        dietary = food.get("dietary")
        allergens = food.get("allergens")
        # Normalise to JSON strings for DB storage
        rec = dict(food)
        if isinstance(dietary, dict):
            rec["dietary"] = json.dumps(dietary)
        elif dietary is None:
            rec["dietary"] = None
        if isinstance(allergens, list):
            rec["allergens"] = json.dumps(allergens)
        elif allergens is None:
            rec["allergens"] = None
        exists = conn.execute("SELECT id FROM foods WHERE name = ?", (food["name"],)).fetchone()
        if exists:
            # Backfill missing metadata for existing entries (ids 1-42) without overwriting core nutrition
            cur = conn.execute("SELECT dietary, allergens, state, quality, source_id FROM foods WHERE id = ?", (exists["id"],)).fetchone()
            if cur and (cur["dietary"] is None or cur["allergens"] is None):
                conn.execute(
                    "UPDATE foods SET source_id=?, state=?, quality=?, dietary=?, allergens=? WHERE id=?",
                    (rec.get("source_id"), rec.get("state"), rec.get("quality"), rec.get("dietary"), rec.get("allergens"), exists["id"]))
                updated += 1
            continue
        # New food: preserve stable id if provided
        if "id" in food and food["id"] is not None:
            cols = ("id",) + base_cols
            vals = (food["id"],) + tuple(rec.get(c) for c in base_cols)
            # Use INSERT OR IGNORE to avoid duplicate id edge
            conn.execute(f"INSERT OR IGNORE INTO foods ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
        else:
            cols = base_cols
            vals = tuple(rec.get(c) for c in base_cols)
            conn.execute(f"INSERT INTO foods ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
        added += 1
    conn.commit()
    return added + updated
