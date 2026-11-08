"""Regression tests for the findings in ``docs/PR8_FINAL_REVIEW.md``.

Each test here pins a *protection*, not merely a helper's return value, so that
deleting or weakening the protection makes a test fail. The three end-to-end
safety tests (``TestH2EndToEndSafetyGates``) deliberately call the real
production functions — :func:`training.prepare_v2_dataset.prepare` and
:func:`training.train_v2.train` — rather than checking a constant or a pure
helper, because that is exactly why the previous review found them unprotected.

Finding map:

* **C-1** restrictive licence descriptions must never be auto-approved;
* **H-1** placeholder author identities must not satisfy an attribution licence;
* **H-2** the review gate, the bytes gate and the model-overwrite guard;
* **M-1** "Screenshot of a website" is descriptive, not evidence of scraping;
* **M-2** the checkpoint guard must protect the real production path;
* **L-1** hosting-destination provenance (Imgur/Photobucket) is scraping evidence;
* **L-2** the ``strip_markup`` contract.
"""

from __future__ import annotations

import io
import json
import sys
import contextlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "training"))

from training.commons_audit import (  # noqa: E402
    build_file_record,
    classify_licence,
    em,
    strip_markup,
)
from training.collect_v2 import _FakeClient, _fake_page, collect_class, enrich  # noqa: E402
from training.licence_policy import (  # noqa: E402
    EXCLUDED,
    REVIEW_REQUIRED,
    TRAINING_APPROVED,
    classify_provenance,
    classify_rights,
    has_restrictive_modifier,
    is_bare_cc0,
    is_placeholder_author,
)
from training.prepare_v2_dataset import prepare  # noqa: E402

PRODUCTION_MODEL = ROOT / "models" / "food_classifier_cc0.pt"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _rights(short_name, declared="CC0_PD", artist="", usage_terms=""):
    licence = {"declared_class": declared, "short_name": short_name}
    if usage_terms:
        licence["usage_terms"] = usage_terms
    return classify_rights(licence, artist=artist)


def _record(pageid, sha1=None, tier=TRAINING_APPROVED, artist="John Smith"):
    """A collect_v2-shaped record as prepare() consumes it."""
    rights = {
        "rights_tier": tier,
        "attribution_sufficient": True,
        "declared_class": "CC0_PD",
    }
    return {
        "pageid": pageid,
        "title": f"File:Test {pageid}.jpg",
        "sha1": sha1 or f"sha1-{pageid}",
        "width": 1200,
        "height": 900,
        "mime": "image/jpeg",
        "description_url": f"https://commons.wikimedia.org/wiki/File:Test_{pageid}.jpg",
        "licence": {"declared_class": "CC0_PD", "short_name": "CC0"},
        "attribution": {"artist_raw": artist, "attribution_required": False},
        "technical_flags": [],
        "metadata_gaps": [],
        "rights": rights,
    }


def _approval(pageid):
    return {"pageid": pageid, "relevance": "relevant", "quality": "good", "flags": {}}


def _jpeg(path):
    """Write a minimal but valid 200x200 JPEG so check_image_bytes passes."""
    Image = pytest.importorskip("PIL.Image")
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (400, 400), (120, 80, 40)).save(path, "JPEG")
    return path


# ---------------------------------------------------------------------------
# C-1 — restrictive licence descriptions
# ---------------------------------------------------------------------------


class TestC1RestrictiveLicenceDescriptions:
    """A CC0 label must not override conditions attached to it."""

    @pytest.mark.parametrize(
        "short_name",
        [
            "CC0 but no commercial use",
            "CC0 with restrictions",
            "CC0 plus additional restrictive conditions",
            "CC0 with additional conditions",
            "CC0 non-commercial",
            "CC0-NC",
            "CC0 but not for resale",
            "CC0, permission required for commercial use",
        ],
    )
    def test_restrictive_cc0_is_never_approved(self, short_name):
        out = _rights(short_name)
        assert out["rights_tier"] != TRAINING_APPROVED, short_name
        # Conservative: contradictory wording is excluded outright rather than
        # deferred, so a later reviewer cannot approve it on the CC0 prefix.
        assert out["rights_tier"] == EXCLUDED, short_name

    @pytest.mark.parametrize(
        "short_name",
        [
            "CC0",
            "CC0 1.0",
            "CC0 1.0 Universal",
            "CC0 1.0 Universal (CC0 1.0)",
            "CC0 1.0 Universal (CC0 1.0) Public Domain Dedication",
            "cc-zero",
            "Cc0",
            "CC0 Public Domain Dedication",
        ],
    )
    def test_genuine_cc0_still_approved(self, short_name):
        assert _rights(short_name)["rights_tier"] == TRAINING_APPROVED, short_name

    def test_cc0_rationale_is_recorded(self):
        out = _rights("CC0 with restrictions")
        assert out["rights_tier"] == EXCLUDED
        assert any("restrictive conditions" in r for r in out["reasons"])

    @pytest.mark.parametrize(
        "short_name",
        ["PD-USGov", "PD-Art", "PD-old", "PD-India", "PD-self", "Public domain"],
    )
    def test_public_domain_handling_preserved(self, short_name):
        # PD families stay deferred to human review, never auto-approved and
        # never silently excluded.
        out = _rights(short_name)
        assert out["rights_tier"] == REVIEW_REQUIRED, short_name
        assert out["public_domain_designation"] is not None

    def test_restrictive_cc0_reachable_end_to_end(self):
        """The real collection path must not auto-approve a contradictory CC0."""
        tree = {
            "Category:Test": {
                "files": [{"title": "File:A.jpg"}],
                "subcats": [],
                "pages": [
                    _fake_page(
                        "File:A.jpg", 1, "s1", "CC0 with restrictions", "A Person"
                    )
                ],
            }
        }
        doc = collect_class(
            _FakeClient(tree), {"slug": "test", "commons_categories": ["Category:Test"]}
        )
        assert doc["files"][0]["rights"]["rights_tier"] == EXCLUDED
        assert doc["counts"]["3_rights_supported"] == 0

    def test_restrictive_modifier_detection_scope(self):
        assert has_restrictive_modifier("CC0 with restrictions")
        assert has_restrictive_modifier("non-commercial use only")
        assert has_restrictive_modifier("no derivatives permitted")
        # A plain dedication carries no modifier.
        assert not has_restrictive_modifier("CC0 1.0 Universal")
        assert not has_restrictive_modifier("")
        # Descriptive prose is not a licence modifier.
        assert not has_restrictive_modifier("A bowl of sambar with rice")

    def test_is_bare_cc0_requires_whole_label(self):
        assert is_bare_cc0("CC0 1.0 Universal")
        assert not is_bare_cc0("CC0 with restrictions")
        assert not is_bare_cc0("CC BY 4.0")
        assert not is_bare_cc0("")

    @pytest.mark.parametrize(
        "short_name",
        [
            # Trailing content that carries no *modifier* keyword, so the
            # modifier check cannot catch it: only the whole-label test can.
            # Prefix matching would approve every one of these.
            "CC0 - see terms below",
            "CC0 courtesy of the uploader",
            "CC0 (attribution appreciated)",
            "CC0 as described elsewhere",
            "CC0 terms apply",
            "CC0 for this image only",
        ],
    )
    def test_cc0_with_unassessed_trailing_text_is_not_approved(self, short_name):
        assert has_restrictive_modifier(short_name) is False, (
            "this case must exercise the whole-label rule, not the modifier rule"
        )
        assert is_bare_cc0(short_name) is False, short_name
        assert _rights(short_name)["rights_tier"] == EXCLUDED, short_name

    @pytest.mark.parametrize(
        "short_name",
        [
            # "of"/"to" trailing a CC0 label must not be mistaken for a copy
            # verb ("copied from", "uploaded to"). The file is still held out by
            # the whole-label rule, but it must be excluded on licence grounds,
            # not flagged as scraped: a scrape signal here would be a false
            # positive that misdescribes legitimate provenance.
            "CC0, courtesy of the photographer",
        ],
    )
    def test_cc0_qualifier_is_not_flagged_as_scraping(self, short_name):
        assert is_bare_cc0(short_name) is False  # held out, conservatively
        out = _rights(short_name)
        assert out["rights_tier"] == EXCLUDED
        assert out["provenance_strength"] != "scrape_risk"
        assert out["provenance_signals"] == []


# ---------------------------------------------------------------------------
# H-1 — placeholder author identities
# ---------------------------------------------------------------------------


class TestH1PlaceholderAuthors:
    """A non-empty string is not necessarily an identity."""

    @pytest.mark.parametrize(
        "artist",
        [
            "unknown",
            "Unknown",
            "UNKNOWN",
            "unknown author",
            "N/A",
            "n/a",
            "N.A.",
            "N / A",
            "none",
            "None",
            "-",
            "\u2014",
            "",
            "   ",
            "\t\n",
            "\u200b",          # zero-width space
            "\u200b\u200b",
            "\ufeff",          # BOM
            "\u00ad",          # soft hyphen
            "Anonymous",
            "anon",
            "nil",
            "null",
            "not applicable",
            "not stated",
            "no author",
        ],
    )
    def test_placeholder_never_satisfies_attribution(self, artist):
        out = _rights("CC BY 4.0", declared="CC_BY", artist=artist)
        assert out["rights_tier"] == EXCLUDED, repr(artist)
        assert out["attribution_sufficient"] is False, repr(artist)

    @pytest.mark.parametrize(
        "artist",
        [
            "John Smith",
            "Anonymouse",                       # real Commons username
            "Alpha from Melbourne, Australia",
            "Randhirreddy at English Wikipedia",
            "Nikhil",
            "N A",                              # initials, not "N/A"
            "12345",
            "Wikimedia Commons",
            "Unknown Soldier Memorial Trust",   # legitimate name containing 'unknown'
        ],
    )
    def test_legitimate_names_still_accepted(self, artist):
        out = _rights("CC BY 4.0", declared="CC_BY", artist=artist)
        assert out["rights_tier"] == TRAINING_APPROVED, artist
        assert out["attribution_sufficient"] is True

    def test_placeholder_flag_is_exposed(self):
        assert _rights("CC BY 4.0", declared="CC_BY", artist="N/A")["author_is_placeholder"]
        assert not _rights("CC BY 4.0", declared="CC_BY", artist="Real Name")[
            "author_is_placeholder"
        ]

    @pytest.mark.parametrize("artist", ["unknown", "N/A", "-", "\u200b"])
    def test_cc_by_sa_placeholder_excluded(self, artist):
        out = _rights("CC BY-SA 4.0", declared="CC_BY_SA", artist=artist)
        assert out["rights_tier"] == EXCLUDED
        assert out["attribution_sufficient"] is False

    def test_cc0_does_not_require_an_author(self):
        # A placeholder author must not make a valid CC0 dedication unusable:
        # CC0 waives attribution entirely.
        assert _rights("CC0", artist="")["rights_tier"] == TRAINING_APPROVED
        assert _rights("CC0", artist="N/A")["rights_tier"] == TRAINING_APPROVED

    def test_placeholder_is_handled_for_non_string_values(self):
        assert is_placeholder_author(None) is True
        assert is_placeholder_author(["A", "B"]) is True
        assert is_placeholder_author({"value": "A"}) is False
        assert is_placeholder_author(123) is False

    @pytest.mark.parametrize("artist", ["unknown", "N/A", "\u200b"])
    def test_placeholder_reachable_end_to_end(self, artist):
        """Through build_file_record -> enrich, a placeholder must not approve."""
        page = {
            "pageid": 7,
            "title": "File:P.jpg",
            "imageinfo": [
                {
                    "sha1": "s7",
                    "width": 1200,
                    "height": 900,
                    "mime": "image/jpeg",
                    "url": "u",
                    "descriptionurl": "d",
                    "extmetadata": {
                        "LicenseShortName": {"value": "CC BY 4.0"},
                        "Artist": {"value": artist},
                    },
                }
            ],
        }
        record = enrich(build_file_record("File:P.jpg", page, [], []))
        assert record["rights"]["rights_tier"] == EXCLUDED, repr(artist)


# ---------------------------------------------------------------------------
# H-2 — end-to-end safety gates
# ---------------------------------------------------------------------------


class TestH2EndToEndSafetyGates:
    """The protections that matter most, exercised through production code.

    Each of these fails if its protection is deleted — verified by mutation in
    the implementation report.
    """

    def test_unreviewed_is_never_training_usable(self, tmp_path):
        """The human-review gate inside prepare(), not a helper."""
        docs = [{"class": "roti", "counts": {}, "files": [_record(1), _record(2)]}]
        report = prepare(docs, reviews={}, images_dir=tmp_path)

        assert report["totals"]["usable_images"] == 0
        for row in report["rows"]:
            assert "review:unreviewed" in row["exclusion_reasons"]
            assert row["training_usable"] is False

    def test_approved_without_bytes_is_never_training_usable(self, tmp_path):
        """The bytes gate inside prepare(), not a helper."""
        docs = [{"class": "roti", "counts": {}, "files": [_record(1), _record(2)]}]
        reviews = {1: _approval(1), 2: _approval(2)}

        # images_dir is None: no bytes are available at all.
        report = prepare(docs, reviews=reviews, images_dir=None)
        assert report["totals"]["usable_images"] == 0
        for row in report["rows"]:
            assert "bytes_missing" in row["exclusion_reasons"]
            assert row["training_usable"] is False

        # images_dir exists but holds no file for this record.
        report2 = prepare(docs, reviews=reviews, images_dir=tmp_path)
        assert report2["totals"]["usable_images"] == 0
        for row in report2["rows"]:
            assert "bytes_missing" in row["exclusion_reasons"]

    def test_positive_control_review_and_bytes_yield_usable(self, tmp_path):
        """Guard against the two tests above passing for the wrong reason.

        With bytes present and a review approval, the row *must* become usable.
        Without this control, deleting the rights gate as well would make the
        negative tests pass trivially.
        """
        Image = pytest.importorskip("PIL.Image")
        docs = [
            {
                "class": "roti",
                "counts": {},
                "files": [_record(1, sha1="sha-unique-1"), _record(2, sha1="sha-unique-2")],
            }
        ]
        images = tmp_path / "images"
        for pageid in (1, 2):
            _jpeg(images / f"{pageid}.jpg")
        report = prepare(
            docs,
            reviews={1: _approval(1), 2: _approval(2)},
            images_dir=images,
        )
        usable = [r for r in report["rows"] if r["training_usable"]]
        assert usable, [r["exclusion_reasons"] for r in report["rows"]]

    def test_train_refuses_to_write_into_models_directory(self):
        """The model-overwrite guard in the real checkpoint path.

        Asserts the *specific* refusal message, not just the exit code. Exit
        code 2 is also returned by the missing-dependency path, so a test that
        only checked ``rc == 2`` would pass in the base environment even with
        the guard deleted (that was finding M-3).
        """
        tv = pytest.importorskip("training.train_v2")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = tv.train(Path("/nonexistent-dataset"), Path("/nonexistent-images"),
                          out_dir=Path("models"))
        message = err.getvalue().lower()
        assert rc == 2
        assert "refusing to write into models" in message, (
            f"expected the production-model refusal, got: {message!r}"
        )
        # Distinguish this from the missing-torch path, which also returns 2.
        assert "missing ml dependency" not in message

    def test_train_refuses_out_pointing_at_production_model(self):
        tv = pytest.importorskip("training.train_v2")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = tv.train(
                Path("/nonexistent-dataset"),
                Path("/nonexistent-images"),
                out_dir=PRODUCTION_MODEL,
            )
        message = err.getvalue().lower()
        assert rc == 2
        assert "refusing" in message
        assert "production model file itself" in message
        assert "missing ml dependency" not in message

    def test_train_refusal_happens_before_any_data_access(self):
        """The guard must fire before the dataset is read or any directory is
        created, so a bad --out cannot leave artefacts behind or overwrite
        something before failing."""
        tv = pytest.importorskip("training.train_v2")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = tv.train(Path("/nonexistent-dataset"), Path("/nonexistent-images"),
                          out_dir=Path("models"))
        assert rc == 2
        # A missing dataset would raise SystemExit or return 3; the specific
        # refusal string proves the guard ran first.
        assert "refusing to write into models" in err.getvalue().lower()

    def test_guard_reports_before_creating_any_output_directory(self, tmp_path, monkeypatch):
        """Behavioural proof that resolution happens before mkdir.

        ``mkdir`` is replaced with a sentinel so the test does not depend on
        whether torch is installed: if the guard were moved after directory
        creation, or removed, the sentinel would fire.
        """
        tv = pytest.importorskip("training.train_v2")
        created = []
        monkeypatch.setattr(
            tv.Path, "mkdir", lambda self, *a, **k: created.append(str(self)), raising=False
        )
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = tv.train(Path("/nonexistent-dataset"), Path("/nonexistent-images"),
                          out_dir=PRODUCTION_MODEL.parent)
        message = err.getvalue().lower()
        assert rc == 2
        # The refusal must be the reason, not the missing-dependency path.
        assert "refusing to write into models" in message, message
        assert "missing ml dependency" not in message
        assert created == [], f"mkdir was called before the refusal: {created}"

# ---------------------------------------------------------------------------
# M-1 / L-1 — screenshot and hosting provenance
# ---------------------------------------------------------------------------


class TestM1ScreenshotIsNotAutomaticallyScraping:
    """A screenshot is an image type; capturing a media work is copying."""

    @pytest.mark.parametrize(
        "text",
        [
            "Screenshot of a website",
            "Screenshot of the menu",
            "Screenshot of the app",
            "Screenshot of the user interface",
            "Screenshot of the restaurant's webpage",
            "Screenshot",
        ],
    )
    def test_ui_capture_is_not_scraping(self, text):
        assert classify_provenance(credit_text=text)["strength"] != "scrape_risk", text

    @pytest.mark.parametrize(
        "text",
        [
            "Screenshot of a video",
            "Screenshot from YouTube",
            "Screenshot of the film",
            "Screenshot taken from a movie",
            "Screen grab of the film",
            "Captured from a video",
        ],
    )
    def test_media_capture_is_scraping(self, text):
        assert classify_provenance(credit_text=text)["strength"] == "scrape_risk", text

    def test_screenshot_does_not_change_a_cc0_tier(self):
        out = classify_rights(
            {"declared_class": "CC0_PD", "short_name": "CC0"},
            credit_text="Screenshot of a website",
        )
        assert out["rights_tier"] == TRAINING_APPROVED

    def test_media_screenshot_excludes_a_cc0_file(self):
        out = classify_rights(
            {"declared_class": "CC0_PD", "short_name": "CC0"},
            credit_text="Screenshot from YouTube",
        )
        assert out["rights_tier"] == EXCLUDED


class TestL1HostingDestination:
    """Anonymous image dumps are evidence of re-upload; attribution routes are not."""

    @pytest.mark.parametrize(
        "text",
        [
            "Uploaded to Imgur",
            "Uploaded on Imgur",
            "Hosted on Photobucket",
            "Posted to Tinypic",
            "Uploaded to a blog",
            "uploaded to the web",
        ],
    )
    def test_anonymous_hosting_is_scraping(self, text):
        assert classify_provenance(credit_text=text)["strength"] == "scrape_risk", text

    @pytest.mark.parametrize(
        "text",
        [
            "Uploaded to Flickr by A Photographer",
            "photo uploaded to Flickr by Ranjith",
            "Uploaded to Commons",
            "Uploaded by Perumalism",
            "Uploaded to Wikimedia Commons",
            "Photo by X on Flickr",
            "Flickr",
        ],
    )
    def test_attribution_bearing_hosting_is_not_scraping(self, text):
        # Flickr is why this matters: Commons' Flickr review imports use the
        # credit line "uploaded to Flickr by <author>", which is attributable
        # provenance, not an anonymous dump.
        assert classify_provenance(credit_text=text)["strength"] != "scrape_risk", text

    def test_platform_mention_alone_is_still_not_scraping(self):
        for text in ["Instagram", "Pinterest", "Facebook", "Reddit"]:
            assert classify_provenance(credit_text=text)["strength"] != "scrape_risk", text


# ---------------------------------------------------------------------------
# L-2 — strip_markup contract
# ---------------------------------------------------------------------------


class TestL2StripMarkupContract:
    """Pin strip_markup so a future revert to str() is caught."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("", ""),
            ("Plain", "Plain"),
            ("<b>Bold</b>", "Bold"),
            ("<a href='x'>Link</a>", "Link"),
            ("  spaced  ", "spaced"),
            ("A &amp; B", "A & B"),
            ("Line<br/>break", "Line break"),
            ("multi\n\nline", "multi line"),
            (123, "123"),
            (1.5, "1.5"),
        ],
    )
    def test_scalar_values(self, value, expected):
        assert strip_markup(value) == expected

    @pytest.mark.parametrize(
        "value",
        [
            None,
            ["A", "B"],
            [],
            {"value": "A"},
            {},
            True,
            False,
            object(),
        ],
    )
    def test_malformed_values_return_empty(self, value):
        # A list must never render as "['A', 'B']": that string is non-empty and
        # would be accepted as a valid attribution downstream.
        assert strip_markup(value) == ""

    def test_list_value_is_not_rendered_as_attribution(self):
        rendered = strip_markup(["Alpha", "Beta"])
        assert "[" not in rendered and "Alpha" not in rendered
        assert rendered == ""

    def test_em_returns_empty_for_non_scalar_entry(self):
        assert em({"Artist": {"value": ["A", "B"]}}, "Artist") == ""
        assert em({"Artist": {"value": True}}, "Artist") == ""
        assert em({"Artist": {"value": 42}}, "Artist") == "42"
        assert em({"Artist": {"value": "<i>Real Name</i>"}}, "Artist") == "Real Name"
        assert em(None, "Artist") == ""
        assert em({}, "Artist") == ""

    def test_list_author_does_not_become_usable_attribution(self):
        """The original defect: a list author passed as attribution."""
        page = {
            "pageid": 9,
            "title": "File:L.jpg",
            "imageinfo": [
                {
                    "sha1": "s9",
                    "width": 1200,
                    "height": 900,
                    "mime": "image/jpeg",
                    "url": "u",
                    "descriptionurl": "d",
                    "extmetadata": {
                        "LicenseShortName": {"value": "CC BY 4.0"},
                        "Artist": {"value": ["A", "B"]},
                    },
                }
            ],
        }
        record = enrich(build_file_record("File:L.jpg", page, [], []))
        assert record["rights"]["rights_tier"] == EXCLUDED
        assert record["attribution"]["artist_raw"] == ""

    def test_classify_licence_survives_malformed_extmetadata(self):
        # Must not raise: one malformed file must not abort a class.
        for ext in [
            {"LicenseShortName": {"value": ["CC0"]}},
            {"LicenseShortName": {"value": {"nested": "x"}}},
            {"LicenseShortName": "bare string"},
            {"LicenseShortName": {"value": True}},
        ]:
            out = classify_licence(ext)
            assert out["declared_class"] in {
                "CC0_PD", "CC_BY", "CC_BY_SA", "NC_RESTRICTED",
                "ND_RESTRICTED", "UNKNOWN_MISSING", "OTHER_REVIEW",
            }


# ---------------------------------------------------------------------------
# Round 3 findings (H-1a, M-3, M-2, M-1, M-4)
# ---------------------------------------------------------------------------


class TestH1aPunctuationOnlyAuthors:
    """An identity must contain a letter or digit; punctuation names nobody."""

    @pytest.mark.parametrize(
        "artist",
        ["--", "?", "...", "==", "[]", "()", "**", "_", "/", "\\\\", "|", "~~~",
         "---", "?!", "…", "·", "\u2014\u2014", "  --  "],
    )
    def test_punctuation_only_is_rejected(self, artist):
        assert is_placeholder_author(artist) is True, repr(artist)

    @pytest.mark.parametrize(
        "artist",
        ["N A", "N.A. Smith", "-John-", "O'Brien, Sean", "李小龙", "Anonymouse",
         "John Smith", "12345", "a", "María González", "J. R. R. Tolkien"],
    )
    def test_legitimate_identities_are_accepted(self, artist):
        assert is_placeholder_author(artist) is False, repr(artist)

    @pytest.mark.parametrize("artist", ["--", "?", "...", "==", "[]"])
    def test_punctuation_author_fails_cc_by_end_to_end(self, artist):
        """Through build_file_record -> enrich, not just the helper."""
        page = {
            "pageid": 11,
            "title": "File:C.jpg",
            "imageinfo": [{
                "sha1": "s11", "width": 1200, "height": 900,
                "mime": "image/jpeg", "url": "u", "descriptionurl": "d",
                "extmetadata": {
                    "LicenseShortName": {"value": "CC BY 4.0"},
                    "Artist": {"value": artist},
                },
            }],
        }
        record = enrich(build_file_record("File:C.jpg", page, [], []))
        assert record["rights"]["rights_tier"] == EXCLUDED, repr(artist)
        assert record["rights"]["attribution_sufficient"] is False

    @pytest.mark.parametrize("artist", ["N A", "-John-", "O'Brien, Sean", "李小龙"])
    def test_legitimate_identity_passes_cc_by_end_to_end(self, artist):
        page = {
            "pageid": 12,
            "title": "File:D.jpg",
            "imageinfo": [{
                "sha1": "s12", "width": 1200, "height": 900,
                "mime": "image/jpeg", "url": "u", "descriptionurl": "d",
                "extmetadata": {
                    "LicenseShortName": {"value": "CC BY 4.0"},
                    "Artist": {"value": artist},
                },
            }],
        }
        record = enrich(build_file_record("File:D.jpg", page, [], []))
        assert record["rights"]["rights_tier"] == TRAINING_APPROVED, repr(artist)


class TestM2RestrictionsMetadata:
    """The Commons Restrictions field must survive and must affect the tier."""

    @pytest.mark.parametrize(
        "restrictions",
        ["no commercial use", "No derivatives", "All rights reserved",
         "non-commercial", "fair use", "no redistribution"],
    )
    def test_licence_restriction_blocks_approval(self, restrictions):
        out = classify_rights(
            {"declared_class": "CC0_PD", "short_name": "CC0", "restrictions": restrictions}
        )
        assert out["rights_tier"] == EXCLUDED, restrictions
        assert out["restrictions_kind"] == "licence"
        assert out["restrictions"] == restrictions  # preserved verbatim

    @pytest.mark.parametrize(
        "restrictions", ["trademarked", "personality rights", "privacy"]
    )
    def test_non_copyright_caveat_does_not_block_but_is_recorded(self, restrictions):
        out = classify_rights(
            {"declared_class": "CC0_PD", "short_name": "CC0", "restrictions": restrictions}
        )
        # Not a licence term, so it does not exclude; but it is kept visible.
        assert out["rights_tier"] == TRAINING_APPROVED
        assert out["restrictions_kind"] == "other"
        assert out["restrictions"] == restrictions
        assert any("not a licence term" in r for r in out["reasons"])

    @pytest.mark.parametrize("restrictions", ["", "   ", None])
    def test_empty_restrictions_are_benign(self, restrictions):
        out = classify_rights(
            {"declared_class": "CC0_PD", "short_name": "CC0", "restrictions": restrictions}
        )
        assert out["rights_tier"] == TRAINING_APPROVED
        assert out["restrictions_kind"] == "none"

    def test_unclassified_text_is_held_for_review(self):
        out = classify_rights(
            {"declared_class": "CC0_PD", "short_name": "CC0",
             "restrictions": "some vague note about usage"}
        )
        # Not assumed benign, not assumed restrictive: deferred to a human.
        assert out["rights_tier"] == REVIEW_REQUIRED
        assert out["restrictions_kind"] == "text"

    def test_restrictions_survive_commons_audit(self):
        out = classify_licence(
            {"LicenseShortName": {"value": "CC0"},
             "Restrictions": {"value": "no commercial use"}}
        )
        assert out["restrictions"] == "no commercial use"

    @pytest.mark.parametrize(
        "restrictions,expected_tier",
        [("no commercial use", EXCLUDED), ("No derivatives", EXCLUDED),
         ("All rights reserved", EXCLUDED), ("trademarked", TRAINING_APPROVED),
         ("personality rights", TRAINING_APPROVED), (None, TRAINING_APPROVED)],
    )
    def test_restrictions_end_to_end(self, restrictions, expected_tier):
        ext = {"LicenseShortName": {"value": "CC0"}}
        if restrictions:
            ext["Restrictions"] = {"value": restrictions}
        page = {
            "pageid": 13, "title": "File:R.jpg",
            "imageinfo": [{
                "sha1": "s13", "width": 1200, "height": 900,
                "mime": "image/jpeg", "url": "u", "descriptionurl": "d",
                "extmetadata": ext,
            }],
        }
        record = enrich(build_file_record("File:R.jpg", page, [], []))
        assert record["rights"]["rights_tier"] == expected_tier, restrictions

    def test_restriction_beats_a_permissive_label(self):
        """A recorded restriction must not be overridden by the short_name."""
        for short in ["CC0", "CC BY 4.0"]:
            declared = "CC0_PD" if short == "CC0" else "CC_BY"
            out = classify_rights(
                {"declared_class": declared, "short_name": short,
                 "restrictions": "no commercial use"},
                artist="A Person",
            )
            assert out["rights_tier"] == EXCLUDED, short


class TestM1PhotographicDescriptions:
    """Everyday camera language must not be read as evidence of copying."""

    @pytest.mark.parametrize(
        "text",
        ["Photo taken from above", "Taken from the kitchen", "Pulled from the tandoor",
         "Retrieved from the menu", "Taken from an angle", "Pulled from the oven",
         "Saved from the freezer", "Grabbed from the counter",
         "Retrieved from the market", "Photo taken from the roof of the restaurant",
         "Taken from a low angle", "Pulled from the tawa"],
    )
    def test_photographic_description_is_not_scraping(self, text):
        assert classify_provenance(credit_text=text)["strength"] != "scrape_risk", text

    @pytest.mark.parametrize(
        "text",
        ["Copied from a website", "Ripped from a DVD", "Downloaded from the internet",
         "Taken from a website", "Taken from the web", "Pulled from a blog",
         "Retrieved from Facebook", "Sourced from Google", "Taken from a book",
         "Copied from Imgur", "Grabbed from a blog", "Saved from a website",
         "Obtained from the internet", "Taken from Wikipedia"],
    )
    def test_genuine_copying_is_still_scraping(self, text):
        assert classify_provenance(credit_text=text)["strength"] == "scrape_risk", text

    def test_photographic_description_does_not_exclude_a_cc0_file(self):
        out = classify_rights(
            {"declared_class": "CC0_PD", "short_name": "CC0"},
            credit_text="Photo taken from above",
        )
        assert out["rights_tier"] == TRAINING_APPROVED

    def test_genuine_copying_still_excludes(self):
        out = classify_rights(
            {"declared_class": "CC0_PD", "short_name": "CC0"},
            credit_text="Copied from a website",
        )
        assert out["rights_tier"] == EXCLUDED


class TestM4DatasetPathValidation:
    """The manifest must point at real, readable image files."""

    @staticmethod
    def _manifest(tmp_path, rows):
        """Write the same rows to each split, with sha1 rewritten per split.

        Rewriting keeps the leakage check out of the way so these tests fail
        only for path reasons.
        """
        for split in ("train", "val", "test"):
            copy = [dict(r, sha1=f"{split}-{r['sha1']}") for r in rows]
            (tmp_path / f"split_{split}.json").write_text(
                json.dumps({"split": split, "count": len(copy), "images": copy})
            )

    @staticmethod
    def _row(pageid, cls, sha1, path):
        return {"pageid": pageid, "class": cls, "training_usable": True,
                "sha1": sha1, "local": {"path": path}}

    def _image(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xff\xd8\xff\xe0" + b"x" * 64)
        return path

    def test_valid_paths_pass(self, tmp_path):
        tv = pytest.importorskip("training.train_v2")
        a = self._image(tmp_path / "a.jpg")
        b = self._image(tmp_path / "b.jpg")
        rows = [self._row(1, "x", "s1", str(a)), self._row(2, "y", "s2", str(b))]
        self._manifest(tmp_path, rows)
        result = tv.check_dataset(tmp_path)
        assert result["ok"] is True, result["problems"]

    def test_missing_file_is_rejected(self, tmp_path):
        tv = pytest.importorskip("training.train_v2")
        b = self._image(tmp_path / "b.jpg")
        rows = [self._row(1, "x", "s1", str(tmp_path / "nope.jpg")),
                self._row(2, "y", "s2", str(b))]
        self._manifest(tmp_path, rows)
        result = tv.check_dataset(tmp_path)
        assert result["ok"] is False
        assert any("missing" in p for p in result["problems"])

    def test_null_path_is_rejected(self, tmp_path):
        tv = pytest.importorskip("training.train_v2")
        b = self._image(tmp_path / "b.jpg")
        rows = [self._row(1, "x", "s1", None), self._row(2, "y", "s2", str(b))]
        self._manifest(tmp_path, rows)
        result = tv.check_dataset(tmp_path)
        assert result["ok"] is False
        assert any("no usable local path" in p for p in result["problems"])

    def test_unreadable_file_is_rejected(self, tmp_path):
        tv = pytest.importorskip("training.train_v2")
        unreadable = self._image(tmp_path / "locked.jpg")
        unreadable.chmod(0o000)
        b = self._image(tmp_path / "b.jpg")
        rows = [self._row(1, "x", "s1", str(unreadable)),
                self._row(2, "y", "s2", str(b))]
        self._manifest(tmp_path, rows)
        try:
            result = tv.check_dataset(tmp_path)
        finally:
            unreadable.chmod(0o644)
        # Running as root defeats the permission bits; accept either diagnosis.
        assert result["ok"] is False
        assert any("unreadable" in p or "empty" in p for p in result["problems"])

    def test_empty_file_is_rejected(self, tmp_path):
        tv = pytest.importorskip("training.train_v2")
        empty = tmp_path / "empty.jpg"
        empty.write_bytes(b"")
        b = self._image(tmp_path / "b.jpg")
        rows = [self._row(1, "x", "s1", str(empty)), self._row(2, "y", "s2", str(b))]
        self._manifest(tmp_path, rows)
        result = tv.check_dataset(tmp_path)
        assert result["ok"] is False
        assert any("empty" in p for p in result["problems"])

    def test_directory_instead_of_file_is_rejected(self, tmp_path):
        tv = pytest.importorskip("training.train_v2")
        (tmp_path / "adir.jpg").mkdir()
        b = self._image(tmp_path / "b.jpg")
        rows = [self._row(1, "x", "s1", str(tmp_path / "adir.jpg")),
                self._row(2, "y", "s2", str(b))]
        self._manifest(tmp_path, rows)
        result = tv.check_dataset(tmp_path)
        assert result["ok"] is False
        assert any("not a regular file" in p for p in result["problems"])

    def test_non_image_extension_is_rejected(self, tmp_path):
        tv = pytest.importorskip("training.train_v2")
        bad = tmp_path / "notes.txt"
        bad.write_bytes(b"hello")
        b = self._image(tmp_path / "b.jpg")
        rows = [self._row(1, "x", "s1", str(bad)), self._row(2, "y", "s2", str(b))]
        self._manifest(tmp_path, rows)
        result = tv.check_dataset(tmp_path)
        assert result["ok"] is False
        assert any("non-image extension" in p for p in result["problems"])

    def test_relative_path_is_resolved_against_the_dataset_dir(self, tmp_path):
        """A relative path must not depend on the process working directory."""
        tv = pytest.importorskip("training.train_v2")
        self._image(tmp_path / "a.jpg")
        b = self._image(tmp_path / "b.jpg")
        rows = [self._row(1, "x", "s1", "a.jpg"), self._row(2, "y", "s2", str(b))]
        self._manifest(tmp_path, rows)
        result = tv.check_dataset(tmp_path)
        assert result["ok"] is True, result["problems"]

    def test_path_escaping_the_dataset_dir_is_rejected(self, tmp_path):
        tv = pytest.importorskip("training.train_v2")
        outside = self._image(tmp_path.parent / "outside_escape.jpg")
        b = self._image(tmp_path / "b.jpg")
        rows = [self._row(1, "x", "s1", "../outside_escape.jpg"),
                self._row(2, "y", "s2", str(b))]
        self._manifest(tmp_path, rows)
        try:
            result = tv.check_dataset(tmp_path)
        finally:
            outside.unlink(missing_ok=True)
        assert result["ok"] is False
        assert any("escapes the dataset directory" in p for p in result["problems"])

    def test_diagnostics_name_the_split_and_pageid(self, tmp_path):
        tv = pytest.importorskip("training.train_v2")
        b = self._image(tmp_path / "b.jpg")
        rows = [self._row(77, "x", "s1", str(tmp_path / "gone.jpg")),
                self._row(2, "y", "s2", str(b))]
        self._manifest(tmp_path, rows)
        result = tv.check_dataset(tmp_path)
        joined = " ".join(result["problems"])
        assert "77" in joined and "train" in joined
