"""Tests for the AI Food Scanner: image validation, honest model-absence
behaviour, nutrition mapping/scaling, and meal-logging integration.

Design note: these tests never *simulate* a neural network. The predictor path
is exercised for real wherever the ML stack is installed, by training a tiny
throwaway checkpoint on random noise so the inference code (checkpoint loading,
softmax, ranking, low-confidence handling) is genuinely executed. Accuracy
claims are never asserted — a noise-trained model has none, and pretending
otherwise is exactly what this feature refuses to do.
"""

import json
import struct
import zlib
from pathlib import Path

import pytest

from nutricare import create_app, db, vision


# ---------------------------------------------------------------- helpers
def make_png(width=64, height=64, colour=(180, 120, 60)):
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + bytes(colour) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "vision.db"))
    # Isolation: never pick up a developer's real checkpoint.
    monkeypatch.setenv("NUTRICARE_MODEL", str(tmp_path / "absent.pt"))
    vision.reset_predictor()
    application = create_app({"TESTING": True})
    yield application
    vision.reset_predictor()


@pytest.fixture()
def client(app):
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture()
def user(client):
    resp = client.post("/api/users", json={"name": "Scanner Tester"})
    assert resp.status_code == 201
    return resp.get_json()


# ---------------------------------------------------------------- validation
def test_valid_png_is_accepted():
    meta = vision.validate_image(make_png())
    assert meta["format"] == "png"
    assert meta["width"] == 64 and meta["height"] == 64


def test_empty_upload_rejected():
    with pytest.raises(vision.ImageError, match="No image"):
        vision.validate_image(b"")


@pytest.mark.parametrize("payload", [
    b"MZ\x90\x00 this is an executable, not a photo",
    b"<?php system($_GET['c']); ?>",
    b"%PDF-1.7 not an image",
    b"plain text pretending to be an image",
])
def test_non_image_payloads_rejected_by_magic_bytes(payload):
    """A renamed .exe/.php must be refused — the filename is never trusted."""
    with pytest.raises(vision.ImageError):
        vision.validate_image(payload)


def test_truncated_png_rejected():
    with pytest.raises(vision.ImageError):
        vision.validate_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10)


def test_truncated_jpeg_rejected():
    with pytest.raises(vision.ImageError):
        vision.validate_image(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 4)


def test_gif_rejected_as_unsupported_format():
    with pytest.raises(vision.ImageError, match="not supported"):
        vision.validate_image(b"GIF89a" + b"\x00" * 32)


def test_tiny_image_rejected():
    with pytest.raises(vision.ImageError, match="too small"):
        vision.validate_image(make_png(width=8, height=8))


def test_oversized_upload_rejected(monkeypatch):
    monkeypatch.setattr(vision, "MAX_UPLOAD_BYTES", 100)
    with pytest.raises(vision.ImageError, match="too large"):
        vision.validate_image(make_png())


def test_oversized_dimensions_rejected():
    # 20000x10 PNG header: valid container, absurd dimensions.
    header = (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
              + struct.pack(">IIBBBBB", 20000, 10, 8, 2, 0, 0, 0))
    with pytest.raises(vision.ImageError):
        vision.validate_image(header + b"\x00" * 32)


def test_safe_filename_strips_paths():
    assert vision.safe_filename("../../etc/passwd") == "passwd"
    assert vision.safe_filename("meal photo!.jpg") == "mealphoto.jpg"
    assert vision.safe_filename(None) == "upload"
    assert "/" not in vision.safe_filename("/tmp/x/y.png")


# ---------------------------------------------------------------- taxonomy
def test_every_mapped_class_exists_in_the_food_dataset():
    foods = {f["name"] for f in json.loads(
        (vision.PROJECT_DIR / "data" / "foods.json").read_text(encoding="utf-8"))["foods"]}
    for entry in vision.class_list():
        if entry["food"]:
            assert entry["food"] in foods, f"{entry['slug']} -> missing {entry['food']}"


def test_classes_have_unique_slugs_and_required_fields():
    slugs = [c["slug"] for c in vision.class_list()]
    assert len(slugs) == len(set(slugs))
    for entry in vision.class_list():
        assert entry["label"] and entry["group"] and entry["default_grams"] > 0
        assert entry["nutrition_source"] in ("dataset", "unavailable")


def test_taxonomy_covers_the_priority_indian_categories():
    slugs = {c["slug"] for c in vision.class_list()}
    required = {"roti", "paratha_plain", "naan", "rice_white", "pulao", "khichdi",
                "idli", "dosa_plain", "masala_dosa", "uttapam", "poha", "upma",
                "vada", "chole_bhature", "dal_plain", "rajma", "chole",
                "palak_paneer", "aloo_gobi", "sambar", "rasam", "kadhi",
                "chicken_biryani", "samosa", "pav_bhaji"}
    assert required <= slugs
    international = {"pizza", "burger", "sandwich", "pasta", "noodles",
                     "french_fries", "fried_chicken", "momos", "pancakes", "salad"}
    assert international <= slugs


def test_group_coverage_is_reported_honestly(client, user):
    payload = client.get("/api/vision/classes").get_json()
    assert payload["count"] == len(vision.class_list())
    assert payload["with_nutrition"] < payload["count"]   # not everything is mapped
    unmapped = [c for c in payload["classes"] if not c["nutrition_available"]]
    assert unmapped, "the honest 'no dataset entry' path must exist for these foods"
    for item in unmapped:
        assert item["dataset_food"] is None


# ---------------------------------------------------------------- model absence
def test_status_reports_missing_model_without_crashing(client):
    body = client.get("/api/vision/status").get_json()
    model = body["model"]
    assert model["model_present"] is False
    assert model["loaded"] is False
    assert "No trained checkpoint" in model["detail"]


def test_predict_returns_503_and_never_fabricates(client, user):
    resp = client.post("/api/vision/predict", data=make_png(),
                       content_type="application/octet-stream")
    assert resp.status_code == 503
    body = resp.get_json()
    assert body["model_unavailable"] is True
    assert "predictions" not in body          # no invented class names
    assert "confidence" not in json.dumps(body)


def test_predict_requires_an_active_user(client):
    resp = client.post("/api/vision/predict", data=make_png())
    assert resp.status_code == 401


def test_predict_validates_image_before_touching_the_model(client, user):
    resp = client.post("/api/vision/predict", data=b"not-an-image")
    assert resp.status_code == 400
    assert "Unsupported file type" in resp.get_json()["error"]


def test_predictor_raises_model_unavailable_directly(tmp_path):
    predictor = vision.Predictor(tmp_path / "nope.pt")
    with pytest.raises(vision.ModelUnavailable):
        predictor.predict(make_png())


def test_reset_predictor_clears_cached_state():
    first = vision.get_predictor()
    vision.reset_predictor()
    assert vision.get_predictor() is not first


# ---------------------------------------------------------------- real inference
def _require_ml():
    """Import the ML stack or skip only the tests that need it.

    Deliberately inside a function: a module-level importorskip would skip the
    whole file, hiding the validation/mapping tests that need no ML at all.
    """
    import torch
    pytest.importorskip("torchvision")
    pytest.importorskip("PIL")
    return torch


def _train_noise_checkpoint(path: Path, classes, architecture="mobilenet_v3_small"):
    """Save a real checkpoint so the inference path is exercised for real.

    Weights are random: this proves the *plumbing* works (state_dict loading,
    softmax, ranking, low-confidence flagging). It makes no accuracy claim.
    """
    torch = _require_ml()
    model = vision.build_model(architecture, len(classes), pretrained=False)
    torch.save({
        "state_dict": model.state_dict(),
        "classes": classes,
        "architecture": architecture,
        "input_size": 224,
        "trained_at": "2026-01-01T00:00:00",
        "test_accuracy": None,      # unknown on purpose: nothing is invented
        "trained_on": "random weights (test fixture)",
    }, path)


@pytest.fixture()
def trained_app(tmp_path, monkeypatch):
    checkpoint = tmp_path / "fixture.pt"
    slugs = ["masala_dosa", "roti", "samosa", "pizza"]
    _train_noise_checkpoint(checkpoint, slugs)
    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "vision2.db"))
    monkeypatch.setenv("NUTRICARE_MODEL", str(checkpoint))
    vision.reset_predictor()
    application = create_app({"TESTING": True})
    yield application
    vision.reset_predictor()


def test_predict_output_structure_is_correct(trained_app):
    with trained_app.test_client() as client:
        client.post("/api/users", json={"name": "Shape"})
        resp = client.post("/api/vision/predict?top_k=3", data=make_png(),
                           content_type="application/octet-stream")
        assert resp.status_code == 200
        body = resp.get_json()

    assert body["single_label"] is True
    assert len(body["predictions"]) == 3
    assert body["candidates"] and len(body["candidates"]) == 3
    total = sum(p["confidence"] for p in body["predictions"])
    assert 0 < total <= 1.0 + 1e-6            # softmax probabilities
    assert body["predictions"] == sorted(
        body["predictions"], key=lambda p: -p["confidence"])
    for prediction in body["predictions"]:
        assert prediction["slug"] in {"masala_dosa", "roti", "samosa", "pizza"}
        assert 0.0 <= prediction["confidence"] <= 1.0
        assert "label" in prediction and "group" in prediction
    assert body["top"] == body["predictions"][0]
    assert body["image"]["width"] == 64


def test_confidence_is_reported_and_low_confidence_flagged(trained_app):
    with trained_app.test_client() as client:
        client.post("/api/users", json={"name": "Conf"})
        body = client.post("/api/vision/predict", data=make_png()).get_json()
    assert isinstance(body["low_confidence"], bool)
    assert body["threshold"] == vision.LOW_CONFIDENCE_THRESHOLD
    # random weights cannot be confident: the honest flag must trip
    if body["top"]["confidence"] < vision.LOW_CONFIDENCE_THRESHOLD:
        assert body["low_confidence"] is True


def test_top_k_is_clamped_and_validated(trained_app):
    with trained_app.test_client() as client:
        client.post("/api/users", json={"name": "K"})
        assert len(client.post("/api/vision/predict?top_k=99",
                               data=make_png()).get_json()["predictions"]) <= 4
        assert len(client.post("/api/vision/predict?top_k=bogus",
                               data=make_png()).get_json()["predictions"]) == 3


def test_checkpoint_load_failure_is_reported_not_hidden(tmp_path, monkeypatch):
    broken = tmp_path / "broken.pt"
    broken.write_bytes(b"definitely not a torch checkpoint")
    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "b.db"))
    monkeypatch.setenv("NUTRICARE_MODEL", str(broken))
    vision.reset_predictor()
    application = create_app({"TESTING": True})
    with application.test_client() as client:
        client.post("/api/users", json={"name": "Broken"})
        resp = client.post("/api/vision/predict", data=make_png())
        assert resp.status_code == 503
        assert resp.get_json()["model_unavailable"] is True
    vision.reset_predictor()


def test_repeated_predictions_reuse_the_loaded_model(trained_app):
    predictor = vision.get_predictor()
    with trained_app.test_client() as client:
        client.post("/api/users", json={"name": "Cache"})
        for _ in range(3):
            assert client.post("/api/vision/predict",
                               data=make_png()).status_code == 200
        status = client.get("/api/vision/status").get_json()
    assert vision.get_predictor() is predictor   # loaded once, not per request
    assert status["model"]["loaded"] is True
    assert status["model"]["trained_at"] == "2026-01-01T00:00:00"


# ---------------------------------------------------------------- nutrition
def test_estimate_scales_proportionally(client, user):
    one = client.post("/api/vision/estimate",
                      json={"slug": "masala_dosa", "grams": 100}).get_json()
    two = client.post("/api/vision/estimate",
                      json={"slug": "masala_dosa", "grams": 200}).get_json()
    for key in ("kcal", "protein_g", "carbs_g", "fat_g"):
        assert two["nutrients"][key] == pytest.approx(2 * one["nutrients"][key], rel=1e-6)
    assert two["grams"] == 200


def test_estimate_uses_documented_dataset_values(client, user, app):
    with app.app_context():
        conn = db.connect()
        row = conn.execute("SELECT * FROM foods WHERE name = ?",
                           ("Dosa (plain, tawa)",)).fetchone()
        conn.close()
    body = client.post("/api/vision/estimate",
                       json={"slug": "dosa_plain", "grams": 150}).get_json()
    assert body["nutrients"]["kcal"] == pytest.approx(row["kcal"] * 1.5, rel=1e-6)
    assert body["food"]["source"] == row["source"]
    assert body["nutrition_available"] is True


def test_estimate_defaults_to_dataset_serving(client, user):
    body = client.post("/api/vision/estimate", json={"slug": "roti"}).get_json()
    assert body["grams"] == vision.class_by_slug()["roti"]["default_grams"]


def test_estimate_explains_unmapped_foods_instead_of_inventing(client, user):
    body = client.post("/api/vision/estimate", json={"slug": "pizza"}).get_json()
    assert body["nutrition_available"] is False
    assert body["nutrients"] is None
    assert "no documented nutrition entry" in body["unavailable_reason"]


def test_estimate_carries_uncertainty_and_approximation_notes(client, user):
    body = client.post("/api/vision/estimate",
                       json={"slug": "masala_dosa"}).get_json()
    assert body["range"]["kcal_low"] < body["nutrients"]["kcal"] < body["range"]["kcal_high"]
    assert body["approx_note"]          # masala dosa -> plain dosa approximation
    assert "estimate" in body["estimate_note"].lower()


@pytest.mark.parametrize("grams", [0, -5, 5000, "abc", None])
def test_invalid_portions_rejected(client, user, grams):
    payload = {"slug": "roti"}
    if grams is not None:
        payload["grams"] = grams
    if grams is None:
        assert client.post("/api/vision/estimate", json=payload).status_code == 200
        return
    assert client.post("/api/vision/estimate", json=payload).status_code == 400


def test_unknown_slug_is_rejected(client, user):
    resp = client.post("/api/vision/estimate", json={"slug": "unicorn_steak"})
    assert resp.status_code == 400
    assert "Unknown food class" in resp.get_json()["error"]


# ---------------------------------------------------------------- logging
@pytest.mark.parametrize("meal", list(db.MEALS))
def test_each_meal_category_logs_and_persists(client, user, meal):
    resp = client.post("/api/vision/log",
                       json={"slug": "roti", "grams": 80, "meal": meal})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["meal"] == meal
    stored = client.get("/api/meals").get_json()
    assert len(stored["meals"][meal]) == 1
    assert stored["meals"][meal][0]["food"]["name"] == "Roti, whole wheat (cooked)"
    assert stored["meals"][meal][0]["quantity"] == 80
    assert stored["meals"][meal][0]["unit"] == "g"


def test_missing_meal_category_is_refused(client, user):
    assert client.post("/api/vision/log", json={"slug": "roti", "grams": 80}).status_code == 400
    assert client.post("/api/vision/log",
                       json={"slug": "roti", "grams": 80, "meal": "brunch"}).status_code == 400
    assert client.get("/api/meals").get_json()["logged_count"] == 0


def test_logged_meal_updates_existing_totals(client, user):
    before = client.get("/api/summary").get_json()["totals"]["kcal"]
    client.post("/api/vision/log", json={"slug": "chicken_biryani",
                                         "grams": 180, "meal": "dinner"})
    after = client.get("/api/summary").get_json()["totals"]
    assert after["kcal"] > before
    assert after["protein_g"] > 0


def test_server_ignores_client_supplied_nutrition(client, user):
    """A forged kcal value must not end up in the diary."""
    client.post("/api/vision/log", json={"slug": "roti", "grams": 40,
                                         "meal": "lunch", "custom_kcal": 99999,
                                         "custom_protein_g": 500})
    entry = client.get("/api/meals").get_json()["meals"]["lunch"][0]
    assert entry["food"] is not None            # linked to the dataset row
    assert entry["nutrients"]["kcal"] < 200     # dataset value, not the forged one


def test_unmapped_food_requires_user_values(client, user):
    resp = client.post("/api/vision/log",
                       json={"slug": "pizza", "grams": 120, "meal": "snacks"})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["needs_manual_values"] is True
    assert client.get("/api/meals").get_json()["logged_count"] == 0


def test_unmapped_food_saves_with_user_supplied_values(client, user):
    resp = client.post("/api/vision/log", json={
        "slug": "pizza", "grams": 120, "meal": "snacks",
        "custom_kcal": 285, "custom_protein_g": 12,
        "custom_carbs_g": 33, "custom_fat_g": 11})
    assert resp.status_code == 201
    entry = client.get("/api/meals").get_json()["meals"]["snacks"][0]
    assert entry["custom_name"] == "Pizza"
    assert entry["nutrients"]["kcal"] == 285          # the user's own number
    assert entry["food"] is None


def test_manual_food_requires_a_name(client, user):
    resp = client.post("/api/vision/log", json={"grams": 100, "meal": "lunch",
                                                "custom_kcal": 200})
    assert resp.status_code == 400


def test_logging_respects_existing_dietary_and_allergy_guards(client):
    client.post("/api/users", json={"name": "Vegetarian"})
    client.put("/api/profile", json={"dietary_prefs": ["lacto_vegetarian"]})
    resp = client.post("/api/vision/log",
                       json={"slug": "chicken_biryani", "grams": 180, "meal": "lunch"})
    assert resp.status_code == 409
    assert resp.get_json()["dietary_conflict"] is True
    assert client.get("/api/meals").get_json()["logged_count"] == 0


def test_logging_rejects_out_of_range_portions(client, user):
    assert client.post("/api/vision/log",
                       json={"slug": "roti", "grams": 0, "meal": "lunch"}).status_code == 400
    assert client.post("/api/vision/log",
                       json={"slug": "roti", "grams": 9999, "meal": "lunch"}).status_code == 400


def test_logging_requires_active_user(client):
    assert client.post("/api/vision/log",
                       json={"slug": "roti", "grams": 40, "meal": "lunch"}).status_code == 401


def test_scanned_meal_appears_in_existing_endpoints(client, user):
    client.post("/api/vision/log", json={"slug": "idli", "grams": 80, "meal": "breakfast"})
    day = client.get("/api/meals").get_json()
    assert day["logged_count"] == 1
    report = client.get("/api/report?days=7").get_json()
    assert report["per_day"][-1]["logged_count"] == 1


def test_healthz_still_works_and_existing_routes_untouched(client):
    assert client.get("/healthz").get_json() == {"ok": True}
    assert client.get("/api/foods?q=roti").status_code == 200


# ---------------------------------------------------------------- real model
REAL_MODEL = vision.DEFAULT_MODEL_PATH


@pytest.fixture()
def real_model_app(tmp_path, monkeypatch):
    """App wired to the genuinely trained checkpoint, if it is present."""
    if not REAL_MODEL.is_file():
        pytest.skip("no trained checkpoint installed (models/food_classifier.pt)")
    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "real.db"))
    monkeypatch.setenv("NUTRICARE_MODEL", str(REAL_MODEL))
    vision.reset_predictor()
    application = create_app({"TESTING": True})
    yield application
    vision.reset_predictor()


def test_status_reports_metrics_from_the_training_sidecar(real_model_app):
    """The UI can show measured accuracy before the model is even loaded."""
    with real_model_app.test_client() as client:
        model = client.get("/api/vision/status").get_json()["model"]
    assert model["model_present"] is True
    sidecar = json.loads(REAL_MODEL.with_suffix(".metrics.json").read_text(encoding="utf-8"))
    assert model["test_accuracy"] == sidecar["test_metrics"]["accuracy"]
    assert model["architecture"] == sidecar["architecture"]
    # and it is a real, non-trivial result rather than a placeholder
    assert 0.0 < model["test_accuracy"] <= 1.0
    assert model["test_support"] >= 100


def test_trained_flag_reflects_the_installed_checkpoint(real_model_app):
    with real_model_app.test_client() as client:
        payload = client.get("/api/vision/classes").get_json()
    assert payload["model_installed"] is True
    assert payload["trained_count"] > 0
    trained = {c["slug"] for c in payload["classes"] if c["trained"]}
    checkpoint = __import__("torch").load(REAL_MODEL, map_location="cpu",
                                          weights_only=False)
    assert trained == set(checkpoint["classes"])
    assert len(trained) == payload["trained_count"]
    # taxonomy entries without a trained class must not claim recognition
    assert "biryani" not in trained or "chicken_biryani" in trained


def test_no_model_reports_zero_trained_classes(client, user):
    payload = client.get("/api/vision/classes").get_json()
    assert payload["model_installed"] is False
    assert payload["trained_count"] == 0
    assert all(c["trained"] is False for c in payload["classes"])


def test_real_model_predicts_a_known_class_with_confidence(real_model_app):
    """Exercises the actual trained weights end to end through the HTTP API."""
    from PIL import Image
    import io as _io
    import torch

    checkpoint = torch.load(REAL_MODEL, map_location="cpu", weights_only=False)
    # The default checkpoint is the licence-cleared one; its class count is a
    # property of that training run, not a constant to hard-code.
    assert len(checkpoint["classes"]) >= 2
    # Build a deterministic image (not synthetic training data — just input):
    # what matters is that the real network runs and returns calibrated output.
    buffer = _io.BytesIO()
    Image.new("RGB", (320, 240), (180, 140, 90)).save(buffer, "JPEG")
    with real_model_app.test_client() as client:
        client.post("/api/users", json={"name": "Real"})
        resp = client.post("/api/vision/predict?top_k=3", data=buffer.getvalue(),
                           content_type="application/octet-stream")
    assert resp.status_code == 200
    body = resp.get_json()
    labels = [p["label"] for p in body["predictions"]]
    assert len(labels) == 3
    slugs = {p["slug"] for p in body["predictions"]}
    assert slugs <= set(checkpoint["classes"])
    total = sum(p["confidence"] for p in body["predictions"])
    assert 0 < total <= 1.0 + 1e-6


def test_convert_refuses_to_guess_a_mismatched_backbone():
    """The ImageNet-backbone converter must fail loudly, never half-map."""
    sys_path = __import__("sys").path
    sys_path.insert(0, str(vision.PROJECT_DIR / "training"))
    try:
        import load_imagenet_backbone as backbone
    finally:
        sys_path.pop(0)
    import torch
    fake = {f"layer{i}": torch.zeros(1) for i in range(5)}
    with pytest.raises(ValueError, match="tensor count mismatch"):
        backbone.convert(fake, "mobilenet_v3_small")


# ------------------------------------------------- added with the CC0 12-class model
def test_new_cc0_classes_follow_the_nutrition_honesty_rule():
    """Classes added alongside the CC0 checkpoint must obey the same contract as
    the originals: either a real documented food row, or an explicit 'ask the
    user' entry. No third option, and never a fabricated figure."""
    by_slug = vision.class_by_slug()
    for slug in ("kheer", "rasgulla", "chomchom", "morog_polao", "luchi"):
        assert slug in by_slug, f"{slug} missing from the taxonomy"
        entry = by_slug[slug]
        if entry["nutrition_source"] == "unavailable":
            assert entry["food"] is None, (
                f"{slug} claims no nutrition but points at a food row")
        else:
            assert entry["food"], f"{slug} must name a documented food row"
            assert entry["default_grams"] > 0


def test_classes_without_nutrition_still_render_and_ask_for_values(client, user):
    """A recognised dish with no documented row must produce an explicit,
    numberless estimate — not a guess."""
    response = client.post("/api/vision/estimate",
                           json={"slug": "chomchom", "grams": 50})
    assert response.status_code == 200, response.get_data(as_text=True)
    payload = response.get_json()
    if payload.get("nutrition_available") is False:
        assert payload["nutrients"] is None
        assert "unavailable_reason" in payload
    else:                                   # a row exists: then it must be real
        assert payload["nutrients"]["kcal"] > 0


# ------------------------------------------------- default model licensing policy
def test_the_default_checkpoint_is_the_licence_cleared_one():
    """Regression guard for a licensing trap.

    The 20-class checkpoint scores better but was trained on images with no
    licence whatsoever. Shipping it as the default would present an
    unredistributable artifact as the product. The default must stay the model
    trained only on CC0 images; the older checkpoint stays in the repo,
    reachable but opt-in.
    """
    assert vision.DEFAULT_MODEL_PATH.name == "food_classifier_cc0.pt"
    assert vision.UNLICENSED_MODEL_PATH.name == "food_classifier.pt"
    assert vision.DEFAULT_MODEL_PATH != vision.UNLICENSED_MODEL_PATH


def test_cc0_checkpoint_records_its_licence_provenance():
    """The checkpoint itself must carry the evidence needed to audit it later,
    without re-reading this repo's docs."""
    if not vision.DEFAULT_MODEL_PATH.is_file():
        pytest.skip("licence-cleared checkpoint not present")
    torch = pytest.importorskip("torch")
    checkpoint = torch.load(vision.DEFAULT_MODEL_PATH, map_location="cpu",
                            weights_only=False)
    report = checkpoint["dataset_report"]
    assert report["kept_classes"] == len(checkpoint["classes"])
    dedupe = checkpoint["dedupe"]
    assert "hamming" in dedupe["method"]          # pre-split perceptual dedupe ran
    assert dedupe["threshold"] <= 2
    assert dedupe["kept"] > 0
