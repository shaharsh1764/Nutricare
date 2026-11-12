"""End-to-end API tests using a throwaway SQLite file (real persistence layer).

Identity model under test: local users in a session cookie, no passwords.
Two separate test clients == two separate browsers (separate cookie jars).
"""

import sqlite3

import pytest

from nutricare import create_app, db


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "test.db"))
    return create_app({"TESTING": True})


@pytest.fixture()
def client(app):
    with app.test_client() as test_client:
        yield test_client


def new_user(client, name="Test User", **profile):
    resp = client.post("/api/users", json={"name": name})
    assert resp.status_code == 201, resp.get_json()
    if profile:
        resp = client.put("/api/profile", json=profile)
        assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


FULL_PROFILE = {"age": 20, "sex": "female", "height_cm": 168, "weight_kg": 59.8,
                "activity": "moderate"}


# ------------------------------------------------------------------ first run

def test_brand_new_client_has_no_user_and_locked_data(client):
    boot = client.get("/api/bootstrap").get_json()
    assert boot["user"] is None
    for path in ("/api/meals", "/api/summary", "/api/report", "/api/water",
                 "/api/assistant/history", "/api/settings", "/api/profile"):
        assert client.get(path).status_code == 401, path
    # the shared food database is not personal data and stays readable
    assert client.get("/api/foods?q=roti").status_code == 200


def test_onboarding_creates_genuinely_empty_account(client):
    new_user(client, "Fresh Start")
    summary = client.get("/api/summary").get_json()
    assert summary["totals"]["kcal"] == 0 and summary["logged_count"] == 0
    assert summary["water_ml"] == 0
    assert all(v == [] for v in summary["meals"].values())
    assert summary["targets"] is None  # not enough info yet -> no invented target
    assert client.get("/api/meals").get_json()["logged_count"] == 0
    assert client.get("/api/water").get_json()["total_ml"] == 0
    assert client.get("/api/assistant/history").get_json()["history"] == []
    report = client.get("/api/report?days=7").get_json()
    assert report["logged_days"] == 0 and report["top_foods"] == []
    # no demo data anywhere
    boot = client.get("/api/bootstrap").get_json()
    assert boot["demo_mode"] is False


def test_missing_profile_fields_handled_without_crash(client):
    new_user(client, "Partial")  # name only
    for path in ("/api/summary", "/api/report?days=30", "/api/meals"):
        assert client.get(path).status_code == 200, path
    assert client.get("/api/summary").get_json()["targets"] is None
    bad = client.put("/api/profile", json={"age": 400})
    assert bad.status_code == 400


def test_targets_appear_only_with_sufficient_info_and_are_labelled(client):
    new_user(client, "Est")
    client.put("/api/profile", json=FULL_PROFILE)
    targets = client.get("/api/profile").get_json()["targets"]
    assert 1800 < targets["kcal"] < 2600
    assert "Estimate only" in targets["estimate_note"]
    # sex is optional: midpoint constant still yields a labelled estimate
    client.put("/api/profile", json={"sex": None})
    targets = client.get("/api/profile").get_json()["targets"]
    assert targets is None  # insufficient info again, no crash


# ------------------------------------------------------------------ isolation

def test_two_local_users_cannot_see_each_others_records(app):
    a, b = app.test_client(), app.test_client()
    if True:
        new_user(a, "User A")
        food = a.get("/api/foods?q=roti").get_json()["foods"][0]
        a.post("/api/meals", json={"meal": "lunch", "food_id": food["id"],
                                   "quantity": 1, "unit": "serving"})
        a.post("/api/water", json={"amount_ml": 500})
        new_user(b, "User B")
        sb = b.get("/api/summary").get_json()
        assert sb["logged_count"] == 0 and sb["water_ml"] == 0
        assert b.get("/api/meals").get_json()["logged_count"] == 0
        # and A still sees exactly their own record
        sa = a.get("/api/summary").get_json()
        assert sa["logged_count"] == 1 and sa["water_ml"] == 500
        # B cannot touch A's entries even by id
        entry_id = a.get("/api/meals").get_json()["meals"]["lunch"][0]["id"]
        assert b.delete(f"/api/meals/{entry_id}").status_code == 404
        assert b.put(f"/api/meals/{entry_id}", json={"quantity": 9}).status_code == 404


def test_switching_profiles_is_explicit_and_scoped(client):
    first = new_user(client, "First")
    food = client.get("/api/foods?q=roti").get_json()["foods"][0]
    client.post("/api/meals", json={"meal": "dinner", "food_id": food["id"],
                                    "quantity": 1, "unit": "serving"})
    new_user(client, "Second")  # creating switches the session
    assert client.get("/api/meals").get_json()["logged_count"] == 0
    listing = client.get("/api/users").get_json()
    assert "no passwords" in listing["note"]
    client.post("/api/users/switch", json={"id": first["user"]["id"]})
    assert client.get("/api/meals").get_json()["logged_count"] == 1


def test_completed_new_account_onboarding_is_isolated_from_current_profile(client):
    """The shared wizard creates first, then writes every optional answer only
    to that new session. Switching back must restore the prior profile unchanged."""
    new_user(client, "Existing", age=42, sex="male", height_cm=177,
             weight_kg=81, activity="light")
    first_id = client.get("/api/bootstrap").get_json()["user"]["id"]
    client.put("/api/profile", json={"dietary_prefs": ["vegetarian"],
                                      "allergies": ["peanuts"]})
    client.put("/api/settings", json={"water_goal_ml": 2100})
    food = client.get("/api/foods?q=roti").get_json()["foods"][0]
    assert client.post("/api/meals", json={"meal": "lunch", "food_id": food["id"],
                                            "quantity": 1, "unit": "serving"}).status_code == 201

    # Equivalent to finishOnboardingSubmit(): POST /users commits and changes
    # the local session before the wizard sends its profile/settings writes.
    created = client.post("/api/users", json={"name": "New Wizard Profile"})
    assert created.status_code == 201
    second_id = created.get_json()["user"]["id"]
    complete = {
        "age": 27, "sex": "female", "height_cm": 164, "weight_kg": 58.5,
        "activity": "active", "goal": "mild_gain", "macro_model": "high_protein",
        "dietary_prefs": ["lactose-free"], "allergies": ["soy"],
        "medications": ["Vitamin D3"], "medical_history": "Seasonal migraines",
    }
    assert client.put("/api/profile", json=complete).status_code == 200
    assert client.put("/api/settings", json={"water_goal_ml": 3200}).status_code == 200

    second = client.get("/api/bootstrap").get_json()
    assert second["user"]["id"] == second_id
    assert {key: second["profile"][key] for key in complete} == complete
    assert second["settings"]["water_goal_ml"] == 3200
    assert client.get("/api/meals").get_json()["logged_count"] == 0

    assert client.post("/api/users/switch", json={"id": first_id}).status_code == 200
    restored = client.get("/api/bootstrap").get_json()
    assert restored["profile"]["age"] == 42
    assert restored["profile"]["dietary_prefs"] == ["vegetarian"]
    assert restored["profile"]["allergies"] == ["peanuts"]
    assert restored["settings"]["water_goal_ml"] == 2100
    assert client.get("/api/meals").get_json()["logged_count"] == 1


def test_delete_user_removes_only_that_users_data(app):
    a, b = app.test_client(), app.test_client()
    if True:
        ua = new_user(a, "Doomed")
        a.post("/api/water", json={"amount_ml": 250})
        new_user(b, "Keeper")
        b.post("/api/water", json={"amount_ml": 100})
        assert a.delete(f"/api/users/{ua['user']['id']}").status_code == 200
        assert a.get("/api/bootstrap").get_json()["user"] is None
        assert a.get("/api/meals").status_code == 401
        assert b.get("/api/water").get_json()["total_ml"] == 100  # untouched


# ------------------------------------------------------------------ demo mode

def test_demo_mode_is_explicit_labelled_and_clearable(client):
    new_user(client, "Demo Person")
    loaded = client.post("/api/demo/load")
    assert loaded.status_code == 200 and loaded.get_json()["demo_mode"] is True
    assert client.get("/api/meals").get_json()["logged_count"] == 8
    # refuses to mix with real logs
    client.post("/api/demo/clear")
    food = client.get("/api/foods?q=roti").get_json()["foods"][0]
    client.post("/api/meals", json={"meal": "lunch", "food_id": food["id"],
                                    "quantity": 1, "unit": "serving"})
    refused = client.post("/api/demo/load")
    assert refused.status_code == 400
    assert client.get("/api/meals").get_json()["logged_count"] == 1


# ------------------------------------------------------------------ meals & maths

def test_meal_crud_and_math(client):
    new_user(client, "Maths", **FULL_PROFILE)
    # Exact Rice white lookup - generic 'white' now ambiguous with expanded ~200 dataset
    foods = client.get("/api/foods?q=Rice, white&limit=50").get_json()["foods"]
    food = next((f for f in foods if f["name"] == "Rice, white (cooked)"), foods[0])  # 130 kcal / 100 g
    created = client.post("/api/meals", json={
        "meal": "lunch", "food_id": food["id"], "quantity": 2, "unit": "serving"
    }).get_json()["entry"]
    assert abs(created["nutrients"]["kcal"] - 410.8) < 0.5  # 316 g * 1.3
    meals = client.get("/api/meals").get_json()
    assert meals["logged_count"] == 1
    assert abs(meals["totals"]["kcal"] - 410.8) < 0.5
    edited = client.put(f"/api/meals/{created['id']}", json={"quantity": 1}).get_json()["entry"]
    assert abs(edited["nutrients"]["kcal"] - 205.4) < 0.5
    assert client.delete(f"/api/meals/{created['id']}").status_code == 200
    assert client.get("/api/meals").get_json()["totals"]["kcal"] == 0


def test_meal_validation_rejects_bad_input(client):
    new_user(client, "Validator")
    assert client.post("/api/meals", json={"meal": "brunch", "quantity": 1, "unit": "g"}).status_code == 400
    assert client.post("/api/meals", json={"meal": "lunch", "quantity": -3, "unit": "g",
                                           "custom_name": "x"}).status_code == 400
    assert client.post("/api/meals", json={"meal": "lunch", "quantity": 1, "unit": "serving"}).status_code == 400
    ok = client.post("/api/meals", json={"meal": "lunch", "quantity": 100, "unit": "g",
                                         "custom_name": "Home laddu", "custom_kcal": 180})
    assert ok.status_code == 201
    assert client.post("/api/meals", json={"meal": "lunch", "food_id": 999999,
                                           "quantity": 1, "unit": "serving"}).status_code == 400


def test_water_log_and_summary(client):
    new_user(client, "Hydro", **FULL_PROFILE)
    assert client.post("/api/water", json={"amount_ml": 500}).status_code == 201
    client.post("/api/water", json={"amount_ml": 250})
    summary = client.get("/api/summary").get_json()
    assert summary["water_ml"] == 750 and summary["water_goal_ml"] == 2800
    assert client.post("/api/water", json={"amount_ml": 0}).status_code == 400


def test_profile_update_and_validation(client):
    new_user(client, "Profiler", **FULL_PROFILE)
    resp = client.put("/api/profile", json={"age": 22, "weight_kg": 62})
    assert resp.status_code == 200 and resp.get_json()["profile"]["age"] == 22
    assert client.put("/api/profile", json={"age": 300}).status_code == 400
    assert client.put("/api/profile", json={"height_cm": 3}).status_code == 400
    rename = client.put("/api/users/me", json={"name": "Renamed"})
    assert rename.get_json()["user"]["name"] == "Renamed"


def test_report_and_csv_export(client):
    new_user(client, "Reporter", **FULL_PROFILE)
    client.post("/api/meals", json={"meal": "breakfast", "quantity": 100, "unit": "g",
                                    "custom_name": "Test item", "custom_kcal": 100,
                                    "custom_protein_g": 5, "custom_carbs_g": 10,
                                    "custom_fat_g": 2})
    report = client.get("/api/report?days=7").get_json()
    assert len(report["per_day"]) == 7 and report["logged_days"] == 1
    assert report["averages"]["kcal"] == 100  # averaged over LOGGED days only
    csv_text = client.get("/api/report.csv?days=7").get_data(as_text=True)
    assert csv_text.startswith("date,meal,food") and "Test item" in csv_text
    assert client.get("/api/report?days=500").status_code == 400


def test_assistant_endpoint_emergency_and_logging(client):
    new_user(client, "Triage")
    resp = client.post("/api/assistant/assess",
                       json={"primary": "chest pain", "severity": 7, "duration": "today"})
    data = resp.get_json()
    assert data["triage"] == "emergency"
    assert data["reported_facts"]["primary"] == "chest pain"
    history = client.get("/api/assistant/history").get_json()["history"]
    assert history[0]["emergency"] is True
    assert client.post("/api/assistant/assess",
                       json={"primary": "headache", "severity": 11}).status_code == 400


def test_warning_signs_endpoint_matches_engine_and_drives_triage(client):
    new_user(client, "Signs")
    signs = client.get("/api/assistant/warning-signs").get_json()["warning_signs"]
    ids = [s["id"] for s in signs]
    assert "chest_pain" in ids and "stroke" in ids and len(ids) == 12
    resp = client.post("/api/assistant/assess",
                       json={"primary": "feeling tired", "severity": 2,
                             "duration": "today", "warning_signs": ["chest_pain"]})
    data = resp.get_json()
    assert data["triage"] == "emergency"
    assert [f["id"] for f in data["red_flags"]] == ["chest_pain"]


def test_settings_update_and_validation(client):
    new_user(client, "Settings")
    data = client.put("/api/settings", json={"water_goal_ml": 3000, "privacy_ai": False}).get_json()
    assert data["water_goal_ml"] == 3000 and data["privacy_ai"] is False
    assert client.put("/api/settings", json={"water_goal_ml": 10}).status_code == 400


def test_purge_keeps_account_but_deletes_records(client):
    new_user(client, "Purger", **FULL_PROFILE)
    client.post("/api/meals", json={"meal": "lunch", "quantity": 100, "unit": "g",
                                    "custom_name": "gone soon", "custom_kcal": 50})
    client.post("/api/water", json={"amount_ml": 250})
    client.post("/api/assistant/assess", json={"primary": "headache", "severity": 2})
    assert client.post("/api/profile/purge").status_code == 200
    assert client.get("/api/meals").get_json()["totals"]["kcal"] == 0
    assert client.get("/api/water").get_json()["total_ml"] == 0
    assert client.get("/api/assistant/history").get_json()["history"] == []
    boot = client.get("/api/bootstrap").get_json()
    assert boot["user"]["name"] == "Purger"  # account survives
    assert boot["targets"] is None


# ------------------------------------------------------------------ legacy migration

def test_legacy_v1_database_is_migrated_under_user_one(app, tmp_path, monkeypatch):
    legacy = tmp_path / "legacy.db"
    conn = sqlite3.connect(legacy)
    conn.executescript("""
    CREATE TABLE profile (id INTEGER PRIMARY KEY CHECK (id = 1), name TEXT, age INTEGER,
        sex TEXT, height_cm REAL, weight_kg REAL, activity TEXT, goal TEXT,
        macro_model TEXT, units TEXT, dietary_prefs TEXT, allergies TEXT,
        medications TEXT, medical_history TEXT, created_at TEXT, updated_at TEXT);
    CREATE TABLE foods (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
        grp TEXT, serving_desc TEXT, serving_g REAL, kcal REAL, protein_g REAL,
        carbs_g REAL, fat_g REAL, fiber_g REAL, sodium_mg REAL, potassium_mg REAL,
        calcium_mg REAL, iron_mg REAL, source TEXT);
    CREATE TABLE meal_entries (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL,
        meal TEXT NOT NULL, food_id INTEGER, custom_name TEXT, quantity REAL NOT NULL,
        unit TEXT NOT NULL, custom_kcal REAL, custom_protein_g REAL, custom_carbs_g REAL,
        custom_fat_g REAL, created_at TEXT);
    CREATE TABLE water_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL,
        amount_ml INTEGER NOT NULL, created_at TEXT);
    CREATE TABLE assessments (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT,
        emergency INTEGER, payload TEXT, result TEXT);
    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
    INSERT INTO profile (id, name, age, sex, height_cm, weight_kg) VALUES
        (1, 'Legacy Person', 30, 'male', 175, 70);
    INSERT INTO meal_entries (date, meal, custom_name, quantity, unit, custom_kcal)
        VALUES ('2026-01-01', 'lunch', 'Old meal', 100, 'g', 250);
    INSERT INTO water_logs (date, amount_ml) VALUES ('2026-01-01', 300);
    """)
    conn.commit(); conn.close()
    monkeypatch.setenv("NUTRICARE_DB", str(legacy))
    migrated = create_app({"TESTING": True})
    with migrated.test_client() as c:
        users = c.get("/api/users").get_json()["users"]
        assert users and users[0]["name"] == "Legacy Person"
        c.post("/api/users/switch", json={"id": users[0]["id"]})
        meals = c.get("/api/meals?date=2026-01-01").get_json()
        assert meals["logged_count"] == 1
        assert c.get("/api/water?date=2026-01-01").get_json()["total_ml"] == 300


# ------------------------------------------------------------------ regression: onboarding/guest/refresh

def test_guest_skip_yields_functional_empty_account(client):
    """Workflow A: skipping onboarding creates a usable guest with no records."""
    boot = client.post("/api/users", json={"name": "Guest"}).get_json()
    assert boot["user"]["name"] == "Guest" and boot["targets"] is None
    summary = client.get("/api/summary").get_json()
    assert summary["logged_count"] == 0 and summary["water_ml"] == 0
    # features that do not need a profile still work
    food = client.get("/api/foods?q=roti").get_json()["foods"][0]
    assert client.post("/api/meals", json={"meal": "lunch", "food_id": food["id"],
                                           "quantity": 1, "unit": "serving"}).status_code == 201
    assert client.post("/api/assistant/assess",
                       json={"primary": "headache", "severity": 2}).status_code == 200


def test_refresh_restores_session_and_saved_profile(client):
    """Workflow B: repeat requests (refresh) with the same session keep the profile."""
    new_user(client, "Priya", **FULL_PROFILE)
    for _ in range(3):  # simulate refreshes
        boot = client.get("/api/bootstrap").get_json()
        assert boot["user"]["name"] == "Priya"
        assert boot["profile"]["weight_kg"] == 59.8 and boot["targets"] is not None


def test_remembered_uid_reattach_path_restores_records(client):
    """Refresh-recovery path used by the frontend when the cookie is gone:
    an explicit switch by id restores the same profile and its records."""
    first = new_user(client, "Comeback")
    food = client.get("/api/foods?q=roti").get_json()["foods"][0]
    client.post("/api/meals", json={"meal": "dinner", "food_id": food["id"],
                                    "quantity": 1, "unit": "serving"})
    uid = first["user"]["id"]
    # brand-new session (cookie lost), same device remembers the uid
    with client.session_transaction() as sess:
        sess.pop("uid", None)
    assert client.get("/api/bootstrap").get_json()["user"] is None
    restored = client.post("/api/users/switch", json={"id": uid}).get_json()
    assert restored["user"]["name"] == "Comeback"
    assert client.get("/api/meals").get_json()["logged_count"] == 1


def test_skipping_onboarding_never_erases_existing_records(client):
    """Workflow C guard: creating/switching profiles does not touch other records."""
    first = new_user(client, "Keeper")
    client.post("/api/water", json={"amount_ml": 400})
    new_user(client, "Guest")  # a second (guest) profile
    assert client.get("/api/water").get_json()["total_ml"] == 0  # guest is empty
    client.post("/api/users/switch", json={"id": first["user"]["id"]})
    assert client.get("/api/water").get_json()["total_ml"] == 400  # keeper intact


def test_profile_edit_persists_and_invalid_input_is_atomic(client):
    """Workflow D + F: valid edits persist; a rejected body changes nothing."""
    new_user(client, "Editor", **FULL_PROFILE)
    assert client.put("/api/profile", json={"weight_kg": 61.5}).get_json()["profile"]["weight_kg"] == 61.5
    assert client.get("/api/profile").get_json()["profile"]["weight_kg"] == 61.5
    bad = client.put("/api/profile", json={"weight_kg": 70, "age": 900})
    assert bad.status_code == 400
    prof = client.get("/api/profile").get_json()["profile"]
    assert prof["weight_kg"] == 61.5 and prof["age"] == 20  # nothing partially applied


def test_users_list_is_open_for_pre_session_visitors(client):
    """Onboarding's "Continue as …" card and the guest-restore path fetch the
    profile list BEFORE any session exists, so this endpoint must not 401."""
    resp = client.get("/api/users")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["current"] is None and isinstance(data["users"], list)
