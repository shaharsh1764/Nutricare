"""Tests for the Biryani human-review workflow.

Covers: sample selection, review record creation, label validation, preservation
of original metadata, duplicate flags, missing metadata, and the guarantee that
training eligibility stays false no matter what a reviewer decides.

No network access and no image bytes are involved.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training.review_sample import (  # noqa: E402
    build_sample_entry,
    select_sample,
    write_sample,
)
from training.review_store import (  # noqa: E402
    FLAG_KEYS,
    QUALITY_LABELS,
    RELEVANCE_LABELS,
    ReviewStore,
    validate_flags,
    validate_labels,
)

MANIFEST = ROOT / "data/v3/commons_pilot/biryani_manifest.json"
REVIEW_DIR = ROOT / "data/v3/commons_pilot/review"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_record(pageid, licence_class="CC_BY_SA", sha1=None, artist="A Person",
                width=1000, height=800, gaps=None):
    return {
        "pageid": pageid,
        "title": f"File:Test {pageid}.jpg",
        "normalized_title": f"file:test {pageid}.jpg",
        "description_url": f"https://commons.wikimedia.org/wiki/File:Test_{pageid}.jpg",
        "sha1": sha1 if sha1 is not None else f"sha{pageid}",
        "width": width,
        "height": height,
        "mime": "image/jpeg",
        "licence": {
            "declared_class": licence_class,
            "short_name": "CC BY-SA 4.0",
            "attribution_required": True,
            "verification": "declared_only",
            "requires_human_review": True,
            "preliminarily_acceptable": True,
        },
        "attribution": {"artist_raw": artist},
        "categories": ["Mutton biryani"],
        "classes": ["biryani"],
        "metadata_gaps": gaps or [],
        "usable_for_training": False,
    }


@pytest.fixture
def sample_dir(tmp_path):
    """A review directory holding a small synthetic sample."""
    files = [
        make_record(1, "CC0_PD"),
        make_record(2, "CC_BY"),
        make_record(3, "CC_BY_SA"),
        make_record(4, "CC_BY_SA", gaps=["missing_artist"], artist=""),
    ]
    entries = [build_sample_entry(r) for r in files]
    write_sample(
        tmp_path,
        entries,
        source_manifest=Path("manifest.json"),
        source_sha256="deadbeef",
        limit=10,
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Sample selection
# ---------------------------------------------------------------------------


def test_sample_respects_limit():
    files = [make_record(i) for i in range(1, 51)]
    assert len(select_sample(files, 10)) == 10
    assert len(select_sample(files, 3)) == 3


def test_sample_is_deterministic():
    files = [make_record(i, "CC_BY_SA") for i in range(1, 21)]
    assert [r["pageid"] for r in select_sample(files, 8)] == [
        r["pageid"] for r in select_sample(files, 8)
    ]


def test_sample_surfaces_rare_licence_classes():
    """CC0 is 1 of 30 but round-robin selection must still show it."""
    files = [make_record(i, "CC_BY_SA") for i in range(1, 30)] + [make_record(999, "CC0_PD")]
    picked = select_sample(files, 5)
    assert 999 in [r["pageid"] for r in picked]


def test_sample_rejects_non_positive_limit():
    with pytest.raises(ValueError):
        select_sample([make_record(1)], 0)


def test_sample_entry_copies_source_fields_only():
    record = make_record(7)
    entry = build_sample_entry(record)
    assert entry["pageid"] == 7
    assert entry["sha1"] == "sha7"
    assert entry["licence"]["declared_class"] == "CC_BY_SA"
    assert entry["thumbnail"]["retrieval_status"] == "url_unresolved"
    # No image bytes, ever.
    assert "image_bytes" not in entry


def test_write_sample_records_provenance(tmp_path):
    entries = [build_sample_entry(make_record(1))]
    path = write_sample(
        tmp_path, entries, source_manifest=Path("m.json"), source_sha256="abc", limit=5
    )
    payload = json.loads(path.read_text())
    assert payload["source_manifest_sha256"] == "abc"
    assert payload["image_bytes_downloaded"] is False
    assert payload["source_manifest_read_only"] is True
    assert "legally cleared" in payload["licence_reminder"]


# ---------------------------------------------------------------------------
# Review record creation
# ---------------------------------------------------------------------------


def test_record_creates_decision_for_known_pageid(sample_dir):
    store = ReviewStore(sample_dir)
    decision = store.record(1, relevance="relevant", quality="good", review_notes="clear")
    assert decision["pageid"] == 1
    assert decision["relevance"] == "relevant"
    assert decision["quality"] == "good"
    assert decision["review_notes"] == "clear"
    assert decision["reviewed_utc"]


def test_record_rejects_pageid_not_in_sample(sample_dir):
    store = ReviewStore(sample_dir)
    with pytest.raises(KeyError, match="not in the review sample"):
        store.record(12345, relevance="relevant")


def test_record_merges_incremental_updates(sample_dir):
    store = ReviewStore(sample_dir)
    store.record(1, relevance="relevant")
    updated = store.record(1, quality="poor")
    assert updated["relevance"] == "relevant"  # earlier judgement kept
    assert updated["quality"] == "poor"


def test_save_then_reload_roundtrips(sample_dir):
    store = ReviewStore(sample_dir)
    store.record(2, relevance="irrelevant", quality="poor")
    path = store.save()
    assert path.name == "review_decisions.json"
    reloaded = ReviewStore(sample_dir)
    assert reloaded.decisions[2]["relevance"] == "irrelevant"


# ---------------------------------------------------------------------------
# Label validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label", RELEVANCE_LABELS)
def test_valid_relevance_labels_accepted(sample_dir, label):
    store = ReviewStore(sample_dir)
    assert store.record(1, relevance=label)["relevance"] == label


@pytest.mark.parametrize("label", ["", "maybe", "RELEVANT", "yes", "none"])
def test_invalid_relevance_labels_rejected(sample_dir, label):
    store = ReviewStore(sample_dir)
    with pytest.raises(ValueError, match="invalid relevance label"):
        store.record(1, relevance=label)


@pytest.mark.parametrize("label", QUALITY_LABELS)
def test_valid_quality_labels_accepted(sample_dir, label):
    store = ReviewStore(sample_dir)
    assert store.record(1, quality=label)["quality"] == label


@pytest.mark.parametrize("label", ["excellent", "bad", "OK", "5"])
def test_invalid_quality_labels_rejected(sample_dir, label):
    store = ReviewStore(sample_dir)
    with pytest.raises(ValueError, match="invalid quality label"):
        store.record(1, quality=label)


def test_validate_labels_allows_none():
    """None means 'not yet judged' and must not raise."""
    validate_labels(None, None)


def test_unknown_flag_key_rejected(sample_dir):
    store = ReviewStore(sample_dir)
    with pytest.raises(ValueError, match="unknown review flag"):
        store.record(1, relevance="relevant", looks_tasty=True)


def test_non_bool_flag_rejected(sample_dir):
    store = ReviewStore(sample_dir)
    with pytest.raises(ValueError, match="must be a bool"):
        store.record(1, possible_duplicate="yes")


def test_validate_flags_accepts_all_known_keys():
    validate_flags({key: True for key in FLAG_KEYS})


# ---------------------------------------------------------------------------
# Duplicate flags
# ---------------------------------------------------------------------------


def test_duplicate_flag_recorded_and_persisted(sample_dir):
    store = ReviewStore(sample_dir)
    store.record(3, relevance="relevant", possible_duplicate=True)
    store.save()
    reloaded = ReviewStore(sample_dir)
    assert reloaded.decisions[3]["flags"]["possible_duplicate"] is True


def test_flags_default_to_none_not_false(sample_dir):
    """Unset flags must be None so 'not checked' is not mistaken for 'no'."""
    store = ReviewStore(sample_dir)
    decision = store.record(1, relevance="relevant")
    assert decision["flags"]["possible_duplicate"] is None
    assert decision["flags"]["watermark_or_branding"] is None
    assert decision["flags"]["collage_or_multiple_dishes"] is None


def test_flag_toggle_preserves_other_flags(sample_dir):
    store = ReviewStore(sample_dir)
    store.record(1, relevance="relevant", possible_duplicate=True)
    updated = store.record(1, watermark_or_branding=True)
    assert updated["flags"]["possible_duplicate"] is True
    assert updated["flags"]["watermark_or_branding"] is True


def test_summary_counts_flags(sample_dir):
    store = ReviewStore(sample_dir)
    store.record(1, relevance="relevant", possible_duplicate=True)
    store.record(2, relevance="uncertain", watermark_or_branding=True)
    summary = store.summary()
    assert summary["flag_totals"]["possible_duplicate"] == 1
    assert summary["flag_totals"]["watermark_or_branding"] == 1


# ---------------------------------------------------------------------------
# Preservation of original metadata
# ---------------------------------------------------------------------------


def test_review_never_modifies_the_sample_file(sample_dir):
    sample_path = sample_dir / "review_sample.json"
    before = hashlib.sha256(sample_path.read_bytes()).hexdigest()
    store = ReviewStore(sample_dir)
    store.record(1, relevance="relevant", quality="good", possible_duplicate=True)
    store.save()
    after = hashlib.sha256(sample_path.read_bytes()).hexdigest()
    assert before == after, "source sample metadata was modified by review"


def test_decisions_live_in_a_separate_file(sample_dir):
    store = ReviewStore(sample_dir)
    store.record(1, relevance="relevant")
    path = store.save()
    assert path.name == "review_decisions.json"
    assert path != sample_dir / "review_sample.json"


def test_decision_keeps_source_identifiers(sample_dir):
    store = ReviewStore(sample_dir)
    decision = store.record(2, relevance="relevant")
    # Enough to trace the human judgement back to the exact Commons file.
    assert decision["sha1"] == "sha2"
    assert decision["title"] == "File:Test 2.jpg"


def test_store_refuses_missing_sample(tmp_path):
    with pytest.raises(FileNotFoundError, match="review_sample.json"):
        ReviewStore(tmp_path)


# ---------------------------------------------------------------------------
# Missing metadata
# ---------------------------------------------------------------------------


def test_sample_preserves_missing_metadata_marker(sample_dir):
    store = ReviewStore(sample_dir)
    image = store.image_for(4)
    assert "missing_artist" in image.get("metadata_gaps", [])
    assert image["attribution"]["artist_raw"] == ""


def test_reviewing_a_record_with_missing_metadata_still_works(sample_dir):
    """Absent metadata must not block review, and must not be invented."""
    store = ReviewStore(sample_dir)
    decision = store.record(4, relevance="uncertain", quality="poor")
    assert decision["relevance"] == "uncertain"
    # The reviewer's note is theirs; the source artist stays empty.
    assert store.image_for(4)["attribution"]["artist_raw"] == ""


# ---------------------------------------------------------------------------
# Training eligibility must remain false
# ---------------------------------------------------------------------------


def test_usable_for_training_false_even_when_reviewer_approves(sample_dir):
    store = ReviewStore(sample_dir)
    decision = store.record(
        1, relevance="relevant", quality="good", review_notes="looks perfect"
    )
    assert decision["usable_for_training"] is False
    assert "does not grant training permission" in decision["usable_reason"]


def test_usable_for_training_false_for_every_decision(sample_dir):
    store = ReviewStore(sample_dir)
    for pageid in store.sample_pageids():
        store.record(pageid, relevance="relevant", quality="good")
    store.save()
    payload = json.loads((sample_dir / "review_decisions.json").read_text())
    assert all(d["usable_for_training"] is False for d in payload["decisions"])
    assert payload["training_eligibility"]["usable_for_training"] is False


def test_store_cannot_be_tricked_into_granting_training(sample_dir):
    """No parameter can grant training permission.

    ``usable_for_training`` is not a reserved keyword, so passing it lands in
    ``**flags`` and is rejected as an unknown flag -- it can never reach the
    stored record as a permissive value.
    """
    store = ReviewStore(sample_dir)
    with pytest.raises(ValueError, match="unknown review flag"):
        store.record(1, relevance="relevant", usable_for_training=True)  # type: ignore[call-arg]


def test_legal_clearance_is_never_claimed(sample_dir):
    store = ReviewStore(sample_dir)
    decision = store.record(1, relevance="relevant", quality="good")
    assert decision["legal_clearance"] == "not_verified"
    assert decision["declared_licence_only"] is True


def test_summary_reports_no_training_eligible_images(sample_dir):
    store = ReviewStore(sample_dir)
    store.record(1, relevance="relevant")
    assert store.summary()["usable_for_training_any"] is False


# ---------------------------------------------------------------------------
# Against the real pilot sample (if generated)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (REVIEW_DIR / "review_sample.json").exists(), reason="no generated sample"
)
def test_real_sample_is_at_most_ten_images():
    sample = json.loads((REVIEW_DIR / "review_sample.json").read_text())
    assert sample["sample_size"] <= 10
    assert len(sample["images"]) == sample["sample_size"]
    assert sample["image_bytes_downloaded"] is False


@pytest.mark.skipif(
    not (REVIEW_DIR / "review_sample.json").exists(), reason="no generated sample"
)
def test_real_sample_entries_are_traceable():
    sample = json.loads((REVIEW_DIR / "review_sample.json").read_text())
    for image in sample["images"]:
        assert image["pageid"]
        assert image["sha1"]
        assert image["description_url"].startswith("https://commons.wikimedia.org/")
        thumb = image["thumbnail"]
        assert thumb["retrieval_status"] in {
            "url_resolved_not_downloaded",
            "url_unresolved",
            "blocked",
        }
        if thumb["retrieval_status"] == "url_resolved_not_downloaded":
            assert thumb["url"].startswith("https://")
            assert thumb["retrieved_utc"]


@pytest.mark.skipif(
    not (REVIEW_DIR / "review_sample.json").exists(), reason="no generated sample"
)
def test_real_sample_matches_manifest_metadata():
    """The sample must be an unmodified projection of the source manifest."""
    manifest = json.loads(MANIFEST.read_text())
    by_pageid = {f["pageid"]: f for f in manifest["files"]}
    sample = json.loads((REVIEW_DIR / "review_sample.json").read_text())
    for image in sample["images"]:
        source = by_pageid[image["pageid"]]
        assert image["sha1"] == source["sha1"]
        assert image["title"] == source["title"]
        assert image["width"] == source["width"]
        assert image["height"] == source["height"]
        assert image["licence"]["declared_class"] == source["licence"]["declared_class"]
        assert image["licence"]["short_name"] == source["licence"]["short_name"]


@pytest.mark.skipif(
    not (REVIEW_DIR / "review_sample.json").exists(), reason="no generated sample"
)
def test_real_sample_covers_multiple_licence_classes():
    sample = json.loads((REVIEW_DIR / "review_sample.json").read_text())
    classes = {i["licence"]["declared_class"] for i in sample["images"]}
    assert len(classes) >= 2, f"expected licence diversity, got {classes}"
