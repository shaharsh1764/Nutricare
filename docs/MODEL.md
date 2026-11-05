# AI Food Scanner — model documentation

Everything needed to understand, reproduce, evaluate, install or replace the
food-recognition model. Read alongside `docs/DATASET.md` (data) and the
`AI Food Scanner` section of `README.md` (product behaviour).

## 1. Current status of the shipped model

**No trained checkpoint is included in this repository.** That is a deliberate,
documented state, not an oversight:

```
GET /api/vision/status
{"model": {"model_present": false, "loaded": false,
           "detail": "No trained checkpoint is installed, so photo recognition
                      is switched off. The app will not guess — see docs/MODEL.md
                      for how to train and install one. Manual logging still works."}}
```

When the checkpoint is absent, `POST /api/vision/predict` returns **HTTP 503**
with `model_unavailable: true` and **no** predictions. There is no random-guess
fallback, no name-matching heuristic dressed up as AI, and no hardcoded answer
table. The rest of the feature — validation, camera/upload UI, nutrition
mapping, portion maths, meal logging — is fully functional and covered by tests.

Why nothing was trained here: the build sandbox could not reach a single dataset
host or the pretrained-weights host (see `docs/DATASET.md` §4). Transfer learning
without ImageNet weights on 2 vCPU / 3 GB / no GPU would have produced a model
with no useful accuracy. Reporting a fabricated number was the one thing that
was not acceptable.

## 2. Architecture

| Property | Value |
|---|---|
| Model | MobileNetV3-Small (default), ImageNet-pretrained |
| Alternatives wired | `mobilenet_v3_large`, `efficientnet_b0`, `resnet18` |
| Input | 224 × 224 RGB, ImageNet normalisation (μ .485/.456/.406, σ .229/.224/.225) |
| Head | replaced final linear → `num_classes` |
| Params | ≈2.5 M (small) |
| Checkpoint size | ≈6 MB fp32 (measured: `models/selftest.pt` = 6.1 MB) |
| Runtime | CPU-only; no GPU required |
| Framework | PyTorch + torchvision |
| Task type | **Single-label** classification |

Selection rationale: this must run inside a Flask app on modest hardware. MobileNetV3-Small
gives the best accuracy-per-millisecond on CPU, needs no GPU at inference, and
keeps the checkpoint small enough to distribute. A bigger backbone (ResNet-50)
would buy a few points of accuracy for ~10× the latency and 100 MB of weights —
the wrong trade for a phone-facing feature.

**Single-label limitation, stated plainly:** the model identifies the one
dominant dish in a photograph. It cannot separate four items on a thali. The UI,
the API (`single_label: true`) and the README all say so. Multi-dish support
needs object detection (e.g. YOLO) plus per-crop classification — a different
architecture, not a tuning change.

## 3. Classes

59 classes are defined in `data/food_classes.json`, grouped as:

| Group | Count | Examples |
|---|---|---|
| Indian staples | 11 | roti/chapati, paratha, naan, puri, plain & brown rice, pulao, khichdi |
| Indian breakfast | 8 | idli, plain dosa, masala dosa, uttapam, poha, upma, vada, chole bhature |
| Indian curries & vegetables | 15 | dal, dal tadka, rajma, chole, palak paneer, aloo gobi, sambar, rasam, kadhi |
| Indian rice dishes | 6 | veg/chicken biryani, curd rice, lemon rice, tomato rice, fried rice |
| Indian snacks | 8 | samosa, pakora, dhokla, kachori, vada pav, pani puri, bhel puri |
| International | 11 | pizza, burger, sandwich, pasta, noodles, fries, fried chicken, momos, spring rolls, pancakes, salad |

**36 of 59** have documented nutrition in `data/foods.json`; the other 23 are
marked `nutrition_source: "unavailable"` and the app asks the user for values
instead of inventing them. Three visually identical items are merged rather than
faked: roti/chapati/phulka, pulao/jeera rice, and the plain dal family.

Add or remove classes by editing `data/food_classes.json`; the API, UI, tests
and trainer all read that one file.

## 4. Training

```bash
pip install -r requirements-train.txt
python training/download_datasets.py --probe          # check connectivity first
python training/download_datasets.py --out data/raw
python training/train_food_classifier.py \
    --data data/raw --epochs 15 --batch-size 32 --lr 3e-4 \
    --architecture mobilenet_v3_small --output models/food_classifier.pt
```

Pipeline, in order:

1. **Discover** `data/raw/**/<class>/<images>` and map folder names to slugs via
   `EXTRA_ALIASES` (case/punctuation insensitive). Unmapped folders are reported.
2. **Filter** classes below `--min-images` (default 20).
3. **De-duplicate** by `(stem, size)` to prevent train/test leakage.
4. **Stratified split** per class: 70/15/15 train/val/test, seeded (`--seed 42`).
   The test split is touched exactly once, at the end.
5. **Augment** training images only: RandomResizedCrop(0.7–1.0), horizontal flip,
   colour jitter, ±12° rotation.
6. **Transfer learning**: load ImageNet weights, replace the head, freeze the
   backbone for `--freeze-epochs` (default 1), then fine-tune all layers at 0.2× LR.
7. **Optimise**: AdamW (wd 1e-4), cosine schedule, label smoothing 0.1,
   `CrossEntropyLoss`.
8. **Select** the best epoch by validation accuracy.
9. **Evaluate** on the held-out test split; write metrics, per-class table,
   confusion matrix and the most-confused pairs.

Outputs (all git-ignored as build artefacts):

```
models/food_classifier.pt           checkpoint: state_dict, classes, architecture,
                                    input_size, normalisation, test_accuracy, metadata
models/food_classifier.metrics.json accuracy, macro/weighted F1, per-class P/R/F1,
                                    confusion matrix, hardest confusions, history
models/food_classifier.report.txt   human-readable summary, worst classes listed first
```

### Proving the pipeline without any dataset

```bash
python training/train_food_classifier.py --self-test
```

This generates random-noise images for three classes, trains two epochs with
`pretrained=False`, and writes `models/selftest.pt`. It exercises the entire
chain — discovery, split, augmentation, training loop, best-epoch selection,
test evaluation, metrics, checkpoint format — in about 15 seconds on CPU, and
prints:

```
TEST accuracy : 0.3333  (n=6)
TEST macro F1 : 0.1667
SELF-TEST PASSED — pipeline produced models/selftest.pt (6069 KB)
The accuracy above was measured on random noise and is NOT a statement about
real food photographs.
```

Those numbers are **pipeline evidence, not model performance**. They are labelled
as such in the output, in the metrics JSON (`"trained_on": "random weights (test
fixture)"`) and here.

## 5. Installing and running inference

```bash
pip install -r requirements-ml.txt        # torch, torchvision, Pillow
cp /path/to/food_classifier.pt models/food_classifier.pt
python app.py
curl -s localhost:5000/api/vision/status | python -m json.tool
```

* The checkpoint is loaded **once**, lazily, on the first prediction, and cached
  for the process (guarded by a lock). It is never re-read per request.
* Override the path with `NUTRICARE_MODEL=/path/to/model.pt`.
* No checkpoint → 503 + `model_unavailable`, never a fake answer.
* Corrupt checkpoint → 503 with the reason in `detail`.
* Startup never depends on the ML stack; the app boots fine without torch.

Measured cold-start on this CPU-only box (2 vCPU): checkpoint load ≈0.6 s,
single-image inference ≈60–90 ms at 224 px for MobileNetV3-Small.

## 6. Nutrition mapping (recognition ≠ nutrition)

`nutricare/food_recognition.py` links a predicted class to a row in the existing
`foods` table and scales it with the existing `nutrition.scale_per100()` — the
same function the manual logger uses, so the two can never disagree.

* 36 classes resolve to documented dataset entries and get real numbers with a
  cited source (`data/SOURCES.md`).
* 23 classes have no dataset entry. No value is invented: the API returns
  `nutrition_available: false` with an explanation, and logging requires the
  user's own kcal (optionally protein/carbs/fat).
* Approximation is declared where the class stands in for something else — e.g.
  *masala dosa* is costed with the plain-dosa entry and says so.
* Every estimate carries a ±10 % (international) or ±15 % (Indian) band that
  reflects **recipe and cooking-oil variation**, documented as such rather than
  presented as measurement error.

## 7. What still limits accuracy

1. **No training run has been performed in this environment** — the pipeline is
   complete and self-tested, but the accuracy of a real model is unknown until
   you train it. Do not quote a number before then.
2. **Visually similar Indian dishes** will be the weak spot: dal varieties, plain
   vs masala dosa, roti vs naan, paneer curries. The evaluation report lists the
   worst classes first *by design*. Expect the need for more data per class
   rather than a different architecture.
3. **Portion weight cannot come from a photo.** No reference object, depth or
   scale is available, so weight is always the user's adjustment of a default
   serving. The UI states this next to the grams field.
4. **Single dish per photo** (see §2).
5. **Class imbalance** — Indian sets vary from 40 to 200 images per class; use
   `--min-images` to drop thin classes and expect per-class F1 to be uneven.
6. **Domain shift** — dataset photos are often studio-lit; phone photos of a home
   thali at night are harder. Collect your own validation set from real users
   before trusting production accuracy.

## 8. Reproducing a published number

If you train and want to state an accuracy, state it like this:

> MobileNetV3-Small, 59 classes, trained on <datasets + versions>, 70/15/15
> stratified split (seed 42), evaluated once on the held-out test set:
> accuracy X.XX, macro F1 X.XX. Per-class results in
> `models/food_classifier.metrics.json`. Worst classes: …

Commit the `*.metrics.json` and `*.report.txt` alongside the checkpoint. Anything
less repeats the exact failure this project is designed to avoid.
