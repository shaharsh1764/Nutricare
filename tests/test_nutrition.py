"""Unit tests for the nutrition mathematics (no server needed)."""

import pytest

from nutricare import nutrition


def test_bmr_female_mifflin_st_jeor():
    # 10*59.8 + 6.25*168 - 5*20 - 161 = 598 + 1050 - 100 - 161 = 1387
    assert nutrition.mifflin_st_jeor_bmr(59.8, 168, 20, "female") == pytest.approx(1387.0)


def test_bmr_male_adds_five():
    assert nutrition.mifflin_st_jeor_bmr(59.8, 168, 20, "male") == pytest.approx(1553.0)


def test_bmr_other_sex_uses_documented_midpoint():
    # midpoint constant -78 = (5 + -161) / 2
    assert nutrition.mifflin_st_jeor_bmr(59.8, 168, 20, "other") == pytest.approx(1470.0)


def test_bmr_rejects_non_positive():
    with pytest.raises(ValueError):
        nutrition.mifflin_st_jeor_bmr(-5, 168, 20, "female")


def test_tdee_moderate_multiplier():
    assert nutrition.tdee(1387.0, "moderate") == pytest.approx(1387.0 * 1.55)


def test_tdee_rejects_unknown_activity():
    with pytest.raises(ValueError):
        nutrition.tdee(1387.0, "extreme")


def test_calorie_target_includes_goal_delta():
    maintain = nutrition.calorie_target(59.8, 168, 20, "female", "moderate", "maintain")
    loss = nutrition.calorie_target(59.8, 168, 20, "female", "moderate", "mild_loss")
    assert maintain - loss == pytest.approx(300)


def test_macro_targets_gram_math():
    targets = nutrition.macro_targets(2000, "balanced")
    assert targets["protein_g"] == pytest.approx(125.0)     # 2000*0.25/4
    assert targets["carbs_g"] == pytest.approx(200.0)       # 2000*0.40/4
    assert targets["fat_g"] == pytest.approx(77.8, abs=0.1)  # 2000*0.35/9


def test_macro_targets_rejects_unknown_model():
    with pytest.raises(ValueError):
        nutrition.macro_targets(2000, "keto_extreme")


def test_scale_per100():
    food = {"kcal": 130, "protein_g": 2.7, "carbs_g": 28.2, "fat_g": 0.3}
    out = nutrition.scale_per100(food, 250)
    assert out["kcal"] == pytest.approx(325.0)
    assert out["protein_g"] == pytest.approx(6.75)


def test_scale_per100_rejects_negative():
    with pytest.raises(ValueError):
        nutrition.scale_per100({"kcal": 100}, -1)


def test_entry_grams_serving_vs_grams():
    food = {"serving_g": 158}
    assert nutrition.entry_grams({"quantity": 2, "unit": "serving"}, food) == 316
    assert nutrition.entry_grams({"quantity": 120, "unit": "g"}, food) == 120


def test_entry_grams_serving_requires_food():
    with pytest.raises(ValueError):
        nutrition.entry_grams({"quantity": 1, "unit": "serving"}, None)


def test_custom_entry_uses_stored_totals():
    entry = {"quantity": 100, "unit": "g", "custom_kcal": 250, "custom_protein_g": 10,
             "custom_carbs_g": 20, "custom_fat_g": 5}
    out = nutrition.entry_nutrients(entry, None)
    assert out["kcal"] == 250 and out["protein_g"] == 10


def test_sum_nutrients():
    rows = [{"kcal": 100, "protein_g": 10}, {"kcal": 50, "protein_g": 5}]
    total = nutrition.sum_nutrients(rows)
    assert total["kcal"] == 150 and total["protein_g"] == 15


def test_micro_targets_sex_specific_iron():
    assert nutrition.micro_targets("female")["iron_mg"] == 18.0
    assert nutrition.micro_targets("male")["iron_mg"] == 8.0
