"""Regression tests for the fixed scanner recognition policy.

A normal scan invokes only the 80-class Indian-food primary model. The
12-class CC0-declared checkpoint is a technical fallback only: it is tried after
an absent/unreadable primary checkpoint, primary initialisation failure, or a
primary inference exception. Low confidence is not a fallback condition.

Predictor doubles make the policy deterministic without claiming model accuracy.
API-level assertions retain the existing validation, nutrition attachment and
meal-log integration paths.
"""
from __future__ import annotations

import copy
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
    """Return one Predictor.predict-shaped result from (slug, confidence)."""
    labels = vision.class_by_slug()
    predictions = [{
        "slug": slug,
        "label": (labels.get(slug) or {}).get("label", slug),
        "group": (labels.get(slug) or {}).get("group", "unknown"),
        "confidence": confidence,
        "confidence_pct": round(confidence * 100, 1),
    } for slug, confidence in slug_conf]
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
    """A scripted predictor that records exactly how scanner policy used it."""

    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error
        self.calls: list[tuple[bytes, int]] = []

    def predict(self, image_bytes, top_k=3):
        self.calls.append((image_bytes, top_k))
        if self._error is not None:
            raise self._error
        return copy.deepcopy(self._result)


@pytest.fixture()
def policy(monkeypatch):
    """Install independent primary/fallback doubles and return them."""
    primary = FakePredictor()
    fallback = FakePredictor()
    monkeypatch.setattr(vision, "get_primary_predictor", lambda: primary)
    monkeypatch.setattr(vision, "get_fallback_predictor", lambda: fallback)
    return primary, fallback


# ------------------------------------------------------ direct policy tests
def test_normal_scan_calls_only_80_class_primary(policy):
    primary, fallback = policy
    primary._result = make_result(("chana_masala", 0.83), ("biryani", 0.05))
    image = make_png()

    result = vision.recognize(image, top_k=2)

    assert primary.calls == [(image, 2)]
    assert fallback.calls == []
    assert result["model"] == vision.PRIMARY_MODEL_NAME
    assert result["top"]["slug"] == "chana_masala"
    assert result["top"]["label"] == vision.class_by_slug()["chana_masala"]["label"]
    assert result["recognition"] == {
        "served_by": vision.PRIMARY_MODEL_NAME,
        "primary_model": vision.PRIMARY_MODEL_NAME,
        "fallback_used": False,
        "fallback_reason": None,
        "prediction_unconfirmed": True,
        "confidence_calibrated": False,
        "confidence_note": vision.CONFIDENCE_NOTE,
        "low_confidence_triggers_fallback": False,
    }
    assert "ensemble" not in result


def test_low_confidence_primary_prediction_never_calls_fallback(policy):
    primary, fallback = policy
    primary._result = make_result(("pithe", 0.12))

    result = vision.recognize(make_png())

    assert result["low_confidence"] is True
    assert result["top"]["confidence"] == 0.12
    assert primary.calls
    assert fallback.calls == []
    assert result["recognition"]["fallback_used"] is False
    assert result["recognition"]["low_confidence_triggers_fallback"] is False


@pytest.mark.parametrize(
    ("error", "expected_reason"),
    [
        (vision.ModelUnavailable("No model checkpoint at primary.pt."),
         "primary_unavailable"),
        (vision.ModelUnavailable("Checkpoint could not be read: corrupt"),
         "primary_unavailable"),
        (RuntimeError("model initialisation failed"), "primary_inference_error"),
        (RuntimeError("inference operator failed"), "primary_inference_error"),
    ],
    ids=("missing", "unreadable", "initialisation", "inference"),
)
def test_technical_primary_failures_use_12_class_fallback(policy, error,
                                                           expected_reason):
    primary, fallback = policy
    primary._error = error
    fallback._result = make_result(("chole", 0.91))
    image = make_png()

    result = vision.recognize(image, top_k=1)

    assert primary.calls == [(image, 1)]
    assert fallback.calls == [(image, 1)]
    assert result["model"] == vision.FALLBACK_MODEL_NAME
    assert result["top"]["slug"] == "chole"
    assert result["recognition"]["fallback_used"] is True
    assert result["recognition"]["fallback_reason"] == expected_reason
    assert result["recognition"]["prediction_unconfirmed"] is True
    assert "ensemble" not in result


def test_primary_image_error_is_not_a_model_failure_and_does_not_fallback(policy):
    primary, fallback = policy
    primary._error = vision.ImageError("This image could not be decoded.")

    with pytest.raises(vision.ImageError, match="could not be decoded"):
        vision.recognize(make_png())

    assert len(primary.calls) == 1
    assert fallback.calls == []


def test_both_technical_failures_are_recognition_unavailable(policy):
    primary, fallback = policy
    primary._error = vision.ModelUnavailable("primary missing")
    fallback._error = vision.ModelUnavailable("fallback missing")

    with pytest.raises(vision.ModelUnavailable, match="both failed"):
        vision.recognize(make_png())

    assert len(primary.calls) == 1
    assert len(fallback.calls) == 1


def test_policy_declares_no_confidence_based_fallback():
    assert vision.TECHNICAL_FALLBACK_CONDITIONS == (
        "the 80-class primary checkpoint is missing",
        "the 80-class primary checkpoint cannot be read",
        "the 80-class primary model cannot initialise",
        "the 80-class primary model raises an inference exception",
    )
    report = vision.recognition_status()
    assert report["policy"]["primary_model"] == vision.PRIMARY_MODEL_NAME
    assert report["policy"]["technical_fallback_model"] == vision.FALLBACK_MODEL_NAME
    assert report["policy"]["low_confidence_triggers_fallback"] is False
    assert report["policy"]["prediction_unconfirmed"] is True
    assert report["policy"]["confidence_calibrated"] is False


# ------------------------------------------------------------- API policy
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "policy.db"))
    app = create_app({"TESTING": True})
    with app.test_client() as test_client:
        assert test_client.post(
            "/api/users", json={"name": "Recognition Policy Tester"}
        ).status_code == 201
        yield test_client


# -------------------------------------------------- scanner class metadata
def test_classes_endpoint_reads_primary_sidecar_without_accessing_predictors(
        client, monkeypatch):
    """Class coverage must not start either model during scanner setup."""
    calls = []

    def unexpected_predictor_access(*args, **kwargs):
        calls.append((args, kwargs))
        pytest.fail("class metadata must not access an inference predictor")

    monkeypatch.setattr(vision, "get_predictor", unexpected_predictor_access)
    monkeypatch.setattr(vision, "get_primary_predictor", unexpected_predictor_access)
    monkeypatch.setattr(vision, "get_fallback_predictor", unexpected_predictor_access)

    response = client.get("/api/vision/classes")

    assert response.status_code == 200
    body = response.get_json()
    assert calls == []
    assert body["model_installed"] is True
    assert body["trained_count"] == 80
    trained = {entry["slug"] for entry in body["classes"] if entry["trained"]}
    assert {"biryani", "chapati", "chana_masala"} <= trained


def test_normal_scanner_metadata_setup_leaves_both_checkpoints_unloaded(
        client, monkeypatch):
    """The status + classes requests made by renderScanner stay side-effect-free."""
    vision.reset_predictor()
    loads = []

    def unexpected_load(self):
        loads.append(self.model_path)
        pytest.fail("scanner initialization must not load a checkpoint")

    monkeypatch.setattr(vision.Predictor, "_load", unexpected_load)

    status = client.get("/api/vision/status")
    coverage = client.get("/api/vision/classes")

    assert status.status_code == 200
    assert coverage.status_code == 200
    assert loads == []
    primary = vision._PREDICTORS[vision.PRIMARY_MODEL_NAME]  # noqa: SLF001
    fallback = vision._PREDICTORS[vision.FALLBACK_MODEL_NAME]  # noqa: SLF001
    assert primary._model is None and primary._attempted is False  # noqa: SLF001
    assert fallback._model is None and fallback._attempted is False  # noqa: SLF001
    assert coverage.get_json()["trained_count"] == 80


def test_api_normal_scan_runs_primary_only_and_attaches_nutrition(client, policy):
    primary, fallback = policy
    primary._result = make_result(("chana_masala", 0.81), ("jalebi", 0.08))
    image = make_png()

    response = client.post("/api/vision/predict?top_k=2", data=image,
                           content_type="application/octet-stream")

    assert response.status_code == 200
    body = response.get_json()
    assert primary.calls == [(image, 2)]
    assert fallback.calls == []
    assert body["model"] == vision.PRIMARY_MODEL_NAME
    assert body["recognition"]["fallback_used"] is False
    assert body["recognition"]["prediction_unconfirmed"] is True
    assert "ensemble" not in body
    assert [c["slug"] for c in body["candidates"]] == ["chana_masala", "jalebi"]
    assert body["candidates"][0]["nutrition"]["nutrition_available"] is True


def test_api_primary_failure_uses_fallback_and_keeps_nutrition_flow(client, policy):
    primary, fallback = policy
    primary._error = vision.ModelUnavailable("primary checkpoint missing")
    fallback._result = make_result(("chole", 0.89))

    response = client.post("/api/vision/predict", data=make_png(),
                           content_type="application/octet-stream")

    assert response.status_code == 200
    body = response.get_json()
    assert len(primary.calls) == 1
    assert len(fallback.calls) == 1
    assert body["model"] == vision.FALLBACK_MODEL_NAME
    assert body["recognition"]["fallback_used"] is True
    assert body["candidates"][0]["nutrition"]["food"]["name"] == \
        "Chole / chana masala (prepared)"


def test_api_both_technical_failures_return_existing_503(client, policy):
    primary, fallback = policy
    primary._error = vision.ModelUnavailable("primary missing")
    fallback._error = RuntimeError("fallback inference failure")

    response = client.post("/api/vision/predict", data=make_png(),
                           content_type="application/octet-stream")

    assert response.status_code == 503
    body = response.get_json()
    assert body["model_unavailable"] is True
    assert "predictions" not in body
    assert "both failed" in body["error"]


def test_api_keeps_image_validation_before_either_model(client, policy):
    primary, fallback = policy

    response = client.post("/api/vision/predict", data=b"not-an-image",
                           content_type="application/octet-stream")

    assert response.status_code == 400
    assert "Unsupported file type" in response.get_json()["error"]
    assert primary.calls == []
    assert fallback.calls == []


def test_legacy_selection_endpoints_are_deprecated_without_selecting(client):
    listing = client.get("/api/vision/models")
    assert listing.status_code == 200
    body = listing.get_json()
    assert body["deprecated"] is True
    assert body["policy"]["primary_model"] == vision.PRIMARY_MODEL_NAME
    assert all(model["selection_allowed"] is False for model in body["models"])

    selected = client.post("/api/vision/select-model", json={"model": "experimental"})
    assert selected.status_code == 410
    assert selected.get_json()["deprecated"] is True

    status_with_legacy_parameter = client.get("/api/vision/status?model=experimental")
    assert status_with_legacy_parameter.status_code == 400
    assert status_with_legacy_parameter.get_json()["deprecated"] is True


def test_legacy_predict_query_does_not_change_fixed_runtime_policy(client, policy):
    primary, fallback = policy
    primary._result = make_result(("chapati", 0.77))

    response = client.post("/api/vision/predict?model=experimental", data=make_png(),
                           content_type="application/octet-stream")

    assert response.status_code == 200
    assert len(primary.calls) == 1
    assert fallback.calls == []
    assert response.get_json()["model"] == vision.PRIMARY_MODEL_NAME


def test_existing_meal_logging_flow_remains_intact(client, policy):
    primary, _fallback = policy
    primary._result = make_result(("chole", 0.9))

    predicted = client.post("/api/vision/predict", data=make_png(),
                            content_type="application/octet-stream").get_json()
    assert predicted["top"]["slug"] == "chole"

    estimate = client.post("/api/vision/estimate",
                           json={"slug": "chole", "grams": 100})
    assert estimate.status_code == 200
    assert estimate.get_json()["nutrition_available"] is True

    logged = client.post("/api/vision/log", json={
        "slug": "chole", "grams": 100, "meal": "lunch",
    })
    assert logged.status_code == 201
    assert logged.get_json()["entry"]["quantity"] == 100.0
