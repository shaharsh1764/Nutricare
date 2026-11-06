# Food image datasets — evaluation and acquisition

This document records which public datasets were considered, what they contain,
their licences, and which were actually obtained. The acquisition pipeline is
`training/download_datasets.py`.

> **Status: two real models ARE trained and shipped, both from a dataset whose
> publisher declares CC0 1.0.** That declaration is documented; the publisher's
> authority over every underlying photograph is not independently verified.
> GitHub is reachable from the build environment even though every dedicated
> dataset host is not. See `docs/MODEL.md` for measured results and
> `docs/COVERAGE.md` for which dishes are supported.
>
> **What changed from the first investigation:** Kaggle, Hugging Face,
> `download.pytorch.org`, Zenodo, archive.org and their mirrors remain blocked,
> and **GitHub release assets** are blocked too (they redirect to
> `release-assets.githubusercontent.com`). What *works* is `codeload.github.com`
> tarballs and the REST API — anything committed **into** a repository.

## 0. Datasets actually used

Only one image dataset is used by the shipped models. Its publisher declares CC0 1.0:

| Dataset | Source | Images | Classes | Licence | Obtained |
|---|---|---|---|---|---|
| Bangladeshi Food Dataset | `github.com/Ishmam97/Bangladeshi-Food-Dataset` | 8,444 in `Train/`; 2,573 used after de-duplication | 44 → **12 mapped** | **CC0 1.0 Universal, declared by the publisher.** The licence text permits commercial use, derivatives and redistribution; the publisher's authority over each underlying image is **not independently verified** | ✅ via `training/fetch_cc0_dataset.py` |
| MobileNetV3 ImageNet weights | `github.com/d-li14/mobilenetv3.pytorch` → `mobilenetv3-small-55df8e1f.pth` | — | 1000 (ImageNet) | **MIT**, © 2019 Duo Li | ✅ `training/load_imagenet_backbone.py`, strict load verified |

### Removed: the 20-class dataset and the checkpoint trained on it

`github.com/dhruvk2002/food-classifier` supplied 6,269 Indian food photographs
across 20 classes, and the first model on this branch was trained on them. That
dataset declares **no licence at all**: no `LICENSE` file, an upstream Kaggle
listing of "Data files © Original Authors", and published work on the same
images stating they were *"extracted from google"*.

Neither the images nor the checkpoint trained on them can be redistributed, so
**both are absent from this repository and from the branch history**. This is a
different situation from the CC0-declared dataset above: there the publisher made
a public-domain dedication, here nobody did. Both carry unresolved chain-of-title
questions, but only one of them carries *any* rights grant at all. The
evidence is recorded in `docs/LICENSING_AUDIT.md` §2 so the decision is
auditable, but no artifact depends on it.

## 0b. Evaluated but not used (and why)

| Dataset | Images | Classes | Reason |
|---|---|---|---|
| `soumen7saha/IndFood-Dataset` | 20,400 | 131 | **Best next candidate.** Covers most of NutriCare's Indian list (dal tadka, rajma, palak paneer, aloo gobi, poha, pongal, bhindi masala, kachori, dabeli…). Not trained on within this session's time budget. |
| `soumen1149/RASOI` | 939 | — | YOLO bounding-box detection format; too small for classification |
| `Sarthak-1408/Indian-Food-Classification` | 23 | — | Sample images + notebook only |
| Food-101 (ETHZ / HF) | 101,000 | 101 | Hosts unreachable |
| Indian Food 101 / 80 (Kaggle) | ~9,000 | 101 / 80 | Kaggle unreachable, requires account token |
| IFD (IIT Delhi) | ~1,000 | 15 | Host DNS does not resolve |
| UEC FOOD-256 | ~31,000 | 256 | Application form; host unreachable |

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

## 4. Environment limitation — corrected

Measured in the build sandbox:

```
BLOCKED  huggingface.co, download.pytorch.org, www.kaggle.com, zenodo.org,
         archive.org, data.vision.ee.ethz.ch, s3.amazonaws.com, gitee.com,
         modelscope.cn, hf-mirror.com, mirrors.* (aliyun/tuna/sjtu)
BLOCKED  raw.githubusercontent.com, objects.githubusercontent.com,
         media.githubusercontent.com, release-assets.githubusercontent.com
WORKS    codeload.github.com   (repository tarballs)
WORKS    api.github.com        (metadata, trees, contents)
WORKS    pypi.org / files.pythonhosted.org
```

The first investigation concluded "no data is obtainable". That was wrong in an
important way: **repository tarballs are a different transport from release
assets and raw content**, and they work. A dataset or checkpoint committed into
a repo is reachable; the same file attached to a *release* is not.

Practical consequence for anyone re-running this: when a dataset or weight file
is only available as a release asset or `raw.githubusercontent.com` link, it
cannot be fetched here. Look for repos that commit the files directly and pull
them with `codeload.github.com/<owner>/<repo>/tar.gz/refs/heads/<branch>`.

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
