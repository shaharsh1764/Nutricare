#!/usr/bin/env python3
"""Fetch the CC0-declared food image dataset used for the shipped models.

Dataset: Ishmam97/Bangladeshi-Food-Dataset  (publisher declares CC0-1.0)
Why this one: it is the only Indian-subcontinent food image collection found in
this environment carrying an **image-level** public-domain dedication that
permits commercial use AND derivative works (CC0 1.0).

  IMPORTANT: the CC0 is the publisher's declaration. Whether the publisher held
  the rights to every underlying photograph has NOT been independently verified
  (the README says images were collected partly from "online platforms"). This
  is a documented rights grant, not a proven chain of title. See
  docs/MODEL.md §10.6.

The distinction below still matters:

  * CC BY-NC-ND 4.0 (Khana) forbids both commercial use and derivatives, so a
    distributed fine-tuned model would breach it.
  * CC BY 4.0 / CC BY-SA 4.0 would permit derivatives with attribution and
    (for SA) share-alike obligations on the model.
  * A repository with NO licence grants no redistribution right at all — being
    public on GitHub does not make contents reusable.

Only classes with a genuine NutriCare equivalent are kept; the mapping lives in
CLASS_MAP below and is recorded in the model metadata.

Usage:
    python training/fetch_cc0_dataset.py --out data/raw/cc0_food
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

REPO = "Ishmam97/Bangladeshi-Food-Dataset"
BRANCH = "main"
URL = f"https://codeload.github.com/{REPO}/tar.gz/refs/heads/{BRANCH}"
LICENCE = "CC0-1.0"
UA = "NutriCare-research/1.0"

# dataset folder -> NutriCare class slug. Only defensible equivalences: every
# entry below is either the same dish under its Bengali name, or a dish that is
# materially the same food. Nothing is merged just to inflate class count, and
# nothing is stretched (see EXCLUDED for what was deliberately left out).
CLASS_MAP = {
    # ---- staples / rice / breads
    "Khichuri": "khichdi",            # khichuri = khichdi
    "Porota": "paratha_plain",        # porota = paratha
    "Luchi": "luchi",                 # deep-fried maida puri — see NOTE_LUCHI
    "Biryani": "chicken_biryani",     # Bangladeshi biryani is a meat biryani
    "Morog_polao": "morog_polao",     # chicken pilaf, a distinct Bengali dish
    # ---- curries / legumes / dairy
    "Chola_bhuna": "chole",           # chana masala, Bengali style
    "Doi": "curd_dahi",               # doi = dahi = yogurt
    # ---- snacks / street food
    "Phuchka": "pani_puri",           # pani puri is phuchka in Bengal
    "Beguni": "pakora",               # besan fritter, pakora/bhajji family
    "Jilapi": "jalebi",               # jilapi = jalebi
    # ---- sweets (all are NutriCare classes in their own right)
    "Payesh": "kheer",                # payesh = kheer (rice pudding)
    "Rosogolla": "rasgulla",          # rosogolla = rasgulla
}

NOTE_LUCHI = ("Luchi is a Bengali deep-fried maida bread; NutriCare already has "
              "'Puri (fried)' documented, which is the closest documented item.")

# Present in the source dataset but NOT mapped, with the reason. Recorded so the
# exclusions are auditable rather than invisible.
EXCLUDED = {
    "Beef Kala Bhuna": "no NutriCare class (no beef dish in the taxonomy)",
    "Hilsha_fish": "no fish class; raw-fish row would badly understate a curry",
    "Malaikari": "coconut fish curry — no equivalent documented entry",
    "Panta Ilish": "fermented-rice + hilsa combination, no equivalent",
    "Haleem": "no equivalent documented entry",
    "Nehari": "no equivalent documented entry",
    "Kabab": "no equivalent documented entry",
    "Dim Bhuna": "egg curry; only plain omelette/boiled egg are documented",
    "Egg_omlete": "generic omelette, not an Indian-specific class — left out",
    "Kacha  Chana": "boiled chickpeas, distinct from chole curry",
    "Alu_Bhorta": "mashed potato, not a NutriCare class",
    "Kacha Golla": "sweet made from fresh chhena — different texture from rasgulla",
    "Kalojam": "kalo jam — sweet without a documented equivalent",
    "Rajvog": "sweet without a documented equivalent",
    "Ravogsai": "sweet without a documented equivalent",
    "Bakorkhani": "sweet without a documented equivalent",
    "Faluda": "dessert drink, no equivalent",
    "Shemai": "vermicelli dessert, no equivalent",
    "Patishapta": "crepe dessert, no equivalent",
    "Shamok Pitha": "pitha (rice cake), no equivalent",
    "Sajer Pitha": "pitha, no equivalent",
    "Nokshi Pitha": "pitha, no equivalent",
    "Pakon Pitha": "pitha, no equivalent",
    "Dudh Puli PItha": "pitha, no equivalent",
    "Maoyaa Laddo": "sweet, no documented equivalent",
    "Lemon Barfi": "sweet, no documented equivalent",
    "Kasmiri Chomchom": "chomchom variant — merged only with --chomchom",
    "Sada Chomchom": "chomchom variant — merged only with --chomchom",
    "S.P.Chomchom": "chomchom variant — merged only with --chomchom",
    "Cream Jam": "sweet, no documented equivalent",
    "Hafsi Sondesh": "sondesh, no documented equivalent",
    "Golap Jam": "sweet, no documented equivalent",
    "Balosai": "sweet, no documented equivalent",
    "Roshmalai": "rasmalai — no documented equivalent",
}
CHOMCHOM_FOLDERS = {"Kasmiri Chomchom": "chomchom",
                    "Sada Chomchom": "chomchom",
                    "S.P.Chomchom": "chomchom"}

MIN_PER_CLASS = 20


def download(out: Path) -> Path:
    archive = out.parent / "cc0_food.tar.gz"
    out.parent.mkdir(parents=True, exist_ok=True)
    if archive.is_file() and tarfile.is_tarfile(archive):
        print(f"  reusing {archive} ({archive.stat().st_size/1e6:.0f} MB)")
        return archive
    print(f"  downloading {URL}")
    request = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=1800) as response, \
            archive.open("wb") as handle:
        shutil.copyfileobj(response, handle, length=1 << 20)
    print(f"  got {archive.stat().st_size/1e6:.0f} MB")
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="data/raw/cc0_food")
    parser.add_argument("--archive", default=None,
                        help="use an existing tarball instead of downloading")
    parser.add_argument("--chomchom", action="store_true",
                        help="merge the three chomchom variants into one class")
    args = parser.parse_args()

    if args.chomchom:
        CLASS_MAP.update(CHOMCHOM_FOLDERS)

    out = Path(args.out)
    if out.is_dir() and any(out.rglob("*.jpg")):
        print(f"already prepared: {out}")
        return 0
    out.mkdir(parents=True, exist_ok=True)

    archive = Path(args.archive) if args.archive else download(out)
    if not tarfile.is_tarfile(archive):
        print(f"not a valid tar archive: {archive}")
        return 2

    kept, skipped = {}, {}
    with tarfile.open(archive) as tar:
        for member in tar:
            if not member.isfile() or not member.name.lower().endswith(
                    (".jpg", ".jpeg", ".png")):
                continue
            parts = member.name.split("/")
            if len(parts) < 3 or parts[1] != "Train":
                continue               # only the Train/ split is used
            folder = parts[2]
            slug = CLASS_MAP.get(folder)
            if not slug:
                skipped[folder] = skipped.get(folder, 0) + 1
                continue
            # Prefix with the source folder: filenames repeat across the
            # dataset's classes (e.g. "Train/Doi/000002.jpg" and
            # "Train/Phuchka/000002.jpg"), and the trainer de-duplicates on
            # filename stem, so an unprefixed name would silently discard
            # valid images.
            safe_folder = folder.replace(" ", "_")
            target = out / slug / f"{safe_folder}__{Path(member.name).name}"
            target.parent.mkdir(parents=True, exist_ok=True)
            handle = tar.extractfile(member)
            if handle:
                target.write_bytes(handle.read())
                kept[slug] = kept.get(slug, 0) + 1

    print(f"\n{'class (NutriCare slug)':<26}{'dataset folder':<14}{'images':>8}")
    inv = {v: k for k, v in CLASS_MAP.items()}
    thin = []
    for slug in sorted(kept):
        folder = inv.get(slug, "?")
        image_count = kept[slug]
        note = ""
        if image_count < MIN_PER_CLASS:
            thin.append(slug)
            note = "  (below --min-images, will be dropped)"
        print(f"{slug:<26}{folder:<14}{image_count:>8}{note}")
    print(f"\ntotal kept: {sum(kept.values())} images in {len(kept)} classes")
    print(f"licence: {LICENCE} (https://github.com/{REPO})")
    if thin:
        print(f"WARNING: thin classes: {', '.join(thin)}")
        print("  A thin class is still worth reporting, but it may be dropped "
              "by the trainer's --min-images threshold.")
    print(f"\nprepared: {out}")
    print("Train with:  python training/train_food_classifier.py "
          f"--data {out} --output models/food_classifier_cc0.pt")
    print("De-duplication runs automatically inside the trainer, globally and "
          "before the split.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
