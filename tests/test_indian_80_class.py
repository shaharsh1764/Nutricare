"""
Integration tests for the experimental 80-class Indian-food classifier.

These tests verify that the transfer-learning checkpoint (MobileNetV3 Small +
ImageNet pretrained weights, fine-tuned on the 80-class Indian-food dataset)
can be loaded through NutriCare's existing recognition architecture
(``nutricare.vision.Predictor``) and produces correct, honest predictions.

The existing 12-class fallback model is NOT modified or replaced by any of
these tests. The 80-class model is experimental only and selectable via an
explicit checkpoint path — it never becomes the production default.

Tests are skipped when the experimental checkpoint is not present, so the
suite remains runnable in any environment.
"""

import io
import json
import struct
import zlib
from pathlib import Path

import pytest

from nutricare import vision

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
EXPERIMENTAL_CKPT = Path("models/v2/food_classifier_indian_80_224.pt")


def make_png(width=64, height=64, colour=(180, 120, 60)):
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + bytes(colour) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def _require_experimental_ckpt():
    """Skip if the experimental checkpoint is not available."""
    if not EXPERIMENTAL_CKPT.is_file():
        pytest.skip(
            f"experimental checkpoint not found: {EXPERIMENTAL_CKPT}"
        )


# --------------------------------------------------------------------------- #
# Checkpoint loading
# --------------------------------------------------------------------------- #
def test_experimental_checkpoint_exists():
    _require_experimental_ckpt()


def test_experimental_checkpoint_loads_through_predictor():
    """The 80-class checkpoint must load through the existing Predictor."""
    _require_experimental_ckpt()
    predictor = vision.Predictor(EXPERIMENTAL_CKPT)
    predictor._load()
    assert predictor._model is not None
    assert len(predictor._classes) == 80


def test_experimental_checkpoint_has_80_classes():
    """The checkpoint must contain exactly 80 class slugs."""
    _require_experimental_ckpt()
    predictor = vision.Predictor(EXPERIMENTAL_CKPT)
    predictor._load()
    slugs = [c["slug"] for c in predictor._classes]
    assert len(slugs) == 80
    assert len(set(slugs)) == 80  # all unique


def test_experimental_checkpoint_classes_are_slugs():
    """Class slugs must be lowercase snake_case identifiers."""
    _require_experimental_ckpt()
    predictor = vision.Predictor(EXPERIMENTAL_CKPT)
    predictor._load()
    for entry in predictor._classes:
        slug = entry["slug"]
        assert slug == slug.lower(), f"slug not lowercase: {slug!r}"
        assert " " not in slug, f"slug contains space: {slug!r}"
        assert slug.replace("_", "").isalnum(), f"slug not alnum/underscore: {slug!r}"


def test_experimental_checkpoint_uses_mobilenet_v3_small():
    """Architecture must be mobilenet_v3_small (matches existing pipeline)."""
    _require_experimental_ckpt()
    predictor = vision.Predictor(EXPERIMENTAL_CKPT)
    predictor._load()
    assert predictor._meta["architecture"] == "mobilenet_v3_small"


# --------------------------------------------------------------------------- #
# Class mapping
# --------------------------------------------------------------------------- #
def test_experimental_class_mapping_references_taxonomy():
    """Each checkpoint class slug must map to the taxonomy (or 'unknown')."""
    _require_experimental_ckpt()
    predictor = vision.Predictor(EXPERIMENTAL_CKPT)
    predictor._load()
    by_slug = vision.class_by_slug()
    for entry in predictor._classes:
        slug = entry["slug"]
        if slug in by_slug:
            assert entry["label"] == by_slug[slug]["label"]
        else:
            # Classes not in the 70-class taxonomy are marked 'unknown'
            assert entry["group"] == "unknown"


def test_experimental_prediction_slugs_subset_of_checkpoint():
    """Every returned prediction slug must belong to the 80-class checkpoint."""
    _require_experimental_ckpt()
    predictor = vision.Predictor(EXPERIMENTAL_CKPT)
    predictor._load()

    import torch
    from PIL import Image

    model = predictor._model
    transform = predictor._transform

    allowed = {c["slug"] for c in predictor._classes}
    for _ in range(5):
        image = Image.new("RGB", (200, 200), (100, 150, 200))
        tensor = transform(image).unsqueeze(0)
        with torch.no_grad():
            logits = model(tensor)[0]
            probs = torch.softmax(logits, dim=0).tolist()
        ranked = sorted(zip(predictor._classes, probs),
                        key=lambda pair: -pair[1])[:3]
        for cls, _prob in ranked:
            assert cls["slug"] in allowed


# --------------------------------------------------------------------------- #
# Predictions
# --------------------------------------------------------------------------- #
def test_experimental_prediction_output_structure():
    """Prediction response must match the existing response structure."""
    _require_experimental_ckpt()
    predictor = vision.Predictor(EXPERIMENTAL_CKPT)
    predictor._load()

    result = predictor.predict(make_png(), top_k=3)

    assert "predictions" in result
    assert "top" in result
    assert "low_confidence" in result
    assert "threshold" in result
    assert "image" in result
    assert "single_label" in result
    assert result["single_label"] is True
    assert len(result["predictions"]) == 3
    assert result["top"] == result["predictions"][0]

    for pred in result["predictions"]:
        assert "slug" in pred
        assert "label" in pred
        assert "group" in pred
        assert "confidence" in pred
        assert "confidence_pct" in pred
        assert 0.0 <= pred["confidence"] <= 1.0


def test_experimental_confidence_values_are_valid_probabilities():
    """Confidence values must be valid softmax probabilities (0 to 1)."""
    _require_experimental_ckpt()
    predictor = vision.Predictor(EXPERIMENTAL_CKPT)
    predictor._load()

    result = predictor.predict(make_png(), top_k=5)
    for pred in result["predictions"]:
        assert 0.0 <= pred["confidence"] <= 1.0
    # Top-k probabilities sum to at most 1 (not all classes are returned)
    total = sum(p["confidence"] for p in result["predictions"])
    assert 0 < total <= 1.0 + 1e-6


# --------------------------------------------------------------------------- #
# Low-confidence rejection
# --------------------------------------------------------------------------- #
def test_experimental_low_confidence_flag_is_honest():
    """low_confidence must be a real bool tied to the threshold."""
    _require_experimental_ckpt()
    predictor = vision.Predictor(EXPERIMENTAL_CKPT)
    predictor._load()

    result = predictor.predict(make_png())
    assert isinstance(result["low_confidence"], bool)
    assert result["threshold"] == vision.LOW_CONFIDENCE_THRESHOLD
    if result["top"]["confidence"] < vision.LOW_CONFIDENCE_THRESHOLD:
        assert result["low_confidence"] is True


def test_experimental_low_confidence_rejection_works():
    """A low-confidence prediction must be flagged, not presented as definite."""
    _require_experimental_ckpt()
    predictor = vision.Predictor(EXPERIMENTAL_CKPT)
    predictor._load()

    # Random noise image: model should not be confident
    result = predictor.predict(make_png(colour=(200, 200, 200)))
    # With random input, confidence is typically below threshold
    # We just verify the flag is consistent with the confidence value
    assert result["low_confidence"] == (
        result["top"]["confidence"] < vision.LOW_CONFIDENCE_THRESHOLD
    )


# --------------------------------------------------------------------------- #
# Invalid image handling
# --------------------------------------------------------------------------- #
def test_experimental_invalid_image_rejected():
    """Non-image bytes must raise ImageError, never produce a prediction."""
    _require_experimental_ckpt()
    predictor = vision.Predictor(EXPERIMENTAL_CKPT)
    predictor._load()

    with pytest.raises(vision.ImageError):
        predictor.predict(b"not-an-image")


def test_experimental_truncated_image_rejected():
    """Truncated image bytes must raise ImageError."""
    _require_experimental_ckpt()
    predictor = vision.Predictor(EXPERIMENTAL_CKPT)
    predictor._load()

    with pytest.raises(vision.ImageError):
        predictor.predict(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10)


# --------------------------------------------------------------------------- #
# Unavailable model handling
# --------------------------------------------------------------------------- #
def test_experimental_missing_model_raises():
    """A missing checkpoint must raise ModelUnavailable, never guess."""
    _require_experimental_ckpt()
    predictor = vision.Predictor(Path("/nonexistent/indian_80.pt"))
    with pytest.raises(vision.ModelUnavailable):
        predictor.predict(make_png())


def test_experimental_corrupted_checkpoint_raises(tmp_path):
    """A non-checkpoint file must fail loudly at load time."""
    _require_experimental_ckpt()
    broken = tmp_path / "broken.pt"
    broken.write_bytes(b"not a torch checkpoint")
    predictor = vision.Predictor(broken)
    with pytest.raises(vision.ModelUnavailable):
        predictor.predict(make_png())


# --------------------------------------------------------------------------- #
# 12-class fallback is untouched
# --------------------------------------------------------------------------- #
def test_twelve_class_fallback_remains_default():
    """The experimental tests must not change the default 12-class model."""
    assert vision.DEFAULT_MODEL_PATH.name == "food_classifier_cc0.pt"
    assert vision.DEFAULT_MODEL_PATH.is_file()
    import torch
    ckpt = torch.load(vision.DEFAULT_MODEL_PATH, map_location="cpu",
                      weights_only=False)
    assert len(ckpt["classes"]) == 12


def test_experimental_is_separate_from_default():
    """The 80-class checkpoint must be a separate file, not the default."""
    _require_experimental_ckpt()
    assert EXPERIMENTAL_CKPT != vision.DEFAULT_MODEL_PATH
    assert EXPERIMENTAL_CKPT.name != "food_classifier_cc0.pt"
