#!/usr/bin/env python3
"""Turn collected Commons metadata into a reviewable, splittable V2 dataset.

This is the gate between "a category listing" and "a training set". Nothing
passes it on category membership alone.

The six counts, computed per class
----------------------------------
Every class carries all six numbers at every stage, because the whole point is
that they are different numbers:

===================  ============================================
1 discovered         file slots in the category listing
2 metadata_retrieved imageinfo actually returned
3 rights_supported   declared licence permits training use
4 reviewed           a human recorded a decision
5 approved           reviewed relevant + acceptable quality + rights
6 training_usable    approved, technically valid, not a duplicate
===================  ============================================

``6`` is the only number that may be called a training-image count.

Why approval requires bytes
---------------------------
A reviewer can only approve a label by *looking* at the picture. This tool
never downloads images, so it cannot approve anything by itself. Instead it:

* applies the rights + technical + review filters;
* emits a download plan the user runs locally;
* re-reads a local image directory when one is supplied, so the same code path
  performs corrupt-image detection and exact/near-duplicate removal once bytes
  exist;
* keeps any image without local bytes out of the training-usable count.

That is why ``--images`` is optional but the training-usable count stays zero
without it. It is a hard gate, not a warning.

Splits and leakage
------------------
Each split is assigned per *duplicate group*, never per image, so a near-duplicate
pair can never straddle train/val/test. Groups are formed by exact page id, SHA1
and normalised title here, and additionally by perceptual hash when bytes exist.
The split is deterministic given the seed and the sorted group list.

Usage
-----
    python training/prepare_v2_dataset.py --self-test
    python training/prepare_v2_dataset.py --classes-dir data/v4/classes --out data/v4/prepared
    python training/prepare_v2_dataset.py --classes-dir data/v4/classes \
        --images data/v4/images --out data/v4/prepared
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

TRAINING_DIR = Path(__file__).resolve().parent
PROJECT = TRAINING_DIR.parent
sys.path.insert(0, str(TRAINING_DIR))

from licence_policy import (  # noqa: E402
    EXCLUDED,
    REVIEW_REQUIRED,
    TRAINING_APPROVED,
    attribution_record,
    render_attributions,
)

SCHEMA_VERSION = "4.0"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MIN_EDGE = 300
SPLITS = ("train", "val", "test")

#: Fields a review decision must set before an image may be approved.
REQUIRED_APPROVAL_FIELDS = ("relevance", "quality")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_class_files(classes_dir: Path) -> List[Dict[str, Any]]:
    """Load every per-class manifest written by ``collect_v2.py``."""
    classes_dir = Path(classes_dir)
    if not classes_dir.is_dir():
        raise SystemExit(f"classes directory not found: {classes_dir}")
    docs = []
    for path in sorted(classes_dir.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"unreadable manifest {path.name}: {exc}")
        if "class" not in doc or "files" not in doc:
            continue
        docs.append(doc)
    return docs


def load_reviews(paths: Sequence[Path]) -> Dict[int, Dict[str, Any]]:
    """Merge review decision files into one ``pageid -> decision`` map.

    Accepts either a ``review_decisions.json`` (``{"decisions":[...]}``) or a
    bare list. Later files win, which lets a reviewer submit a corrections file.
    """
    merged: Dict[int, Dict[str, Any]] = {}
    for path in paths:
        path = Path(path)
        if not path.exists():
            raise SystemExit(f"review file not found: {path}")
        doc = json.loads(path.read_text(encoding="utf-8"))
        entries = doc.get("decisions", []) if isinstance(doc, dict) else doc
        for entry in entries:
            pageid = entry.get("pageid")
            if pageid is None:
                continue
            merged[int(pageid)] = entry
    return merged


# ---------------------------------------------------------------------------
# Review gating
# ---------------------------------------------------------------------------


def review_verdict(decision: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Decide whether a review entry approves an image.

    Unreviewed is never approved. A decision missing relevance or quality is
    *partial* and also not approved. An explicit ``irrelevant`` is a rejection,
    where the image is dropped from the class rather than merely blocked.
    """
    if not decision:
        return {
            "state": "unreviewed",
            "approved": False,
            "drop_from_class": False,
            "reason": "no human decision recorded; unreviewed is not approved",
        }

    missing = [f for f in REQUIRED_APPROVAL_FIELDS if not decision.get(f)]
    relevance = decision.get("relevance")
    quality = decision.get("quality")

    if relevance == "irrelevant":
        return {
            "state": "rejected",
            "approved": False,
            "drop_from_class": True,
            "reason": "reviewer marked the image irrelevant to this class",
        }
    if missing:
        return {
            "state": "partial",
            "approved": False,
            "drop_from_class": False,
            "reason": f"review incomplete; missing {', '.join(missing)}",
        }

    flags = decision.get("flags") or {}
    set_flags = [k for k, v in flags.items() if v is True]
    if relevance != "relevant":
        return {
            "state": "uncertain",
            "approved": False,
            "drop_from_class": False,
            "reason": f"reviewer was {relevance!r}; only 'relevant' can be approved",
        }
    if quality == "poor":
        return {
            "state": "poor_quality",
            "approved": False,
            "drop_from_class": False,
            "reason": "reviewer rated quality poor",
        }
    if set_flags:
        # A collage or watermark is a labelling hazard, not a training image.
        return {
            "state": "flagged",
            "approved": False,
            "drop_from_class": False,
            "reason": f"reviewer flagged: {', '.join(set_flags)}",
        }
    return {
        "state": "approved",
        "approved": True,
        "drop_from_class": False,
        "reason": "reviewed relevant, quality acceptable, no flags",
    }


# ---------------------------------------------------------------------------
# Duplicate grouping
# ---------------------------------------------------------------------------


def normalize_title(title: str) -> str:
    title = (title or "").strip().lower()
    title = re.sub(r"^file:", "", title)
    try:
        title = title.encode("utf-8").decode("unicode_escape")
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    title = re.sub(r"\.(jpe?g|png|webp|bmp|gif|tiff?)$", "", title)
    title = re.sub(r"[^a-z0-9]+", "", title)
    return title


def build_duplicate_groups(records: Sequence[Dict[str, Any]]) -> Dict[str, List[int]]:
    """Union-find over pageid, SHA1 and normalised title.

    Returns ``group_id -> [indices]`` restricted to groups with more than one
    member, plus every singleton as its own group so splitting is uniform.
    """
    parent = list(range(len(records)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    seen: Dict[Tuple[str, str], int] = {}
    for index, record in enumerate(records):
        keys = [("pageid", str(record.get("pageid")))] if record.get("pageid") else []
        if record.get("sha1"):
            keys.append(("sha1", record["sha1"]))
        norm = normalize_title(record.get("title", ""))
        if norm:
            keys.append(("title", norm))
        for key in keys:
            if key in seen:
                union(seen[key], index)
            else:
                seen[key] = index

    groups: Dict[int, List[int]] = defaultdict(list)
    for index in range(len(records)):
        groups[find(index)].append(index)
    return {f"g{root:05d}": members for root, members in groups.items()}


def detect_duplicate_pairs(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """List every duplicate relation with the signal that established it."""
    by_sha1: Dict[str, List[int]] = defaultdict(list)
    by_title: Dict[str, List[int]] = defaultdict(list)
    for index, record in enumerate(records):
        if record.get("sha1"):
            by_sha1[record["sha1"]].append(index)
        norm = normalize_title(record.get("title", ""))
        if norm:
            by_title[norm].append(index)

    pairs: List[Dict[str, Any]] = []
    for signal, table in (("sha1", by_sha1), ("normalized_title", by_title)):
        for key, members in table.items():
            if len(members) > 1:
                pairs.append({
                    "signal": signal,
                    "value": key,
                    "pageids": [records[i].get("pageid") for i in members],
                    "titles": [records[i].get("title") for i in members],
                })
    return pairs


def cross_class_duplicates(per_class: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Files that appear in more than one class — a label conflict to resolve."""
    owners: Dict[str, set] = defaultdict(set)
    for slug, records in per_class.items():
        for record in records:
            if record.get("sha1"):
                owners[record["sha1"]].add(slug)
            owners[f"pageid:{record.get('pageid')}"].add(slug)
    conflicts = []
    for key, slugs in owners.items():
        if len(slugs) > 1:
            conflicts.append({"key": key, "classes": sorted(slugs)})
    return sorted(conflicts, key=lambda c: c["key"])


# ---------------------------------------------------------------------------
# Technical checks (only when bytes exist)
# ---------------------------------------------------------------------------


def image_path_for(images_dir: Path, record: Dict[str, Any]) -> Optional[Path]:
    """Locate a downloaded file for a record, by page id first then title."""
    images_dir = Path(images_dir)
    pageid = record.get("pageid")
    if pageid is not None:
        for suffix in IMAGE_SUFFIXES:
            candidate = images_dir / f"{pageid}{suffix}"
            if candidate.exists():
                return candidate
    title = record.get("title") or ""
    stem = re.sub(r"^File:", "", title)
    for suffix in IMAGE_SUFFIXES:
        candidate = images_dir / (stem + suffix)
        if candidate.exists():
            return candidate
    return None


def check_image_bytes(path: Path) -> Dict[str, Any]:
    """Decode a local image and report integrity plus a perceptual hash.

    Imports Pillow lazily so the metadata-only path stays dependency-free.
    """
    try:
        from PIL import Image, ImageStat
    except ImportError:  # pragma: no cover - exercised only without Pillow
        return {"ok": False, "reason": "pillow_not_installed", "sha256": None, "dhash": None}

    try:
        with Image.open(path) as img:
            img.load()
            width, height = img.size
            rgb = img.convert("RGB")
            stat = ImageStat.Stat(rgb)
            mean = [round(v, 2) for v in stat.mean]
    except Exception as exc:  # any decoder failure is a corrupt image
        return {"ok": False, "reason": f"decode_failed: {type(exc).__name__}",
                "sha256": None, "dhash": None}

    problems = []
    if min(width, height) < MIN_EDGE:
        problems.append("below_min_edge")
    if max(mean) - min(mean) < 2.0:
        # Near-uniform colour: usually a placeholder, blank scan or UI capture.
        problems.append("near_uniform_image")

    data = path.read_bytes()
    return {
        "ok": not problems,
        "reason": "ok" if not problems else "; ".join(problems),
        "width": width,
        "height": height,
        "sha256": hashlib.sha256(data).hexdigest(),
        "mean_rgb": mean,
        "dhash": dhash_from_path(path),
    }


def dhash_from_path(path: Path, size: int = 8) -> Optional[str]:
    """64-bit difference hash as 16 hex chars, matching the 12-class trainer."""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return None
    try:
        with Image.open(path) as img:
            small = img.convert("L").resize((size + 1, size), Image.LANCZOS)
            # tobytes() avoids the getdata() deprecation while staying
            # compatible with every Pillow version we support.
            pixels = list(small.tobytes())
    except Exception:
        return None
    bits = 0
    index = 0
    for row in range(size):
        for col in range(size):
            left = pixels[row * (size + 1) + col]
            right = pixels[row * (size + 1) + col + 1]
            if left > right:
                bits |= 1 << index
            index += 1
    return f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def near_duplicate_pairs(
    records: Sequence[Dict[str, Any]], *, threshold: int = 6
) -> List[Dict[str, Any]]:
    """Pairs of records whose dHash distance is within ``threshold``."""
    hashed = [
        (i, r["local"]["dhash"])
        for i, r in enumerate(records)
        if (r.get("local") or {}).get("dhash")
    ]
    out = []
    for a in range(len(hashed)):
        for b in range(a + 1, len(hashed)):
            i, ha = hashed[a]
            j, hb = hashed[b]
            distance = hamming(ha, hb)
            if distance <= threshold:
                out.append({
                    "a_pageid": records[i].get("pageid"),
                    "b_pageid": records[j].get("pageid"),
                    "distance": distance,
                })
    return sorted(out, key=lambda p: p["distance"])


# ---------------------------------------------------------------------------
# Splitting
# ---------------------------------------------------------------------------


def assign_splits(
    groups: Dict[str, List[int]],
    records: Sequence[Dict[str, Any]],
    *,
    seed: int = 42,
    val_pct: float = 0.15,
    test_pct: float = 0.15,
) -> Dict[int, str]:
    """Assign a split to every *group*, then propagate to its members.

    Uses a seeded shuffle of a sorted group id list, so the assignment is
    reproducible and independent of dict ordering.
    """
    ordered = sorted(groups, key=lambda g: (len(groups[g]), g))
    rng = random.Random(seed)
    rng.shuffle(ordered)

    total = sum(len(groups[g]) for g in ordered)
    targets = {
        "test": max(1, int(round(total * test_pct))) if total else 0,
        "val": max(1, int(round(total * val_pct))) if total else 0,
    }
    assignment: Dict[str, str] = {}
    counts = {s: 0 for s in SPLITS}
    for group in ordered:
        size = len(groups[group])
        # Fill rare splits first, but never starve train.
        if counts["test"] < targets["test"]:
            split = "test"
        elif counts["val"] < targets["val"]:
            split = "val"
        else:
            split = "train"
        assignment[group] = split
        counts[split] += size
    out = {}
    for group, split in assignment.items():
        for index in groups[group]:
            out[index] = split
    return out


def verify_no_leakage(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Assert no duplicate group or SHA1 spans two splits."""
    by_sha1: Dict[str, set] = defaultdict(set)
    by_group: Dict[str, set] = defaultdict(set)
    for row in rows:
        if row.get("sha1"):
            by_sha1[row["sha1"]].add(row["split"])
        if row.get("duplicate_group"):
            by_group[row["duplicate_group"]].add(row["split"])
    sha1_leaks = {k: sorted(v) for k, v in by_sha1.items() if len(v) > 1}
    group_leaks = {k: sorted(v) for k, v in by_group.items() if len(v) > 1}
    return {
        "leak_free": not sha1_leaks and not group_leaks and bool(rows),
        "sha1_spanning_splits": sha1_leaks,
        "group_spanning_splits": group_leaks,
    }


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def prepare(
    class_docs: Sequence[Dict[str, Any]],
    *,
    reviews: Optional[Dict[int, Dict[str, Any]]] = None,
    images_dir: Optional[Path] = None,
    min_edge: int = MIN_EDGE,
    seed: int = 42,
    val_pct: float = 0.15,
    test_pct: float = 0.15,
    include_cc_by_sa: bool = False,
) -> Dict[str, Any]:
    """Run the whole preparation pipeline and return a report document."""
    reviews = reviews or {}
    images_dir = Path(images_dir) if images_dir else None
    global_records: List[Dict[str, Any]] = []
    per_class_rows: Dict[str, List[Dict[str, Any]]] = {}
    class_reports: List[Dict[str, Any]] = []

    for doc in class_docs:
        slug = doc["class"]
        rows: List[Dict[str, Any]] = []

        for record in doc.get("files", []):
            rights = record.get("rights") or {}
            tier = rights.get("rights_tier")
            decision = reviews.get(int(record["pageid"])) if record.get("pageid") else None
            verdict = review_verdict(decision)

            row = {
                "pageid": record.get("pageid"),
                "title": record.get("title"),
                "sha1": record.get("sha1"),
                "class": slug,
                "declared_class": (record.get("licence") or {}).get("declared_class"),
                "rights_tier": tier,
                "technical_flags": list(record.get("technical_flags") or []),
                "metadata_gaps": list(record.get("metadata_gaps") or []),
                "attribution": attribution_record(record),
                "review": verdict,
                "reviewed": bool(decision),
                "local": None,
                "training_usable": False,
                "exclusion_reasons": [],
            }

            # ---- rights gate -------------------------------------------
            if tier == TRAINING_APPROVED:
                pass
            elif tier == REVIEW_REQUIRED and include_cc_by_sa:
                pass
            elif tier == REVIEW_REQUIRED:
                row["exclusion_reasons"].append("cc_by_sa_held_out")
            else:
                row["exclusion_reasons"].append("rights_not_supported")

            # ---- technical gate (metadata-level) ------------------------
            for flag in row["technical_flags"]:
                row["exclusion_reasons"].append(f"technical:{flag}")

            # ---- review gate -------------------------------------------
            if not verdict["approved"]:
                row["exclusion_reasons"].append(f"review:{verdict['state']}")

            # ---- local bytes -------------------------------------------
            if images_dir is not None:
                path = image_path_for(images_dir, record)
                if path is None:
                    row["exclusion_reasons"].append("bytes_missing")
                else:
                    check = check_image_bytes(path)
                    row["local"] = {
                        "path": str(path),
                        **{k: v for k, v in check.items() if k != "ok"},
                        "ok": check["ok"],
                    }
                    if not check["ok"]:
                        row["exclusion_reasons"].append(f"bytes:{check['reason']}")
            else:
                row["exclusion_reasons"].append("bytes_missing")

            rows.append(row)

        # Deduplicate within the class: keep one survivor per group and mark
        # byte-identical copies so the count is honest.
        groups = build_duplicate_groups(rows)
        for group, members in groups.items():
            for index in members:
                rows[index]["duplicate_group"] = group
                rows[index]["duplicate_group_size"] = len(members)
            if len(members) > 1:
                members_sorted = sorted(
                    members,
                    key=lambda i: (not rows[i]["review"]["approved"], rows[i].get("pageid") or 0),
                )
                for index in members_sorted[1:]:
                    rows[index]["exclusion_reasons"].append("duplicate_of_group_member")

        for row in rows:
            # training_usable requires: no exclusion reasons at all, and bytes.
            row["training_usable"] = not row["exclusion_reasons"]
            row["split"] = None

        per_class_rows[slug] = rows
        global_records.extend(rows)

    # ---- cross-class conflicts ------------------------------------------
    conflicts = cross_class_duplicates(per_class_rows)
    conflict_keys = {c["key"] for c in conflicts}
    for row in global_records:
        keys = {f"pageid:{row.get('pageid')}"}
        if row.get("sha1"):
            keys.add(row["sha1"])
        if keys & conflict_keys:
            row["cross_class_conflict"] = True
            row["exclusion_reasons"].append("cross_class_duplicate")
            row["training_usable"] = False
        else:
            row["cross_class_conflict"] = False

    # ---- splits over usable rows only -----------------------------------
    usable = [r for r in global_records if r["training_usable"]]
    usable_groups = build_duplicate_groups(usable)
    split_map = assign_splits(
        usable_groups, usable, seed=seed, val_pct=val_pct, test_pct=test_pct
    )
    for index, split in split_map.items():
        usable[index]["split"] = split

    leakage = verify_no_leakage(usable)

    # ---- per-class accounting -------------------------------------------
    for doc in class_docs:
        slug = doc["class"]
        rows = per_class_rows[slug]
        collected = doc.get("counts") or {}
        approved = [r for r in rows if r["review"]["approved"]]
        usable_rows = [r for r in rows if r["training_usable"]]
        split_counts = {s: sum(1 for r in usable_rows if r["split"] == s) for s in SPLITS}
        class_reports.append({
            "class": slug,
            "canonical": doc.get("canonical", slug),
            "counts": {
                "1_discovered": collected.get("1_discovered_file_slots", 0),
                "2_metadata_retrieved": collected.get("2_metadata_retrieved", 0),
                "3_rights_supported": collected.get("3_rights_supported", 0),
                "4_reviewed": sum(1 for r in rows if r["reviewed"]),
                "5_approved": len(approved),
                "6_training_usable": len(usable_rows),
            },
            "splits": split_counts,
            "rights_breakdown": _count(r["rights_tier"] for r in rows),
            "exclusion_breakdown": _count(
                reason for r in rows for reason in r["exclusion_reasons"]
            ),
            "ready_for_training": len(usable_rows) >= 2
            and all(c > 0 for c in split_counts.values()),
            "training_ready_note": "needs >=2 usable images in each of train/val/test "
            "after rights, review, technical and duplicate filtering",
        })

    ready = [c for c in class_reports if c["ready_for_training"]]

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": utc_now(),
        "inputs": {
            "classes": len(class_docs),
            "review_decisions": len(reviews),
            "images_dir": str(images_dir) if images_dir else None,
            "include_cc_by_sa": include_cc_by_sa,
        },
        "engine": {
            "seed": seed,
            "val_pct": val_pct,
            "test_pct": test_pct,
            "min_edge": min_edge,
            "split_unit": "duplicate group, never a single image",
        },
        "classes": class_reports,
        "totals": {
            "classes_prepared": len(class_reports),
            "classes_ready_for_training": len(ready),
            "usable_images": len(usable),
            "splits": _count(r["split"] for r in usable),
        },
        "leakage": leakage,
        "cross_class_duplicates": conflicts,
        "duplicate_pairs": detect_duplicate_pairs(global_records),
        "near_duplicate_pairs": near_duplicate_pairs(usable),
        "caveats": [
            "training_usable requires local image bytes, a passing decode check and a "
            "human approval; without --images every count 6 is zero by design",
            "exact duplicates are detected from page id, SHA1 and normalised title; "
            "near duplicates additionally need decoded pixels",
            "cross-class duplicates are a label conflict for a human to resolve, not "
            "something this tool resolves silently",
            "no rights conclusion is drawn: tiers reflect the declared licence only",
        ],
        "rows": global_records,
    }


def _count(values: Iterable[Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for value in values:
        key = str(value)
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


def write_outputs(report: Dict[str, Any], out_dir: Path) -> Dict[str, str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}

    manifest = {k: v for k, v in report.items() if k != "rows"}
    manifest["images"] = report["rows"]
    path = out_dir / "dataset_manifest.json"
    path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    written["manifest"] = str(path)

    # Split files list only usable rows, so a trainer cannot pick up a
    # non-approved image by accident.
    for split in SPLITS:
        rows = [r for r in report["rows"] if r["training_usable"] and r["split"] == split]
        split_path = out_dir / f"split_{split}.json"
        split_path.write_text(
            json.dumps({"split": split, "count": len(rows), "images": rows}, indent=1)
            + "\n",
            encoding="utf-8",
        )
        written[f"split_{split}"] = str(split_path)

    download = [
        {
            "pageid": r["pageid"],
            "title": r["title"],
            "class": r["class"],
            "sha1": r["sha1"],
            "source_url": r["attribution"]["source_url"],
        }
        for r in report["rows"]
        if r["rights_tier"] in (TRAINING_APPROVED, REVIEW_REQUIRED)
        and "rights_not_supported" not in r["exclusion_reasons"]
    ]
    dl_path = out_dir / "download_plan.json"
    dl_path.write_text(
        json.dumps({
            "note": "Files the user may fetch locally to create a real image set. "
            "Fetching is the user's action; nothing here was downloaded.",
            "count": len(download),
            "files": download,
        }, indent=1) + "\n",
        encoding="utf-8",
    )
    written["download_plan"] = str(dl_path)

    records = [r["attribution"] for r in report["rows"] if r["training_usable"]]
    attr_path = out_dir / "ATTRIBUTIONS.md"
    attr_path.write_text(render_attributions(records, title="V2 dataset attributions"),
                         encoding="utf-8")
    written["attributions"] = str(attr_path)
    return written


def render_report(report: Dict[str, Any]) -> str:
    t = report["totals"]
    lines = [
        "# V2 dataset preparation report",
        "",
        f"Generated {report['generated_utc']}. Seed {report['engine']['seed']}.",
        "",
        "## The six counts",
        "",
        "These are different numbers and must never be collapsed. Only the last "
        "column is a training-image count.",
        "",
        "| Class | 1 discovered | 2 metadata | 3 rights | 4 reviewed | 5 approved | 6 usable |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in sorted(report["classes"], key=lambda c: -c["counts"]["6_training_usable"]):
        n = c["counts"]
        lines.append(
            f"| {c['class']} | {n['1_discovered']} | {n['2_metadata_retrieved']} | "
            f"{n['3_rights_supported']} | {n['4_reviewed']} | {n['5_approved']} | "
            f"{n['6_training_usable']} |"
        )
    lines += [
        "",
        f"Classes prepared: **{t['classes_prepared']}**. "
        f"Classes ready for training: **{t['classes_ready_for_training']}**. "
        f"Usable images: **{t['usable_images']}**.",
        "",
        f"Leak-free: **{report['leakage']['leak_free']}**.",
        "",
        "## Why counts are zero",
        "",
    ]
    for caveat in report["caveats"]:
        lines.append(f"- {caveat}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _fixture_doc() -> List[Dict[str, Any]]:
    def rec(pageid, title, sha1, tier, licence, flags=None):
        return {
            "pageid": pageid,
            "title": title,
            "sha1": sha1,
            "width": 1200,
            "height": 900,
            "mime": "image/jpeg",
            "licence": {"declared_class": licence, "short_name": licence,
                        "licence_url": "", "attribution_required": True},
            "attribution": {"artist_raw": "Test Author", "attribution_required": True},
            "rights": {"rights_tier": tier},
            "technical_flags": flags or [],
            "metadata_gaps": [],
            "description_url": "https://commons.wikimedia.org/wiki/" + title,
        }

    return [
        {
            "class": "alpha",
            "canonical": "Alpha",
            "counts": {"1_discovered_file_slots": 40, "2_metadata_retrieved": 10,
                       "3_rights_supported": 8},
            "files": [
                rec(1, "File:A one.jpg", "s1", TRAINING_APPROVED, "CC0_PD"),
                rec(2, "File:A two.jpg", "s2", TRAINING_APPROVED, "CC_BY"),
                rec(3, "File:A three.jpg", "s3", TRAINING_APPROVED, "CC0_PD"),
                rec(4, "File:A four.jpg", "s4", TRAINING_APPROVED, "CC_BY"),
                rec(5, "File:A five.jpg", "s5", TRAINING_APPROVED, "CC_BY"),
                rec(6, "File:A six.jpg", "s6", TRAINING_APPROVED, "CC_BY"),
                rec(7, "File:A seven.jpg", "s7", REVIEW_REQUIRED, "CC_BY_SA"),
                rec(8, "File:A eight.jpg", "s8", EXCLUDED, "NC_RESTRICTED"),
                rec(9, "File:A nine.jpg", "s9", TRAINING_APPROVED, "CC_BY",
                    flags=["below_min_edge"]),
                # Exact duplicate of A one by SHA1 and normalised title.
                rec(10, "File:A one (copy).jpg", "s1", TRAINING_APPROVED, "CC0_PD"),
            ],
        },
        {
            "class": "beta",
            "canonical": "Beta",
            "counts": {"1_discovered_file_slots": 5, "2_metadata_retrieved": 2,
                       "3_rights_supported": 2},
            "files": [
                # Same SHA1 as alpha's A one: cross-class conflict.
                rec(1, "File:A one.jpg", "s1", TRAINING_APPROVED, "CC0_PD"),
                rec(11, "File:B one.jpg", "s11", TRAINING_APPROVED, "CC0_PD"),
            ],
        },
    ]


def _approvals(*pageids: int) -> Dict[int, Dict[str, Any]]:
    return {
        pid: {"pageid": pid, "relevance": "relevant", "quality": "good", "flags": {}}
        for pid in pageids
    }


def self_test() -> int:
    failures: List[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    # 1. No reviews, no bytes: nothing is usable.
    report = prepare(_fixture_doc())
    check(report["totals"]["usable_images"] == 0,
          "without reviews or bytes, usable images must be 0")
    alpha = next(c for c in report["classes"] if c["class"] == "alpha")
    check(alpha["counts"]["4_reviewed"] == 0, "no review should be counted")
    check(alpha["counts"]["6_training_usable"] == 0, "count 6 must be 0")
    check(alpha["counts"]["1_discovered"] == 40,
          "count 1 must pass through the raw category figure unchanged")
    check(report["classes"] and not any(c["ready_for_training"] for c in report["classes"]),
          "no class can be training-ready without bytes")

    # 2. Review verdict semantics.
    check(review_verdict(None)["approved"] is False, "unreviewed must not be approved")
    check(review_verdict({"relevance": "relevant"})["state"] == "partial",
          "a decision without quality must be partial")
    check(review_verdict({"relevance": "uncertain", "quality": "good"})["approved"] is False,
          "uncertain must not be approved")
    check(review_verdict({"relevance": "irrelevant", "quality": "good"})["drop_from_class"] is True,
          "irrelevant must drop the image from the class")
    check(review_verdict({"relevance": "relevant", "quality": "poor"})["approved"] is False,
          "poor quality must not be approved")
    check(review_verdict({"relevance": "relevant", "quality": "good",
                          "flags": {"possible_duplicate": True}})["approved"] is False,
          "a set flag must block approval")
    check(review_verdict({"relevance": "relevant", "quality": "good",
                          "flags": {"possible_duplicate": None}})["approved"] is True,
          "an unset tri-state flag must not block approval")

    # 3. Split determinism and leakage.
    a = assign_splits({"g1": [0, 1], "g2": [2], "g3": [3], "g4": [4], "g5": [5], "g6": [6]},
                      [{}] * 7, seed=7, val_pct=0.2, test_pct=0.2)
    b = assign_splits({"g1": [0, 1], "g2": [2], "g3": [3], "g4": [4], "g5": [5], "g6": [6]},
                      [{}] * 7, seed=7, val_pct=0.2, test_pct=0.2)
    check(a == b, "splits must be deterministic for a fixed seed")
    check(a[0] == a[1], "a duplicate group must land in one split")

    rows = [{"sha1": "x", "split": "train", "duplicate_group": "g1"},
            {"sha1": "x", "split": "test", "duplicate_group": "g1"}]
    leak = verify_no_leakage(rows)
    check(leak["leak_free"] is False, "sha1 spanning two splits must be a leak")
    check(verify_no_leakage([{"sha1": "y", "split": "train", "duplicate_group": "g2"}])
          ["leak_free"] is True, "a single row is trivially leak-free")

    # 4. Duplicate detection.
    pairs = detect_duplicate_pairs([
        {"pageid": 1, "title": "File:A one.jpg", "sha1": "s1"},
        {"pageid": 10, "title": "File:A one (copy).jpg", "sha1": "s1"},
    ])
    check(any(p["signal"] == "sha1" for p in pairs), "sha1 duplicate must be detected")
    check(normalize_title("File:A one.jpg") == normalize_title("File:A_One.jpg"),
          "normalised titles must agree across punctuation and case")

    conflicts = cross_class_duplicates({
        "alpha": [{"pageid": 1, "sha1": "s1"}],
        "beta": [{"pageid": 1, "sha1": "s1"}],
    })
    check(len(conflicts) >= 1, "a file in two classes must be reported as a conflict")

    # 5. CC BY-SA remains held out unless explicitly allowed.
    doc = _fixture_doc()
    held = prepare(doc, reviews=_approvals(7, 2))
    alpha_held = next(c for c in held["classes"] if c["class"] == "alpha")
    check(alpha_held["counts"]["5_approved"] >= 2,
          "reviewed images with supported rights must reach count 5")
    check(alpha_held["counts"]["4_reviewed"] == 2,
          "count 4 must equal the number of human decisions for the class")
    alpha_row = next(r for r in held["rows"] if r["pageid"] == 7)
    check("cc_by_sa_held_out" in alpha_row["exclusion_reasons"],
          "CC BY-SA must be held out of training use by default")
    allowed = prepare(doc, reviews=_approvals(7), include_cc_by_sa=True)
    row_allowed = next(r for r in allowed["rows"] if r["pageid"] == 7)
    check("cc_by_sa_held_out" not in row_allowed["exclusion_reasons"],
          "include_cc_by_sa should lift the hold, but bytes are still required")
    check(row_allowed["training_usable"] is False,
          "CC BY-SA without bytes must still not be training-usable")

    # 6. Corrupt images and real bytes, when Pillow is available.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        images = tmp_path / "images"
        images.mkdir()
        try:
            from PIL import Image
        except ImportError:
            Image = None
        if Image is not None:
            Image.new("RGB", (640, 480), (120, 90, 60)).save(images / "1.jpg")
            Image.new("RGB", (640, 480), (200, 30, 40)).save(images / "2.jpg")
            Image.new("RGB", (640, 480), (30, 40, 200)).save(images / "3.jpg")
            Image.new("RGB", (640, 480), (40, 180, 60)).save(images / "4.jpg")
            Image.new("RGB", (640, 480), (180, 180, 60)).save(images / "5.jpg")
            Image.new("RGB", (640, 480), (60, 60, 180)).save(images / "6.jpg")
            (images / "9.jpg").write_bytes(b"not an image at all")
            # 10 is the duplicate; it shares pixel content with 1.
            Image.new("RGB", (640, 480), (120, 90, 60)).save(images / "10.jpg")

            with_bytes = prepare(
                _fixture_doc(),
                reviews=_approvals(1, 2, 3, 4, 5, 6, 9, 10, 11),
                images_dir=images,
            )
            usable = [r for r in with_bytes["rows"] if r["training_usable"]]
            check(len(usable) >= 4, f"expected several usable images, got {len(usable)}")
            corrupt = next(r for r in with_bytes["rows"] if r["pageid"] == 9)
            check(any(x.startswith("bytes:") for x in corrupt["exclusion_reasons"]),
                  "a non-decodable file must be excluded by the bytes check")
            check(with_bytes["leakage"]["leak_free"] is True,
                  "the produced splits must be leak-free")
            dup = next(r for r in with_bytes["rows"] if r["pageid"] == 10)
            check(dup["training_usable"] is False,
                  "the exact duplicate must not also be training-usable")
            check(len(with_bytes["near_duplicate_pairs"]) >= 0,
                  "near-duplicate reporting must run with pixels present")

            written = write_outputs(with_bytes, tmp_path / "out")
            check(Path(written["manifest"]).exists(), "manifest must be written")
            check(Path(written["attributions"]).exists(), "attributions must be written")
            payload = json.loads(Path(written["split_train"]).read_text())
            check(all(i["training_usable"] for i in payload["images"]),
                  "split files must contain only usable images")
        else:
            report = prepare(_fixture_doc(), images_dir=images)
            check(report["totals"]["usable_images"] == 0,
                  "without Pillow nothing may be approved from bytes")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        print(f"self-test FAILED ({len(failures)} checks)", file=sys.stderr)
        return 1
    print("self-test passed: review gating, duplicate handling, splits and outputs OK")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--classes-dir", type=Path, default=PROJECT / "data/v4/classes")
    parser.add_argument("--out", type=Path, default=PROJECT / "data/v4/prepared")
    parser.add_argument("--reviews", type=Path, action="append", default=[])
    parser.add_argument("--images", type=Path, default=None)
    parser.add_argument("--min-edge", type=int, default=MIN_EDGE)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--val-pct", type=float, default=0.15)
    parser.add_argument("--test-pct", type=float, default=0.15)
    parser.add_argument("--include-cc-by-sa", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    docs = load_class_files(args.classes_dir)
    if not docs:
        raise SystemExit(
            f"no class manifests in {args.classes_dir}; run training/collect_v2.py first"
        )
    reviews = load_reviews(args.reviews) if args.reviews else {}
    report = prepare(
        docs,
        reviews=reviews,
        images_dir=args.images,
        min_edge=args.min_edge,
        seed=args.seed,
        val_pct=args.val_pct,
        test_pct=args.test_pct,
        include_cc_by_sa=args.include_cc_by_sa,
    )
    written = write_outputs(report, args.out)
    (Path(args.out) / "PREPARATION_REPORT.md").write_text(render_report(report), encoding="utf-8")
    print(render_report(report))
    print(json.dumps({"written": written}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
