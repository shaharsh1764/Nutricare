"""Regression tests for the V2 collection, rights and preparation pipeline.

These tests enforce the properties that are easy to break silently:

* the six counts stay separate and are never conflated;
* nothing becomes training-usable from metadata alone;
* unreviewed is never approved, and approved is never inferred;
* CC BY-SA stays out of the training-approved tier by default;
* splits are leak-free and deterministic;
* the 12-class production model and the first Biryani review sample are
  untouchable.

No network access and no image bytes are required. The one test that decodes
pixels skips itself when Pillow is absent, so the suite passes on the base
requirements too.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "training"))

from training.build_v2_review_batches import (  # noqa: E402
    PROTECTED_DIRS,
    _is_protected,
    build_batch_doc,
    prepare_entries,
    select_batch,
    write_batch,
)
from training.collect_v2 import (  # noqa: E402
    _FakeClient,
    _fake_page,
    collect_class,
    count_six,
    enrich,
    plan,
)
from training.licence_policy import (  # noqa: E402
    EXCLUDED,
    REVIEW_REQUIRED,
    TRAINING_APPROVED,
    attribution_record,
    classify_rights,
    render_attributions,
    rights_summary,
)
from training.prepare_v2_dataset import (  # noqa: E402
    assign_splits,
    build_duplicate_groups,
    check_image_bytes,
    cross_class_duplicates,
    detect_duplicate_pairs,
    normalize_title,
    prepare,
    review_verdict,
    verify_no_leakage,
    write_outputs,
)

FIXTURE = ROOT / "tests/fixtures/commons/v4_measured_sample.json"
PROTECTED_MODEL = ROOT / "models/food_classifier_cc0.pt"
BIRYANI_REVIEW = ROOT / "data/v3/commons_pilot/review"


# ---------------------------------------------------------------------------
# Licence policy
# ---------------------------------------------------------------------------


class TestRightsTiering:
    def test_cc0_with_author_is_training_approved(self):
        out = classify_rights({"declared_class": "CC0_PD"}, artist="Someone")
        assert out["rights_tier"] == TRAINING_APPROVED
        assert out["training_approved"] is True

    def test_cc_by_with_author_is_training_approved(self):
        out = classify_rights({"declared_class": "CC_BY"}, artist="Someone")
        assert out["rights_tier"] == TRAINING_APPROVED

    def test_cc_by_without_author_is_excluded(self):
        # An attribution licence with nobody to attribute is not usable.
        out = classify_rights({"declared_class": "CC_BY"}, artist="")
        assert out["rights_tier"] == EXCLUDED
        assert any("no author" in r for r in out["reasons"])

    def test_cc_by_sa_is_held_out(self):
        out = classify_rights({"declared_class": "CC_BY_SA"}, artist="X")
        assert out["rights_tier"] == REVIEW_REQUIRED
        assert out["training_approved"] is False

    @pytest.mark.parametrize("cls", ["NC_RESTRICTED", "ND_RESTRICTED", "UNKNOWN_MISSING",
                                    "OTHER_REVIEW", "SOMETHING_NEW"])
    def test_non_permissive_classes_are_excluded(self, cls):
        assert classify_rights({"declared_class": cls}, artist="X")["rights_tier"] == EXCLUDED

    def test_missing_declared_class_is_excluded(self):
        assert classify_rights({}, artist="X")["rights_tier"] == EXCLUDED

    def test_scrape_provenance_overrides_permissive_licence(self):
        out = classify_rights(
            {"declared_class": "CC0_PD"}, artist="X",
            permission_text="Taken from Google image search",
        )
        assert out["rights_tier"] == EXCLUDED
        assert out["provenance_strength"] == "scrape_risk"

    def test_external_review_provenance_is_detected(self):
        out = classify_rights(
            {"declared_class": "CC_BY"}, artist="X",
            permission_text="This file was reviewed by the Flickr upload bot",
        )
        assert out["provenance_strength"] == "external_review"
        assert out["rights_tier"] == TRAINING_APPROVED

    def test_legal_clearance_is_never_claimed(self):
        out = classify_rights({"declared_class": "CC0_PD"}, artist="X")
        assert out["legal_clearance"] == "not_verified"
        assert out["verification"] == "declared_only"
        assert out["human_review_required"] is True

    def test_summary_separates_tiers(self):
        tiers = [
            classify_rights({"declared_class": "CC0_PD"}, artist="A"),
            classify_rights({"declared_class": "CC_BY_SA"}, artist="B"),
            classify_rights({"declared_class": "NC_RESTRICTED"}, artist="C"),
        ]
        summary = rights_summary(tiers)
        assert summary["by_tier"][TRAINING_APPROVED] == 1
        assert summary["by_tier"][REVIEW_REQUIRED] == 1
        assert summary["by_tier"][EXCLUDED] == 1
        assert "not legal clearance" in summary["note"]

    def test_attribution_record_and_render(self):
        record = {
            "pageid": 1, "title": "File:A.jpg", "sha1": "s", "description_url": "u",
            "attribution": {"artist_raw": "An Author"},
            "licence": {"short_name": "CC BY 4.0", "licence_url": "https://cc/by/4.0",
                        "attribution_required": True},
        }
        entry = attribution_record(record)
        assert entry["author"] == "An Author"
        assert entry["licence_url"] == "https://cc/by/4.0"
        text = render_attributions([entry])
        assert "An Author" in text
        assert "constitutes legal clearance" in text


# ---------------------------------------------------------------------------
# Collection and the six counts
# ---------------------------------------------------------------------------


def _tree():
    return {
        "Category:Demo": {
            "files": [
                {"title": "File:CC0.jpg"},
                {"title": "File:CCBY.jpg"},
                {"title": "File:SA.jpg"},
                {"title": "File:NC.jpg"},
                {"title": "File:NoArtist.jpg"},
                {"title": "File:Tiny.jpg"},
                {"title": "File:Dupe.jpg"},
            ],
            "subcats": [],
            "pages": [
                _fake_page("File:CC0.jpg", 1, "s1", "CC0", "A"),
                _fake_page("File:CCBY.jpg", 2, "s2", "CC BY 4.0", "B"),
                _fake_page("File:SA.jpg", 3, "s3", "CC BY-SA 4.0", "C"),
                _fake_page("File:NC.jpg", 4, "s4", "CC BY-NC 4.0", "D"),
                _fake_page("File:NoArtist.jpg", 5, "s5", "CC BY 4.0", None),
                _fake_page("File:Tiny.jpg", 6, "s6", "CC0", "E", 100, 80),
                _fake_page("File:Dupe.jpg", 7, "s1", "CC0", "A"),
            ],
        }
    }


class TestCollectSixCounts:
    def test_six_counts_are_separate_and_honest(self):
        doc = collect_class(_FakeClient(_tree()), {"slug": "demo",
                                                   "commons_categories": ["Category:Demo"]})
        counts = doc["counts"]
        assert counts["1_discovered_file_slots"] == 7
        assert counts["2_metadata_retrieved"] == 7
        # CC0, CC BY with author; the copy, the tiny file and the authorless
        # CC BY file are all excluded.
        assert counts["3_rights_supported"] == 2
        assert counts["3b_rights_review_required_cc_by_sa"] == 1
        assert counts["4_reviewed"] == 0
        assert counts["5_approved"] == 0
        assert counts["6_training_usable"] == 0

    def test_collector_never_marks_anything_usable(self):
        doc = collect_class(_FakeClient(_tree()), {"slug": "demo",
                                                   "commons_categories": ["Category:Demo"]})
        assert all(r["usable_for_training"] is False for r in doc["files"])

    def test_duplicate_is_flagged_and_not_counted(self):
        doc = collect_class(_FakeClient(_tree()), {"slug": "demo",
                                                   "commons_categories": ["Category:Demo"]})
        dupes = [r for r in doc["files"] if r.get("exact_duplicate_of")]
        assert len(dupes) == 1
        assert "exact_duplicate_in_class" in dupes[0]["technical_flags"]

    def test_discovered_count_is_not_a_usable_count(self):
        doc = collect_class(_FakeClient(_tree()), {"slug": "demo",
                                                   "commons_categories": ["Category:Demo"]})
        assert doc["counts"]["1_discovered_file_slots"] > doc["counts"]["6_training_usable"]

    def test_count_six_forbids_metadata_only_approval(self):
        records = [{
            "rights": {"rights_tier": TRAINING_APPROVED},
            "technical_flags": [],
            "licence": {"declared_class": "CC0_PD"},
            "pageid": 1, "sha1": "s",
        }]
        counts = count_six(records, discovered_slots=1)
        assert counts["3_rights_supported"] == 1
        assert counts["4_reviewed"] == counts["5_approved"] == counts["6_training_usable"] == 0

    def test_enrich_flags_undersized_and_odd_aspect(self):
        base = {"pageid": 1, "sha1": "s", "mime": "image/jpeg",
                "width": 100, "height": 90, "licence": {"declared_class": "CC0_PD"},
                "attribution": {"artist_raw": "A"}}
        assert "below_min_edge" in enrich(base)["technical_flags"]
        wide = dict(base, width=4000, height=400)
        assert "extreme_aspect_ratio" in enrich(wide)["technical_flags"]
        good = dict(base, width=800, height=600)
        assert enrich(good)["technical_flags"] == []

    def test_plan_reports_missing_categories(self, tmp_path):
        result = plan(
            [
                {"slug": "a", "commons_categories": ["Category:A"]},
                {"slug": "b", "commons_categories": []},
            ],
            tmp_path,
        )
        assert result["to_collect"] == ["a"]
        assert result["no_commons_category"] == ["b"]

    def test_collected_class_is_recognised_by_plan(self, tmp_path):
        doc = collect_class(_FakeClient(_tree()), {"slug": "demo",
                                                   "commons_categories": ["Category:Demo"]})
        from training.collect_v2 import write_class
        write_class(doc, tmp_path)
        result = plan([{"slug": "demo", "commons_categories": ["Category:Demo"]}], tmp_path)
        assert result["already_collected"] == ["demo"]
        assert result["to_collect"] == []


# ---------------------------------------------------------------------------
# Review gating
# ---------------------------------------------------------------------------


class TestReviewVerdict:
    def test_unreviewed_is_not_approved(self):
        verdict = review_verdict(None)
        assert verdict["approved"] is False
        assert verdict["state"] == "unreviewed"

    def test_partial_decision_is_not_approved(self):
        assert review_verdict({"relevance": "relevant"})["state"] == "partial"
        assert review_verdict({"quality": "good"})["state"] == "partial"

    def test_unknown_relevance_is_not_approved(self):
        assert review_verdict({"relevance": "uncertain", "quality": "good"})["approved"] is False

    def test_irrelevant_drops_the_image(self):
        verdict = review_verdict({"relevance": "irrelevant", "quality": "good"})
        assert verdict["approved"] is False
        assert verdict["drop_from_class"] is True

    def test_poor_quality_is_not_approved(self):
        assert review_verdict({"relevance": "relevant", "quality": "poor"})["approved"] is False

    def test_raised_flag_blocks_approval(self):
        verdict = review_verdict({"relevance": "relevant", "quality": "good",
                                  "flags": {"watermark_or_branding": True}})
        assert verdict["approved"] is False
        assert "watermark_or_branding" in verdict["reason"]

    def test_unset_tristate_flag_does_not_block(self):
        # null means "not looked at", which is not the same as false.
        verdict = review_verdict({"relevance": "relevant", "quality": "good",
                                  "flags": {"possible_duplicate": None,
                                            "collage_or_multiple_dishes": False}})
        assert verdict["approved"] is True

    def test_clean_approval(self):
        verdict = review_verdict({"relevance": "relevant", "quality": "acceptable"})
        assert verdict["approved"] is True


# ---------------------------------------------------------------------------
# Dedupe and splits
# ---------------------------------------------------------------------------


class TestDedupeAndSplits:
    def test_normalize_title_is_stable(self):
        assert normalize_title("File:A_one.jpg") == normalize_title("File:A_One.JPG")
        assert normalize_title("File:A one.jpg") == normalize_title("file:a-one.jpg")

    def test_groups_unify_by_sha1_and_title(self):
        records = [
            {"pageid": 1, "title": "File:One.jpg", "sha1": "s1"},
            {"pageid": 2, "title": "File:One (copy).jpg", "sha1": "s1"},
            {"pageid": 3, "title": "File:Other.jpg", "sha1": "s3"},
        ]
        groups = build_duplicate_groups(records)
        sizes = sorted(len(v) for v in groups.values())
        assert sizes == [1, 2]

    def test_duplicate_pairs_report_the_signal(self):
        pairs = detect_duplicate_pairs([
            {"pageid": 1, "title": "File:A.jpg", "sha1": "same"},
            {"pageid": 2, "title": "File:B.jpg", "sha1": "same"},
        ])
        assert any(p["signal"] == "sha1" for p in pairs)

    def test_cross_class_duplicates_are_reported(self):
        conflicts = cross_class_duplicates({
            "a": [{"pageid": 1, "sha1": "s1"}],
            "b": [{"pageid": 1, "sha1": "s1"}],
        })
        assert conflicts and conflicts[0]["classes"] == ["a", "b"]

    def test_split_assignment_is_deterministic_and_group_atomic(self):
        groups = {f"g{i}": [i * 2, i * 2 + 1] for i in range(8)}
        first = assign_splits(groups, [{}] * 16, seed=11, val_pct=0.2, test_pct=0.2)
        second = assign_splits(groups, [{}] * 16, seed=11, val_pct=0.2, test_pct=0.2)
        assert first == second
        for members in groups.values():
            assert len({first[i] for i in members}) == 1

    def test_different_seeds_differ(self):
        groups = {f"g{i}": [i] for i in range(20)}
        a = assign_splits(groups, [{}] * 20, seed=1)
        b = assign_splits(groups, [{}] * 20, seed=999)
        assert a != b

    def test_leakage_detection_catches_sha1_spanning_splits(self):
        leak = verify_no_leakage([
            {"sha1": "x", "split": "train", "duplicate_group": "g1"},
            {"sha1": "x", "split": "test", "duplicate_group": "g2"},
        ])
        assert leak["leak_free"] is False

    def test_leakage_detection_catches_group_spanning_splits(self):
        leak = verify_no_leakage([
            {"sha1": "a", "split": "train", "duplicate_group": "g1"},
            {"sha1": "b", "split": "val", "duplicate_group": "g1"},
        ])
        assert leak["leak_free"] is False
        assert "g1" in leak["group_spanning_splits"]

    def test_clean_split_has_no_leak(self):
        clean = verify_no_leakage([
            {"sha1": "a", "split": "train", "duplicate_group": "g1"},
            {"sha1": "b", "split": "test", "duplicate_group": "g2"},
        ])
        assert clean["leak_free"] is True

    def test_empty_input_is_not_called_leak_free(self):
        assert verify_no_leakage([])["leak_free"] is False


# ---------------------------------------------------------------------------
# Preparation on real measured metadata
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def measured_docs():
    from training.demo_v2_pipeline import FixtureClient
    from training.collect_v2 import collect_class as collect

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    client = FixtureClient(fixture["classes"])
    docs = []
    for slug, entry in fixture["classes"].items():
        docs.append(collect(client, {
            "slug": slug,
            "canonical": slug.title(),
            "commons_categories": entry["commons_categories"],
        }, depth=0))
    return docs


class TestPrepareOnMeasuredData:
    def test_fixture_provenance_is_recorded(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        provenance = fixture["provenance"]
        assert provenance["bytes_downloaded"] == 0
        assert provenance["endpoint"] == "https://commons.wikimedia.org/w/api.php"

    def test_fixture_has_no_fabricated_urls(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for entry in fixture["classes"].values():
            for page in entry["files"]:
                assert page["pageid"] > 0
                assert len(page["sha1"]) == 40
                assert page["width"] > 0 and page["height"] > 0

    def test_nothing_is_usable_without_bytes_or_reviews(self, measured_docs):
        report = prepare(measured_docs)
        assert report["totals"]["usable_images"] == 0
        assert all(c["counts"]["6_training_usable"] == 0 for c in report["classes"])

    def test_counts_one_two_three_are_populated(self, measured_docs):
        report = prepare(measured_docs)
        for c in report["classes"]:
            assert c["counts"]["1_discovered"] > 0
            assert c["counts"]["2_metadata_retrieved"] > 0
            assert c["counts"]["4_reviewed"] == 0

    def test_synthetic_reviews_raise_five_but_not_six(self, measured_docs):
        from training.demo_v2_pipeline import synthetic_reviews

        decisions = synthetic_reviews(measured_docs, {})
        report = prepare(measured_docs, reviews=decisions)
        for c in report["classes"]:
            assert c["counts"]["4_reviewed"] > 0
            assert c["counts"]["5_approved"] > 0
            # The hard gate: no bytes, so still nothing trainable.
            assert c["counts"]["6_training_usable"] == 0
        assert report["totals"]["usable_images"] == 0

    def test_cc_by_sa_is_held_out_of_training(self, measured_docs):
        from training.demo_v2_pipeline import synthetic_reviews

        decisions = synthetic_reviews(measured_docs, {})
        report = prepare(measured_docs, reviews=decisions)
        held = [r for r in report["rows"]
                if r["rights_tier"] == REVIEW_REQUIRED
                and "cc_by_sa_held_out" in r["exclusion_reasons"]]
        assert held, "some CC BY-SA files must be explicitly held out"

    def test_outputs_are_written_and_split_files_hold_only_usable(self, measured_docs, tmp_path):
        from training.demo_v2_pipeline import synthetic_reviews

        report = prepare(measured_docs, reviews=synthetic_reviews(measured_docs, {}))
        written = write_outputs(report, tmp_path)
        for key in ("manifest", "split_train", "split_val", "split_test",
                    "download_plan", "attributions"):
            assert Path(written[key]).exists()
        for split in ("train", "val", "test"):
            payload = json.loads(Path(written[f"split_{split}"]).read_text())
            assert payload["count"] == len(payload["images"])
            assert all(i["training_usable"] for i in payload["images"])

    def test_download_plan_lists_only_permitted_files(self, measured_docs, tmp_path):
        from training.demo_v2_pipeline import synthetic_reviews

        report = prepare(measured_docs, reviews=synthetic_reviews(measured_docs, {}))
        written = write_outputs(report, tmp_path)
        plan_doc = json.loads(Path(written["download_plan"]).read_text())
        assert plan_doc["count"] == len(plan_doc["files"])
        assert "nothing here was downloaded" in plan_doc["note"]
        excluded = {r["pageid"] for r in report["rows"] if r["rights_tier"] == EXCLUDED}
        assert not (excluded & {f["pageid"] for f in plan_doc["files"]})

    def test_measured_metadata_really_is_mostly_share_alike(self, measured_docs):
        # Documents the finding that shapes the whole plan. If a future capture
        # overturns it, this test should be updated deliberately, not ignored.
        tiers = {}
        for doc in measured_docs:
            for record in doc["files"]:
                tier = record["rights"]["rights_tier"]
                tiers[tier] = tiers.get(tier, 0) + 1
        assert tiers.get(REVIEW_REQUIRED, 0) > tiers.get(TRAINING_APPROVED, 0)


# ---------------------------------------------------------------------------
# Review batches
# ---------------------------------------------------------------------------


class TestReviewBatches:
    def _files(self):
        from training.collect_v2 import _fake_page
        return [
            enrich({
                "pageid": i, "title": f"File:X{i}.jpg", "sha1": f"s{i}",
                "mime": "image/jpeg", "width": 1000, "height": 800,
                "licence": {"declared_class": cls},
                "attribution": {"artist_raw": f"Author{i % 3}"},
                "metadata_gaps": [], "categories": [],
            })
            for i, cls in enumerate(
                ["CC0_PD"] * 4 + ["CC_BY"] * 4 + ["CC_BY_SA"] * 4, start=1
            )
        ]

    def test_batch_is_capped_and_unique(self):
        batch = select_batch(self._files(), limit=6)
        assert len(batch) == 6
        assert len({b["pageid"] for b in batch}) == 6

    def test_batch_is_deterministic(self):
        first = [b["pageid"] for b in select_batch(self._files(), limit=6)]
        second = [b["pageid"] for b in select_batch(self._files(), limit=6)]
        assert first == second

    def test_entries_are_never_usable(self):
        entries = prepare_entries(select_batch(self._files(), limit=5))
        assert all(e["usable_for_training"] is False for e in entries)

    def test_thumbnail_is_unresolved_not_invented(self):
        entries = prepare_entries(select_batch(self._files(), limit=3))
        for entry in entries:
            assert entry["thumbnail"]["url"] == ""
            assert entry["thumbnail"]["retrieval_status"] == "url_unresolved"

    def test_batch_document_states_no_bytes_downloaded(self):
        doc = build_batch_doc({"class": "x"}, prepare_entries(select_batch(self._files(), limit=3)),
                              limit=3)
        assert doc["image_bytes_downloaded"] is False
        assert "licence_reminder" in doc

    def test_biryani_review_dir_is_protected(self):
        assert _is_protected(BIRYANI_REVIEW) is True
        assert any(p == BIRYANI_REVIEW for p in PROTECTED_DIRS)

    def test_writing_into_biryani_review_is_refused(self, tmp_path):
        with pytest.raises(SystemExit):
            write_batch(BIRYANI_REVIEW, {"class": "x"})

    def test_existing_batch_is_not_silently_overwritten(self, tmp_path):
        target = tmp_path / "roti"
        write_batch(target, {"class": "roti"})
        with pytest.raises(SystemExit):
            write_batch(target, {"class": "roti"})

    def test_batch_with_decisions_is_never_regenerated(self, tmp_path):
        target = tmp_path / "roti"
        write_batch(target, {"class": "roti"})
        (target / "review_decisions.json").write_text('{"decisions": []}', encoding="utf-8")
        with pytest.raises(SystemExit):
            write_batch(target, {"class": "roti"}, force=True)


# ---------------------------------------------------------------------------
# Preservation guarantees
# ---------------------------------------------------------------------------


class TestPreservation:
    def test_core_modules_import(self):
        from training import (  # noqa: F401
            build_v2_review_batches,
            collect_v2,
            licence_policy,
            prepare_v2_dataset,
        )

    def test_production_model_path_is_untouched_by_pipeline(self):
        # The pipeline must only ever write under models/v2/.
        import training.train_v2 as tv

        assert tv.PROTECTED_MODEL == PROTECTED_MODEL
        assert tv.DEFAULT_OUT == ROOT / "models" / "v2"
        assert tv.DEFAULT_OUT != PROTECTED_MODEL.parent

    def test_first_biryani_sample_is_intact(self):
        sample = BIRYANI_REVIEW / "review_sample.json"
        if not sample.exists():
            pytest.skip("biryani review sample not present in this checkout")
        doc = json.loads(sample.read_text(encoding="utf-8"))
        assert doc["sample_size"] == 10
        assert doc["image_bytes_downloaded"] is False
        for image in doc["images"]:
            assert image["usable_for_training"] is False

    def test_collector_default_output_is_under_v4(self):
        from training.collect_v2 import DEFAULT_OUT

        assert "v4" in str(DEFAULT_OUT)
        assert "v3/commons_pilot" not in str(DEFAULT_OUT)


# ---------------------------------------------------------------------------
# Byte-level checks (require Pillow)
# ---------------------------------------------------------------------------


class TestImageBytes:
    def test_corrupt_file_is_rejected(self, tmp_path):
        pytest.importorskip("PIL")
        bad = tmp_path / "bad.jpg"
        bad.write_bytes(b"definitely not a jpeg")
        result = check_image_bytes(bad)
        assert result["ok"] is False
        assert result["reason"].startswith("decode_failed")

    def test_valid_file_passes_and_hashes(self, tmp_path):
        PIL = pytest.importorskip("PIL")
        from PIL import Image

        good = tmp_path / "good.jpg"
        Image.new("RGB", (640, 480), (10, 120, 200)).save(good)
        result = check_image_bytes(good)
        assert result["sha256"] and len(result["sha256"]) == 64
        assert result["dhash"] and len(result["dhash"]) == 16
        assert result["width"] == 640

    def test_near_uniform_image_is_flagged(self, tmp_path):
        pytest.importorskip("PIL")
        from PIL import Image

        flat = tmp_path / "flat.png"
        Image.new("RGB", (400, 400), (255, 255, 255)).save(flat)
        result = check_image_bytes(flat)
        assert "near_uniform_image" in result["reason"]

    def test_undersized_image_is_flagged(self, tmp_path):
        pytest.importorskip("PIL")
        from PIL import Image

        small = tmp_path / "small.jpg"
        Image.new("RGB", (100, 100), (30, 60, 90)).save(small)
        assert "below_min_edge" in check_image_bytes(small)["reason"]


# ---------------------------------------------------------------------------
# Training pipeline guards (import-only; torch is optional)
# ---------------------------------------------------------------------------


class TestTrainingGuards:
    def test_check_dataset_rejects_empty_split(self, tmp_path):
        pytest.importorskip("torch")
        from training.train_v2 import check_dataset

        for split in ("train", "val"):
            (tmp_path / f"split_{split}.json").write_text(json.dumps({
                "split": split, "count": 1,
                "images": [{"pageid": 1, "class": "a", "training_usable": True,
                            "sha1": "s1", "local": {"path": "/tmp/x.jpg"}}],
            }), encoding="utf-8")
        (tmp_path / "split_test.json").write_text(
            json.dumps({"split": "test", "count": 0, "images": []}), encoding="utf-8"
        )
        audit = check_dataset(tmp_path)
        assert audit["ok"] is False
        assert any("test split is empty" in p for p in audit["problems"])

    def test_check_dataset_rejects_cross_split_duplicates(self, tmp_path):
        pytest.importorskip("torch")
        from training.train_v2 import check_dataset

        shared = {"pageid": 1, "class": "a", "training_usable": True,
                  "sha1": "same", "local": {"path": "/tmp/x.jpg"}}
        for split in ("train", "val", "test"):
            (tmp_path / f"split_{split}.json").write_text(json.dumps({
                "split": split, "count": 1, "images": [shared],
            }), encoding="utf-8")
        audit = check_dataset(tmp_path)
        assert audit["ok"] is False
        assert any("spans splits" in p for p in audit["problems"])

    def test_check_dataset_rejects_non_usable_rows(self, tmp_path):
        pytest.importorskip("torch")
        from training.train_v2 import check_dataset

        row = {"pageid": 1, "class": "a", "training_usable": False,
               "sha1": "s", "local": {"path": "/tmp/x.jpg"}}
        for split in ("train", "val", "test"):
            (tmp_path / f"split_{split}.json").write_text(json.dumps({
                "split": split, "count": 1, "images": [row],
            }), encoding="utf-8")
        assert any("not marked training_usable" in p
                   for p in check_dataset(tmp_path)["problems"])

    def test_single_class_is_refused(self, tmp_path):
        pytest.importorskip("torch")
        from training.train_v2 import check_dataset

        row = {"pageid": 1, "class": "only", "training_usable": True,
               "sha1": "s", "local": {"path": "/tmp/x.jpg"}}
        for split in ("train", "val", "test"):
            (tmp_path / f"split_{split}.json").write_text(json.dumps({
                "split": split, "count": 1, "images": [row],
            }), encoding="utf-8")
        assert any("at least 2 classes" in p for p in check_dataset(tmp_path)["problems"])

    def test_majority_baseline(self):
        pytest.importorskip("torch")
        from training.train_v2 import majority_baseline

        train = [{"class": "a"}] * 5 + [{"class": "b"}] * 1
        test = [{"class": "a"}, {"class": "b"}]
        base = majority_baseline(test, train)
        assert base["predicted_class"] == "a"
        assert base["accuracy"] == 0.5

    def test_empty_test_split_gives_no_baseline(self):
        pytest.importorskip("torch")
        from training.train_v2 import majority_baseline

        assert majority_baseline([], [{"class": "a"}])["accuracy"] is None
