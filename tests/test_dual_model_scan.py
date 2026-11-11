"""Dual-model Scan a Meal: both checkpoints analyse the same image.

The decision logic is exercised with scripted predictor doubles so every
rule (agreement, alias-canonical agreement, cross-model support,
single-model confidence, unresolved disagreement, per-model fallback) is
tested deterministically. The doubles only stand in for the two Predictor
objects at the ``vision.get_predictor`` seam — no model behaviour is
simulated beyond returning ranked predictions, and the API tests run the
real nutrition pipeline. The strategy never compares raw softmax scores
across models, and several tests exist specifically to prove that.
"""
import struct
import zlib

import pytest

from nutricare import create_app, vision


def make_png(width=64, height=64, colour=(180, 120, 60)):
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + bytes(colour) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def make_result(*slug_conf, threshold=vision.LOW_CONFIDENCE_THRESHOLD):
    """A Predictor.predict-shaped result from (slug, confidence) pairs."""
    labels = vision.class_by_slug()
    predictions = [{
        "slug": slug,
        "label": (labels.get(slug) or {}).get("label", slug),
        "group": (labels.get(slug) or {}).get("group", "unknown"),
        "confidence": conf,
        "confidence_pct": round(conf * 100, 1),
    } for slug, conf in slug_conf]
    return {
        "predictions": predictions,
        "top": predictions[0],
        "low_confidence": predictions[0]["confidence"] < threshold,
        "threshold": threshold,
        "image": {"format": "png", "width": 64, "height": 64},
        "single_label": True,
        "note": vision.SINGLE_LABEL_NOTE,
    }


class FakePredictor:
    """Records the exact image bytes it was asked to analyse."""

    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error
        self.calls = []

    def predict(self, image_bytes, top_k=3):
        self.calls.append(image_bytes)
        if self._error is not None:
            raise self._error
        import copy
        return copy.deepcopy(self._result)

    def status(self):
        return {"model_present": self._error is None, "loaded": True}

    # food_recognition.trained_slugs probes this; reporting "no checkpoint
    # path" keeps /classes honest (taxonomy shown, nothing marked trained).
    available_path = False
    _classes = []


@pytest.fixture()
def dual(monkeypatch):
    """Install scripted predictors for both models; returns the registry."""
    fakes = {}

    def install(name, result=None, error=None):
        fakes[name] = FakePredictor(result=result, error=error)

    def fake_get_predictor(name="default"):
        return fakes[name]

    monkeypatch.setattr(vision, "get_predictor", fake_get_predictor)
    return install


def run_dual(dual, default=None, experimental=None,
             default_error=None, experimental_error=None, image=None):
    dual("default", result=default, error=default_error)
    dual("experimental", result=experimental, error=experimental_error)
    return vision.predict_both_models(image or make_png(), top_k=3)


# ------------------------------------------------------------ canonical keys
def test_canonical_key_merges_only_alias_equivalent_dishes():
    assert vision.canonical_food_key("chole") == \
        vision.canonical_food_key("chana_masala")
    assert vision.canonical_food_key("chomchom") == \
        vision.canonical_food_key("cham_cham")
    assert vision.canonical_food_key("chapati") == \
        vision.canonical_food_key("roti")
    # Generic vs specific dish: related, NOT interchangeable labels.
    assert vision.canonical_food_key("chicken_biryani") != \
        vision.canonical_food_key("biryani")
    # Same dataset nutrition entry via approximation is NOT the same dish:
    assert vision.canonical_food_key("kheer") != \
        vision.canonical_food_key("phirni")
    assert vision.canonical_food_key("jalebi") == "jalebi"
    assert vision.canonical_food_key("not_a_slug") == "not_a_slug"


def test_biryani_pair_is_not_treated_as_agreement(dual):
    """12-class chicken_biryani vs 80-class biryani must not be reported as
    the models agreeing on one food, and the candidates stay separate."""
    result = run_dual(
        dual,
        default=make_result(("chicken_biryani", 0.85), ("jalebi", 0.05)),
        experimental=make_result(("biryani", 0.80), ("gulab_jamun", 0.05)))
    ens = result["ensemble"]
    assert ens["agreement"] is False
    assert ens["rule"] == "disagreement_unresolved"
    assert ens["needs_user_confirmation"] is True
    keys = [p["canonical_key"] for p in result["predictions"]]
    assert "biryani" in keys and "chicken_biryani" in keys


def test_mutual_cross_support_is_unresolved_not_experimental_win(dual):
    """Each top-1 in the other's list: symmetric evidence. The old logic
    handed the win to the experimental model (0.41 over 0.95); it must now
    ask the user, with the production top-1 kept provisional."""
    result = run_dual(
        dual,
        default=make_result(("jalebi", 0.95), ("gulab_jamun", 0.03)),
        experimental=make_result(("gulab_jamun", 0.41), ("jalebi", 0.30)))
    ens = result["ensemble"]
    assert ens["rule"] == "disagreement_unresolved"
    assert ens["uncertain"] is True
    assert ens["needs_user_confirmation"] is True
    assert ens["selected_model"] == "default"
    assert result["top"]["slug"] == "jalebi"
    assert result["low_confidence"] is True


# ------------------------------------------------------------- both run
def test_both_models_receive_the_same_image(dual):
    image = make_png()
    result = run_dual(
        dual,
        default=make_result(("jalebi", 0.9)),
        experimental=make_result(("jalebi", 0.8)),
        image=image)
    assert result["ensemble"]["models"]["default"]["available"] is True
    assert result["ensemble"]["models"]["experimental"]["available"] is True


def test_both_models_called_with_identical_bytes(dual):
    image = make_png(colour=(10, 20, 30))
    run_dual(
        dual,
        default=make_result(("jalebi", 0.9)),
        experimental=make_result(("jalebi", 0.8)),
        image=image)
    default_fake = vision.get_predictor("default")
    experimental_fake = vision.get_predictor("experimental")
    assert default_fake.calls == [image]
    assert experimental_fake.calls == [image]
    assert default_fake.calls[0] is image
    assert experimental_fake.calls[0] is image


# ------------------------------------------------------------- agreement
def test_agreement_same_slug_accepted_and_deduplicated(dual):
    result = run_dual(
        dual,
        default=make_result(("jalebi", 0.9), ("rasgulla", 0.05)),
        experimental=make_result(("jalebi", 0.7), ("gulab_jamun", 0.2)))
    ens = result["ensemble"]
    assert ens["agreement"] is True and ens["rule"] == "agreement"
    assert ens["uncertain"] is False and result["low_confidence"] is False
    assert result["top"]["slug"] == "jalebi"
    slugs = [p["slug"] for p in result["predictions"]]
    assert slugs.count("jalebi") == 1          # no duplicate candidate
    assert result["top"]["source_models"] == ["default", "experimental"]


def test_agreement_across_different_class_names(dual):
    """12-class 'chole' and 80-class 'chana_masala' are the same food."""
    result = run_dual(
        dual,
        default=make_result(("chole", 0.85)),
        experimental=make_result(("chana_masala", 0.75)))
    ens = result["ensemble"]
    assert ens["agreement"] is True and ens["rule"] == "agreement"
    keys = [p["canonical_key"] for p in result["predictions"]]
    assert len(keys) == len(set(keys)) == 1     # one canonical candidate


def test_agreement_but_both_uncertain_still_needs_confirmation(dual):
    result = run_dual(
        dual,
        default=make_result(("jalebi", 0.20)),
        experimental=make_result(("jalebi", 0.25)))
    assert result["ensemble"]["rule"] == "agreement_low_confidence"
    assert result["ensemble"]["needs_user_confirmation"] is True
    assert result["low_confidence"] is True


# ---------------------------------------------------------- disagreement
def test_raw_confidences_are_never_compared_across_models(dual):
    """Experimental 0.99 vs production 0.85, no shared candidates: a naive
    max-confidence ensemble would pick the experimental answer. The
    conservative strategy must refuse and ask the user instead."""
    result = run_dual(
        dual,
        default=make_result(("jalebi", 0.85), ("rasgulla", 0.05)),
        experimental=make_result(("gulab_jamun", 0.99), ("ras_malai", 0.005)))
    ens = result["ensemble"]
    assert ens["rule"] == "disagreement_unresolved"
    assert ens["uncertain"] is True and ens["needs_user_confirmation"] is True
    assert ens["selected_model"] == "default"   # provisional, not the 0.99
    assert result["low_confidence"] is True
    # Both disagreeing foods are offered for confirmation, selected first.
    assert [p["slug"] for p in result["predictions"]][:2] == \
        ["jalebi", "gulab_jamun"]


def test_cross_model_support_selects_supported_prediction(dual):
    result = run_dual(
        dual,
        default=make_result(("jalebi", 0.8), ("rasgulla", 0.1)),
        experimental=make_result(("gulab_jamun", 0.7), ("jalebi", 0.2)))
    ens = result["ensemble"]
    assert ens["rule"] == "cross_model_support"
    assert ens["selected_slug"] == "jalebi"
    assert ens["selected_model"] == "default"
    assert result["top"]["slug"] == "jalebi"


def test_single_model_confident_breaks_disagreement(dual):
    """Only judged against each model's OWN threshold, never head-to-head."""
    result = run_dual(
        dual,
        default=make_result(("jalebi", 0.30), ("rasgulla", 0.2)),
        experimental=make_result(("gulab_jamun", 0.9), ("ras_malai", 0.05)))
    ens = result["ensemble"]
    assert ens["rule"] == "single_model_confident"
    assert ens["selected_slug"] == "gulab_jamun"
    assert ens["selected_model"] == "experimental"
    assert result["low_confidence"] is False


def test_both_low_confidence_disagreement_is_uncertain(dual):
    result = run_dual(
        dual,
        default=make_result(("jalebi", 0.2)),
        experimental=make_result(("gulab_jamun", 0.3)))
    assert result["ensemble"]["rule"] == "disagreement_unresolved"
    assert result["low_confidence"] is True
    assert result["ensemble"]["needs_user_confirmation"] is True


# -------------------------------------------------------------- fallback
def test_experimental_unavailable_uses_production_model(dual):
    result = run_dual(
        dual,
        default=make_result(("jalebi", 0.9)),
        experimental_error=vision.ModelUnavailable("no checkpoint"))
    ens = result["ensemble"]
    assert ens["rule"] == "single_model_fallback"
    assert ens["unavailable_models"] == ["experimental"]
    assert ens["models"]["experimental"]["available"] is False
    assert "no checkpoint" in ens["models"]["experimental"]["error"]
    assert result["top"]["slug"] == "jalebi"
    assert result["low_confidence"] is False


def test_default_unavailable_uses_experimental_model(dual):
    result = run_dual(
        dual,
        default_error=vision.ModelUnavailable("corrupt checkpoint"),
        experimental=make_result(("gulab_jamun", 0.9)))
    ens = result["ensemble"]
    assert ens["rule"] == "single_model_fallback"
    assert ens["unavailable_models"] == ["default"]
    assert result["top"]["slug"] == "gulab_jamun"


def test_single_model_fallback_preserves_its_low_confidence(dual):
    result = run_dual(
        dual,
        default_error=vision.ModelUnavailable("missing"),
        experimental=make_result(("gulab_jamun", 0.2)))
    assert result["low_confidence"] is True
    assert result["ensemble"]["needs_user_confirmation"] is True


def test_both_models_unavailable_raises(dual):
    with pytest.raises(vision.ModelUnavailable):
        run_dual(
            dual,
            default_error=vision.ModelUnavailable("missing default"),
            experimental_error=vision.ModelUnavailable("missing experimental"))


def test_scanner_ui_wires_agreement_and_disagreement_indicators():
    """The result template must actually render the ensemble indicators
    (a regression test: the flags were once computed but never displayed)."""
    from pathlib import Path
    js = Path("static/js/views_scanner.js").read_text(encoding="utf-8")
    result_view = js[js.index("function scanShowResult"):]
    assert "confirmed by both models" in result_view
    assert "recognition models disagree" in result_view
    assert "ensemble.agreement" in result_view


# ------------------------------------------------------------- API level
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "dual.db"))
    app = create_app({"TESTING": True})
    with app.test_client() as test_client:
        assert test_client.post(
            "/api/users", json={"name": "Dual Tester"}).status_code == 201
        yield test_client


def test_api_scan_runs_both_and_attaches_single_nutrition(client, dual):
    dual("default", result=make_result(("chole", 0.85), ("jalebi", 0.05)))
    dual("experimental",
         result=make_result(("chana_masala", 0.75), ("gulab_jamun", 0.1)))
    resp = client.post("/api/vision/predict?top_k=3", data=make_png(),
                       content_type="application/octet-stream")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["model"] == "dual"
    assert body["ensemble"]["agreement"] is True
    # One canonical candidate for the agreed food — no duplicate nutrition.
    agreed = [c for c in body["candidates"]
              if c["canonical_key"] == body["top"]["canonical_key"]]
    assert len(agreed) == 1
    nutrition = agreed[0]["nutrition"]
    assert nutrition["nutrition_available"] is True
    assert nutrition["food"]["name"] == "Chole / chana masala (prepared)"
    assert nutrition["nutrients"]["kcal"] > 0
    # Debug evidence retained in the payload.
    ens = body["ensemble"]
    assert ens["models"]["default"]["top"]["slug"] == "chole"
    assert ens["models"]["experimental"]["top"]["slug"] == "chana_masala"
    assert ens["confidence_scores_comparable"] is False


def test_api_scan_with_only_experimental_available(client, dual):
    dual("default", error=vision.ModelUnavailable("default missing"))
    dual("experimental", result=make_result(("gulab_jamun", 0.9)))
    resp = client.post("/api/vision/predict", data=make_png(),
                       content_type="application/octet-stream")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["top"]["slug"] == "gulab_jamun"
    assert body["ensemble"]["unavailable_models"] == ["default"]
    assert body["candidates"][0]["nutrition"]["slug"] == "gulab_jamun"


def test_api_scan_both_unavailable_is_503_never_fabricated(client, dual):
    dual("default", error=vision.ModelUnavailable("d"))
    dual("experimental", error=vision.ModelUnavailable("e"))
    resp = client.post("/api/vision/predict", data=make_png(),
                       content_type="application/octet-stream")
    assert resp.status_code == 503
    body = resp.get_json()
    assert body["model_unavailable"] is True
    assert "predictions" not in body


def test_api_scan_ignores_legacy_model_parameter(client, dual):
    """No manual model selection: ?model=experimental must not stop the
    production model from being evaluated too."""
    dual("default", result=make_result(("jalebi", 0.9)))
    dual("experimental", result=make_result(("jalebi", 0.8)))
    resp = client.post("/api/vision/predict?model=experimental",
                       data=make_png(), content_type="application/octet-stream")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["model"] == "dual"
    assert body["ensemble"]["models"]["default"]["available"] is True


def test_existing_scanner_flow_still_intact(client, dual):
    """Status, classes, portion estimate and meal logging are unchanged."""
    dual("default", result=make_result(("jalebi", 0.9)))
    dual("experimental", result=make_result(("jalebi", 0.85)))
    assert client.get("/api/vision/status").status_code == 200
    classes = client.get("/api/vision/classes").get_json()
    assert classes["count"] > 0

    body = client.post("/api/vision/predict", data=make_png(),
                       content_type="application/octet-stream").get_json()
    slug = body["top"]["slug"]
    est = client.post("/api/vision/estimate",
                      json={"slug": slug, "grams": 100}).get_json()
    assert est["slug"] == slug and est["nutrition_available"] is True

    logged = client.post("/api/vision/log", json={
        "slug": slug, "grams": 100, "meal": "lunch"})
    assert logged.status_code == 201
    assert logged.get_json()["entry"]["quantity"] == 100.0
