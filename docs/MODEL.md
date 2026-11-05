# AI Food Scanner — model documentation

Two real, trained checkpoints are included in this repository. **This document
covers both.** It reports what each actually achieves, how each was produced,
and where each is weak.

| | **Default: 12-class CC0 model** | Opt-in: 20-class model |
|---|---|---|
| File | `models/food_classifier_cc0.pt` | `models/food_classifier.pt` |
| Test accuracy | **0.8947** (n=380) | 0.8143 (n=926) |
| Test macro F1 | **0.9047** | 0.8087 |
| Training-data licence | **CC0 1.0 — cleared** | none declared — **not cleared** |
| Safe to redistribute | **yes** | **no** |
| Details | §10 below | §1–§7 below |

Why the default is *not* the higher-capability legacy model: the 20-class
checkpoint was trained on images with no licence anywhere in the chain. Shipping
it as the product would present an unredistributable artifact as NutriCare. The
licence-cleared model is also the more accurate one, which makes the choice easy
rather than a compromise. `docs/COVERAGE.md` tracks which dishes are supported
and which are blocked, with reasons.

## 1. Headline results — 20-class model (opt-in, licensing unresolved)

| Metric | Value |
|---|---|
| Test accuracy | **0.8143** |
| Test macro F1 | **0.8087** |
| Test weighted F1 | **0.8122** |
| Held-out test images | 926 |
| Classes | 20 |
| Architecture | mobilenet_v3_small @ 160px, ImageNet-pretrained |
| Training time | 1141s on 2 vCPU (no GPU) |
| Checkpoint size | 6.0 MB fp32 |

Trained 2026-11-05T10:58:21+00:00. Split: **train 4332 / val 926 / test 926**,
stratified per class. This run removed only byte-identical and same-stem
duplicates — it predates the global perceptual de-duplication now in the
trainer, and a later audit found 1 train→test and 2 train→val near-duplicate
pairs (impact −0.0002). See `docs/LICENSING_AUDIT.md` §4.5.

## 2. Before/after: what changed

An earlier version of this document stated that no model could be trained
because the sandbox could not reach Kaggle, Hugging Face or
`download.pytorch.org`. That finding was correct for those hosts but **the
investigation was not complete**. GitHub is reachable here, and GitHub hosts
both halves of what was missing:

| Need | Found on GitHub | How it was obtained |
|---|---|---|
| Indian food images | `dhruvk2002/food-classifier` — 6,269 real images, 20 Indian-majority classes, committed directly to the repo | `codeload.github.com` tarball (1.6 GB) |
| ImageNet weights | `d-li14/mobilenetv3.pytorch` — `mobilenetv3-small-55df8e1f.pth`, 10.3 MB ImageNet checkpoint | `codeload.github.com` tarball |

`download.pytorch.org`, `huggingface.co` and every dataset host remain blocked,
and GitHub **release assets** redirect to `release-assets.githubusercontent.com`
which is also blocked. What works is `codeload.github.com` tarballs and the REST
API — i.e. anything committed *into a repository*, as opposed to attached to a
release.

## 3. Datasets

### Used for training

| Property | Value |
|---|---|
| Name | Food Classification dataset (20 Indian food classes) |
| Source | https://github.com/dhruvk2002/food-classifier |
| Images | 6,271 files; **6,269 verified readable** (0 corrupt, 0 below 64px) |
| Resolution | min 148×141, median 751×681, max 7360×7360 |
| Classes | 20 (listed in §4) |
| Licence | ⛔ **None declared.** No `LICENSE` file exists; the upstream Kaggle listing says "Data files © Original Authors". **Not cleared for redistribution** — see `docs/LICENSING_AUDIT.md`. |
| Downloaded & inspected | **Yes** — full tarball, every image opened with Pillow |

### Also evaluated, not used

| Dataset | Images | Classes | Why not used |
|---|---|---|---|
| `soumen7saha/IndFood-Dataset` | 20,400 | 131 | ⛔ **Rejected on licensing.** Its images come from Khana, licensed **CC BY-NC-ND 4.0** (no derivatives, no commercial use). A trained model is a derivative. Coverage would have been excellent — the blocker is legal, not technical (`docs/LICENSING_AUDIT.md` §5.1). |
| `Ishmam97/Bangladeshi-Food-Dataset` | 8,442 (Train split) | 44 → 7 mapped | ✅ **Used.** **CC0 1.0.** Trained as `models/food_classifier_cc0.pt` — the licence-clean alternative in §10. |
| `soumen1149/RASOI` | 939 | detection dataset (YOLO labels) | Bounding-box format, too small for classification |
| `Sarthak-1408/Indian-Food-Classification` | 23 | — | Sample images only, plus a notebook |
| Food-101, UECFOOD-256, IFD, Indian Food 101/80 | — | — | Hosts unreachable (Kaggle / ETHZ / IITD / UEC); GitHub release assets blocked |

## 4. Classes this model genuinely supports

The model predicts **exactly these 20 classes** and nothing else. They are
recorded in the checkpoint's `classes` field and exposed at
`GET /api/vision/classes` as `trained: true`.

| Model class | NutriCare label | Nutrition source |
|---|---|---|
| roti | Roti / Chapati / Phulka | dataset (IFCT) |
| naan | Naan (butter naan) | dataset |
| idli | Idli | dataset |
| masala_dosa | Masala Dosa | dataset (plain dosa, approximation disclosed) |
| pav_bhaji | Pav Bhaji | dataset |
| chole_bhature | Chole Bhature | dataset |
| samosa | Samosa | dataset |
| dal_makhani | Dal Makhani | **none — user enters values** |
| kadai_paneer | Kadai Paneer | **none** |
| dhokla | Dhokla | **none** |
| pakora | Pakora / Bhajji | **none** |
| pani_puri | Pani Puri | **none** |
| fried_rice | Fried Rice | **none** |
| pizza | Pizza | **none** |
| burger | Burger | **none** |
| momos | Momos | **none** |
| chai | Chai / Masala Chai | **none** |
| jalebi | Jalebi | **none** |
| kulfi | Kulfi | **none** |
| kaathi_rolls | Kathi Roll / Frankie | **none** |

The remaining 45 entries in `data/food_classes.json` are **not** supported by
this model. The UI only offers trained classes for photo recognition; the full
taxonomy remains available for manual logging. Adding a class requires training
on it — it cannot be claimed by adding a row to a JSON file.

## 5. Per-class performance (test split)

Sorted worst-first, so the weak classes are not hidden.

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| pav_bhaji | 0.733 | 0.635 | 0.680 | 52 |
| pakora | 0.765 | 0.634 | 0.693 | 41 |
| kulfi | 0.778 | 0.636 | 0.700 | 33 |
| roti | 0.712 | 0.689 | 0.700 | 61 |
| pani_puri | 0.765 | 0.684 | 0.722 | 19 |
| dal_makhani | 0.683 | 0.872 | 0.766 | 47 |
| naan | 0.787 | 0.755 | 0.771 | 49 |
| kaathi_rolls | 0.821 | 0.744 | 0.780 | 43 |
| samosa | 0.806 | 0.763 | 0.784 | 38 |
| chole_bhature | 0.778 | 0.803 | 0.790 | 61 |
| pizza | 0.786 | 0.846 | 0.815 | 39 |
| masala_dosa | 0.841 | 0.804 | 0.822 | 46 |
| momos | 0.826 | 0.826 | 0.826 | 46 |
| kadai_paneer | 0.881 | 0.839 | 0.860 | 62 |
| fried_rice | 0.817 | 0.924 | 0.867 | 53 |
| chai | 0.841 | 0.930 | 0.883 | 57 |
| idli | 0.909 | 0.870 | 0.889 | 46 |
| dhokla | 0.872 | 0.954 | 0.911 | 43 |
| jalebi | 0.896 | 0.977 | 0.935 | 44 |
| burger | 0.978 | 0.978 | 0.978 | 46 |

## 6. Confusion matrix (test split)

Rows are actual labels, columns are predictions.

| actual \ predicted | burger | chai | chole_bhature | dal_makhani | dhokla | fried_rice | idli | jalebi | kaathi_rolls | kadai_paneer | kulfi | masala_dosa | momos | naan | pakora | pani_puri | pav_bhaji | pizza | roti | samosa |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| burger | 45 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| chai | 0 | 53 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 0 |
| chole_bhature | 0 | 1 | 49 | 2 | 0 | 1 | 0 | 1 | 2 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 2 | 0 | 1 | 0 |
| dal_makhani | 0 | 0 | 0 | 41 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 2 | 0 |
| dhokla | 0 | 0 | 0 | 0 | 41 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| fried_rice | 0 | 0 | 0 | 0 | 1 | 49 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 1 | 0 | 0 |
| idli | 0 | 0 | 1 | 0 | 0 | 1 | 40 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 |
| jalebi | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 43 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| kaathi_rolls | 1 | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 32 | 0 | 0 | 1 | 1 | 2 | 0 | 0 | 0 | 1 | 3 | 0 |
| kadai_paneer | 0 | 0 | 0 | 1 | 1 | 1 | 0 | 1 | 0 | 52 | 0 | 0 | 0 | 0 | 2 | 0 | 2 | 1 | 1 | 0 |
| kulfi | 0 | 3 | 0 | 1 | 0 | 0 | 2 | 1 | 0 | 0 | 21 | 1 | 0 | 0 | 0 | 1 | 1 | 0 | 2 | 0 |
| masala_dosa | 0 | 1 | 2 | 2 | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 37 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 0 |
| momos | 0 | 1 | 2 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 38 | 0 | 2 | 0 | 0 | 0 | 0 | 0 |
| naan | 0 | 0 | 1 | 2 | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 37 | 0 | 0 | 0 | 2 | 5 | 0 |
| pakora | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 2 | 0 | 26 | 2 | 1 | 0 | 0 | 6 |
| pani_puri | 0 | 2 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 13 | 0 | 0 | 0 | 0 |
| pav_bhaji | 0 | 2 | 1 | 7 | 1 | 1 | 0 | 0 | 0 | 2 | 0 | 3 | 0 | 0 | 0 | 1 | 33 | 1 | 0 | 0 |
| pizza | 0 | 0 | 0 | 1 | 1 | 1 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 33 | 0 | 0 |
| roti | 0 | 0 | 3 | 1 | 0 | 2 | 0 | 1 | 2 | 0 | 0 | 1 | 0 | 4 | 0 | 0 | 2 | 3 | 42 | 0 |
| samosa | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 0 | 1 | 2 | 1 | 0 | 0 | 1 | 0 | 0 | 29 |

### Most confused pairs

| Actual | Predicted as | Count |
|---|---|---|
| pav_bhaji | dal_makhani | 7 |
| pakora | samosa | 6 |
| naan | roti | 5 |
| roti | naan | 4 |
| roti | pizza | 3 |
| roti | chole_bhature | 3 |
| pav_bhaji | masala_dosa | 3 |
| kulfi | chai | 3 |

Interpretation, stated plainly:

* **Weakest classes are the flatbreads and the fried snack family.**
  `roti ↔ naan` (5 and 4 mutual confusions) are the same dough cooked two ways;
  `pakora → samosa` (6) is a genuine visual ambiguity between fried
  batter-coated snacks; `pav_bhaji → dal_makhani` (7) reflects both being a
  reddish, saucy bowl. These are the expected failure modes, not data errors.
* `pani_puri` has only 130 source images (19 in test), the smallest class — its
  0.72 F1 is the least statistically reliable number here.
* `burger` (0.978) and `jalebi` (0.935) are visually distinctive and score
  accordingly, which is a sanity check that the pipeline is learning real
  features rather than dataset artefacts.

## 7. Training configuration

| Setting | Value |
|---|---|
| Backbone | MobileNetV3-Small, ImageNet weights from `d-li14/mobilenetv3.pytorch` |
| Weight conversion | `training/load_imagenet_backbone.py` — positional key mapping + 18 1×1 convs reshaped from `nn.Linear`; **strict load verified** before training |
| Head | final linear replaced: 1024 → 20 |
| Input | 160×160, ImageNet normalisation |
| Augmentation (train only) | RandomResizedCrop(0.7–1.0), horizontal flip, colour jitter 0.25/0.25/0.2, rotation ±12° |
| Schedule | 1 epoch head-only, then full fine-tune; AdamW (wd 1e-4); cosine LR; lr 3e-4 (0.2× after unfreeze) |
| Loss | cross-entropy, label smoothing 0.1 |
| Batch size | 32 |
| Epochs | 14 |
| Model selection | best validation accuracy (epoch 14, val_acc 0.827) |
| Seed | 42 |
| Device | CPU (2 vCPU, 3 GB) |

Reproduce end to end:

```bash
curl -sSL https://codeload.github.com/dhruvk2002/food-classifier/tar.gz/refs/heads/main \
  | tar xz && mv "food-classifier-main/Food Classification" data/raw/indian_food_20
curl -sSL https://codeload.github.com/d-li14/mobilenetv3.pytorch/tar.gz/refs/heads/master \
  | tar xz
python training/load_imagenet_backbone.py \
  --checkpoint mobilenetv3.pytorch-master/pretrained/mobilenetv3-small-55df8e1f.pth \
  --out models/backbone_mobilenet_v3_small.pth
python training/train_food_classifier.py --data data/raw/indian_food_20 \
  --epochs 14 --batch-size 32 --lr 3e-4 --image-size 160 --freeze-epochs 1 \
  --backbone models/backbone_mobilenet_v3_small.pth \
  --backbone-source "d-li14/mobilenetv3.pytorch mobilenetv3-small-55df8e1f.pth" \
  --output models/food_classifier.pt
```

## 8. Running inference

An ML runtime is required. The checkpoint is committed, so a fresh clone only
needs the extra dependencies:

```bash
pip install -r requirements-ml.txt     # torch, torchvision, Pillow
python app.py
curl -s localhost:5000/api/vision/status | python -m json.tool
```

Measured on this CPU-only box: cold checkpoint load ≈0.6 s, single 160px
inference ≈35–60 ms. The model is loaded once per process, lazily, behind a
lock. `NUTRICARE_MODEL` overrides the path.

Without `requirements-ml.txt`, the app still boots and the scanner reports
photo recognition as unavailable — it never guesses.

## 9. Honest limitations

1. **12 classes, not 65, and not the 27 requested Indian dishes.** Everything
   outside §10 is unsupported for photo recognition. `docs/COVERAGE.md` maps
   every requested dish to *supported / blocked* with the reason.
2. **Single-label.** One dominant dish per photo; it cannot separate rice, dal
   and sabzi on one plate. That needs object detection, not classification.
3. **The default model is licence-cleared; the 20-class one is not.** The 20-class
   checkpoint was trained on a web-scraped compilation with no declared licence
   at all. Do *not* read that as "fine for personal/educational use" —
   educational use is a possible defence, not a permission. It is opt-in and
   must not be redistributed. See `docs/LICENSING_AUDIT.md`.
4. **CC0 is a dedication by the publisher, not a chain-of-title guarantee.** The
   source README says images came partly from "online platforms". It is far
   stronger than an unlicensed scrape and it is still not a warranty.
5. **Domain shift.** Source photos are largely studio-style. Real phone photos of
   a home thali under warm indoor light will score lower than 89%. Collect ~50
   real photos per class to measure true field accuracy.
6. **Weakest classes are reported.** `morog_polao` F1 0.727 and
   `chicken_biryani` 0.800 sit next to each other in the confusion matrix; rice
   dishes are the known weak spot. Three classes (chomchom, jalebi, kheer) have
   only 3–4 test images — do not read their 1.000 as real.
7. **5 of the 12 classes have no documented nutrition**, so the scanner asks the
   user for values rather than inventing them. Two rows added with this model
   (kheer, rasgulla) are flagged `approximate` and recipe-derived.
8. **Class imbalance** (21–444 images per class) makes the thinnest classes the
   least reliable.
9. **No portion estimation from pixels.** Weight is always the user's adjustment
   of a dataset default serving.
10. **Not evaluated for safety-critical use.** This is a convenience estimate,
    not dietary or medical advice.

## 10. The installed model: CC0 12-class checkpoint

`models/food_classifier_cc0.pt` **is the default checkpoint**. It is trained only
on CC0 1.0 images and is safe to redistribute. The older 20-class model is more
capable but its images carry no licence, so it is no longer the default — it
remains in the repository, reachable but opt-in.

| | 20-class (opt-in) | **12-class (default)** |
|---|---|---|
| Checkpoint | `models/food_classifier.pt` | `models/food_classifier_cc0.pt` |
| Classes | 20 | **12** |
| Input size | 160 px | 224 px |
| Test accuracy | 0.8143 | **0.8947** |
| Test macro F1 | 0.8087 | **0.9047** |
| Test support | 926 | 380 |
| Training-data licence | none declared ⛔ | **CC0 1.0** ✅ |
| Default | no (`NUTRICARE_MODEL=models/food_classifier.pt`) | **yes** |
| Size | 6.0 MB | 6.0 MB |
| CPU inference | ~35–60 ms | **16 ms median, 42 ms p95** |

### 10.1 Training data and de-duplication

Source: `Ishmam97/Bangladeshi-Food-Dataset` (CC0 1.0), `Train/` split only,
8,444 images across 44 classes, mapped to 12 NutriCare classes.

```
images offered       3,247   (12 mapped classes)
after de-duplication 2,573   dropped 170 exact + 504 near-duplicate
split                train 1,778 · val 380 · test 380
```

De-duplication runs **globally, before the split**: MD5 for exact copies, 64-bit
dHash with Hamming ≤ 2 for re-encoded near-duplicates. It removed **21%** of the
offered images. An earlier bucketed implementation missed 48 pairs; the current
version is an exact all-pairs scan, and §10.3 confirms it now finds none.

### 10.2 Per-class results (test split)

| Class | Precision | Recall | F1 | n |
|---|---|---|---|---|
| morog_polao | 0.857 | 0.632 | **0.727** | 19 |
| chicken_biryani | 0.745 | 0.864 | **0.800** | 44 |
| khichdi | 0.877 | 0.833 | 0.855 | 60 |
| chole | 0.867 | 0.867 | 0.867 | 15 |
| pani_puri | 0.900 | 0.857 | 0.878 | 42 |
| curd_dahi | 1.000 | 0.792 | 0.884 | 24 |
| pakora | 0.889 | 0.970 | 0.927 | 33 |
| paratha_plain | 0.941 | 0.970 | 0.955 | 66 |
| rasgulla | 0.943 | 0.985 | 0.964 | 67 |
| chomchom | 1.000 | 1.000 | 1.000 | **4** |
| jalebi | 1.000 | 1.000 | 1.000 | **3** |
| kheer | 1.000 | 1.000 | 1.000 | **3** |

**Read the last three rows with suspicion.** 4, 3 and 3 test images cannot
support a 1.000. Those classes are kept because they are recognisable, but no
claim of perfect accuracy is made — the sample is simply too small.

Dominant confusion: `morog_polao ↔ chicken_biryani` and `khichdi ↔
chicken_biryani`. All three are rice dishes on a plate and the model separates
them poorly. This is the weakest area, reported rather than removed.

### 10.3 Leakage audit (post-fix)

The same perceptual scan that originally found 153 cross-split pairs now reports:

```
train <-> test : exact md5 collisions = 0, near-duplicate (dHash<=2) = 0
train <-> val  : exact md5 collisions = 0, near-duplicate (dHash<=2) = 0
```

### 10.4 Independent reproduction

Re-derived through the application's own `nutricare.vision.Predictor`, not the
trainer's evaluator:

```
reported  : 0.8947 (380 test images)
re-derived: 0.8945 (339/379) — one image excluded, see below
```

The excluded image is a 9 MP photo that NutriCare's own upload guard rejects
(maximum 8,000 px). That is correct product behaviour, reported rather than
quietly skipped.

## 11. Next concrete step

The blocker is licensing, not modelling. To reach 20+ *shippable* classes,
obtain a dataset whose rights holder grants derivative-model distribution —
either own photography (~60 dishes × ~120 images), a commercial licence, or
written permission from the current 20-class dataset's curator. **Do not
retrain on `soumen7saha/IndFood-Dataset` or Khana:** both derive from
CC BY-NC-ND 4.0 material, which forbids derivative works and commercial use
(`docs/LICENSING_AUDIT.md` §5.1).
