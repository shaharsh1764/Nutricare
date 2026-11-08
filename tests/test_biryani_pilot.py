"""Tests for the Biryani pilot manifest builder.

These validate the *processing* of the real Commons transcriptions: dedupe
semantics, multi-category preservation, licence classification, and the
guarantees that nothing is marked usable or training-ready.

No network access and no image bytes are involved.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training.build_biryani_pilot import (  # noqa: E402
    CLASS_SLUG,
    TAXONOMY_CATEGORIES,
    analyse,
    build_manifest,
    load_raw,
)
from training.commons_audit import (  # noqa: E402
    CC0_PD,
    CC_BY,
    CC_BY_SA,
    NC_RESTRICTED,
    PRELIMINARILY_ACCEPTABLE,
    UNKNOWN_MISSING,
)

RAW_DIR = ROOT / "data/v3/commons_pilot/raw"


# ---------------------------------------------------------------------------
# Fixtures built in-memory (no dependency on the captured files)
# ---------------------------------------------------------------------------


def raw_row(pageid, title, licence, sha1=None, artist="A", width=1000, height=800):
    return {
        "pageid": pageid,
        "title": title,
        "license_short": licence,
        "artist": artist,
        "attribution_required": "true",
        "sha1": sha1 or f"sha{pageid}",
        "width": width,
        "height": height,
        "mime": "image/jpeg",
        "permission": None,
    }


# ---------------------------------------------------------------------------
# Dedupe and multi-category membership
# ---------------------------------------------------------------------------


def test_file_in_two_categories_is_one_record_with_both_categories():
    by_category = {
        "Biryani": [raw_row(1, "File:Shared.jpg", "CC BY-SA 4.0")],
        "Chicken biryani": [raw_row(1, "File:Shared.jpg", "CC BY-SA 4.0")],
    }
    records = build_manifest(by_category)
    assert len(records) == 1
    assert records[0]["categories"] == ["Biryani", "Chicken biryani"]
    assert records[0]["in_multiple_categories"] is True


def test_dedupe_is_by_pageid_not_title():
    """Two distinct pages that happen to share a title stay separate."""
    by_category = {
        "Biryani": [
            raw_row(1, "File:Same name.jpg", "CC0", sha1="aaa"),
            raw_row(2, "File:Same name.jpg", "CC0", sha1="bbb"),
        ]
    }
    records = build_manifest(by_category)
    assert len(records) == 2
    summary = analyse(records, by_category)
    # Same title, different bytes: an exact-duplicate check must NOT merge them.
    assert summary["measured"]["exact_sha1_duplicate_groups"] == 0
    assert summary["measured"]["duplicate_normalized_title_groups"] == 1


def test_exact_sha1_duplicates_detected_across_categories():
    by_category = {
        "Biryani": [raw_row(1, "File:A.jpg", "CC0", sha1="same")],
        "Mutton biryani": [raw_row(2, "File:B.jpg", "CC0", sha1="same")],
    }
    records = build_manifest(by_category)
    summary = analyse(records, by_category)
    assert summary["measured"]["exact_sha1_duplicate_groups"] == 1
    assert summary["measured"]["exact_sha1_duplicate_files"] == 2
    assert summary["duplicate_groups_sha1"][0]["sha1"] == "same"


def test_multi_category_count_matches_records():
    by_category = {
        "Biryani": [raw_row(1, "File:A.jpg", "CC0"), raw_row(2, "File:B.jpg", "CC0")],
        "Chicken biryani": [raw_row(2, "File:B.jpg", "CC0")],
    }
    records = build_manifest(by_category)
    summary = analyse(records, by_category)
    assert summary["measured"]["files_in_multiple_categories"] == 1
    assert summary["multi_category_files"][0]["title"] == "File:B.jpg"


def test_raw_row_count_differs_from_unique_count_when_overlapping():
    by_category = {
        "Biryani": [raw_row(1, "File:A.jpg", "CC0"), raw_row(2, "File:B.jpg", "CC0")],
        "Chicken biryani": [raw_row(1, "File:A.jpg", "CC0")],
    }
    records = build_manifest(by_category)
    summary = analyse(records, by_category)
    assert summary["measured"]["raw_rows_across_captured_categories"] == 3
    assert summary["measured"]["unique_commons_files"] == 2


# ---------------------------------------------------------------------------
# Licence classification on real-shaped values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "short,expected",
    [
        ("CC0", CC0_PD),
        ("Public domain", CC0_PD),
        ("CC BY 2.0", CC_BY),
        ("CC BY 3.0", CC_BY),
        ("CC BY-SA 4.0", CC_BY_SA),
        ("CC BY-SA 2.0", CC_BY_SA),
        ("CC BY-NC 4.0", NC_RESTRICTED),
        ("", UNKNOWN_MISSING),
    ],
)
def test_real_licence_strings_classify_correctly(short, expected):
    rows = {"Biryani": [raw_row(1, "File:A.jpg", short)]}
    records = build_manifest(rows)
    assert records[0]["licence"]["declared_class"] == expected


def test_missing_licence_is_a_gap_and_not_acceptable():
    rows = {"Biryani": [raw_row(1, "File:A.jpg", "")]}
    records = build_manifest(rows)
    assert records[0]["licence"]["declared_class"] == UNKNOWN_MISSING
    assert records[0]["licence"]["preliminarily_acceptable"] is False
    assert "missing_licence" in records[0]["metadata_gaps"]


def test_missing_artist_recorded_as_gap():
    rows = {"Biryani": [raw_row(1, "File:A.jpg", "CC BY 4.0", artist="")]}
    records = build_manifest(rows)
    assert "missing_artist" in records[0]["metadata_gaps"]


def test_nc_is_excluded_from_acceptable_total():
    rows = {
        "Biryani": [
            raw_row(1, "File:Ok.jpg", "CC0"),
            raw_row(2, "File:NC.jpg", "CC BY-NC 4.0"),
        ]
    }
    records = build_manifest(rows)
    summary = analyse(records, rows)
    assert summary["measured"]["preliminarily_acceptable"] == 1
    assert summary["measured"]["unknown_or_unsuitable"] == 1


def test_declared_licence_never_becomes_verified_rights():
    rows = {"Biryani": [raw_row(1, "File:A.jpg", "CC0")]}
    record = build_manifest(rows)[0]
    assert record["licence"]["verification"] == "declared_only"
    assert record["licence"]["requires_human_review"] is True


# ---------------------------------------------------------------------------
# Hard guarantees
# ---------------------------------------------------------------------------


def test_nothing_is_marked_usable_or_training_ready():
    rows = {"Biryani": [raw_row(1, "File:A.jpg", "CC0")]}
    records = build_manifest(rows)
    summary = analyse(records, rows)
    assert all(r["usable_for_training"] is False for r in records)
    assert summary["training_ready"] is False
    assert "not assessed" in records[0]["usable_reason"]


def test_perceptual_dedupe_is_declared_not_performed():
    rows = {"Biryani": [raw_row(1, "File:A.jpg", "CC0")]}
    summary = analyse(build_manifest(rows), rows)
    assert any("perceptual" in item for item in summary["not_determined"])


def test_legal_clearance_is_listed_as_not_determined():
    rows = {"Biryani": [raw_row(1, "File:A.jpg", "CC0")]}
    summary = analyse(build_manifest(rows), rows)
    assert any("legally cleared" in item for item in summary["not_determined"])


# ---------------------------------------------------------------------------
# Against the real captured data
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not RAW_DIR.exists(), reason="no captured raw data present")
def test_real_capture_loads_and_is_internally_consistent():
    by_category = load_raw(RAW_DIR)
    assert by_category, "expected captured categories"
    records = build_manifest(by_category)
    summary = analyse(records, by_category)
    m = summary["measured"]

    # Dedupe invariants.
    assert m["unique_commons_files"] == len(records)
    assert m["unique_pageids"] == len(records)
    # Every captured page has a pageid and a sha1 in the real data.
    assert all(r["pageid"] for r in records)
    assert all(r["sha1"] for r in records)
    # Licence classes partition the records exactly.
    assert sum(m["licence_distribution"].values()) == len(records)
    assert m["preliminarily_acceptable"] + m["unknown_or_unsuitable"] == len(records)


@pytest.mark.skipif(not RAW_DIR.exists(), reason="no captured raw data present")
def test_real_capture_provenance_is_present():
    for path in sorted(RAW_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        prov = payload.get("_provenance", {})
        assert prov.get("endpoint") == "https://commons.wikimedia.org/w/api.php"
        assert prov.get("category")
        assert prov.get("method")
        # Every record must be independently re-verifiable.
        for page in payload["pages"]:
            assert page.get("pageid")
            assert page.get("title", "").startswith("File:")


@pytest.mark.skipif(not RAW_DIR.exists(), reason="no captured raw data present")
def test_real_capture_has_no_fabricated_fields():
    """Rows must only carry fields the API actually returns."""
    allowed = {
        "pageid", "title", "width", "height", "sha1", "mime",
        "license_short", "license_url", "artist", "attribution_required",
        "permission",
    }
    by_category = load_raw(RAW_DIR)
    for rows in by_category.values():
        for row in rows:
            assert set(row) <= allowed, set(row) - allowed


def test_taxonomy_categories_match_the_taxonomy_file():
    taxonomy = json.loads(
        (ROOT / "data/v3/taxonomy_100_proposed.json").read_text(encoding="utf-8")
    )
    entry = next(c for c in taxonomy["classes"] if c["slug"] == CLASS_SLUG)
    assert entry["commons_categories"] == TAXONOMY_CATEGORIES
