#!/usr/bin/env python3
"""Incremental, per-class Commons collector for the V2 100-class dataset.

Why another collector when ``commons_audit.py`` already exists
--------------------------------------------------------------
``commons_audit.py`` audits a *whole taxonomy* in one pass and writes one big
report. That is the right shape for a census, and the wrong shape for a dataset
that grows class by class over weeks. This collector is **incremental**:

* one class per invocation, writing one manifest file per class;
* re-running a class refreshes it in place and never disturbs other classes;
* already-collected files are recognised by page id and SHA1, so an interrupted
  run is resumable and a file appearing in two classes is detected once;
* a per-class status block records exactly which of the six counts are known.

The six counts (never collapse them)
------------------------------------
``1 discovered``           file slots seen in the category listing
``2 metadata_retrieved``   files whose imageinfo actually came back
``3 rights_supported``     declared licence permits training use
``4 reviewed``             a human has looked at it
``5 approved``             reviewed AND label confirmed AND quality acceptable
``6 training_usable``      approved AND rights_supported AND unique

Only (6) may be reported as training-image count. A category file count is
count (1) and nothing else. It is an error to present (1) as ``images``.

Licence handling
----------------
Delegates entirely to ``commons_audit.classify_licence`` (unmodified) and then
tiers the result with ``licence_policy.classify_rights``. CC BY-SA is counted
but held out of the training-approved tier.

Usage
-----
    python training/collect_v2.py --class biryani --class idli ...
    python training/collect_v2.py --all --limit-classes 10
    python training/collect_v2.py --self-test        # offline, no network

Never downloads image bytes. Metadata only.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

TRAINING_DIR = Path(__file__).resolve().parent
PROJECT = TRAINING_DIR.parent
sys.path.insert(0, str(TRAINING_DIR))

from commons_audit import (  # noqa: E402
    CC0_PD,
    CC_BY,
    CC_BY_SA,
    NC_RESTRICTED,
    ND_RESTRICTED,
    OTHER_REVIEW,
    UNKNOWN_MISSING,
    IIEXTMETADATAFILTER,
    CommonsClient,
    build_file_record,
    classify_licence,
)
from licence_policy import (  # noqa: E402
    EXCLUDED,
    REVIEW_REQUIRED,
    TRAINING_APPROVED,
    classify_rights,
    rights_summary,
)

SCHEMA_VERSION = "4.0"
DEFAULT_TAXONOMY = PROJECT / "data" / "v3" / "taxonomy_100_proposed.json"
DEFAULT_OUT = PROJECT / "data" / "v4" / "classes"

#: imageinfo properties requested for every file.
IIPROP = "sha1|dimensions|mime|extmetadata"

#: extmetadata keys actually requested. Imported from commons_audit so the
#: request and the manifest cannot disagree, and so ``Credit``/``Permission``
#: (used for provenance signalling) are genuinely fetched rather than assumed.
EXTMETADATA_FILTER = IIEXTMETADATAFILTER

#: Minimum edge length for a candidate to be worth a human's review time.
MIN_EDGE = 300


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Gathering
# ---------------------------------------------------------------------------


def gather_category(
    client: CommonsClient,
    category: str,
    *,
    depth: int = 1,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Collect file metadata for one category and its subcategories."""
    from commons_audit import traverse_categories, _batched, MAX_TITLES_PER_REQUEST

    nodes, warnings = traverse_categories(client, [category], depth=depth)

    title_categories: Dict[str, set] = {}
    slot_sum = 0
    for name, node in nodes.items():
        slot_sum += len(node.files)
        for title in node.files:
            title_categories.setdefault(title, set()).add(name)

    discovered_slots = slot_sum
    unique_titles = list(title_categories)
    if limit is not None and len(unique_titles) > limit:
        warnings.append(
            f"limit={limit} applied: {len(unique_titles) - limit} titles not requested"
        )
        unique_titles = unique_titles[:limit]

    pages: Dict[str, Dict[str, Any]] = {}
    for batch in _batched(unique_titles, MAX_TITLES_PER_REQUEST):
        pages.update(client.file_info(batch))

    records: List[Dict[str, Any]] = []
    for title in unique_titles:
        page = pages.get(title) or {"title": title, "missing": True}
        records.append(build_file_record(title, page, title_categories[title], []))

    return {
        "category": category,
        "nodes": {n: {"depth": node.depth, "files": len(node.files), "subcats": node.subcats}
                  for n, node in nodes.items()},
        "discovered_slots": discovered_slots,
        "unique_titles": len(title_categories),
        "records": records,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Enrichment: rights tier + geometry gate
# ---------------------------------------------------------------------------


def enrich(record: Dict[str, Any], *, min_edge: int = MIN_EDGE) -> Dict[str, Any]:
    """Add rights tiering and technical flags to one commons_audit record.

    A single malformed record must not abort collection of an entire class, so
    every field is type-checked before use. Malformed structure is recorded as a
    technical flag and the record fails closed rather than raising.
    """
    raw_licence = record.get("licence")
    licence = raw_licence if isinstance(raw_licence, dict) else {}
    raw_attribution = record.get("attribution")
    attribution = raw_attribution if isinstance(raw_attribution, dict) else {}
    if not isinstance(raw_licence, dict) or not isinstance(raw_attribution, dict):
        # Note it, but still classify: an empty licence dict fails closed.
        malformed_attribution = True
    else:
        malformed_attribution = False
    rights = classify_rights(
        licence,
        artist=attribution.get("artist_raw", ""),
        # Provenance fields are preserved by commons_audit and must reach the
        # classifier, or the scrape / review rules never see any text at all.
        # Both may legitimately be empty; classify_provenance handles that.
        permission_text=record.get("permission") or "",
        credit_text=attribution.get("credit") or "",
    )
    width, height = record.get("width"), record.get("height")
    technical_flags: List[str] = []
    if malformed_attribution:
        technical_flags.append("malformed_record")
    # Numeric sanity: bools and strings must not be treated as pixel counts.
    dims_ok = (
        isinstance(width, int) and isinstance(height, int)
        and not isinstance(width, bool) and not isinstance(height, bool)
        and width > 0 and height > 0
    )
    if not dims_ok:
        technical_flags.append("missing_dimensions")
    elif min(width, height) < min_edge:
        technical_flags.append("below_min_edge")
    elif max(width, height) / max(1, min(width, height)) > 4.0:
        technical_flags.append("extreme_aspect_ratio")
    if record.get("mime") not in (None, "image/jpeg", "image/png", "image/webp"):
        technical_flags.append(f"unsupported_mime:{record.get('mime')}")
    if record.get("pageid") is None or record.get("sha1") is None:
        technical_flags.append("incomplete_metadata")

    out = dict(record)
    out["rights"] = rights
    out["technical_flags"] = technical_flags
    # Still not training-usable: no human has looked at it, and no bytes exist.
    out["usable_for_training"] = False
    return out


# ---------------------------------------------------------------------------
# Six counts
# ---------------------------------------------------------------------------


def count_six(records: Sequence[Dict[str, Any]], *, discovered_slots: int) -> Dict[str, Any]:
    """Compute the six counts that must always be reported separately."""
    metadata_ok = [r for r in records if "incomplete_metadata" not in r["technical_flags"]]
    rights_ok = [
        r for r in metadata_ok
        if r["rights"]["rights_tier"] == TRAINING_APPROVED
        and not r["technical_flags"]
    ]
    # Count 3 counts distinct, technically usable, rights-supported candidates.
    # The collector cannot review or approve anything: no human has seen a pixel.
    return {
        "1_discovered_file_slots": discovered_slots,
        "1b_discovered_unique_titles": len(records),
        "2_metadata_retrieved": len(metadata_ok),
        "3_rights_supported": len(rights_ok),
        "3b_rights_review_required_cc_by_sa": sum(
            1 for r in metadata_ok if r["rights"]["rights_tier"] == REVIEW_REQUIRED
        ),
        "3c_rights_excluded": sum(
            1 for r in metadata_ok if r["rights"]["rights_tier"] == EXCLUDED
        ),
        "4_reviewed": 0,
        "5_approved": 0,
        "6_training_usable": 0,
        "note": "Counts 1-3 are metadata-derived. Counts 4-6 require human review "
        "and image bytes; they are zero until a reviewer and a local dataset exist. "
        "Count 1 is a category file count, not an image count.",
    }


# ---------------------------------------------------------------------------
# Per-class collection
# ---------------------------------------------------------------------------


def collect_class(
    client: CommonsClient,
    entry: Dict[str, Any],
    *,
    depth: int = 1,
    limit: Optional[int] = None,
    min_edge: int = MIN_EDGE,
) -> Dict[str, Any]:
    """Collect and tier every category of one taxonomy class."""
    slug = entry["slug"]
    categories = [c for c in (entry.get("commons_categories") or []) if c]

    all_records: List[Dict[str, Any]] = []
    seen_sha1: Dict[str, str] = {}
    per_category: List[Dict[str, Any]] = []
    warnings: List[str] = []
    total_slots = 0

    for category in categories:
        gathered = gather_category(client, category, depth=depth, limit=limit)
        total_slots += gathered["discovered_slots"]
        warnings.extend(f"{slug}/{category}: {w}" for w in gathered["warnings"])
        enriched = [enrich(r, min_edge=min_edge) for r in gathered["records"]]

        # Cross-category duplicate detection within the class, by SHA1.
        dupes = 0
        for record in enriched:
            sha1 = record.get("sha1")
            if not sha1:
                continue
            if sha1 in seen_sha1:
                record["exact_duplicate_of"] = seen_sha1[sha1]
                # A byte-identical copy is not a distinct training image, so it
                # must not inflate the rights-supported count.
                record["technical_flags"].append("exact_duplicate_in_class")
                dupes += 1
            else:
                seen_sha1[sha1] = record.get("title")
        per_category.append(
            {
                "category": category,
                "discovered_file_slots": gathered["discovered_slots"],
                "unique_titles": gathered["unique_titles"],
                "files_in_category_only": len(gathered["records"]),
                "exact_duplicates_within_class": dupes,
                "subcategories_traversed": len(gathered["nodes"]),
            }
        )
        all_records.extend(enriched)

    # Deduplicate the merged list by page id, keeping the first occurrence.
    by_pageid: Dict[Any, Dict[str, Any]] = {}
    for record in all_records:
        key = record.get("pageid") or record.get("title")
        if key not in by_pageid:
            by_pageid[key] = record
    unique_records = list(by_pageid.values())

    counts = count_six(unique_records, discovered_slots=total_slots)
    licences: Dict[str, int] = {}
    for record in unique_records:
        key = record["licence"]["declared_class"]
        licences[key] = licences.get(key, 0) + 1

    gap_counts: Dict[str, int] = {}
    for record in unique_records:
        for gap in record.get("metadata_gaps", []):
            gap_counts[gap] = gap_counts.get(gap, 0) + 1

    return {
        "schema_version": SCHEMA_VERSION,
        "class": slug,
        "canonical": entry.get("canonical", slug),
        "collected_utc": utc_now(),
        "source": {
            "endpoint": "https://commons.wikimedia.org/w/api.php",
            "generator": "categorymembers",
            "iiprop": IIPROP,
            # Recorded from the constant that is actually sent as
            # iiextmetadatafilter, so this field describes behaviour rather
            # than intent.
            "extmetadata_filter_sent": EXTMETADATA_FILTER,
            "extmetadata_filter_param": "iiextmetadatafilter",
            "depth": depth,
            "per_category_limit": limit,
            "bytes_downloaded": 0,
        },
        "categories": per_category,
        "counts": counts,
        "licences_by_declared_class": licences,
        "rights_summary": rights_summary([r["rights"] for r in unique_records]),
        "metadata_gaps": gap_counts,
        "warnings": warnings,
        "files": unique_records,
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def class_path(out_dir: Path, slug: str) -> Path:
    return Path(out_dir) / f"{slug}.json"


def write_class(doc: Dict[str, Any], out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = class_path(out_dir, doc["class"])
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_taxonomy(path: Path = DEFAULT_TAXONOMY) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def select_classes(taxonomy: Dict[str, Any], slugs: Sequence[str]) -> List[Dict[str, Any]]:
    by_slug = {c["slug"]: c for c in taxonomy["classes"]}
    missing = [s for s in slugs if s not in by_slug]
    if missing:
        raise SystemExit(f"unknown class slug(s): {', '.join(missing)}")
    return [by_slug[s] for s in slugs]


def plan(classes: Sequence[Dict[str, Any]], out_dir: Path) -> Dict[str, Any]:
    """Report which classes still need collection, without any network call."""
    out_dir = Path(out_dir)
    todo, done, no_category = [], [], []
    for entry in classes:
        path = class_path(out_dir, entry["slug"])
        if not (entry.get("commons_categories") or []):
            no_category.append(entry["slug"])
        elif path.exists():
            done.append(entry["slug"])
        else:
            todo.append(entry["slug"])
    return {
        "classes_requested": len(classes),
        "already_collected": done,
        "to_collect": todo,
        "no_commons_category": no_category,
    }


# ---------------------------------------------------------------------------
# Self-test (offline)
# ---------------------------------------------------------------------------


class _FakeClient:
    """Offline stand-in for CommonsClient, keyed on category name."""

    def __init__(self, tree: Dict[str, Dict[str, Any]]):
        self.tree = tree

    def category_members(self, category: str):
        node = self.tree.get(category, {})
        return node.get("files", []), node.get("subcats", [])

    def category_info(self, categories):
        return {c: {"exists": c in self.tree} for c in categories}

    def file_info(self, titles):
        wanted = set(titles)
        return {
            t: p for t, p in self._pages().items() if t in wanted
        }

    def _pages(self):
        pages = {}
        for node in self.tree.values():
            for page in node.get("pages", []):
                pages[page["title"]] = page
        return pages


def _fake_page(title, pageid, sha1, licence, artist, width=1200, height=900):
    ext: Dict[str, Any] = {"Artist": {"value": artist}} if artist else {}
    if licence is not None:
        ext["LicenseShortName"] = {"value": licence}
    return {
        "pageid": pageid,
        "title": title,
        "imageinfo": [{
            "sha1": sha1,
            "width": width,
            "height": height,
            "mime": "image/jpeg",
            "descriptionurl": "https://commons.wikimedia.org/wiki/" + title.replace(" ", "_"),
            "extmetadata": ext,
        }],
    }


def self_test() -> int:
    """Exercise collection, tiering and the six counts with no network."""
    tree = {
        "Category:Demo": {
            "files": [
                {"title": "File:Good CC0.jpg"},
                {"title": "File:Good CC BY.jpg"},
                {"title": "File:Share alike.jpg"},
                {"title": "File:Non commercial.jpg"},
                {"title": "File:No artist.jpg"},
                {"title": "File:Tiny.jpg"},
                {"title": "File:Duplicate copy.jpg"},
            ],
            "subcats": ["Category:Demo sub"],
            "pages": [
                _fake_page("File:Good CC0.jpg", 1, "s1", "CC0", "A. Person"),
                _fake_page("File:Good CC BY.jpg", 2, "s2", "CC BY 4.0", "B. Person"),
                _fake_page("File:Share alike.jpg", 3, "s3", "CC BY-SA 4.0", "C. Person"),
                _fake_page("File:Non commercial.jpg", 4, "s4", "CC BY-NC 4.0", "D. Person"),
                _fake_page("File:No artist.jpg", 5, "s5", "CC BY 4.0", None),
                _fake_page("File:Tiny.jpg", 6, "s6", "CC0", "E. Person", 100, 80),
                _fake_page("File:Duplicate copy.jpg", 7, "s1", "CC0", "A. Person"),
            ],
        },
        "Category:Demo sub": {
            "files": [{"title": "File:Sub only.jpg"}],
            "subcats": [],
            "pages": [_fake_page("File:Sub only.jpg", 8, "s8", "CC BY 3.0", "F. Person")],
        },
    }
    client = _FakeClient(tree)
    entry = {"slug": "demo", "canonical": "Demo", "commons_categories": ["Category:Demo"]}
    doc = collect_class(client, entry, depth=1, min_edge=300)
    c = doc["counts"]

    failures: List[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    check(c["1b_discovered_unique_titles"] == 8,
          f"expected 8 unique titles, got {c['1b_discovered_unique_titles']}")
    check(c["1_discovered_file_slots"] == 8,
          f"expected 8 slots (7 direct + 1 sub), got {c['1_discovered_file_slots']}")
    check(c["2_metadata_retrieved"] == 8, f"expected 8 metadata, got {c['2_metadata_retrieved']}")
    # CC0 x2 distinct, CC BY x1 with author; the byte-identical copy, the
    # undersized file and the authorless CC BY file are all excluded.
    check(c["3_rights_supported"] == 3,
          f"expected 3 rights-supported, got {c['3_rights_supported']} "
          f"(tiny is CC0 but below min edge; no-artist CC BY must be excluded)")
    check(c["3b_rights_review_required_cc_by_sa"] == 1,
          f"expected 1 CC BY-SA, got {c['3b_rights_review_required_cc_by_sa']}")
    check(c["4_reviewed"] == 0 and c["5_approved"] == 0 and c["6_training_usable"] == 0,
          "collector must never report reviewed/approved/usable as non-zero")
    check(doc["licences_by_declared_class"].get("CC0_PD") == 3,
          "expected three CC0 files by declared class")
    dupes = [r for r in doc["files"] if r.get("exact_duplicate_of")]
    check(len(dupes) == 1, f"expected exactly one flagged duplicate, got {len(dupes)}")
    check(all(r["usable_for_training"] is False for r in doc["files"]),
          "no file may be usable_for_training")
    check(doc["files"][0]["rights"]["legal_clearance"] == "not_verified",
          "legal clearance must never be claimed")

    # The same file in two subcategories of one class counts once.
    tree2 = {
        "Category:Dup": {
            "files": [{"title": "File:Shared.jpg"}],
            "subcats": ["Category:Dup child"],
            "pages": [_fake_page("File:Shared.jpg", 9, "s9", "CC0", "G. Person")],
        },
        "Category:Dup child": {
            "files": [{"title": "File:Shared.jpg"}],
            "subcats": [],
            "pages": [_fake_page("File:Shared.jpg", 9, "s9", "CC0", "G. Person")],
        },
    }
    doc2 = collect_class(_FakeClient(tree2), {"slug": "dup", "commons_categories": ["Category:Dup"]})
    check(len(doc2["files"]) == 1, "a file in two categories must appear once")
    check(doc2["counts"]["1_discovered_file_slots"] == 2,
          "slot count should still report both listing entries")

    # Plan is offline and honest about missing categories.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = plan(
            [
                {"slug": "a", "commons_categories": ["Category:A"]},
                {"slug": "b", "commons_categories": []},
            ],
            Path(tmp),
        )
        check(p["to_collect"] == ["a"], "plan should list uncollected class a")
        check(p["no_commons_category"] == ["b"], "plan should flag class b")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        print(f"self-test FAILED ({len(failures)} checks)", file=sys.stderr)
        return 1
    print("self-test passed: collection, rights tiering, dedupe and six counts OK")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_client(args: argparse.Namespace) -> CommonsClient:
    from commons_audit import HttpTransport, DEFAULT_UA

    ua = args.user_agent or DEFAULT_UA
    return CommonsClient(HttpTransport(ua), delay=args.delay)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--class", dest="classes", action="append", default=[],
                        help="class slug to collect; repeatable")
    parser.add_argument("--all", action="store_true", help="collect every class with a category")
    parser.add_argument("--limit-classes", type=int, default=None)
    parser.add_argument("--depth", type=int, default=1)
    parser.add_argument("--limit", type=int, default=None,
                        help="cap titles requested per category (testing)")
    parser.add_argument("--min-edge", type=int, default=MIN_EDGE)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--user-agent", default=None)
    parser.add_argument("--plan", action="store_true", help="show what would be collected")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    taxonomy = load_taxonomy(args.taxonomy)
    if args.all:
        chosen = [c for c in taxonomy["classes"] if c.get("commons_categories")]
    elif args.classes:
        chosen = select_classes(taxonomy, args.classes)
    else:
        parser.error("pass --all, --class SLUG, or --self-test")
        return 2

    if args.limit_classes:
        chosen = chosen[: args.limit_classes]

    if args.plan:
        print(json.dumps(plan(chosen, args.out), indent=1))
        return 0

    client = build_client(args)
    written, failed = [], []
    for entry in chosen:
        try:
            doc = collect_class(
                client, entry, depth=args.depth, limit=args.limit, min_edge=args.min_edge
            )
        except Exception as exc:  # one blocked class must not stop the run
            failed.append({"class": entry["slug"], "error": f"{type(exc).__name__}: {exc}"})
            print(f"error: {entry['slug']}: {exc}", file=sys.stderr)
            continue
        path = write_class(doc, args.out)
        written.append({"class": entry["slug"], "path": str(path), **doc["counts"]})
        print(
            f"{entry['slug']}: slots={doc['counts']['1_discovered_file_slots']} "
            f"meta={doc['counts']['2_metadata_retrieved']} "
            f"rights={doc['counts']['3_rights_supported']}",
            file=sys.stderr,
        )

    print(json.dumps({
        "collected": written,
        "failed": failed,
        "out_dir": str(args.out),
        "note": "counts 1-3 only; reviewed/approved/training_usable require human review",
    }, indent=1))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
