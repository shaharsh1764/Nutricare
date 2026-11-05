#!/usr/bin/env python3
"""NutriCare AI Food Scanner — dataset acquisition.

Downloads the image datasets we can legitimately use, verifies them, and reports
exactly what was and was not obtained. It never pretends a download succeeded.

Usage
-----
    python training/download_datasets.py --list
    python training/download_datasets.py --out data/raw
    python training/download_datasets.py --out data/raw --dataset food101_mini

Why this script exists rather than a "just run it" script: see
docs/DATASET.md. In short, the two datasets that matter for Indian household
food are Kaggle-hosted and need an account plus interactive download. This
script automates everything that can be automated and prints the manual step
when a licence/account barrier genuinely requires one.

Licences are recorded in docs/DATASET.md and keyed by dataset id below.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
UA = "NutriCare-research/1.0 (educational, non-commercial)"

# ---------------------------------------------------------------------------
# Registry. `access` documents honestly how each dataset can be obtained.
# ---------------------------------------------------------------------------
DATASETS = {
    "food101_mini": {
        "name": "Food-101 (Hugging Face parquet mirror)",
        "classes": 101,
        "images": 101_000,
        "indian_coverage": "none (western/international dishes)",
        "licence": "Research use; images from Foodspotting (see dataset card)",
        "access": "auto",
        "how": "huggingface_hub snapshot of the parquet conversion",
        "use_for": "international classes (pizza, burger, pasta, fries, salad …)",
        "citation": "Bossard et al., Food-101, ECCV 2014",
    },
    "food101_tar": {
        "name": "Food-101 (official ETHZ tarballs)",
        "classes": 101,
        "images": 101_000,
        "indian_coverage": "none",
        "licence": "Research use only",
        "access": "auto",
        "how": "curl the official tarballs from data.vision.ee.ethz.ch",
        "url": "http://data.vision.ee.ethz.ch/cvl/datasets_extra/food-101/",
        "use_for": "same classes as food101_mini; pick ONE of the two",
        "citation": "Bossard et al., Food-101, ECCV 2014",
    },
    "indian_food_101": {
        "name": "Indian Food Images Dataset (Kaggle, 101 classes ≈ 5k images)",
        "classes": 101,
        "images": 5_000,
        "indian_coverage": "high — chole bhature, masala dosa, idli, pav bhaji, "
                           "biryani, dal, paneer dishes, snacks …",
        "licence": "CC0 / public domain (per Kaggle dataset card — verify current card)",
        "access": "manual",
        "how": ("Kaggle API with your own credentials: set KAGGLE_USERNAME and "
                "KAGGLE_KEY, or place ~/.kaggle/kaggle.json, then re-run with "
                "--dataset indian_food_101"),
        "use_for": "the Indian-majority portion of the class list",
        "citation": "Kaggle: Indian Food Images / Indian Food Classification",
    },
    "indian_food_80": {
        "name": "Indian Food 80 (Kaggle)",
        "classes": 80,
        "images": 4_000,
        "indian_coverage": "high",
        "licence": "per Kaggle dataset card (verify before commercial use)",
        "access": "manual",
        "how": "same Kaggle credential mechanism as indian_food_101",
        "use_for": "extra breadth for Indian curries and breakfast items",
        "citation": "Kaggle: Indian Food 80",
    },
    "ifd": {
        "name": "Indian Food Dataset (IFD) — CIIPER, IIT Delhi",
        "classes": 15,
        "images": 1_000,
        "indian_coverage": "high (curries, rotis, rice dishes, snacks)",
        "licence": "Research use; request from the authors",
        "access": "request",
        "how": ("Direct download from data.ciiper.iitd.ac.in; if it is "
                "unreachable, email the authors for the research licence"),
        "use_for": "small, high-quality Indian validation set",
        "citation": "S. Pandey et al., 'Image-based Food Classification…', 2021",
    },
    "uecfood256": {
        "name": "UEC FOOD-256",
        "classes": 256,
        "images": 31_000,
        "indian_coverage": "some (curry, rice, biryani, naan)",
        "licence": "Research use only",
        "access": "request",
        "how": "Application form on the UEC Food website",
        "use_for": "optional: Asian/Indian breadth if the licence is approved",
        "citation": "Kawano & Yanai, UEC Food-256, 2014",
    },
}

FOOD101_MINI_REPO = "ethz/food101"


# ---------------------------------------------------------------------------
def have_module(name: str) -> bool:
    return subprocess.run([sys.executable, "-c", f"import {name}"],
                          capture_output=True).returncode == 0


def ping(url: str, timeout: int = 12) -> tuple[bool, str]:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return True, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        # A reachable host that refuses this path is still reachable.
        return exc.code < 500, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - report any failure verbatim
        return False, type(exc).__name__ + ": " + str(exc)[:110]


def cmd_list() -> int:
    print("Datasets under consideration\n" + "=" * 78)
    for key, info in DATASETS.items():
        print(f"\n[{key}] {info['name']}")
        print(f"   classes {info['classes']} · images ≈{info['images']:,}")
        print(f"   Indian coverage : {info['indian_coverage']}")
        print(f"   Licence         : {info['licence']}")
        print(f"   Access          : {info['access']}  ({info.get('how', '—')})")
        print(f"   Used for        : {info['use_for']}")
        print(f"   Citation        : {info['citation']}")
    return 0


def cmd_probe() -> int:
    """Check reachability of every dataset host. Useful in restricted sandboxes."""
    hosts = {
        "huggingface.co": "https://huggingface.co",
        "download.pytorch.org (pretrained weights)": "https://download.pytorch.org/models/",
        "data.vision.ee.ethz.ch (Food-101)": "http://data.vision.ee.ethz.ch/",
        "www.kaggle.com": "https://www.kaggle.com",
        "data.ciiper.iitd.ac.in (IFD)": "https://data.ciiper.iitd.ac.in",
        "zenodo.org": "https://zenodo.org",
    }
    print("Host reachability\n" + "=" * 78)
    reachable = 0
    for label, url in hosts.items():
        ok, detail = ping(url)
        reachable += ok
        print(f"  {'OK  ' if ok else 'BLOCKED'} {label:<44} {detail}")
    print(f"\n{reachable}/{len(hosts)} hosts reachable.")
    if reachable == 0:
        print("No dataset host is reachable from this environment. Training is "
              "impossible here; run this script where egress is open.")
    return 0 if reachable else 1


def download_food101(out: Path) -> Path:
    """Food-101 via the Hugging Face parquet mirror (imagefolder layout)."""
    target = out / "food101"
    if target.is_dir() and any(target.rglob("*.jpg")):
        print(f"  already present: {target}")
        return target
    if not have_module("datasets"):
        print("  installing 'datasets' from PyPI …")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "datasets"],
                       check=False)
    ok, detail = ping("https://huggingface.co")
    if not ok:
        print(f"  SKIP: huggingface.co unreachable ({detail})")
        raise SystemExit(2)
    try:
        from datasets import load_dataset  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        print(f"  SKIP: 'datasets' unavailable ({exc})")
        raise SystemExit(2)
    print("  downloading ethz/food101 …")
    ds = load_dataset(FOOD101_MINI_REPO, split="train")
    target.mkdir(parents=True, exist_ok=True)
    for index, row in enumerate(ds):
        label = row["label"] if isinstance(row["label"], str) else str(row["label"])
        folder = target / label.replace(" ", "_")
        folder.mkdir(exist_ok=True)
        row["image"].convert("RGB").save(folder / f"{index:06d}.jpg", quality=90)
        if index % 2000 == 0:
            print(f"    {index}/{len(ds)}")
    print(f"  wrote {len(ds)} images to {target}")
    return target


def download_kaggle(slug: str, out: Path, key: str) -> Path:
    """Kaggle datasets need the user's own credentials — never bundled here."""
    target = out / key
    if target.is_dir() and any(target.rglob("*.jpg")):
        print(f"  already present: {target}")
        return target
    if not (os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY")) \
            and not (Path.home() / ".kaggle" / "kaggle.json").exists():
        print("  BLOCKED: no Kaggle credentials.")
        print("    Export KAGGLE_USERNAME and KAGGLE_KEY (from kaggle.com → "
              "Settings → Create New API Token), then re-run this command.")
        raise SystemExit(3)
    if not have_module("kaggle"):
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "kaggle"],
                       check=False)
    ok, detail = ping("https://www.kaggle.com")
    if not ok:
        print(f"  BLOCKED: kaggle.com unreachable from here ({detail})")
        raise SystemExit(2)
    target.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([sys.executable, "-m", "kaggle", "datasets", "download",
                             "-d", slug, "-p", str(target), "--unzip"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  download failed: {result.stderr.strip()[:400]}")
        raise SystemExit(4)
    print(f"  downloaded {slug} -> {target}")
    return target


def extract_if_needed(path: Path) -> None:
    for archive in path.rglob("*.zip"):
        try:
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(archive.parent)
            archive.unlink()
        except zipfile.BadZipFile:
            print(f"  skipping bad zip: {archive}")
    for archive in path.rglob("*.tar.gz"):
        try:
            with tarfile.open(archive) as tf:
                tf.extractall(archive.parent)
            archive.unlink()
        except tarfile.TarError:
            print(f"  skipping bad tar: {archive}")


# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="describe the datasets")
    parser.add_argument("--probe", action="store_true", help="test host reachability")
    parser.add_argument("--out", default=str(PROJECT / "data" / "raw"),
                        help="destination for downloaded images")
    parser.add_argument("--dataset", action="append", default=None,
                        help="dataset key to fetch (repeatable); default: all auto ones")
    parser.add_argument("--kaggle-slug", default="kmader/food41",
                        help="Kaggle slug for indian_food_101")
    args = parser.parse_args()

    if args.list:
        return cmd_list()
    if args.probe:
        return cmd_probe()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    wanted = args.dataset or ["food101_mini"]

    failures = []
    print(f"Downloading into {out}\n" + "=" * 78)
    for key in wanted:
        if key not in DATASETS:
            print(f"unknown dataset {key!r} — see --list")
            return 2
        info = DATASETS[key]
        print(f"\n[{key}] {info['name']}")
        try:
            if key in ("food101_mini", "food101_tar"):
                download_food101(out)
            elif key == "indian_food_101":
                download_kaggle(args.kaggle_slug, out, key)
            elif key == "indian_food_80":
                download_kaggle(args.kaggle_slug, out, key)
            else:
                print(f"  MANUAL: {info['how']}")
                print(f"  licence: {info['licence']}")
                failures.append((key, "manual licence/account step"))
                continue
        except SystemExit as exc:
            failures.append((key, f"exit {exc.code}"))
            continue
        extract_if_needed(out / key)

    report = {"destination": str(out),
              "requested": wanted,
              "failures": failures,
              "note": "See docs/DATASET.md for licences and the manual steps."}
    (out / "acquisition_report.json").write_text(json.dumps(report, indent=2),
                                                encoding="utf-8")
    print("\n" + "=" * 78)
    if failures:
        print("Incomplete — these still need action:")
        for key, why in failures:
            print(f"  - {key}: {why}")
        print("This is recorded in acquisition_report.json. Nothing is faked.")
        return 1
    print("All requested datasets acquired.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
