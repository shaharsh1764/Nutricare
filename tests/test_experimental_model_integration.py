"""Integration tests for the experimental 80-class model wiring.

Covers: repository-relative checkpoint location, env override, graceful
missing/invalid checkpoint handling, strict loading with 80 outputs,
default-vs-experimental switching, and the API surface. The 12-class
production model must remain the default throughout.
"""
import struct
import zlib
from pathlib import Path

import pytest

from nutricare import vision

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
def _reset():
    vision.reset_predictor()
    yield
    vision.reset_predictor()


# ---------------------------------------------------------------- paths
def test_experimental_path_is_repo_relative_and_present():
    assert vision.EXPERIMENTAL_MODEL_PATH == REPO_CKPT.absolute() or \
        str(vision.EXPERIMENTAL_MODEL_PATH).endswith("models/v2/food_classifier_indian_80_224.pt")
    assert "/home/user/nutricare_exp" not in str(vision.EXPERIMENTAL_MODEL_PATH)
    assert vision.EXPERIMENTAL_MODEL_PATH.is_file()
    assert vision.EXPERIMENTAL_MODEL_PATH != vision.DEFAULT_MODEL_PATH


def test_experimental_path_env_override(tmp_path):
    """Env override is honoured at import time (checked in a subprocess so no
    module reload can disturb other tests' class identities)."""
    import os
    import subprocess
    import sys
    target = tmp_path / "elsewhere.pt"
    env = dict(os.environ, NUTRICARE_EXPERIMENTAL_MODEL=str(target))
    out = subprocess.run(
        [sys.executable, "-c",
         "from nutricare import vision; print(vision.EXPERIMENTAL_MODEL_PATH)"],
        capture_output=True, text=True, env=env, check=True)
    assert out.stdout.strip() == str(target)


def test_default_path_unchanged():
    assert vision.DEFAULT_MODEL_PATH.name == "food_classifier_cc0.pt"
    models = {m["name"]: m for m in vision.get_available_models()}
    assert models["default"]["present"] is True
    assert models["default"]["experimental"] is False
    assert models["experimental"]["experimental"] is True
    assert models["experimental"]["present"] is True


# ------------------------------------------------------- missing / invalid
def test_missing_experimental_checkpoint_handled_gracefully(tmp_path, monkeypatch):
    monkeypatch.setattr(vision, "EXPERIMENTAL_MODEL_PATH", tmp_path / "absent.pt")
    vision.reset_predictor()
    models = {m["name"]: m for m in vision.get_available_models()}
    assert models["experimental"]["present"] is False
    status = vision.model_status("experimental")  # must NOT raise
    assert status["model_present"] is False
    with pytest.raises(vision.ModelUnavailable):
        vision.get_predictor("experimental").predict(make_png())


def test_invalid_experimental_checkpoint_handled_gracefully(tmp_path, monkeypatch):
    pytest.importorskip("torch")
    bad = tmp_path / "corrupt.pt"
    bad.write_bytes(b"this is not a checkpoint")
    monkeypatch.setattr(vision, "EXPERIMENTAL_MODEL_PATH", bad)
    vision.reset_predictor()
    models = {m["name"]: m for m in vision.get_available_models()}
    assert models["experimental"]["present"] is True  # file exists...
    with pytest.raises(vision.ModelUnavailable):      # ...but never fakes a prediction
        vision.get_predictor("experimental").predict(make_png())


# ------------------------------------------------------------- strict load
def test_experimental_checkpoint_loads_strictly_with_80_classes():
    pytest.importorskip("torch")
    predictor = vision.Predictor(REPO_CKPT)
    predictor._load()
    assert predictor._model is not None
    assert len(predictor._classes) == 80
    assert predictor._meta.get("input_size") == 224


def test_default_predictor_is_12_class():
    pytest.importorskip("torch")
    predictor = vision.get_predictor()
    result = predictor.predict(make_png())
    slugs = {p["slug"] for p in result["predictions"]}
    assert slugs  # produced predictions from the 12-class default
    status = vision.model_status()
    assert "food_classifier_cc0" in status["model_path"]


def test_switching_between_models():
    pytest.importorskip("torch")
    default = vision.get_predictor("default")
    experimental = vision.get_predictor("experimental")
    assert default is not experimental
    assert default.model_path != experimental.model_path
    result = experimental.predict(make_png())
    assert result["predictions"]
    assert vision.get_predictor() is default  # no-arg still default


# -------------------------------------------------------------------- API
def _client(tmp_path, monkeypatch):
    from nutricare import create_app
    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "api.db"))
    vision.reset_predictor()
    app = create_app({"TESTING": True})
    client = app.test_client()
    assert client.post("/api/users", json={"name": "API Tester"}).status_code == 201
    return client


def test_api_status_for_both_models(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.get("/api/vision/status")
    assert r.status_code == 200
    assert "food_classifier_cc0" in r.get_json()["model"]["model_path"]
    r = client.get("/api/vision/status?model=experimental")
    assert r.status_code == 200
    assert "food_classifier_indian_80_224" in r.get_json()["model"]["model_path"]
    assert client.get("/api/vision/status?model=bogus").status_code == 400


def test_api_status_experimental_missing_is_graceful(tmp_path, monkeypatch):
    monkeypatch.setattr(vision, "EXPERIMENTAL_MODEL_PATH", tmp_path / "absent.pt")
    client = _client(tmp_path, monkeypatch)
    r = client.get("/api/vision/status?model=experimental")
    assert r.status_code == 200  # previously raised -> 500
    assert r.get_json()["model"]["model_present"] is False
    assert client.post("/api/vision/select-model",
                       json={"model": "experimental"}).status_code == 400
    r = client.post("/api/vision/predict?model=experimental",
                    data=make_png(), content_type="application/octet-stream")
    # Dual-model: missing experimental checkpoint -> production still answers.
    assert r.status_code == 200
    body = r.get_json()
    assert body["model"] == "dual"
    assert body["ensemble"]["models"]["experimental"]["available"] is False
    assert body["ensemble"]["models"]["default"]["available"] is True


def test_api_prediction_runs_both_models(tmp_path, monkeypatch):
    """Dual-model scanning replaced manual selection: the legacy ?model=
    parameter is ignored and BOTH checkpoints evaluate every scan."""
    pytest.importorskip("torch")
    client = _client(tmp_path, monkeypatch)
    r = client.post("/api/vision/predict?model=experimental&top_k=3",
                    data=make_png(), content_type="application/octet-stream")
    assert r.status_code == 200
    body = r.get_json()
    assert body["model"] == "dual"
    assert body["predictions"]
    assert body["ensemble"]["models"]["default"]["available"] is True
    assert body["ensemble"]["models"]["experimental"]["available"] is True
    r = client.post("/api/vision/predict?top_k=3",
                    data=make_png(), content_type="application/octet-stream")
    assert r.status_code == 200
    assert r.get_json()["model"] == "dual"  # no silent single-model switch


def test_api_models_endpoint_reports_session_selection(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.get("/api/vision/models").get_json()["selected"] == "default"
    assert client.post("/api/vision/select-model",
                       json={"model": "experimental"}).status_code == 200
    assert client.get("/api/vision/models").get_json()["selected"] == "experimental"
    assert client.post("/api/vision/select-model",
                       json={"model": "default"}).status_code == 200
    assert client.get("/api/vision/models").get_json()["selected"] == "default"
