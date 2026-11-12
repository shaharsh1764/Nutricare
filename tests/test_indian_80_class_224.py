"""
Integration tests for NutriCare's primary 80-class Indian-food recognition model
(224x224 input resolution, MobileNetV3 Small + ImageNet transfer learning).

These tests exercise the real Predictor against the actual experimental
checkpoint. No neural network is simulated — inference is genuinely executed.

Coverage:
  - Checkpoint loads through nutricare.vision.Predictor
  - 224x224 preprocessing matches training configuration
  - All 80 class slugs are mapped
  - Prediction output structure (slug, label, group, confidence)
  - Softmax probabilities are valid (0-1, top-k sum <= 1)
  - Top-k predictions are clamped and validated
  - Low-confidence rejection works (threshold 0.40)
  - Invalid and corrupted images are rejected
  - Missing primary checkpoint raises ModelUnavailable
  - The 12-class checkpoint remains unchanged and available as technical fallback
  - Normal prediction uses the fixed primary/fallback policy, never a selector

The 80-class checkpoint is the scanner primary. Its training-image rights remain
unresolved and every returned food prediction remains unconfirmed.
"""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import pytest

from nutricare import create_app, db, vision

from nutricare import create_app, db, vision
from nutricare.vision import ModelUnavailable, Predictor

# Experimental checkpoint (NutriCare-compatible format, 224x224 input).
EXPERIMENTAL_CKPT = Path("models/v2/food_classifier_indian_80_224.pt")

# Default production checkpoint (must remain unchanged).
DEFAULT_CKPT = Path("models/food_classifier_cc0.pt")

# 12-class fallback (must remain unchanged).
FALLBACK_CKPT = Path("models/food_classifier_cc0.pt")

LOW_CONFIDENCE_THRESHOLD = 0.40


# ------------------------------------------------------------------ helpers
def make_png(width=224, height=224, colour=(180, 120, 60)):
    """Create a valid PNG in memory (no Pillow needed for construction)."""
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + bytes(colour) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def _sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ checkpoint verification
def test_experimental_checkpoint_exists():
    assert EXPERIMENTAL_CKPT.is_file(), (
        f"Experimental checkpoint not found: {EXPERIMENTAL_CKPT}"
    )


def test_experimental_checkpoint_sha256():
    """SHA256 of the metadata-sanitised checkpoint, with provenance.

    The original training-run checkpoint (SHA256 754b368c...) carried a
    false embedded licence string. It was re-serialised with corrected
    metadata only - weights bit-identical (state_dict hash and fixed-input
    logits verified) - by training/sanitise_checkpoint_metadata.py. The
    original hash must remain recorded in the metrics sidecar.
    """
    actual = _sha256(EXPERIMENTAL_CKPT)
    expected = (
        "b1e8187d45ad8f8cf6676c86350c08c8a231422d36cab71e152abba772b87068"
    )
    assert actual == expected, f"SHA256 mismatch: {actual} != {expected}"
    import json as _json
    metrics = _json.loads(EXPERIMENTAL_CKPT.with_suffix(".metrics.json")
                          .read_text(encoding="utf-8"))
    assert metrics["checkpoint_original_sha256"] == (
        "754b368cdf084233db00f86fc50693d00d85a433a366a832187ab35063b833dc")
    assert metrics["checkpoint_sanitised_sha256"] == expected
    assert metrics["licence"].startswith("UNRESOLVED")


def test_experimental_checkpoint_loads_through_predictor():
    """The converted checkpoint must load via the existing Predictor."""
    predictor = Predictor(EXPERIMENTAL_CKPT)
    predictor._load()
    assert predictor._model is not None
    assert len(predictor._classes) == 80


def test_experimental_checkpoint_has_80_classes():
    predictor = Predictor(EXPERIMENTAL_CKPT)
    predictor._load()
    assert len(predictor._classes) == 80


def test_experimental_checkpoint_classes_are_slugs():
    predictor = Predictor(EXPERIMENTAL_CKPT)
    predictor._load()
    slugs = [c["slug"] for c in predictor._classes]
    assert len(slugs) == len(set(slugs)), "Duplicate class slugs"
    assert all(isinstance(s, str) and s for s in slugs), "Empty or non-string slug"


def test_experimental_checkpoint_uses_mobilenet_v3_small():
    predictor = Predictor(EXPERIMENTAL_CKPT)
    predictor._load()
    assert predictor._meta.get("architecture") == "mobilenet_v3_small"


def test_experimental_checkpoint_input_size_is_224():
    """Preprocessing must use 224x224 exactly as during training."""
    predictor = Predictor(EXPERIMENTAL_CKPT)
    predictor._load()
    assert predictor._meta.get("input_size") == 224


def test_experimental_checkpoint_class_names_match_training():
    """Class names must match the 80 classes from the training run."""
    import torch
    ckpt = torch.load(EXPERIMENTAL_CKPT, map_location="cpu", weights_only=False)
    expected = ckpt["classes"]
    predictor = Predictor(EXPERIMENTAL_CKPT)
    predictor._load()
    actual = [c["slug"] for c in predictor._classes]
    assert actual == expected, "Class order mismatch with training checkpoint"


# ------------------------------------------------------------------ prediction structure
def test_experimental_prediction_output_structure():
    predictor = Predictor(EXPERIMENTAL_CKPT)
    predictor._load()
    result = predictor.predict(make_png(), top_k=5)
    assert "predictions" in result
    assert "top" in result
    assert "low_confidence" in result
    assert "threshold" in result
    assert "image" in result
    assert "single_label" in result
    assert result["single_label"] is True
    assert len(result["predictions"]) <= 5


def test_experimental_prediction_fields():
    predictor = Predictor(EXPERIMENTAL_CKPT)
    predictor._load()
    result = predictor.predict(make_png(), top_k=3)
    for pred in result["predictions"]:
        assert "slug" in pred
        assert "label" in pred
        assert "group" in pred
        assert "confidence" in pred
        assert "confidence_pct" in pred
        assert 0.0 <= pred["confidence"] <= 1.0
        assert 0.0 <= pred["confidence_pct"] <= 100.0


def test_experimental_confidence_values_are_valid_probabilities():
    """Confidence values must be valid softmax probabilities (0 to 1)."""
    predictor = Predictor(EXPERIMENTAL_CKPT)
    predictor._load()
    result = predictor.predict(make_png(), top_k=5)
    total = sum(p["confidence"] for p in result["predictions"])
    assert 0 < total <= 1.0 + 1e-6, f"Top-k softmax sum {total} not in (0, 1]"


def test_experimental_top_k_is_clamped():
    predictor = Predictor(EXPERIMENTAL_CKPT)
    predictor._load()
    # top_k > 5 should be clamped
    result = predictor.predict(make_png(), top_k=10)
    assert len(result["predictions"]) <= 5
    # top_k = 1 should return exactly 1
    result = predictor.predict(make_png(), top_k=1)
    assert len(result["predictions"]) == 1


def test_experimental_low_confidence_flag_is_honest():
    """low_confidence must be True when top confidence < threshold."""
    predictor = Predictor(EXPERIMENTAL_CKPT)
    predictor._load()
    result = predictor.predict(make_png(), top_k=5)
    top_conf = result["top"]["confidence"]
    assert result["low_confidence"] == (top_conf < LOW_CONFIDENCE_THRESHOLD)
    assert result["threshold"] == LOW_CONFIDENCE_THRESHOLD


# ------------------------------------------------------------------ invalid images
def test_experimental_invalid_image_rejected():
    predictor = Predictor(EXPERIMENTAL_CKPT)
    predictor._load()
    with pytest.raises(vision.ImageError):
        predictor.predict(b"not an image")


def test_experimental_truncated_image_rejected():
    predictor = Predictor(EXPERIMENTAL_CKPT)
    predictor._load()
    # Truncated PNG: valid header but cut off
    truncated = make_png()[:100]
    with pytest.raises(vision.ImageError):
        predictor.predict(truncated)


# ------------------------------------------------------------------ missing/corrupted model
def test_experimental_missing_model_raises(tmp_path, monkeypatch):
    """A missing experimental checkpoint must raise ModelUnavailable, not silently
    fall back to the default model."""
    missing = tmp_path / "nonexistent_experimental.pt"
    predictor = Predictor(missing)
    with pytest.raises(ModelUnavailable):
        predictor._load()


def test_experimental_corrupted_checkpoint_raises(tmp_path):
    """A corrupted checkpoint file must raise ModelUnavailable."""
    corrupted = tmp_path / "corrupted.pt"
    corrupted.write_bytes(b"not a valid checkpoint")
    predictor = Predictor(corrupted)
    with pytest.raises(ModelUnavailable):
        predictor._load()


# ------------------------------------------------------------------ default model unchanged
def test_default_model_remains_unchanged():
    """The default 12-class CC0 checkpoint must be untouched."""
    assert DEFAULT_CKPT.is_file()
    import hashlib
    h = hashlib.sha256(DEFAULT_CKPT.read_bytes()).hexdigest()
    expected = (
        "f74d10f6efe6a7848870b16388d56a570086901afa11d6ed78e7cd914f02ad87"
    )
    assert h == expected, f"Default model SHA256 changed: {h}"


def test_experimental_is_separate_from_default():
    """The experimental checkpoint must be a different file from the default."""
    assert EXPERIMENTAL_CKPT != DEFAULT_CKPT
    assert _sha256(EXPERIMENTAL_CKPT) != _sha256(DEFAULT_CKPT)


def test_primary_predictor_uses_the_80_class_checkpoint():
    predictor = vision.get_primary_predictor()
    assert predictor.model_path == vision.PRIMARY_MODEL_PATH
    assert predictor.model_path == EXPERIMENTAL_CKPT.resolve()


# ------------------------------------------------------------------ 12-class fallback
def test_twelve_class_technical_fallback_remains_available():
    """The 12-class checkpoint is intact but is not normal scan priority."""
    fallback = Predictor(FALLBACK_CKPT)
    fallback._load()
    assert len(fallback._classes) == 12
    assert fallback._meta.get("input_size") == 224  # CC0 model uses 224


def test_available_models_report_fixed_primary_and_technical_fallback_roles():
    models = {m["name"]: m for m in vision.get_available_models()}
    assert models[vision.PRIMARY_MODEL_NAME]["classes"] == 80
    assert models[vision.PRIMARY_MODEL_NAME]["role"] == "primary"
    assert models[vision.FALLBACK_MODEL_NAME]["classes"] == 12
    assert models[vision.FALLBACK_MODEL_NAME]["role"] == "technical_fallback"
    assert all(m["selection_allowed"] is False for m in models.values())


# ------------------------------------------------------------------ end-to-end via app
def test_end_to_end_prediction_with_experimental_model(tmp_path, monkeypatch):
    """End-to-end: load experimental model, predict on a real image, verify
    output structure and low-confidence handling. Does not fabricate accuracy."""
    from nutricare import create_app

    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "vision_e2e.db"))
    monkeypatch.setenv("NUTRICARE_MODEL", str(tmp_path / "absent.pt"))
    vision.reset_predictor()

    application = create_app({"TESTING": True})
    with application.test_client() as client:
        # Register a user (needed for /api/vision/predict)
        resp = client.post("/api/users", json={"name": "Scanner Tester"})
        assert resp.status_code == 201

        # The fixed runtime uses the 80-class primary model. The absent
        # NUTRICARE_MODEL override affects only the technical fallback.
        resp = client.post("/api/vision/predict?top_k=5",
                           data=make_png(),
                           content_type="application/octet-stream")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["model"] == vision.PRIMARY_MODEL_NAME
        assert body["recognition"]["fallback_used"] is False
        assert body["recognition"]["prediction_unconfirmed"] is True
        assert "ensemble" not in body
        assert len(body["predictions"]) <= 5
        assert "low_confidence" in body
        assert "threshold" in body

    vision.reset_predictor()


# ------------------------------------------------------------------ nutrition mappings for experimental model
def test_experimental_nutrition_mappings_have_food_entries():
    """Newly added taxonomy entries for experimental classes must reference
    existing foods.json entries."""
    taxonomy = json.loads(Path("data/food_classes.json").read_text())
    classes_by_slug = {c["slug"]: c for c in taxonomy["classes"]}

    mapped = {
        "biryani": "Chicken biryani",
        "chapati": "Roti, whole wheat (cooked)",
        "chana_masala": "Chole / chana masala (prepared)",
        "cham_cham": "Chomchom (chhena sweet, prepared)",
        "kadhi_pakoda": "Kadhi pakora (prepared)",
        "lassi": "Lassi, sweet (prepared)",
        "chak_hao_kheer": "Kheer, milk-rice (prepared)",
        "doodhpak": "Kheer, milk-rice (prepared)",
        "navrattan_korma": "Vegetable curry, mixed (prepared)",
        "phirni": "Kheer, milk-rice (prepared)",
    }
    for slug, expected_food in mapped.items():
        assert slug in classes_by_slug, f"{slug} missing from taxonomy"
        entry = classes_by_slug[slug]
        assert entry["food"] == expected_food, (
            f"{slug}: expected food={expected_food!r}, got {entry['food']!r}"
        )


def test_experimental_nutrition_mappings_resolve_via_api(tmp_path, monkeypatch):
    """Nutrition estimates work for experimentally mapped classes via the API."""
    from nutricare import create_app

    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "vision_nutrition.db"))
    monkeypatch.setenv("NUTRICARE_MODEL", str(tmp_path / "absent.pt"))
    vision.reset_predictor()

    application = create_app({"TESTING": True})
    with application.test_client() as client:
        client.post("/api/users", json={"name": "Nutrition Tester"})

        for slug in ["biryani", "chapati", "lassi", "kadhi_pakoda"]:
            resp = client.post("/api/vision/estimate",
                               json={"slug": slug, "grams": 150})
            assert resp.status_code == 200, f"{slug}: {resp.get_json()}"
            body = resp.get_json()
            assert body["nutrition_available"] is True, f"{slug}: no nutrition"
            assert body["nutrients"]["kcal"] > 0, f"{slug}: zero calories"
            assert body["food"] is not None, f"{slug}: no food entry"

    vision.reset_predictor()


def test_experimental_nutrition_approximate_marked(tmp_path, monkeypatch):
    """Approximate mappings carry approx_note explaining the approximation."""
    from nutricare import create_app

    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "vision_approx.db"))
    monkeypatch.setenv("NUTRICARE_MODEL", str(tmp_path / "absent.pt"))
    vision.reset_predictor()

    application = create_app({"TESTING": True})
    with application.test_client() as client:
        client.post("/api/users", json={"name": "Approx Tester"})

        # chak_hao_kheer mapped to kheer (approx)
        resp = client.post("/api/vision/estimate",
                           json={"slug": "chak_hao_kheer", "grams": 150})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["nutrition_available"] is True
        assert body["approx_note"] is not None
        assert "black rice" in body["approx_note"].lower()

    vision.reset_predictor()


def test_experimental_missing_nutrition_mappings(tmp_path, monkeypatch):
    """Classes without nutrition mappings return nutrition_available=False
    with an honest message, not an error."""
    from nutricare import create_app

    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "vision_nonutrition.db"))
    monkeypatch.setenv("NUTRICARE_MODEL", str(tmp_path / "absent.pt"))
    vision.reset_predictor()

    application = create_app({"TESTING": True})
    with application.test_client() as client:
        client.post("/api/users", json={"name": "NoNutrition Tester"})

        for slug in ["butter_chicken", "gulab_jamun", "dum_aloo", "gajar_ka_halwa"]:
            resp = client.post("/api/vision/estimate",
                               json={"slug": slug, "grams": 150})
            assert resp.status_code == 200, f"{slug}: {resp.get_json()}"
            body = resp.get_json()
            assert body["nutrition_available"] is False, f"{slug}: should have no nutrition"
            assert "unavailable_reason" in body, f"{slug}: missing reason"

    vision.reset_predictor()


def test_experimental_serving_size_calculations(tmp_path, monkeypatch):
    """Nutrition scales correctly with portion size."""
    from nutricare import create_app

    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "vision_serving.db"))
    monkeypatch.setenv("NUTRICARE_MODEL", str(tmp_path / "absent.pt"))
    vision.reset_predictor()

    application = create_app({"TESTING": True})
    with application.test_client() as client:
        client.post("/api/users", json={"name": "Serving Tester"})

        # Same slug, different portions
        resp_100 = client.post("/api/vision/estimate",
                               json={"slug": "biryani", "grams": 100})
        resp_300 = client.post("/api/vision/estimate",
                               json={"slug": "biryani", "grams": 300})
        assert resp_100.status_code == 200
        assert resp_300.status_code == 200

        n100 = resp_100.get_json()["nutrients"]
        n300 = resp_300.get_json()["nutrients"]

        # 3x portion should give ~3x calories
        assert n100 is not None and n300 is not None
        ratio = n300["kcal"] / n100["kcal"]
        assert 2.9 < ratio < 3.1, f"Expected ~3x scaling, got {ratio}x"

    vision.reset_predictor()


def test_experimental_classes_endpoint_shows_all_80(tmp_path, monkeypatch):
    """The classes endpoint reports all taxonomy classes including experimental."""
    from nutricare import create_app

    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "vision_classes80.db"))
    monkeypatch.setenv("NUTRICARE_MODEL", str(tmp_path / "absent.pt"))
    vision.reset_predictor()

    application = create_app({"TESTING": True})
    with application.test_client() as client:
        client.post("/api/users", json={"name": "Classes80 Tester"})

        resp = client.get("/api/vision/classes")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["count"] >= 80, f"Expected >= 80 classes, got {body['count']}"

        slugs = {c["slug"] for c in body["classes"]}
        # All experimental model classes should be in the taxonomy
        experimental_slugs = [
            "biryani", "chapati", "chana_masala", "cham_cham",
            "kadhi_pakoda", "lassi", "butter_chicken", "gulab_jamun",
            "dum_aloo", "gajar_ka_halwa"
        ]
        for slug in experimental_slugs:
            assert slug in slugs, f"{slug} missing from classes endpoint"

    vision.reset_predictor()


# ------------------------------------------------------------------ recognition-to-nutrition integration
def test_experimental_prediction_includes_nutrition(tmp_path, monkeypatch):
    """End-to-end: experimental model prediction includes nutrition for
    mapped classes, and honest unavailability for unmapped ones."""
    from nutricare import create_app

    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "vision_e2e_nutrition.db"))
    monkeypatch.setenv("NUTRICARE_MODEL", str(tmp_path / "absent.pt"))
    vision.reset_predictor()

    application = create_app({"TESTING": True})
    with application.test_client() as client:
        client.post("/api/users", json={"name": "E2E Nutrition Tester"})

        # Predict with the fixed 80-class primary. We cannot control the
        # actual class, but every candidate still needs a nutrition response.
        resp = client.post("/api/vision/predict?top_k=5",
                           data=make_png(),
                           content_type="application/octet-stream")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["model"] == vision.PRIMARY_MODEL_NAME
        assert body["recognition"]["fallback_used"] is False

        # Each candidate should have nutrition info (available or not)
        for candidate in body["candidates"]:
            assert "nutrition" in candidate, f"Missing nutrition for {candidate['slug']}"
            assert "nutrition_available" in candidate["nutrition"]

    vision.reset_predictor()


# ------------------------------------------------------------------ default model unchanged after taxonomy changes
def test_default_model_classes_still_work(tmp_path, monkeypatch):
    """The 12-class default model still works after taxonomy expansion."""
    from nutricare import create_app

    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "vision_default.db"))
    monkeypatch.setenv("NUTRICARE_MODEL", str(FALLBACK_CKPT))
    monkeypatch.setattr(vision, "PRIMARY_MODEL_PATH", tmp_path / "missing-primary.pt")
    vision.reset_predictor()

    application = create_app({"TESTING": True})
    with application.test_client() as client:
        client.post("/api/users", json={"name": "Default Tester"})

        resp = client.post("/api/vision/predict?top_k=3",
                           data=make_png(),
                           content_type="application/octet-stream")
        assert resp.status_code == 200
        body = resp.get_json()
        # Force a missing primary checkpoint so this is a genuine technical
        # fallback test, not a selectable/default model test.
        assert len(body["predictions"]) <= 3
        assert body["model"] == vision.FALLBACK_MODEL_NAME
        assert body["recognition"]["fallback_used"] is True
        assert body["top"]["slug"] in \
            {"chicken_biryani", "chole", "chomchom", "curd_dahi", "jalebi",
             "kheer", "khichdi", "morog_polao", "pakora", "pani_puri",
             "paratha_plain", "rasgulla"}
        assert "low_confidence" in body

        # All predicted slugs should be in the taxonomy
        taxonomy = json.loads(Path("data/food_classes.json").read_text())
        taxonomy_slugs = {c["slug"] for c in taxonomy["classes"]}
        for pred in body["predictions"]:
            assert pred["slug"] in taxonomy_slugs, f"{pred['slug']} not in taxonomy"

    vision.reset_predictor()
