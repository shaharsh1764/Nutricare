"""NutriCare nutrition mathematics.

All functions are pure (no DB / no Flask) so they can be unit-tested directly.
Formulas used:
  * Basal metabolic rate (BMR): Mifflin-St Jeor equation (widely used clinical
    estimation formula, e.g. referenced by the Academy of Nutrition and Dietetics).
      male:   BMR = 10*weight_kg + 6.25*height_cm - 5*age + 5
      female: BMR = 10*weight_kg + 6.25*height_cm - 5*age - 161
  * Total daily energy expenditure (TDEE) = BMR * activity factor
    (standard PAL multipliers, see e.g. FAO/WHO/UNU energy requirement reports).
  * Macro gram targets from a calorie target and a distribution model:
      protein 4 kcal/g, carbohydrate 4 kcal/g, fat 9 kcal/g.
"""

from __future__ import annotations

# ---------------------------------------------------------------- constants

KCAL_PER_G = {"protein": 4.0, "carbs": 4.0, "fat": 9.0}

ACTIVITY_FACTORS = {
    "sedentary": 1.2,      # desk study, little exercise
    "light": 1.375,        # light exercise 1-3 days/week
    "moderate": 1.55,      # moderate exercise 3-5 days/week
    "active": 1.725,       # hard exercise 6-7 days/week
    "very_active": 1.9,    # physical job + training
}

GOAL_DELTAS = {           # kcal added to TDEE
    "maintain": 0,
    "mild_loss": -300,
    "mild_gain": 300,
}

# fraction of calories from (carbs, protein, fat)
MACRO_MODELS = {
    "balanced":     {"carbs": 0.40, "protein": 0.25, "fat": 0.35},
    "high_protein": {"carbs": 0.30, "protein": 0.35, "fat": 0.35},
    "low_carb":     {"carbs": 0.25, "protein": 0.35, "fat": 0.40},
}

# Daily micronutrient reference targets used by Reports (adult reference values,
# rounded; iron is sex-specific). Sources: ICMR-NIN 2020 / USDA Dietary Guidelines.
MICRO_TARGETS = {
    "fiber_g": 28.0,
    "sodium_mg": 2300.0,      # upper limit, not a target
    "potassium_mg": 3500.0,
    "calcium_mg": 1000.0,
}
IRON_TARGET = {"female": 18.0, "male": 8.0, "other": 14.0}

NUTRIENT_KEYS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g",
                 "sodium_mg", "potassium_mg", "calcium_mg", "iron_mg")


# ---------------------------------------------------------------- energy

def mifflin_st_jeor_bmr(weight_kg: float, height_cm: float, age: int, sex: str) -> float:
    """Return BMR in kcal/day using the Mifflin-St Jeor equation.

    sex == 'other' (or 'prefer not to say') uses the midpoint of the male/female
    constants (-78): a documented assumption, clearly labelled as an estimate
    in the UI. This is a population formula, never a diagnosis.
    """
    if weight_kg is None or height_cm is None or age is None:
        raise ValueError("weight, height and age are required")
    if weight_kg <= 0 or height_cm <= 0 or age <= 0:
        raise ValueError("weight, height and age must be positive")
    constant = {"male": 5, "female": -161}.get(sex, -78)
    base = 10.0 * weight_kg + 6.25 * height_cm - 5.0 * age
    return base + constant


def tdee(bmr: float, activity: str) -> float:
    if activity not in ACTIVITY_FACTORS:
        raise ValueError(f"unknown activity level {activity!r}")
    return bmr * ACTIVITY_FACTORS[activity]


def calorie_target(weight_kg, height_cm, age, sex, activity, goal="maintain") -> float:
    """Personalised daily calorie target (TDEE adjusted for goal)."""
    if goal not in GOAL_DELTAS:
        raise ValueError(f"unknown goal {goal!r}")
    return max(800.0, tdee(mifflin_st_jeor_bmr(weight_kg, height_cm, age, sex),
                           activity) + GOAL_DELTAS[goal])


def macro_targets(kcal: float, model: str = "balanced") -> dict:
    """Gram targets for protein/carbs/fat for a calorie target."""
    if model not in MACRO_MODELS:
        raise ValueError(f"unknown macro model {model!r}")
    frac = MACRO_MODELS[model]
    return {
        "protein_g": round(kcal * frac["protein"] / KCAL_PER_G["protein"], 1),
        "carbs_g": round(kcal * frac["carbs"] / KCAL_PER_G["carbs"], 1),
        "fat_g": round(kcal * frac["fat"] / KCAL_PER_G["fat"], 1),
        "model": model,
        "fractions": frac,
    }


# ---------------------------------------------------------------- food maths

def scale_per100(food: dict, grams: float) -> dict:
    """Scale per-100g nutrient values to `grams`. Returns rounded dict."""
    if grams is None or grams < 0:
        raise ValueError("grams must be >= 0")
    factor = grams / 100.0
    out = {}
    for key in NUTRIENT_KEYS:
        out[key] = round(float(food.get(key) or 0.0) * factor, 2)
    return out


def entry_grams(entry: dict, food: dict | None) -> float:
    """Grams actually eaten for a meal entry.

    unit == 'serving' -> quantity * food.serving_g
    unit == 'g'       -> quantity grams directly
    """
    qty = float(entry.get("quantity"))
    unit = entry.get("unit")
    if unit == "g":
        return qty
    if unit == "serving":
        if food is None or not food.get("serving_g"):
            raise ValueError("serving unit requires a database food with serving_g")
        return qty * float(food["serving_g"])
    raise ValueError(f"unknown unit {unit!r}")


def entry_nutrients(entry: dict, food: dict | None) -> dict:
    """Nutrients for one meal entry (custom entries carry their own totals)."""
    if food is None:  # custom / manual entry: values stored per entry
        return {
            "kcal": float(entry.get("custom_kcal") or 0),
            "protein_g": float(entry.get("custom_protein_g") or 0),
            "carbs_g": float(entry.get("custom_carbs_g") or 0),
            "fat_g": float(entry.get("custom_fat_g") or 0),
            "fiber_g": 0.0, "sodium_mg": 0.0, "potassium_mg": 0.0,
            "calcium_mg": 0.0, "iron_mg": 0.0,
            "grams": float(entry.get("quantity") or 0),
        }
    grams = entry_grams(entry, food)
    nutrients = scale_per100(food, grams)
    nutrients["grams"] = round(grams, 2)
    return nutrients


def sum_nutrients(rows: list[dict]) -> dict:
    """Sum a list of nutrient dicts over NUTRIENT_KEYS."""
    total = {k: 0.0 for k in NUTRIENT_KEYS}
    for row in rows:
        for k in NUTRIENT_KEYS:
            total[k] += float(row.get(k) or 0.0)
    return {k: round(v, 2) for k, v in total.items()}


def micro_targets(sex: str) -> dict:
    t = dict(MICRO_TARGETS)
    t["iron_mg"] = IRON_TARGET.get(sex, IRON_TARGET["other"])
    return t
