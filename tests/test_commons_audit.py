"""Tests for the Wikimedia Commons metadata auditor.

Every test runs **without network access**: responses come from a scripted
transport. Nothing here downloads an image or trains a model.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from training.commons_audit import (  # noqa: E402
    API_HOST,
    CC0_PD,
    CC_BY,
    CC_BY_SA,
    NC_RESTRICTED,
    ND_RESTRICTED,
    OTHER_REVIEW,
    UNKNOWN_MISSING,
    PRELIMINARILY_ACCEPTABLE,
    CategoryNode,
    CommonsAPIError,
    CommonsClient,
    FixtureTransport,
    build_file_record,
    classify_licence,
    count_potential_band,
    normalize_title,
    render_markdown,
    run_audit,
    traverse_categories,
)

TAXONOMY_PATH = Path(__file__).resolve().parents[1] / "data/v3/taxonomy_100_proposed.json"


# ---------------------------------------------------------------------------
# Fake API plumbing
# ---------------------------------------------------------------------------


class ScriptedClient(CommonsClient):
    """CommonsClient whose transport is a dict of canned responses."""

    def __init__(self, members=None, info=None, files=None, **kwargs):
        self._members = members or {}
        self._info = info or {}
        self._files = files or {}
        self.calls = []
        super().__init__(self._transport, **kwargs)

    def _transport(self, params):
        self.calls.append(dict(params))
        action = params.get("action")
        if action == "query" and params.get("list") == "categorymembers":
            title = params["cmtitle"].split(":", 1)[-1]
            pages = self._members.get(title)
            if pages is None:
                return {"query": {"categorymembers": []}}
            if isinstance(pages, dict):
                pages = [pages]
            index = int(params.get("cmcontinue") or 0)
            if index >= len(pages):
                return {"query": {"categorymembers": []}}
            return pages[index]
        if action == "query" and params.get("prop") == "categoryinfo":
            titles = params["titles"].split("|")
            out = []
            for t in titles:
                short = t.split(":", 1)[-1]
                stat = self._info.get(short)
                if stat is None:
                    out.append({"title": t, "missing": True})
                else:
                    out.append(
                        {
                            "title": t,
                            "ns": 14,
                            "categoryinfo": {
                                "files": stat[0],
                                "subcats": stat[1],
                                "pages": stat[0] + stat[1],
                            },
                        }
                    )
            return {"query": {"pages": out}}
        if action == "query" and params.get("prop") == "imageinfo":
            titles = params["titles"].split("|")
            out = []
            for t in titles:
                page = self._files.get(t)
                if page is None:
                    out.append({"title": t, "missing": True})
                else:
                    out.append(page)
            return {"query": {"pages": out}}
        raise AssertionError(f"unexpected params: {params}")


def file_page(title, *, licence="CC BY-SA 4.0", artist="Someone", pageid=1,
              url="https://upload.wikimedia.org/x.jpg", width=1200, height=900,
              sha1="abc", permission="", mime="image/jpeg"):
    ext = {}
    if licence is not None:
        ext["LicenseShortName"] = {"value": licence}
    if artist is not None:
        ext["Artist"] = {"value": f"<a href='#'>{artist}</a>"}
    if permission:
        ext["Permission"] = {"value": permission}
    ext["AttributionRequired"] = {"value": "true"}
    info = {
        "url": url,
        "width": width,
        "height": height,
        "sha1": sha1,
        "mime": mime,
        "mediatype": "BITMAP",
        "size": 12345,
        "descriptionurl": f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}",
        "extmetadata": ext,
    }
    return {"pageid": pageid, "title": title, "ns": 6, "imageinfo": [info]}


def members_page(files, subcats):
    out = [{"title": s, "ns": 14} for s in subcats]
    out += [{"title": f, "ns": 6, "pageid": i + 1} for i, f in enumerate(files)]
    return {"query": {"categorymembers": out}}


# ---------------------------------------------------------------------------
# 1. Licence classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("CC0", CC0_PD),
        ("Public domain", CC0_PD),
        ("PD-USGov", CC0_PD),
        ("CC BY 4.0", CC_BY),
        ("CC BY 2.0", CC_BY),
        ("CC BY-SA 4.0", CC_BY_SA),
        ("CC BY-SA 3.0", CC_BY_SA),
        ("CC BY-NC 4.0", NC_RESTRICTED),
        ("CC BY-NC-SA 4.0", NC_RESTRICTED),
        ("CC BY-ND 4.0", ND_RESTRICTED),
        ("CC BY-NC-ND 4.0", NC_RESTRICTED),
        ("Fair use", OTHER_REVIEW),
        ("GFDL", OTHER_REVIEW),
        ("", UNKNOWN_MISSING),
    ],
)
def test_classify_licence_buckets(value, expected):
    result = classify_licence({"LicenseShortName": {"value": value}} if value else {})
    assert result["declared_class"] == expected


def test_nc_beats_sa_so_by_nc_sa_is_never_treated_as_by_sa():
    """Regression guard: 'CC BY-NC-SA' must not collapse into the acceptable CC BY-SA."""
    result = classify_licence({"LicenseShortName": {"value": "CC BY-NC-SA 4.0"}})
    assert result["declared_class"] == NC_RESTRICTED
    assert result["preliminarily_acceptable"] is False


def test_nd_beats_cc_by():
    result = classify_licence({"LicenseShortName": {"value": "CC BY-ND 4.0"}})
    assert result["declared_class"] == ND_RESTRICTED
    assert not result["preliminarily_acceptable"]


def test_declaration_is_never_proof():
    result = classify_licence({"LicenseShortName": {"value": "CC BY 4.0"}})
    assert result["verification"] == "declared_only"
    assert result["requires_human_review"] is True


def test_restrictions_field_forces_review_but_keeps_class():
    result = classify_licence(
        {
            "LicenseShortName": {"value": "CC BY-SA 4.0"},
            "Restrictions": {"value": "personality rights"},
        }
    )
    assert result["declared_class"] == CC_BY_SA
    assert "personality rights" in result["review_reason"]


def test_share_alike_is_flagged_not_resolved():
    result = classify_licence({"LicenseShortName": {"value": "CC BY-SA 4.0"}})
    assert result["share_alike"] is True
    # The tool flags the question; it must not assert an answer.
    assert "share-alike" in result["review_reason"].lower()


def test_acceptable_set_excludes_restrictive_buckets():
    assert PRELIMINARILY_ACCEPTABLE == {CC0_PD, CC_BY, CC_BY_SA}


def test_marketplace_style_category_is_not_licence_proof():
    """A category name is not a licence: no extmetadata still means unknown."""
    assert classify_licence({})["declared_class"] == UNKNOWN_MISSING


# ---------------------------------------------------------------------------
# 2. Pagination and continuation
# ---------------------------------------------------------------------------


def test_category_members_follows_continuation():
    pages = [
        {
            "continue": {"cmcontinue": "1", "continue": "||"},
            "query": {"categorymembers": [{"title": "File:A.jpg", "ns": 6, "pageid": 1}]},
        },
        {
            "continue": {"cmcontinue": "2", "continue": "||"},
            "query": {"categorymembers": [{"title": "File:B.jpg", "ns": 6, "pageid": 2}]},
        },
        {"query": {"categorymembers": [{"title": "File:C.jpg", "ns": 6, "pageid": 3}]}},
    ]
    # Serve successive pages as the continue token advances.
    class Client(CommonsClient):
        def __init__(self):
            super().__init__(lambda p: pages[int(p.get("cmcontinue", 0))])

    files, subcats = Client().category_members("Jalebi")
    assert [f["title"] for f in files] == ["File:A.jpg", "File:B.jpg", "File:C.jpg"]
    assert subcats == []


def test_pagination_guard_raises_rather_than_truncating():
    def always_more(params):
        return {
            "continue": {"cmcontinue": "x", "continue": "||"},
            "query": {"categorymembers": [{"title": "File:A.jpg", "ns": 6}]},
        }

    client = CommonsClient(always_more, max_pages=3)
    with pytest.raises(CommonsAPIError, match="pagination exceeded"):
        list(client.query_all({"action": "query", "list": "categorymembers"}))


def test_query_all_stops_without_continue():
    calls = []

    def transport(params):
        calls.append(params)
        return {"query": {"categorymembers": []}}

    list(CommonsClient(transport).query_all({"action": "query"}))
    assert len(calls) == 1


def test_file_info_batches_at_api_limit():
    """50 titles per request, per MediaWiki's anonymous cap."""
    client = ScriptedClient()
    client.file_info([f"File:F{i}.jpg" for i in range(120)])
    imageinfo_calls = [c for c in client.calls if c.get("prop") == "imageinfo"]
    assert len(imageinfo_calls) == 3
    assert all(len(c["titles"].split("|")) <= 50 for c in imageinfo_calls)


def test_file_info_keeps_missing_titles_visible():
    client = ScriptedClient(files={"File:Real.jpg": file_page("File:Real.jpg")})
    result = client.file_info(["File:Real.jpg", "File:Gone.jpg"])
    assert result["File:Real.jpg"]["pageid"] == 1
    assert result["File:Gone.jpg"]["missing"] is True


# ---------------------------------------------------------------------------
# 3. Recursive traversal
# ---------------------------------------------------------------------------


def test_recursive_traversal_reaches_grandchildren():
    members = {
        "Biryani": members_page(["File:B1.jpg", "File:B2.jpg"], ["Chicken biryani"]),
        "Chicken biryani": members_page(["File:C1.jpg"], ["Hyderabadi biryani"]),
        "Hyderabadi biryani": members_page(["File:H1.jpg"], []),
    }
    client = ScriptedClient(members=members)
    nodes, warnings = traverse_categories(client, ["Biryani"], depth=2)
    assert set(nodes) == {"Biryani", "Chicken biryani", "Hyderabadi biryani"}
    assert nodes["Chicken biryani"].parent == "Biryani"
    assert nodes["Hyderabadi biryani"].depth == 2
    assert warnings == []


def test_depth_limit_warns_instead_of_silently_stopping():
    members = {
        "Biryani": members_page(["File:B1.jpg"], ["Chicken biryani"]),
        "Chicken biryani": members_page(["File:C1.jpg"], ["Hyderabadi biryani"]),
    }
    client = ScriptedClient(members=members)
    nodes, warnings = traverse_categories(client, ["Biryani"], depth=0)
    assert set(nodes) == {"Biryani"}
    assert any("subcategories not traversed" in w for w in warnings)


def test_cycles_are_visited_once():
    members = {
        "A": members_page([], ["B"]),
        "B": members_page([], ["A"]),
    }
    client = ScriptedClient(members=members)
    nodes, _ = traverse_categories(client, ["A"], depth=5)
    assert set(nodes) == {"A", "B"}


def test_diamond_inheritance_visits_each_category_once():
    members = {
        "Root": members_page([], ["Left", "Right"]),
        "Left": members_page([], ["Shared"]),
        "Right": members_page([], ["Shared"]),
        "Shared": members_page(["File:S.jpg"], []),
    }
    client = ScriptedClient(members=members)
    nodes, _ = traverse_categories(client, ["Root"], depth=3)
    assert set(nodes) == {"Root", "Left", "Right", "Shared"}
    assert nodes["Shared"].parent in {"Left", "Right"}


def test_max_categories_bound_warns():
    members = {f"Cat{i}": members_page([], [f"Cat{i+1}"]) for i in range(10)}
    client = ScriptedClient(members=members)
    nodes, warnings = traverse_categories(client, ["Cat0"], depth=10, max_categories=3)
    assert len(nodes) == 3
    assert any("max_categories" in w for w in warnings)


# ---------------------------------------------------------------------------
# 4. Dedupe / multi-category / multi-class
# ---------------------------------------------------------------------------


def _audit_taxonomy(classes):
    return {"classes": classes}


def _class(slug, cats):
    return {"slug": slug, "canonical": slug.title(), "commons_categories": cats}


def test_file_in_two_categories_is_counted_once_with_both_memberships():
    members = {
        "Biryani": members_page(["File:Shared.jpg", "File:OnlyB.jpg"], []),
        "Chicken biryani": members_page(["File:Shared.jpg"], []),
    }
    files = {"File:Shared.jpg": file_page("File:Shared.jpg", pageid=1),
             "File:OnlyB.jpg": file_page("File:OnlyB.jpg", pageid=2)}
    client = ScriptedClient(members=members, files=files)
    result = run_audit(
        client,
        _audit_taxonomy([_class("biryani", ["Biryani", "Chicken biryani"])]),
        depth=0,
        source_mode="test",
    )
    manifest = result["manifest"]
    assert len(manifest) == 2  # unique files, not 3 memberships
    shared = next(r for r in manifest if r["title"] == "File:Shared.jpg")
    assert shared["categories"] == ["Biryani", "Chicken biryani"]
    assert shared["in_multiple_categories"] is True
    assert result["summary"]["files"]["raw_category_file_sum"] == 3
    assert result["summary"]["files"]["unique_file_titles"] == 2
    assert result["summary"]["files"]["overlap_entries_collapsed"] == 1


def test_file_spanning_two_classes_is_flagged_and_counted_in_both():
    members = {
        "Biryani": members_page(["File:Shared.jpg"], []),
        "Pulao": members_page(["File:Shared.jpg"], []),
    }
    files = {"File:Shared.jpg": file_page("File:Shared.jpg")}
    client = ScriptedClient(members=members, files=files)
    result = run_audit(
        client,
        _audit_taxonomy([_class("biryani", ["Biryani"]), _class("pulao", ["Pulao"])]),
        depth=0,
        source_mode="test",
    )
    record = result["manifest"][0]
    assert record["classes"] == ["biryani", "pulao"]
    assert record["in_multiple_classes"] is True
    assert result["summary"]["files"]["files_in_multiple_classes"] == 1
    per_class = {r["slug"]: r["unique_files"] for r in result["summary"]["per_class"]}
    # Counted in both classes; that double-count is visible, not hidden.
    assert per_class == {"biryani": 1, "pulao": 1}


def test_exact_sha1_duplicates_detected_and_labelled_as_exact_only():
    members = {"Biryani": members_page(["File:A.jpg", "File:B.jpg"], [])}
    files = {
        "File:A.jpg": file_page("File:A.jpg", pageid=1, sha1="same"),
        "File:B.jpg": file_page("File:B.jpg", pageid=2, sha1="same"),
    }
    client = ScriptedClient(members=members, files=files)
    result = run_audit(client, _audit_taxonomy([_class("biryani", ["Biryani"])]),
                       depth=0, source_mode="test")
    files_summary = result["summary"]["files"]
    assert files_summary["exact_sha1_duplicate_groups"] == 1
    assert files_summary["exact_sha1_duplicate_files"] == 2
    # Perceptual dedupe has NOT run; that must be explicit.
    assert any("perceptual" in u for u in result["summary"]["unknowns"])


def test_duplicate_normalized_titles_grouped():
    members = {"Biryani": members_page(["File:A.jpg", "File:a.jpg"], [])}
    files = {
        "File:A.jpg": file_page("File:A.jpg", pageid=1, sha1="x"),
        "File:a.jpg": file_page("File:a.jpg", pageid=2, sha1="y"),
    }
    client = ScriptedClient(members=members, files=files)
    result = run_audit(client, _audit_taxonomy([_class("biryani", ["Biryani"])]),
                       depth=0, source_mode="test")
    assert result["summary"]["files"]["duplicate_normalized_title_groups"] == 1


def test_normalize_title_handles_underscores_and_case():
    assert normalize_title("File:Aloo_Gobi.JPG") == "file:aloo gobi.jpg"
    assert normalize_title("  File:Aloo   Gobi.JPG ") == "file:aloo gobi.jpg"


# ---------------------------------------------------------------------------
# 5. Missing / incomplete metadata
# ---------------------------------------------------------------------------


def test_missing_licence_is_recorded_as_unknown_not_acceptable():
    members = {"Jalebi": members_page(["File:NoLic.jpg"], [])}
    files = {"File:NoLic.jpg": file_page("File:NoLic.jpg", licence=None)}
    client = ScriptedClient(members=members, files=files)
    result = run_audit(client, _audit_taxonomy([_class("jalebi", ["Jalebi"])]),
                       depth=0, source_mode="test")
    record = result["manifest"][0]
    assert record["licence"]["declared_class"] == UNKNOWN_MISSING
    assert record["licence"]["preliminarily_acceptable"] is False
    assert "missing_licence" in record["metadata_gaps"]


def test_missing_artist_and_permission_recorded():
    members = {"Jalebi": members_page(["File:NoArtist.jpg"], [])}
    files = {"File:NoArtist.jpg": file_page("File:NoArtist.jpg", artist=None)}
    client = ScriptedClient(members=members, files=files)
    result = run_audit(client, _audit_taxonomy([_class("jalebi", ["Jalebi"])]),
                       depth=0, source_mode="test")
    gaps = result["manifest"][0]["metadata_gaps"]
    assert "missing_artist" in gaps
    assert "missing_permission" in gaps
    assert result["summary"]["metadata_gaps"]["missing_artist"] == 1


def test_file_without_imageinfo_flagged():
    record = build_file_record("File:Broken.jpg", {"title": "File:Broken.jpg", "missing": True},
                               ["Jalebi"], ["jalebi"])
    assert "no_imageinfo" in record["metadata_gaps"]
    assert record["licence"]["declared_class"] == UNKNOWN_MISSING
    assert record["usable_for_training"] is False


def test_record_never_claims_usable_even_with_perfect_metadata():
    record = build_file_record(
        "File:Perfect.jpg",
        file_page("File:Perfect.jpg", licence="CC0", permission="see page"),
        ["Jalebi"], ["jalebi"],
    )
    assert record["licence"]["declared_class"] == CC0_PD
    assert record["usable_for_training"] is False
    assert "not assessed" in record["usable_reason"]


# ---------------------------------------------------------------------------
# 6. Invalid API responses and retry handling
# ---------------------------------------------------------------------------


def test_api_error_response_raises():
    client = CommonsClient(lambda p: {"error": {"code": "badtoken", "info": "nope"}})
    with pytest.raises(CommonsAPIError, match="badtoken"):
        client.query({"action": "query"})


def test_maxlag_error_is_retried_then_succeeds():
    responses = [
        {"error": {"code": "maxlag", "info": "lagged"}},
        {"query": {"pages": []}},
    ]
    sleeps = []
    client = CommonsClient(lambda p: responses.pop(0), sleep=sleeps.append)
    assert client.query({"action": "query"}) == {"query": {"pages": []}}
    assert sleeps  # backed off before retrying


def test_retry_exhaustion_raises():
    sleeps = []
    client = CommonsClient(lambda p: {"error": {"code": "maxlag", "info": "x"}},
                           sleep=sleeps.append, max_attempts=3)
    with pytest.raises(CommonsAPIError):
        client.query({"action": "query"})
    assert len(sleeps) == 2  # between attempts only


def test_transport_retries_transient_failures():
    from training.commons_audit import HttpTransport

    attempts = {"n": 0}

    def fake_urlopen(request, timeout=None):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise OSError("SSL_ERROR_SYSCALL")  # what the sandbox egress proxy does
        class Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps({"query": {"pages": []}}).encode()
        return Resp()

    import training.commons_audit as module
    original = module.urllib.request.urlopen
    module.urllib.request.urlopen = fake_urlopen
    try:
        transport = HttpTransport("UA", max_attempts=4, sleep=lambda s: None)
        assert transport({"action": "query"}) == {"query": {"pages": []}}
        assert attempts["n"] == 3
    finally:
        module.urllib.request.urlopen = original


def test_transport_gives_up_with_retryable_error():
    from training.commons_audit import HttpTransport

    def always_fail(request, timeout=None):
        raise OSError("SSL_ERROR_SYSCALL in connection to commons.wikimedia.org:443")

    import training.commons_audit as module
    original = module.urllib.request.urlopen
    module.urllib.request.urlopen = always_fail
    try:
        transport = HttpTransport("UA", max_attempts=2, sleep=lambda s: None)
        with pytest.raises(CommonsAPIError, match="unreachable"):
            transport({"action": "query"})
    finally:
        module.urllib.request.urlopen = original


def test_malformed_json_payload_is_retried_not_crashed():
    calls = {"n": 0}

    def transport(params):
        calls["n"] += 1
        if calls["n"] == 1:
            raise CommonsAPIError("bad payload", retryable=True)
        return {"query": {"pages": []}}

    client = CommonsClient(transport, sleep=lambda s: None)
    assert client.query({"action": "query"}) == {"query": {"pages": []}}


def test_formatversion_1_dict_pages_are_understood():
    """Commons may return pages as a dict (fv=1); parsing must not assume a list."""
    def transport(params):
        if params.get("prop") == "categoryinfo":
            return {"query": {"pages": {"123": {"title": "Category:Jalebi",
                                                "categoryinfo": {"files": 7, "subcats": 2}}}}}
        return {"query": {"pages": {"456": {"pageid": 456, "title": "File:A.jpg",
                                            "imageinfo": [file_page("File:A.jpg")["imageinfo"][0]]}}}}

    client = CommonsClient(transport)
    info = client.category_info(["Jalebi"])
    assert info["Jalebi"]["files"] == 7
    files = client.file_info(["File:A.jpg"])
    assert files["File:A.jpg"]["pageid"] == 456


def test_normalized_titles_are_matched_back():
    def transport(params):
        return {
            "query": {
                "normalized": [{"from": "Category:jalebi", "to": "Category:Jalebi"}],
                "pages": [{"title": "Category:Jalebi",
                           "categoryinfo": {"files": 3, "subcats": 0}}],
            }
        }

    client = CommonsClient(transport)
    assert client.category_info(["jalebi"])["jalebi"]["files"] == 3


def test_missing_category_reported_not_crashed():
    client = ScriptedClient(members={}, info={})
    nodes, _ = traverse_categories(client, ["DoesNotExist"], depth=1)
    assert nodes["DoesNotExist"].files == []
    result = run_audit(client, _audit_taxonomy([_class("x", ["DoesNotExist"])]),
                       depth=1, source_mode="test")
    # Category exists in traversal but has no categoryinfo -> still reported.
    assert result["summary"]["per_class"][0]["unique_files"] == 0


# ---------------------------------------------------------------------------
# 7. Count bands and taxonomy mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "count,band",
    [(0, "unknown_or_unassessed"), (1, "insufficient"), (49, "insufficient"),
     (50, "limited"), (99, "limited"), (100, "moderate"), (199, "moderate"),
     (200, "strong"), (5000, "strong")],
)
def test_count_potential_bands(count, band):
    assert count_potential_band(count) == band


def test_zero_count_with_unmeasured_flag_is_unknown():
    assert count_potential_band(0, unmeasured=True) == "unknown_or_unassessed"


def test_taxonomy_to_category_mapping_uses_declared_categories():
    members = {"Biryani": members_page(["File:B.jpg"], []),
               "Chicken biryani": members_page(["File:C.jpg"], [])}
    files = {"File:B.jpg": file_page("File:B.jpg", pageid=1),
             "File:C.jpg": file_page("File:C.jpg", pageid=2)}
    client = ScriptedClient(members=members, files=files,
                            info={"Biryani": (1, 0), "Chicken biryani": (1, 0)})
    result = run_audit(
        client,
        _audit_taxonomy([_class("biryani", ["Biryani", "Chicken biryani"])]),
        depth=0, source_mode="test",
    )
    row = result["summary"]["per_class"][0]
    assert row["categories_requested"] == ["Biryani", "Chicken biryani"]
    assert row["categories_found"] == ["Biryani", "Chicken biryani"]
    assert row["unique_files"] == 2


def test_class_inherits_files_from_subcategory():
    members = {
        "Biryani": members_page(["File:B.jpg"], ["Chicken biryani"]),
        "Chicken biryani": members_page(["File:C.jpg"], []),
    }
    files = {"File:B.jpg": file_page("File:B.jpg", pageid=1),
             "File:C.jpg": file_page("File:C.jpg", pageid=2)}
    client = ScriptedClient(members=members, files=files)
    result = run_audit(client, _audit_taxonomy([_class("biryani", ["Biryani"])]),
                       depth=2, source_mode="test")
    row = result["summary"]["per_class"][0]
    assert row["unique_files"] == 2  # subcategory file inherits the class


def test_missing_category_recorded_on_class():
    members = {"Biryani": members_page([], [])}
    client = ScriptedClient(members=members, info={"Biryani": (5, 0)})
    result = run_audit(
        client,
        _audit_taxonomy([_class("biryani", ["Biryani", "Nonexistent cat"])]),
        depth=0, source_mode="test",
    )
    row = result["summary"]["per_class"][0]
    assert row["categories_missing"] == ["Nonexistent cat"]


# ---------------------------------------------------------------------------
# 8. Manifest generation and report
# ---------------------------------------------------------------------------


def test_manifest_and_report_written(tmp_path):
    from training.commons_audit import main

    fixture = {
        "responses": [
            {"match": {"list": "categorymembers"},
             "pages": [members_page(["File:A.jpg"], [])]},
            {"match": {"prop": "categoryinfo"},
             "pages": [{"query": {"pages": [
                 {"title": "Category:Jalebi", "categoryinfo": {"files": 1, "subcats": 0}}]}}]},
            {"match": {"prop": "imageinfo"},
             "pages": [{"query": {"pages": [file_page("File:A.jpg")]}}]},
        ]
    }
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(json.dumps(fixture))
    taxonomy_path = tmp_path / "tax.json"
    taxonomy_path.write_text(json.dumps(_audit_taxonomy([_class("jalebi", ["Jalebi"])])))

    out = tmp_path / "out"
    code = main(["--taxonomy", str(taxonomy_path), "--out", str(out),
                 "--fixture", str(fixture_path), "--depth", "0"])
    assert code == 0
    manifest = json.loads((out / "commons_manifest.json").read_text())
    assert set(manifest) >= {"schema_version", "source_mode", "note", "files"}
    assert len(manifest["files"]) == 1
    assert manifest["files"][0]["title"] == "File:A.jpg"
    assert (out / "commons_audit_summary.json").exists()
    report = (out / "COMMONS_AUDIT_REPORT.md").read_text()
    assert "nothing here is training-ready" in report.lower()
    assert "Unique Commons files" in report


def test_manifest_record_has_required_provenance_fields():
    record = build_file_record(
        "File:A.jpg", file_page("File:A.jpg", permission="see page"), ["Jalebi"], ["jalebi"]
    )
    for key in ("pageid", "title", "url", "description_url", "width", "height",
                "mime", "licence", "attribution", "permission", "categories",
                "classes", "metadata_gaps", "usable_for_training"):
        assert key in record, key
    for key in ("declared_class", "short_name", "licence_url", "attribution_required",
                "verification", "requires_human_review", "preliminarily_acceptable"):
        assert key in record["licence"], key


def test_report_marks_every_class_not_ready():
    members = {"Jalebi": members_page(["File:A.jpg"], [])}
    files = {"File:A.jpg": file_page("File:A.jpg", licence="CC0")}
    client = ScriptedClient(members=members, files=files,
                            info={"Jalebi": (1, 0)})
    result = run_audit(client, _audit_taxonomy([_class("jalebi", ["Jalebi"])]),
                       depth=0, source_mode="test")
    assert all(row["training_ready"] is False for row in result["summary"]["per_class"])
    report = render_markdown(result["summary"]).lower()
    assert "training-ready" in report
    assert "not a prediction" in report or "not predictions" in report


def test_fixture_transport_matches_and_reports_unmatched():
    transport = FixtureTransport({"responses": [
        {"match": {"list": "categorymembers"}, "response": {"query": {"categorymembers": []}}}
    ]})
    assert transport({"list": "categorymembers", "cmtitle": "x"})["query"] == {"categorymembers": []}
    with pytest.raises(CommonsAPIError, match="no fixture rule"):
        transport({"list": "somethingelse"})


def test_no_network_is_used_in_tests(monkeypatch):
    """Runtime guard: an offline audit must never open a socket.

    Any real ``urlopen`` call is replaced with an immediate failure, so a test
    that accidentally reached for the network would fail loudly here.
    """
    import training.commons_audit as module

    def forbidden(*args, **kwargs):
        raise AssertionError("test attempted a real network request")

    monkeypatch.setattr(module.urllib.request, "urlopen", forbidden)

    members = {"Jalebi": members_page(["File:A.jpg"], [])}
    files = {"File:A.jpg": file_page("File:A.jpg", licence="CC0")}
    client = ScriptedClient(members=members, files=files, info={"Jalebi": (1, 0)})
    result = run_audit(client, _audit_taxonomy([_class("jalebi", ["Jalebi"])]),
                       depth=0, source_mode="test")
    assert result["summary"]["files"]["unique_file_titles"] == 1


# ---------------------------------------------------------------------------
# 9. Real taxonomy integration (offline, mocked responses)
# ---------------------------------------------------------------------------


def test_real_taxonomy_loads_and_maps_without_network():
    taxonomy = json.loads(TAXONOMY_PATH.read_text())
    assert len(taxonomy["classes"]) == 100
    with_categories = [c for c in taxonomy["classes"] if c.get("commons_categories")]
    assert with_categories, "expected the V3 taxonomy to declare Commons categories"

    client = ScriptedClient(members={}, files={})  # every category resolves to empty
    result = run_audit(client, taxonomy, depth=0, source_mode="test")
    assert len(result["summary"]["per_class"]) == 100
    # With no data every class is unmeasured/unknown, never "strong".
    bands = {r["count_potential_by_unique_files"] for r in result["summary"]["per_class"]}
    assert bands == {"unknown_or_unassessed"}
    assert all(r["training_ready"] is False for r in result["summary"]["per_class"])


# ---------------------------------------------------------------------------
# 10. End-to-end run against the recorded demo fixture
# ---------------------------------------------------------------------------

DEMO_FIXTURE = Path(__file__).parent / "fixtures/commons/demo_tree.json"


def test_end_to_end_demo_fixture(tmp_path):
    """Full CLI run offline: pagination, subcategory inheritance, overlap, dedupe."""
    from training.commons_audit import main

    tax = {"classes": [
        {"slug": "jalebi", "canonical": "Jalebi", "commons_categories": ["Jalebi"]},
        {"slug": "gulab_jamun", "canonical": "Gulab Jamun",
         "commons_categories": ["Gulab jamun"]},
        {"slug": "rasgulla", "canonical": "Rasgulla", "commons_categories": ["Rasgulla"]},
    ]}
    tax_path = tmp_path / "tax.json"
    tax_path.write_text(json.dumps(tax))
    out = tmp_path / "out"
    assert main(["--taxonomy", str(tax_path), "--out", str(out),
                 "--fixture", str(DEMO_FIXTURE), "--depth", "2"]) == 0

    manifest = json.loads((out / "commons_manifest.json").read_text())
    summary = json.loads((out / "commons_audit_summary.json").read_text())

    # Jalebi spans two API pages of categorymembers -> both reached.
    titles = {r["title"] for r in manifest["files"]}
    assert "File:Shared sweet.jpg" in titles  # second page of the paginated category
    # Subcategory file inherits the parent class.
    jalebi_3 = next(r for r in manifest["files"] if r["title"] == "File:Jalebi 3.jpg")
    assert jalebi_3["classes"] == ["jalebi"]
    # NC file present but not preliminarily acceptable.
    nc = next(r for r in manifest["files"] if r["title"] == "File:Jalebi 2.jpg")
    assert nc["licence"]["declared_class"] == NC_RESTRICTED
    assert nc["licence"]["preliminarily_acceptable"] is False
    # Exact SHA1 duplicate pair detected across different classes.
    assert summary["files"]["exact_sha1_duplicate_groups"] == 1
    # Missing licence and missing artist recorded, never silently accepted.
    assert summary["licences"]["by_declared_class"][UNKNOWN_MISSING] == 1
    assert summary["metadata_gaps"]["missing_artist"] >= 1
    # Rasgulla was requested but does not exist -> reported, not fabricated.
    assert "Rasgulla" in summary["categories"]["requested_missing"]
    # Nothing is ever marked ready or usable.
    assert all(r["training_ready"] is False for r in summary["per_class"])
    assert all(f["usable_for_training"] is False for f in manifest["files"])
    assert manifest["note"].startswith("Metadata only")
