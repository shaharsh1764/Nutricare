"""The active image classifiers must resolve to documented nutrition rows."""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NUTRIENTS = (
    "kcal", "protein_g", "carbs_g", "fat_g", "fiber_g",
    "sodium_mg", "potassium_mg", "calcium_mg", "iron_mg",
)


def _load(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_primary_and_fallback_model_classes_have_complete_documented_nutrition():
    classes_data = _load("data/food_classes.json")
    foods_data = _load("data/foods.json")
    primary = _load("models/v2/food_classifier_indian_80_224.metrics.json")["class_names"]
    fallback = list(_load("models/food_classifier_cc0.metrics.json")["dataset"]["classes"])
    by_slug = {row["slug"]: row for row in classes_data["classes"]}
    by_name = {row["name"]: row for row in foods_data["foods"]}

    assert len(primary) == 80
    assert classes_data["_meta"]["trained_model_coverage"]["classes"] == primary
    assert classes_data["_meta"]["fallback_model_coverage"]["classes"] == fallback
    assert len(fallback) == 12
    assert foods_data["_meta"]["total_foods"] == len(foods_data["foods"])

    for slug in primary + fallback:
        entry = by_slug[slug]
        food = by_name[entry["food"]]
        assert entry["nutrition_source"] == "dataset"
        assert all(food.get(key) is not None and math.isfinite(float(food[key]))
                   for key in NUTRIENTS), (slug, food["name"])
        assert food["quality"] in {"verified", "approximate"}
        assert food["source"]
        assert food["allergens"] is not None and food["dietary"] is not None


def test_recipe_derived_model_foods_are_reproducible_and_explicitly_approximate():
    foods = _load("data/foods.json")["foods"]
    profile_doc = _load("data/model_food_recipe_profiles.json")
    by_id = {row["id"]: row for row in foods}
    by_source = {row["source_id"]: row for row in foods if row.get("source_id")}
    # 68 rows shipped with the 80-class coverage audit, plus the prepared dishes added
    # later. Keep the shipped audit count as a floor so rows cannot silently disappear.
    assert len(profile_doc["profiles"]) >= 68
    assert "not laboratory" in profile_doc["limitations"].lower()

    for profile in profile_doc["profiles"]:
        food = by_source[profile["recipe_id"]]
        assert food["name"] == profile["food_name"]
        assert food["quality"] == "approximate"
        assert food["source"] == "Recipe-derived (NutriCare)"
        assert math.isclose(
            sum(item["grams_per_100g"] for item in profile["ingredients"])
            + profile["water_g_per_100g"], 100.0, abs_tol=0.02,
        )
        salt_grams = sum(
            item["grams_per_100g"] for item in profile["ingredients"]
            if item.get("ingredient") == "salt"
        )
        assert math.isclose(salt_grams, profile["salt_g_per_100g"], abs_tol=0.001)
        computed = {key: 0.0 for key in NUTRIENTS}
        for ingredient in profile["ingredients"]:
            if "food_id" not in ingredient:
                assert ingredient["ingredient"] == "salt"
                computed["sodium_mg"] += ingredient["grams_per_100g"] * 393.4
                continue
            source = by_id[ingredient["food_id"]]
            grams = ingredient["grams_per_100g"]
            for key in NUTRIENTS:
                computed[key] += float(source.get(key) or 0) * grams / 100
        for key in NUTRIENTS:
            assert math.isclose(food[key], computed[key], abs_tol=0.11), (
                profile["slug"], key, food[key], computed[key]
            )
