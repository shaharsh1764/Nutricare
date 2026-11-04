"""NutriCare REST API (Flask blueprint).

Identity: a local user id is kept in the Flask session cookie. There is NO
password authentication — the UI and README state this plainly. Every personal
endpoint is scoped to the session user; without a session user they return 401
so the frontend can show onboarding instead of someone else's data.
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request, session, Response

from . import assistant, db, insights, nutrition

api = Blueprint("api", __name__, url_prefix="/api")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def err(message: str, code: int = 400):
    return jsonify({"error": message}), code


def current_uid(conn) -> int | None:
    uid = session.get("uid")
    if uid is None:
        return None
    return uid if db.get_user(conn, uid) else None


def no_user():
    return err("No active local user. Complete the welcome setup first.", 401)


# ------------------------------------------------------------------ validation

def v_date(value, field="date") -> str:
    value = str(value or "")
    if not DATE_RE.match(value):
        raise ValueError(f"{field} must look like YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field} is not a real calendar date")
    return value


def v_number(value, field, lo, hi, integer=False):
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number")
    if integer:
        if float(num).is_integer() is False:
            raise ValueError(f"{field} must be a whole number")
        num = int(num)
    if not (lo <= num <= hi):
        raise ValueError(f"{field} must be between {lo} and {hi}")
    return num


def v_str_list(value, field, max_items=20, max_len=80):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list of short texts")
    out = []
    for item in value[:max_items]:
        item = str(item).strip()
        if item:
            out.append(item[:max_len])
    return out


# ------------------------------------------------------------------ bootstrap & users

def targets_for(profile: dict, settings: dict) -> dict | None:
    """Personalised targets — an ESTIMATE, labelled as such. Returns None when
    information is insufficient (the UI then asks the user to complete profile)."""
    if not (profile.get("age") and profile.get("sex") and profile.get("height_cm")
            and profile.get("weight_kg")):
        return None
    kcal = nutrition.calorie_target(profile["weight_kg"], profile["height_cm"],
                                    profile["age"], profile["sex"],
                                    profile.get("activity", "moderate"),
                                    profile.get("goal", "maintain"))
    macros = nutrition.macro_targets(kcal, profile.get("macro_model", "balanced"))
    return {
        "kcal": round(kcal),
        "protein_g": macros["protein_g"], "carbs_g": macros["carbs_g"],
        "fat_g": macros["fat_g"],
        "water_ml": settings["water_goal_ml"],
        "micro": nutrition.micro_targets(profile["sex"]),
        "bmr": round(nutrition.mifflin_st_jeor_bmr(
            profile["weight_kg"], profile["height_cm"], profile["age"], profile["sex"])),
        "estimate_note": ("Estimate only: Mifflin-St Jeor BMR × activity factor, "
                          "± goal adjustment. Not a diagnosis or medical advice; "
                          "edit any input in Health Profile."),
    }


def bootstrap_payload(conn):
    uid = current_uid(conn)
    base = {"assistant": assistant.engine_mode(), "today": db.today(),
            "meals": db.MEALS, "user": None}
    if uid is None:
        return base
    user = db.get_user(conn, uid)
    profile = db.get_profile(conn, uid)
    settings = db.get_settings(conn, uid)
    base.update({
        "user": {"id": user["id"], "name": user["name"]},
        "profile": profile,
        "settings": settings,
        "targets": targets_for(profile, settings),
        "demo_mode": settings.get("demo_mode", False),
    })
    return base


@api.get("/bootstrap")
def bootstrap():
    return jsonify(bootstrap_payload(db.get_db()))


@api.post("/users")
def create_user():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()[:60]
    if not name:
        return err("Please choose a display name (it never leaves this device).")
    conn = db.get_db()
    uid = db.create_user(conn, name)
    session["uid"] = uid
    return jsonify(bootstrap_payload(conn)), 201


@api.put("/users/me")
def rename_user():
    data = request.get_json(silent=True) or {}
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    name = str(data.get("name") or "").strip()[:60]
    if not name:
        return err("Display name cannot be empty")
    conn.execute("UPDATE users SET name = ? WHERE id = ?", (name, uid))
    conn.commit()
    return jsonify(bootstrap_payload(conn))


@api.get("/users")
def list_users():
    conn = db.get_db()
    return jsonify({"users": db.list_users(conn), "current": current_uid(conn),
                    "note": "Local profiles only — no passwords. Anyone using this "
                            "browser can switch profiles; this organises data, it does "
                            "not secure it."})


@api.post("/users/switch")
def switch_user():
    data = request.get_json(silent=True) or {}
    conn = db.get_db()
    try:
        uid = int(v_number(data.get("id"), "id", 1, 10**9, integer=True))
    except (ValueError, TypeError):
        return err("id must be a whole number")
    if not db.get_user(conn, uid):
        return err("Unknown user id", 404)
    session["uid"] = uid
    return jsonify(bootstrap_payload(conn))


@api.delete("/users/<int:uid>")
def delete_user(uid):
    conn = db.get_db()
    if not db.get_user(conn, uid):
        return err("Unknown user id", 404)
    db.delete_user(conn, uid)
    if session.get("uid") == uid:
        session.pop("uid", None)
    return jsonify({"ok": True})


# ------------------------------------------------------------------ profile

def _optional(cast):
    def wrapper(value):
        if value is None or value == "":
            return None
        return cast(value)
    return wrapper


PROFILE_FIELDS = {
    "age": _optional(lambda v: v_number(v, "age", 10, 120, integer=True)),
    "sex": _optional(lambda v: v if v in ("female", "male", "other") else (_ for _ in ()).throw(
        ValueError("sex must be female, male or other"))),
    "height_cm": _optional(lambda v: v_number(v, "height", 50, 250)),
    "weight_kg": _optional(lambda v: v_number(v, "weight", 20, 300)),
    "activity": lambda v: v if v in nutrition.ACTIVITY_FACTORS else (_ for _ in ()).throw(
        ValueError("unknown activity level")),
    "goal": lambda v: v if v in nutrition.GOAL_DELTAS else (_ for _ in ()).throw(
        ValueError("unknown goal")),
    "macro_model": lambda v: v if v in nutrition.MACRO_MODELS else (_ for _ in ()).throw(
        ValueError("unknown macro model")),
    "units": lambda v: v if v in ("metric", "imperial") else (_ for _ in ()).throw(
        ValueError("units must be metric or imperial")),
    "medical_history": lambda v: str(v or "")[:500],
}


@api.get("/profile")
def get_profile():
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    profile = db.get_profile(conn, uid)
    return jsonify({"profile": profile,
                    "targets": targets_for(profile, db.get_settings(conn, uid))})


@api.put("/profile")
def put_profile():
    data = request.get_json(silent=True) or {}
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    updates, lists = {}, {}
    try:
        for field, cast in PROFILE_FIELDS.items():
            if field in data:
                updates[field] = cast(data[field])
        for field in ("dietary_prefs", "allergies", "medications"):
            if field in data:
                lists[field] = json.dumps(v_str_list(data[field], field))
    except ValueError as exc:
        return err(str(exc))
    updates["updated_at"] = db.now()
    sets = ", ".join(f"{k} = ?" for k in list(updates) + list(lists))
    conn.execute(f"UPDATE profile SET {sets} WHERE user_id = ?",
                 list(updates.values()) + list(lists.values()) + [uid])
    conn.commit()
    profile = db.get_profile(conn, uid)
    return jsonify({"profile": profile,
                    "targets": targets_for(profile, db.get_settings(conn, uid))})


@api.post("/profile/purge")
def purge():
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    db.purge_user_data(conn, uid)
    return jsonify({"ok": True, "message": "All personal data for this profile deleted."})


# ------------------------------------------------------------------ demo mode

@api.post("/demo/load")
def demo_load():
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    if not db.load_demo_data(conn, uid):
        return err("Demo mode needs an empty log so fictional and real data never "
                   "mix. Delete your logs (or use another local profile) first.")
    return jsonify(bootstrap_payload(conn))


@api.post("/demo/clear")
def demo_clear():
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    db.clear_demo_data(conn, uid)
    return jsonify(bootstrap_payload(conn))


# ------------------------------------------------------------------ foods (shared, non-personal)

@api.get("/foods")
def foods():
    q = (request.args.get("q") or "").strip().lower()
    limit = max(1, min(int(request.args.get("limit", 12)), 250))
    conn = db.get_db()
    if q:
        rows = conn.execute(
            "SELECT * FROM foods WHERE lower(name) LIKE ? OR lower(grp) LIKE ? "
            "ORDER BY name LIMIT ?", (f"%{q}%", f"%{q}%", limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM foods ORDER BY name LIMIT ?", (limit,)).fetchall()
    foods_list = [dict(r) for r in rows]
    # Dietary/allergy filtering for authenticated users: uses explicit dietary/allergen
    # metadata as primary source of truth (data/foods.json), not name substrings.
    # Preserves history: only affects search, not stored meals.
    try:
        uid = current_uid(conn)
        if uid is not None:
            profile = db.get_profile(conn, uid)
            prefs = profile.get("dietary_prefs")
            allergies = profile.get("allergies")
            if prefs or allergies:
                from . import insights as _insights
                filtered = []
                for f in foods_list:
                    if not _insights.is_excluded(f, allergies, prefs):
                        filtered.append(f)
                foods_list = filtered
    except Exception:
        pass
    return jsonify({"foods": foods_list})


# ------------------------------------------------------------------ meals

def meal_entry_payload(conn, row) -> dict:
    entry = dict(row)
    entry.pop("user_id", None)
    food = None
    if entry.get("food_id"):
        frow = conn.execute("SELECT * FROM foods WHERE id = ?", (entry["food_id"],)).fetchone()
        food = dict(frow) if frow else None
    entry["food"] = food
    entry["display_name"] = food["name"] if food else (entry.get("custom_name") or "Custom item")
    entry["nutrients"] = nutrition.entry_nutrients(entry, food)
    return entry


@api.get("/meals")
def get_meals():
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    try:
        day = v_date(request.args.get("date", db.today()))
    except ValueError as exc:
        return err(str(exc))
    rows = conn.execute(
        "SELECT * FROM meal_entries WHERE user_id = ? AND date = ? ORDER BY id",
        (uid, day)).fetchall()
    grouped = {m: [] for m in db.MEALS}
    for row in rows:
        payload = meal_entry_payload(conn, row)
        grouped.setdefault(payload["meal"], []).append(payload)
    totals = nutrition.sum_nutrients(
        [e["nutrients"] for group in grouped.values() for e in group])
    return jsonify({"date": day, "meals": grouped, "totals": totals,
                    "logged_count": sum(len(v) for v in grouped.values())})


@api.post("/meals")
def create_meal():
    data = request.get_json(silent=True) or {}
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    try:
        day = v_date(data.get("date", db.today()))
        meal = data.get("meal")
        if meal not in db.MEALS:
            raise ValueError(f"meal must be one of {db.MEALS}")
        quantity = v_number(data.get("quantity"), "quantity", 0.01, 1000)
        unit = data.get("unit")
        if unit not in ("serving", "g"):
            raise ValueError("unit must be 'serving' or 'g'")
        food_id = data.get("food_id")
        custom = None
        if food_id in (None, "", 0):
            food_id = None
            custom = str(data.get("custom_name") or "").strip()[:80]
            if not custom:
                raise ValueError("custom_name is required when food_id is not given")
            for field in ("custom_kcal", "custom_protein_g", "custom_carbs_g", "custom_fat_g"):
                if data.get(field) is not None:
                    v_number(data[field], field, 0, 100000)
        else:
            food_id = int(v_number(food_id, "food_id", 1, 10**9, integer=True))
            frow = conn.execute("SELECT * FROM foods WHERE id = ?", (food_id,)).fetchone()
            if not frow:
                raise ValueError("food_id not found in database")
            # Dietary/allergy guard: reject incompatible foods for this user's preferences.
            # Uses explicit dietary/allergen metadata as primary truth, not name matching.
            # Preserves history: existing meals (different food_id) are not affected.
            food_dict = dict(frow)
            try:
                profile = db.get_profile(conn, uid)
                from . import insights as _insights
                if _insights.is_excluded(food_dict, profile.get("allergies"), profile.get("dietary_prefs")):
                    raise ValueError(f"This food is incompatible with your dietary preference ({', '.join(profile.get('dietary_prefs') or [])}) or allergy and cannot be added. Historical meals are preserved.")
            except ValueError:
                raise
            except Exception:
                pass
        if unit == "serving" and food_id is None:
            raise ValueError("custom entries must use unit 'g'")
    except (ValueError, TypeError) as exc:
        return err(str(exc))
    cur = conn.execute(
        "INSERT INTO meal_entries (user_id, date, meal, food_id, custom_name, quantity,"
        " unit, custom_kcal, custom_protein_g, custom_carbs_g, custom_fat_g, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (uid, day, meal, food_id, custom, quantity, unit,
         data.get("custom_kcal"), data.get("custom_protein_g"),
         data.get("custom_carbs_g"), data.get("custom_fat_g"), db.now()))
    conn.commit()
    row = conn.execute("SELECT * FROM meal_entries WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify({"entry": meal_entry_payload(conn, row)}), 201


@api.put("/meals/<int:entry_id>")
def update_meal(entry_id):
    data = request.get_json(silent=True) or {}
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    row = conn.execute("SELECT * FROM meal_entries WHERE id = ? AND user_id = ?",
                       (entry_id, uid)).fetchone()
    if not row:
        return err("meal entry not found", 404)
    entry = dict(row)
    try:
        if "date" in data:
            entry["date"] = v_date(data["date"])
        if "meal" in data:
            if data["meal"] not in db.MEALS:
                raise ValueError(f"meal must be one of {db.MEALS}")
            entry["meal"] = data["meal"]
        if "quantity" in data:
            entry["quantity"] = v_number(data["quantity"], "quantity", 0.01, 1000)
        if "unit" in data:
            if data["unit"] not in ("serving", "g"):
                raise ValueError("unit must be 'serving' or 'g'")
            entry["unit"] = data["unit"]
    except (ValueError, TypeError) as exc:
        return err(str(exc))
    conn.execute(
        "UPDATE meal_entries SET date=?, meal=?, quantity=?, unit=? WHERE id=? AND user_id=?",
        (entry["date"], entry["meal"], entry["quantity"], entry["unit"], entry_id, uid))
    conn.commit()
    row = conn.execute("SELECT * FROM meal_entries WHERE id = ?", (entry_id,)).fetchone()
    return jsonify({"entry": meal_entry_payload(conn, row)})


@api.delete("/meals/<int:entry_id>")
def delete_meal(entry_id):
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    cur = conn.execute("DELETE FROM meal_entries WHERE id = ? AND user_id = ?",
                       (entry_id, uid))
    conn.commit()
    if cur.rowcount == 0:
        return err("meal entry not found", 404)
    return jsonify({"ok": True})


# ------------------------------------------------------------------ water

@api.get("/water")
def get_water():
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    try:
        day = v_date(request.args.get("date", db.today()))
    except ValueError as exc:
        return err(str(exc))
    rows = conn.execute("SELECT * FROM water_logs WHERE user_id = ? AND date = ? ORDER BY id",
                        (uid, day)).fetchall()
    logs = [dict(r) for r in rows]
    for log in logs:
        log.pop("user_id", None)
    return jsonify({"date": day, "logs": logs,
                    "total_ml": sum(r["amount_ml"] for r in rows)})


@api.post("/water")
def add_water():
    data = request.get_json(silent=True) or {}
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    try:
        day = v_date(data.get("date", db.today()))
        amount = int(v_number(data.get("amount_ml"), "amount_ml", 10, 3000, integer=True))
    except (ValueError, TypeError) as exc:
        return err(str(exc))
    cur = conn.execute(
        "INSERT INTO water_logs (user_id, date, amount_ml, created_at) VALUES (?, ?, ?, ?)",
        (uid, day, amount, db.now()))
    conn.commit()
    total = conn.execute("SELECT SUM(amount_ml) t FROM water_logs WHERE user_id = ? AND date = ?",
                         (uid, day)).fetchone()["t"] or 0
    return jsonify({"ok": True, "total_ml": total, "id": cur.lastrowid}), 201


@api.delete("/water/<int:log_id>")
def delete_water(log_id):
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    cur = conn.execute("DELETE FROM water_logs WHERE id = ? AND user_id = ?", (log_id, uid))
    conn.commit()
    if cur.rowcount == 0:
        return err("water log not found", 404)
    return jsonify({"ok": True})


# ------------------------------------------------------------------ summary & reports

def day_rows(conn, uid, day):
    rows = conn.execute(
        "SELECT * FROM meal_entries WHERE user_id = ? AND date = ? ORDER BY id",
        (uid, day)).fetchall()
    return [meal_entry_payload(conn, row) for row in rows]


@api.get("/summary")
def summary():
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    try:
        day = v_date(request.args.get("date", db.today()))
    except ValueError as exc:
        return err(str(exc))
    profile = db.get_profile(conn, uid)
    settings = db.get_settings(conn, uid)
    entries = day_rows(conn, uid, day)
    totals = nutrition.sum_nutrients([e["nutrients"] for e in entries])
    water = conn.execute("SELECT SUM(amount_ml) t FROM water_logs WHERE user_id = ? AND date = ?",
                         (uid, day)).fetchone()["t"] or 0
    grouped = {m: [] for m in db.MEALS}
    for entry in entries:
        grouped[entry["meal"]].append(entry)
    return jsonify({"date": day, "totals": totals, "water_ml": water,
                    "water_goal_ml": settings["water_goal_ml"],
                    "logged_count": len(entries),
                    "targets": targets_for(profile, settings),
                    "meals": grouped, "profile": profile})


@api.get("/report")
def report():
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    try:
        days = int(v_number(request.args.get("days", 7), "days", 1, 90, integer=True))
    except (ValueError, TypeError) as exc:
        return err(str(exc))
    profile = db.get_profile(conn, uid)
    settings = db.get_settings(conn, uid)
    targets = targets_for(profile, settings)
    today = date.today()
    per_day, food_counts = [], {}
    micro_sum = {k: 0.0 for k in ("fiber_g", "sodium_mg", "potassium_mg",
                                  "calcium_mg", "iron_mg")}
    meal_days = 0
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        entries = day_rows(conn, uid, day)
        totals = nutrition.sum_nutrients([e["nutrients"] for e in entries])
        water = conn.execute(
            "SELECT SUM(amount_ml) t FROM water_logs WHERE user_id = ? AND date = ?",
            (uid, day)).fetchone()["t"] or 0
        per_day.append({"date": day, **totals, "water_ml": water,
                        "logged_count": len(entries),
                        "meal_count": len({e["meal"] for e in entries})})
        if len({e["meal"] for e in entries}) >= 3:
            meal_days += 1
        for entry in entries:
            food_counts[entry["display_name"]] = food_counts.get(entry["display_name"], 0) + 1
            for key in micro_sum:
                micro_sum[key] += entry["nutrients"].get(key, 0.0)
    n = max(days, 1)
    logged_days = sum(1 for d in per_day if d["logged_count"] > 0)
    macro_totals = nutrition.sum_nutrients(per_day)
    water_total = sum(d["water_ml"] for d in per_day)
    top_foods = sorted(food_counts.items(), key=lambda kv: -kv[1])[:6]
    return jsonify({
        "days": days,
        "per_day": per_day,
        "logged_days": logged_days,
        "averages": {
            "kcal": round(macro_totals["kcal"] / logged_days) if logged_days else 0,
            "protein_g": round(macro_totals["protein_g"] / logged_days, 1) if logged_days else 0,
            "carbs_g": round(macro_totals["carbs_g"] / logged_days, 1) if logged_days else 0,
            "fat_g": round(macro_totals["fat_g"] / logged_days, 1) if logged_days else 0,
            "water_ml": round(water_total / logged_days) if logged_days else 0,
        },
        "macro_totals": macro_totals,
        "micro_avg": {k: round(v / logged_days, 1) if logged_days else 0.0
                      for k, v in micro_sum.items()},
        "micro_targets": nutrition.micro_targets(profile.get("sex") or "other"),
        "top_foods": [{"name": k, "times": v} for k, v in top_foods],
        "meal_consistency_pct": round(100.0 * meal_days / logged_days) if logged_days else 0,
        "targets": targets,
    })


@api.get("/report.csv")
def report_csv():
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    try:
        days = int(v_number(request.args.get("days", 7), "days", 1, 90, integer=True))
    except (ValueError, TypeError) as exc:
        return err(str(exc))
    today = date.today()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "meal", "food", "quantity", "unit", "grams",
                     "kcal", "protein_g", "carbs_g", "fat_g"])
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        for entry in day_rows(conn, uid, day):
            n = entry["nutrients"]
            writer.writerow([day, entry["meal"], entry["display_name"],
                             entry["quantity"], entry["unit"], n["grams"],
                             n["kcal"], n["protein_g"], n["carbs_g"], n["fat_g"]])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":
                             f'attachment; filename="nutricare-report-{days}d.csv"'})


@api.get("/export.json")
def export_json():
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    return jsonify({
        "exported_at": db.now(),
        "user": db.get_user(conn, uid),
        "profile": db.get_profile(conn, uid),
        "settings": db.get_settings(conn, uid),
        "meals": [dict(r) for r in conn.execute(
            "SELECT * FROM meal_entries WHERE user_id = ?", (uid,))],
        "water": [dict(r) for r in conn.execute(
            "SELECT * FROM water_logs WHERE user_id = ?", (uid,))],
        "assessments": [dict(r) for r in conn.execute(
            "SELECT id, created_at, emergency FROM assessments WHERE user_id = ?", (uid,))],
    })


# ------------------------------------------------------------------ assistant

@api.post("/assistant/assess")
def assess():
    data = request.get_json(silent=True) or {}
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    profile = db.get_profile(conn, uid)
    try:
        result = assistant.assess(data, profile)
    except ValueError as exc:
        return err(str(exc))
    conn.execute(
        "INSERT INTO assessments (user_id, created_at, emergency, payload, result) "
        "VALUES (?, ?, ?, ?, ?)",
        (uid, db.now(), 1 if result["triage"] == "emergency" else 0,
         json.dumps(data), json.dumps(result)))
    conn.commit()
    return jsonify(result)


@api.get("/assistant/history")
def assistant_history():
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    rows = conn.execute(
        "SELECT id, created_at, emergency, payload FROM assessments "
        "WHERE user_id = ? ORDER BY id DESC LIMIT 20", (uid,)).fetchall()
    out = []
    for row in rows:
        payload = json.loads(row["payload"] or "{}")
        out.append({"id": row["id"], "created_at": row["created_at"],
                    "emergency": bool(row["emergency"]),
                    "primary": payload.get("primary", "")})
    return jsonify({"history": out})


@api.get("/assistant/warning-signs")
def warning_signs():
    return jsonify({"warning_signs": [
        {"id": s["id"], "label": s["label"]} for s in assistant.WARNING_SIGNS]})


# ------------------------------------------------------------------ settings

@api.get("/settings")
def get_settings():
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    return jsonify(db.get_settings(conn, uid))


@api.put("/settings")
def put_settings():
    data = request.get_json(silent=True) or {}
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    try:
        if "water_goal_ml" in data:
            value = int(v_number(data["water_goal_ml"], "water_goal_ml", 500, 6000, integer=True))
            db.set_setting(conn, uid, "water_goal_ml", str(value))
        for key in ("privacy_research", "privacy_ai", "privacy_sync"):
            if key in data:
                if not isinstance(data[key], bool):
                    raise ValueError(f"{key} must be true/false")
                db.set_setting(conn, uid, key, "1" if data[key] else "0")
    except (ValueError, TypeError) as exc:
        return err(str(exc))
    conn.commit()
    return jsonify(db.get_settings(conn, uid))


# ------------------------------------------------------- smart nutrition insights
# Read-only analytics over existing tables (no schema changes, no writes).
# All computation lives in insights.py; these endpoints only gather rows with
# the same per-user isolation (WHERE user_id = ?) as every other endpoint.

@api.get("/insights")
def daily_insights():
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    try:
        day = v_date(request.args.get("date", db.today()))
    except ValueError as exc:
        return err(str(exc))
    profile = db.get_profile(conn, uid)
    settings = db.get_settings(conn, uid)
    entries = day_rows(conn, uid, day)
    totals = nutrition.sum_nutrients([e["nutrients"] for e in entries])
    water = conn.execute("SELECT SUM(amount_ml) t FROM water_logs WHERE user_id = ? AND date = ?",
                         (uid, day)).fetchone()["t"] or 0
    foods = [dict(r) for r in conn.execute("SELECT * FROM foods ORDER BY id")]
    return jsonify(insights.daily_payload(
        date=day, entries=entries, totals=totals, water_ml=water,
        water_goal_ml=settings["water_goal_ml"],
        targets=targets_for(profile, settings), profile=profile, foods=foods))


@api.get("/insights/weekly")
def weekly_insights():
    conn = db.get_db()
    uid = current_uid(conn)
    if uid is None:
        return no_user()
    profile = db.get_profile(conn, uid)
    settings = db.get_settings(conn, uid)
    today = date.today()
    per_day = []
    for offset in range(13, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        entries = day_rows(conn, uid, day)
        totals = nutrition.sum_nutrients([e["nutrients"] for e in entries])
        water = conn.execute(
            "SELECT SUM(amount_ml) t FROM water_logs WHERE user_id = ? AND date = ?",
            (uid, day)).fetchone()["t"] or 0
        per_day.append({
            "date": day, **totals, "water_ml": water, "logged_count": len(entries),
            "food_names": [e["display_name"] for e in entries],
            "groups": sorted({e["food"]["grp"] for e in entries if e.get("food")}),
            "has_dataset_entry": any(e.get("food") for e in entries),
        })
    return jsonify(insights.weekly_payload(
        per_day, targets_for(profile, settings), settings["water_goal_ml"], profile))
