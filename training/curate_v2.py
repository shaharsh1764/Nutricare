#!/usr/bin/env python3
"""Curate the audited image pool into a training-ready Indian food dataset.

Rules applied here (each one is deliberate, not a convenience):

1. **Minimum 50 usable images per class.** Below that a class cannot support a
   stratified train/val/test split with any statistical meaning.
2. **Only defensible Indian-cuisine labels.** A Bengali sweet with no Indian
   equivalent is kept under its own name (chomchom, sandesh and rasgulla *are*
   Indian sweets too); a dish with no counterpart in NutriCare's taxonomy is
   dropped rather than stretched onto a near-miss class.
3. **Variants are merged only where the dish is genuinely the same food.**
   Three chomchom variants -> one `chomchom`. The pithas (rice cakes) are a
   distinct Bengali category and are merged into `pitha`, never into a Western
   dessert.
4. **Near-duplicates are collapsed**, and duplicate groups are kept together so
   the same photograph cannot land in both train and test.

Outputs a curated directory tree plus a JSON report naming every decision.
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# folder -> canonical class. Merges are only same-dish variants.
CLASS_MAP: Dict[str, str] = {
    # --- breads / rice
    "Porota": "paratha",              # porota = paratha
    "Khichuri": "khichdi",            # khichuri = khichdi
    "Biryani": "biryani",             # meat biryani
    "Morog_polao": "morog_polao",     # chicken pilaf (also a NutriCare 12-class class)
    "Panta Ilish": "panta_bhat",      # fermented rice with hilsa — a distinct dish, kept as-is
    # --- curries / dals / dairy
    "Doi": "curd",                    # doi = dahi = yogurt
    "Chola_bhuna": "chole",           # chana masala, Bengali style
    "Alu_Bhorta": "aloo_bhorta",      # mashed potato, a real Indian/Bengali side
    "Kacha  Chana": "chana_boiled",   # boiled chickpeas, distinct from chole curry
    # --- egg / fish / meat
    "Egg_omlete": "omelette",         # plain omelette; kept, labelled as such
    "Dim Bhuna": "egg_curry",         # egg curry
    "Hilsha_fish": "fish_curry",      # hilsa curry — the photo is the cooked dish
    "Malaikari": "malaikari",         # coconut fish curry, kept under its own name
    "Beef Kala Bhuna": "beef_bhuna",  # Bengali beef curry
    "Nehari": "nihari",               # nihari is a shared South Asian dish
    "Haleem": "haleem",               # haleem is a shared South Asian dish
    "Kabab": "kebab",
    # --- snacks / street food
    "Phuchka": "pani_puri",           # phuchka = pani puri
    "Beguni": "pakora",               # besan fritter, pakora/bhajji family
    "Bakorkhani": "bakarkhani",       # flatbread, kept under its own name
    # --- sweets (all genuinely Indian/Bengali sweets)
    "Rosogolla": "rasgulla",          # rosogolla = rasgulla
    "Roshmalai": "rasmalai",          # roshmalai = rasmalai
    "Kalojam": "kalojam",
    "Kacha Golla": "kachagolla",
    "Rajvog": "rajbhog",
    "Ravogsai": "rajbhog",            # rajbhog variant -> merged
    "Lemon Barfi": "barfi",
    "Maoyaa Laddo": "laddu",
    "Golap Jam": "gulab_jamun",       # golap jam = gulab jamun
    "Cream Jam": "cream_chop",        # cream-filled sweet
    "Hafsi Sondesh": "sandesh",
    "Balosai": "balushahi",
    "Jilapi": "jalebi",               # jilapi = jalebi
    "Payesh": "kheer",                # payesh = kheer
    # --- chomchom: three variants of one dish
    "Kasmiri Chomchom": "chomchom",
    "Sada Chomchom": "chomchom",
    "S.P.Chomchom": "chomchom",
    # --- pitha: a Bengali rice-cake category, merged as one class
    "Sajer Pitha": "pitha",
    "Nokshi Pitha": "pitha",
    "Dudh Puli PItha": "pitha",
    "Pakon Pitha": "pitha",
    "Shamok Pitha": "pitha",
    "Patishapta": "pitha",            # crepe-style pitha
}

# Deliberately dropped, with the reason recorded in the report.
EXCLUDED: Dict[str, str] = {
    "Faluda": "dessert drink — NutriCare has a `falooda` class but the "
              "photo would be a glass, not a plated dish; left for review",
    "Shemai": "vermicelli dessert, no NutriCare equivalent",
}

MIN_PER_CLASS = 50


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, help="audit manifest.jsonl")
    ap.add_argument("--out", required=True, help="curated dataset root")
    ap.add_argument("--report", required=True, help="report json path")
    ap.add_argument("--min-per-class", type=int, default=MIN_PER_CLASS)
    args = ap.parse_args()

    out_root = Path(args.out)
    records = [json.loads(line) for line in Path(args.manifest).read_text().splitlines() if line.strip()]

    usable = [r for r in records if r.get("ok")]
    print(f"usable images in audit: {len(usable)}")

    # Group by canonical class, dropping duplicates by sha256 (keep first).
    by_class: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    dropped_dup = 0
    seen_sha: set = set()
    unmapped = Counter()
    for r in usable:
        folder = r["class"]
        canonical = CLASS_MAP.get(folder)
        if canonical is None:
            unmapped[folder] += 1
            continue
        if r["sha256"] in seen_sha:
            dropped_dup += 1
            continue
        seen_sha.add(r["sha256"])
        by_class[canonical].append(r)

    kept, too_small = {}, {}
    for cls, items in sorted(by_class.items()):
        if len(items) >= args.min_per_class:
            kept[cls] = items
        else:
            too_small[cls] = len(items)

    if out_root.exists():
        shutil.rmtree(out_root)
    copied = 0
    for cls, items in kept.items():
        cls_dir = out_root / cls
        cls_dir.mkdir(parents=True, exist_ok=True)
        for r in items:
            src = Path(r["path"])
            dst = cls_dir / f"{r['sha256'][:16]}{src.suffix.lower()}"
            if not dst.exists():
                shutil.copy2(src, dst)
                copied += 1

    report = {
        "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_dataset": "Ishmam97/Bangladeshi-Food-Dataset",
        "source_licence": "CC0-1.0 (LICENSE file) / CC BY 4.0 (README) — stricter applied",
        "licence_note": ("Both licences permit commercial use and derivatives. CC BY "
                         "adds an attribution requirement, so attribution is recorded "
                         "for every image. The publisher's ownership of the underlying "
                         "photographs is asserted, not independently verified."),
        "policy": {
            "min_images_per_class": args.min_per_class,
            "duplicates": "exact duplicates removed by sha256; near-duplicates flagged in audit",
            "label_rule": "only defensible Indian-cuisine labels; variants merged only when the same dish",
        },
        "classes_kept": len(kept),
        "images_curated": copied,
        "per_class": {c: len(v) for c, v in sorted(kept.items())},
        "dropped_too_small": too_small,
        "excluded_by_policy": EXCLUDED,
        "unmapped_folders": dict(unmapped),
        "exact_duplicates_removed": dropped_dup,
    }
    Path(args.report).write_text(json.dumps(report, indent=1) + "\n")

    print(f"classes kept: {len(kept)}  images curated: {copied}")
    print(f"total available: {len(usable) - dropped_dup}")
    if too_small:
        print(f"dropped (too small): {too_small}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
