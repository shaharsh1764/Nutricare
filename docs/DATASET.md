# Food image datasets — evaluation and acquisition

This document records which public datasets were considered, what they contain,
their licences, and exactly what could and could not be obtained in this
environment. The acquisition pipeline is `training/download_datasets.py`.

> **Status: no dataset could be downloaded in the environment where this feature
> was built.** Every dataset host was unreachable (see
> [Environment limitation](#environment-limitation)). The code path that fetches,
> verifies and reports them is complete and re-runnable; the images themselves
> are the missing input. Nothing in this repository pretends otherwise.

## 1. Datasets evaluated

| Dataset | Classes | Images | Indian household food? | Licence | Access |
|---|---|---|---|---|---|
| **Indian Food Images / Indian Food Classification** (Kaggle) | 101 | ≈5,000 | **Yes — high.** Chole bhature, masala dosa, idli, pav bhaji, biryani, dal, paneer dishes, samosa, jalebi… | CC0 / public domain per dataset card (re-verify the live card) | Kaggle account + API token |
| **Indian Food 80** (Kaggle) | 80 | ≈4,000 | **Yes — high** | Per dataset card (verify before commercial use) | Kaggle account + API token |
| **Indian Food Dataset (IFD)** — CIIPER, IIT Delhi | 15 | ≈1,000 | **Yes — high**: curries, rotis, rice, snacks | Research use; request from authors | Direct download / author request |
| **Food-101** (ETHZ Zürich) | 101 | 101,000 | No (western/international dishes) | Research use only | Auto download |
| **UEC FOOD-256** (Univ. of Electro-Communications) | 256 | ≈31,000 | Some (curry, rice, biryani, naan) | Research use only | Application form |

### Why these and not "the biggest one"

Accuracy on Food-101 alone would be useless for this audience. An Indian home
cook photographs dal, roti, poha and sambar — classes Food-101 does not contain
at all. The selection therefore prioritises **Indian coverage first**, and uses
Food-101 only to teach the international classes that Indians actually eat
(pizza, burger, pasta, fries, salad, pancakes).

### Overlap between datasets

* `indian_food_101` and `indian_food_80` share some class names but not images.
  Both may be used; the alias map in `train_food_classifier.py` merges them.
* Food-101 and the Indian sets share **no** classes, so there is no label-space
  conflict — only label *mapping* into NutriCare's 59-class taxonomy.
* Duplicate protection: `discover()` + `split_dataset()` de-duplicate by
  `(filename_stem, file_size)` before splitting, which catches the same photo
  shipped twice — a common cause of inflated test accuracy.

## 2. Label mapping

Datasets use their own folder names. `training/train_food_classifier.py` maps
them onto the canonical taxonomy in `data/food_classes.json` through
`EXTRA_ALIASES`, case- and punctuation-insensitively. Folders that map to no
class are **reported, not silently dropped**:

```
unmapped folders: 12 (see metrics json; add aliases to EXTRA_ALIASES)
```

Classes with fewer than `--min-images` (default 20) usable images are dropped
from training and listed in the dataset report.

## 3. Acquisition

```bash
# What is available and under which licence
python training/download_datasets.py --list

# Can this machine reach the hosts at all?
python training/download_datasets.py --probe

# Fetch the auto-downloadable datasets
python training/download_datasets.py --out data/raw

# Kaggle datasets need YOUR token (never bundled in this repo)
export KAGGLE_USERNAME=... KAGGLE_KEY=...      # or ~/.kaggle/kaggle.json
python training/download_datasets.py --dataset indian_food_101 --out data/raw
```

Expected layout after acquisition (standard imagefolder):

```
data/raw/
  food101/            pizza/ burger/ ...          (101 folders)
  indian_food_101/    masala_dosa/ idli/ ...      (folder names vary by release)
```

Both are passed to the trainer with a repeated `--data` flag if they live in
separate roots.

## 4. Environment limitation

Measured inside the build sandbox with `--probe`, every host was unreachable:

```
BLOCKED huggingface.co                      TLS connection closed
BLOCKED download.pytorch.org                 TLS connection closed
BLOCKED data.vision.ee.ethz.ch               remote closed connection
BLOCKED www.kaggle.com                       TLS connection closed
BLOCKED data.ciiper.iitd.ac.in               DNS: name not known
BLOCKED zenodo.org                           TLS connection closed
0/6 hosts reachable
```

`*.pypi.org` and `files.pythonhosted.org` are the only reachable hosts (they
serve Python packages, not images or ImageNet weights). `huggingface-hub`,
`kaggle`, `timm` and `torchvision` all install fine — but each fetches its
actual images/weights at runtime from the hosts above.

**Consequence:** in that sandbox, no dataset could be downloaded and no
pretrained weights could be fetched, so transfer learning — the only sound
approach for this class count — could not be performed. Training was therefore
not attempted rather than attempted badly, and **no accuracy figure is claimed
anywhere in this repository**.

Run `--probe` on your own machine or CI runner before training; it takes ten
seconds and tells you immediately whether the pipeline can proceed.

## 5. Licence notes and obligations

* **Food-101** — images collected via Foodspotting; released for research. Do
  not redistribute the images. Ship the *model weights*, not the dataset.
* **Indian Food (Kaggle, CC0)** — permissive, but re-read the dataset card at the
  time you download; Kaggle cards change.
* **IFD / UEC FOOD-256** — research-only. Using the resulting model in a
  commercial product requires checking the licence with the authors.
* This repository commits **no images**. `.gitignore` excludes `data/raw/` and
  common image extensions, with explicit exceptions for app assets.

If you train and later distribute a checkpoint, keep `models/*.metrics.json`
alongside it so anyone can see what it actually achieves and on which split.

## 6. Citations

* Bossard, Guillaumin, Van Gool. *Food-101 — Mining Discriminative Components
  with Random Forests.* ECCV 2014.
* Pandey, S. et al. *Image-based Food Classification and Volume Estimation.*
  CIIPER, IIT Delhi, 2021 (IFD).
* Kawano, Y., Yanai, K. *Automatic Expansion of a Food Image Dataset Leveraging
  Existing Categories with Domain Adaptation.* ECCV Workshops 2014 (UEC Food).
* Kaggle datasets: see each dataset card on kaggle.com.
