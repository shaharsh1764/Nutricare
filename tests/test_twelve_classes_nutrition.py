"""Nutrition contract for the 12 classes the shipped CC0 model can predict.

Three properties matter here, and each has been violated somewhere in this
project's history, so each gets a test:

1. Every one of the 12 trained classes resolves to a documented food row.
2. Missing nutrition is reported as missing — never as a 0 kcal measurement.
3. Recipe-derived values are labelled approximate and carry their derivation,
   so a reader can check the arithmetic instead of trusting a number.
"""

import json
from pathlib import Path

import pytest

from nutricare import vision

# The classes in models/food_classifier_cc0.pt.
TRAINED_12 = [
    "chicken_biryani", "chole", "chomchom", "curd_dahi", "jalebi", "kheer",
    "khichdi", "morog_polao", "pakora", "pani_puri", "paratha_plain", "rasgulla",
]

PROJECT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "twelve.db"))
    monkeypatch.setenv("NUTRICARE_MODEL", str(tmp_path / "absent.pt"))
    vision.reset_predictor()
    from nutricare import create_app
    application = create_app({"TESTING": True})
    yield application
    vision.reset_predictor()


@pytest.fixture()
def client(app, tmp_path):
    with app.test_client() as c:
        c.post("/api/users", json={"name": "Twelve"})
        yield c


def test_all_twelve_trained_classes_are_in_the_taxonomy():
    slugs = {e["slug"] for e in vision.class_list()}
    missing = [s for s in TRAINED_12 if s not in slugs]
    assert not missing, f"trained classes absent from taxonomy: {missing}"


def test_all_twelve_have_documented_nutrition():
    """No trained class may be left with an empty nutrition path."""
    by_slug = vision.class_by_slug()
    undocumented = [s for s in TRAINED_12
                    if not by_slug[s].get("food")
                    or by_slug[s]["nutrition_source"] != "dataset"]
    assert not undocumented, f"no documented nutrition for: {undocumented}"


def test_twelve_rows_exist_in_the_food_dataset():
    rows = {f["name"] for f in json.loads(
        (PROJECT / "data" / "foods.json").read_text(encoding="utf-8"))["foods"]}
    by_slug = vision.class_by_slug()
    for slug in TRAINED_12:
        assert by_slug[slug]["food"] in rows, f"{slug} -> missing row"


@pytest.mark.parametrize("slug", TRAINED_12)
def test_estimate_returns_real_energy_for_every_trained_class(client, slug):
    """A real portion must yield a positive calorie figure — not zero, not null."""
    payload = client.post("/api/vision/estimate",
                          json={"slug": slug, "grams": 100}).get_json()
    assert payload["nutrition_available"] is True
    nutrients = payload["nutrients"]
    assert nutrients is not None
    assert nutrients["kcal"] > 0, f"{slug} reports {nutrients['kcal']} kcal"
    # requested portion is echoed top-level, not inside nutrients
    assert payload["grams"] == 100


@pytest.mark.parametrize("slug", TRAINED_12)
def test_missing_nutrition_is_never_reported_as_zero(client, slug):
    """The specific bug: 'no data' must not be serialised as 0 kcal.

    Either the class has real data (kcal > 0), or it explicitly reports
    nutrition_available False with nutrients=None. 0 kcal is not a valid answer
    for either branch.
    """
    payload = client.post("/api/vision/estimate",
                          json={"slug": slug, "grams": 150}).get_json()
    if payload["nutrition_available"]:
        assert payload["nutrients"]["kcal"] > 0
    else:
        assert payload["nutrients"] is None
        assert payload.get("unavailable_reason")


def test_undocumented_class_still_reports_unavailable_not_zero(client):
    """The honest path must survive: 26 taxonomy classes have no row."""
    by_slug = vision.class_by_slug()
    empty = [s for s, e in by_slug.items() if not e.get("food")]
    assert empty, "expected some taxonomy classes to remain undocumented"
    payload = client.post("/api/vision/estimate",
                          json={"slug": empty[0], "grams": 100}).get_json()
    assert payload["nutrition_available"] is False
    assert payload["nutrients"] is None
    assert "unavailable_reason" in payload


@pytest.mark.parametrize("slug", ["chomchom", "pakora", "pani_puri", "jalebi",
                                  "morog_polao"])
def test_recipe_derived_rows_are_flagged_approximate_with_their_derivation(slug):
    """A recipe-derived number must say so, and say how it was obtained."""
    entry = vision.class_by_slug()[slug]
    assert entry["nutrition_source"] == "dataset"
    assert entry.get("approx_note"), f"{slug} has no approximation note"

    foods = {f["name"]: f for f in json.loads(
        (PROJECT / "data" / "foods.json").read_text(encoding="utf-8"))["foods"]}
    row = foods[entry["food"]]
    assert row["quality"] == "approximate", f"{slug} row not marked approximate"
    assert row["source"] == "Recipe-derived (NutriCare)"
    # the derivation must be recorded, not just the number
    assert "recipe" in row["source_id"].lower()
    assert row["kcal"] > 0


def test_portion_scaling_still_works_for_a_recipe_derived_class(client):
    """Doubling the portion must double the energy, exactly as before."""
    small = client.post("/api/vision/estimate",
                        json={"slug": "pakora", "grams": 100}).get_json()
    large = client.post("/api/vision/estimate",
                        json={"slug": "pakora", "grams": 200}).get_json()
    assert abs(large["nutrients"]["kcal"] - 2 * small["nutrients"]["kcal"]) < 0.5


def test_recipe_derived_class_can_be_logged_without_manual_values(client):
    """These classes now carry data, so the manual-values prompt must not fire."""
    resp = client.post("/api/vision/log",
                       json={"slug": "pakora", "grams": 80, "meal": "snacks"})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    diary = client.get("/api/meals").get_json()
    logged = diary["meals"]["snacks"]
    assert logged and logged[0]["nutrients"]["kcal"] > 0


def test_manual_entry_still_works_for_an_undocumented_class(client):
    """Preserved behaviour: no data means the user supplies the values."""
    by_slug = vision.class_by_slug()
    empty = next(s for s, e in by_slug.items() if not e.get("food"))

    refused = client.post("/api/vision/log",
                          json={"slug": empty, "grams": 100, "meal": "lunch"})
    assert refused.status_code == 400
    assert refused.get_json().get("needs_manual_values") is True

    accepted = client.post("/api/vision/log",
                           json={"slug": empty, "grams": 100, "meal": "lunch",
                                 "custom_kcal": 220, "custom_protein_g": 6})
    assert accepted.status_code == 201, accepted.get_data(as_text=True)
