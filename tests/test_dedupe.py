"""Tests for the pre-split de-duplication pass.

Background: the first shipped model was de-duplicated only *inside*
`split_dataset`, and only on MD5 + filename stem. Consecutive photographs of the
same plate survive both checks — different bytes, different names — so a
near-duplicate could sit in train and its twin in test. Measured on the 7-class
CC0 model, that inflated test accuracy by roughly +0.007.

`dedupe_global` therefore runs over the whole dataset before any split exists.
These tests pin the behaviour that matters: the collapse happens, it happens
across classes, and the order of the input does not change the outcome.
"""

import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from training.train_food_classifier import dedupe_global, split_dataset  # noqa: E402

pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


def make_image(path: Path, seed: int, size=(96, 96), jpeg_quality=90):
    """A deterministic image with pseudo-random *structure*.

    dHash compares neighbouring pixels, so it sees structure rather than colour.
    A smooth gradient would hash identically for every seed and make these tests
    meaningless — so the content is seeded noise, upsampled to give coarse
    blocks that survive JPEG re-encoding while still differing between seeds.
    """
    import random

    rng = random.Random(seed)
    coarse = Image.new("L", (12, 12))
    coarse.putdata([rng.randrange(256) for _ in range(12 * 12)])
    img = coarse.resize(size, Image.NEAREST).convert("RGB")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=jpeg_quality)
    return path


def test_exact_duplicates_are_collapsed(tmp_path):
    a = make_image(tmp_path / "roti" / "001.jpg", seed=3)
    # Same bytes, different name.
    b = tmp_path / "roti" / "copy_of_001.jpg"
    b.write_bytes(a.read_bytes())

    kept, stats = dedupe_global({"roti": [a, b]}, verbose=False)
    assert len(kept["roti"]) == 1
    assert stats["dropped_exact"] == 1


def test_reencoded_near_duplicate_is_caught(tmp_path):
    """Same photograph, different JPEG quality => different MD5, near-identical
    pixels. This is the exact leak the old trainer could not see."""
    original = make_image(tmp_path / "khichdi" / "001.jpg", seed=5, jpeg_quality=95)
    reencoded = tmp_path / "khichdi" / "001_reencoded.jpg"
    Image.open(original).save(reencoded, "JPEG", quality=55)

    assert original.read_bytes() != reencoded.read_bytes()   # md5 differs

    kept, stats = dedupe_global({"khichdi": [original, reencoded]}, verbose=False)
    assert len(kept["khichdi"]) == 1
    assert stats["dropped_near"] == 1


def test_near_duplicate_spanning_two_classes_is_dropped_once(tmp_path):
    """One photograph filed under two labels teaches the model nothing about
    the difference between them. It must survive in exactly one class."""
    common = make_image(tmp_path / "kheer" / "001.jpg", seed=9)
    other = tmp_path / "rasgulla" / "001.jpg"
    other.parent.mkdir(parents=True, exist_ok=True)
    Image.open(common).save(other, "JPEG", quality=70)
    distinct = make_image(tmp_path / "rasgulla" / "002.jpg", seed=17)

    kept, stats = dedupe_global({"kheer": [common], "rasgulla": [other, distinct]},
                                verbose=False)
    total = len(kept["kheer"]) + len(kept["rasgulla"])
    assert total == 2, "the cross-class pair must collapse to one image"
    assert stats["dropped_cross_class"] == 1


def test_distinct_images_are_all_kept(tmp_path):
    classes = {}
    for offset, slug in enumerate(("roti", "idli", "jalebi")):
        # Distinct seed ranges per class: reusing the same seeds would create
        # genuinely identical images across classes, which the pass *should*
        # collapse.
        classes[slug] = [make_image(tmp_path / slug / f"{i}.jpg",
                                    seed=offset * 100 + i + 2) for i in range(4)]
    kept, stats = dedupe_global(classes, verbose=False)
    assert sum(len(v) for v in kept.values()) == 12
    assert stats["dropped_exact"] == stats["dropped_near"] == 0


def test_unreadable_file_is_reported_not_silently_kept(tmp_path):
    bad = tmp_path / "roti" / "broken.jpg"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"this is not an image")
    good = make_image(tmp_path / "roti" / "ok.jpg", seed=4)

    kept, stats = dedupe_global({"roti": [bad, good]}, verbose=False)
    assert len(kept["roti"]) == 1
    assert stats["dropped_unreadable"] == 1


def test_dedupe_is_independent_of_class_iteration_order(tmp_path):
    """A survivor choice that depended on dict ordering would make the split
    non-reproducible between runs."""
    files = {}
    for slug in ("kheer", "rasgulla"):
        files[slug] = [make_image(tmp_path / slug / f"{i}.jpg", seed=i + 2)
                       for i in range(3)]
    twin = tmp_path / "rasgulla" / "twin.jpg"
    Image.open(files["kheer"][0]).save(twin, "JPEG", quality=60)
    files["rasgulla"].append(twin)

    first, _ = dedupe_global({"kheer": files["kheer"],
                              "rasgulla": files["rasgulla"]}, verbose=False)
    reversed_order, _ = dedupe_global({"rasgulla": files["rasgulla"],
                                       "kheer": files["kheer"]}, verbose=False)
    assert ({k: sorted(p.name for p in v) for k, v in first.items()}
            == {k: sorted(p.name for p in v) for k, v in reversed_order.items()})


def test_split_after_dedupe_has_disjoint_hashes(tmp_path):
    """End-to-end guarantee: after the global pass, no test image has an
    MD5-identical twin in train."""
    import hashlib
    classes = {"roti": [make_image(tmp_path / "roti" / f"{i}.jpg", seed=i + 2)
                        for i in range(10)],
               "idli": [make_image(tmp_path / "idli" / f"{i}.jpg", seed=i + 300)
                        for i in range(10)]}
    deduped, _ = dedupe_global(classes, verbose=False)
    splits = split_dataset(deduped, 0.2, 0.2, seed=42)

    train = {hashlib.md5(p.read_bytes()).hexdigest() for p, _ in splits["train"]}
    test = {hashlib.md5(p.read_bytes()).hexdigest() for p, _ in splits["test"]}
    assert train and test
    assert not (train & test)
