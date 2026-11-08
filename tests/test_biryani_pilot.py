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


# ---------------------------------------------------------------------------
# Regression tests: attribution_required / licence_url / usage_terms mapping
#
# These exist because a previous version of the builder passed only
# license_short and artist into the classifier. AttributionRequired was then
# always absent, and the classifier defaulted it to False -- so every CC BY-SA
# file was silently recorded as not requiring attribution. These tests pin the
# correct field mapping so the bug cannot return.
# ---------------------------------------------------------------------------


def raw_row_with_attribution(pageid, title, licence, attribution_required, licence_url=None):
    row = raw_row(pageid, title, licence)
    row["attribution_required"] = attribution_required
    if licence_url is not None:
        row["license_url"] = licence_url
    return row


def test_cc_by_sa_with_api_true_reports_true():
    """The original bug: CC BY-SA must keep the API's 'true', not default to False."""
    rows = {
        "Biryani": [
            raw_row_with_attribution(1, "File:A.jpg", "CC BY-SA 4.0", "true")
        ]
    }
    record = build_manifest(rows)[0]
    assert record["licence"]["declared_class"] == CC_BY_SA
    assert record["licence"]["attribution_required"] is True
    assert record["licence"]["attribution_required_source"] == "api:extmetadata"


def test_cc_by_with_api_true_reports_true():
    rows = {"Biryani": [raw_row_with_attribution(1, "File:A.jpg", "CC BY 2.0", "true")]}
    assert build_manifest(rows)[0]["licence"]["attribution_required"] is True


def test_cc0_with_api_false_reports_false():
    rows = {"Biryani": [raw_row_with_attribution(1, "File:A.jpg", "CC0", "false")]}
    record = build_manifest(rows)[0]
    assert record["licence"]["declared_class"] == CC0_PD
    assert record["licence"]["attribution_required"] is False
    assert record["licence"]["attribution_required_source"] == "api:extmetadata"


def test_missing_attribution_field_is_unknown_not_false():
    """An absent field must never be reported as 'no attribution required'."""
    row = raw_row(1, "File:A.jpg", "CC BY-SA 4.0")
    row.pop("attribution_required")
    record = build_manifest({"Biryani": [row]})[0]
    assert record["licence"]["attribution_required"] is None
    assert record["licence"]["attribution_required_source"] == "unrecorded_in_capture"


def test_api_supplied_licence_url_is_used_verbatim():
    rows = {
        "Biryani": [
            raw_row_with_attribution(
                1, "File:A.jpg", "CC BY-SA 4.0", "true",
                licence_url="https://creativecommons.org/licenses/by-sa/4.0",
            )
        ]
    }
    licence = build_manifest(rows)[0]["licence"]
    assert licence["licence_url"] == "https://creativecommons.org/licenses/by-sa/4.0"
    assert licence["licence_url_source"] == "api:extmetadata"
    assert licence["licence_url_derived"] is None


def test_untranscribed_licence_url_is_derived_and_labelled():
    """When the capture omitted LicenseUrl, mark it derived -- never as API data."""
    rows = {"Biryani": [raw_row_with_attribution(1, "File:A.jpg", "CC BY-SA 4.0", "true")]}
    licence = build_manifest(rows)[0]["licence"]
    assert licence["licence_url"] == ""  # API value stays empty, not fabricated
    assert licence["licence_url_source"] == "derived:canonical_cc_deed_url"
    assert licence["licence_url_derived"] == "https://creativecommons.org/licenses/by-sa/4.0"


def test_cc0_derived_url_points_at_the_cc0_deed():
    rows = {"Biryani": [raw_row_with_attribution(1, "File:A.jpg", "CC0", "false")]}
    licence = build_manifest(rows)[0]["licence"]
    assert "publicdomain/zero" in licence["licence_url_derived"]


def test_unknown_licence_gets_no_derived_url():
    rows = {"Biryani": [raw_row_with_attribution(1, "File:A.jpg", "Some odd licence", "true")]}
    licence = build_manifest(rows)[0]["licence"]
    assert licence["licence_url_derived"] is None
    assert licence["licence_url_source"] == "unrecorded_in_capture"


def test_usage_terms_is_empty_because_it_was_not_requested():
    """Empty must mean 'not asked', not 'no usage terms apply'."""
    rows = {"Biryani": [raw_row_with_attribution(1, "File:A.jpg", "CC BY-SA 4.0", "true")]}
    licence = build_manifest(rows)[0]["licence"]
    assert licence["usage_terms"] == ""
    assert licence["usage_terms_source"] == "not_requested_in_query"


def test_preliminarily_acceptable_is_not_permission_to_train():
    """The flag must never be readable as authorisation."""
    rows = {"Biryani": [raw_row_with_attribution(1, "File:A.jpg", "CC0", "false")]}
    record = build_manifest(rows)[0]
    assert record["licence"]["preliminarily_acceptable"] is True
    assert record["licence"]["verification"] == "declared_only"
    assert record["licence"]["requires_human_review"] is True
    # Usability is still false even on the most permissive possible licence.
    assert record["usable_for_training"] is False


def test_attribution_block_carries_source_marker():
    rows = {"Biryani": [raw_row_with_attribution(1, "File:A.jpg", "CC BY-SA 4.0", "true")]}
    attribution = build_manifest(rows)[0]["attribution"]
    assert attribution["attribution_required"] is True
    assert attribution["attribution_required_source"] == "api:extmetadata"


def test_summary_flags_cc_by_without_attribution():
    rows = {
        "Biryani": [
            raw_row_with_attribution(1, "File:Good.jpg", "CC BY-SA 4.0", "true"),
            raw_row_with_attribution(2, "File:Bad.jpg", "CC BY-SA 4.0", "false"),
        ]
    }
    summary = analyse(build_manifest(rows), rows)
    # A CC BY-SA file recorded as not requiring attribution is a violation.
    assert summary["measured"]["attribution_violations_cc_by_without_attribution"] == 1


@pytest.mark.skipif(not RAW_DIR.exists(), reason="no captured raw data present")
def test_real_capture_has_zero_attribution_violations():
    by_category = load_raw(RAW_DIR)
    summary = analyse(build_manifest(by_category), by_category)
    m = summary["measured"]
    assert m["attribution_violations_cc_by_without_attribution"] == 0
    assert m["attribution_required_unknown"] == 0
    # Exactly the two CC0 files may lack an attribution requirement.
    assert m["attribution_required_false"] == 2
    assert m["licence_distribution"].get("CC0_PD", 0) == 2
    assert m["attribution_required_true"] == sum(
        v for k, v in m["licence_distribution"].items() if k in ("CC_BY", "CC_BY_SA")
    )


@pytest.mark.skipif(not RAW_DIR.exists(), reason="no captured raw data present")
def test_real_capture_attribution_matches_raw_source_field():
    """Cross-check the manifest against the raw field, file by file."""
    by_category = load_raw(RAW_DIR)
    raw_by_pageid = {}
    for rows in by_category.values():
        for row in rows:
            raw_by_pageid[row["pageid"]] = row
    for record in build_manifest(by_category):
        raw = raw_by_pageid[record["pageid"]]
        expected = str(raw["attribution_required"]).lower() == "true"
        assert record["licence"]["attribution_required"] is expected


@pytest.mark.skipif(not RAW_DIR.exists(), reason="no captured raw data present")
def test_real_capture_never_fabricates_licence_url():
    """An empty API value must stay empty, with the derived value kept separate."""
    by_category = load_raw(RAW_DIR)
    for record in build_manifest(by_category):
        if record["licence"]["licence_url_source"] == "derived:canonical_cc_deed_url":
            assert record["licence"]["licence_url"] == ""
            assert record["licence"]["licence_url_derived"]


@pytest.mark.skipif(not RAW_DIR.exists(), reason="no captured raw data present")
def test_every_real_record_still_not_usable():
    by_category = load_raw(RAW_DIR)
    records = build_manifest(by_category)
    assert all(r["usable_for_training"] is False for r in records)
    assert all(r["licence"]["verification"] == "declared_only" for r in records)
