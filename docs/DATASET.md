# Food image datasets — evaluation and acquisition

This document records which public datasets were considered, what they contain,
their licences, and which were actually obtained. The acquisition pipeline is
`training/download_datasets.py`.

> **Status: a real model HAS been trained and is shipped.**
> GitHub is reachable from the build environment even though every dedicated
> dataset host is not, and two GitHub repositories carried everything needed:
> 6,269 real Indian food photographs and a genuine ImageNet MobileNetV3
> checkpoint. See `docs/MODEL.md` for the measured results.
>
> **What changed from the first investigation:** Kaggle, Hugging Face,
> `download.pytorch.org`, Zenodo, archive.org and their mirrors remain blocked,
> and **GitHub release assets** are blocked too (they redirect to
> `release-assets.githubusercontent.com`). What *works* is `codeload.github.com`
> tarballs and the REST API — anything committed **into** a repository. That
> distinction is what unblocked the project.

## 0. Datasets actually used

| Dataset | Source | Images | Classes | Licence | Obtained |
|---|---|---|---|---|---|
| Food Classification (20 Indian classes) | `github.com/dhruvk2002/food-classifier` | 6,269 readable (of 6,271) | 20 | **None declared** — no LICENSE file; educational/research use assumed, verify before commercial redistribution | ✅ full tarball, every image inspected with Pillow |
| MobileNetV3 ImageNet weights | `github.com/d-li14/mobilenetv3.pytorch` → `mobilenetv3-small-55df8e1f.pth` | — | 1000 (ImageNet) | Repository's own terms; converted to torchvision layout | ✅ `training/load_imagenet_backbone.py`, strict load verified |

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
