# Independent review — PR #8 (full diff, base `main` → `1d73936`)

Review date 2026-11-05. Scope: the **complete** PR #8 diff against
`origin/main` (`84ebb5b`), four commits, 30 files, +14,945 / −12.

**No file was modified during this review.** All probes ran from `/tmp` scratch
copies. Working tree is clean; the repository is byte-identical to `1d73936` at
the end of the review.

## Verdict: **REQUEST CHANGES**

Three findings are safety-relevant and two of them are reachable from the real
collection path (not merely from calling the API directly). None fabricates a
result or marks anything legally cleared, and no image can reach training without
human review — the outer gates hold. But the licence layer can currently mark a
**restrictively-licensed** work as `TRAINING_APPROVED`, and a **placeholder
author** satisfies the CC BY attribution requirement. In a pipeline whose whole
purpose is trustworthy rights data, those are exactly the errors that must not
ship.

| # | Severity | Finding |
|---|---|---|
| C-1 | **Critical** | CC0 approval keys on a prefix, so a restrictive modifier is ignored; reachable end-to-end |
| H-1 | **High** | Placeholder author strings (`unknown`, `N/A`, `-`) satisfy the CC BY attribution requirement |
| H-2 | **High** | The safety gates that matter most have **no behavioural tests**; 3 of 6 mutants survived |
| M-1 | Medium | `"Screenshot of a website"` is classified `scrape_risk` — an image *type*, not evidence of scraping |
| M-2 | Medium | The `models/` protection guard is ineffective and untested |
| L-1 | Low | Scrape false negatives remain (`Hosted on Photobucket`, `Uploaded to Imgur`, `no known source`) |
| L-2 | Low | `commons_audit.strip_markup` behaviour changed for a pre-existing module; no regression found, but no test pins the new contract |

---

## C-1 — Critical: restrictive licence modifier ignored on the CC0/PD path

**Files:** `training/licence_policy.py:128` (`_CC0_SHORT`), `:283-296` (tiering)

`_CC0_SHORT = re.compile(r"^\s*(cc0|cc[\s-]?zero)\b", re.IGNORECASE)` matches a
CC0 **prefix** and the tiering branch then approves without inspecting the rest
of the string. `commons_audit.classify_licence` also folds these into `CC0_PD`
because its NC/ND regexes require `cc by`/`by-nc` forms and do not fire on
`"CC0 but no commercial use"` or `"CC0 with restrictions"`.

Reproducible, through the real collection path:

```python
tree = {'Category:D': {'files': [{'title': 'File:A.jpg'}], 'subcats': [],
        'pages': [_fake_page('File:A.jpg', 1, 's1', 'CC0 but no commercial use', 'A')]}}
d = collect_class(_FakeClient(tree), {'slug': 'd', 'commons_categories': ['Category:D']})
# => bucket: CC0_PD   tier: TRAINING_APPROVED   3_rights_supported: 1
```

Also confirmed for `"CC0 with restrictions"`. Direct classification:

| `short_name` | Tier |
|---|---|
| `CC0` | `TRAINING_APPROVED` (correct) |
| `CC0 1.0` | `TRAINING_APPROVED` (correct) |
| `CC0-NC` | `EXCLUDED` (correct — NC caught upstream) |
| **`CC0 but no commercial use`** | **`TRAINING_APPROVED`** ✗ |
| **`CC0 with restrictions`** | **`TRAINING_APPROVED`** ✗ |

**Why it matters.** This is a *false approval of a restricted work*, not merely a
missed exclusion. It corrupts `rights_supported` counts, and it survives into
`prepare_v2_dataset` as `TRAINING_APPROVED`. A human reviewer would still have to
approve before count 6, so nothing reaches training unaided — but the rights
layer is supposed to be the conservative one.

**Recommended correction.** In `licence_policy`, treat a CC0 label as valid only
when the **whole** string is a CC0 label, reusing the existing
`_LICENCE_LABEL_ONLY` logic, and explicitly reject strings containing
`nc`/`non-?commercial`/`nd`/`no derivative`/`restrict`:

```python
is_cc0 = _CC0_SHORT.match(designation_text) and not re.search(
    r"(nc\b|non[-\s]?commercial|nd\b|no[-\s]?deriv|restrict)", designation_text, re.I)
```

Additionally, `commons_audit._RE_NC`/`_RE_ND` should fire on a bare `nc`/`nd`
token so the bucket itself is correct. Add tests for both strings end-to-end.

---

## H-1 — High: placeholder authors satisfy the attribution requirement

**File:** `training/licence_policy.py:283` (`attribution_sufficient = bool(artist)`)

The check is "is the string non-empty", so any placeholder passes:

| `Artist` value | Tier | `attribution_sufficient` |
|---|---|---|
| `unknown` | `TRAINING_APPROVED` | True |
| `Anonymous` | `TRAINING_APPROVED` | True |
| `N/A` | `TRAINING_APPROVED` | True |
| `-` | `TRAINING_APPROVED` | True |
| `none` | `TRAINING_APPROVED` | True |
| `"\u200b"` (zero-width space) | `TRAINING_APPROVED` | True |

Confirmed end-to-end via `build_file_record` → `enrich`.

**Why it matters.** CC BY requires attribution *to a named party*. `N/A` names
nobody, so the licence condition cannot be satisfied, yet the file is approved and
its attribution row would read `N/A`. Note `"   "` and `"\u00a0"` are correctly
trimmed — the gap is specifically placeholder *words* and zero-width characters.

**Recommended correction.** Reject a placeholder set
(`unknown`, `anonymous`, `n/a`, `na`, `none`, `-`, `—`, `?`) and strip
zero-width characters (`\u200b-\u200d\ufeff`) before the emptiness check. Add
parametrised positive/negative tests.

---

## H-2 — High: the decisive safety gates have no behavioural tests

Six mutants were applied to a scratch copy. **Three survived the full suite:**

| Mutation | Result |
|---|---|
| **M-A** remove the review gate in `prepare()` (`review:unreviewed` no longer excludes) | **640 passed — SURVIVED** |
| **M-B** remove the bytes gate (`bytes_missing` no longer excludes) | **640 passed — SURVIVED** |
| **M-C** `verify_no_leakage` returns `leak_free: True` unconditionally | 1 failed — killed |
| **M-D** splits assigned per-image instead of per-group | 1 failed — killed |
| **M-E** `train_v2` stops checking `training_usable` | 1 failed — killed |
| **M-F** remove the production-model path guard | **640 passed — SURVIVED** |

Root causes:

- The review gate is tested only through `review_verdict()` (a pure function).
  **No test calls `prepare()` and asserts** `review:unreviewed` is in
  `exclusion_reasons`. Grep for `review:unreviewed` in `tests/` returns nothing.
- `bytes_missing` is asserted in exactly one place
  (`test_licence_provenance_fixes.py:531`), in a test that also passes when the
  gate is removed because other reasons still exclude.
- `test_production_model_path_is_untouched_by_pipeline` only asserts
  `tv.PROTECTED_MODEL == PROTECTED_MODEL` — a constant comparison. It never calls
  `train()` with `out_dir=models/`.

**Why it matters.** "Unreviewed is never approved" and "no bytes, no training" are
the two invariants the entire project rests on. Both are currently protected only
by code that no test would notice being deleted — and the previous review round
already had to fix two bugs of exactly this class.

**Recommended correction.** Add three behavioural tests:

1. `prepare(docs, reviews={})` → every row carries `review:unreviewed` and
   `totals["usable_images"] == 0`.
2. `prepare(docs, images_dir=None, reviews=<all approved>)` → every row carries
   `bytes_missing` and `usable_images == 0`.
3. `train(..., out_dir=Path("models"))` returns `2` and writes nothing.

---

## M-1 — Medium: `"Screenshot of a website"` misclassified as scraping

**File:** `training/licence_policy.py` (`_COPY_VERB`, the `\bscreenshot(s|ed)?\b` alternative)

```
classify_provenance(permission_text="Screenshot of a website") -> scrape_risk
```

A screenshot is a legitimate way to depict a user interface or a menu, and
Commons holds many. The alternative matches "screenshot" unconditionally, so it
fires on the noun alone rather than on evidence of copying.

**Why it matters.** It is an over-exclusion: a permitted file is dropped. Lower
severity than C-1 because it only removes candidates, never adds them.

**Recommended correction.** Require a source: match `screenshot\s+(from|of|taken
from)` only when the object is a video/film/site *being copied*, or drop the bare
`screenshot` alternative and keep `screen grab of`/`captured from a video`.

---

## M-2 — Medium: the `models/` guard is ineffective and untested

**File:** `training/train_v2.py:~370`

```python
if out_dir.resolve() == PROTECTED_MODEL.parent.resolve() and (out_dir / PROTECTED_MODEL.name).exists():
```

The checkpoint is written to `out_dir / "food_classifier_v2_experimental.pt"`, so
this guard can never fire for a real overwrite of `food_classifier_cc0.pt`. It
only refuses when the target directory *is* `models/` and the production file
happens to exist — a condition that does not correspond to the risk. Behaviour is
in fact safe (a distinct filename is used), but the guard is dead weight that
reads as protection and is not tested (M-F).

**Recommended correction.** Either delete the guard and rely on the distinct
filename plus a test asserting no write outside `models/v2/`, or invert it to
refuse any `out_dir` whose resolved path equals `models/`.

---

## L-1 — Low: remaining scrape false negatives

```
"Hosted on Photobucket"        -> unknown
"Uploaded to Imgur"            -> unknown
"no known source"              -> unknown
"image courtesy of example.com"-> unknown
```

These fail to *unknown*, never to `cleared`, so the exposure is a missed signal
rather than a false permission. `imgur` is in `_SOCIAL_PLATFORM` but a
`uploaded to` verb is not in `_COPY_VERB`. Recommend adding
`(hosted|uploaded)\s+(on|to)` and `no known source`.

## L-2 — Low: `commons_audit.strip_markup` contract changed without a pinning test

`strip_markup` now returns `""` for lists, dicts and booleans where it previously
returned `str(value)`. This is a **pre-existing module** shared with the Biryani
pilot. I verified no regression: rebuilding the pilot from captured raw produces a
**byte-identical manifest** (ignoring `generated_utc`/`provenance`), and the 93
recorded authors contain no bracket/brace artifacts. But no test pins the new
contract, so a future revert would not be caught. Recommend a direct unit test.

---

## Verified correct (no finding)

**Licence layer** — the following were attacked and held:

- A non-CC0 `short_name` inside a `CC0_PD` bucket → `EXCLUDED` for `CC BY 4.0`,
  `CC BY-SA 4.0`, `CC BY-NC 4.0`, `CC BY-NC-ND`, `GFDL`, `All rights reserved`,
  `Fair use`, `artwork copyrighted`.
- Empty, whitespace-only, `None` and absent `short_name`/`usage_terms` → `EXCLUDED`
  (fails closed).
- Public Domain: nine designations all deferred to `REVIEW_REQUIRED` with stable
  keys; unrecognised PD → `pd_unrecognised`; no PD designation is accepted.
- Authorless CC BY-SA → `EXCLUDED`; `--include-cc-by-sa` cannot admit an
  authorless or unreviewed file.
- `attribution_required=False` does not exempt CC BY.

**Provenance layer** — permission vs credit separation holds; `"Transferred from
en.wikipedia"` is `transfer_only` in both fields and never a review; licence
echoes (`CC BY-SA 2.0`, `CC0`, `GFDL`, `Creative Commons Attribution`) are
`unknown` with a `permission_licence_echo` signal; genuine grant language is still
`permission_asserted`; empty metadata is `unknown`; `unknown` never implies
verified; `independent_review` still reports
`verification="declared_only"`, `legal_clearance="not_verified"`.

**Preparation and training**

- With no reviews, `usable_images == 0` even when every row is `TRAINING_APPROVED`.
- With reviews but no bytes, `usable_images == 0`.
- A row missing a `rights` key is excluded (`rights_not_supported`).
- `check_dataset` refuses non-usable rows, rows without a local path, single-class
  datasets, and SHA1 spanning splits.
- Split integrity: over **200 seeds**, **0** duplicate groups straddled splits and
  **0** seeds produced an empty split.
- The trainer refuses an empty test split rather than inventing a metric.

**Artifacts** — committed review batches report `byte_downloaded: false`, all
thumbnails `url_unresolved`, and **0** images with `usable_for_training: true`.
All three committed `split_*.json` have `count: 0`. `ATTRIBUTIONS.md` is an empty
table carrying the "not legal clearance" notice. No fabricated approval anywhere.

**Preservation** — fallback model hash
`f74d10f6efe6a7848870b16388d56a570086901afa11d6ed78e7cd914f02ad87`, identical
to the pre-PR value. `models/`, `data/v3/`, `nutricare/` show no modifications.
The Biryani manifest rebuilds byte-identically. No human decisions touched. The
100-class taxonomy is unchanged. No real-photo accuracy is claimed anywhere; the
only training result in the repo is the synthetic self-test, correctly labelled.

---

## Test results (exact)

| Run | Result |
|---|---|
| Focused (licence, provenance, preparation, commons, biryani, review) | **407 passed, 0 failed, 0 skipped, 0 errored** |
| Full suite (`/tmp/v2venv` with torch) | **640 passed, 0 failed, 0 skipped, 0 errored** |
| Base env (no torch/Pillow) | 615 passed, 12 skipped, 3 failed, 4 errors — all 7 in `tests/test_vision.py`, pre-existing torch absence, 0 non-vision failures |
| Mutation testing | 6 applied, **3 survived** (M-A, M-B, M-F) |

## Existing assertions weakened?

No. `tests/test_v2_pipeline.py` changes across the PR are additive only
(`short_name` added to fixtures; `external_review` renamed to
`independent_review`). The CC BY author-requirement test is unchanged.

---

## Required before merge

1. **C-1** — reject restrictive modifiers on the CC0 path; add end-to-end tests.
2. **H-1** — reject placeholder and zero-width authors; add parametrised tests.
3. **H-2** — add the three missing behavioural tests (review gate, bytes gate,
   `models/` refusal).

**M-1**, **M-2**, **L-1**, **L-2** are recommended but not blocking.

Stopping here per instructions — no corrections applied, awaiting approval.
