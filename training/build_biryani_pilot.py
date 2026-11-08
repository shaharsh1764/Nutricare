#!/usr/bin/env python3
"""Build and analyse the Biryani pilot manifest from real Commons metadata.

Consumes the raw API transcriptions in ``data/v3/commons_pilot/raw/*.json``,
de-duplicates by Commons page id **and** SHA1 while preserving every category
membership, classifies each file's declared licence with the V2 auditor's
classifier, and writes:

  data/v3/commons_pilot/biryani_manifest.json   one record per unique file
  data/v3/commons_pilot/biryani_pilot_summary.json  aggregate + per-category

This stage performs **no network access and no image download**. It also does
not judge relevance, quality, or label correctness, and it does not mark any
file usable or training-ready.

Usage:
    python training/build_biryani_pilot.py
    python training/build_biryani_pilot.py --raw data/v3/commons_pilot/raw --out /tmp/x
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from training.commons_audit import (  # noqa: E402
    CC0_PD,
    CC_BY,
    CC_BY_SA,
    NC_RESTRICTED,
    ND_RESTRICTED,
    OTHER_REVIEW,
    PRELIMINARILY_ACCEPTABLE,
    UNKNOWN_MISSING,
    classify_licence,
    count_potential_band,
    normalize_title,
)

CLASS_SLUG = "biryani"
CLASS_CANONICAL = "Biryani"

#: Categories the taxonomy declares for the `biryani` class.
TAXONOMY_CATEGORIES = ["Biryani", "Chicken biryani", "Hyderabadi biryani"]


def _licence_block(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Classify a transcribed file's declared licence via the shared classifier.

    The raw rows store flattened fields, so rebuild the extmetadata shape the
    classifier expects. Nothing is inferred: absent fields stay absent.
    """
    extmetadata: Dict[str, Any] = {}
    if raw.get("license_short"):
        extmetadata["LicenseShortName"] = {"value": raw["license_short"]}
    if raw.get("license_url"):
        extmetadata["LicenseUrl"] = {"value": raw["license_url"]}
    if raw.get("artist"):
        extmetadata["Artist"] = {"value": raw["artist"]}
    if raw.get("attribution_required") is not None:
        extmetadata["AttributionRequired"] = {"value": str(raw["attribution_required"])}
    if raw.get("permission"):
        extmetadata["Permission"] = {"value": raw["permission"]}
    return classify_licence(extmetadata)


def load_raw(raw_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Return {category: [raw rows]} from the transcription files."""
    by_category: Dict[str, List[Dict[str, Any]]] = {}
    for path in sorted(raw_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        category = (payload.get("_provenance") or {}).get("category")
        if not category:
            continue
        by_category.setdefault(category, []).extend(payload.get("pages", []))
    return by_category


def build_manifest(by_category: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Merge per-category rows into one record per unique Commons file."""
    merged: Dict[int, Dict[str, Any]] = {}
    for category, rows in by_category.items():
        for raw in rows:
            pageid = raw.get("pageid")
            record = merged.setdefault(
                pageid,
                {
                    "pageid": pageid,
                    "title": raw.get("title"),
                    "sha1": raw.get("sha1"),
                    "width": raw.get("width"),
                    "height": raw.get("height"),
                    "mime": raw.get("mime"),
                    "raw_licence_short": raw.get("license_short"),
                    "raw_artist": raw.get("artist"),
                    "categories": [],
                },
            )
            if category not in record["categories"]:
                record["categories"].append(category)

    records: List[Dict[str, Any]] = []
    for pageid, record in merged.items():
        title = record["title"] or ""
        licence = _licence_block(
            {
                "license_short": record["raw_licence_short"],
                "artist": record["raw_artist"],
            }
        )
        gaps: List[str] = []
        if not record.get("sha1"):
            gaps.append("missing_sha1")
        if not record.get("width") or not record.get("height"):
            gaps.append("missing_dimensions")
        if licence["declared_class"] == UNKNOWN_MISSING:
            gaps.append("missing_licence")
        if not record.get("raw_artist"):
            gaps.append("missing_artist")

        categories = sorted(record["categories"])
        records.append(
            {
                "pageid": pageid,
                "title": title,
                "normalized_title": normalize_title(title),
                "description_url": "https://commons.wikimedia.org/wiki/"
                + title.replace(" ", "_"),
                "sha1": record.get("sha1"),
                "width": record.get("width"),
                "height": record.get("height"),
                "mime": record.get("mime"),
                "licence": licence,
                "attribution": {
                    "artist_raw": record.get("raw_artist") or "",
                    "attribution_required": licence["attribution_required"],
                },
                "categories": categories,
                "classes": [CLASS_SLUG],
                "in_multiple_categories": len(categories) > 1,
                "metadata_gaps": gaps,
                "usable_for_training": False,
                "usable_reason": "not assessed: relevance, quality, duplicates and "
                "label correctness require further inspection",
            }
        )
    records.sort(key=lambda r: (r["pageid"] or 0))
    return records


def analyse(records: List[Dict[str, Any]], by_category: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    licence_counts: Dict[str, int] = {}
    for record in records:
        key = record["licence"]["declared_class"]
        licence_counts[key] = licence_counts.get(key, 0) + 1

    gap_counts: Dict[str, int] = {}
    for record in records:
        for gap in record["metadata_gaps"]:
            gap_counts[gap] = gap_counts.get(gap, 0) + 1

    # Exact-byte duplicates as reported by Commons SHA1 (not perceptual hashing).
    sha1_groups: Dict[str, List[str]] = {}
    for record in records:
        if record.get("sha1"):
            sha1_groups.setdefault(record["sha1"], []).append(record["title"])
    dup_sha1 = {k: v for k, v in sha1_groups.items() if len(v) > 1}

    norm_groups: Dict[str, List[str]] = {}
    for record in records:
        if record.get("normalized_title"):
            norm_groups.setdefault(record["normalized_title"], []).append(record["title"])
    dup_norm = {k: v for k, v in norm_groups.items() if len(v) > 1}

    per_category: List[Dict[str, Any]] = []
    for category, rows in sorted(by_category.items()):
        members = [r for r in records if category in r["categories"]]
        acceptable = [r for r in members if r["licence"]["preliminarily_acceptable"]]
        per_category.append(
            {
                "category": category,
                "raw_rows_returned": len(rows),
                "unique_files_in_category": len(members),
                "files_acceptable_licence": len(acceptable),
                "files_in_multiple_categories": sum(
                    1 for r in members if r["in_multiple_categories"]
                ),
                "count_potential": count_potential_band(len(members)),
            }
        )

    acceptable_total = sum(
        1 for r in records if r["licence"]["preliminarily_acceptable"]
    )
    summary = {
        "class_slug": CLASS_SLUG,
        "class_canonical": CLASS_CANONICAL,
        "taxonomy_categories": TAXONOMY_CATEGORIES,
        "measured": {
            "categories_captured_per_file": sorted(by_category),
            "raw_rows_across_captured_categories": sum(
                len(v) for v in by_category.values()
            ),
            "unique_commons_files": len(records),
            "unique_pageids": len({r["pageid"] for r in records}),
            "unique_sha1_values": len({r["sha1"] for r in records if r["sha1"]}),
            "files_in_multiple_categories": sum(
                1 for r in records if r["in_multiple_categories"]
            ),
            "exact_sha1_duplicate_groups": len(dup_sha1),
            "exact_sha1_duplicate_files": sum(len(v) for v in dup_sha1.values()),
            "duplicate_normalized_title_groups": len(dup_norm),
            "licence_distribution": licence_counts,
            "preliminarily_acceptable": acceptable_total,
            "unknown_or_unsuitable": len(records) - acceptable_total,
            "metadata_gaps": gap_counts,
            "count_potential_by_unique_files": count_potential_band(len(records)),
            "count_potential_by_acceptable_licence": count_potential_band(
                acceptable_total
            ),
        },
        "per_category": per_category,
        "duplicate_groups_sha1": [
            {"sha1": k, "titles": v} for k, v in dup_sha1.items()
        ],
        "multi_category_files": [
            {"title": r["title"], "categories": r["categories"]}
            for r in records
            if r["in_multiple_categories"]
        ],
        "not_determined": [
            "image relevance to the labelled dish",
            "visual quality, framing, resolution adequacy",
            "perceptual / near-duplicate rate (needs image bytes)",
            "label correctness and class separability",
            "whether any file is legally cleared for redistribution",
            "categories beyond those captured here (the full biryani tree is larger)",
        ],
        "training_ready": False,
        "training_ready_reason": "count and licence screening only; no relevance, "
        "quality, duplicate or label review performed",
    }
    return summary


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Biryani pilot manifest.")
    parser.add_argument("--raw", default="data/v3/commons_pilot/raw")
    parser.add_argument("--out", default="data/v3/commons_pilot")
    args = parser.parse_args(argv)

    raw_dir = Path(args.raw)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    by_category = load_raw(raw_dir)
    if not by_category:
        print(f"error: no transcription files found in {raw_dir}", file=sys.stderr)
        return 2

    records = build_manifest(by_category)
    summary = analyse(records, by_category)

    manifest = {
        "schema_version": "1.0-pilot",
        "source_mode": "real_commons_metadata",
        "class": CLASS_SLUG,
        "note": "Real Commons metadata. No image bytes were downloaded. No file is "
        "verified, licence-cleared, or training-ready.",
        "provenance": "See data/v3/commons_pilot/raw/*.json _provenance blocks.",
        "counts_are": "unique Commons files meeting at least one captured category",
        "files": records,
    }
    (out_dir / "biryani_manifest.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out_dir / "biryani_pilot_summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    m = summary["measured"]
    print(
        f"categories={len(by_category)} unique_files={m['unique_commons_files']} "
        f"acceptable={m['preliminarily_acceptable']} "
        f"multi_cat={m['files_in_multiple_categories']} "
        f"sha1_dups={m['exact_sha1_duplicate_groups']}"
    )
    print(f"wrote {out_dir/'biryani_manifest.json'}")
    print(f"wrote {out_dir/'biryani_pilot_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
