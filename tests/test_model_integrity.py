"""Byte-integrity regression tests for shipped NutriCare checkpoint artifacts.

Recognition-policy changes must never retrain, rewrite, replace, or otherwise
mutate any shipped model checkpoint. These hashes are intentionally checked
without importing torch so the guard runs in the base test environment too.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest


EXPECTED_SHA256 = {
    Path("models/food_classifier_cc0.pt"):
        "f74d10f6efe6a7848870b16388d56a570086901afa11d6ed78e7cd914f02ad87",
    Path("models/food_classifier_cc0_7class.pt"):
        "c5a1a2bb94b2213609e0dbf3a6b6f27cf09dc13c2bd2d06116d4a03226417319",
    Path("models/v2/food_classifier_indian_80_224.pt"):
        "b1e8187d45ad8f8cf6676c86350c08c8a231422d36cab71e152abba772b87068",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@pytest.mark.parametrize("path, expected", EXPECTED_SHA256.items())
def test_shipped_checkpoint_hash_is_unchanged(path: Path, expected: str):
    assert path.is_file(), f"Required shipped checkpoint is missing: {path}"
    assert sha256(path) == expected
