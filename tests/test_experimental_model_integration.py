"""Integration checks for the 80-class-primary scanner configuration."""
from __future__ import annotations

import os
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

from nutricare import create_app, vision

REPO_CKPT = Path("models/v2/food_classifier_indian_80_224.pt")


def make_png(width=64, height=64, colour=(180, 120, 60)):
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + bytes(colour) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


@pytest.fixture(autouse=True)
def reset_predictors():
    vision.reset_predictor()
    yield
    vision.reset_predictor()


def test_primary_path_is_repo_relative_and_present():
    assert vision.PRIMARY_MODEL_PATH == REPO_CKPT.absolute() or \
        str(vision.PRIMARY_MODEL_PATH).endswith("models/v2/food_classifier_indian_80_224.pt")
    assert "/home/user/nutricare_exp" not in str(vision.PRIMARY_MODEL_PATH)
    assert vision.PRIMARY_MODEL_PATH.is_file()
    assert vision.PRIMARY_MODEL_PATH != vision.DEFAULT_MODEL_PATH
    assert vision.EXPERIMENTAL_MODEL_PATH == vision.PRIMARY_MODEL_PATH


def test_primary_path_accepts_new_and_legacy_environment_overrides(tmp_path):
    target = tmp_path / "elsewhere.pt"
    for variable in ("NUTRICARE_PRIMARY_MODEL", "NUTRICARE_EXPERIMENTAL_MODEL"):
        env = dict(os.environ, **{variable: str(target)})
        output = subprocess.run(
            [sys.executable, "-c",
             "from nutricare import vision; print(vision.PRIMARY_MODEL_PATH)"],
            capture_output=True, text=True, env=env, check=True,
        )
        assert output.stdout.strip() == str(target)


def test_available_models_describe_fixed_roles_not_a_selector():
    models = {model["name"]: model for model in vision.get_available_models()}
    primary = models[vision.PRIMARY_MODEL_NAME]
    fallback = models[vision.FALLBACK_MODEL_NAME]
    assert primary["role"] == "primary"
    assert primary["classes"] == 80
    assert primary["present"] is True
    assert fallback["role"] == "technical_fallback"
    assert fallback["classes"] == 12
    assert fallback["present"] is True
    assert all(model["selection_allowed"] is False for model in models.values())


def test_missing_primary_checkpoint_is_reported_without_loading(tmp_path, monkeypatch):
    monkeypatch.setattr(vision, "PRIMARY_MODEL_PATH", tmp_path / "absent.pt")
    vision.reset_predictor()

    status = vision.model_status("primary")

    assert status["model_present"] is False
    assert status["loaded"] is False
    with pytest.raises(vision.ModelUnavailable):
        vision.get_primary_predictor().predict(make_png())


def test_unreadable_primary_checkpoint_raises_at_load(tmp_path, monkeypatch):
    pytest.importorskip("torch")
    bad = tmp_path / "corrupt.pt"
    bad.write_bytes(b"this is not a checkpoint")
    monkeypatch.setattr(vision, "PRIMARY_MODEL_PATH", bad)
    vision.reset_predictor()

    with pytest.raises(vision.ModelUnavailable):
        vision.get_primary_predictor().predict(make_png())


def test_primary_checkpoint_loads_strictly_with_80_classes():
    pytest.importorskip("torch")
    predictor = vision.get_primary_predictor()
    predictor._load()
    assert predictor._model is not None
    assert len(predictor._classes) == 80
    assert predictor._meta.get("input_size") == 224


def test_legacy_default_helper_remains_12_class_for_non_scan_callers():
    """The old helper remains available; /predict does not use it."""
    legacy = vision.get_predictor()
    primary = vision.get_primary_predictor()
    assert legacy is vision.get_fallback_predictor()
    assert legacy is not primary
    assert legacy.model_path == vision.configured_fallback_model_path()
    assert primary.model_path == vision.PRIMARY_MODEL_PATH


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "api.db"))
    app = create_app({"TESTING": True})
    client = app.test_client()
    assert client.post("/api/users", json={"name": "API Tester"}).status_code == 201
    return client


def test_status_reports_primary_fallback_policy(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/vision/status")

    assert response.status_code == 200
    body = response.get_json()
    assert body["primary"]["classes"] == 80
    assert body["fallback"]["classes"] == 12
    assert body["policy"]["primary_model"] == vision.PRIMARY_MODEL_NAME
    assert body["policy"]["low_confidence_triggers_fallback"] is False
    assert body["policy"]["prediction_unconfirmed"] is True
    assert client.get("/api/vision/status?model=experimental").status_code == 400


def test_legacy_selection_endpoint_is_gone(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post("/api/vision/select-model", json={"model": "experimental"})

    assert response.status_code == 410
    body = response.get_json()
    assert body["deprecated"] is True
    assert body["policy"]["technical_fallback_model"] == vision.FALLBACK_MODEL_NAME
