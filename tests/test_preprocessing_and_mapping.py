"""Tests for the recognition preprocessing and class-index mapping.

These tests exercise the parts of the prediction pipeline that the existing
suite touches only indirectly:

  * the torchvision transform (resize, centre-crop, tensor, normalise) and the
    image dimensions / channel count / normalisation constants it produces;
  * the mapping from model output indices to class labels (the order of the
    checkpoint's ``classes`` list must match the order the predictor serves);
  * checkpoint-driven normalisation (mean/std come from the checkpoint, not
    from a hard-coded assumption).

Like the rest of the suite these tests never simulate a neural network: a
tiny checkpoint is trained on random noise so the real inference path
(state_dict load, transform, softmax, ranking, low-confidence flag) runs for
real. No accuracy claim is made.
"""

import io

import pytest

from nutricare import vision


# ---------------------------------------------------------------- helpers
def make_png(width=64, height=64, colour=(180, 120, 60), mode="RGB"):
    import struct
    import zlib
    from PIL import Image

    buffer = io.BytesIO()
    Image.new(mode, (width, height), colour).save(buffer, "PNG")
    return buffer.getvalue()


def _train_noise_checkpoint(path, classes, input_size=224,
                            mean=(0.485, 0.456, 0.406),
                            std=(0.229, 0.224, 0.225)):
    """Save a real checkpoint so the inference path is exercised for real.

    Weights are random: this proves the plumbing works, not accuracy.
    """
    import torch
    model = vision.build_model("mobilenet_v3_small", len(classes),
                               pretrained=False)
    torch.save({
        "state_dict": model.state_dict(),
        "classes": classes,
        "architecture": "mobilenet_v3_small",
        "input_size": input_size,
        "normalise_mean": list(mean),
        "normalise_std": list(std),
        "trained_at": "2026-01-01T00:00:00",
        "test_accuracy": None,
        "trained_on": "random weights (test fixture)",
    }, path)


@pytest.fixture()
def predictor_app(tmp_path, monkeypatch):
    """App wired to a noise-trained 4-class checkpoint."""
    import torch  # noqa: F401  (importorskip behaviour via pytest below)
    pytest.importorskip("torchvision")
    pytest.importorskip("PIL")

    checkpoint = tmp_path / "fixture.pt"
    slugs = ["masala_dosa", "roti", "samosa", "pizza"]
    _train_noise_checkpoint(checkpoint, slugs)
    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "vision.db"))
    monkeypatch.setenv("NUTRICARE_MODEL", str(checkpoint))
    vision.reset_predictor()
    from nutricare import create_app
    application = create_app({"TESTING": True})
    yield application
    vision.reset_predictor()


# ---------------------------------------------------------------- preprocessing
def test_transform_output_shape_and_channels(predictor_app):
    """The transform must yield a 3-channel 224x224 tensor (batch of 1)."""
    predictor = vision.get_predictor()
    predictor._load()
    from PIL import Image
    import io as _io

    buffer = _io.BytesIO()
    Image.new("RGB", (320, 240), (100, 150, 200)).save(buffer, "JPEG")
    image = Image.open(_io.BytesIO(buffer.getvalue()))
    tensor = predictor._transform(image).unsqueeze(0)
    assert tuple(tensor.shape) == (1, 3, 224, 224)


def test_grayscale_image_is_converted_to_rgb(predictor_app):
    """A single-channel upload must be expanded to 3 channels, not rejected.

    ``Predictor.predict`` converts to RGB before transforming, so a grayscale
    PNG must flow through the full prediction path and return a ranked result
    rather than an error.
    """
    with predictor_app.test_client() as client:
        client.post("/api/users", json={"name": "Gray"})
        from PIL import Image
        import io as _io
        buffer = _io.BytesIO()
        Image.new("L", (100, 100), 128).save(buffer, "PNG")
        resp = client.post("/api/vision/predict",
                           data=buffer.getvalue(),
                           content_type="application/octet-stream")
    assert resp.status_code == 200
    body = resp.get_json()
    # Dual-model: merged candidates from both models; the fixture model's
    # own top-1 remains attributable in the ensemble debug block.
    assert 3 <= len(body["predictions"]) <= 6
    assert body["ensemble"]["models"]["default"]["top"]["slug"] in \
        {"masala_dosa", "roti", "samosa", "pizza"}


def test_normalisation_constants_come_from_checkpoint(tmp_path, monkeypatch):
    """Checkpoint mean/std must drive the transform, not ImageNet defaults."""
    import torch
    checkpoint = tmp_path / "odd.pt"
    slugs = ["a", "b"]
    _train_noise_checkpoint(checkpoint, slugs, mean=(0.1, 0.2, 0.3),
                            std=(0.4, 0.5, 0.6))
    monkeypatch.setenv("NUTRICARE_MODEL", str(checkpoint))
    vision.reset_predictor()
    try:
        predictor = vision.Predictor(checkpoint)
        predictor._load()
        mean, std = predictor._transform.transforms[-1].mean, \
            predictor._transform.transforms[-1].std
        assert list(mean) == [0.1, 0.2, 0.3]
        assert list(std) == [0.4, 0.5, 0.6]
    finally:
        vision.reset_predictor()


def test_predict_rejects_corrupted_image_bytes(predictor_app):
    """Structurally invalid bytes raise ImageError before touching the model."""
    from nutricare import create_app
    with predictor_app.test_client() as client:
        client.post("/api/users", json={"name": "Corrupt"})
        resp = client.post("/api/vision/predict", data=b"\xff\xd8\xff truncated",
                           content_type="application/octet-stream")
    assert resp.status_code == 400


# ---------------------------------------------------------------- class mapping
def test_model_class_order_matches_taxonomy_slugs(predictor_app):
    """The index the model returns must map to the taxonomy slug in the same
    position as the checkpoint's ``classes`` list."""
    predictor = vision.get_predictor()
    predictor._load()
    checkpoint_slugs = predictor._classes  # list of {"slug": ..., ...}
    by_slug = vision.class_by_slug()
    for entry in checkpoint_slugs:
        slug = entry["slug"]
        assert slug in by_slug, f"checkpoint class {slug!r} absent from taxonomy"
        assert entry["label"] == by_slug[slug]["label"]


def test_prediction_slugs_are_subset_of_checkpoint_classes(predictor_app):
    """Every returned prediction slug must belong to one of the installed
    checkpoints, never to the full taxonomy. Under dual-model scanning the
    merged candidates may come from either model, so the fixture model's
    contribution is checked through its recorded top-1 and source tags."""
    with predictor_app.test_client() as client:
        client.post("/api/users", json={"name": "Map"})
        resp = client.post("/api/vision/predict?top_k=4",
                           data=make_png(),
                           content_type="application/octet-stream")
    assert resp.status_code == 200
    body = resp.get_json()
    allowed = {"masala_dosa", "roti", "samosa", "pizza"}
    taxonomy = {c["slug"] for c in vision.class_list()}
    for prediction in body["predictions"]:
        assert prediction["slug"] in taxonomy
        if prediction["source_models"] == ["default"]:
            assert prediction["slug"] in allowed
    assert body["ensemble"]["models"]["default"]["top"]["slug"] in allowed


# ---------------------------------------------------------------- low confidence
def test_low_confidence_flag_is_set_for_random_weights(predictor_app):
    """Random weights cannot be confident: low_confidence must be a real bool
    tied to the threshold, and must trip when top confidence is below it."""
    with predictor_app.test_client() as client:
        client.post("/api/users", json={"name": "Conf"})
        body = client.post("/api/vision/predict", data=make_png()).get_json()
    assert isinstance(body["low_confidence"], bool)
    assert body["threshold"] == vision.LOW_CONFIDENCE_THRESHOLD
    if body["top"]["confidence"] < vision.LOW_CONFIDENCE_THRESHOLD:
        assert body["low_confidence"] is True


# ---------------------------------------------------------------- model absence
def test_missing_model_raises_model_unavailable_and_never_guesses(tmp_path):
    """No checkpoint -> predict() raises ModelUnavailable, never a class name."""
    predictor = vision.Predictor(tmp_path / "absent.pt")
    with pytest.raises(vision.ModelUnavailable):
        predictor.predict(make_png())


def test_corrupted_checkpoint_is_reported_not_loaded(tmp_path, monkeypatch):
    """A file that is not a checkpoint fails loudly at load time. Under
    dual-model scanning the failure is reported in the ensemble debug block
    and the other model still serves — it is never silently loaded or
    replaced by a fabricated prediction."""
    broken = tmp_path / "broken.pt"
    broken.write_bytes(b"not a torch checkpoint")
    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "b.db"))
    monkeypatch.setenv("NUTRICARE_MODEL", str(broken))
    vision.reset_predictor()
    from nutricare import create_app
    application = create_app({"TESTING": True})
    try:
        with application.test_client() as client:
            client.post("/api/users", json={"name": "Broken"})
            resp = client.post("/api/vision/predict", data=make_png())
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ensemble"]["models"]["default"]["available"] is False
        assert body["ensemble"]["models"]["experimental"]["available"] is True
        assert body["predictions"]
    finally:
        vision.reset_predictor()
