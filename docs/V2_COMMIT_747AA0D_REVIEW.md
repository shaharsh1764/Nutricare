# Independent review — commit 747aa0d

Review date 2026-11-05. Reviewed commit `747aa0d` ("Fix licence author requirements
and restore provenance flow") against its parent `a133dcb`, on branch
`arena/e9641d19-nutricare` (PR #8, open, unmerged).

**No code, test, or data file was modified during this review.** All probes ran
from `/tmp` scratch copies. Working tree is clean and matches `747aa0d`.

## Verdict: **APPROVE WITH NON-BLOCKING NOTES**

No critical or high-severity correctness or safety issue was found. Every
behaviour the commit claims to fix is genuinely fixed, the fixes fail closed
under misclassification, and all six required mutation tests are caught by the
new tests. The notes below are real but non-blocking: they are places where the
implementation is narrower or more optimistic than its own documentation
suggests, not places where an unsafe image can pass.

---

## 1. Verified correct

### 1.1 CC0 without an author

Confirmed passing rights eligibility (`licence_policy.py:128`, `:283-296`), with
author metadata still preserved. Missing authorship is never promoted to
provenance:

```
CC0, artist=""  -> TRAINING_APPROVED, attribution_sufficient=False,
                   verification="declared_only", legal_clearance="not_verified"
                   reason: "no author recorded (permitted for CC0, but the
                            attribution record will show 'unknown')"
```

The gap is *recorded*, not silently dropped.

### 1.2 Fail-closed under misclassification (important, and correct)

I tested the scenario where upstream `classify_licence` puts a non-CC0 work into
the `CC0_PD` bucket. Approval is keyed on `short_name`, not the bucket, so it
fails closed:

| Bucket | `short_name` | Author | Tier |
|---|---|---|---|
| `CC0_PD` | `CC BY 4.0` | none | **EXCLUDED** |
| `CC0_PD` | `CC BY-SA 4.0` | none | **EXCLUDED** |
| `CC0_PD` | `CC BY-NC 4.0` | none | **EXCLUDED** |
| `OTHER_REVIEW` | `CC0` | none | **EXCLUDED** |

No malformed or mismatched attribution data produced an unsafe pass.

### 1.3 Public Domain

All nine deferred PD families respond correctly, and a bare `CC0_PD` entry with
no licence text fails closed:

```
PD-USGov / PD-Art / PD-scan / PD-old-100 / PD-India / PD-self
  / No known copyright restrictions / Public domain / PD-1996  -> REVIEW_REQUIRED
CC0_PD with no short_name and no usage_terms                   -> EXCLUDED
```

Brace and spacing variants (`PD US Gov`, `Pd-usgov`, `public  domain`) are all
matched. An unrecognised PD wording is named `pd_unrecognised` and deferred.

### 1.4 CC BY and CC BY-SA

- CC BY without an author → `EXCLUDED`; with an author → `TRAINING_APPROVED`.
- `attribution_required=False` does **not** exempt CC BY (correct — the flag is
  uploader-maintained).
- Authorless CC BY-SA → `EXCLUDED`. The `--include-cc-by-sa` path cannot reach
  training eligibility, because `prepare_v2_dataset.py:540` re-checks
  `attribution_sufficient` and adds `attribution_incomplete`.
- `--include-cc-by-sa` cannot make an unreviewed image training-eligible:
  `training_usable` still requires a human approval and local bytes.

### 1.5 Provenance

- `scrape_risk` correctly gates **every** licence, including reclassifying an
  otherwise-approved CC BY into `EXCLUDED`.
- Wikipedia transfer is `transfer_only`, never a review — verified in both the
  `Credit` and `Permission` fields.
- Flickr description → `attribution_only`. `Own work` → `attribution_only`.
- A review claim in `Credit` alone is **not** promoted to `independent_review`
  (recorded as a `credit_review_claim` signal instead).
- Empty/absent metadata → `unknown`. Absent `permission` key does not raise.
- No API metadata path produces a positive classification from nothing.

### 1.6 End-to-end and single call path

`grep` confirms exactly **one** production call site of `classify_rights`
(`collect_v2.py:158`). `commons_audit.run_audit` does not classify rights, so no
alternate path bypasses the new checks. `Credit` and `Permission` survive
`build_file_record` → `enrich` → `classify_rights`, verified by direct trace.

The manifest now records `extmetadata_filter_sent`, derived from
`IIEXTMETADATAFILTER` — the same constant actually sent as
`iiextmetadatafilter`. Request and manifest cannot drift.

### 1.7 Mutation testing — all six required mutants killed

Performed on throwaway copies in `/tmp`:

| Mutation | Tests that failed |
|---|---|
| Remove `Credit`/`Permission` forwarding in `enrich()` | 4 |
| Treat "transferred from" as independent review | 2 |
| Allow authorless CC BY-SA back into review | 7 |
| Approve an unknown PD designation | 12 |
| Manifest reports a filter that is not sent | 2 |
| Stop sending `iiextmetadatafilter` at all | 1 |

The tests genuinely detect the bugs; they are not decorative.

### 1.8 No assertions weakened

`git diff` of the only modified test file (`tests/test_v2_pipeline.py`, 11 lines)
shows **additive-only** changes: `short_name` added to four fixture dicts, and
the strength renamed `external_review` → `independent_review`. No assertion was
deleted or loosened. The CC BY author-requirement test was deliberately left
untouched as the regression guard.

### 1.9 Preservation checks

| Requirement | Result |
|---|---|
| Fallback model hash | `f74d10f6efe6a7848870b16388d56a570086901afa11d6ed78e7cd914f02ad87` — **identical** |
| `models/`, `data/v3/`, `nutricare/` modified | None (`git status` clean for all three) |
| Biryani pilot / human decisions touched | No — the commit touches no file under `data/v3/` or `data/v4/review/` |
| 100-class target | Unchanged; `data/v3/taxonomy_100_proposed.json` not in the diff |
| Restrictions relaxed | None found |

### 1.10 Test results (exact)

- Focused (`test_licence_provenance_fixes` + `test_v2_pipeline` + `test_commons_audit`): **230 passed, 0 failed, 0 skipped, 0 errors**
- Full suite: **551 passed, 0 failed, 0 skipped, 0 errors**
- Base env without torch/Pillow: 526 passed, 12 skipped, 3 failed, 4 errors — all 7 are the pre-existing `tests/test_vision.py` torch-absent failures, unchanged from baseline

---

## 2. Findings (all non-blocking)

### NB-1 — Scrape detection is narrower than the original, and misses common phrasings

**Severity: Medium** · `training/licence_policy.py:110-114`

The commit rewrote `_SCRAPE_RISK`. Two of the changes are regressions in
coverage, not improvements:

| Text | Old regex | New regex |
|---|---|---|
| `bing` | HIT | **miss** |
| `Bing` | HIT | **miss** |
| `Bing images` | HIT | HIT |
| `"bingo night"` (false positive) | HIT | miss (correctly fixed) |

The change from `bing` to `bing (image|search)` fixes a real false positive but
also stops a bare `Bing` credit from being flagged. Separately, these realistic
indicator phrasings are **not** detected at all (old and new alike):

`from Google`, `google.com/search?q=x`, `copied from Facebook`, `Instagram`,
`Yandex images`, `screenshot from a video`, `sourced from the web`.

**Why it matters.** End-to-end, an undetected scrape indicator yields an
*approved* image:

```
Credit="from Google"           -> provenance=unknown, tier=TRAINING_APPROVED
Credit="copied from Facebook"  -> provenance=unknown, tier=TRAINING_APPROVED
Credit="google image search"   -> provenance=scrape_risk, tier=EXCLUDED
```

This is not a regression introduced by this commit — the `from Google` gap exists
in both versions — and it is *fail-open only in the sense of not excluding*: it
never marks anything legally cleared, and a human review is still required before
count 6. But the commit's own report calls the rules "functioning"; they are
functioning for a narrow set of phrasings only.

**Recommended correction.** Broaden to `\bbing\b(?!\w)` (word-bounded, which keeps
the `bingo` fix), add `google` as a bare word, and add `facebook|instagram|reddit|
yandex|duckduckgo|screenshot|copied from|sourced from`. Add a regression test for
each. Note that `wallpaper`, `pinterest` and `no source` remain over-broad and can
false-positive on dish descriptions ("wallpaper paste texture" → `scrape_risk`),
so broad words should be tightened at the same time. That over-breadth is
currently harmless (it only ever excludes), so it is a Low sub-issue.

### NB-2 — Only `scrape_risk` affects the tier; the ranking is documentation only

**Severity: Low** · `training/licence_policy.py:~283`

All six strengths are computed and ranked, but only `scrape_risk` changes the
outcome. Measured with an identical CC BY file and author:

```
unknown / attribution_only / transfer_only /
permission_asserted / independent_review  -> all TRAINING_APPROVED
scrape_risk                               -> EXCLUDED
```

**Why it matters.** The documentation in `docs/V2_LICENCE_PROVENANCE_INVESTIGATION.md`
describes the six strengths as if they were a meaningful ladder. In practice
`provenance_strength` is audit metadata and `unknown` is indistinguishable from
`independent_review` for tiering. That is arguably the right policy (provenance
was never meant to be a gate), but the report should say so plainly rather than
implying graded confidence. `rights_summary()["by_provenance_strength"]` is
therefore of limited decision value today.

**Recommended correction.** State explicitly in the docs that provenance is
informational except for `scrape_risk`. If graded gating is ever wanted, that is
a separate policy decision.

### NB-3 — `permission_asserted` fires on a bare licence echo

**Severity: Low** · `training/licence_policy.py:86-93`

`Permission="CC BY-SA 2.0"` and `Permission="Creative Commons Attribution"` — a
mere restatement of the licence — classify as `permission_asserted`, via the
`\bcc[\s-]?by\b` and `\bcreative commons\b` alternatives. That is an
over-claim: echoing a licence tag is not evidence that permission was granted.

Harmless today (it does not change the tier, per NB-2), but misleading in an
audit trail.

**Recommended correction.** Drop `\bcc[\s-]?by\b` and `\bcreative commons\b` from
`_PERMISSION_EVIDENCE`; keep only explicit grant language (`permission granted`,
`used with permission`, `released under`).

### NB-4 — Malformed metadata types raise instead of failing closed

**Severity: Low** · `training/licence_policy.py:195-196`, `:274`; `collect_v2.py:164-165`

`enrich()` handles `None` and missing keys safely, but a non-string value
raises:

```
artist_raw = ["A","B"]  -> AttributeError: 'list' object has no attribute 'strip'
credit     = 123        -> AttributeError: 'int' object has no attribute 'strip'
permission = {"value": "x"} -> AttributeError: 'dict' object has no attribute 'strip'
```

`classify_provenance(credit_text=123)` likewise raises.

**Why it matters.** `enrich()` is called inside `collect_class()`, which catches
exceptions per class (`collect_v2.py` `try/except` in `main`). One malformed
record would therefore abort collection of that entire class rather than
excluding the one file. It fails closed (no bad data is admitted) but loses a
whole class's work.

**Recommended correction.** Coerce with `str(x or "")` at the boundary, or
normalise non-string extmetadata values in `commons_audit.em()`. Low priority
because real Commons extmetadata values are strings.

### NB-5 — Dead constant `_APPROVED_CLASSES` left behind

**Severity: Low** · `training/licence_policy.py:53`

`_APPROVED_CLASSES = frozenset({"CC0_PD", "CC_BY"})` has zero remaining
references. It was the root cause of Issue 1 (the shared author branch), so
leaving it in place invites a future contributor to re-couple the licences
through it. Not a correctness bug.

**Recommended correction.** Delete it, or add a comment stating it is retained
only for external import compatibility.

### NB-6 — Documentation says ten PD designations; the code has nine

**Severity: Low** · `docs/V2_LICENCE_PROVENANCE_INVESTIGATION.md:~575` vs `licence_policy.py:130-145`

The report's PD table lists ten rows (including `pd_unrecognised`), while
`_DEFERRED_PD_SHORT` holds nine families. `pd_unrecognised` is returned by a
separate branch and is correctly deferred, so behaviour is right; only the
"ten families" phrasing is imprecise. Cosmetic.

---

## 3. Demo-artifact review

**Included and appropriate.** The regenerated artifacts accurately represent the
current pipeline and are safe to keep in PR #8.

- **Deterministic.** Re-running `demo_v2_pipeline.py` and comparing every
  non-timestamp field produced identical content:
  `classes/roti.json`, `classes/idli.json`, `prepared/dataset_manifest.json`.
  Only `collected_utc` / `generated_utc` differ between runs.
- **Accurate.** The diff is exactly the two intended changes: the manifest key
  renamed to `extmetadata_filter_sent` (+ `extmetadata_filter_param`), and the
  new rights sub-fields (`provenance_signals`, `public_domain_designation`,
  `attribution_sufficient`, `short_name`, `designation_text`). One message now
  reads `"CC BY permits…"` instead of `"CC_BY permits…"` — clearer.
- **No review data touched.** `git show --stat 747aa0d -- data/v3/ data/v4/review/`
  is empty; no source records or human decisions were modified.
- **Counts not misleading.** The demo still reports `usable_images: 0` and
  `classes_ready_for_training: 0`, and rights counts are unchanged
  (roti 2 supported / 12 CC BY-SA held; idli 1 / 13). `by_provenance_strength`
  is uniformly `unknown`, which is *correct*: the captured fixture contains no
  `Credit`/`Permission` keys.

---

## 4. Previously reported accuracy that this review corrects

One claim in the commit message and prior report is overstated in a way worth
recording, though it does not affect code correctness:

- The report states the new test file contains "88 tests". The file contains
  **60 test functions**, reporting 88 collected cases because of `parametrize`.
  Both numbers are defensible, but the report should say "60 test functions /
  88 cases" to avoid confusion in future audits.

The claim that "three pre-existing tests were updated because they asserted the
previous behaviour" is accurate and verified: all three updates were additive.

---

## 5. Summary of required action

Nothing blocks merge. Recommended, in priority order:

1. **NB-1** (Medium) — broaden scrape detection and add regression tests; it is
   the only finding with a plausible real-world safety benefit.
2. **NB-3 / NB-2** (Low) — stop treating a licence echo as permission evidence,
   and state plainly in the docs that provenance is informational except
   `scrape_risk`.
3. **NB-5 / NB-6 / NB-4** (Low) — remove the dead constant, correct the PD count,
   coerce non-string metadata.

No security regression, no preservation violation, and no fabricated result was
found. The commit does what it claims for the cases it targets; the residual risk
lives in scrape phrasings it does not yet recognise, which fails to an approved-
but-human-review-pending state rather than to a false clearance.
