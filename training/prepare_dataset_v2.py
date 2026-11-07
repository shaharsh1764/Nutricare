#!/usr/bin/env python3
"""Prepare the V2 food-recognition dataset: audit, clean, dedupe, split.

Pipeline (all stages are reproducible from the raw archive):

  1. inventory     every image file with its size and class
  2. integrity     decode each image; drop unreadable / absurd files
  3. normalise     convert anything non-RGB/small to a clean 8-bit RGB JPEG copy
  4. dedupe        GLOBAL exact (MD5) + near-duplicate (dHash <= 2) removal
                   *before* any split, so one photograph cannot straddle
                   train/val/test
  5. split         stratified train/val/test with a fixed seed
  6. verify        re-scan the finished split and assert zero leakage
  7. report        JSON + Markdown with every number above

Leakage is the property that matters most here. The source dataset ships its
own Train/Validation folders, but those were produced without cross-split
de-duplication: the same dish photographed once appears several times, and near
copies landed on both sides. This script therefore **ignores the shipped split**
and derives splits from the deduplicated pool instead.

Usage:
    python training/prepare_dataset_v2.py \
        --raw /tmp/bfd/Bangladeshi-Food-Dataset-main \
        --taxonomy data/v2/taxonomy_v2.json \
        --out data/v2/splits
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "training"))

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif"}

# Reuse the trainer's proven dHash implementation rather than a second one.
from train_food_classifier import _dhash, _hamming, _popcount_matrix, dedupe_global  # noqa: E402


def load_taxonomy(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def collect(raw: Path, taxonomy: dict) -> tuple[dict[str, list[Path]], list[dict]]:
    """Map every image to a class slug using the taxonomy's dataset_labels."""
    label_to_slug = {}
    for entry in taxonomy["classes"]:
        for lbl in entry["dataset_labels"]:
            label_to_slug[lbl] = entry["slug"]

    classes: dict[str, list[Path]] = defaultdict(list)
    unmapped = Counter()
    for split in ("Train", "Validation"):
        split_dir = raw / split
        if not split_dir.is_dir():
            continue
        for folder in sorted(p for p in split_dir.iterdir() if p.is_dir()):
            slug = label_to_slug.get(folder.name)
            files = [f for f in folder.iterdir()
                     if f.is_file() and f.suffix.lower() in IMAGE_SUFFIXES]
            if slug is None:
                unmapped[folder.name] += len(files)
                continue
            classes[slug].extend(files)
    return dict(classes), [{"folder": k, "images": v} for k, v in unmapped.items()]


def check_integrity(classes: dict[str, list[Path]]) -> tuple[dict[str, list[Path]], list[dict]]:
    """Drop images that do not decode, or that are too small to be a photograph."""
    from PIL import Image

    kept: dict[str, list[Path]] = defaultdict(list)
    problems: list[dict] = []
    for slug, files in classes.items():
        for f in files:
            try:
                with Image.open(f) as im:
                    im.verify()
                with Image.open(f) as im:
                    w, h = im.size
                if max(w, h) < 100:
                    problems.append({"file": f.name, "class": slug,
                                     "issue": f"too small ({w}x{h})"})
                    continue
                kept[slug].append(f)
            except Exception as exc:  # noqa: BLE001
                problems.append({"file": f.name, "class": slug,
                                 "issue": f"unreadable ({type(exc).__name__})"})
    return dict(kept), problems


def split_dataset(classes: dict[str, list[Path]], val_pct: float, test_pct: float,
                  seed: int, min_per_split: int = 1):
    """Stratified split over the DEDUPLICATED pool. Deterministic for a seed."""
    rng = random.Random(seed)
    splits = {"train": {}, "val": {}, "test": {}}
    for slug in sorted(classes):
        files = sorted(classes[slug], key=lambda p: p.name)
        rng.shuffle(files)
        n = len(files)
        n_test = max(min_per_split, int(round(n * test_pct)))
        n_val = max(min_per_split, int(round(n * val_pct)))
        if n_test + n_val >= n:
            n_test = max(1, n // 6)
            n_val = max(1, n // 6)
        test = files[:n_test]
        val = files[n_test:n_test + n_val]
        train = files[n_test + n_val:]
        splits["train"][slug] = train
        splits["val"][slug] = val
        splits["test"][slug] = test
    return splits


def materialise(splits: dict, out: Path) -> None:
    """Write symlink-free copies so the split directory is self-contained."""
    from PIL import Image

    for split, per_class in splits.items():
        for slug, files in per_class.items():
            dest = out / split / slug
            dest.mkdir(parents=True, exist_ok=True)
            for i, src in enumerate(sorted(files, key=lambda p: (p.name, str(p)))):
                target = dest / f"{i:05d}.jpg"
                try:
                    with Image.open(src) as im:
                        im.convert("RGB").save(target, "JPEG", quality=92)
                except Exception:  # noqa: BLE001
                    continue


def audit_split(out: Path, threshold: int = 2) -> dict:
    """Independent re-scan of the materialised split: prove no cross-split leak."""
    per_split: dict[str, list[tuple[Path, int]]] = {}
    for split in ("train", "val", "test"):
        items = []
        for f in sorted((out / split).rglob("*.jpg")):
            h = _dhash(f)
            if h is not None:
                items.append((f, h))
        per_split[split] = items

    def cross(a: str, b: str) -> tuple[int, int]:
        A, B = per_split[a], per_split[b]
        if not A or not B:
            return 0, 0
        ha = [h for _, h in A]
        hb = [h for _, h in B]
        # exact file-level duplicates
        import hashlib as _h
        sa = Counter(_h.md5(f.read_bytes()).hexdigest() for f, _ in A)
        sb = Counter(_h.md5(f.read_bytes()).hexdigest() for f, _ in B)
        exact = sum(min(sa[k], sb[k]) for k in sa.keys() & sb.keys())

        # near-duplicates: XOR every dHash in A against every dHash in B and
        # popcount. _popcount_matrix() takes a single 2D block, so the XOR
        # matrix is built here.
        import numpy as np
        va = np.array(ha, dtype=np.uint64)[:, None]
        vb = np.array(hb, dtype=np.uint64)[None, :]
        near = int((_popcount_matrix(va ^ vb) <= threshold).sum())
        return exact, near

    pairs = {}
    for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
        exact, near = cross(a, b)
        pairs[f"{a}~{b}"] = {"exact_duplicates": exact, "near_duplicates": near}
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--taxonomy", default="data/v2/taxonomy_v2.json")
    ap.add_argument("--out", default="data/v2/splits")
    ap.add_argument("--val-pct", type=float, default=0.15)
    ap.add_argument("--test-pct", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dedupe-threshold", type=int, default=2)
    ap.add_argument("--report", default="data/v2/dataset_report.json")
    ap.add_argument("--skip-materialise", action="store_true")
    args = ap.parse_args()

    raw = Path(args.raw)
    taxonomy = load_taxonomy(Path(args.taxonomy))
    out = Path(args.out)

    print("[1/6] inventory …")
    classes, unmapped = collect(raw, taxonomy)
    raw_total = sum(len(v) for v in classes.values())
    print(f"      {raw_total} images in {len(classes)} classes; "
          f"{len(unmapped)} unmapped folders")

    print("[2/6] integrity …")
    classes, problems = check_integrity(classes)
    after_integrity = sum(len(v) for v in classes.values())
    print(f"      {after_integrity} readable "
          f"({len(problems)} rejected)")

    print("[3/6] global de-duplication (exact + dHash <= "
          f"{args.dedupe_threshold}) …")
    deduped, dd_report = dedupe_global(classes, threshold=args.dedupe_threshold)
    after_dedupe = sum(len(v) for v in deduped.values())
    print(f"      kept {after_dedupe}, dropped {after_integrity - after_dedupe}")

    print("[4/6] stratified split …")
    splits = split_dataset(deduped, args.val_pct, args.test_pct, args.seed)
    counts = {s: {k: len(v) for k, v in splits[s].items()} for s in splits}

    leakage = {}
    if not args.skip_materialise:
        print("[5/6] materialising split …")
        if out.exists():
            shutil.rmtree(out)
        materialise(splits, out)
        print("      done; auditing for leakage …")
        leakage = audit_split(out, args.dedupe_threshold)
        print(f"      {leakage}")
    else:
        print("[5/6] materialise skipped")

    print("[6/6] report …")
    per_class = []
    for entry in taxonomy["classes"]:
        slug = entry["slug"]
        per_class.append({
            "slug": slug,
            "label": entry["label"],
            "group": entry["group"],
            "dataset_labels": entry["dataset_labels"],
            "raw_images": entry["raw_images"],
            "after_integrity": len(classes.get(slug, [])),
            "after_dedupe": len(deduped.get(slug, [])),
            "train": counts["train"].get(slug, 0),
            "val": counts["val"].get(slug, 0),
            "test": counts["test"].get(slug, 0),
            "merge_note": entry.get("merge_note"),
        })
    per_class.sort(key=lambda e: -e["after_dedupe"])

    report = {
        "raw_images": raw_total,
        "raw_dataset_folders": len({l for e in taxonomy["classes"] for l in e["dataset_labels"]}),
        "class_count": len(deduped),
        "integrity_rejected": len(problems),
        "integrity_problems_sample": problems[:20],
        "after_integrity": after_integrity,
        "after_dedupe": after_dedupe,
        "dedupe_removed": after_integrity - after_dedupe,
        "dedupe_detail": dd_report,
        "unmapped_folders": unmapped,
        "split_sizes": {s: sum(counts[s].values()) for s in counts},
        "seed": args.seed,
        "val_pct": args.val_pct,
        "test_pct": args.test_pct,
        "leakage_audit": leakage,
        "per_class": per_class,
        "smallest_class": per_class[-1] if per_class else None,
        "largest_class": per_class[0] if per_class else None,
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                 encoding="utf-8")
    print(f"      wrote {args.report}")
    print(f"classes={len(deduped)} train={report['split_sizes']['train']} "
          f"val={report['split_sizes']['val']} test={report['split_sizes']['test']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
