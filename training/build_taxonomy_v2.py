#!/usr/bin/env python3
"""Build the Food Recognition V2 class taxonomy from the dataset's real folders.

Why this script exists
---------------------
The V2 taxonomy is derived from data, not hand-written. Every dataset folder
must map to exactly one class, or the build fails. That way a folder can never
silently drop out of training, and a class can never appear in the taxonomy
without images behind it.

Scope, stated plainly
---------------------
The only image dataset reachable from this build environment was
Ishmam97/Bangladeshi-Food-Dataset. The two Indian datasets named in the project
brief (HuggingFace indian-foods-dataset, UEC FOOD-100) were unreachable, so this
taxonomy is **Bengali/Bangladeshi cuisine only**. It is not a 150-class pan-
Indian + international taxonomy and it is not presented as one.

Merges
------
A few dataset labels are stylistic variants of a single dish that a photograph
cannot reliably separate (e.g. four named varieties of chomchom). Those are
merged into one class and the merge is recorded in the taxonomy output. Nothing
is merged merely to tidy the numbers, and no two genuinely different foods share
a class.

Usage:
    python training/build_taxonomy_v2.py --raw /tmp/bfd/Bangladeshi-Food-Dataset-main \
        --out data/v2/taxonomy_v2.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

# dataset folder -> (slug, canonical label, group). Every one of the 45 folders
# in the dataset must appear here; the build asserts that.
FOLDER_MAP: dict[str, tuple[str, str, str]] = {
    # ---- rice & grains
    "Biryani": ("biryani_bengali", "Biryani (Bengali style)", "rice"),
    "Khichuri": ("khichuri", "Khichuri (Bengali khichdi)", "rice"),
    "Morog_polao": ("morog_polao", "Morog Polao (chicken pilaf)", "rice"),
    "Panta Ilish": ("panta_ilish", "Panta Ilish (fermented rice with hilsa)", "rice"),
    "Shemai": ("shemai", "Shemai (vermicelli)", "dessert"),
    # ---- breads
    "Bakorkhani": ("bakarkhani", "Bakarkhani (crisp flatbread)", "bread"),
    "Porota": ("porota", "Porota (paratha)", "bread"),
    "Patishapta": ("patishapta", "Patishapta (stuffed crepe)", "dessert"),
    # ---- curries & mains
    "Beef Kala Bhuna": ("beef_kala_bhuna", "Beef Kala Bhuna", "curry"),
    "Chola_bhuna": ("chola_bhuna", "Chola Bhuna (chickpea curry)", "curry"),
    "Dim Bhuna": ("egg_bhuna", "Dim Bhuna (egg curry)", "curry"),
    "Haleem": ("haleem", "Haleem", "curry"),
    "Hilsha_fish": ("hilsa_curry", "Hilsa fish curry", "curry"),
    "Malaikari": ("malaikari", "Malaikari (coconut milk curry)", "curry"),
    "Nehari": ("nihari", "Nihari", "curry"),
    "Alu_Bhorta": ("aloo_bhorta", "Aloo Bhorta (mashed potato)", "side"),
    "Kacha  Chana": ("kacha_chana", "Kacha Chana (green gram)", "side"),
    "Doi": ("doi", "Doi (sweet yogurt)", "dairy"),
    # ---- snacks & street food
    "Beguni": ("beguni", "Beguni (besan-fried aubergine)", "snack"),
    "Egg_omlete": ("omelette", "Omelette", "snack"),
    "Kabab": ("kebab", "Kebab", "snack"),
    "Phuchka": ("phuchka", "Phuchka (pani puri)", "street_food"),
    # ---- sweets
    "Kasmiri Chomchom": ("chomchom", "Chomchom", "sweet"),
    "S.P.Chomchom": ("chomchom", "Chomchom", "sweet"),
    "Sada Chomchom": ("chomchom", "Chomchom", "sweet"),
    "Balosai": ("sandesh", "Sandesh", "sweet"),
    "Hafsi Sondesh": ("sandesh", "Sandesh", "sweet"),
    "Kacha Golla": ("sandesh", "Sandesh", "sweet"),
    "Rosogolla": ("rasgulla", "Rasgulla", "sweet"),
    "Roshmalai": ("rasmalai", "Rasmalai", "sweet"),
    "Rajvog": ("rajbhog", "Rajbhog", "sweet"),
    "Kalojam": ("kalojam", "Kalojam", "sweet"),
    "Ravogsai": ("ravogsai", "Ravogsai", "sweet"),
    "Jilapi": ("jalebi", "Jalebi (Jilapi)", "sweet"),
    "Golap Jam": ("golap_jam", "Golap Jam (rose syrup sweet)", "sweet"),
    "Lemon Barfi": ("lemon_barfi", "Lemon Barfi", "sweet"),
    "Maoyaa Laddo": ("maoyaa_laddo", "Maoyaa Laddo", "sweet"),
    "Cream Jam": ("cream_jam", "Cream Jam", "sweet"),
    "Faluda": ("falooda", "Falooda", "dessert"),
    "Payesh": ("payesh", "Payesh (rice pudding)", "dessert"),
    "Dudh Puli PItha": ("dudh_puli_pitha", "Dudh Puli Pitha", "dessert"),
    "Nokshi Pitha": ("nokshi_pitha", "Nokshi Pitha", "dessert"),
    "Pakon Pitha": ("pakon_pitha", "Pakon Pitha", "dessert"),
    "Sajer Pitha": ("sajer_pitha", "Sajer Pitha", "dessert"),
    "Shamok Pitha": ("shamok_pitha", "Shamok Pitha", "dessert"),
}

MERGE_NOTES = {
    "chomchom": "Four dataset labels (Chomchom, Sada/S.P./Kasmiri Chomchom) are "
                "stylistic variants of one sweet and are not reliably separable "
                "from a photograph. Merged, not silently dropped.",
    "sandesh": "Balosai, Hafsi Sondesh and Kacha Golla are all fresh chhena "
               "sweets of the sandesh family. Merged.",
}

PROVENANCE = {
    "id": "bfd",
    "repository": "Ishmam97/Bangladeshi-Food-Dataset",
    "licence_readme": "CC BY 4.0",
    "licence_file": "CC0 1.0 Universal",
    "licence_conflict": True,
    "licence_treated_as": "CC BY 4.0",
    "attribution_required": True,
    "provenance_caveat": (
        "README says images were collected from 'homes, restaurants, markets, "
        "and online platforms'. The publisher's licence grant is not a verified "
        "chain of title for every underlying photograph."
    ),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True, help="extracted dataset root")
    ap.add_argument("--out", default="data/v2/taxonomy_v2.json")
    args = ap.parse_args()

    raw = Path(args.raw)
    folders = set()
    for split in ("Train", "Validation"):
        for d in (raw / split).iterdir():
            if d.is_dir():
                folders.add(d.name)

    unknown = sorted(folders - set(FOLDER_MAP))
    missing = sorted(set(FOLDER_MAP) - folders)
    if unknown:
        raise SystemExit(f"dataset folders with no mapping: {unknown}")
    if missing:
        raise SystemExit(f"mapped folders absent from dataset: {missing}")

    # count images per resulting slug
    counts: Counter[str] = Counter()
    folder_counts: dict[str, int] = {}
    for split in ("Train", "Validation"):
        for d in sorted((raw / split).iterdir()):
            if not d.is_dir():
                continue
            n = sum(1 for f in d.iterdir() if f.is_file())
            folder_counts[d.name] = folder_counts.get(d.name, 0) + n
            counts[FOLDER_MAP[d.name][0]] += n

    by_slug: dict[str, dict] = {}
    for folder, (slug, label, group) in FOLDER_MAP.items():
        entry = by_slug.setdefault(slug, {
            "slug": slug, "label": label, "group": group,
            "dataset_labels": [], "raw_images": 0,
        })
        entry["dataset_labels"].append(folder)
        entry["raw_images"] += folder_counts[folder]

    classes = sorted(by_slug.values(), key=lambda e: (-e["raw_images"], e["slug"]))
    for c in classes:
        c["dataset_labels"].sort()
        c["merge_note"] = MERGE_NOTES.get(c["slug"])

    payload = {
        "version": "1.0",
        "created": "2026-11-07",
        "class_count": len(classes),
        "raw_image_count": sum(counts.values()),
        "dataset_label_count": len(FOLDER_MAP),
        "cuisine_scope": "Bengali / Bangladeshi only",
        "target_not_met": {
            "requested_indian": 120, "requested_international": 30,
            "requested_total": 150, "actual_total": len(classes),
            "reason": "The Indian and international datasets were unreachable "
                      "from the build environment; only this dataset could be "
                      "accessed. No classes were invented to reach 150.",
        },
        "provenance": PROVENANCE,
        "classes": classes,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"wrote {out}: {len(classes)} classes from {len(FOLDER_MAP)} labels, "
          f"{sum(counts.values())} raw images")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
