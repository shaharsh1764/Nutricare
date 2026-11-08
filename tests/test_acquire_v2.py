"""Tests for the V2 byte acquirer (``training/acquire_v2.py``).

These exercise the real production functions — no reimplementations. Every
test that touches bytes builds genuine PNG data with Pillow, so a decoder
failure means the code under test is wrong, not that the fixture was fake.

The property under test throughout is the same one the review of PR #8
enforced for licences: unknown or unverified content must never be counted as
usable. Here that means a transfer that did not happen is never reported as a
rejection, a thumbnail is never an image, and a permissive licence never
approves a label.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "training"))

from acquire_v2 import (  # noqa: E402
    MIN_BYTES,
    REPORT_COLUMNS,
    acquire_one,
    audit_duplicates,
    download_image,
    is_thumb_url,
    plan_from_seed,
    plan_record,
    render_attempt_report,
    run_acquisition_attempt,
)

pytest.importorskip("PIL", reason="Pillow is required for image byte tests")

from PIL import Image  # noqa: E402


def png_bytes(seed: int = 0, size: tuple[int, int] = (400, 400)) -> bytes:
    """A decodable, non-uniform PNG. Small enough to keep tests fast."""
    img = Image.new("RGB", size, (seed % 256, 40, 90))
    for x in range(0, size[0], 7):
        for y in range(0, size[1], 11):
            img.putpixel((x, y), (255, (x + seed) % 256, y % 256))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def seed_record(cls: str = "biryani", pageid: int = 1, licence: str = "CC0",
                artist: str | None = "Test Author",
                declared_bytes: int = 123456) -> dict:
    """A seed in the same shape the Commons API returns.

    ``declared_bytes`` must be the true size of the payload the opener will
    serve, or the acquirer will (correctly) reject the transfer as a
    substitution.
    """
    ext = {"LicenseShortName": {"value": licence, "source": "commons-desc-page"}}
    if artist is not None:
        ext["Artist"] = {"value": artist, "source": "commons-desc-page"}
    return {
        "class": cls,
        "page": {
            "pageid": pageid,
            "ns": 6,
            "title": f"File:Seed {pageid}.jpg",
            "imageinfo": [{
                "size": declared_bytes,
                "width": 1200,
                "height": 900,
                "sha1": "a" * 40,
                "url": f"https://upload.wikimedia.org/wikipedia/commons/a/ab/Seed_{pageid}.jpg",
                "descriptionurl": f"https://commons.wikimedia.org/wiki/File:Seed_{pageid}.jpg",
                "mime": "image/jpeg",
                "extmetadata": ext,
            }],
        },
    }


class TestDownloadIntegrity:
    def test_valid_image_is_written_and_hashed(self, tmp_path: Path) -> None:
        payload = png_bytes(3)
        dest = tmp_path / "1.png"
        result = download_image("https://example.invalid/a.png", dest,
                                opener=lambda u, t: payload,
                                expected_bytes=len(payload))
        assert result["ok"] is True
        assert dest.read_bytes() == payload
        assert result["sha256"]
        assert (result["width"], result["height"]) == (400, 400)
        assert result["dhash"]

    def test_empty_response_is_rejected_and_leaves_no_file(self, tmp_path: Path) -> None:
        dest = tmp_path / "2.png"
        result = download_image("u", dest, opener=lambda u, t: b"")
        assert result["ok"] is False
        assert result["reason"] == "empty_response"
        assert not dest.exists()

    def test_body_below_floor_is_rejected(self, tmp_path: Path) -> None:
        result = download_image("u", tmp_path / "3.png",
                                opener=lambda u, t: b"x" * (MIN_BYTES - 1))
        assert result["ok"] is False
        assert result["reason"].startswith("too_small")

    def test_truncated_body_fails_declared_size(self, tmp_path: Path) -> None:
        payload = png_bytes(4)
        result = download_image("u", tmp_path / "4.png",
                                opener=lambda u, t: payload[: len(payload) // 2],
                                expected_bytes=len(payload))
        assert result["ok"] is False
        assert result["reason"].startswith("size_mismatch")

    def test_non_image_body_is_deleted_not_kept(self, tmp_path: Path) -> None:
        dest = tmp_path / "5.png"
        junk = b"<!doctype html><h1>404</h1>" + b" " * 4096
        result = download_image("u", dest, opener=lambda u, t: junk)
        assert result["ok"] is False
        assert result["reason"].startswith("decode_failed")
        # An undecodable file must not survive to be miscounted later.
        assert not dest.exists()

    def test_transport_error_is_captured_not_raised(self, tmp_path: Path) -> None:
        def boom(url: str, timeout: float) -> bytes:
            raise OSError("connection reset by peer")

        result = download_image("u", tmp_path / "6.png", opener=boom)
        assert result["ok"] is False
        assert result["reason"].startswith("fetch_failed")

    def test_uniform_image_is_flagged_but_kept_for_inspection(self, tmp_path: Path) -> None:
        blank = Image.new("RGB", (600, 600), (120, 120, 120))
        buf = io.BytesIO()
        blank.save(buf, format="PNG")
        dest = tmp_path / "7.png"
        result = download_image("u", dest, opener=lambda u, t: buf.getvalue())
        assert result["ok"] is False
        assert "near_uniform_image" in result["reason"]
        # Quality judgements keep the file so a human can look at it; only
        # undecodable bytes are discarded.
        assert result.get("kept_for_inspection") is True


class TestThumbnailIsNotAnImage:
    @pytest.mark.parametrize("url", [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/X.jpg/512px-X.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/X.jpg",
        "https://example.org/thumb",
        None,
        "",
    ])
    def test_thumb_or_missing_url_is_flagged(self, url) -> None:
        assert is_thumb_url(url) is True

    def test_original_url_is_not_flagged(self) -> None:
        assert is_thumb_url(
            "https://upload.wikimedia.org/wikipedia/commons/a/ab/X.jpg"
        ) is False

    def test_thumb_record_is_skipped_without_transfer(self, tmp_path: Path) -> None:
        calls: list[str] = []

        def opener(url: str, timeout: float) -> bytes:
            calls.append(url)
            return png_bytes()

        planned = plan_record(
            {"pageid": 9, "title": "File:T.jpg",
             "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/T.jpg/512px-T.jpg",
             "licence": {"declared_class": "CC0_PD", "short_name": "CC0"},
             "attribution": {"artist_raw": "A"}},
            class_slug="idli",
        )
        result = acquire_one(planned, images_dir=tmp_path, opener=opener)
        assert result["acquire_status"] == "skipped_thumb_only"
        assert calls == [], "a thumbnail URL must never be fetched as the image"


class TestRightsAreDelegatedNotReimplemented:
    def test_non_commercial_licence_is_excluded_before_transfer(self, tmp_path: Path) -> None:
        planned = plan_record(
            {"pageid": 1, "title": "File:A.jpg", "url": "https://upload.wikimedia.org/a/ab/A.jpg",
             "licence": {"declared_class": "NC_RESTRICTED", "short_name": "CC BY-NC 4.0"},
             "attribution": {"artist_raw": "Someone"}},
            class_slug="biryani",
        )
        assert planned["rights_tier"] == "EXCLUDED"

        called: list[str] = []
        result = acquire_one(planned, images_dir=tmp_path,
                             opener=lambda u, t: called.append(u) or png_bytes())
        assert result["acquire_status"] == "skipped_rights_excluded"
        assert called == []

    def test_restriction_metadata_flows_through_the_pr8_policy(self) -> None:
        # A restrictive phrase in the Commons Restrictions field must reach the
        # PR #8 classifier and hold the record, not be dropped on the way.
        seed = seed_record(licence="CC0")
        seed["page"]["imageinfo"][0]["extmetadata"]["Restrictions"] = {
            "value": "Trademarked no commercial use", "source": "commons-desc-page"}
        planned = plan_from_seed(seed)
        assert planned["rights_tier"] in ("REVIEW_REQUIRED", "EXCLUDED")

    @pytest.mark.parametrize("licence", ["CC0", "CC BY 4.0", "Public domain"])
    def test_permissive_licence_never_auto_approves(self, licence: str) -> None:
        planned = plan_from_seed(seed_record(licence=licence))
        assert planned["rights_tier"] != "EXCLUDED"
        assert planned["human_review_status"] == "pending"

    def test_plan_record_also_starts_pending(self) -> None:
        """The second planning entry point must agree with the first.

        ``plan_record`` is what ``acquire_one`` is fed by the collector, so a
        permissive licence must not pre-approve a label here either.
        """
        planned = plan_record(
            {"pageid": 5, "title": "File:P.jpg",
             "url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/P.jpg",
             "licence": {"declared_class": "CC0_PD", "short_name": "CC0"},
             "attribution": {"artist_raw": "A"}},
            class_slug="idli",
        )
        assert planned["rights_tier"] == "TRAINING_APPROVED"
        assert planned["human_review_status"] == "pending"

    def test_missing_author_is_recorded_not_invented(self) -> None:
        planned = plan_from_seed(seed_record(artist=None))
        # No author is recorded, and none is invented to fill the gap.
        assert not planned["author"]
        assert "assumed" not in str(planned["author"]).lower()
        assert planned["human_review_status"] == "pending"


class TestDuplicateAudit:
    def test_byte_identical_copies_are_counted_once(self, tmp_path: Path) -> None:
        payload = png_bytes(1)
        rows = []
        for pid in (1, 2):
            path = tmp_path / f"{pid}.png"
            path.write_bytes(payload)
            rows.append({"pageid": pid, "acquire_status": "downloaded",
                         "local_sha256": _sha(path), "integrity": {"dhash": "0" * 16}})
        audit = audit_duplicates(rows)
        assert audit["downloaded"] == 2
        assert audit["exact_duplicate_extra_copies"] == 1
        assert audit["unique_by_content"] == 1

    def test_failed_transfers_never_form_duplicates(self) -> None:
        rows = [
            {"pageid": 1, "acquire_status": "failed", "local_sha256": "same",
             "integrity": {"dhash": "0000000000000000"}},
            {"pageid": 2, "acquire_status": "failed", "local_sha256": "same",
             "integrity": {"dhash": "0000000000000000"}},
        ]
        audit = audit_duplicates(rows)
        assert audit["downloaded"] == 0
        assert audit["exact_duplicate_extra_copies"] == 0
        assert audit["near_duplicate_pairs"] == []

    def test_empty_audit_is_zeroed_not_missing(self) -> None:
        audit = audit_duplicates([])
        assert audit == {"downloaded": 0, "exact_duplicate_groups": {},
                         "exact_duplicate_extra_copies": 0,
                         "near_duplicate_pairs": [], "unique_by_content": 0}


class TestAcquisitionReport:
    def _seeds(self, tmp_path: Path) -> Path:
        size = len(png_bytes())
        records = [seed_record("biryani", 1, declared_bytes=size),
                   seed_record("biryani", 2, declared_bytes=size),
                   seed_record("idli", 3, declared_bytes=size)]
        path = tmp_path / "seeds.json"
        path.write_text(json.dumps({"records": records}))
        return path

    def test_every_required_column_is_present(self, tmp_path: Path) -> None:
        report = run_acquisition_attempt(
            self._seeds(tmp_path), out_dir=tmp_path / "out",
            images_dir=tmp_path / "img", opener=lambda u, t: png_bytes(),
        )
        assert set(REPORT_COLUMNS) <= set(report["totals"])
        for slug, row in report["per_class"].items():
            assert set(REPORT_COLUMNS) <= set(row), slug

    def test_successful_transfer_keeps_review_pending(self, tmp_path: Path) -> None:
        report = run_acquisition_attempt(
            self._seeds(tmp_path), out_dir=tmp_path / "out",
            images_dir=tmp_path / "img", opener=lambda u, t: png_bytes(),
        )
        assert report["totals"]["images_downloaded"] == 3
        assert report["totals"]["passing_integrity"] == 3
        # Downloaded but unreviewed: usable count stays 0.
        assert report["totals"]["final_usable"] == 0
        assert report["totals"]["awaiting_human_review"] == 3

    def test_network_failure_is_not_a_quality_rejection(self, tmp_path: Path) -> None:
        """Regression: a failed fetch must never be reported as a rejection.

        Counting unreachable images as "rejected for quality" would invent
        judgements about photographs nobody ever saw.
        """
        def boom(url: str, timeout: float) -> bytes:
            raise OSError("TLS closed")

        report = run_acquisition_attempt(
            self._seeds(tmp_path), out_dir=tmp_path / "out",
            images_dir=tmp_path / "img", opener=boom,
        )
        totals = report["totals"]
        assert totals["images_downloaded"] == 0
        assert totals["rejected_irrelevant_or_quality"] == 0
        assert totals["final_usable"] == 0
        assert all(row["_transfer_failed"] == row["images_discovered"]
                   for row in report["per_class"].values())

    def test_no_download_still_reports_zeroed_download_columns(self, tmp_path: Path) -> None:
        report = run_acquisition_attempt(
            self._seeds(tmp_path), out_dir=tmp_path / "out", download=False,
        )
        assert report["download_attempted"] is False
        assert report["totals"]["images_discovered"] == 3
        assert report["totals"]["images_downloaded"] == 0

    def test_report_states_final_usable_is_zero(self, tmp_path: Path) -> None:
        report = run_acquisition_attempt(
            self._seeds(tmp_path), out_dir=tmp_path / "out",
            images_dir=tmp_path / "img", opener=lambda u, t: png_bytes(),
        )
        text = render_attempt_report(report)
        assert "Final usable images: 0" in text
        assert "not a training count" in text

    def test_limit_per_class_is_respected(self, tmp_path: Path) -> None:
        report = run_acquisition_attempt(
            self._seeds(tmp_path), out_dir=tmp_path / "out",
            images_dir=tmp_path / "img", opener=lambda u, t: png_bytes(),
            limit_per_class=1,
        )
        assert report["per_class"]["biryani"]["images_discovered"] == 1

    def test_output_file_is_written(self, tmp_path: Path) -> None:
        out = tmp_path / "out"
        run_acquisition_attempt(self._seeds(tmp_path), out_dir=out,
                                images_dir=tmp_path / "img", download=False)
        written = json.loads((out / "acquisition_attempt.json").read_text())
        assert written["totals"]["final_usable"] == 0


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
