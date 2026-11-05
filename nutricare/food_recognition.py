"""AI Food Scanner: orchestration from a predicted class to a nutrition estimate.

Recognition and nutrition are separate concerns (and separate modules):

  ``vision.py``    -> which food is in the photo
  ``this module``  -> how many nutrients that food has, at a chosen portion

Nutritional values are never invented here. A class is only "resolvable" when
``data/food_classes.json`` names an entry that really exists in the shared
``foods`` table; otherwise the estimate is returned as unavailable and the UI
must ask the user for their own label values. That is deliberate: an honest
"unknown" beats a fabricated calorie count.

Portion scaling reuses ``nutrition.scale_per100`` — the same arithmetic the
manual food logger uses — so a scanned meal and a hand-logged meal can never
disagree about the same food.
"""

from __future__ import annotations

import sqlite3

from . import nutrition, vision

MIN_GRAMS = 1.0
MAX_GRAMS = 3000.0


class EstimateError(ValueError):
    """The requested portion or class is not usable."""


def resolve_food(conn: sqlite3.Connection, slug: str) -> dict | None:
    """The dataset row for a class, or None when the class has no mapped entry."""
    entry = vision.class_by_slug().get(slug)
    if not entry:
        raise EstimateError(f"Unknown food class {slug!r}.")
    name = entry.get("food")
    if not name:
        return None
    row = conn.execute("SELECT * FROM foods WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else None


def default_grams(slug: str) -> float:
    entry = vision.class_by_slug().get(slug) or {}
    return float(entry.get("default_grams") or 100.0)


def _available_entry(row: dict) -> dict:
    """Subset of the dataset row that is safe/useful to show in the UI."""
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "group": row.get("grp"),
        "serving_desc": row.get("serving_desc"),
        "serving_g": row.get("serving_g"),
        "per_100g": {k: row.get(k) for k in nutrition.NUTRIENT_KEYS},
        "source": row.get("source"),
        "source_id": row.get("source_id"),
        "quality": row.get("quality"),
    }


def estimate(conn: sqlite3.Connection, slug: str, grams: float | None = None,
             *, allow_excluded: bool = True) -> dict:
    """Nutrition for one predicted class at ``grams`` (defaults to the dataset serving)."""
    entry = vision.class_by_slug().get(slug)
    if not entry:
        raise EstimateError(f"Unknown food class {slug!r}.")

    portion = default_grams(slug) if grams is None else float(grams)
    if not (MIN_GRAMS <= portion <= MAX_GRAMS):
        raise EstimateError(
            f"Portion must be between {MIN_GRAMS:g} g and {MAX_GRAMS:g} g.")

    row = resolve_food(conn, slug)
    base = {
        "slug": slug,
        "label": entry["label"],
        "group": entry["group"],
        "grams": round(portion, 1),
        "default_grams": default_grams(slug),
        "approx_note": entry.get("approx_note"),
        "nutrition_available": row is not None,
        "estimate_note": vision.ESTIMATE_NOTE,
        "portion_note": vision.PORTION_NOTE,
    }

    if row is None:
        # No documented entry: say so, and hand back nothing numeric.
        base["nutrients"] = None
        base["food"] = None
        base["unavailable_reason"] = (
            f"There is no documented nutrition entry for “{entry['label']}” in "
            "NutriCare's dataset, so no calorie figure is shown. Add it as a "
            "custom item using the values from your packaging or recipe.")
        return base

    nutrients = nutrition.scale_per100(row, portion)
    base["nutrients"] = nutrients
    base["food"] = _available_entry(row)
    # Rough uncertainty band: recipe/oil variation is the dominant error source
    # for cooked Indian dishes, not the classifier. Documented, not hidden.
    band = 0.15 if entry["group"].startswith("indian") else 0.10
    base["range"] = {
        "kcal_low": round(nutrients["kcal"] * (1 - band), 1),
        "kcal_high": round(nutrients["kcal"] * (1 + band), 1),
        "band_pct": round(band * 100),
        "explanation": (
            f"±{round(band * 100)}% band reflects recipe and cooking-oil variation "
            "for this kind of dish. It is not a measurement uncertainty."),
    }
    return base


def predictions_with_nutrition(conn: sqlite3.Connection, result: dict,
                               grams: float | None = None) -> list[dict]:
    """Attach a nutrition estimate to every ranked prediction."""
    out = []
    for prediction in result["predictions"]:
        item = dict(prediction)
        try:
            item["nutrition"] = estimate(conn, prediction["slug"], grams)
        except EstimateError as exc:  # pragma: no cover - defensive
            item["nutrition"] = {"error": str(exc), "nutrition_available": False}
        out.append(item)
    return out


def available_classes(conn: sqlite3.Connection) -> dict:
    """Class list annotated with whether nutrition can be resolved from the DB."""
    dataset_names = {r["name"] for r in conn.execute("SELECT name FROM foods")}
    out = []
    for entry in vision.class_list():
        name = entry.get("food")
        out.append({
            "slug": entry["slug"],
            "label": entry["label"],
            "group": entry["group"],
            "aliases": entry.get("aliases", []),
            "default_grams": entry.get("default_grams"),
            "nutrition_available": bool(name and name in dataset_names),
            "dataset_food": name if name in dataset_names else None,
            "approx_note": entry.get("approx_note"),
        })
    return {
        "classes": out,
        "count": len(out),
        "with_nutrition": sum(1 for c in out if c["nutrition_available"]),
        "single_label": True,
        "note": vision.SINGLE_LABEL_NOTE,
    }
