# AI Food Scanner — model documentation

Two real, trained checkpoints are included in this repository, both trained
only on **CC0 1.0** images. **This document covers both.** It reports what each
actually achieves, how each was produced, and where each is weak.

| | **Default: 12-class model** | Alternative: 7-class model |
|---|---|---|
| File | `models/food_classifier_cc0.pt` | `models/food_classifier_cc0_7class.pt` |
| Test accuracy | **0.8947** (n=380) | 0.8609 (n=302) |
| Leak-free test accuracy | 0.8947 (0 leakage) | 0.8539 (after removing 35 leaked) |
| Test macro F1 | **0.9047** | 0.8724 |
| Training-data licence | **CC0 1.0 — cleared** | **CC0 1.0 — cleared** |
| Safe to redistribute | **yes** | **yes** |
| Details | §10 below | §10.5 below |

### What is NOT in this repository, and why

An earlier commit on this branch shipped a **20-class** checkpoint
(`models/food_classifier.pt`, 81.43% test accuracy) trained on 6,269 images from
`dhruvk2002/food-classifier`. That dataset declares **no licence at all** — no
`LICENSE` file, an upstream Kaggle listing of "Data files © Original Authors",
and published work on the same images stating they were *"extracted from
google"*. Nothing in that chain can grant redistribution rights.

It has therefore been **removed from the repository and from this branch's git
history**, not merely demoted: leaving it in any commit would mean distributing
an artifact that cannot lawfully be redistributed. Its metrics are not published
any more either, since they describe a model nobody can obtain from here.

The audit that reached this conclusion is `docs/LICENSING_AUDIT.md` §1–§4; the
full evidence chain and what would be needed to clear such a dataset are in §2
and §6 there.

## 1. Why the training pipeline exists

The 20-class model that once occupied these sections is gone (§ above). What
remains is the machinery that produced it and still produces the shipped models:

| Component | Role |
|---|---|
| `training/download_datasets.py` | dataset registry, including licence and status for each candidate |
| `training/fetch_cc0_dataset.py` | fetches the CC0 source, maps folders to NutriCare classes, records exclusions |
| `training/load_imagenet_backbone.py` | converts the MIT-licensed d-li14 MobileNetV3 weights to torchvision layout |
| `training/train_food_classifier.py` | global de-duplication, stratified split, training, evaluation, metrics |

The pipeline is unchanged and reusable. Pointing it at a licence-cleared dataset
is the only requirement, which is exactly what §10 documents.

## 2. Datasets used by the shipped models

Only one dataset is used, and it is CC0:

| Property | Value |
|---|---|
| Source | `github.com/Ishmam97/Bangladeshi-Food-Dataset` |
| Licence | **CC0 1.0 Universal** — commercial use, derivatives and redistribution all permitted |
| Images | 8,444 in the `Train/` split, 44 classes |
| Mapped to NutriCare | 12 classes, 3,247 images offered, 2,573 after de-duplication |
| Caveat | CC0 waives only the rights the dedicator holds; the README says images came partly from "online platforms" |

`docs/COVERAGE.md` §4 lists every dataset investigated and rejected, including
the two that looked permissive but were not.

## 3. Classes the shipped model genuinely supports

The default model predicts **exactly these 12 classes** and nothing else. They
are recorded in the checkpoint's `classes` field and exposed at
`GET /api/vision/classes` as `trained: true`.

| Model class | NutriCare label | Nutrition |
|---|---|---|
| paratha_plain | Paratha (plain) | dataset (IFCT) |
| khichdi | Khichdi | dataset (IFCT) |
| chicken_biryani | Chicken Biryani | dataset (IFCT) |
| chole | Chole / Chana Masala | dataset (IFCT) |
| curd_dahi | Curd / Dahi | dataset (IFCT) |
| rasgulla | Rasgulla / Rosogolla | **approximate**, recipe-derived |
| kheer | Kheer / Payesh | **approximate**, recipe-derived |
| pani_puri | Pani Puri | **none — user enters values** |
| pakora | Pakora / Bhajji | **none — user enters values** |
| chomchom | Chomchom | **none — user enters values** |
| morog_polao | Morog Polao | **none — user enters values** |
| jalebi | Jalebi | **none — user enters values** |

The remaining entries in `data/food_classes.json` are **not** supported by this
model. The UI only offers trained classes for photo recognition; the full
taxonomy remains available for manual logging. Adding a class requires training
on it — it cannot be claimed by adding a row to a JSON file.

## 8. Running inference

An ML runtime is required. The checkpoint is committed, so a fresh clone only
needs the extra dependencies:

```bash
pip install -r requirements-ml.txt     # torch, torchvision, Pillow
python app.py
curl -s localhost:5000/api/vision/status | python -m json.tool
```

Measured on this CPU-only box: cold checkpoint load ≈2.0 s, single 224px
inference ≈16 ms median (42 ms p95). The model is loaded once per process,
lazily, behind a lock. `NUTRICARE_MODEL` overrides the path — use that to select
the 7-class checkpoint, or to point at a checkpoint you obtained yourself.

Without `requirements-ml.txt`, the app still boots and the scanner reports
photo recognition as unavailable — it never guesses.

## 9. Honest limitations

1. **12 classes, not 65, and not the 27 requested Indian dishes.** Everything
   outside §10 is unsupported for photo recognition. `docs/COVERAGE.md` maps
   every requested dish to *supported / blocked* with the reason.
2. **Single-label.** One dominant dish per photo; it cannot separate rice, dal
   and sabzi on one plate. That needs object detection, not classification.
3. **The unlicensed 20-class checkpoint has been removed from the repository and
   from this branch's history.** It was trained on a web-scraped compilation
   with no declared licence at all. Do *not* read that as "fine for
   personal/educational use" — educational use is a possible defence, not a
   permission. If you have a local copy, it is not covered by this project's
   licensing. See `docs/LICENSING_AUDIT.md`.
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
on CC0 1.0 images and is safe to redistribute.

| | **12-class (default)** | 7-class (alternative) |
|---|---|---|
| Checkpoint | `models/food_classifier_cc0.pt` | `models/food_classifier_cc0_7class.pt` |
| Classes | **12** | 7 |
| Input size | 224 px | 160 px |
| Test accuracy | **0.8947** | 0.8609 (leak-free 0.8539) |
| Test macro F1 | **0.9047** | 0.8724 |
| Test support | 380 | 302 |
| Training-data licence | **CC0 1.0** ✅ | **CC0 1.0** ✅ |
| Default | **yes** | no (`NUTRICARE_MODEL=…_7class.pt`) |
| Size | 6.0 MB | 6.0 MB |
| CPU inference | **16 ms median, 42 ms p95** | ~35–60 ms |

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

### 10.5 The 7-class checkpoint (alternative)

`models/food_classifier_cc0_7class.pt` is the first CC0 run, kept for comparison
and because its numbers were measured before the global de-duplication fix:

| Metric | Value |
|---|---|
| Classes | 7 (chicken biryani, curd/dahi, jalebi, khichdi, pakora, pani puri, paratha) |
| Test accuracy as reported | 0.8609 (n=302) |
| Leak-free accuracy | **0.8539** (n=267, after removing 35 train-leaked images) |
| Macro F1 | 0.8724 |
| Input size | 160 px |
| Licence | CC0 1.0 — cleared |

Its 0.8609 is inflated by about +0.007 by near-duplicate frames that straddled
the split; the honest figure is 0.8539. The 12-class model replaced it and fixed
that class of problem, so the 12-class model is the default.

Select it with `NUTRICARE_MODEL=models/food_classifier_cc0_7class.pt`.

## 11. Next concrete step

The blocker is licensing, not modelling. To reach 20+ *shippable* classes,
obtain a dataset whose rights holder grants derivative-model distribution —
either own photography (~60 dishes × ~120 images), a commercial licence, or
written permission from the current 20-class dataset's curator. **Do not
retrain on `soumen7saha/IndFood-Dataset` or Khana:** both derive from
CC BY-NC-ND 4.0 material, which forbids derivative works and commercial use
(`docs/LICENSING_AUDIT.md` §5.1).
