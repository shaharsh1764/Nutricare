#!/usr/bin/env python3
"""Fetch the CC0-licensed food image dataset used for the redistributable model.

Dataset: Ishmam97/Bangladeshi-Food-Dataset  (CC0-1.0)
Why this one: it is the only Indian-subcontinent food image collection found in
this environment whose **image-level** licence permits commercial use AND
derivative works (CC0 1.0). That distinction matters:

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

# dataset folder -> NutriCare class slug. Only true equivalents, no stretching.
CLASS_MAP = {
    "Biryani": "chicken_biryani",   # Bangladeshi biryani is typically meat biryani
    "Khichuri": "khichdi",          # same dish, Bengali spelling
    "Porota": "paratha_plain",      # paratha/porota
    "Jilapi": "jalebi",             # jalebi/jilapi
    "Phuchka": "pani_puri",         # pani puri is called phuchka in Bengal
    "Beguni": "pakora",             # gram-flour fritter, the pakora family
    "Doi": "curd_dahi",             # doi = dahi = yogurt
}
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
    args = parser.parse_args()

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
            target = out / slug / Path(member.name).name
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
        print(f"  NutriCare already has documented nutrition for khichdi/paratha/dal"
              f" etc., so a thin class is still worth reporting — but it may be"
              f" dropped by the trainer's --min-images threshold.")
    print(f"\nprepared: {out}")
    print("Train with:  python training/train_food_classifier.py "
          f"--data {out} --output models/food_classifier_cc0.pt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
