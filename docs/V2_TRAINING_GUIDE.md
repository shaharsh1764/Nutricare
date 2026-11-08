# V2 experimental training: local procedure

The V2 pipeline is written and tested, but **no real V2 model was trained in this
environment.** Wikimedia image hosts are unreachable from the sandbox where the
code was written (`upload.wikimedia.org` returns nothing), so there were no bytes
to decode, review or learn from. Everything below is the exact procedure to run
it locally.

Read the honesty note at the bottom before quoting any number.

---

## What is verified vs. what is not

| Item | Verified in the sandbox | Note |
|---|---|---|
| Dataset collection code | Yes, offline self-test + live failure path | Live API unreachable here |
| Licence tiering | Yes, 22 unit tests | Rules, not legal advice |
| Review batches | Yes, 2 real batches built | Reviewer time still required |
| Preparation / splits / dedupe | Yes, 30 unit tests | Uses captured real metadata |
| Training code path | Yes, trains on synthetic patterns | 0.75 vs 0.25 majority baseline |
| **A model on real food photographs** | **No** | No image bytes available |
| **Real accuracy figures** | **None exist** | Do not invent them |

---

## Requirements (Windows / PowerShell)

```powershell
cd <path>\to\Nutricare
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-training.txt
```

`requirements-training.txt` carries torch, torchvision, Pillow and numpy and is
deliberately separate from `requirements.txt`, so the app and its 390 existing
tests keep running on a machine with no ML stack.

CPU-only is enough. A GPU helps but is not needed at this data scale.

---

## Step 1 — Collect metadata

Metadata only; no images are downloaded.

```powershell
python training\collect_v2.py --all --depth 1
```

Result: one JSON manifest per class in `data/v4/classes/`. Re-running refreshes
in place and never disturbs other classes.

Expect CC BY-SA to dominate. To see the permissive subset:

```powershell
python training\collect_v2.py --class naan --class roti --class biryani
```

Check what is still outstanding:

```powershell
python training\collect_v2.py --all --plan
```

## Step 2 — Build review batches

```powershell
python training\build_v2_review_batches.py --per-class 10 --plan
python training\build_v2_review_batches.py --per-class 10
```

Batches land in `data/v4/review/<class>/review_sample.json`. Entry thumbnails are
recorded as `url_unresolved` on purpose: the collector does not invent URLs. The
existing review workflow (`training/review_sample.py`, `review_store.py`,
`render_review_page.py`) resolves and displays them.

The first Biryani review sample under `data/v3/commons_pilot/review/` is
protected in code: writing into it raises, and a batch that already has
`review_decisions.json` can never be regenerated.

## Step 3 — Download the images you are permitted to use

This is your action, on your machine, and it is the step an authorised human
must take. The download plan lists only files whose declared licence is
CC0/PD/CC BY, plus CC BY-SA for review purposes:

```powershell
python -c "import json;d=json.load(open('data/v4/prepared/download_plan.json'));print(d['count'])"
```

Save files as `data\v4\images\<pageid>.jpg` (the page id is what the pipeline
matches on first). Keep `ATTRIBUTIONS.md` alongside any redistribution.

## Step 4 — Review, then prepare

Record decisions with the existing review tooling. Approval requires
`relevance: relevant`, `quality: good` or `acceptable`, and no raised flags.
Unreviewed is never approved.

```powershell
python training\prepare_v2_dataset.py `
    --classes-dir data\v4\classes `
    --images data\v4\images `
    --reviews data\v4\review\roti\review_decisions.json `
    --out data\v4\prepared
```

This performs the real gate: rights filter, review filter, corrupt-image
detection, exact dedupe (page id / SHA1 / normalised title), near-duplicate
detection (dHash), cross-class duplicate conflicts, and leak-free stratified
splits assigned per duplicate group.

Read `data\v4\prepared\PREPARATION_REPORT.md`. **Count 6 is the only number that
is a training-image count.** If your classes have fewer than 2 usable images in
each split, they will not be marked ready, and training will refuse.

## Step 5 — Train

```powershell
python training\train_v2.py `
    --dataset data\v4\prepared `
    --images data\v4\images `
    --epochs 12 --architecture mobilenet_v3_small --image-size 160 `
    --out models\v2
```

Outputs, both under `models\v2\`:

- `food_classifier_v2_experimental.pt` — weights, class mapping, image size
- `food_classifier_v2_experimental.metrics.json` — accuracy, macro/weighted F1,
  per-class precision/recall/F1, confusion matrix, hardest confused pairs,
  majority-class baseline and lift over it

The run refuses to start, and produces no metrics at all, if the test split is
empty, if any row is not marked `training_usable`, if a SHA1 or duplicate group
spans two splits, or if fewer than 2 classes are present.

## Step 6 — Evaluate honestly

```powershell
python -c "import json;m=json.load(open('models/v2/food_classifier_v2_experimental.metrics.json'));print(m['test']['accuracy'],m['baseline'],m['lift_over_baseline'])"
```

Report the accuracy **and** the baseline together. If `lift_over_baseline` is
zero or negative, the correct conclusion is that the usable data is too small,
not that the metric is unfair.

---

## Expected output paths

```
data/v4/classes/<slug>.json                       per-class collection manifests
data/v4/review/<slug>/review_sample.json          review batches (2 committed)
data/v4/prepared/dataset_manifest.json            full provenance per image
data/v4/prepared/split_{train,val,test}.json      usable images only
data/v4/prepared/download_plan.json               files you may fetch
data/v4/prepared/ATTRIBUTIONS.md                  attribution for every usable image
models/v2/food_classifier_v2_experimental.pt      experimental weights
models/v2/food_classifier_v2_experimental.metrics.json
```

---

## Why BatchNorm is configured the way it is

`train_v2.py` defaults to cumulative BatchNorm running statistics
(`momentum=None`). Measured on this pipeline: with the default exponential
momentum, validation accuracy stayed at chance (0.25) while training loss fell to
0.16 — memorisation with no generalisation. Switching to cumulative averages took
the identical run to 0.75 test accuracy. V2 classes are small, so a handful of
batches per epoch is normal, which is exactly the regime where this bites.
Override with `--bn-momentum exponential` if you disagree, but measure it.

## Honesty note

There are **no real V2 accuracy figures in this repository**, because no model
has been trained on real photographs. The numbers produced by
`training/train_v2.py --self-test` (0.75 test accuracy against a 0.25 majority
baseline) are on synthetic black-and-white patterns generated by the test itself.
They prove the training, evaluation, checkpointing and refusal paths are wired
correctly. They say nothing whatsoever about recognising Indian food.

The 12-class production model (`models/food_classifier_cc0.pt`) is untouched and
remains the model the app serves. The V2 experimental model is not wired into the
app, and `train_v2.py` refuses to write into the production model path.
