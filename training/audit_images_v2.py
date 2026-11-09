#!/usr/bin/env python3
"""Audit real image bytes for the V2 Indian/Bengali food dataset.

Why this exists
---------------
The earlier tools could only *plan* acquisition. This one runs over bytes that
actually exist on disk: it decodes every file, records dimensions, hashes for
exact duplicates, a perceptual hash for near duplicates, and writes a manifest
that names the licence for every single image.

Nothing here guesses. A file that does not decode is counted as corrupt and its
class loses an image. A file whose licence cannot be stated is not trained on.

Usage:
    python training/audit_images_v2.py --src /tmp/bd_raw/... --out data/v4/dataset
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MIN_EDGE = 300  # matches prepare_v2_dataset.MIN_EDGE


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def inspect_one(args: Tuple[str, str]) -> Dict[str, Any]:
    """Decode a single image and return everything we can prove about it."""
    path_s, class_name = args
    path = Path(path_s)
    out: Dict[str, Any] = {
        "path": path_s,
        "class": class_name,
        "filename": path.name,
        "ok": False,
        "reason": None,
        "width": None,
        "height": None,
        "sha256": None,
        "dhash": None,
        "mode": None,
        "bytes": None,
    }
    try:
        data = path.read_bytes()
        out["bytes"] = len(data)
    except Exception as exc:  # noqa: BLE001
        out["reason"] = f"read_failed:{type(exc).__name__}"
        return out

    if not data:
        out["reason"] = "empty_file"
        return out
    out["sha256"] = hashlib.sha256(data).hexdigest()

    try:
        from PIL import Image
    except ImportError:
        out["reason"] = "pillow_missing"
        return out

    try:
        with Image.open(path) as img:
            img.load()                      # force full decode
            width, height = img.size
            mode = img.mode
            # Perceptual hash: 8x8 difference hash on greyscale.
            small = img.convert("L").resize((9, 8), Image.LANCZOS)
            pixels = list(small.tobytes())
    except Exception as exc:  # noqa: BLE001 - any decoder failure is corrupt
        out["reason"] = f"decode_failed:{type(exc).__name__}"
        return out

    out["width"] = width
    out["height"] = height
    out["mode"] = mode

    bits = 0
    index = 0
    for row in range(8):
        for col in range(8):
            left = pixels[row * 9 + col]
            right = pixels[row * 9 + col + 1]
            if left > right:
                bits |= 1 << index
            index += 1
    out["dhash"] = f"{bits:016x}"

    problems = []
    if min(width, height) < MIN_EDGE:
        problems.append(f"below_min_edge:{min(width, height)}")
    out["ok"] = not problems
    out["reason"] = "ok" if not problems else ";".join(problems)
    return out


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def find_near_duplicates(records: List[Dict[str, Any]], threshold: int = 5
                         ) -> List[Dict[str, Any]]:
    """Pairs whose dHash distance is within ``threshold``.

    Bucketed by the top 16 bits of the hash so this stays linear-ish instead of
    comparing all ~10k images pairwise.
    """
    hashed = [(r["sha256"], r["dhash"], r["class"], r["path"])
              for r in records if r.get("dhash")]
    buckets: Dict[str, List[Tuple[str, str, str, str]]] = defaultdict(list)
    for item in hashed:
        buckets[item[1][:4]].append(item)

    pairs = []
    seen = set()
    for bucket in buckets.values():
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                a, b = bucket[i], bucket[j]
                if a[0] == b[0]:
                    continue  # exact dup already reported separately
                key = tuple(sorted((a[0], b[0])))
                if key in seen:
                    continue
                if hamming(a[1], b[1]) <= threshold:
                    seen.add(key)
                    pairs.append({"a": a[3], "b": b[3],
                                  "a_class": a[2], "b_class": b[2],
                                  "cross_class": a[2] != b[2]})
    return pairs


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Audit real image bytes.")
    ap.add_argument("--src", required=True, help="root containing class folders")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--licence", default="CC0-1.0 / CC-BY-4.0 (repo declares both)")
    ap.add_argument("--licence-url", default="https://github.com/Ishmam97/Bangladeshi-Food-Dataset")
    ap.add_argument("--dataset-name", default="Ishmam97/Bangladeshi-Food-Dataset")
    args = ap.parse_args(argv)

    src = Path(args.src)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    jobs: List[Tuple[str, str]] = []
    for class_dir in sorted(p for p in src.rglob("*") if p.is_dir()):
        images = [p for p in sorted(class_dir.iterdir())
                  if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]
        if images:
            for p in images:
                jobs.append((str(p), class_dir.name))

    print(f"found {len(jobs)} image files across "
          f"{len({c for _, c in jobs})} class folders", flush=True)

    records: List[Dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for i, rec in enumerate(pool.map(inspect_one, jobs, chunksize=64), 1):
            records.append(rec)
            if i % 1000 == 0:
                print(f"  decoded {i}/{len(jobs)}", flush=True)

    for rec in records:
        rec["source_dataset"] = args.dataset_name
        rec["licence"] = args.licence
        rec["licence_url"] = args.licence_url

    corrupt = [r for r in records if r["reason"] and r["reason"].startswith(("decode_failed", "read_failed", "empty_file"))]
    below_edge = [r for r in records if r["reason"] and r["reason"].startswith("below_min_edge")]
    good = [r for r in records if r["ok"]]

    # exact duplicates
    by_sha: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in good:
        by_sha[r["sha256"]].append(r)
    exact_groups = {sha: [x["path"] for x in items]
                    for sha, items in by_sha.items() if len(items) > 1}
    exact_extra = sum(len(v) - 1 for v in exact_groups.values())

    near = find_near_duplicates(good)

    per_class_total = Counter(r["class"] for r in records)
    per_class_good = Counter(r["class"] for r in good)

    summary = {
        "generated_utc": utc_now(),
        "source_dataset": args.dataset_name,
        "source_path": str(src),
        "licence": args.licence,
        "licence_url": args.licence_url,
        "licence_note": ("The repository ships a CC0 1.0 LICENSE file but its README "
                         "states CC BY 4.0. Both permit commercial use and derivatives; "
                         "CC BY additionally requires attribution. NutriCare applies the "
                         "stricter (CC BY 4.0) and records attribution for every image. "
                         "Publisher provenance of the underlying photographs is asserted, "
                         "not independently verified."),
        "counts": {
            "image_files_found": len(records),
            "decoded_ok": len(good),
            "corrupt": len(corrupt),
            "below_min_edge": len(below_edge),
            "exact_duplicate_extra_copies": exact_extra,
            "near_duplicate_pairs": len(near),
            "unique_by_content": len(good) - exact_extra,
            "classes_total": len(per_class_total),
            "classes_with_50_or_more": sum(1 for c in per_class_good.values() if c >= 50),
        },
        "per_class": {
            c: {"found": per_class_total[c], "usable": per_class_good[c]}
            for c in sorted(per_class_total)
        },
        "corrupt_files": [{"path": r["path"], "reason": r["reason"]} for r in corrupt][:200],
        "exact_duplicate_groups": list(exact_groups.values())[:200],
        "near_duplicate_pairs": near[:500],
        "cross_class_near_duplicates": sum(1 for p in near if p["cross_class"]),
    }

    (out_dir / "audit.json").write_text(json.dumps(summary, indent=1) + "\n")
    (out_dir / "manifest.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n")

    print(json.dumps(summary["counts"], indent=1))
    print(f"\nwritten: {out_dir/'audit.json'}")
    print(f"written: {out_dir/'manifest.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
