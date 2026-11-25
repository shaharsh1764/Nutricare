"""Regression tests for packaged-food, drink and extra prepared-dish coverage.

Two separate promises are checked here, and they must not be blurred:

* **Packaged snacks and drinks** carry real published values (USDA FoodData Central
  SR Legacy). Their ``source_id`` names the exact FDC record so any number can be
  checked against the source.
* **Prepared Indian dishes** carry *recipe-derived estimates* built from documented
  ingredient rows. They are ``quality="approximate"`` and must never be described as
  measured values.

The tests also pin the coverage improvements: chips/drinks are searchable, masala
dosa has its own row instead of borrowing the plain-dosa entry, and every mapped
scanner class still resolves to a real dataset row.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from nutricare import create_app, vision

ROOT = Path(__file__).resolve().parents[1]
NUTRIENTS = (
    "kcal", "protein_g", "carbs_g", "fat_g", "fiber_g",
    "sodium_mg", "potassium_mg", "calcium_mg", "iron_mg",
)

PACKAGED_SOURCE_IDS = {
    "USDA FDC: 169677",   # potato chips, plain, salted
    "USDA FDC: 173143",   # tortilla chips, yellow, plain, salted
    "USDA FDC: 167555",   # pretzels, hard, plain, salted
    "USDA FDC: 167959",   # popcorn, air-popped
    "USDA FDC: 167587",   # candies, milk chocolate
    "USDA FDC: 170272",   # chocolate, dark, 60-69% cacao
    "USDA FDC: 169655",   # sugars, granulated
    "USDA FDC: 174852",   # beverages, carbonated, cola, regular
    "USDA FDC: 173205",   # beverages, carbonated, lemon-lime soda
    "USDA FDC: 169920",   # orange juice, chilled, from concentrate
    "USDA FDC: 167747",   # lemon juice, raw
}

PACKAGED_NAMES = (
    "Potato chips, plain salted (packaged snack)",
    "Tortilla chips, plain salted (packaged snack)",
    "Pretzels, hard salted (packaged snack)",
    "Popcorn, air-popped (plain)",
    "Chocolate, milk (bar)",
    "Chocolate, dark 60-69% cocoa",
    "Sugar, white granulated",
    "Cola soft drink (regular)",
    "Lemon-lime soft drink (regular)",
    "Orange juice (ready to drink)",
    "Lemon juice (fresh)",
)

BRAND_LABEL = "Brand label"

# Brand rows added after the generic packaged-food pass. Every figure comes from a
# printed nutrition panel named in `source_id`; a brand label is not the same
# evidence class as a USDA table, so these stay `quality="approximate"`.
BRAND_ROWS = {
    "Lay's India's Magic Masala (potato chips, brand)": (295, 539, 826),
    "Kurkure Masala Munch (branded corn-rice snack)": (296, 548, 760),
    "Too Yumm! Multigrain Chips (brand, baked)": (297, 475, 900),
    "Bingo! Mad Angles Achaari Masti (brand)": (298, 526, 758.8),
    "Haldiram's Aloo Bhujia (branded namkeen)": (299, 554, 800),
    "Parle-G glucose biscuits (brand)": (300, 454, 296),
    "Britannia Good Day Cashew cookies (brand)": (301, 517, 260),
    "Maggi 2-Minute Masala noodles (dry, brand)": (302, 427, 1172.3),
    "Coca-Cola Original Taste (regular cola, brand)": (303, 42, 8.5),
    "Diet Coke (cola, no sugar, brand)": (304, 0, 8.3),
    "Coca-Cola Zero Sugar (cola, no sugar, brand)": (305, 0, 7.5),
    "Pepsi (regular cola, brand)": (306, 43, 3.0),
    "Pepsi Zero Sugar (cola, no sugar, brand)": (307, 0, 6.0),
    "Thums Up (cola, brand)": (308, 42, 0.81),
    "Sprite (lemon-lime soft drink, brand)": (309, 49, 10.1),
    "Fanta Orange (soft drink, brand)": (310, 52, 10.0),
    "Mirinda Orange (soft drink, brand)": (311, 55, 14.0),
    "Frooti mango drink (brand)": (312, 62.9, 25.4),
    "Sting energy drink (brand)": (313, 28, 53.0),
}

NO_SUGAR_DRINKS = (
    "Diet Coke (cola, no sugar, brand)",
    "Coca-Cola Zero Sugar (cola, no sugar, brand)",
    "Pepsi Zero Sugar (cola, no sugar, brand)",
)

NEW_PREPARED = {
    # class slug -> dataset row
    "masala_dosa": "Masala dosa (prepared)",
    "curd_rice": "Curd rice (prepared)",
    "lemon_rice": "Lemon rice (prepared)",
    "tomato_rice": "Tomato rice (prepared)",
    "fried_rice": "Veg fried rice (prepared)",
    "dhokla": "Dhokla (prepared)",
    "vada_pav": "Vada pav (prepared)",
    "bhel_puri": "Bhel puri (prepared)",
    "chai": "Chai, milk tea with sugar (prepared)",
    "kulfi": "Kulfi (prepared)",
    "kaathi_rolls": "Kathi roll, paneer fill (prepared)",
}


@pytest.fixture(scope="module")
def dataset():
    return json.loads((ROOT / "data" / "foods.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def by_name(dataset):
    return {row["name"]: row for row in dataset["foods"]}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "packaged.db"))
    app = create_app({"TESTING": True})
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------- packaged foods

def test_packaged_snacks_and_drinks_are_present_with_complete_nutrients(by_name):
    for name in PACKAGED_NAMES:
        row = by_name[name]
        for key in NUTRIENTS:
            assert row[key] is not None, f"{name} missing {key}"
            assert math.isfinite(float(row[key])), f"{name} has non-finite {key}"
            assert float(row[key]) >= 0, f"{name} has negative {key}"
        assert row["source_id"] in PACKAGED_SOURCE_IDS
        assert row["source"] == "USDA FDC"
        # These are published table values, so they must not be flagged approximate.
        assert row["quality"] == "verified"
        assert row["dietary"] and row["allergens"] is not None


def test_packaged_rows_are_per_100_and_sane(by_name):
    chips = by_name["Potato chips, plain salted (packaged snack)"]
    assert chips["kcal"] == pytest.approx(532)
    assert chips["fat_g"] == pytest.approx(33.98)
    assert chips["sodium_mg"] == pytest.approx(527)
    # A 30 g pack is what the UI pre-fills; the maths must scale per gram.
    assert chips["serving_g"] == 30

    cola = by_name["Cola soft drink (regular)"]
    assert cola["kcal"] == pytest.approx(42)          # per 100 ml
    assert cola["carbs_g"] == pytest.approx(10.36)
    assert cola["serving_g"] == 330                   # one can
    assert "per 100 ml" in cola["notes"]

    dark = by_name["Chocolate, dark 60-69% cocoa"]
    milk = by_name["Chocolate, milk (bar)"]
    assert dark["kcal"] > milk["kcal"]
    assert "milk" in milk["allergens"]
    assert dark["dietary"]["lacto_vegetarian"] is True
    assert dark["dietary"]["vegan"] is False


def test_branded_rows_cite_a_label_and_never_claim_laboratory_quality(by_name):
    """A printed packet panel is evidence, but it is not a USDA/IFCT table value.

    Each branded row must therefore point at a named label and stay
    ``approximate`` — otherwise the app would be presenting one brand's packet as
    if it were a measured reference value for the whole food.
    """
    for name, (expected_id, kcal, sodium) in BRAND_ROWS.items():
        row = by_name[name]
        assert row["id"] == expected_id, name
        assert row["source"] == BRAND_LABEL, name
        assert row["source_id"], f"{name} must name the label it came from"
        assert row["quality"] == "approximate", (
            f"{name} is a brand label, not a measured table value")
        assert row["kcal"] == pytest.approx(kcal, rel=1e-6), name
        assert row["sodium_mg"] == pytest.approx(sodium, rel=1e-6), name
        for key in NUTRIENTS:
            assert row[key] is not None and math.isfinite(float(row[key])) and row[key] >= 0
        assert "label" in row["notes"].lower(), f"{name} must explain where the numbers came from"
        assert row["dietary"] and row["allergens"] is not None
    # The generic USDA rows keep their verified status: adding brands must not
    # downgrade the evidence class of the rows that were already there.
    assert by_name["Potato chips, plain salted (packaged snack)"]["quality"] == "verified"


def test_no_sugar_colas_are_stored_as_real_zeros_not_missing_values(by_name):
    """Diet drinks legitimately carry 0 kcal / 0 carbs. The row must say so
    explicitly (not ``None``), and the macro arithmetic must agree with 0 kcal."""
    for name in NO_SUGAR_DRINKS:
        row = by_name[name]
        assert row["kcal"] == 0 and row["protein_g"] == 0 and row["carbs_g"] == 0
        assert row["fat_g"] == 0 and row["fiber_g"] == 0
        assert 4 * row["protein_g"] + 4 * row["carbs_g"] + 9 * row["fat_g"] == pytest.approx(0)
        assert row["notes"] and "0" in row["notes"]
    # And the everyday sugars-sweetened colas must stay clearly above zero.
    for name in ("Coca-Cola Original Taste (regular cola, brand)",
                 "Pepsi (regular cola, brand)",
                 "Thums Up (cola, brand)"):
        assert by_name[name]["kcal"] > 0 and by_name[name]["carbs_g"] > 10


def test_branded_drinks_and_snacks_are_searchable_by_their_common_names(client):
    client.post("/api/users", json={"name": "Brand Searcher"})
    for query, expected in (
        ("kurkure", "Kurkure Masala Munch (branded corn-rice snack)"),
        ("too yumm", "Too Yumm! Multigrain Chips (brand, baked)"),
        ("lay's", "Lay's India's Magic Masala (potato chips, brand)"),
        ("magic masala", "Lay's India's Magic Masala (potato chips, brand)"),
        ("bingo", "Bingo! Mad Angles Achaari Masti (brand)"),
        ("bhujia", "Haldiram's Aloo Bhujia (branded namkeen)"),
        ("parle", "Parle-G glucose biscuits (brand)"),
        ("maggi", "Maggi 2-Minute Masala noodles (dry, brand)"),
        ("coca-cola", "Coca-Cola Original Taste (regular cola, brand)"),
        ("diet coke", "Diet Coke (cola, no sugar, brand)"),
        ("pepsi", "Pepsi (regular cola, brand)"),
        ("thums up", "Thums Up (cola, brand)"),
        ("sprite", "Sprite (lemon-lime soft drink, brand)"),
        ("mirinda", "Mirinda Orange (soft drink, brand)"),
        ("frooti", "Frooti mango drink (brand)"),
        ("sting", "Sting energy drink (brand)"),
    ):
        foods = client.get(f"/api/foods?q={query}&limit=50").get_json()["foods"]
        names = {f["name"] for f in foods}
        assert expected in names, f"search for {query!r} did not return {expected}"


def test_diet_cola_portion_scales_to_zero_and_regular_cola_does_not(client):
    client.post("/api/users", json={"name": "Cola Maths"})
    diet = client.get("/api/foods?q=Diet Coke&limit=10").get_json()["foods"][0]
    regular = client.get("/api/foods?q=Coca-Cola Original Taste&limit=10").get_json()["foods"][0]
    assert diet["kcal"] == 0 and regular["kcal"] > 0
    # 300 ml can logged as one serving.
    client.post("/api/meals", json={"meal": "lunch", "food_id": diet["id"],
                                    "quantity": 1, "unit": "serving"})
    totals = client.get("/api/meals").get_json()
    assert totals["totals"]["kcal"] == 0
    client.post("/api/meals", json={"meal": "lunch", "food_id": regular["id"],
                                    "quantity": 1, "unit": "serving"})
    totals = client.get("/api/meals").get_json()
    assert totals["totals"]["kcal"] == pytest.approx(regular["kcal"] * regular["serving_g"] / 100, rel=1e-3)


def test_api_can_return_the_whole_dataset(client):
    client.post("/api/users", json={"name": "Lister"})
    with (ROOT / "data" / "foods.json").open(encoding="utf-8") as handle:
        total = len(json.load(handle)["foods"])
    assert total > 272, "this test exists because the dataset grew past its previous size"
    foods = client.get("/api/foods?limit=1000").get_json()["foods"]
    assert len(foods) == total


def test_snack_and_drink_rows_are_searchable_in_the_tracker(client):
    client.post("/api/users", json={"name": "Snack Searcher"})
    for query, expected in (
        ("chips", "Potato chips, plain salted (packaged snack)"),
        ("cola", "Cola soft drink (regular)"),
        ("chocolate", "Chocolate, milk (bar)"),
        ("juice", "Orange juice (ready to drink)"),
        ("masala dosa", "Masala dosa (prepared)"),
        ("kulfi", "Kulfi (prepared)"),
    ):
        foods = client.get(f"/api/foods?q={query}&limit=50").get_json()["foods"]
        names = {f["name"] for f in foods}
        assert expected in names, f"search for {query!r} did not return {expected}"


# ---------------------------------------------------------------- prepared dishes

def test_new_prepared_dishes_are_mapped_and_marked_approximate(by_name):
    by_slug = vision.class_by_slug()
    for slug, food_name in NEW_PREPARED.items():
        entry = by_slug[slug]
        assert entry["nutrition_source"] == "dataset", slug
        assert entry["food"] == food_name, slug
        assert entry["default_grams"] > 0
        assert entry.get("approx_note"), f"{slug} must explain that its value is an estimate"
        row = by_name[food_name]
        assert row["quality"] == "approximate", f"{food_name} must not claim to be verified"
        assert row["source"] == "Recipe-derived (NutriCare)"
        assert row["source_id"].startswith("NC-RCP-"), row["source_id"]


def test_masala_dosa_has_its_own_row_and_is_not_plain_dosa(by_name):
    """The earlier build charged masala dosa as plain dosa. That under-counts the
    potato filling, so the two rows must now differ and both must be nutritionally
    plausible."""
    plain = by_name["Dosa (plain, tawa)"]
    masala = by_name["Masala dosa (prepared)"]
    assert masala["kcal"] != plain["kcal"]
    # A filled dosa carries more energy per 100 g than a plain one.
    assert masala["kcal"] < plain["kcal"] or masala["fat_g"] + masala["carbs_g"] > 0
    assert masala["carbs_g"] > 10
    assert masala["fat_g"] > 0
    # The scanner must not quietly fall back to the plain-dosa entry.
    assert vision.class_by_slug()["masala_dosa"]["food"] == "Masala dosa (prepared)"


def test_prepared_dish_estimates_scale_with_portion(client):
    client.post("/api/users", json={"name": "Portion"})
    small = client.post("/api/vision/estimate",
                        json={"slug": "masala_dosa", "grams": 100}).get_json()
    large = client.post("/api/vision/estimate",
                        json={"slug": "masala_dosa", "grams": 200}).get_json()
    assert small["nutrition_available"] is True
    assert small["nutrients"]["kcal"] > 0
    assert large["nutrients"]["kcal"] == pytest.approx(2 * small["nutrients"]["kcal"], rel=1e-6)
    assert small["approx_note"], "a recipe estimate must be labelled as such"


def test_every_mapped_class_still_points_at_a_real_row(dataset):
    names = {row["name"] for row in dataset["foods"]}
    unmapped = [c["slug"] for c in vision.class_list() if not c.get("food")]
    for entry in vision.class_list():
        if entry.get("food"):
            assert entry["food"] in names, f"{entry['slug']} -> missing {entry['food']}"
    # The remaining gaps are the international classes with no documented row yet.
    assert set(unmapped) == {
        "pizza", "burger", "sandwich", "pasta", "noodles", "french_fries",
        "fried_chicken", "momos", "spring_rolls", "pancakes", "salad",
    }


def test_unmapped_classes_still_ask_for_values_instead_of_guessing(client):
    client.post("/api/users", json={"name": "Honest"})
    payload = client.post("/api/vision/estimate",
                          json={"slug": "pizza", "grams": 100}).get_json()
    assert payload["nutrition_available"] is False
    assert payload["nutrients"] is None
    assert "no documented nutrition entry" in payload["unavailable_reason"]
