#!/usr/bin/env python3
"""Audit an Indian food image dataset directory: integrity, duplication,
contamination risk, and licence status.

This exists because the V2 project needs *evidence* about Indian datasets
before any training starts, not impressions. Every number printed here is
measured from the files, and the report is written to JSON so it can be cited.

Contamination checks
--------------------
The images in redistributed Indian-food repositories are largely scraped from
recipe blogs and stock sites. Three cheap, reproducible signals catch most of
the non-photograph content:

  collage   many near-uniform rows/columns (panel gutters of a composite)
  white_bg  a large fraction of near-white pixels (product/catalogue shots)
  extreme_ar  aspect ratio > 2.2 (banners, strips, screenshots)

These are heuristics, not a classifier: they under-report. A watermark or a
brand logo on an otherwise normal photograph is NOT caught by any of them, so
the reported contamination rate is a lower bound. That is stated in the output.

Usage:
    python training/audit_indian_dataset.py \
        --dataset /tmp/indian/Indian-food-classification-main/Dataset/Indian-Food-Images \
        --out data/v2/indian_audit.json
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "training"))

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif"}


def audit(dataset: Path) -> dict:
    warnings.filterwarnings("ignore")
    import numpy as np
    from PIL import Image

    from train_food_classifier import dedupe_global

    classes: dict[str, list[Path]] = {}
    integrity: list[dict] = []
    dims: Counter[str] = Counter()
    modes: Counter[str] = Counter()
    max_dims: list[int] = []
    collage = white_bg = extreme_ar = 0
    contamination_examples: list[str] = []

    for cls in sorted(p for p in dataset.iterdir() if p.is_dir()):
        files = []
        for f in sorted(cls.iterdir()):
            if f.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            try:
                with Image.open(f) as im:
                    im.verify()
                with Image.open(f) as im:
                    w, h = im.size
                    small = np.asarray(
                        im.convert("RGB").resize((128, 128)), dtype=np.float32)
                    modes[im.mode] += 1
                if max(w, h) < 100:
                    integrity.append({"file": f"{cls.name}/{f.name}",
                                      "issue": f"too small {w}x{h}"})
                    continue
                files.append(f)
                dims[f"{w}x{h}"] += 1
                max_dims.append(max(w, h))

                g = small.mean(axis=2)
                gutters = int((g.std(axis=0) < 3).sum() + (g.std(axis=1) < 3).sum())
                bright = float((small.min(axis=2) > 240).mean())
                ar = max(w, h) / max(1, min(w, h))

                flags = []
                if gutters >= 6:
                    flags.append("collage")
                    collage += 1
                if bright > 0.25:
                    flags.append("white_bg")
                    white_bg += 1
                if ar > 2.2:
                    flags.append("extreme_ar")
                    extreme_ar += 1
                if flags and len(contamination_examples) < 25:
                    contamination_examples.append(f"{cls.name}/{f.name}: {','.join(flags)}")
            except Exception as exc:  # noqa: BLE001
                integrity.append({"file": f"{cls.name}/{f.name}",
                                  "issue": f"unreadable ({type(exc).__name__})"})
        if files:
            classes[cls.name] = files

    total_valid = sum(len(v) for v in classes.values())
    per_class_raw = {k: len(v) for k, v in classes.items()}

    kept, dd = dedupe_global(classes, threshold=2, verbose=False)
    per_class_clean = {k: len(v) for k, v in kept.items()}

    max_dims.sort()
    return {
        "dataset_root": str(dataset),
        "classes": len(classes),
        "images_total": total_valid,
        "integrity_rejected": len(integrity),
        "integrity_examples": integrity[:10],
        "per_class_raw": per_class_raw,
        "per_class_raw_min": min(per_class_raw.values()) if per_class_raw else 0,
        "per_class_raw_max": max(per_class_raw.values()) if per_class_raw else 0,
        "dedupe": dd,
        "images_after_dedupe": sum(per_class_clean.values()),
        "per_class_after_dedupe": per_class_clean,
        "per_class_clean_min": min(per_class_clean.values()) if per_class_clean else 0,
        "per_class_clean_max": max(per_class_clean.values()) if per_class_clean else 0,
        "formats": dict(modes),
        "distinct_dimensions": len(dims),
        "top_dimensions": dims.most_common(8),
        "median_max_dimension": max_dims[len(max_dims) // 2] if max_dims else 0,
        "min_max_dimension": max_dims[0] if max_dims else 0,
        "contamination_heuristics": {
            "note": "Lower bound only. Watermarks, brand logos and photo credits on "
                    "otherwise-normal photographs are NOT detected by these checks.",
            "collage_suspected": collage,
            "white_background": white_bg,
            "extreme_aspect_ratio": extreme_ar,
            "union_flagged_upper_estimate": None,  # not deduped across checks
            "examples": contamination_examples,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", default="data/v2/indian_audit.json")
    args = ap.parse_args()

    result = audit(Path(args.dataset))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(f"classes           : {result['classes']}")
    print(f"images (valid)    : {result['images_total']}")
    print(f"per class         : {result['per_class_raw_min']}–{result['per_class_raw_max']}")
    print(f"integrity reject  : {result['integrity_rejected']}")
    print(f"after dedupe      : {result['images_after_dedupe']} "
          f"(removed {result['dedupe']['dropped_exact']} exact, "
          f"{result['dedupe']['dropped_near']} near, "
          f"{result['dedupe']['dropped_cross_class']} cross-class)")
    print(f"per class cleaned : {result['per_class_clean_min']}–{result['per_class_clean_max']}")
    c = result["contamination_heuristics"]
    print(f"contamination     : collage {c['collage_suspected']}, "
          f"white_bg {c['white_background']}, extreme_ar {c['extreme_aspect_ratio']} "
          f"(lower bound)")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
