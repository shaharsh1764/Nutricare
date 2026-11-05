"""AI Food Scanner HTTP endpoints (Flask blueprint).

Mounted at ``/api/vision`` by the app factory, next to the existing ``/api``
blueprint — no existing endpoint is touched.

Security decisions, all deliberate:
  * The uploaded image is validated from its **magic bytes**, never from the
    client-supplied filename or Content-Type.
  * It is held in memory for the single prediction call. It is never written
    to disk and never sent anywhere: no photo leaves this process, so nothing
    is uploaded to a third party and nothing persists after the request.
  * Client-supplied nutrition is ignored on save. The numbers stored in the
    diary are recomputed server-side from the food dataset and the portion
    the user asked for (see ``_nutrition_for_save``).
  * Saving reuses the existing ``meal_entries`` table and ``db.MEALS``
    categories, so the scanner cannot create a parallel meal system.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from . import db, food_recognition, nutrition, vision

vision_api = Blueprint("vision", __name__, url_prefix="/api/vision")

MAX_TOP_K = 5


def _err(message: str, code: int = 400, **extra):
    payload = {"error": message}
    payload.update(extra)
    return jsonify(payload), code


def _current_uid(conn) -> int | None:
    uid = session.get("uid")
    if uid is None:
        return None
    return uid if db.get_user(conn, uid) else None


def _no_user():
    return _err("No active local user. Complete the welcome setup first.", 401)


# ------------------------------------------------------------------ status
@vision_api.get("/status")
def status():
    """Is a trained model installed? Used by the UI to be honest up front."""
    return jsonify({
        "model": vision.model_status(),
        "estimate_note": vision.ESTIMATE_NOTE,
        "portion_note": vision.PORTION_NOTE,
        "single_label_note": vision.SINGLE_LABEL_NOTE,
    })


@vision_api.get("/classes")
def classes():
    conn = db.get_db()
    return jsonify(food_recognition.available_classes(conn))


# ------------------------------------------------------------------ predict
def _read_upload():
    """Pull the image out of a multipart form or a raw body. Memory only."""
    if "image" in request.files:
        return request.files["image"].read()
    if "photo" in request.files:
        return request.files["photo"].read()
    return request.get_data(cache=False) or b""


@vision_api.post("/predict")
def predict():
    """Classify one photograph and attach nutrition estimates.

    Returns 503 with ``model_unavailable: true`` — never a fake prediction —
    when no checkpoint is installed.
    """
    uid_conn = db.get_db()
    if _current_uid(uid_conn) is None:
        return _no_user()

    raw = _read_upload()
    try:
        vision.validate_image(raw)
    except vision.ImageError as exc:
        return _err(str(exc))

    try:
        top_k = int(request.args.get("top_k", 3))
    except (TypeError, ValueError):
        top_k = 3
    top_k = max(1, min(top_k, MAX_TOP_K))

    grams = request.args.get("grams")
    grams_value = None
    if grams not in (None, ""):
        try:
            grams_value = float(grams)
        except (TypeError, ValueError):
            return _err("grams must be a number")

    try:
        result = vision.get_predictor().predict(raw, top_k=top_k)
    except vision.ImageError as exc:
        return _err(str(exc))
    except vision.ModelUnavailable as exc:
        return _err(str(exc), 503, model_unavailable=True,
                    hint="Train or install a checkpoint with docs/MODEL.md. "
                         "NutriCare will not guess a food name.")

    result["candidates"] = food_recognition.predictions_with_nutrition(
        uid_conn, result, grams_value)
    return jsonify(result)


# ------------------------------------------------------------------ estimate
@vision_api.post("/estimate")
def estimate():
    """Nutrition for one class + portion. Portion edits re-call this endpoint."""
    conn = db.get_db()
    if _current_uid(conn) is None:
        return _no_user()

    data = request.get_json(silent=True) or {}
    slug = str(data.get("slug") or "").strip()
    if not slug:
        return _err("slug is required (see /api/vision/classes).")
    grams = data.get("grams")
    if grams is not None:
        try:
            grams = float(grams)
        except (TypeError, ValueError):
            return _err("grams must be a number")
    try:
        return jsonify(food_recognition.estimate(conn, slug, grams))
    except food_recognition.EstimateError as exc:
        return _err(str(exc))


# ------------------------------------------------------------------ log meal
def _nutrition_for_save(conn, slug: str, grams: float) -> tuple[dict | None, dict | None]:
    """Recompute nutrition server-side. Client numbers are deliberately ignored."""
    try:
        estimate = food_recognition.estimate(conn, slug, grams)
    except food_recognition.EstimateError as exc:
        raise ValueError(str(exc))
    return estimate.get("food"), estimate.get("nutrients")


@vision_api.post("/log")
def log_meal():
    """Save a recognised meal into the EXISTING meal_entries table.

    Two shapes are supported:
      * class with a documented dataset entry -> ``food_id`` + ``quantity`` in grams
      * class with no dataset entry, or a manual correction -> ``custom_name``
        plus the user's own per-portion values (never classifier-invented).
    """
    data = request.get_json(silent=True) or {}
    conn = db.get_db()
    uid = _current_uid(conn)
    if uid is None:
        return _no_user()

    meal = str(data.get("meal") or "").strip().lower()
    if meal not in db.MEALS:
        return _err(f"meal must be one of {list(db.MEALS)} — "
                    "choose when you had this meal (breakfast, lunch, snacks, dinner).")

    try:
        day = data.get("date") or db.today()
        from .api import v_date  # reuse the existing validator
        day = v_date(day)
    except ValueError as exc:
        return _err(str(exc))

    slug = str(data.get("slug") or "").strip()
    manual_name = str(data.get("custom_name") or "").strip()[:80]
    try:
        grams = float(data.get("grams"))
    except (TypeError, ValueError):
        return _err("grams must be a number")
    if not (food_recognition.MIN_GRAMS <= grams <= food_recognition.MAX_GRAMS):
        return _err(f"grams must be between {food_recognition.MIN_GRAMS:g} "
                    f"and {food_recognition.MAX_GRAMS:g}")

    food_id = None
    custom_name = None
    custom = {k: None for k in
              ("custom_kcal", "custom_protein_g", "custom_carbs_g", "custom_fat_g")}

    if slug:
        if slug not in vision.class_by_slug():
            return _err(f"Unknown food class {slug!r}.")
        try:
            food_row, _nutrients = _nutrition_for_save(conn, slug, grams)
        except ValueError as exc:
            return _err(str(exc))

        if food_row is not None:
            food_id = food_row["id"]
        else:
            # No documented entry -> the user must supply the numbers.
            entry = vision.class_by_slug()[slug]
            custom_name = entry["label"]
            provided = {"custom_kcal": data.get("custom_kcal"),
                        "custom_protein_g": data.get("custom_protein_g"),
                        "custom_carbs_g": data.get("custom_carbs_g"),
                        "custom_fat_g": data.get("custom_fat_g")}
            if all(v in (None, "") for v in provided.values()):
                return _err(
                    f"“{custom_name}” has no documented nutrition entry, so its "
                    "values cannot be guessed. Enter the calories (and optionally "
                    "protein/carbs/fat) for this portion, or log it as a custom item.",
                    needs_manual_values=True)
            for key, value in provided.items():
                if value in (None, ""):
                    continue
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    return _err(f"{key} must be a number")
                if not (0 <= number <= 100000):
                    return _err(f"{key} is out of range")
                custom[key] = number
            if custom["custom_kcal"] is None:
                return _err("custom_kcal is required for a food with no dataset entry",
                            needs_manual_values=True)
    else:
        # Fully manual correction: the user named the food themself.
        if not manual_name:
            return _err("Provide either a recognised slug or a custom_name.")
        custom_name = manual_name
        for key in custom:
            value = data.get(key)
            if value in (None, ""):
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                return _err(f"{key} must be a number")
            if not (0 <= number <= 100000):
                return _err(f"{key} is out of range")
            custom[key] = number
        if custom["custom_kcal"] is None:
            return _err("custom_kcal is required when logging a manual food.",
                        needs_manual_values=True)

    quantity = round(grams, 1)
    unit = "g"

    # Mirror the existing /api/meals dietary + allergy guard so a scanned meal
    # obeys exactly the same preferences as a manually logged one.
    if food_id is not None:
        from .api import current_uid  # noqa: F401  (documentation of shared behaviour)
        from . import insights
        row = conn.execute("SELECT * FROM foods WHERE id = ?", (food_id,)).fetchone()
        if row is None:
            return _err("food_id not found in database", 404)
        food_dict = dict(row)
        profile = db.get_profile(conn, uid)
        try:
            if insights.is_excluded(food_dict, profile.get("allergies"),
                                    profile.get("dietary_prefs")):
                return _err(
                    f"“{food_dict['name']}” is incompatible with your dietary "
                    "preferences or allergies and was not logged.", 409,
                    dietary_conflict=True)
        except Exception:  # metadata problems must not block logging
            pass

    cur = conn.execute(
        "INSERT INTO meal_entries (user_id, date, meal, food_id, custom_name,"
        " quantity, unit, custom_kcal, custom_protein_g, custom_carbs_g,"
        " custom_fat_g, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (uid, day, meal, food_id, custom_name, quantity, unit,
         custom["custom_kcal"], custom["custom_protein_g"],
         custom["custom_carbs_g"], custom["custom_fat_g"], db.now()))
    conn.commit()

    entry_row = conn.execute("SELECT * FROM meal_entries WHERE id = ?",
                             (cur.lastrowid,)).fetchone()
    entry = dict(entry_row)
    entry.pop("user_id", None)

    # Day totals after the insert, so the dashboard/tracker can refresh from
    # one response (existing /api/meals and /api/summary remain authoritative).
    rows = conn.execute(
        "SELECT * FROM meal_entries WHERE user_id = ? AND date = ?",
        (uid, day)).fetchall()
    totals = nutrition.sum_nutrients([
        nutrition.entry_nutrients(dict(r), _food_for(conn, r)) for r in rows])

    return jsonify({
        "entry": entry,
        "date": day,
        "meal": meal,
        "display_name": custom_name or (_food_for(conn, entry_row) or {}).get("name"),
        "totals": totals,
        "logged_count": len(rows),
    }), 201


def _food_for(conn, row) -> dict | None:
    """Look up the linked food row for a meal entry (dict or sqlite3.Row)."""
    food_id = row["food_id"]
    if not food_id:
        return None
    found = conn.execute("SELECT * FROM foods WHERE id = ?", (food_id,)).fetchone()
    return dict(found) if found else None
