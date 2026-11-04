"""Smart Nutrition Insights — read-only analytics over EXISTING stored records.

Design rules (mirrors the app's safety stance):
* every number comes from meal_entries / water_logs rows or the foods dataset —
  nothing is invented, and missing logs are never treated as zero intake;
* personalised targets stay labelled estimates (computed by the existing
  api.targets_for / nutrition functions, never re-implemented here);
* recommendations only ever come from the built-in food dataset, filtered by
  recorded allergies and dietary preferences;
* a logged gap is wording-conservative: it describes intake versus a target or
  general reference — it never claims a medical deficiency, diagnosis or plan.

Pure functions only: api.py fetches rows and passes plain dicts/lists in.
"""
from __future__ import annotations

from . import nutrition

# ---------------------------------------------------------------- thresholds
# Documented, conservative: a "gap" needs intake below 80% of the reference;
# "above" needs more than 115%. Weekly "consistently" claims need >= 3 logged
# days so two random days can never produce a pattern claim.
GAP_BELOW = 0.80
OVER_ABOVE = 1.15
MICRO_GAP = 0.70
WEEK_MIN_DAYS_FOR_PATTERN = 3
MAX_RECOMMENDATIONS = 3

DISCLAIMER = ("General educational guidance built only from your own logged records and the "
              "built-in food dataset. Not medical advice — a day (or week) of intake below a "
              "target does not by itself prove a medical deficiency, and nothing here is a "
              "diagnosis or a prescribed diet.")

MISSING_DAYS_NOTE = ("Days without records are shown as missing — they are NOT treated as "
                     "zero-intake days, so averages describe your logged days only.")

# ------------------------------------------------------- filtering vocabulary
# Free-text allergies/preferences are matched conservatively by keyword against
# food NAMES in the dataset (documented in README). When in doubt, exclude.
# Dietary policy (documented, explicit):
# - Vegetarian = lacto-vegetarian: excludes meat/fish/poultry and EGGS, allows dairy.
#   Eggs are classified as non-vegetarian (common in this app's Indian food context;
#   ovo-vegetarian users should select 'vegan' or manage eggs via allergies).
# - Vegan = excludes all animal products: meat/fish/egg/dairy/honey.
# This is preserved and documented here (README §8) — not silently changed.

ALLERGY_KEYWORDS = {
    "peanut": ["peanut"],
    "tree nut": ["almond", "walnut", "cashew", "pistachio", "nut"],
    "nut": ["almond", "walnut", "cashew", "pistachio", "nut"],
    "almond": ["almond"],
    "walnut": ["walnut"],
    "cashew": ["cashew"],
    "milk": ["milk", "curd", "dahi", "paneer", "yogurt", "yoghurt", "ghee", "butter", "cream", "casein", "whey"],
    "lactose": ["milk", "curd", "dahi", "paneer", "yogurt", "yoghurt", "ghee", "butter", "cream", "casein", "whey"],
    "dairy": ["milk", "curd", "dahi", "paneer", "yogurt", "yoghurt", "ghee", "butter", "cream", "casein", "whey"],
    "casein": ["milk", "curd", "dahi", "paneer", "yogurt", "yoghurt", "ghee", "butter", "cream", "casein", "whey"],
    "whey": ["milk", "curd", "dahi", "paneer", "yogurt", "yoghurt", "ghee", "butter", "cream", "casein", "whey"],
    "egg": ["egg"],
    "fish": ["salmon", "fish", "anchovy", "anchovies"],
    "seafood": ["salmon", "fish", "shrimp", "prawn", "crab"],
    "shellfish": ["shrimp", "prawn", "crab"],
    "gluten": ["wheat", "roti", "bread", "barley", "rye"],
    "wheat": ["wheat", "roti", "bread"],
    "soy": ["soy", "tofu"],
    "sesame": ["sesame", "tahini"],
}
# Category-aware dairy groups (reliable metadata): Dairy & Alternatives covers most
# dairy in this dataset; Oils & Fats contains Ghee (clarified milk fat) which must
# also be excluded for milk/dairy/lactose allergies even though its grp is not Dairy.
DAIRY_GROUPS = {"Dairy & Alternatives"}
DAIRY_OIL_NAMES = {"ghee"}  # subset of Oils & Fats that is dairy-derived
# Vegetarian excludes meat/fish/poultry + EGGS (lacto-vegetarian policy, documented above)
MEAT_FISH_WORDS = ["chicken", "salmon", "fish", "meat", "mutton", "beef", "pork", "lamb", "egg"]
VEGAN_EXTRA_WORDS = MEAT_FISH_WORDS + [
    "milk", "curd", "dahi", "paneer", "yogurt", "yoghurt", "ghee", "butter", "cream",
    "honey", "casein", "whey",
]

NUTRIENT_LABELS = {
    "protein_g": ("protein", "g"), "fiber_g": ("fibre", "g"),
    "calcium_mg": ("calcium", "mg"), "iron_mg": ("iron", "mg"),
}


def _norm_list(values) -> list[str]:
    """Profile lists arrive as JSON-decoded lists of free-text strings."""
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    return [str(v).strip().lower() for v in values if str(v).strip()]

# --- helpers to read new per-food metadata (with safe fallback) ---
import json as _json

def _allergens_of(food: dict) -> list[str] | None:
    raw = food.get("allergens")
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            parsed = _json.loads(raw)
            return [str(x).lower() for x in parsed] if isinstance(parsed, list) else None
        except Exception:
            return None
    if isinstance(raw, list):
        return [str(x).lower() for x in raw]
    return None

def _dietary_of(food: dict) -> dict | None:
    raw = food.get("dietary")
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            parsed = _json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    if isinstance(raw, dict):
        return raw
    return None

def _pref_is_vegan(prefs_norm: list[str]) -> bool:
    joined = " ".join(prefs_norm)
    return "vegan" in joined

def _pref_is_vegetarian(prefs_norm: list[str]) -> bool:
    joined = " ".join(prefs_norm)
    return ("vegetarian" in joined or joined.strip() == "veg" or "veg " in joined or " veg" in joined) and not _pref_is_vegan(prefs_norm)

ALLERGEN_ALIASES = {
    "milk": {"milk", "dairy", "lactose", "casein", "whey"},
    "peanut": {"peanut"},
    "tree_nut": {"tree nut", "tree_nut", "almond", "walnut", "cashew", "pistachio", "nut"},
    "soy": {"soy", "soya", "tofu"},
    "wheat": {"wheat", "gluten", "barley", "rye", "roti", "bread"},
    "fish": {"fish", "salmon", "anchovy", "hilsa", "rohu", "pomfret", "tuna", "sardine"},
    "shellfish": {"shellfish", "shrimp", "prawn", "crab"},
    "egg": {"egg"},
    "sesame": {"sesame", "til", "tahini"},
}

def _user_allergy_maps_to_food_allergen(user_allergy: str, food_allergen: str) -> bool:
    ua = user_allergy.lower()
    fa = food_allergen.lower()
    for code, aliases in ALLERGEN_ALIASES.items():
        if code == fa:
            return any(a in ua for a in aliases)
        # also allow reverse: user's allergy string contains code
        if fa in ALLERGEN_ALIASES and any(a in ua for a in ALLERGEN_ALIASES[fa]):
            # already handled
            pass
    # direct substring match as fallback
    return fa in ua or fa.replace("_", " ") in ua or fa.replace("_","") in ua

def food_matches_allergy(food_name: str, allergies, food_grp: str | None = None, food_allergens: list[str] | None = None) -> bool:
    """Prefer explicit per-food allergen metadata; fallback to keyword+grp for legacy rows.
    Safe default: if metadata missing/ambiguous, do NOT assume allergen-free — exclude when allergy cannot be ruled out."""
    norm_allergies = _norm_list(allergies)
    if not norm_allergies:
        return False
    name = food_name.lower()
    grp = (food_grp or "").strip()
    # If explicit allergen list present, use it precisely
    if food_allergens is not None:
        for allergy in norm_allergies:
            for fa in food_allergens:
                if _user_allergy_maps_to_food_allergen(allergy, fa):
                    return True
        return False
    # Fallback: legacy keyword + grp logic (for 1-42 before backfill, or if allergens is None)
    for allergy in norm_allergies:
        for key, words in ALLERGY_KEYWORDS.items():
            if key in allergy and any(w in name for w in words):
                return True
        if any(d in allergy for d in ("milk", "dairy", "lactose", "casein", "whey")):
            if grp in DAIRY_GROUPS or (grp == "Oils & Fats" and any(o in name for o in DAIRY_OIL_NAMES)):
                return True
        if any(n in allergy for n in ("peanut", "tree nut")) or allergy.strip() == "nut" or allergy.strip().endswith(" nut"):
            if grp == "Nuts & Seeds" and any(w in name for w in ["peanut", "almond", "walnut", "cashew", "pistachio"]):
                return True
    # If allergen metadata missing entirely, be conservative: if user's allergy is plausible for this grp, exclude
    # e.g., Dairy group with milk allergy but name didn't match keyword => still exclude
    if food_allergens is None:
        for allergy in norm_allergies:
            if any(d in allergy for d in ("milk", "dairy", "lactose", "casein", "whey")) and grp in DAIRY_GROUPS:
                return True
            if "sesame" in allergy and food_grp == "Nuts & Seeds" and "sesame" in name:
                pass # already covered
    return False


def food_allowed_by_prefs(food_name: str, prefs, food_grp: str | None = None, food_dietary: dict | None = None) -> bool:
    """Prefer explicit dietary metadata; fallback to keyword logic.
    Vegetarian = lacto-vegetarian (excludes meat/fish/egg, allows dairy) — documented.
    Vegan = excludes all animal products. Missing dietary metadata => fallback to name keywords."""
    plist = _norm_list(prefs)
    if not plist:
        return True
    joined = " ".join(plist)
    name = food_name.lower()
    grp = (food_grp or "").strip()
    # Explicit dietary metadata path
    if food_dietary is not None:
        if _pref_is_vegan(plist):
            return bool(food_dietary.get("vegan"))
        # Specific variants before generic vegetarian (which contains "vegetarian" substring)
        if "lacto-ovo" in joined or "lacto ovo" in joined or ("ovo" in joined and "lacto" in joined):
            return bool(food_dietary.get("lacto_ovo_vegetarian"))
        if "ovo" in joined:
            return bool(food_dietary.get("ovo_vegetarian"))
        if _pref_is_vegetarian(plist):
            return bool(food_dietary.get("lacto_vegetarian"))
        if "egg-free" in joined or "no egg" in joined:
            return "egg" not in (food_dietary or {}) and "egg" not in name # fallback
        return True
    # Fallback keyword path
    if "vegan" in joined:
        if grp == "Dairy & Alternatives":
            return False
        if grp == "Oils & Fats" and "ghee" in name:
            return False
        return not any(w in name for w in VEGAN_EXTRA_WORDS)
    if "vegetarian" in joined or "veg" == joined:
        return not any(w in name for w in MEAT_FISH_WORDS)
    if "egg-free" in joined or "no egg" in joined:
        return "egg" not in name
    return True


def is_excluded(food: dict, allergies, prefs) -> bool:
    # Prefer new metadata columns, fallback to legacy grp/name
    allergens = _allergens_of(food)
    dietary = _dietary_of(food)
    return (food_matches_allergy(food["name"], allergies, food.get("grp"), allergens)
            or not food_allowed_by_prefs(food["name"], prefs, food.get("grp"), dietary))


# ------------------------------------------------------------ recommendations
def _per_serving(food: dict, key: str) -> float:
    grams = float(food.get("serving_g") or 100.0)
    return float(food.get(key) or 0.0) / 100.0 * grams


def rank_foods(foods: list[dict], nutrient_key: str, allergies, prefs,
               exclude_names: set[str], limit: int = MAX_RECOMMENDATIONS) -> list[dict]:
    """Top dataset foods for one nutrient, per serving, after safety filters.
    Never invents foods: output is always a subset of the passed dataset rows."""
    label, unit = NUTRIENT_LABELS[nutrient_key]
    candidates = []
    for food in foods:
        if food["name"] in exclude_names or is_excluded(food, allergies, prefs):
            continue
        amount = _per_serving(food, nutrient_key)
        if amount <= 0:
            continue
        candidates.append((amount, food))
    candidates.sort(key=lambda pair: -pair[0])
    out = []
    for amount, food in candidates[:limit]:
        serving = food.get("serving_desc") or f"{food.get('serving_g') or 100:g} g"
        kcal = _per_serving(food, "kcal")
        out.append({
            "food_id": food["id"],
            "name": food["name"],
            "group": food.get("grp"),
            "serving_desc": serving,
            "contribution": f"≈{amount:.1f} {unit} {label} (+{kcal:.0f} kcal) per {serving}",
            "why": (f"Highest {label} per serving in the built-in dataset among foods that "
                    "fit your recorded allergies and dietary preferences."),
        })
    return out


def _gap_card(gap_id: str, title: str, detail: str, recs: list[dict],
              filtered_note: str = "") -> dict:
    card = {"id": gap_id, "level": "gap", "title": title, "detail": detail}
    if recs:
        card["recommendations"] = recs
    elif filtered_note:
        card["recommendations_note"] = filtered_note
    return card


NO_MATCH_NOTE = ("Every stronger dataset source is excluded by your recorded allergies or "
                 "dietary preferences — nothing is recommended rather than suggesting an "
                 "unsafe food. You can review both in My Profile.")


# ---------------------------------------------------------------- daily payload
def daily_payload(*, date: str, entries: list[dict], totals: dict, water_ml: int,
                  water_goal_ml: int, targets: dict | None, profile: dict,
                  foods: list[dict]) -> dict:
    allergies = profile.get("allergies")
    prefs = profile.get("dietary_prefs")
    logged_count = len(entries)
    logged_names = {e["display_name"] for e in entries}
    groups = sorted({e["food"]["grp"] for e in entries if e.get("food")})
    has_dataset_entry = any(e.get("food") for e in entries)   # fibre/micro data sufficiency
    personalized = targets is not None
    micro = nutrition.micro_targets(profile.get("sex") or "other")
    empty = logged_count == 0 and not water_ml

    def pct(value, target):
        return round(100.0 * value / target) if target else None

    metrics = [
        {"key": "kcal", "label": "Calories", "unit": "kcal", "value": round(totals["kcal"]),
         "target": targets["kcal"] if targets else None,
         "pct": pct(totals["kcal"], targets["kcal"]) if targets else None},
        {"key": "protein_g", "label": "Protein", "unit": "g", "value": round(totals["protein_g"], 1),
         "target": targets["protein_g"] if targets else None,
         "pct": pct(totals["protein_g"], targets["protein_g"]) if targets else None},
        {"key": "carbs_g", "label": "Carbohydrates", "unit": "g", "value": round(totals["carbs_g"], 1),
         "target": targets["carbs_g"] if targets else None,
         "pct": pct(totals["carbs_g"], targets["carbs_g"]) if targets else None},
        {"key": "fat_g", "label": "Fat", "unit": "g", "value": round(totals["fat_g"], 1),
         "target": targets["fat_g"] if targets else None,
         "pct": pct(totals["fat_g"], targets["fat_g"]) if targets else None},
        {"key": "water_ml", "label": "Water", "unit": "ml", "value": int(water_ml),
         "target": int(water_goal_ml), "pct": pct(water_ml, water_goal_ml)},
    ]

    insights: list[dict] = []
    if empty:
        insights.append({
            "id": "no_records", "level": "info", "title": "No records for this day yet",
            "detail": ("Nothing is logged — and an empty log never means zero intake. Insights "
                       "appear only from your real records; log a meal or water in the tracker "
                       "to get started."),
        })
    else:
        # energy versus (estimated) target
        if targets:
            ratio = totals["kcal"] / targets["kcal"] if targets["kcal"] else 0
            if ratio < GAP_BELOW:
                insights.append({
                    "id": "kcal_below", "level": "info",
                    "title": "Calories below your estimated target",
                    "detail": (f"{round(totals['kcal'])} of ~{targets['kcal']} kcal logged "
                               f"({round(100 * ratio)}%). With the day in progress — or "
                               "incomplete logging — this is an observation, not a problem."),
                })
            elif ratio > OVER_ABOVE:
                insights.append({
                    "id": "kcal_above", "level": "info",
                    "title": "Calories above your estimated target",
                    "detail": (f"{round(totals['kcal'])} of ~{targets['kcal']} kcal logged "
                               f"({round(100 * ratio)}%). Targets are estimates; a single day "
                               "above them is normal variation."),
                })
            else:
                insights.append({
                    "id": "kcal_on_track", "level": "good",
                    "title": "Energy intake tracking near your estimated target",
                    "detail": (f"{round(totals['kcal'])} of ~{targets['kcal']} kcal logged "
                               f"({round(100 * ratio)}% of the estimate)."),
                })
        elif logged_count:
            insights.append({
                "id": "kcal_no_target", "level": "info",
                "title": "Logged energy — no personalised target yet",
                "detail": (f"{round(totals['kcal'])} kcal recorded today. Add age, sex, height "
                           "and weight in My Profile for an estimated target (clearly labelled "
                           "as an estimate)."),
            })
        # protein versus target
        if targets and targets["protein_g"] and totals["protein_g"] < targets["protein_g"] * GAP_BELOW:
            recs = rank_foods(foods, "protein_g", allergies, prefs, logged_names)
            insights.append(_gap_card(
                "protein_below", "Protein intake below target",
                f"{round(totals['protein_g'], 1)} g of ~{targets['protein_g']} g logged "
                f"({pct(totals['protein_g'], targets['protein_g'])}% of the estimate). "
                "Dataset options that fit your allergy/preference filters:",
                recs, NO_MATCH_NOTE))
        # fibre versus reference (only with dataset-backed entries)
        fiber_ref = micro["fiber_g"]
        if has_dataset_entry and totals["fiber_g"] < fiber_ref * GAP_BELOW:
            recs = rank_foods(foods, "fiber_g", allergies, prefs, logged_names)
            ref_label = "your sex-based reference" if personalized else "a general 28 g reference"
            insights.append(_gap_card(
                "fiber_below", "Fibre intake below reference",
                f"{round(totals['fiber_g'], 1)} g of ~{fiber_ref} g logged ({ref_label}, "
                "from dataset entries only — custom items carry no fibre data).",
                recs, NO_MATCH_NOTE))
        # calcium / iron versus references (dataset-backed entries only)
        if has_dataset_entry:
            for key, ref_key, gap_id, title in (
                    ("calcium_mg", "calcium_mg", "calcium_below", "Calcium intake below reference"),
                    ("iron_mg", "iron_mg", "iron_below", "Iron intake below reference")):
                ref = micro[ref_key]
                if ref and totals[key] < ref * MICRO_GAP:
                    recs = rank_foods(foods, key, allergies, prefs, logged_names)
                    insights.append(_gap_card(
                        gap_id, title,
                        f"{round(totals[key])} mg of ~{ref} mg logged"
                        f"{' (sex-based reference)' if personalized else ' (general reference)'}. "
                        "This describes logged intake only — it is not a claim about your body's "
                        "stores or health.",
                        recs, NO_MATCH_NOTE))
        # fat above target — informational only
        if targets and targets["fat_g"] and totals["fat_g"] > targets["fat_g"] * OVER_ABOVE:
            insights.append({
                "id": "fat_above", "level": "info", "title": "Fat above the estimated target",
                "detail": (f"{round(totals['fat_g'], 1)} g of ~{targets['fat_g']} g logged. "
                           "A planning heads-up, not a problem in itself."),
            })
        # hydration versus the user's selected goal
        if water_ml < water_goal_ml:
            insights.append({
                "id": "water_below", "level": "gap" if logged_count else "info",
                "title": "Hydration below your selected goal",
                "detail": (f"{int(water_ml)} ml of {int(water_goal_ml)} ml logged "
                           f"({pct(water_ml, water_goal_ml)}% of the goal you chose in Settings)."
                           + ("" if logged_count else " No water logged yet today.")),
            })
        else:
            insights.append({
                "id": "water_on_track", "level": "good", "title": "Hydration goal reached",
                "detail": f"{int(water_ml)} ml logged against your {int(water_goal_ml)} ml goal.",
            })
        # variety across dataset groups
        if logged_count >= 3 and len(groups) <= 2:
            insights.append({
                "id": "variety_low", "level": "info", "title": "Limited variety in logged foods",
                "detail": (f"{logged_count} items logged today from {len(groups)} dataset "
                           f"food group(s) ({', '.join(groups) if groups else 'none dataset-based'}). "
                           "Variety is a general healthy-eating principle, not a rule — this is "
                           "an observation about today's log only."),
            })

    payload = {
        "date": date,
        "personalized": personalized,
        "logged_count": logged_count,
        "distinct_food_groups": groups,
        "targets": targets,
        "totals": totals,
        "water_ml": int(water_ml),
        "water_goal_ml": int(water_goal_ml),
        "metrics": metrics,
        "insights": insights,
        "disclaimer": DISCLAIMER,
    }
    if not personalized:
        payload["limitation_note"] = (
            "Profile incomplete — these are NON-personalised insights: intake is compared only "
            "with your selected water goal and general references. Add age, sex, height and "
            "weight in My Profile for personalised (estimate-labelled) targets.")
    return payload


# --------------------------------------------------------------- weekly payload
def weekly_payload(per_day: list[dict], targets: dict | None, water_goal_ml: int,
                   profile: dict) -> dict:
    """per_day: 14 oldest→newest dicts with date, kcal/protein_g/carbs_g/fat_g/
    fiber_g, water_ml, logged_count, food_names, groups, has_dataset_entry."""
    current, previous = per_day[-7:], per_day[:7]

    def summarize(week: list[dict]) -> dict | None:
        logged = [d for d in week if d["logged_count"] > 0]
        if not logged:
            return None
        n = len(logged)
        counts: dict[str, int] = {}
        groups: set[str] = set()
        for d in logged:
            for name in d["food_names"]:
                counts[name] = counts.get(name, 0) + 1
            groups.update(d["groups"])
        micro = nutrition.micro_targets(profile.get("sex") or "other")
        fiber_days = sum(1 for d in logged if d["has_dataset_entry"])
        avg = lambda key: round(sum(d[key] for d in logged) / n, 1)  # noqa: E731
        s = {
            "start": week[0]["date"], "end": week[-1]["date"],
            "logged_days": n, "missing_days": len(week) - n,
            "averages": {
                "kcal": round(sum(d["kcal"] for d in logged) / n),
                "protein_g": avg("protein_g"), "carbs_g": avg("carbs_g"),
                "fat_g": avg("fat_g"), "water_ml": round(sum(d["water_ml"] for d in logged) / n),
                "fiber_g": (round(sum(d["fiber_g"] for d in logged) / fiber_days, 1)
                            if fiber_days else None),
            },
            "top_foods": [{"name": k, "times": v} for k, v in
                          sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]],
            "distinct_food_groups": sorted(groups),
            "water_goal_ml": int(water_goal_ml),
        }
        patterns = []
        if n >= WEEK_MIN_DAYS_FOR_PATTERN:
            if targets:
                ratio = s["averages"]["kcal"] / targets["kcal"] if targets["kcal"] else 0
                if ratio > OVER_ABOVE:
                    patterns.append({
                        "id": "week_kcal_above", "level": "info",
                        "title": "Calories consistently above the estimated target",
                        "detail": (f"Average {s['averages']['kcal']} kcal over {n} logged days "
                                   f"vs ~{targets['kcal']} kcal estimated ({round(100 * ratio)}%). "
                                   "Based on logged days only — unlogged days are unknown, not zero.")})
                elif ratio < GAP_BELOW:
                    patterns.append({
                        "id": "week_kcal_below", "level": "info",
                        "title": "Calories consistently below the estimated target",
                        "detail": (f"Average {s['averages']['kcal']} kcal over {n} logged days "
                                   f"vs ~{targets['kcal']} kcal estimated ({round(100 * ratio)}%). "
                                   "Incomplete logging can look identical — this is not a judgement.")})
                if targets["protein_g"] and s["averages"]["protein_g"] < targets["protein_g"] * GAP_BELOW:
                    patterns.append({
                        "id": "week_protein_below", "level": "gap",
                        "title": "Protein below target on logged days",
                        "detail": (f"Average {s['averages']['protein_g']} g vs ~{targets['protein_g']} g "
                                   f"estimated, over {n} logged days.")})
            if s["averages"]["fiber_g"] is not None and s["averages"]["fiber_g"] < micro["fiber_g"] * GAP_BELOW:
                patterns.append({
                    "id": "week_fiber_below", "level": "gap",
                    "title": "Fibre below reference on logged days",
                    "detail": (f"Average {s['averages']['fiber_g']} g vs ~{micro['fiber_g']} g "
                               f"reference over {fiber_days} day(s) with dataset entries.")})
            if s["averages"]["water_ml"] < water_goal_ml * GAP_BELOW:
                patterns.append({
                    "id": "week_water_below", "level": "gap",
                    "title": "Hydration below your selected goal",
                    "detail": (f"Average {s['averages']['water_ml']} ml vs {int(water_goal_ml)} ml "
                               f"goal over {n} logged days.")})
            elif s["averages"]["water_ml"] >= water_goal_ml:
                patterns.append({
                    "id": "week_water_met", "level": "good",
                    "title": "Hydration goal met on average",
                    "detail": f"Average {s['averages']['water_ml']} ml vs {int(water_goal_ml)} ml goal."})
            if len(groups) <= 3:
                patterns.append({
                    "id": "week_variety_low", "level": "info",
                    "title": "Limited variety across the week",
                    "detail": (f"Logged foods span {len(groups)} dataset group(s): "
                               f"{', '.join(sorted(groups)) if groups else 'none dataset-based'}.")})
        else:
            patterns.append({
                "id": "week_not_enough", "level": "info",
                "title": "Not enough logged days for weekly patterns",
                "detail": (f"{n} logged day(s) so far — patterns are only claimed from "
                           f"{WEEK_MIN_DAYS_FOR_PATTERN}+ logged days.")})
        s["patterns"] = patterns
        return s

    cur, prev = summarize(current), summarize(previous)
    comparison = None
    if cur and prev and cur["logged_days"] >= WEEK_MIN_DAYS_FOR_PATTERN and prev["logged_days"] >= WEEK_MIN_DAYS_FOR_PATTERN:
        rows = []
        for key, label, unit in (("kcal", "Calories", "kcal"), ("protein_g", "Protein", "g"),
                                 ("carbs_g", "Carbs", "g"), ("fat_g", "Fat", "g"),
                                 ("water_ml", "Water", "ml")):
            c, p = cur["averages"][key], prev["averages"][key]
            delta = round(100.0 * (c - p) / p) if p else None
            rows.append({"metric": label, "unit": unit, "current": c, "previous": p,
                         "delta_pct": delta,
                         "direction": "up" if (delta or 0) > 0 else ("down" if (delta or 0) < 0 else "flat")})
        comparison = {"rows": rows,
                      "note": (f"Compared against {prev['logged_days']} logged day(s) in the "
                               "previous week — averages cover logged days only.")}
    elif cur and not prev:
        comparison = {"rows": [],
                      "note": "No records in the previous week — nothing to compare yet "
                              "(missing records are never shown as a trend)."}
    elif cur and prev:
        # Previous week exists but has insufficient records for a reliable comparison
        comparison = {"rows": [],
                      "note": (f"Previous week has only {prev['logged_days']} logged day(s) — "
                               f"comparison requires {WEEK_MIN_DAYS_FOR_PATTERN}+ logged days in both weeks.")}
    return {
        "window_days": 14,
        "current_week": cur,
        "previous_week": prev,
        "comparison": comparison,
        "missing_days_note": MISSING_DAYS_NOTE,
        "personalized": targets is not None,
        "disclaimer": DISCLAIMER,
    }
