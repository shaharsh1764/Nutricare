"""The scanner must refuse images that cannot plausibly contain a dish.

Motivation, measured on this repository's own model: softmax confidence cannot
detect "this is not food". A plain white image scored 89.9% "Lassi", a solid
grey one 81.0%, and a smooth blue gradient 86.2%. A confidence gate alone
therefore serves confident nonsense for exactly the images a user is most
likely to send by accident (a blank frame, a wall, a mis-tap).

`vision.mean_gradient` measures how much local structure an image has, and
`MIN_IMAGE_TEXTURE` refuses anything below it before a forward pass runs.
These tests pin both the measurement and the refusal, and — equally important
— that ordinary photographs are NOT refused.
"""
from __future__ import annotations

import io
import struct
import zlib

import pytest

from nutricare import vision


def png_from(image):
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def flat(colour, size=(224, 224)):
    from PIL import Image
    return Image.new("RGB", size, colour)


def checker(size=(224, 224), block=16, a=(255, 255, 255), b=(0, 0, 0)):
    from PIL import Image, ImageDraw
    image = Image.new("RGB", size, a)
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], block):
        for x in range(0, size[0], block):
            if ((x // block) + (y // block)) % 2:
                draw.rectangle([x, y, x + block - 1, y + block - 1], fill=b)
    return image


def vertical_gradient(size=(224, 224)):
    from PIL import Image, ImageDraw
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    for y in range(size[1]):
        t = y / (size[1] - 1)
        draw.line([(0, y), (size[0], y)],
                  fill=(int(120 + 135 * t), int(160 + 95 * t), int(220 + 35 * t)))
    return image


# --------------------------------------------------------------- the measure

def test_flat_colour_has_no_texture():
    for colour in [(0, 0, 0), (128, 128, 128), (255, 255, 255), (243, 232, 214)]:
        assert vision.mean_gradient(flat(colour)) == pytest.approx(0.0, abs=0.01)


def test_smooth_gradient_is_near_zero_texture():
    """A wall/sky gradient has almost no local detail, despite varying colour."""
    assert vision.mean_gradient(vertical_gradient()) < 0.5


def test_structured_images_exceed_the_threshold():
    assert vision.mean_gradient(checker()) > vision.MIN_IMAGE_TEXTURE


def test_threshold_sits_below_real_photographs():
    """Guard the number: real photos in this repo score ~8-10, far above 2.0."""
    assert vision.MIN_IMAGE_TEXTURE == 2.0


# --------------------------------------------------------------- the refusal

def test_blank_image_is_refused_as_not_usable(tmp_path, monkeypatch):
    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "u.db"))
    from nutricare import create_app
    app = create_app()

    with app.test_client() as client:
        client.post("/api/users", json={"name": "Blank"})
        response = client.post("/api/vision/predict",
                               data=png_from(flat((255, 255, 255))),
                               content_type="application/octet-stream")

    assert response.status_code == 422
    body = response.get_json()
    assert body["code"] == "image_not_usable"
    # The point of the fix: no label is ever offered for a blank frame.
    assert "predictions" not in body
    assert "top" not in body
    assert "candidates" not in body
    assert "recognisable" in body["error"] or "photo" in body["error"]


def test_blank_image_is_refused_before_any_prediction():
    """The decisive regression: blank white used to score 89.9% 'Lassi'.

    Whatever the classifier would have said, a no-texture image must be
    refused, and it must be refused *before* the network runs — the forward
    pass is never reached, so no label can be produced.
    """
    image = flat((255, 255, 255))
    assert vision.mean_gradient(image) < vision.MIN_IMAGE_TEXTURE

    predictor = vision.Predictor.__new__(vision.Predictor)
    predictor._load = lambda: None
    predictor._transform = lambda _img: pytest.fail("no forward pass for a blank image")
    with pytest.raises(vision.ImageNotUsable):
        predictor.predict(png_from(image))


def test_a_broken_deployment_is_not_blamed_on_the_photo(tmp_path, monkeypatch):
    """Missing/corrupt checkpoint must report as a model fault, not bad input.

    The usability gate runs on decoded pixels, but checkpoint loading comes
    first: telling a user their photo has "nothing recognisable" when the model
    is simply absent would hide a deployment error behind an accusation.
    """
    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "m.db"))
    monkeypatch.setattr(vision, "PRIMARY_MODEL_PATH", tmp_path / "absent.pt")
    monkeypatch.setenv("NUTRICARE_MODEL", str(tmp_path / "absent-fallback.pt"))
    # The predictor is a process-wide singleton: whatever this test does to it
    # must be undone, or later tests inherit a "no checkpoint" world.
    vision.reset_predictor()
    try:
        from nutricare import create_app
        app = create_app()

        with app.test_client() as client:
            client.post("/api/users", json={"name": "Broken"})
            response = client.post("/api/vision/predict",
                                   data=png_from(flat((255, 255, 255))),
                                   content_type="application/octet-stream")
    finally:
        vision.reset_predictor()

    body = response.get_json()
    assert body.get("code") != "image_not_usable"
    assert response.status_code == 503
    assert body.get("model_unavailable") is True


def test_image_not_usable_is_an_image_error():
    """Callers that already handle bad uploads keep working unchanged."""
    assert issubclass(vision.ImageNotUsable, vision.ImageError)
    exc = vision.ImageNotUsable(0.4)
    assert exc.texture == 0.4
    assert "recognis" in str(exc).lower() or "photo" in str(exc).lower()


def test_structured_image_passes_the_gate(tmp_path, monkeypatch):
    """A textured frame must reach the model (and then be judged on confidence).

    Uses the abstention code, not image_not_usable, as the distinguishing mark.
    """
    monkeypatch.setenv("NUTRICARE_DB", str(tmp_path / "s.db"))
    from nutricare import create_app
    app = create_app()

    with app.test_client() as client:
        client.post("/api/users", json={"name": "Structured"})
        response = client.post("/api/vision/predict",
                               data=png_from(checker()),
                               content_type="application/octet-stream")

    body = response.get_json()
    assert body.get("code") != "image_not_usable"
