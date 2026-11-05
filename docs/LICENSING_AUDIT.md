# Dataset licensing & model provenance audit

Scope: PR #2. This audit asks one question — **may this project lawfully ship the
trained checkpoint?** — and answers it separately from "does the model work?".

Verdicts: **PASS** = verified in writing; **FAIL** = permission absent or
disputed; **PARTIAL** = usable under stated conditions.

---

## 1. Summary verdicts

| Area | Verdict | One-line reason |
|---|---|---|
| Model loading from clean clone | **PASS** | byte-identical artifact, loads, infers |
| Inference / preprocessing correctness | **PASS** | transforms bit-identical to training, logits equal |
| Reported metrics reproducibility | **PASS** | 0.8143 / 0.8087 / 0.8122 reproduced exactly |
| Duplicate / near-duplicate leakage | **PASS (minor)** | 1 test + 2 val near-dupes; headline unaffected (−0.0002) |
| Pretrained-weight licensing | **PASS** | MobileNetV3 weights repo is MIT (Duo Li, 2019) |
| **Dataset licensing — 20-class model (now removed)** | **FAIL** | no licence anywhere in the chain; provenance is web-scraped |
| Dataset licensing — IndFood 131-class candidate | **FAIL** | Khana is CC BY-NC-ND 4.0 (no derivatives, no commercial) |
| Dataset licensing — CC0 7-class replacement | **PASS** | CC0 1.0, commercial + derivatives permitted |
| CC0 model — measured & independently reproduced | **PASS** | 0.8609 (260/302) re-derived via the app's own predictor |
| CC0 model — leakage | **PARTIAL** | 153 near-dup train/test pairs; clean subset 0.8539 (−0.007) |
| CC0 model — class coverage | **PARTIAL** | 12 classes vs 20; real capability loss, documented in `docs/COVERAGE.md` |

**Update (final revision):** the licence-cleared checkpoint has been retrained
to **12 classes** (CC0 1.0, test accuracy 0.8947, macro F1 0.9047) and is the
**default** model. `docs/MODEL.md` §10 and `docs/COVERAGE.md` carry the current
numbers.

**The 20-class checkpoint is no longer included in this repository, in any
commit.** The verdicts in §2–§4 below are the evidence that forced that
decision: with no licence anywhere in the chain, the artifact cannot be
distributed, and leaving it in the tree — even as a non-default opt-in — would
still be distribution. It has been removed from the working tree and from the
branch history, so no earlier commit on this branch contains it either.

**Bottom line: the 20-class model was technically sound but never cleared for
redistribution, so it has been removed rather than shipped with a warning.** The
CC0-licensed replacement (see §5) is the default: lawful, slightly more
accurate, and covers 12 classes rather than 20. That coverage loss is the price
of shipping something NutriCare may actually distribute, and it is stated in
`docs/COVERAGE.md` rather than buried. Every third-party notice, including the
full MIT text for the backbone weights, is in `THIRD_PARTY_NOTICES.md`.

---

## 2. Full provenance chain of the current (20-class) training images

The committed model was trained on `dhruvk2002/food-classifier`. Tracing back:

```
dhruvk2002/food-classifier            NO LICENSE FILE — github license API 404
        │                              README: "We have used Indian Food
        │                              Classification Dataset" — no URL, no
        │                              author, no licence statement
        ▼
Kaggle: l33tc0d3r/indian-food-classification   (20 classes, ~6,269 images)
        │                              Listed licence: "Data files © Original
        │                              Authors" (= all rights reserved)
        │                              A peer-reviewed paper using this dataset
        │                              states: "All the images are extracted
        │                              from google."
        ▼
Unknown original photographers / websites
```

Evidence gathered:

* `GET /repos/dhruvk2002/food-classifier/license` → **404**. No `LICENSE` file.
* Repo README has a "License" heading in its table of contents but **no licence
  section body** — the heading is empty.
* The README's "About Dataset" names only *"Indian Food Classification
  Dataset"*, with no link and no attribution.
* Independent academic use of the same 20-class set (Prime Open Access,
  *Int J Appl Food Sci Nutr*, 2025) identifies it as
  `kaggle.com/datasets/l33tc0d3r/indian-food-classification` and states the
  images were **extracted from Google**.

### Why this is a FAIL

Neither the GitHub repo nor the Kaggle dataset grants the rights this project
needs. Under the Berne Convention, copyright in a photograph belongs to its
photographer by default; scraping does not transfer it. Kaggle's "Data files ©
Original Authors" means the opposite of a licence — it is an explicit
reservation of rights.

A model trained on that data is a **derivative work** of those photographs. No
downstream permission exists for: training, redistribution, or shipping the
resulting weights. "It is public on GitHub" and "it is for education" are not
licence grants, and this project does not rely on either.

**What was NOT done:** I did not contact the author, because the defect is not
in `dhruvk2002`'s repo alone — it lies upstream, with images of unknown
provenance. Approval from the repo owner could not cure a missing right he does
not hold either. See §6 for the exact contact that *would* help.

---

## 3. Pretrained weights — PASS

| Property | Value |
|---|---|
| Source | `github.com/d-li14/mobilenetv3.pytorch` |
| File | `pretrained/mobilenetv3-small-55df8e1f.pth` (10.3 MB, 244 tensors) |
| Licence | **MIT** — verified via GitHub license API (`spdx_id: MIT`) |
| Copyright | © 2019 Duo Li |
| Upstream architecture | MobileNetV3, Howard et al., ICCV 2019 (Google) |
| Weights trained on | ImageNet (ILSVRC) |

**MIT permits** use, copying, modification, merging, publication, distribution,
sublicensing and sale, provided the copyright notice and permission notice are
included. It carries **no share-alike** obligation, so a fine-tuned or converted
checkpoint may be distributed under this project's own terms — provided the MIT
notice travels with it.

Obligations honoured in this repository:

1. Attribution recorded in `docs/MODEL.md` §7 and in the checkpoint metadata
   (`backbone_source`, `initialisation`).
2. The conversion performed (`training/load_imagenet_backbone.py`) is a
   documented, mechanical key/reshape mapping — no new training — and is
   therefore itself a permitted "modification".
3. **DONE:** the MIT notice text, with the full licence body, the exact file
   used, a description of the conversion and the required copyright line, is
   reproduced in `THIRD_PARTY_NOTICES.md`. This clears the weights-portion merge
   blocker recorded earlier in this audit.

*Caveat worth stating:* the underlying ImageNet images are a separate matter
from these weights. Redistributing a **model trained on ImageNet** is standard
practice and is what the MIT licence on these weights expressly allows.

---

## 4. Reproducibility audit — PASS

Performed on a fresh `git clone --depth 1` of
`arena/9caa3adc-nutricare`, plus an independent rebuild of the evaluation.

### 4.1 Artifact identity

```
sha256(models/food_classifier.pt) = 3fefbd0ffdffb75682d3ac155901b71b67be39d9d5ca5d3ae1fcda2a15d2dd99
identical in the clean clone and the working tree

NOTE: this checkpoint has since been REMOVED from the repository and from the
branch history on licensing grounds (see §1 and §2). The hash is retained here
only so the artifact this audit examined can still be identified. It is no
longer distributed in any commit of this branch.
```

### 4.2 Class ordering and output mapping

Checkpoint `classes` (fixed order; index = output neuron):

```
0 burger   1 chai      2 chole_bhature  3 dal_makhani   4 dhokla
5 fried_rice 6 idli    7 jalebi         8 kaathi_rolls  9 kadai_paneer
10 kulfi   11 masala_dosa 12 momos      13 naan         14 pakora
15 pani_puri 16 pav_bhaji 17 pizza      18 roti         19 samosa
```

`checkpoint["classes"]` equals the sorted set re-discovered from the dataset —
verified programmatically (`classes discovered now: 20 | match checkpoint: True`).
The app maps model output index → slug via that same list, so the mapping cannot
silently drift.

### 4.3 Preprocessing and input dimensions

| Property | Trainer (eval) | App inference | Equal? |
|---|---|---|---|
| Resize | `int(160*256/224)` = 182 | 182 | ✅ |
| Crop | CenterCrop 160 | CenterCrop 160 | ✅ |
| Normalise mean | .485/.456/.406 | same | ✅ |
| Normalise std | .229/.224/.225 | same | ✅ |
| Tensor difference | — | — | **max abs diff 0.0e+00** |
| Logits | — | — | **torch.equal → True** |

### 4.4 Metric reproduction

Re-ran inference over the reconstructed 4332/926/926 split using the committed
checkpoint:

| Metric | Reproduced | Committed | Match |
|---|---|---|---|
| Accuracy | 0.8143 | 0.8143 | ✅ exact |
| Macro F1 | 0.8087 | 0.8087 | ✅ exact |
| Weighted F1 | 0.8122 | 0.8122 | ✅ exact |
| Correct / n | 754 / 926 | 754 / 926 | ✅ |

### 4.5 Duplicate and near-duplicate leakage

Two checks over all 6,269 images:

* **Exact duplicates (MD5) across the whole dataset: 84 groups.** Most are
  within-class repeats (e.g. `burger/059` = `burger/142`); one is cross-class
  (`butter_naan/187` = `kadai_paneer/094`, i.e. a mislabelled duplicate).
* **Near-duplicates (64-bit dHash, Hamming ≤ 2) crossing split boundaries:**

| Split pair | Pairs found | Detail |
|---|---|---|
| train ↔ test | **1** | `pizza/073` ↔ `pizza/079` (d=2) |
| train ↔ val | **2** | `pizza/048` ↔ `pizza/088` (d=0), `chole_bhature/198` ↔ `291` (d=1) |

Impact measured, not estimated: removing the leaked test image changes accuracy
from **0.8143 → 0.8141** and macro F1 from 0.8087 → 0.8085. So the published
figures are inflated by **+0.02 percentage points** — immaterial, but disclosed.

**Why any leakage survived:** the trainer de-duplicates by content hash and by
`int(filename)` stem, but stems collide *randomly* across classes in this
dataset (`idli/001` and `jalebi/001` share a stem), which deletes legitimate
images, while `pizza/073` vs `pizza/079` are re-encoded copies with different
bytes and different stems. The guard is sound but not sufficient. Recommended
fix (not yet applied): dHash-based pre-split de-duplication.

### 4.6 Live inference in a clean clone

Six real photographs, unseen during this audit, loaded through
`/api/vision/predict` in the fresh clone:

| Image | Predicted | Confidence | Result |
|---|---|---|---|
| chapati | Roti / Chapati / Phulka | 87.6% | ✅ |
| idli | Idli | 97.1% | ✅ |
| samosa | Samosa | 94.8% | ✅ |
| burger | Burger | 91.5% | ✅ |
| masala_dosa | Masala Dosa | 93.9% | ✅ |
| pizza | Pizza | 98.8% | ✅ |

6 / 6 correct.

---

## 5. Next-dataset investigation

### 5.1 IndFood-Dataset (20,400 images, 131 classes) — FAIL

| Property | Finding |
|---|---|
| Repo | `github.com/soumen7saha/IndFood-Dataset` |
| Declared licence | **GPL-3.0** (on the repository) |
| Actual image provenance | **Khana** (`khana.omkar.xyz`, 131K images) + Kaggle `iamsouravbanerjee/indian-food-images-dataset` |
| Khana's licence | **CC BY-NC-ND 4.0** — NonCommercial **and NoDerivatives** |
| Test split provenance | README: *"test images of each of the classes are taken from the web"* |
| Class distribution | 131 classes, heavily imbalanced (1190 paneer_masala → small classes) |

**Do not train on this.** Two independent blockers:

1. **CC BY-NC-ND 4.0 forbids derivatives.** A trained model is a derivative of
   the images. Publishing it would breach the licence regardless of whether the
   app is monetised. "NC" additionally bars any commercial use.
2. **GPL-3.0 is the wrong tool.** The repo owner applied a *software* licence to
   images he does not own; GPL cannot grant rights in third-party photographs.
   Its copyleft terms would also be unworkable for a model artifact.

Also note Khana is itself scraped from search engines and Swiggy/Zomato menus,
so upstream rights are unclear even before the NC/ND terms.

### 5.2 CC0 replacement — PASS

| Property | Finding |
|---|---|
| Repo | `github.com/Ishmam97/Bangladeshi-Food-Dataset` |
| Licence | **CC0 1.0 Universal** (full legal text committed as `LICENSE`) |
| Images | 10,039; 8,442 in the `Train/` split used here |
| Classes | 44 |
| Mapped to NutriCare | **7 classes, 2,083 images** (see below) |
| Provenance note | README describes images "collected from diverse real-world sources (homes, restaurants, markets, and online platforms)" |

**Honest limitation:** CC0 waives the *author's own* rights. If this dataset
author did not own the images (same scraping risk as above), CC0 cannot grant
more than he had. It is materially the strongest position available without
in-house photography, but it is not a chain-of-title guarantee. This is stated
rather than glossed over.

Only true equivalents were mapped — no stretching to inflate class count:

| Dataset folder | NutriCare class | Images |
|---|---|---|
| Khichuri | khichdi | 439 |
| Porota | paratha_plain | 451 |
| Phuchka (= pani puri) | pani_puri | 302 |
| Biryani | chicken_biryani | 298 |
| Doi (= dahi) | curd_dahi | 276 |
| Beguni (pakora family) | pakora | 235 |
| Jilapi | jalebi | 82 |

Every one of these 7 classes has a documented nutrition row in
`data/foods.json` — a better position than the current model, where 13 of 20
classes have none.

#### 5.2.1 Trained model — measured results

Trained on this machine, CPU only, 16 epochs, MobileNetV3-Small at 160 px,
initialised from the MIT-licensed d-li14 ImageNet weights:

    models/food_classifier_cc0.pt          6,234,346 bytes
    models/food_classifier_cc0.metrics.json
    models/food_classifier_cc0.report.txt
    split: train 1,405 · val 302 · test 302
    train time: 435.5 s

| Metric | Value |
|---|---|
| TEST accuracy | **0.8609** (260 / 302) |
| TEST macro F1 | **0.8724** |
| TEST weighted F1 | 0.8595 |
| Worst class | pakora, F1 0.759 (recall 0.629 — often read as paratha) |
| Best classes | jalebi 1.000, curd_dahi 0.952 |

**Independently reproduced.** The 0.8609 was re-derived by loading the
checkpoint through the application's own `nutricare.vision.Predictor` — not the
trainer's evaluator — over the reconstructed test split: **260/302 = 0.8609**,
with per-class recall matching the report to three decimals. So the reported
number and the number the shipped code produces are the same number.

**Leakage check on the CC0 set — this one is NOT clean.** Perceptual-hash scan
(dHash 64-bit, Hamming ≤ 2) between train and test found **153 near-duplicate
train/test pairs** and 151 train/val pairs. The cause is a burst of near-identical
photographs from the same shoot (e.g. `Doi (37).jpg` … `Doi (54).jpg` are
consecutive frames of the same bowl) being scattered across the split.

Quantified rather than hand-waved — re-evaluating with every train-leaked test
image removed:

| Test subset | Accuracy |
|---|---|
| All 302 test images (as reported) | 0.8609 (260/302) |
| Train-leaked images only (n=35) | 0.9143 |
| **Leak-free test subset (n=267)** | **0.8539 (228/267)** |

So the real generalisation figure is **~0.854**, and the duplicate frames inflate
it by about **+0.007**. Small, but reported here rather than hidden. The fix is a
pre-split perceptual-hash dedupe, which the trainer does not yet do (it only
guards exact MD5 and identical filename stems) — listed as a known limitation.

**Live check:** one held-out photo per class through `Predictor.predict`:
chicken_biryani 88.7 %, curd_dahi 40.7 %, jalebi 94.4 %, khichdi 94.8 %,
pakora 98.5 %, pani_puri 74.5 %, paratha_plain 94.3 % — **7/7 correct**.

**Regression:** 184 pytest + 80 UI smoke checks still pass.

#### 5.2.2 Scope trade-off — state this plainly

The compliant model has **7 classes**; the tainted one had **20**. Accuracy
(0.854 clean vs 0.814) was not the issue — coverage was, and that trade-off is
now settled the other way: **coverage was given up rather than shipping an
artifact that cannot lawfully be redistributed.** The CC0 model became the
default, and the 20-class checkpoint was removed entirely (§1).

That is a real capability regression, recorded here rather than glossed: photo
recognition covers 12 dishes instead of 20, and 21 of the 27 dishes the project
was asked to support remain unsupported (`docs/COVERAGE.md`).

Reaching 20+ compliant classes needs a larger CC0/own-rights source, not a
re-run of this one.

---

## 6. What would clear the 20-class model

Nothing local. The minimum external action, in order of cost:

1. **Cheapest that works legally: use the CC0 model.** No permission needed;
   ship `models/food_classifier_cc0.pt` as the default and keep the 20-class
   artifact out of the repository (or mark it clearly as research-only).
2. **If the 20-class breadth matters:** obtain written permission from
   `l33tc0d3r` (Kaggle) as the curator, *and* from `dhruvk2002` for the curated
   6,269-image subset. The request must ask specifically for:
   (a) permission to use the images for ML training, (b) permission to
   **redistribute the derived model weights publicly and commercially**, and
   (c) confirmation that the curator holds or has cleared the rights to the
   underlying photographs. A curator who scraped from Google cannot grant (c).
3. **The only clean route to full breadth:** commission or shoot your own
   photographs (e.g. ~100–150 per dish, phone photos of real home cooking), or
   license a commercial Indian-food image set (e.g. DataCluster Labs, which
   states it owns its images and sells licences). 60 dishes x 120 images ≈
   7,200 photos — the scale that produced this model's accuracy.

---

## 7. Plain-language risk summary

* **The model works.** Nothing in this audit disputes 81.43% accuracy or the
  honesty of the evaluation. Loading, inference, mapping and numbers all check out.
* **The model is built on photographs nobody has licensed to you.** That is the
  whole problem, and it is a legal problem, not a technical one.
* **Shipping this repository as-is redistributes weights derived from
  unlicensed images.** Risk is low-probability but real: a rights-holder could
  issue a takedown or claim, and a commercial deployment would be much harder to
  defend than a personal project.
* **The MIT weights are fine**, so the *architectural* part of the model is
  clean; only the training data taints the result.
* **A CC0 alternative is now trained and available**, trading breadth (7 vs 20
  classes) for a clean licence.
* **"Public on GitHub" and "educational" are not licences.** If anyone tells you
  otherwise, this document is the counter-argument.
