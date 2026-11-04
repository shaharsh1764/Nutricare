"""Vegetarian filtering regression tests — targeted bug fix validation.

Food search, meal logging, and Smart Nutrition Insights must consistently enforce
vegetarian preference using explicit dietary metadata (data/foods.json dietary booleans),
not name substrings. Historical meals preserved.
"""
import pytest
from nutricare import create_app

FULL = {"age": 25, "sex": "female", "height_cm": 165, "weight_kg": 60, "activity": "moderate"}

@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "test.db"))
    return create_app({"TESTING": True})

@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c

def new_user(client, name="Veg Tester", **prof):
    r = client.post("/api/users", json={"name": name})
    assert r.status_code == 201
    if prof:
        r = client.put("/api/profile", json=prof)
        assert r.status_code == 200
    return r

def veg_client(client):
    new_user(client, **FULL)
    r = client.put("/api/profile", json={**FULL, "dietary_prefs": ["vegetarian"]})
    assert r.status_code == 200
    return client

# 1. Vegetarian cannot find chicken biryani
def test_vegetarian_cannot_find_chicken_biryani(client):
    veg_client(client)
    foods = client.get("/api/foods?q=chicken biryani&limit=50").get_json()["foods"]
    assert len(foods) == 0, f"chicken biryani leaked: {foods}"
    # broader chicken query also empty
    foods = client.get("/api/foods?q=chicken&limit=50").get_json()["foods"]
    assert all("chicken" not in f["name"].lower() for f in foods)

# 2. Vegetarian cannot add via API (bypass frontend)
def test_vegetarian_cannot_add_chicken_biryani_via_api(client):
    veg_client(client)
    cb_id = 22  # stable ID for Chicken biryani (data/foods.json)
    resp = client.post("/api/meals", json={"meal":"lunch","food_id":cb_id,"quantity":1,"unit":"serving"})
    assert resp.status_code == 400
    assert "incompatible" in resp.get_json()["error"].lower()
    assert "preserved" in resp.get_json()["error"].lower() or "historical" in resp.get_json()["error"].lower()

# 3. Chicken, mutton, fish excluded
def test_vegetarian_excludes_meat_fish(client):
    veg_client(client)
    for q in ["chicken", "mutton", "fish", "salmon", "prawn", "crab", "tuna", "rohu"]:
        foods = client.get(f"/api/foods?q={q}&limit=50").get_json()["foods"]
        bad = [f["name"] for f in foods if f["dietary"] and '"non_vegetarian": true' in f["dietary"]]
        # Also check via insights logic: any returned should be vegetarian
        assert not bad, f"non-veg leaked for {q}: {bad}"
        # Direct name check
        assert all("chicken" not in n.lower() and "mutton" not in n.lower() for n in [f["name"] for f in foods])

# 4. Vegetarian foods remain searchable and addable
def test_vegetarian_foods_remain(client):
    veg_client(client)
    for q, expected in [("dal", "Dal"), ("roti", "Roti"), ("rice", "Rice"), ("spinach", "Spinach")]:
        foods = client.get(f"/api/foods?q={q}").get_json()["foods"]
        assert len(foods) > 0, f"{q} should still be available"
        # add one
        f = next((x for x in foods if expected.lower() in x["name"].lower()), foods[0])
        r = client.post("/api/meals", json={"meal":"lunch","food_id":f["id"],"quantity":1,"unit":"serving"})
        assert r.status_code == 201, f"vegetarian food {f['name']} should be addable"

# 5. Insights excludes incompatible foods
def test_insights_excludes_incompatible(client):
    veg_client(client)
    roti = client.get("/api/foods?q=Roti, whole wheat&limit=50").get_json()["foods"]
    roti = next(f for f in roti if f["name"]=="Roti, whole wheat (cooked)")
    client.post("/api/meals", json={"meal":"lunch","food_id":roti["id"],"quantity":1,"unit":"serving"})
    insights = client.get("/api/insights").get_json()
    for ins in insights["insights"]:
        for rec in ins.get("recommendations", []):
            assert "Chicken" not in rec["name"] and "Mutton" not in rec["name"] and "Fish" not in rec["name"] and rec["name"] not in {"Salmon (baked)", "Chicken biryani"}

# 6. Changing preference immediately applies filtering
def test_changing_preference_immediately_filters(client):
    new_user(client, **FULL)
    # before vegetarian, chicken present
    foods_before = client.get("/api/foods?q=chicken biryani").get_json()["foods"]
    assert len(foods_before)==1
    client.put("/api/profile", json={**FULL, "dietary_prefs":["vegetarian"]})
    foods_after = client.get("/api/foods?q=chicken biryani").get_json()["foods"]
    assert len(foods_after)==0
    # revert to no restriction
    client.put("/api/profile", json={**FULL, "dietary_prefs":[]})
    foods_revert = client.get("/api/foods?q=chicken biryani").get_json()["foods"]
    assert len(foods_revert)==1

# 7. Historical chicken biryani remains intact
def test_historical_chicken_biryani_preserved(client):
    new_user(client, **FULL)
    cb = client.get("/api/foods?q=chicken biryani").get_json()["foods"][0]
    r = client.post("/api/meals", json={"meal":"lunch","food_id":cb["id"],"quantity":1,"unit":"serving"})
    assert r.status_code == 201
    # switch to vegetarian
    client.put("/api/profile", json={**FULL, "dietary_prefs":["vegetarian"]})
    # historical still there
    meals = client.get("/api/meals").get_json()
    assert meals["logged_count"]==1
    assert meals["meals"]["lunch"][0]["display_name"]=="Chicken biryani"
    # nutrition unchanged
    assert meals["meals"]["lunch"][0]["nutrients"]["kcal"] == 306.0
    # new incompatible rejected
    r2 = client.post("/api/meals", json={"meal":"dinner","food_id":cb["id"],"quantity":1,"unit":"serving"})
    assert r2.status_code == 400

# 8. Users without restrictions retain existing behaviour
def test_no_restriction_retains_behaviour(client):
    new_user(client, **FULL)
    # dietary_prefs empty => all foods visible
    foods = client.get("/api/foods?q=chicken biryani").get_json()["foods"]
    assert len(foods)==1
    cb = foods[0]
    r = client.post("/api/meals", json={"meal":"lunch","food_id":cb["id"],"quantity":1,"unit":"serving"})
    assert r.status_code == 201
    # search for vegetarian foods still works
    assert client.get("/api/foods?q=dal").get_json()["foods"]

# 9. Existing allergy filtering still works
def test_allergy_filtering_still_works(client):
    new_user(client, **FULL)
    client.put("/api/profile", json={**FULL, "allergies":["milk"], "dietary_prefs":["vegetarian"]})
    # paneer (milk) should be filtered even though vegetarian would allow dairy
    paneer = client.get("/api/foods?q=paneer").get_json()["foods"]
    assert len(paneer)==0, f"milk allergy should hide paneer: {paneer}"
    # milk itself filtered
    milk = client.get("/api/foods?q=Milk, whole").get_json()["foods"]
    assert len(milk)==0
    # non-dairy veg still available
    dal = client.get("/api/foods?q=dal").get_json()["foods"]
    assert len(dal)>0

# 10. Other dietary preferences retain behaviour
def test_other_dietary_preferences_retain(client):
    new_user(client, **FULL)
    # vegan should exclude dairy+egg
    client.put("/api/profile", json={**FULL, "dietary_prefs":["vegan"]})
    assert len(client.get("/api/foods?q=paneer").get_json()["foods"])==0
    assert len(client.get("/api/foods?q=Egg, whole").get_json()["foods"])==0
    assert len(client.get("/api/foods?q=Chicken biryani").get_json()["foods"])==0
    # dal should remain for vegan
    assert len(client.get("/api/foods?q=dal").get_json()["foods"])>0
    # lacto-ovo should allow egg+dairy but not meat
    client.put("/api/profile", json={**FULL, "dietary_prefs":["lacto-ovo vegetarian"]})
    # egg allowed? our logic treats lacto-ovo as includes egg+dairy, excludes meat
    egg = client.get("/api/foods?q=Egg, whole (boiled)").get_json()["foods"]
    # lacto-ovo vegetarian should allow egg per our dietary flags (lacto_ovo true for egg)
    # Egg's dietary lacto_ovo true, so should be present
    assert len(egg)==1, f"egg should be allowed for lacto-ovo: {egg}"
    # chicken still blocked
    assert len(client.get("/api/foods?q=chicken biryani").get_json()["foods"])==0
