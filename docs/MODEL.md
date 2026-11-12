# AI Food Scanner — model card and runtime policy

## Current scanner policy

NutriCare's scan endpoint uses one fixed policy:

1. Load and run `models/v2/food_classifier_indian_80_224.pt`, the **80-class
   Indian-food model**, for every normal photo-recognition request.
2. Return only that model's ranked predictions and its raw softmax confidence
   metadata.
3. Run `models/food_classifier_cc0.pt`, the **12-class CC0-declared model**,
   only after a genuine technical failure of the primary model.

The exact technical fallback conditions are:

- the 80-class checkpoint is missing;
- the 80-class checkpoint cannot be read;
- the 80-class model cannot initialise; or
- the 80-class model raises an inference exception.

The fallback is **not** invoked for a low-confidence prediction. NutriCare does
not run both models for a normal scan, compare their scores, combine their
rankings, use agreement/cross-support, or select a model per session.

An invalid or undecodable upload is an image error, not a model failure, so it
does not cause fallback. If both checkpoints fail technically, the API returns
its explicit `503` recognition-unavailable response and does not invent a food
name.

Every prediction is **unconfirmed**. The response's confidence is the selected
model's raw softmax output, not a calibrated probability that the food is
correct. `LOW_CONFIDENCE_THRESHOLD` remains an existing uncertainty signal for
clients, but it has no documented calibration or rejection evaluation and does
not change the model policy. User confirmation belongs to the follow-up scanner
workflow work; this runtime change does not automatically add meals.

## Shipped artifacts

| Role | Artifact | Classes | Measured held-out result | Runtime use |
|---|---|---:|---|---|
| Primary | `models/v2/food_classifier_indian_80_224.pt` | 80 | accuracy 0.5672, macro-F1 0.5559, n=647 | Every normal scan |
| Technical fallback | `models/food_classifier_cc0.pt` | 12 | accuracy 0.8947, macro-F1 0.9047, n=380 | Only after primary technical failure |
| Comparison artifact | `models/food_classifier_cc0_7class.pt` | 7 | reported accuracy 0.8609; leakage-cleaned 0.8539, n=267 | Never selected by a scan |

The metrics above are held-out results on each model's own source dataset. They
do **not** establish real-world phone-photo accuracy, medical suitability, or
confidence calibration. The 80-class model's training/test gap is large
(0.9656 train accuracy versus 0.5672 test accuracy); its output must not be
presented as a confirmed identification.

## 80-class primary: source, performance, and rights

The 80-class checkpoint is MobileNetV3 Small at 224px, warm-started from the
12-class CC0 checkpoint with a new classification head. Its sidecar is
`models/v2/food_classifier_indian_80_224.metrics.json`.

The checkpoint was trained from the 3,997-image snapshot in
[`SoumyaXD/Indian-Food-Classifier`](https://github.com/SoumyaXD/Indian-Food-Classifier).
Forensic Git-blob comparison established that those images are byte-identical to
a 3,997-image subset of the 4,000 committed images in
[`gnpaone/Indian-food-classification`](https://github.com/gnpaone/Indian-food-classification).
The gnpaone README links the upstream image corpus to Kaggle's
`iamsouravbanerjee/indian-food-images-dataset`.

This establishes an accessible technical lineage, **not** a rights grant:

- SoumyaXD supplies no repository licence or image provenance statement.
- gnpaone has a GPL-3.0 repository licence, which does not prove permission to
  relicense third-party photographs.
- The upstream Kaggle-image terms and chain of title were not independently
  verified.
- Public Git access is not permission to train on or redistribute photographs
  or derived weights.

Therefore the primary checkpoint remains **UNRESOLVED / internal experimental
use only / do not redistribute**. Do not call the model or dataset
legally cleared. The model's stronger runtime priority is a product policy and
is not a legal clearance decision.

The output order is the checkpoint's 80 stored class names, not the broader
NutriCare taxonomy order. The sidecar documents 3,997 images, 80 classes,
50 images per class except `cham_cham` (47), and a duplicate-group-aware
70/15/15 split (2,705 / 645 / 647).

## 12-class technical fallback and 7-class comparison checkpoint

The 12-class fallback and 7-class comparison checkpoint derive from
`Ishmam97/Bangladeshi-Food-Dataset`, whose publisher declares CC0 1.0. That is
materially different from an undocumented web scrape, but it is still not a
chain-of-title guarantee: the publisher's authority over every underlying image
was not independently verified. See `THIRD_PARTY_NOTICES.md` and
`docs/LICENSING_AUDIT.md` for the evidence and limitations.

The 12-class fallback predicts only these classes:

```text
chicken_biryani, chole, chomchom, curd_dahi, jalebi, kheer,
khichdi, morog_polao, pakora, pani_puri, paratha_plain, rasgulla
```

It is retained so an installed primary-model technical failure does not turn a
valid photo into a fabricated answer. It must not be used to override a normal
uncertain 80-class result. The 7-class artifact is retained for comparison only
and is outside the scanner policy.

## API and deployment notes

`POST /api/vision/predict` exposes the selected runtime in its `model` field and
adds `recognition` metadata including `fallback_used`,
`prediction_unconfirmed`, and `low_confidence_triggers_fallback: false`.
There is no `ensemble` result block.

`GET /api/vision/status` reports the fixed policy, primary/fallback status, and
whether each checkpoint is present without loading either model.

Legacy endpoints are deliberately not selectors:

- `GET /api/vision/models` remains as a deprecated policy/status response.
- `POST /api/vision/select-model` returns `410 Gone` with the fixed policy.
- `/api/vision/status?model=...` returns `400` rather than implying that a
  request can choose the normal inference model.
- A legacy `model` query parameter on `/predict` is ignored; it cannot change
  the fixed policy.

For deployments, `NUTRICARE_PRIMARY_MODEL` overrides the primary path.
`NUTRICARE_EXPERIMENTAL_MODEL` remains a compatible old name for that setting.
`NUTRICARE_FALLBACK_MODEL` overrides the technical fallback; legacy
`NUTRICARE_MODEL` is accepted as a fallback-path compatibility setting only.

Install runtime ML dependencies with:

```bash
pip install -r requirements-ml.txt
python app.py
```

Without Torch, torchvision, and Pillow, both models fail honestly and the web
application still supports the existing manual logging path.

## Integrity guard

Recognition runtime changes must not retrain, replace, or rewrite model files.
The test suite verifies these SHA-256 hashes:

```text
models/food_classifier_cc0.pt
f74d10f6efe6a7848870b16388d56a570086901afa11d6ed78e7cd914f02ad87

models/food_classifier_cc0_7class.pt
c5a1a2bb94b2213609e0dbf3a6b6f27cf09dc13c2bd2d06116d4a03226417319

models/v2/food_classifier_indian_80_224.pt
b1e8187d45ad8f8cf6676c86350c08c8a231422d36cab71e152abba772b87068
```

## Catalogue and serving limitations

Recognition and nutrition are separate. A model label is not proof that
NutriCare has a nutrition entry for that dish. Current catalogue coverage and
alias corrections remain separate Phase 2 work: 62 of the 80 primary labels
lack a catalogue nutrition row, and six existing direct mappings are too broad
or incorrect to treat as equivalent. This runtime change does not alter foods,
nutrition, aliases, portions, or meal logging.

A photo cannot measure food weight, oil, recipe, ingredients, or allergens.
NutriCare's serving grams are dataset defaults that a user can adjust; they are
not image-derived weights. Nutrition estimates and any unavailable values keep
the existing catalogue's source and quality information.

## General limitations

- Single-label classification only: one dominant dish, not multi-dish plate
  segmentation.
- No medical or safety-critical use.
- Source-dataset scores may not generalise to restaurant, home, camera, lighting,
  regional-recipe, or packaging variation.
- Low raw softmax probability is a useful uncertainty cue but does not establish
  correctness; high raw softmax probability does not confirm a food.
- The 80-class model's unresolved image rights are a material product/legal
  limitation independent of its runtime behavior.
