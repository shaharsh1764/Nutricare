"""Regression tests for the final review findings NB-1, NB-2, NB-3, NB-4.

Each finding from `docs/V2_COMMIT_747AA0D_REVIEW.md` gets positive **and**
negative coverage, because a detector that fires on everything is as useless as
one that fires on nothing.

* **NB-1** scraping detection missed `from Google`, `copied from Facebook`,
  `Instagram`, `Yandex`, video screenshots, and regressed on a bare `Bing`.
* **NB-2** provenance strength was described as a confidence ladder when only
  `scrape_risk` affects eligibility.
* **NB-3** a bare licence echo (`Permission = "CC BY-SA 2.0"`) was treated as
  evidence of permission.
* **NB-4** malformed metadata (`artist_raw = ["A"]`) raised `AttributeError`,
  aborting collection of an entire class.

No network access and no image bytes are required.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "training"))

from training.collect_v2 import (  # noqa: E402
    _FakeClient,
    collect_class,
    enrich,
)
from training.commons_audit import build_file_record  # noqa: E402
from training.licence_policy import (  # noqa: E402
    EXCLUDED,
    REVIEW_REQUIRED,
    TRAINING_APPROVED,
    classify_provenance,
    classify_rights,
    is_licence_label_only,
    platform_mentions,
    scrape_signals,
)

#: Every strength the classifier may return.
STRENGTHS = {
    "scrape_risk", "independent_review", "permission_asserted",
    "attribution_only", "transfer_only", "unknown",
}


def page(short="CC0", artist=None, credit=None, permission=None, pageid=1,
         width=1200, height=900):
    ext = {"LicenseShortName": {"value": short}}
    if artist is not None:
        ext["Artist"] = {"value": artist}
    if credit is not None:
        ext["Credit"] = {"value": credit}
    if permission is not None:
        ext["Permission"] = {"value": permission}
    return {
        "pageid": pageid,
        "title": f"File:T{pageid}.jpg",
        "imageinfo": [{
            "sha1": f"sha{pageid}", "width": width, "height": height,
            "mime": "image/jpeg", "url": "u", "descriptionurl": "d",
            "extmetadata": ext,
        }],
    }


# ---------------------------------------------------------------------------
# NB-1 — scraping detection
# ---------------------------------------------------------------------------


class TestNB1ScrapePositives:
    """Texts that genuinely indicate a scraped or copied image."""

    @pytest.mark.parametrize("text", [
        "From Google",
        "from Google",
        "Taken from Google image search",
        "google.com/search?q=biryani",
        "Bing",                    # bare Bing: regression fixed
        "bing",
        "Bing images",
        "Yandex images",
        "copied from Facebook",
        "Downloaded from a blog",
        "Screenshot from a video",
        "screen grab of the film",
        "captured from a youtube video",
        "scraped from a website",
        "clip art",
        "hotlinked from a forum",
        "reuploaded from another site",
        "found on the internet",
        "source unknown",
        "unknown source",
        "sourced from the web",
    ])
    def test_scrape_indicator_detected(self, text):
        assert classify_provenance(credit_text=text)["strength"] == "scrape_risk"

    def test_search_engine_in_permission_field_detected(self):
        assert classify_provenance(
            permission_text="Image from Google"
        )["strength"] == "scrape_risk"

    def test_scrape_dominates_a_permission_grant(self):
        out = classify_provenance(
            permission_text="Permission granted to use this image",
            credit_text="copied from Facebook",
        )
        assert out["strength"] == "scrape_risk"

    def test_scrape_excludes_an_otherwise_approved_cc_by(self):
        out = classify_rights(
            {"declared_class": "CC_BY", "short_name": "CC BY 4.0"}, artist="A",
            credit_text="from Google",
        )
        assert out["rights_tier"] == EXCLUDED
        assert out["provenance_strength"] == "scrape_risk"

    def test_signals_name_the_reason(self):
        signals = scrape_signals("copied from Facebook")
        assert "copy_verb" in signals

    def test_search_engine_source_signal(self):
        assert "search_engine_source" in scrape_signals("from Google")


class TestNB1ScrapeNegatives:
    """Texts that must NOT be treated as scraping (false-positive guards)."""

    @pytest.mark.parametrize("text", [
        "bingo night",                       # 'bing' inside 'bingo'
        "Own work",
        "Flickr",                            # bare platform mention
        "uploaded to Flickr by A Photographer",
        "Instagram",                         # platform alone is not copying
        "via Yahoo",
        "wallpaper paste texture",           # 'wallpaper' removed from pattern
        "no source of information about the dish",
        "unknown source of the spice",
        "Breakfast",
        "Lamb Korma, raita, Masoor Dal",
        "Uploaded by Perumalism",
        "Transferred from en.wikipedia to Commons by Number55",
    ])
    def test_not_scraping(self, text):
        assert classify_provenance(credit_text=text)["strength"] != "scrape_risk"

    def test_platform_mention_is_advisory_only(self):
        # Instagram is visible to an auditor but does not change the tier.
        assert platform_mentions("Instagram") == ["instagram"]
        resp = classify_rights(
            {"declared_class": "CC0_PD", "short_name": "CC0"}, credit_text="Instagram"
        )
        assert resp["rights_tier"] == TRAINING_APPROVED

    def test_platform_mentions_empty_for_unrelated_text(self):
        assert platform_mentions("Own work") == []
        assert platform_mentions("") == []

    def test_informative_food_description_is_not_scraping(self):
        out = classify_provenance(
            credit_text="A bowl of sambar served with rice and papad"
        )
        assert out["strength"] != "scrape_risk"


# ---------------------------------------------------------------------------
# NB-2 — provenance vs eligibility are separate decisions
# ---------------------------------------------------------------------------


class TestNB2ProvenanceIsNotAConfidenceLadder:
    def test_only_scrape_risk_changes_the_tier(self):
        base = {"declared_class": "CC_BY", "short_name": "CC BY 4.0"}
        observed = {}
        for label, kw in [
            ("unknown", {}),
            ("attribution_only", {"credit_text": "Own work"}),
            ("transfer_only", {"credit_text": "Transferred from en.wikipedia"}),
            ("permission_asserted", {"permission_text": "Permission granted to use"}),
            ("independent_review",
             {"permission_text": "flickrreview|File Upload Bot (Magnus Manske)|2013"}),
            ("scrape_risk", {"credit_text": "from Google"}),
        ]:
            out = classify_rights(base, artist="A", **kw)
            assert out["provenance_strength"] == label, label
            observed[label] = out["rights_tier"]
        # Every non-scrape strength is equivalent for eligibility.
        assert set(observed.values()) == {TRAINING_APPROVED, EXCLUDED}
        assert observed["scrape_risk"] == EXCLUDED
        for label in ("unknown", "attribution_only", "transfer_only",
                      "permission_asserted", "independent_review"):
            assert observed[label] == TRAINING_APPROVED

    def test_unknown_never_implies_verified(self):
        out = classify_rights({"declared_class": "CC0_PD", "short_name": "CC0"})
        assert out["provenance_strength"] == "unknown"
        assert out["verification"] == "declared_only"
        assert out["legal_clearance"] == "not_verified"
        assert out["human_review_required"] is True

    def test_independent_review_never_establishes_permission(self):
        out = classify_rights(
            {"declared_class": "CC_BY", "short_name": "CC BY 4.0"}, artist="A",
            permission_text="flickrreview|File Upload Bot (Magnus Manske)|2013",
        )
        assert out["provenance_strength"] == "independent_review"
        # A review confirms the tag matched, not ownership.
        assert out["verification"] == "declared_only"
        assert out["legal_clearance"] == "not_verified"
        assert out["human_review_required"] is True

    def test_training_approved_is_only_a_licence_verdict(self):
        # The flag reflects licence policy, never human or technical approval.
        out = classify_rights({"declared_class": "CC0_PD", "short_name": "CC0"})
        assert out["training_approved"] is True
        assert out["human_review_required"] is True

    def test_all_strengths_are_within_the_documented_set(self):
        samples = ["", "Own work", "Transferred from en.wikipedia", "from Google",
                   "Permission granted", "flickrreview|bot|2013", "Breakfast"]
        for text in samples:
            assert classify_provenance(credit_text=text)["strength"] in STRENGTHS


# ---------------------------------------------------------------------------
# NB-3 — licence echoes are not permission evidence
# ---------------------------------------------------------------------------


class TestNB3LicenceEchoes:
    @pytest.mark.parametrize("echo", [
        "CC BY-SA 2.0",
        "CC BY 4.0",
        "CC0",
        "cc-by-sa-3.0",
        "Creative Commons Attribution",
        "Attribution 4.0 International",
        "Public domain",
        "GFDL",
        "CC BY-NC 4.0",
    ])
    def test_licence_echo_is_not_permission_evidence(self, echo):
        out = classify_provenance(permission_text=echo)
        assert out["strength"] == "unknown", echo
        assert "permission_licence_echo" in out["signals"]

    def test_licence_echo_does_not_grant_a_tier_upgrade(self):
        out = classify_rights(
            {"declared_class": "CC_BY", "short_name": "CC BY 4.0"}, artist="A",
            permission_text="CC BY-SA 2.0",
        )
        assert out["provenance_strength"] == "unknown"

    @pytest.mark.parametrize("statement", [
        "Permission granted to use this image",
        "Used with permission",
        "With the permission of the author",
        "Written permission obtained",
        "Released to the public domain",
        "Licensed for reuse",
    ])
    def test_real_permission_statements_still_detected(self, statement):
        out = classify_provenance(permission_text=statement)
        assert out["strength"] == "permission_asserted", statement

    def test_empty_permission_field_is_unknown(self):
        assert classify_provenance(permission_text="")["strength"] == "unknown"
        assert classify_provenance(permission_text="   ")["strength"] == "unknown"

    def test_generic_description_mentioning_a_licence_is_not_permission(self):
        # "CC BY 4.0 photo taken in Kerala" is a description, not a grant, and
        # it is not a pure label either, so it falls through to unknown.
        out = classify_provenance(permission_text="CC BY 4.0 photo taken in Kerala")
        assert out["strength"] != "permission_asserted"

    def test_conflicting_credit_and_permission_prefers_permission(self):
        # A licence echo in Permission must not be overridden by a review claim
        # in the weaker Credit field.
        out = classify_provenance(
            permission_text="CC BY-SA 2.0",
            credit_text="This file was reviewed by the Flickr upload bot",
        )
        assert "permission_licence_echo" in out["signals"]
        assert out["strength"] != "permission_asserted"

    def test_author_name_is_not_permission(self):
        out = classify_provenance(permission_text="Alice Photographer")
        assert out["strength"] != "permission_asserted"

    def test_transfer_is_not_permission(self):
        out = classify_provenance(permission_text="Transferred from en.wikipedia")
        assert out["strength"] != "permission_asserted"

    def test_is_licence_label_only_helper(self):
        for label in ["CC BY-SA 2.0", "CC0 1.0", "Public domain", "Creative Commons"]:
            assert is_licence_label_only(label) is True, label
        for not_label in ["", "Permission granted", "CC BY 4.0 photo from Kerala"]:
            assert is_licence_label_only(not_label) is False, not_label

    def test_original_metadata_is_preserved_for_audit(self):
        record = build_file_record(
            "File:T1.jpg", page("CC BY-SA 4.0", permission="CC BY-SA 2.0"), [], []
        )
        assert record["permission"] == "CC BY-SA 2.0"
        # The echo is recorded in the classification rather than discarded.
        assert "permission_licence_echo" in enrich(record)["rights"]["provenance_signals"]


# ---------------------------------------------------------------------------
# NB-4 — malformed metadata must not abort collection
# ---------------------------------------------------------------------------


class TestNB4MalformedMetadata:
    def _lic(self, short="CC0", declared="CC0"):
        return {"declared_class": declared, "short_name": short}

    @pytest.mark.parametrize("record", [
        {"licence": {"declared_class": "CC_BY", "short_name": "CC BY 4.0"},
         "attribution": {"artist_raw": ["A"]}},
        {"licence": {"declared_class": "CC_BY", "short_name": "CC BY 4.0"},
         "attribution": {"artist_raw": None}},
        {"licence": {"declared_class": "CC_BY", "short_name": "CC BY 4.0"},
         "attribution": {"artist_raw": {"nested": "A"}}},
        {"licence": {"declared_class": "CC0", "short_name": "CC0"},
         "attribution": {"credit": 12345}},
        {"licence": {"declared_class": "CC0", "short_name": "CC0"},
         "attribution": {}, "permission": {"value": "Permission granted"}},
        {"licence": None, "attribution": {}},
        {"licence": {"declared_class": "CC0", "short_name": "CC0"},
         "attribution": ["not", "a", "dict"]},
        {"licence": {"declared_class": "CC0", "short_name": ["CC0"]},
         "attribution": {}},
        {"licence": {"declared_class": "CC0", "short_name": "CC0"},
         "attribution": {}, "width": "1200", "height": "900"},
        {"licence": {"declared_class": "CC0", "short_name": "CC0"},
         "attribution": {}, "width": True, "height": True},
        {"licence": {"declared_class": "CC0", "short_name": "CC0"},
         "attribution": {}, "width": None, "height": None},
    ])
    def test_enrich_never_raises(self, record):
        result = enrich(dict(record))
        assert result["rights"]["rights_tier"] in {
            TRAINING_APPROVED, REVIEW_REQUIRED, EXCLUDED
        }

    def test_malformed_artist_is_not_trusted_attribution(self):
        # A list where one author is expected must not become a name.
        out = enrich({
            "licence": {"declared_class": "CC_BY", "short_name": "CC BY 4.0"},
            "attribution": {"artist_raw": ["Alice", "Bob"]},
        })
        assert out["rights"]["rights_tier"] == EXCLUDED
        assert out["rights"]["attribution_sufficient"] is False

    def test_malformed_licence_flagged_and_excluded(self):
        out = enrich({"licence": None, "attribution": {}})
        assert "malformed_record" in out["technical_flags"]
        assert out["rights"]["rights_tier"] == EXCLUDED

    def test_non_integer_dimensions_are_not_treated_as_pixels(self):
        for dims in [("1200", "900"), (True, True), (None, None), (0, 0)]:
            out = enrich({
                "licence": {"declared_class": "CC0", "short_name": "CC0"},
                "attribution": {}, "width": dims[0], "height": dims[1],
            })
            assert "missing_dimensions" in out["technical_flags"], dims

    def test_valid_metadata_is_still_preserved(self):
        out = enrich({
            "licence": {"declared_class": "CC_BY", "short_name": "CC BY 4.0"},
            "attribution": {"artist_raw": "A Person", "credit": "Own work"},
            "permission": "Permission granted",
            "width": 1200, "height": 900, "pageid": 1, "sha1": "s",
            "mime": "image/jpeg",
        })
        assert out["rights"]["rights_tier"] == TRAINING_APPROVED
        assert out["rights"]["attribution_sufficient"] is True
        assert out["rights"]["provenance_strength"] == "permission_asserted"
        assert "malformed_record" not in out["technical_flags"]
        assert out["technical_flags"] == []

    def test_one_bad_file_does_not_abort_class_collection(self):
        # The whole point of NB-4: a malformed record is excluded, not fatal.
        good = page("CC0", pageid=1)
        bad = page("CC BY 4.0", pageid=2)
        bad["imageinfo"][0]["extmetadata"]["Artist"] = {"value": ["A", "B"]}
        tree = {
            "Category:Demo": {
                "files": [{"title": "File:T1.jpg"}, {"title": "File:T2.jpg"}],
                "subcats": [],
                "pages": [good, bad],
            }
        }
        doc = collect_class(_FakeClient(tree),
                            {"slug": "demo", "commons_categories": ["Category:Demo"]})
        assert len(doc["files"]) == 2, "both files must survive collection"
        by_id = {r["pageid"]: r for r in doc["files"]}
        assert by_id[1]["rights"]["rights_tier"] == TRAINING_APPROVED
        # The malformed one is excluded rather than crashing the run.
        assert by_id[2]["rights"]["rights_tier"] == EXCLUDED
        assert doc["counts"]["3_rights_supported"] == 1

    def test_malformed_record_never_becomes_eligible(self):
        doc = collect_class(
            _FakeClient({"Category:Demo": {
                "files": [{"title": "File:T1.jpg"}], "subcats": [],
                "pages": [page("CC BY 4.0", artist=None, pageid=1)],
            }}),
            {"slug": "demo", "commons_categories": ["Category:Demo"]},
        )
        assert doc["counts"]["3_rights_supported"] == 0


# ---------------------------------------------------------------------------
# NB-5 — the dead constant is gone
# ---------------------------------------------------------------------------


class TestNB5DeadCode:
    def test_approved_classes_constant_removed(self):
        from training import licence_policy

        assert not hasattr(licence_policy, "_APPROVED_CLASSES"), (
            "_APPROVED_CLASSES was the shared set that applied CC BY's author "
            "requirement to CC0; it must not be reintroduced"
        )

    def test_review_classes_still_present(self):
        from training import licence_policy

        assert licence_policy._REVIEW_CLASSES == frozenset({"CC_BY_SA"})
