# V2 expansion plan: from 100-class target to a real training set

Status 2026-11-05. The 100-class taxonomy stands unchanged. Nothing was removed,
renamed, merged or replaced. Classes without adequate data are recorded as
**collection gaps**, not deleted.

This document is the working plan for the next expansion cycles. It exists
because the measurement work changed what the bottleneck is.

---

## 1. What we learned, and why the plan changed

The original assumption was that category size was the limiting factor. It is
not. Measured across all 100 classes:

- 97 classes have a live Commons category; 8,270 direct file slots in total;
- 55 classes have 50+ files, 26 have 100+, 9 have 200+;
- **but** files whose declared licence is genuinely unrestricted (CC0 / PD /
  CC BY, excluding share-alike) are a small minority everywhere.

The Biryani pilot's own manifest shows the shape precisely: **89 of 93 files are
CC BY-SA**, 2 CC BY, 2 CC0. Direct per-category measurements of unrestricted
files: Naan 30 of 230, Biryani 27 of 468, Roti 12 of 393, Idli 3 of 248,
Dosa 1 of 73.

So a strictly permissive dataset yields roughly **1–3 images per class** before
review losses. That is not enough for a 100-class model, and pretending
otherwise would just produce a model that memorises.

**The binding constraint is licensing, not supply.** That should drive the next
sprint far more than more category crawling would.

## 2. The one decision that unblocks the most

CC BY-SA files are usable images with a *known* obligation, not
unusable images. The open question is whether share-alike obligations extend to
trained model weights. That is a legal question, and this project does not answer
it.

Until it is answered, the pipeline defaults to holding CC BY-SA out of the
training-approved tier (`REVIEW_REQUIRED`), and `prepare_v2_dataset.py` supports
`--include-cc-by-sa` so a decision can be applied without a code change.

Whoever resolves it needs: the licence text (CC BY-SA 2.0/3.0/4.0), the planned
distribution of the weights, and whether the dataset itself is redistributed.
With a favourable answer, the usable pool goes from ~1–3 per class to roughly
50–150 per class for the stronger classes. Everything else in this plan is
secondary to that.

In parallel, and not blocked on legal review:

- broaden the permissive pool by searching Commons *outside* the taxonomy
  categories: `haslicense:unrestricted` with dish-name synonyms, plus PD sources
  such as `Category:PD-India` and pre-1950 photographs;
- treat each Commons author who releases under CC0 as a vein worth mining —
  a handful of prolific CC0 food photographers supply a disproportionate share;
- record for each class whether its permissive pool is genuinely exhausted, so
  the gap list is defensible rather than assumed.

## 3. Where the 100 classes currently stand

Full tables are in `data/v4/reports/COVERAGE_REPORT.md` and
`data/v4/coverage_100.json`. Summary:

| Band | Classes | Interpretation |
|---|---|---|
| 200+ direct files | 9 | Supply is not the issue; licensing is |
| 100–199 | 17 | Viable once licensing is settled |
| 50–99 | 29 | Needs subcategory depth plus review |
| 1–49 | 41 | Thin; needs synonyms, subcategories or an alternative source |
| 0 / unmeasured | 4 | Genuine collection gaps |

Collection gaps recorded so far, and what is needed:

- **Vada** — `Category:Vada` is empty. The dish is `medu vada` / `vadai`; a
  corrected category reference is needed. Nothing was renamed without approval.
- **Sambar** — the taxonomy references `Category:Sambar`, which does not exist
  as such; `Category:Sambhar` has 8 files. Discrepancy recorded, taxonomy left
  alone.
- **Matar paneer** — previously unmeasured at 0; now measures 31 files. Recorded
  as a measurement, not an approval.

## 4. Next cycle, in order

Each cycle is `collect → review → prepare → train → evaluate → compare`, against
a **stable test set**.

**Cycle 1 — settle the licence question.** In parallel: expand the permissive
pool with synonym and PD-source searches; fix the `vada` and `sambar` category
references. No code changes required for any of this.

**Cycle 2 — first real dataset.** Target the classes with the deepest permissive
pools first (Naan, Biryani, Roti, Chutney, Samosa, Tandoori chicken, Lassi).
Run `collect_v2.py --all`, build batches, review, then prepare with real bytes.
Expect the honest answer to be **fewer than 5 classes ready**. Report that
number; do not pad it.

**Cycle 3 — first real model.** Train on whatever genuinely qualified. Report
accuracy next to the majority baseline. If lift is near zero, the finding is
"data too small", and the fix is more review, not a bigger network.

**Cycle 4 onwards — breadth.** Add classes in bands of ~10, retrain, and compare
against the preceding cycle on the same test split. Freeze the test set once
enough classes have data, and only ever add to it from newly collected classes.

## 5. Invariants that must not drift

- Keep all 100 classes. Gaps are recorded, never deleted.
- Keep the six counts separate. Nothing but count 6 is a training count.
- Keep the three checks separate: technical validity, label correctness,
  provenance rights. They fail independently.
- Unreviewed is never approved; a declared licence is never verified permission.
- Splits are assigned per duplicate group, so no near-duplicate can straddle
  train/val/test.
- Never overwrite the first Biryani review sample or its decisions.
- Never write into `models/food_classifier_cc0.pt`. V2 writes only to
  `models/v2/`.
- The app keeps serving the 12-class fallback. Only propose replacing it after
  V2 is measurably better on a stable, reviewed test set.
- Do not claim the 100-class model is complete until all 100 classes have
  adequate verified data and evaluation coverage.

## 6. What "done" looks like for the next milestone

Not "a model exists". The milestone is: **at least 5 classes with ≥20
training-usable images each, split leak-free, with a held-out evaluation that
beats the majority baseline.** If the data cannot reach that, the milestone is
the honest count plus the recorded reason — which is a legitimate outcome and the
one most likely to be true on the first pass.

## 7. Tooling map

| Tool | Purpose |
|---|---|
| `training/collect_v2.py` | Incremental per-class metadata collection |
| `training/licence_policy.py` | Rights tiering and attribution records |
| `training/build_v2_review_batches.py` | Multi-class review batches |
| `training/prepare_v2_dataset.py` | Rights/review/dedupe gate and leak-free splits |
| `training/train_v2.py` | Experimental training and honest evaluation |
| `training/demo_v2_pipeline.py` | End-to-end evidence run on captured metadata |
| `tests/test_v2_pipeline.py` | 73 regression tests for the above |

Each tool has a `--self-test` that runs offline. Run them before trusting a
result produced on the network.
