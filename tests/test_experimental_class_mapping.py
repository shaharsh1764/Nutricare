"""Output-index -> slug -> label mapping verification for the 80-class model.

The mapping is proven from artifacts, not assumed:
  training order  = checkpoint["classes"] (written by the trainer)
  training record = models/v2/*.metrics.json "class_names" (must match)
  inference order = Predictor._classes, built strictly from checkpoint order
                    (vision.Predictor._load); the 137-entry taxonomy only
                    supplies label/group per slug, never ordering.
"""
import json
import struct
import zlib
from pathlib import Path

import pytest

from nutricare import vision

CKPT = Path("models/v2/food_classifier_indian_80_224.pt")
METRICS = Path("models/v2/food_classifier_indian_80_224.metrics.json")
TAXONOMY = Path("data/food_classes.json")


def make_png(width=64, height=64, colour=(180, 120, 60)):
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + bytes(colour) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def _checkpoint_classes():
    torch = pytest.importorskip("torch")
    ck = torch.load(CKPT, map_location="cpu", weights_only=False)
    return ck["classes"]


def _taxonomy():
    return {c["slug"]: c for c in json.loads(TAXONOMY.read_text())["classes"]}


def test_training_order_source_is_consistent():
    classes = _checkpoint_classes()
    metrics = json.loads(METRICS.read_text())
    assert classes == metrics["class_names"]      # training record matches checkpoint
    assert classes == sorted(classes)             # trainer scanned class folders alphabetically
    assert len(classes) == 80 and len(set(classes)) == 80


def test_every_output_index_maps_to_a_taxonomy_entry():
    classes = _checkpoint_classes()
    taxonomy = _taxonomy()
    for index, slug in enumerate(classes):
        assert slug in taxonomy, f"output index {index} ({slug}) has no taxonomy entry"
        entry = taxonomy[slug]
        assert entry["label"], f"index {index} ({slug}) has an empty display label"
    labels = [taxonomy[s]["label"] for s in classes]
    assert len(set(labels)) == 80                 # no duplicate display names among the 80


def test_representative_output_indices():
    classes = _checkpoint_classes()
    taxonomy = _taxonomy()
    # alphabetical training order, verified against the artifacts above
    assert classes[0] == "adhirasam"
    assert classes[79] == "unni_appam"
    for slug in ("gulab_jamun", "biryani", "chicken_tikka_masala", "rabri"):
        entry = taxonomy[slug]
        assert classes[classes.index(slug)] == slug
        assert entry["label"] and entry["label"] != slug or slug in entry["label"].lower()


def test_inference_order_is_checkpoint_order_not_taxonomy_order():
    pytest.importorskip("torch")
    predictor = vision.Predictor(CKPT)
    predictor._load()
    inferred = [c["slug"] for c in predictor._classes]
    assert inferred == _checkpoint_classes()
    taxonomy_order = [c["slug"] for c in json.loads(TAXONOMY.read_text())["classes"]]
    assert inferred != taxonomy_order             # taxonomy (137) never drives ordering
    # labels attached at inference come from the taxonomy entry for the same slug
    taxonomy = _taxonomy()
    for cls in predictor._classes:
        assert cls["label"] == taxonomy[cls["slug"]]["label"]


def test_predictions_use_only_the_80_checkpoint_slugs():
    pytest.importorskip("torch")
    predictor = vision.Predictor(CKPT)
    result = predictor.predict(make_png(), top_k=5)
    allowed = set(_checkpoint_classes())
    assert result["predictions"]
    assert {p["slug"] for p in result["predictions"]} <= allowed


def test_no_cross_contamination_with_12_class_ordering():
    pytest.importorskip("torch")
    experimental = vision.Predictor(CKPT)
    experimental._load()
    default = vision.Predictor(vision.DEFAULT_MODEL_PATH)
    default._load()
    assert len(experimental._classes) == 80
    assert len(default._classes) == 12
    assert [c["slug"] for c in experimental._classes] != [c["slug"] for c in default._classes]
    result = default.predict(make_png(), top_k=3)
    assert {p["slug"] for p in result["predictions"]} <= {c["slug"] for c in default._classes}


def test_nutrition_lookup_is_keyed_by_checkpoint_slug(tmp_path, monkeypatch):
    """End-to-end: experimental predictions carry nutrition info resolved via
    the predicted slug (or an honest unavailable marker), never via an index
    into some other class list."""
    pytest.importorskip("torch")
    from nutricare import create_app
    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "mapping.db"))
    vision.reset_predictor()
    app = create_app({"TESTING": True})
    with app.test_client() as client:
        assert client.post("/api/users", json={"name": "Mapping Tester"}).status_code == 201
        resp = client.post("/api/vision/predict?top_k=5",
                           data=make_png(), content_type="application/octet-stream")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["model"] == vision.PRIMARY_MODEL_NAME
        assert body["recognition"]["fallback_used"] is False
        allowed = set(_checkpoint_classes())
        for candidate in body["candidates"]:
            assert "nutrition" in candidate
            assert "nutrition_available" in candidate["nutrition"]
            # The primary output is keyed by its checkpoint slug, never a
            # position in NutriCare's broader taxonomy.
            assert candidate["slug"] in allowed
    vision.reset_predictor()


def test_status_reports_checkpoint_output_count_before_load():
    exp = vision.Predictor(vision.EXPERIMENTAL_MODEL_PATH)
    assert exp._model is None                       # not loaded yet
    assert exp.status()["classes"] == 80            # not the 137-entry taxonomy
    default = vision.Predictor(vision.DEFAULT_MODEL_PATH)
    assert default.status()["classes"] == 12


def test_status_count_does_not_depend_on_sidecar(tmp_path):
    pytest.importorskip("torch")
    import shutil
    lonely = tmp_path / "lonely.pt"
    shutil.copy(CKPT, lonely)                       # checkpoint with NO metrics sidecar
    predictor = vision.Predictor(lonely)
    assert predictor.status()["classes"] == 80


def test_status_missing_checkpoint_reports_unknown_count(tmp_path):
    predictor = vision.Predictor(tmp_path / "absent.pt")
    status = predictor.status()                     # must not raise
    assert status["model_present"] is False
    assert status["classes"] is None                # honest unknown, not 137
