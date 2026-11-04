"""Dataset quality tests for expanded ~200 food dataset.

Covers schema validity, duplicates, units, dietary/allergen metadata,
and that recommendations/search/logging still work with new foods.
"""
import json
from pathlib import Path

import pytest
from nutricare import create_app

DATA_PATH = Path(__file__).parent.parent / "data" / "foods.json"

@pytest.fixture
def dataset():
    payload = json.loads(DATA_PATH.read_text())
    return payload["foods"], payload.get("_meta", {})

@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "test.db"))
    return create_app({"TESTING": True})

@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c

def new_user(client, name="Dataset Tester", **profile):
    r = client.post("/api/users", json={"name": name})
    assert r.status_code == 201, r.get_json()
    if profile:
        r = client.put("/api/profile", json=profile)
        assert r.status_code == 200, r.get_json()
    return r.get_json()

# ---------------- schema validity
def test_dataset_schema_validity(dataset):
    foods, meta = dataset
    assert len(foods) >= 180, f"expected ~200 foods, got {len(foods)}"
    assert len(foods) <= 220, f"too many foods: {len(foods)}"
    required = {"id","name","grp","serving_desc","serving_g","kcal","protein_g","carbs_g","fat_g","fiber_g","sodium_mg","potassium_mg","calcium_mg","iron_mg","source","source_id","state","quality","dietary","allergens"}
    for f in foods:
        missing = required - set(f.keys())
        assert not missing, f"{f['name']} missing {missing}"
        # types
        assert isinstance(f["id"], int) and f["id"] > 0
        assert isinstance(f["name"], str) and f["name"].strip()
        assert isinstance(f["grp"], str) and f["grp"].strip()
        assert isinstance(f["serving_g"], (int,float)) and f["serving_g"] > 0
        assert f["state"] in {"raw","dry","cooked","prepared"}
        assert f["quality"] in {"verified","approximate","illustrative"}

def test_duplicate_ids(dataset):
    foods, _ = dataset
    ids = [f["id"] for f in foods]
    assert len(ids) == len(set(ids)), "duplicate ids found"
    names = [f["name"] for f in foods]
    assert len(names) == len(set(names)), f"duplicate names: {[n for n in set(names) if names.count(n)>1]}"
    # stable ids 1-42 preserved
    orig_names = {"Roti, whole wheat (cooked)", "Rice, white (cooked)", "Paneer (plain, whole milk)"}
    for n in orig_names:
        assert any(f["name"]==n for f in foods), f"original food {n} missing"

def test_original_ids_preserved(dataset):
    foods,_ = dataset
    # IDs 1..42 must exist and be original foods
    ids = {f["id"]: f["name"] for f in foods}
    assert ids[1] == "Roti, whole wheat (cooked)"
    assert ids[2] == "Rice, white (cooked)"
    assert ids[42] == "Ghee"

def test_missing_nutritional_values(dataset):
    foods,_ = dataset
    for f in foods:
        for key in ["kcal","protein_g","carbs_g","fat_g","fiber_g","sodium_mg","potassium_mg","calcium_mg","iron_mg"]:
            assert f[key] is not None, f"{f['name']} missing {key}"
            assert isinstance(f[key], (int,float)), f"{f['name']} bad type for {key}"
            assert f[key] >=0, f"{f['name']} negative {key}"

def test_unit_consistency(dataset):
    foods,_ = dataset
    for f in foods:
        assert f["serving_g"] > 0 and f["serving_g"] <= 1000, f"{f['name']} serving_g out of range"
        # serving_desc should mention serving_g or be plausible
        assert isinstance(f["serving_desc"], str) and len(f["serving_desc"])>0
        # per 100g sanity: kcal per 100g between 0 and 900 (oil max)
        assert 0 <= f["kcal"] <= 900, f"{f['name']} kcal out of range {f['kcal']}"
        # protein < 90, carbs <100 etc
        assert 0 <= f["protein_g"] <= 90
        assert 0 <= f["carbs_g"] <= 100
        assert 0 <= f["fat_g"] <= 100

def test_dietary_classifications(dataset):
    foods,_ = dataset
    for f in foods:
        d = f["dietary"]
        assert isinstance(d, dict)
        for k in ["lacto_vegetarian","ovo_vegetarian","lacto_ovo_vegetarian","vegan","non_vegetarian"]:
            assert k in d and isinstance(d[k], bool), f"{f['name']} missing dietary {k}"
        # at least one true
        assert any(d.values()), f"{f['name']} no dietary true"
        # vegan => all veg true, non_veg false
        if d["vegan"]:
            assert d["lacto_vegetarian"] and d["lacto_ovo_vegetarian"] and not d["non_vegetarian"]
        if d["non_vegetarian"]:
            # per policy eggs are non-veg
            pass
    # specific policy: Egg is non-veg
    egg = next(f for f in foods if f["name"]=="Egg, whole (boiled)")
    assert egg["dietary"]["non_vegetarian"] is True
    assert egg["dietary"]["lacto_vegetarian"] is False
    # Dal is vegan
    dal = next(f for f in foods if f["name"]=="Dal, toor/arhar (cooked, no added salt)")
    assert dal["dietary"]["vegan"] is True

def test_allergen_metadata(dataset):
    foods,_ = dataset
    allowed = {"milk","peanut","tree_nut","soy","wheat","fish","shellfish","egg","sesame"}
    for f in foods:
        al = f["allergens"]
        assert isinstance(al, list), f"{f['name']} allergens not list"
        for a in al:
            assert a in allowed, f"{f['name']} unknown allergen {a}"
    # coverage: each required allergen appears at least once
    all_al = set(a for f in foods for a in f["allergens"])
    for req in ["milk","peanut","tree_nut","soy","wheat","fish","shellfish","egg","sesame"]:
        assert req in all_al, f"allergen {req} missing from dataset"

def test_allergen_filtering_requires_metadata(client):
    """Milk allergy must filter via allergen metadata, not just name substring."""
    FULL = {"age":25,"sex":"female","height_cm":165,"weight_kg":60,"activity":"moderate"}
    new_user(client, **FULL)
    client.put("/api/profile", json={"allergies":["milk"]})
    # Log roti to trigger protein gap recommendations
    foods = client.get("/api/foods?q=Roti, whole wheat&limit=50").get_json()["foods"]
    roti = next(f for f in foods if f["name"]=="Roti, whole wheat (cooked)")
    client.post("/api/meals", json={"meal":"lunch","food_id":roti["id"],"quantity":1,"unit":"serving"})
    insights = client.get("/api/insights").get_json()
    for ins in insights["insights"]:
        for rec in ins.get("recommendations", []):
            # none should be dairy
            assert rec["name"] not in {"Paneer (plain, whole milk)","Curd / dahi (plain, whole milk)","Milk, whole","Ghee","Cheese, cheddar","Butter, salted"}, f"milk allergen recommended {rec['name']}"

def test_allergen_ambiguous_excluded(client):
    """If allergen cannot be ruled out, food excluded (conservative)."""
    FULL = {"age":25,"sex":"female","height_cm":165,"weight_kg":60,"activity":"moderate"}
    new_user(client, **FULL)
    client.put("/api/profile", json={"allergies":["sesame"]})
    # Sesame seeds should be excluded
    roti = client.get("/api/foods?q=Roti, whole wheat&limit=50").get_json()["foods"]
    roti = next(f for f in roti if f["name"]=="Roti, whole wheat (cooked)")
    client.post("/api/meals", json={"meal":"lunch","food_id":roti["id"],"quantity":1,"unit":"serving"})
    insights = client.get("/api/insights").get_json()
    for ins in insights["insights"]:
        for rec in ins.get("recommendations", []):
            assert "Sesame" not in rec["name"], "sesame allergen should be excluded"

def test_dietary_classification_filtering(client):
    """lacto-vegetarian excludes meat/fish/egg, vegan further excludes dairy."""
    FULL = {"age":25,"sex":"female","height_cm":165,"weight_kg":60,"activity":"moderate"}
    new_user(client, **FULL)
    client.put("/api/profile", json={"dietary_prefs":["vegetarian"]})
    roti = client.get("/api/foods?q=Roti, whole wheat&limit=50").get_json()["foods"]
    roti = next(f for f in roti if f["name"]=="Roti, whole wheat (cooked)")
    client.post("/api/meals", json={"meal":"lunch","food_id":roti["id"],"quantity":1,"unit":"serving"})
    insights = client.get("/api/insights").get_json()
    for ins in insights["insights"]:
        for rec in ins.get("recommendations", []):
            assert "Chicken" not in rec["name"] and "Salmon" not in rec["name"] and "Egg, whole" not in rec["name"], f"non-veg recommended for vegetarian: {rec['name']}"
    # vegan should exclude paneer
    new_user(client, name="Vegan2", **FULL)
    client.put("/api/profile", json={"dietary_prefs":["vegan"]})
    client.post("/api/meals", json={"meal":"lunch","food_id":roti["id"],"quantity":1,"unit":"serving"})
    insights2 = client.get("/api/insights").get_json()
    for ins in insights2["insights"]:
        for rec in ins.get("recommendations", []):
            assert rec["name"] not in {"Paneer (plain, whole milk)","Milk, whole","Egg, whole (boiled)"}

def test_food_recommendations_from_dataset_only(client):
    FULL = {"age":25,"sex":"female","height_cm":165,"weight_kg":60,"activity":"moderate"}
    new_user(client, **FULL)
    roti = client.get("/api/foods?q=Roti, whole wheat&limit=50").get_json()["foods"]
    roti = next(f for f in roti if f["name"]=="Roti, whole wheat (cooked)")
    client.post("/api/meals", json={"meal":"lunch","food_id":roti["id"],"quantity":1,"unit":"serving"})
    insights = client.get("/api/insights").get_json()
    dataset_names = {f["name"] for f in client.get("/api/foods?limit=250").get_json()["foods"]}
    for ins in insights["insights"]:
        for rec in ins.get("recommendations", []):
            assert rec["name"] in dataset_names

def test_existing_food_search_still_works(client):
    assert client.get("/api/foods?q=roti").status_code == 200
    assert len(client.get("/api/foods?q=roti").get_json()["foods"]) >= 1
    assert client.get("/api/foods?q=dal").get_json()["foods"]
    assert client.get("/api/foods?limit=250").get_json()["foods"]
    # total count should be ~196
    all_foods = client.get("/api/foods?limit=250").get_json()["foods"]
    assert len(all_foods) >= 190

def test_existing_meal_logging_with_new_dataset(client):
    new_user(client, "Logger")
    # old food id 1 should still work
    r = client.post("/api/meals", json={"meal":"lunch","food_id":1,"quantity":1,"unit":"serving"})
    assert r.status_code == 201
    assert r.get_json()["entry"]["display_name"] == "Roti, whole wheat (cooked)"
    # new food id 43 should also work
    r2 = client.post("/api/meals", json={"meal":"dinner","food_id":43,"quantity":1,"unit":"serving"})
    assert r2.status_code == 201

def test_no_duplicate_names_in_db(client):
    foods = client.get("/api/foods?limit=250").get_json()["foods"]
    names = [f["name"] for f in foods]
    assert len(names) == len(set(names))

def test_preparation_states_covered(dataset):
    foods,_ = dataset
    states = set(f["state"] for f in foods)
    assert "raw" in states and "cooked" in states and "dry" in states

def test_sources_recorded(dataset):
    foods,_ = dataset
    for f in foods:
        assert f["source"] and f["source_id"]
        assert f["quality"] in {"verified","approximate","illustrative"}

def test_ambiguous_not_assumed_safe():
    """Ghee is dairy-derived (Oils & Fats but contains milk fat) — must be filtered for milk allergy."""
    from nutricare.insights import food_matches_allergy, is_excluded
    assert food_matches_allergy("Ghee", ["milk"], "Oils & Fats") is True
    mock = {"name":"Test Cheese","grp":"Dairy & Alternatives","allergens":'["milk"]',"dietary":'{"vegan":false,"lacto_vegetarian":true,"ovo_vegetarian":false,"lacto_ovo_vegetarian":true,"non_vegetarian":false}'}
    assert is_excluded(mock, ["milk"], []) is True
    # Missing metadata (None) should not be assumed safe — fallback grp check still protects dairy
    assert food_matches_allergy("Paneer mystery", ["milk"], "Dairy & Alternatives") is True
