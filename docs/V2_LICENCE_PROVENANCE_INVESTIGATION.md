# Investigation: licence classification and provenance detection

Inspection date 2026-11-05, against branch `arena/e9641d19-nutricare` @ `a133dcb`
(PR #8, open, unmerged).

**No production code was modified.** Working tree is clean; all 463 tests still
pass; `models/food_classifier_cc0.pt` is byte-identical
(`f74d10f6efe6a7848870b16388d56a570086901afa11d6ed78e7cd914f02ad87`).

## Verdict summary

| # | Suspected issue | Verdict |
|---|---|---|
| 1 | CC0 / Public Domain unnecessarily requires an author | **Confirmed** — and the deeper problem is worse than stated: CC0 and Public Domain cannot be distinguished downstream at all |
| 2 | Provenance detection is not connected to collection | **Confirmed**, with an important correction: the API request is *not* a filter, so the data *is* captured — it is simply dropped at the single hand-off point |
| — | Authorless CC BY-SA is never rejected | **New finding** (latent, currently masked) |

Both suspected issues are real. Issue 2's root cause is narrower than "the data
isn't fetched", and fixing it naively would introduce a false-positive bug
(§4.3).

---

## 1. Issue 1 — CC0 / Public Domain requires an author

### 1.1 Where it lives

`training/licence_policy.py`:

| Line(s) | Content |
|---|---|
| 52–55 | `_APPROVED_CLASSES = frozenset({"CC0_PD", "CC_BY"})` — one set for both, so both inherit the same author rule |
| 114 | `if declared in _APPROVED_CLASSES:` |
| **115–117** | `if not artist:` → `tier = EXCLUDED`, reason `"attribution-bearing licence but no author recorded"` |
| 118–120 | scrape-risk exclusion |
| 121–124 | otherwise `TRAINING_APPROVED` |

The defect is the **shared branch at line 114**. CC0 and Public Domain impose no
attribution condition, yet they are routed through a check whose own message
("attribution-bearing licence") is false for them.

### 1.2 Answers to the specific questions

**(1) Does the implementation exclude CC0/PD when the artist is missing?**
Yes. Reproduced:

| Record | `declared_class` | Tier |
|---|---|---|
| CC0, author present | `CC0_PD` | `TRAINING_APPROVED` |
| **CC0, author absent** | `CC0_PD` | **`EXCLUDED`** |
| Public domain, author present | `CC0_PD` | `TRAINING_APPROVED` |
| **Public domain, author absent** | `CC0_PD` | **`EXCLUDED`** |
| CC BY 4.0, author present | `CC_BY` | `TRAINING_APPROVED` |
| **CC BY 4.0, author absent** | `CC_BY` | **`EXCLUDED`** (correct) |

Measured impact on a realistic batch of 10 files (6 anonymous PD + 4 CC0 with an
author):

```
metadata_retrieved : 10
rights_supported   : 4      <-- 6 anonymous public-domain files silently dropped
excluded           : 6
reason: "attribution-bearing licence but no author recorded"
```

This matters because anonymous public-domain material (old photographs, PD-India,
government works, museum scans) is disproportionately authorless *and* is one of
the few genuinely unencumbered pools available. §2 of
`docs/V2_EXPANSION_PLAN.md` explicitly names PD sources as the way to widen the
permissive pool; this bug blocks exactly that route.

**(2) Does it distinguish licences requiring attribution from those that do not?**
No. It has the information to do so and does not use it:

- `licence["attribution_required"]` is read at line 92 and echoed back in the
  output at line 145, but is **never consulted** by the tiering logic.
- Real captured data confirms the flag discriminates: the CC0 file
  `File:Roti - Massachusetts.jpg` carries `AttributionRequired=false`, while
  CC BY 2.0 files carry `AttributionRequired=true`.

So a CC0 file with `attribution_required=false` is still excluded for lacking an
author — the exact opposite of what the flag says.

**(3) Does `commons_audit.py` correctly distinguish CC0, Public Domain and CC BY?**

Partly. It is correct with respect to **CC BY**, and lossy with respect to **CC0
vs Public Domain**.

- `training/commons_audit.py:88` defines `CC0_PD = "CC0_PD"` — a single merged
  bucket. Line 170 assigns it for both CC0 and Public Domain, using `_RE_CC0`
  (lines 105–107), which matches `cc0`, `public domain`, `^pd`, `pd-`,
  `no known copyright`, `no restrictions`.
- Precedence is sound: line 162 NC → 164 ND → 166 non-free → **170 CC0/PD** →
  172 SA → 175 CC BY. Because CC0/PD is tested *before* BY, `CC0` cannot be
  misread as `CC BY`. This is why §1.2(4) below is safe.

Verified classification:

| Declared string | `declared_class` |
|---|---|
| `CC0`, `CC0 1.0 Universal` | `CC0_PD` |
| `Public domain`, `PD-USGov`, `PD-old-100`, `No known copyright restrictions` | `CC0_PD` |
| `CC BY 4.0`, `Attribution 4.0 International` | `CC_BY` |
| `CC BY-SA 4.0` | `CC_BY_SA` |
| `CC BY-NC 4.0` / `CC BY-ND 4.0` | `NC_RESTRICTED` / `ND_RESTRICTED` |
| `Copyright expired` | `OTHER_REVIEW` (conservative, acceptable) |
| *(empty)* | `UNKNOWN_MISSING` |

Downstream, CC0 and Public Domain are **indistinguishable**:

```
CC0           declared_class: CC0_PD
Public domain declared_class: CC0_PD
identical     : True
short_name still differs: "CC0" | "Public domain"
```

`short_name` distinguishes them, but `licence_policy.py` never reads it. **Any fix
must decide CC0-vs-PD from `short_name` (or a new sub-field), not from
`declared_class`** — otherwise "CC0 exemption" would silently also exempt
`PD-USGov`, `PD-old-100` and anything else the regex folds in.

**(4) Could changing this logic accidentally allow CC BY without sufficient attribution?**

Not if the fix stays inside the `CC0_PD` branch, because the merged bucket *cannot*
contain a CC BY string: `_RE_CC0` is evaluated before `_RE_CCBY`, and `_RE_CCBY`
requires `cc by` / `by <digit>` / `attribution` — none of which `_RE_CC0` matches.
`CC BY` remains in the `**CC_BY**` path, which keeps its author requirement.

The realistic way to break this is **restructuring the shared set at line 52**:
splitting `_APPROVED_CLASSES` carelessly, or replacing the `if not artist`
condition with `if not artist and licence["attribution_required"]`. That last
form is subtly wrong: Commons sometimes reports `AttributionRequired=false` for
CC BY 0/1.0-era files, and the flag is uploader-maintained. **Gate on a positive
identification of the licence, not on the flag's absence.** Recommended safe
predicate in §6.

**(5) Are there existing tests covering these cases?**

`tests/test_v2_pipeline.py::TestRightsTiering` (17 rights-related tests pass):

| Case | Covered? |
|---|---|
| CC0 with author → approved | Yes (line 79–82) |
| CC BY with author → approved | Yes (84–87) |
| CC BY without author → excluded | Yes (89–93) |
| CC BY-SA held out | Yes (94–98) |
| NC/ND/unknown excluded | Yes, parametrised (100–106) |
| **CC0 without author** | **No** |
| **Public Domain without author** | **No** |
| **CC0 vs PD distinction** | **No** (`PUBLIC` appears 0 times in the file) |
| `attribution_required` influencing the decision | **No** |

The suite encodes the *current intended* behaviour, so it would not catch this
bug — and once fixed, **line 89–93 must stay unchanged** as the regression guard
for CC BY.

---

## 2. Issue 2 — provenance detection is not connected to collection

### 2.1 Complete data flow, Commons API → `classify_rights()`

```
HttpTransport / CommonsClient.file_info()          commons_audit.py:405-432
  request: action=query, prop=imageinfo, iiprop="url|size|mime|mediatype|sha1|extmetadata|canonicaltitle"
           (commons_audit.py:81)
  NO iiextmetadatafilter is sent  -> API returns the full extmetadata set
        |
        v
build_file_record()                                 commons_audit.py:539-600
  line 551: credit     = em(extmetadata, "Credit")
  line 552: permission = em(extmetadata, "Permission")
  line 585-589: record["attribution"]["credit"] = credit
  line 590:     record["permission"]            = permission
        |                                   <-- BOTH FIELDS ARE PRESERVED
        v
collect_v2.gather_category()                        collect_v2.py:~120
  client.file_info(batch) -> build_file_record(...)  -> fields carried through
        |
        v
collect_v2.enrich()                                 collect_v2.py:150-156
  rights = classify_rights(licence,
             artist=(record.get("attribution") or {}).get("artist_raw", ""))
        |                                   <-- HAND-OFF POINT. ONLY artist.
        v
licence_policy.classify_rights(licence, *, artist, permission_text, credit_text)
  permission_text and credit_text default to ""       licence_policy.py:75-81
  provenance_text = f"{permission_text} {credit_text}".strip()   -> "" always
  -> provenance_strength = "unknown"                  licence_policy.py:95-111
```

`collect_v2.enrich()` is the **only** production call site of `classify_rights`
(verified by `grep -rn "classify_rights(" --include=*.py .`: 1 production hit,
line 153 of `collect_v2.py`; all others are tests).

### 2.2 Answers to the specific questions

**(1) Does `collect_v2.py` retrieve Permission and Credit from Commons?**
**Yes — inadvertently, and it is not what the code claims.**

`collect_v2.py:82-83` declares:

```python
IIPROP = "sha1|dimensions|mime|extmetadata"
EXTMETADATA_FILTER = "LicenseShortName|LicenseUrl|Artist|AttributionRequired|UsageTerms"
```

`EXTMETADATA_FILTER` looks like a filter, but it is **never sent to the API**. It
appears exactly once, at `collect_v2.py:297`, where it is written into the output
JSON's `source` block as `"extmetadata_filter": EXTMETADATA_FILTER`. No
`iiextmetadatafilter` parameter is ever added to a request (grep: zero request
sites). The API therefore returns **all** extmetadata, including `Credit` and
`Permission`.

This is a **documentation defect with security value**: the manifest's
`source.extmetadata_filter` field records a filter that was never applied. Anyone
auditing a manifest could reasonably conclude `Credit`/`Permission` were
deliberately excluded, when in fact they were fetched and then discarded.

**(2) Does `commons_audit.py` preserve them in the file record?**
**Yes.** `Credit` → `record["attribution"]["credit"]` (line 585–589);
`Permission` → `record["permission"]` (line 590). Both flattened to plain text by
`strip_markup()`. Also, `build_file_record` raises the `missing_permission`
metadata gap when `Permission` is empty — so the pipeline already *knows* when
this field is absent.

**(3) Are these fields passed to `classify_rights()` anywhere in the pipeline?**
**No.** Only `artist` is passed (`collect_v2.py:153-156`). The parameters exist,
are documented, and are dead in production.

**(4) Are the scraping-risk rules functioning, partially functioning, or inactive?**
**Effectively inactive.** Reproduced end-to-end with a record that carries an
explicit scrape indicator:

```
commons_audit kept credit     : 'Taken from Google image search'
commons_audit kept permission : 'Google'
after enrich provenance_strength: unknown          <-- rule never saw the text
after enrich rights_tier        : TRAINING_APPROVED <-- scrape indicator had no effect
```

And with the text supplied, the rule works correctly:

```
classify_rights(..., permission_text='Google',
                    credit_text='Taken from Google image search')
  -> provenance_strength: scrape_risk   tier: EXCLUDED
```

So `_SCRAPE_RISK`, `_STRONG_PROVENANCE` and `_WEAK_PROVENANCE` are all
**inactive in production** while fully passing their unit tests, because every
test calls `classify_rights()` directly and **no test ever exercises `enrich()`'s
forwarding**. `grep` confirms: `credit` appears 0 times in
`tests/test_v2_pipeline.py`; `permission_text` appears only in the two
direct-call tests (lines 110, 118).

Consequence: every production record reports `provenance_strength = "unknown"`.
`rights_summary()["by_provenance_strength"]` is therefore always
`{"unknown": N}`, and the provenance section of the coverage report is
uninformative. Note this is a **fail-safe** bug: the classifier is *more*
permissive than intended (it does not exclude scrape-risk files), not less. It
never marks anything cleared.

**(5) Are there alternative provenance checks elsewhere?**
Only two, both weak for this purpose:

- `metadata_gaps` records `missing_permission` / `missing_artist`
  (`commons_audit.py:556-566`). Presence of a gap is recorded but **never
  influences the rights tier**.
- `attribution_record()` / `render_attributions()` (`licence_policy.py:170-206`)
  reproduce author and licence for attribution purposes only. No provenance
  judgement.

There is no other scrape or re-hosting check in the codebase.

---

## 3. What a naive fix would break — measured

`permission_text`/`credit_text` are not empty in practice, and they are **mostly
benign boilerplate**. Supplying them unexamined would reclassify many legitimate
files:

| Real `Credit` value (captured from Commons) | Current rule's verdict | Correct verdict |
|---|---|---|
| `Own work` | `self_declared` | OK |
| `Transferred from en.wikipedia to Commons by Number55 using CommonsHelper.` | **`external_review`** | **wrong** — a wiki transfer is not a licence review |
| `Breakfast` (description text) | `unknown` | OK (harmless) |
| `Lamb Korma, raita, Masoor Dal, ...` | `unknown` | OK |
| `Taken from Google image search` | `scrape_risk` | correct |

The false positive is material: `_STRONG_PROVENANCE`
(`licence_policy.py:57-61`) matches `transferred from` and `verified by`, so a
routine en.wikipedia→Commons transfer would be reported as having had an
"independent licence review". That is an over-claim about provenance — precisely
what the project's standing constraints forbid.

Two further measured facts that constrain the fix:

- Real Flickr imports carry **`Credit` = the photo description** and **no
  `Permission` key at all** (`File:Breakfast (6090558570).jpg` →
  `Credit: "Breakfast\n\nUploaded by Perumalism"`, no `Permission`). So the
  fields are unreliable as provenance signals, and `missing_permission` will fire
  on most Flickr-derived files.
- The genuine "licence reviewed by a bot" marker lives in **`Permission`**, not
  `Credit`. Reproduced by fetching `Permission|Credit` for three real files: only
  the en.wikipedia transfer produced a `Credit`; no file produced a `Permission`
  at all.

---

## 4. Additional problems discovered

**4.1 Authorless CC BY-SA is never rejected (latent).**
`classify_rights` checks the author only inside the `_APPROVED_CLASSES` branch
(line 115). CC BY-SA goes to the `_REVIEW_CLASSES` branch (126–131) with **no
author check**, even though CC BY-SA carries the same attribution obligation:

```
CC_BY_SA  no artist -> REVIEW_REQUIRED
CC_BY     no artist -> EXCLUDED
CC0_PD    no artist -> EXCLUDED
```

Today this is **masked**: those files sit at `REVIEW_REQUIRED`, and
`prepare_v2_dataset.py` adds `cc_by_sa_held_out`, so they never reach count 6.
It becomes live the moment anything passes `--include-cc-by-sa` with real bytes.
Verified: with `include_cc_by_sa=True` the only exclusion reason on such a record
is `bytes_missing` — nothing checks the missing author. This should be fixed in
the same change, or the CC BY-SA decision will import an attribution gap.

**4.2 `source.extmetadata_filter` records a filter that was never applied.**
See §2.2(1). A manifest field that misdescribes the query is a provenance-integrity
problem, not just a cosmetic one.

**4.3 Metadata gaps do not affect the rights tier.**
`missing_permission` is recorded per file but never consulted. Given that
`Permission` is the only field carrying a real review signal, this is where the
information should eventually flow.

**4.4 `attribution_required` is collected and echoed but never used for a decision.**
Line 92 reads it, line 145 returns it, and nothing branches on it. That is the
direct cause of Issue 1.

---

## 5. Test coverage: what exists, what is missing

Current state: **463 passed**; the 17 rights/provenance tests pass, and they pass
*despite* both bugs because they call `classify_rights()` directly.

| Required case | Status |
|---|---|
| CC0 with no artist | **Missing** |
| Public Domain with no artist | **Missing** |
| CC BY with no artist | Covered (`test_cc_by_without_author_is_excluded`) |
| CC BY with an artist | Covered |
| CC BY-SA classification | Covered |
| NC and ND exclusion | Covered (parametrised) |
| Missing and unrecognised licences | Covered |
| Provenance text with scraping indicators | Covered — **only via direct call** |
| Provenance text indicating independent review | Covered — **only via direct call** |
| Empty / unavailable provenance metadata | **Missing** |
| **End-to-end metadata flow: Commons record → `enrich()` → `classify_rights()`** | **Missing — this is the gap that hid Issue 2** |

Also missing: CC0-vs-PD distinction; `attribution_required=false` on CC0;
authorless CC BY-SA; the en.wikipedia "transferred from" false positive.

Recommended tests (to be added with the fix, not now):

1. `enrich()` forwards `Credit`/`Permission` — build a record carrying a scrape
   Credit, run `enrich()`, assert `rights_tier == EXCLUDED`. This single test
   would have caught Issue 2.
2. `enrich()` on a record with no `Credit`/`Permission` yields
   `provenance_strength == "unknown"` and does not exclude.
3. CC0 (`short_name="CC0"`) with no artist → `TRAINING_APPROVED`.
4. Public Domain with no artist → decision recorded per §6.2.
5. CC0 vs PD produce distinguishable outcomes or a recorded sub-type.
6. CC BY with no artist → still `EXCLUDED` (must remain unchanged).
7. `"Transferred from en.wikipedia..."` is **not** `external_review`.

---

## 6. Recommended minimal fixes (for approval — not applied)

### 6.1 Issue 1: author requirement only where attribution is actually required

Keep the CC BY guard exactly as-is. Introduce a positive predicate for the
no-attribution case, driven by `short_name` rather than by the merged bucket or
the unreliable flag:

```python
# licence_policy.py, replacing lines 114-124
_SHORT_CC0 = re.compile(r"^\s*cc0\b|cc[- ]?zero", re.IGNORECASE)
_SHORT_PD  = re.compile(r"public domain|^\s*pd[- ]|no known copyright", re.IGNORECASE)

declared = ...
is_cc0 = bool(_SHORT_CC0.search(short))    # short = licence["short_name"]
is_pd  = bool(_SHORT_PD.search(short))
needs_attribution = declared == "CC_BY" or (declared == "CC0_PD" and not (is_cc0 or is_pd))
```

- **CC0** → never requires an author; `attribution_required` is echoed, not relied on.
- **Public Domain** → decide explicitly (§6.2), do not inherit CC0's rule by accident.
- **CC BY** → unchanged, still requires an author.

Rationale for keying on `short_name`: it is the only field that still separates
CC0 from PD after `commons_audit` merges them, and it comes straight from
Commons' own `LicenseShortName`.

### 6.2 Decision needed: should anonymous Public Domain be approved?

Not a bug to fix silently — a policy call for you. Two defensible options:

- **(A) Approve anonymous PD.** Rationale: PD imposes no attribution condition.
  Cost: `ATTRIBUTIONS.md` would show `unknown` for those rows, so any
  redistribution listing has a hole. Today's renderer already prints `unknown`
  (verified), so the mechanism exists.
- **(B) Keep PD requiring an author, exempt only CC0.** Rationale: PD has many
  incompatible provenances (`PD-USGov`, `PD-old-100`, `PD-India`), and recording
  *why* something is PD is more defensible than trusting the string. Lower blast
  radius, still fixes the measured 6/10 loss for the CC0 subset.

Recommendation: **(A) for CC0 unconditionally; (B) for PD until each PD template
is reviewed.** It fixes most of the measured loss without touching the riskiest
class of records.

### 6.3 Issue 2: plumb provenance through `enrich()`

```python
# collect_v2.enrich()
rights = classify_rights(
    licence,
    artist=(record.get("attribution") or {}).get("artist_raw", ""),
    permission_text=record.get("permission") or "",
    credit_text=(record.get("attribution") or {}).get("credit") or "",
)
```

Necessary but **not sufficient**. Also required:

1. **Tighten `_STRONG_PROVENANCE`** to stop matching wiki transfers. Remove
   `transferred from`; anchor on the review bots, e.g.
   `flickr (upload|review) bot`, `confirmed to be (licensed|free)`,
   `reviewed by .*bot`.
2. **Prefer `Permission` over `Credit` for review signals.** `Credit` is
   description text in practice. Consider passing them to distinct code paths
   rather than concatenating (`licence_policy.py:95`), so a scrape note in
   `Credit` and a review note in `Permission` cannot mask each other.
3. **Fix the misleading manifest field**: either actually send
   `iiextmetadatafilter` (including `Credit|Permission`) or rename
   `source.extmetadata_filter` to make clear no filtering occurred.
4. **Add the end-to-end `enrich()` tests** from §5.

Until (1) is fixed, plumbing the fields through would replace a fail-safe no-op
with an over-claiming classifier. **(1) must ship with (3).**

### 6.4 Authorless CC BY-SA

Add the author check to the `_REVIEW_CLASSES` branch, or apply it uniformly after
tiering as an orthogonal `attribution_incomplete` flag. Preferred: keep tiering
and attribution separate, and let `prepare_v2_dataset.py` treat
`attribution_incomplete` as an exclusion when `--include-cc-by-sa` is used.

---

## 7. Risks of changing the classification rules

| Risk | Mitigation |
|---|---|
| Authorless **CC BY** accidentally approved | Keep CC BY on the author path; §5 test 6 asserts it stays `EXCLUDED` |
| `AttributionRequired=false` used as a blanket exemption | Do not gate on the flag (it is uploader-maintained and wrong for CC BY 0/1.0); gate on positive licence identification |
| `CC0_PD` merge causes PD templates to inherit CC0's exemption | Key on `short_name`; decide PD explicitly (§6.2) |
| Provenance plumbing creates false `external_review` | Tighten `_STRONG_PROVENANCE` in the same change (§6.3.1) |
| Provenance plumbing starts excluding real files | Expected and correct, but will **lower counts**. Do not treat the drop as a regression; do not relax the rule to recover the numbers |
| Approving anonymous PD leaves attribution rows "unknown" | Accept, or choose option (B); never fill the gap with a guessed author |
| CC BY-SA count changes if authors are enforced | Will reduce `--include-cc-by-sa` usable counts; correct per §4.1 |

**Counts will go down for some classes and up for others.** Per the standing
constraint, no licence or provenance requirement may be weakened to protect a
count.

## 8. Constraints honoured during this investigation

- No production code modified; working tree clean.
- 12-class fallback model untouched (hash verified identical).
- Biryani pilot and all human review decisions untouched.
- No licence or provenance requirement weakened anywhere.
- No legal clearance claimed; every record still carries
  `legal_clearance: not_verified`.
- PR #8 left open and unmerged; no new PR created, no commit made.

## 9. Reproducing this investigation

The probes are reproducible from the repository with no network access (except
where noted). Run with the training venv
(`pip install -r requirements.txt -r requirements-training.txt`):

```bash
# Issue 1: author requirement applied to CC0/PD
python - <<'PY'
import sys; sys.path.insert(0,'.'); sys.path.insert(0,'training')
from commons_audit import build_file_record
from licence_policy import classify_rights
for lic, artist in [("CC0","A"),("CC0",None),("Public domain",None),("CC BY 4.0",None)]:
    ext={"LicenseShortName":{"value":lic}}
    if artist: ext["Artist"]={"value":artist}
    p={"pageid":1,"title":"File:X.jpg","imageinfo":[{"sha1":"s","width":9,"height":9,
        "mime":"image/jpeg","url":"u","descriptionurl":"d","extmetadata":ext}]}
    r=build_file_record("File:X.jpg",p,[],[])
    print(lic, bool(artist), classify_rights(r["licence"],artist=artist or "")["rights_tier"])
PY

# Issue 2: scrape Credit captured but never forwarded
python - <<'PY'
import sys; sys.path.insert(0,'.'); sys.path.insert(0,'training')
from commons_audit import build_file_record
from collect_v2 import enrich
ext={"LicenseShortName":{"value":"CC0"},"Artist":{"value":"A"},
     "Credit":{"value":"Taken from Google image search"},"Permission":{"value":"Google"}}
p={"pageid":1,"title":"File:X.jpg","imageinfo":[{"sha1":"s","width":900,"height":900,
    "mime":"image/jpeg","url":"u","descriptionurl":"d","extmetadata":ext}]}
rec=build_file_record("File:X.jpg",p,[],[])
print("captured:",repr(rec["attribution"]["credit"]),repr(rec["permission"]))
print("forwarded:",enrich(rec)["rights"]["provenance_strength"])   # 'unknown'
PY
```

Live-API facts in §3 were captured via the MediaWiki action API
(`action=query&prop=imageinfo&iiprop=extmetadata&iiextmetadatafilter=Permission|Credit`)
on `File:Chickenbiryani.JPG`, `File:Mutton Biryani.jpg`,
`File:Roti - Massachusetts.jpg`, `File:Breakfast (6090558570).jpg`,
`File:Breakfast South India.jpg`.

---

**Awaiting approval before implementing any fix.** The recommended order is:
§6.3.1 (`_STRONG_PROVENANCE` tightening) and §6.3.3 (manifest field) together
with §6.3 plumbing; then §6.1/§6.2 pending your decision on anonymous Public
Domain; then §6.4. Each with the §5 tests.

---

# Resolution (implemented after approval)

Both issues were fixed on this branch. Summary of what changed and what was
learned during implementation that the investigation could not have known.

## Final licence rules

| Licence | Author required? | Tier | Rationale |
|---|---|---|---|
| **CC0** (`short_name` matches CC0 / CC0 1.0 / CC-Zero) | **No** | `TRAINING_APPROVED` | CC0 waives attribution, so an author name is not a condition of use |
| **Public Domain**, any designation | n/a | `REVIEW_REQUIRED` | Deferred. Not equivalent to CC0 |
| **CC BY** (all versions) | **Yes** | `TRAINING_APPROVED` only with an author; otherwise `EXCLUDED` | Attribution is a licence condition |
| **CC BY-SA** (all versions) | **Yes** | `REVIEW_REQUIRED` with an author; `EXCLUDED` without | Share-alike hold retained; the author gap is no longer bypassable |
| NC / ND / other / unknown | n/a | `EXCLUDED` | Unchanged |

`attribution_required` is still never used as an exemption: it is
uploader-maintained and wrong for some CC BY 0/1.0-era files.

### Public Domain designations

**None are accepted.** Each named family is deferred with its own stable key and
reason, most-specific first:

| Designation | Key |
|---|---|
| `PD-USGov` | `pd_usgov` |
| `PD-Art` | `pd_art` |
| `PD-scan` | `pd_scan` |
| `PD-old-*` | `pd_old` |
| `PD-India` | `pd_india` |
| `PD-self` | `pd_self` |
| `No known copyright restrictions` | `no_known_copyright` |
| `Public domain` | `public_domain_generic` |
| any other `PD-…` | `pd_other_template` |
| unrecognised PD wording | `pd_unrecognised` |

Why none are accepted: each asserts a *different reason* the work is out of
copyright (a government publication, an expired term, a non-US jurisdiction, a
donor agreement). Verified from captured data that **no PD record exists in the
corpus at all** — the Biryani manifest is 89 CC BY-SA, 2 CC BY, 2 CC0, and the
V4 fixture contains zero PD entries. Accepting any template would have been a
guess with no supporting evidence. A bare `CC0_PD` bucket entry with no
`short_name` or `usage_terms` fails closed (`EXCLUDED`).

## Final provenance rules

`classify_provenance()` now separates six distinct strengths, which is what the
investigation asked for but the original single regex could not express:

| Strength | Meaning |
|---|---|
| `scrape_risk` | Scraped / re-hosted source. Disqualifies regardless of licence |
| `independent_review` | A licence-review bot confirmation (in `Permission`, or asserted in `Credit`) |
| `permission_asserted` | An explicit release or permission statement |
| `attribution_only` | Describes who to credit ("Own work", Flickr description) |
| `transfer_only` | Wiki housekeeping ("Transferred from en.wikipedia"). **Never a review** |
| `unknown` | Empty, absent, or uninformative |

`Permission` outranks `Credit`. A review claimed only in `Credit` is recorded as
a `credit_review_claim` signal but is **not** promoted to `independent_review`.
Nothing is ever promoted to "verified": `verification` stays `declared_only` and
`legal_clearance` stays `not_verified` in every case.

### Things the investigation could not have known

1. **The API filter was never the cause of missing provenance, and adding one
   was still necessary.** `iiextmetadatafilter` was never sent, so the API
   returned everything. The fix sends the filter explicitly *and* derives the
   manifest field from the same constant, so request and manifest cannot drift.

2. **`Permission` is usually absent even when a review exists.** Verified against
   `File:Ravi Shankar, Somers Town, London (4072820079).jpg`, whose wikitext
   contains `{{flickrreview|File Upload Bot (Magnus Manske)|2013-01-28}}` yet
   whose extmetadata returns **no `Permission` key at all**, only `Credit` and
   `Artist`. `insource:"PermissionOTRS"` returned 0 hits for `Category:Curry`.
   So `independent_review` will fire rarely in practice, and the pipeline must
   never *assume* review because a file looks like a Flickr import.

3. **`transfer_only` was a real false-positive risk that is now a correct
   classification**, not merely suppressed. Matching `transferred from` as
   "independent review" would have been an over-claim.

4. **The authorless CC BY-SA gap was reachable in practice**, not merely
   theoretical: with `--include-cc-by-sa` the only exclusion left was
   `bytes_missing`. `prepare_v2_dataset.py` now also checks
   `attribution_sufficient`, so lifting the share-alike hold cannot lift the
   attribution requirement.

## Test coverage added

`tests/test_licence_provenance_fixes.py` — **88 tests**, including the
integration tests the old suite lacked. The decisive one builds a record through
`build_file_record` → `enrich` and asserts a scrape-risk `Credit` yields
`EXCLUDED`; that single test fails on the pre-fix code. A `_RecordingTransport`
double asserts the actual outgoing `iiextmetadatafilter` matches the constant
recorded in the manifest.

Three pre-existing tests were updated because they asserted the old behaviour
(bare `{"declared_class": "CC0_PD"}` with no licence text, and the old
`external_review` strength name). CC BY's author requirement test was **left
unchanged** as the regression guard.

## Known limitations

- **Counts fell slightly and should have.** Anon PD files previously counted as
  rights-supported are now deferred, and scrape-risk files are now excluded. No
  requirement was relaxed anywhere.
- **`independent_review` is rare** because Commons does not expose review
  templates in extmetadata (see above). This is a data-source limitation.
- **PD remains untested against real records** because none exist in the corpus.
  The deferral is correct but has never been exercised on genuine PD metadata.
- `Credit`-field review claims remain unverifiable by construction.

---

# Post-review corrections (NB-1 … NB-5)

Applied after the independent review in `docs/V2_COMMIT_747AA0D_REVIEW.md`.

## NB-1 — scraping detection

Layer rules so a *mention* is never confused with *evidence of copying*:

| Layer | Example | Detected alone? |
|---|---|---|
| Unambiguous scrape vocabulary | `scraped`, `clip art`, `hotlinked`, `re-uploaded` | Yes |
| Copy verb | `copied from`, `downloaded from`, `screenshot from a video` | Yes |
| Search engine named | `from Google`, bare `Bing`, `google.com/search?q=` | **Yes** — no licensed original comes "from Google" |
| Social platform named | `Flickr`, `Instagram`, `via Yahoo` | **No** — a host is not proof of copying |

Platform mentions are surfaced by `platform_mentions()` for auditing only and
never change the tier. `wallpaper` was removed from the pattern (it
false-positived on "wallpaper paste texture"), and `unknown source` is now
anchored so "unknown source of the spice" is not flagged.

Restored `Bing` detection lost in the previous commit. Restored
`found on the internet`, which the previous rewrite had dropped.

## NB-2 — provenance is not a confidence ladder

Documented in the module docstring as five **separate** decisions:
licence-policy eligibility, provenance classification, human visual approval,
technical validity, and final `training_usable`. Provenance is audit information:
except for `scrape_risk` it does not change `rights_tier`, and `unknown` is no
worse than `independent_review` for eligibility. `unknown` never implies verified;
`independent_review` never establishes permission.

`training_approved` is retained (renaming would touch downstream manifests) with
an inline note pinning its meaning to "the declared licence policy permits
training use" — not human or technical approval.

## NB-3 — licence echoes rejected

`Permission = "CC BY-SA 2.0"` is now recognised as a licence echo
(`is_licence_label_only`) and classified `unknown` with a
`permission_licence_echo` signal, instead of `permission_asserted`. Only genuine
grant language counts (`permission granted`, `used with permission`,
`released to the public domain`, `licensed for reuse`). The original field value
is preserved in the record for audit.

## NB-4 — malformed metadata

`_coerce_text()` in `licence_policy` and a hardened `strip_markup`/`em` in
`commons_audit` reject non-scalar values instead of stringifying them. This
closed a real hole found during implementation: a list author was rendered as
`"['A', 'B']"`, which passed as a valid attribution and made an authorless CC BY
file **TRAINING_APPROVED**. It now yields `""` and the file is `EXCLUDED`.

`enrich()` also type-checks `licence`/`attribution` and pixel dimensions
(booleans and strings are not pixel counts), flagging `malformed_record`. A single
malformed file is excluded rather than aborting the class.

## NB-5 — dead constant removed

`_APPROVED_CLASSES` deleted, with a comment recording that coupling CC0/PD with
CC BY in one set is what caused the original author-requirement bug. A test
asserts it is not reintroduced.
