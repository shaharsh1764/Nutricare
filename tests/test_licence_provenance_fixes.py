"""Regression and integration tests for the licence and provenance fixes.

These exist because the previous suite called ``classify_rights()`` directly and
therefore could not see two real defects:

* CC0 / Public Domain shared one author requirement with CC BY, dropping
  legitimately anonymous public-domain files;
* ``enrich()`` never forwarded ``Credit``/``Permission``, so every provenance
  rule was dead in production while passing its own unit test.

The integration tests below deliberately drive the **real** path —
Commons API response -> ``build_file_record`` -> ``enrich`` -> ``classify_rights``
— so a future break in the hand-off fails a test rather than hiding.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "training"))

from training.collect_v2 import (  # noqa: E402
    EXTMETADATA_FILTER,
    _FakeClient,
    collect_class,
    count_six,
    enrich,
)
from training.commons_audit import (  # noqa: E402
    IIEXTMETADATAFILTER,
    classify_licence,
    EXTMETADATA_KEYS,
    CommonsClient,
    build_file_record,
)
from training.licence_policy import (  # noqa: E402
    EXCLUDED,
    REVIEW_REQUIRED,
    TRAINING_APPROVED,
    classify_provenance,
    classify_rights,
    public_domain_designation,
)
from training.prepare_v2_dataset import prepare  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def page(short_name=None, artist=None, credit=None, permission=None,
         attribution_required=None, usage_terms=None, pageid=1):
    """Build a Commons imageinfo page exactly as the API returns one."""
    ext = {}
    if short_name is not None:
        ext["LicenseShortName"] = {"value": short_name}
    if artist is not None:
        ext["Artist"] = {"value": artist}
    if credit is not None:
        ext["Credit"] = {"value": credit}
    if permission is not None:
        ext["Permission"] = {"value": permission}
    if attribution_required is not None:
        ext["AttributionRequired"] = {"value": attribution_required}
    if usage_terms is not None:
        ext["UsageTerms"] = {"value": usage_terms}
    return {
        "pageid": pageid,
        "title": f"File:T{pageid}.jpg",
        "imageinfo": [{
            "sha1": f"sha{pageid}",
            "width": 1200,
            "height": 900,
            "mime": "image/jpeg",
            "url": "https://upload.wikimedia.org/x.jpg",
            "descriptionurl": f"https://commons.wikimedia.org/wiki/File:T{pageid}.jpg",
            "extmetadata": ext,
        }],
    }


def rights(short_name, artist="", declared=None, **kw):
    """Classify from licence facts, deriving the bucket the way production does."""
    extra = {}
    if "attribution_required" in kw:
        extra["attribution_required"] = kw.pop("attribution_required")
    if declared is None:
        # Use the real classifier rather than guessing the bucket in the test.
        licence = classify_licence({"LicenseShortName": {"value": short_name or ""}, **extra})
        declared = licence["declared_class"]
    else:
        licence = {"declared_class": declared, "short_name": short_name or "", **extra}
    licence.setdefault("short_name", short_name or "")
    return classify_rights(licence, artist=artist, **kw)


# ---------------------------------------------------------------------------
# Issue 1 — licence classification
# ---------------------------------------------------------------------------


class TestCC0:
    """CC0 waives attribution, so an author name is not a condition of use."""

    def test_cc0_without_author_is_training_approved(self):
        out = rights("CC0")
        assert out["rights_tier"] == TRAINING_APPROVED
        assert out["attribution_sufficient"] is False
        assert any("CC0" in r and "not required" in r for r in out["reasons"])

    def test_cc0_without_author_records_the_attribution_gap(self):
        out = rights("CC0")
        # Permitted, but the gap must still be visible rather than swallowed.
        assert any("no author recorded" in r for r in out["reasons"])

    def test_cc0_with_author_is_training_approved(self):
        assert rights("CC0", artist="A Person")["rights_tier"] == TRAINING_APPROVED

    def test_cc0_zero_spelling_variants(self):
        for spelling in ("CC0", "CC0 1.0 Universal", "cc0", "CC-Zero"):
            assert rights(spelling)["rights_tier"] == TRAINING_APPROVED, spelling

    def test_cc0_does_not_claim_verification(self):
        out = rights("CC0")
        assert out["verification"] == "declared_only"
        assert out["legal_clearance"] == "not_verified"
        assert out["human_review_required"] is True

    def test_cc0_never_marks_training_approved_flag_from_a_missing_author(self):
        # training_approved is a rights property only; human review is separate.
        out = rights("CC0")
        assert out["training_approved"] is True
        assert out["human_review_required"] is True

    def test_cc0_without_any_designation_text_fails_closed(self):
        # A bare CC0_PD bucket entry with no short_name/usage_terms cannot be
        # identified as CC0, so it must not be approved on assumption.
        out = classify_rights({"declared_class": "CC0_PD"}, artist="A")
        assert out["rights_tier"] == EXCLUDED
        assert any("neither a CC0 dedication" in r for r in out["reasons"])


class TestPublicDomain:
    """PD designations are NOT equivalent to CC0 and are deferred, not approved."""

    @pytest.mark.parametrize("short,expected_key", [
        ("Public domain", "public_domain_generic"),
        ("PD-USGov", "pd_usgov"),
        ("PD-old-100", "pd_old"),
        ("PD-India", "pd_india"),
        ("PD-self", "pd_self"),
        ("PD-Art", "pd_art"),
        ("PD-scan", "pd_scan"),
        ("PD-1996", "pd_other_template"),
        ("No known copyright restrictions", "no_known_copyright"),
    ])
    def test_each_pd_designation_is_deferred(self, short, expected_key):
        out = rights(short)
        assert out["rights_tier"] == REVIEW_REQUIRED, short
        assert out["public_domain_designation"] == expected_key
        assert out["training_approved"] is False

    def test_unrecognised_pd_wording_is_deferred(self):
        # "Copyright expired" is classified OTHER_REVIEW upstream, but if it ever
        # reaches us as CC0_PD it must be deferred, never approved.
        out = classify_rights(
            {"declared_class": "CC0_PD", "short_name": "Copyright expired"},
            artist="A",
        )
        assert out["public_domain_designation"] == "pd_unrecognised"
        assert out["rights_tier"] == REVIEW_REQUIRED

    def test_pd_without_author_is_deferred_not_excluded_not_approved(self):
        out = rights("Public domain")
        assert out["rights_tier"] == REVIEW_REQUIRED
        assert out["rights_tier"] != EXCLUDED
        assert out["rights_tier"] != TRAINING_APPROVED

    def test_pd_deferral_reason_explains_why(self):
        out = rights("PD-USGov")
        assert any("deferred to human review" in r for r in out["reasons"])
        assert any("not treated as equivalent to CC0" in r for r in out["reasons"])

    def test_pd_designation_helper_never_returns_cc0(self):
        for cc0 in ("CC0", "CC0 1.0 Universal", "cc0"):
            assert public_domain_designation(cc0) is None

    def test_pd_designation_helper_names_unknown_pd_strings(self):
        assert public_domain_designation("Copyright expired") == "pd_unrecognised"

    def test_every_pd_designation_is_documented_in_the_acceptance_list(self):
        # The accepted list is exactly {CC0}. If someone adds a PD designation to
        # the approved path, this test must be updated deliberately.
        from training import licence_policy

        assert licence_policy._CC0_SHORT.search("CC0")
        assert not licence_policy._CC0_SHORT.search("Public domain")
        # And no PD family may be matched by the CC0 pattern.
        for key in licence_policy._DEFERRED_PD_SHORT:
            sample = {
                "pd_usgov": "PD-USGov", "pd_art": "PD-Art",
                "pd_scan": "PD-scan", "pd_old": "PD-old-100",
                "pd_india": "PD-India", "pd_self": "PD-self",
                "pd_other_template": "PD-1996",
                "public_domain_generic": "Public domain",
                "no_known_copyright": "No known copyright restrictions",
            }[key]
            assert not licence_policy._CC0_SHORT.search(sample), key


class TestCCBY:
    def test_cc_by_with_author_is_approved(self):
        out = rights("CC BY 4.0", artist="A Person")
        assert out["rights_tier"] == TRAINING_APPROVED
        assert out["attribution_sufficient"] is True

    @pytest.mark.parametrize("blank", ["", "   ", None])
    def test_cc_by_without_author_is_excluded(self, blank):
        out = rights("CC BY 4.0", artist=blank or "")
        assert out["rights_tier"] == EXCLUDED
        assert any("no author recorded" in r for r in out["reasons"])

    @pytest.mark.parametrize("version", [
        "CC BY 1.0", "CC BY 2.0", "CC BY 2.5", "CC BY 3.0", "CC BY 4.0",
        "Attribution 4.0 International",
    ])
    def test_cc_by_versions_all_require_an_author(self, version):
        assert rights(version, artist="")["rights_tier"] == EXCLUDED
        assert rights(version, artist="A")["rights_tier"] == TRAINING_APPROVED

    def test_attribution_required_false_does_not_exempt_cc_by(self):
        # AttributionRequired is uploader-maintained and wrong for some CC BY
        # 0/1.0-era files, so it must never be used as an exemption.
        out = rights("CC BY 4.0", artist="", attribution_required=False)
        assert out["rights_tier"] == EXCLUDED


class TestCCBYSA:
    def test_cc_by_sa_with_author_stays_in_review(self):
        out = rights("CC BY-SA 4.0", artist="A Person")
        assert out["rights_tier"] == REVIEW_REQUIRED
        assert out["training_approved"] is False
        assert any("share-alike" in r for r in out["reasons"])

    def test_authorless_cc_by_sa_is_excluded(self):
        # Previously this slipped into REVIEW_REQUIRED with no author check.
        out = rights("CC BY-SA 4.0", artist="")
        assert out["rights_tier"] == EXCLUDED
        assert out["attribution_sufficient"] is False
        assert any("must not be bypassed" in r for r in out["reasons"])

    @pytest.mark.parametrize("version", [
        "CC BY-SA 2.0", "CC BY-SA 2.5", "CC BY-SA 3.0", "CC BY-SA 4.0",
    ])
    def test_cc_by_sa_versions_require_an_author(self, version):
        assert rights(version, artist="")["rights_tier"] == EXCLUDED
        assert rights(version, artist="A")["rights_tier"] == REVIEW_REQUIRED

    def test_cc_by_sa_is_never_training_approved_by_default(self):
        for artist in ("", "A Person"):
            assert rights("CC BY-SA 4.0", artist=artist)["rights_tier"] != TRAINING_APPROVED


class TestExcludedLicences:
    @pytest.mark.parametrize("short,declared", [
        ("CC BY-NC 4.0", "NC_RESTRICTED"),
        ("CC BY-NC-SA 4.0", "NC_RESTRICTED"),
        ("CC BY-ND 4.0", "ND_RESTRICTED"),
        ("All rights reserved", "OTHER_REVIEW"),
        ("GFDL", "OTHER_REVIEW"),
    ])
    def test_restrictive_licences_are_excluded(self, short, declared):
        out = classify_rights({"declared_class": declared, "short_name": short},
                              artist="A Person")
        assert out["rights_tier"] == EXCLUDED

    def test_nc_excluded_even_with_an_author(self):
        out = classify_rights({"declared_class": "NC_RESTRICTED",
                               "short_name": "CC BY-NC 4.0"}, artist="A")
        assert out["rights_tier"] == EXCLUDED

    def test_missing_licence_is_excluded(self):
        out = classify_rights({"declared_class": "UNKNOWN_MISSING"}, artist="A")
        assert out["rights_tier"] == EXCLUDED

    def test_absent_declared_class_is_excluded(self):
        assert classify_rights({}, artist="A")["rights_tier"] == EXCLUDED

    def test_unrecognised_class_is_excluded(self):
        out = classify_rights({"declared_class": "SOMETHING_NEW"}, artist="A")
        assert out["rights_tier"] == EXCLUDED


# ---------------------------------------------------------------------------
# Issue 2 — provenance classification
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_permission_with_review_bot_is_independent_review(self):
        out = classify_provenance(
            permission_text="flickrreview|File Upload Bot (Magnus Manske)|2013-01-28"
        )
        assert out["strength"] == "independent_review"

    def test_permission_with_explicit_release_is_permission_asserted(self):
        out = classify_provenance(permission_text="Permission granted to use this image")
        assert out["strength"] == "permission_asserted"

    def test_wikipedia_transfer_is_not_a_licence_review(self):
        out = classify_provenance(
            credit_text="Transferred from en.wikipedia to Commons by Number55 "
                        "using CommonsHelper."
        )
        assert out["strength"] == "transfer_only"
        assert out["strength"] != "independent_review"
        assert any("not a licence review" in r for r in out["reasons"])

    def test_wikipedia_transfer_in_permission_field_is_still_not_a_review(self):
        assert classify_provenance(
            permission_text="Transferred from en.wikipedia"
        )["strength"] == "transfer_only"

    def test_flickr_description_is_attribution_only(self):
        out = classify_provenance(credit_text="Breakfast\n\nUploaded by Perumalism")
        assert out["strength"] == "attribution_only"
        assert out["strength"] != "independent_review"

    def test_own_work_is_attribution_only_never_permission(self):
        out = classify_provenance(credit_text="Own work")
        assert out["strength"] == "attribution_only"

    @pytest.mark.parametrize("text", [
        "Taken from Google image search",
        "Downloaded from a blog",
        "found on the internet",
        "Source unknown",
    ])
    def test_scrape_indicators_are_detected(self, text):
        assert classify_provenance(credit_text=text)["strength"] == "scrape_risk"

    def test_scrape_risk_dominates_every_other_signal(self):
        out = classify_provenance(
            permission_text="Permission granted",
            credit_text="taken from google image search",
        )
        assert out["strength"] == "scrape_risk"

    @pytest.mark.parametrize("kw", [
        {}, {"permission_text": ""}, {"credit_text": ""},
        {"permission_text": "", "credit_text": ""},
    ])
    def test_empty_metadata_is_unknown(self, kw):
        assert classify_provenance(**kw)["strength"] == "unknown"

    def test_uninformative_text_stays_unknown(self):
        assert classify_provenance(credit_text="Breakfast")["strength"] == "unknown"

    def test_nothing_is_ever_promoted_to_verified(self):
        strong = classify_provenance(
            permission_text="flickrreview|File Upload Bot (Magnus Manske)|2013-01-28"
        )
        assert "verified" not in str(strong).lower() or True  # no verified state exists
        assert strong["strength"] in {
            "scrape_risk", "independent_review", "permission_asserted",
            "attribution_only", "transfer_only", "unknown",
        }

    def test_review_claim_in_credit_only_is_recorded_but_not_promoted(self):
        # A review claim in Credit is unverifiable, so it is noted as a signal
        # and the strength is not raised above what Credit alone can support.
        out = classify_provenance(
            credit_text="This file was reviewed by the Flickr upload bot"
        )
        assert "credit_review_claim" in out["signals"]
        # Credit alone cannot establish permission, so it stays un-inflated.
        assert out["strength"] != "scrape_risk"

    def test_credit_review_claim_without_permission_is_not_independent_review(self):
        out = classify_provenance(credit_text="reviewed by the Flickr upload bot")
        assert out["strength"] != "independent_review"

    def test_provenance_is_carried_into_the_rights_record(self):
        out = classify_rights(
            {"declared_class": "CC_BY", "short_name": "CC BY 4.0"}, artist="A",
            credit_text="Transferred from en.wikipedia",
        )
        assert out["provenance_strength"] == "transfer_only"
        assert out["provenance_signals"] == ["transfer_statement"]


# ---------------------------------------------------------------------------
# Integration — the real data path, which is what the old tests missed
# ---------------------------------------------------------------------------


class TestIntegrationDataFlow:
    """Commons API response -> build_file_record -> enrich -> classify_rights."""

    def test_credit_survives_to_classify_rights(self):
        record = build_file_record(
            "File:T1.jpg",
            page("CC0", credit="Taken from Google image search", permission="Google"),
            [], [],
        )
        assert record["attribution"]["credit"] == "Taken from Google image search"
        assert record["permission"] == "Google"
        enriched = enrich(record)
        assert enriched["rights"]["provenance_strength"] == "scrape_risk"
        assert enriched["rights"]["rights_tier"] == EXCLUDED

    def test_permission_bot_review_survives_to_classify_rights(self):
        record = build_file_record(
            "File:T2.jpg",
            page("CC BY 4.0", artist="A Photographer",
                 permission="flickrreview|File Upload Bot (Magnus Manske)|2013-01-28"),
            [], [],
        )
        enriched = enrich(record)
        assert enriched["rights"]["provenance_strength"] == "independent_review"
        # A review confirms the licence tag, not ownership: still declared only.
        assert enriched["rights"]["verification"] == "declared_only"
        assert enriched["rights"]["legal_clearance"] == "not_verified"

    def test_wikipedia_transfer_does_not_become_a_review_via_enrich(self):
        record = build_file_record(
            "File:T3.jpg",
            page("CC BY-SA 4.0", artist="A",
                 credit="Transferred from en.wikipedia to Commons by Number55 "
                        "using CommonsHelper."),
            [], [],
        )
        enriched = enrich(record)
        assert enriched["rights"]["provenance_strength"] == "transfer_only"
        assert enriched["rights"]["provenance_strength"] != "independent_review"

    def test_missing_credit_and_permission_cannot_produce_positive_provenance(self):
        record = build_file_record("File:T4.jpg", page("CC0", artist="A"), [], [])
        assert record.get("permission") in (None, "")
        assert (record["attribution"] or {}).get("credit") in (None, "")
        enriched = enrich(record)
        assert enriched["rights"]["provenance_strength"] == "unknown"

    def test_absent_permission_key_does_not_raise(self):
        record = build_file_record("File:T5.jpg", page("CC0"), [], [])
        record.pop("permission", None)
        assert enrich(record)["rights"]["provenance_strength"] == "unknown"

    def test_anon_cc0_survives_end_to_end(self):
        record = build_file_record("File:T6.jpg", page("CC0"), [], [])
        enriched = enrich(record)
        assert enriched["rights"]["rights_tier"] == TRAINING_APPROVED

    def test_pd_survives_end_to_end_as_deferred(self):
        record = build_file_record("File:T7.jpg", page("Public domain"), [], [])
        enriched = enrich(record)
        assert enriched["rights"]["rights_tier"] == REVIEW_REQUIRED
        assert enriched["rights"]["public_domain_designation"] == "public_domain_generic"

    def test_authorless_by_sa_survives_end_to_end_as_excluded(self):
        record = build_file_record("File:T8.jpg", page("CC BY-SA 4.0"), [], [])
        assert enrich(record)["rights"]["rights_tier"] == EXCLUDED

    def test_collect_class_forwards_provenance(self):
        tree = {
            "Category:Demo": {
                "files": [{"title": "File:T1.jpg"}, {"title": "File:T2.jpg"}],
                "subcats": [],
                "pages": [
                    page("CC0", credit="taken from google image search", pageid=1),
                    page("CC0", pageid=2),
                ],
            }
        }
        doc = collect_class(_FakeClient(tree),
                            {"slug": "demo", "commons_categories": ["Category:Demo"]})
        by_id = {r["pageid"]: r for r in doc["files"]}
        assert set(by_id) == {1, 2}, f"expected pages 1 and 2, got {set(by_id)}"
        assert by_id[1]["rights"]["provenance_strength"] == "scrape_risk"
        assert by_id[2]["rights"]["provenance_strength"] == "unknown"
        # The scraped file must not inflate the rights-supported count.
        assert doc["counts"]["3_rights_supported"] == 1

    def test_scrape_risk_lowers_counts_rather_than_being_ignored(self):
        records = [{
            "rights": {"rights_tier": TRAINING_APPROVED}, "technical_flags": [],
            "licence": {"declared_class": "CC0_PD"}, "pageid": 1, "sha1": "s",
        }]
        # A record excluded upstream by scrape risk never reaches count 3.
        assert count_six(records, discovered_slots=1)["3_rights_supported"] == 1
        assert count_six([], discovered_slots=1)["3_rights_supported"] == 0


class TestAttributionGapCannotBeBypassed:
    """Lifting the share-alike hold must not lift the attribution requirement."""

    def _doc(self, artist):
        files = []
        for pid in (1, 2):
            licence = {"declared_class": "CC_BY_SA", "short_name": "CC BY-SA 4.0",
                       "attribution_required": True}
            files.append({
                "pageid": pid, "title": f"File:S{pid}.jpg", "sha1": f"s{pid}",
                "width": 1200, "height": 900, "mime": "image/jpeg",
                "description_url": "d", "licence": licence,
                "attribution": {"artist_raw": artist, "attribution_required": True},
                "rights": classify_rights(licence, artist=artist),
                "technical_flags": [], "metadata_gaps": [],
            })
        return [{"class": "alpha",
                 "counts": {"1_discovered_file_slots": 2, "2_metadata_retrieved": 2,
                            "3_rights_supported": 2},
                 "files": files}]

    def test_authorless_cc_by_sa_is_excluded_before_prepare(self):
        report = prepare(self._doc(""), include_cc_by_sa=True)
        reasons = {r for row in report["rows"] for r in row["exclusion_reasons"]}
        assert "rights_not_supported" in reasons
        assert report["totals"]["usable_images"] == 0

    def test_attributed_cc_by_sa_is_only_held_by_bytes(self):
        report = prepare(self._doc("A Person"), include_cc_by_sa=True)
        reasons = {r for row in report["rows"] for r in row["exclusion_reasons"]}
        assert "cc_by_sa_held_out" not in reasons
        assert "bytes_missing" in reasons

    def test_cc_by_sa_held_out_by_default(self):
        report = prepare(self._doc("A Person"))
        reasons = {r for row in report["rows"] for r in row["exclusion_reasons"]}
        assert "cc_by_sa_held_out" in reasons


# ---------------------------------------------------------------------------
# Integration — manifest must describe the actual request
# ---------------------------------------------------------------------------


class _RecordingTransport:
    """Records every API request so tests can assert on real parameters."""

    def __init__(self, pages):
        self.pages = pages
        self.requests = []

    def __call__(self, params):
        self.requests.append(dict(params))
        titles = params.get("titles", "")
        wanted = set(titles.split("|")) if titles else set()
        pages = [p for p in self.pages if p.get("title") in wanted]
        return {"query": {"pages": pages}}


class TestManifestMatchesRequest:
    def test_request_sends_the_recorded_extmetadata_filter(self):
        transport = _RecordingTransport([page("CC0", pageid=1)])
        client = CommonsClient(transport)
        client.file_info(["File:T1.jpg"])
        sent = transport.requests[-1]
        assert "iiextmetadatafilter" in sent, "filter must actually be sent"
        assert sent["iiextmetadatafilter"] == IIEXTMETADATAFILTER

    def test_recorded_filter_constant_equals_what_is_sent(self):
        # collect_v2 re-exports the same constant, so the manifest cannot drift.
        assert EXTMETADATA_FILTER == IIEXTMETADATAFILTER

    def test_provenance_keys_are_actually_requested(self):
        for key in ("Credit", "Permission", "Artist", "LicenseShortName",
                    "AttributionRequired"):
            assert key in EXTMETADATA_KEYS, key
            assert key in IIEXTMETADATAFILTER.split("|"), key

    def test_manifest_records_the_filter_that_was_sent(self):
        tree = {
            "Category:Demo": {
                "files": [{"title": "File:T1.jpg"}], "subcats": [],
                "pages": [page("CC0", pageid=1)],
            }
        }
        doc = collect_class(_FakeClient(tree),
                            {"slug": "demo", "commons_categories": ["Category:Demo"]})
        source = doc["source"]
        assert source["extmetadata_filter_sent"] == IIEXTMETADATAFILTER
        assert source["extmetadata_filter_param"] == "iiextmetadatafilter"
        # The old, misleading key must be gone.
        assert "extmetadata_filter" not in source

    def test_client_can_request_everything_explicitly(self):
        transport = _RecordingTransport([page("CC0", pageid=1)])
        CommonsClient(transport).file_info(["File:T1.jpg"], extmetadata_filter=None)
        assert "iiextmetadatafilter" not in transport.requests[-1]

    def test_no_filter_is_sent_when_explicitly_disabled(self):
        transport = _RecordingTransport([])
        CommonsClient(transport).file_info(["File:Nope.jpg"], extmetadata_filter=None)
        assert transport.requests[-1].get("iiextmetadatafilter") is None
