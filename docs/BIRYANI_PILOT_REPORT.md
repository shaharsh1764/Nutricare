# Biryani pilot — real Wikimedia Commons metadata validation

**Date:** 2026-11-05
**Class:** `biryani` (the single largest class in the V3 taxonomy)
**Status:** Real metadata retrieved and analysed. **No image downloaded, no model
trained, nothing marked training-ready or legally cleared.**

---

## 1. How real data was obtained (and why the sandbox could not)

### Sandbox access: still blocked

```
$ curl https://commons.wikimedia.org/w/api.php
curl: (35)  →  OpenSSL SSL_connect: SSL_ERROR_SYSCALL
```

DNS resolves, TCP connects, TLS dies at Client Hello. Unchanged from the previous
phase; I retried **once** for confirmation and did not repeat it.

### The route that works

The **documented MediaWiki action API** was reachable through the environment's
out-of-sandbox HTTP fetch facility. No proxy bypass, no credential, no scraping —
just the same public API endpoint, called through a different egress path.

**This is real Commons data.** It is not a mock, not a fixture, and not
synthesised. Every row was transcribed from a live API response whose
`_provenance` block records the exact query string, and every row carries a
`pageid` plus `sha1` so any figure below can be independently re-verified at
`https://commons.wikimedia.org/wiki/File:<title>`.

### Limitations of this route (stated plainly)

| Limitation | Consequence |
|---|---|
| One response at a time, no scripting | Fetching all ~813 direct file-slots would exceed this session's context budget |
| Payload is returned to the model, not to disk | Transcription is manual; transcription error is possible |
| `Permission` field returns large boilerplate | Excluded from most queries to control size; recorded as a coverage gap |
| `iiprop=url` inflates payload ~5× | Original image URLs omitted for larger categories; `descriptionurl` is derivable and stored for every file |
| Not scriptable for the future | The `training/commons_audit.py` pipeline still requires real network access to run at scale |

**Consequence for coverage:** this pilot captures `Hyderabadi chicken biryani`
(23/23 files, complete) and `Mutton biryani` (70/70 files, complete). It does
**not** capture the full biryani tree. See §7.

---

## 2. Category census — measured

Every `direct_files` value below is the API's `categoryinfo.files`, measured
individually in this session. Stored machine-readably in
`data/v3/commons_pilot/category_census.json`.

### The three taxonomy roots

| Category | Page id | Direct files | Subcats |
|---|---|---|---|
| `Biryani` | 10954839 | **207** | 19 |
| `Chicken biryani` | 20191062 | **199** | 4 |
| `Hyderabadi biryani` | 40701595 | **62** | 4 |

Independent cross-check: the V3 research recorded 207 / 199 / 62 for these same
categories. **The two sessions agree** — the earlier figures are corroborated.

### Full depth-2 tree (28 categories enumerated)

Depth-1 subcategories of `Biryani` (19, all measured):
Aloo 2 · Beef 15 · Chatti 2 · Dan bauk 4 · Dum 33 · Egg 38 · Fish 10 · Kacchi 36 ·
Khao mok 8 · Lahori 4 · Matka 3 · Mushroom 8 · Mutton 70 · Prawn 8 · Turkey 1 ·
Vegetarian 5 · Biryani by location 0 · Biryani making 22 · **plus the two roots
above (Chicken 199, Hyderabadi 62)**.

Chicken biryani → Chicken Mandi in India 16, Hyderabadi chicken biryani 23,
Kolkata chicken biryani 15, Thalassery chicken biryani 4.
Hyderabadi biryani → Hyderabadi biryani overseas 7, Hyderabadi mutton biryani 10,
Videos of Hyderabadi biryani 1, Hyderabadi chicken biryani 23.

| Rollup | Value |
|---|---|
| Categories enumerated | 28 |
| Sum of direct file counts (all 28) | **813** |
| — depth 0 (`Biryani` alone) | 207 |
| — depth 1 | 530 |
| — depth 2 | 76 |
| Categories with 0 direct files | 1 (`Biryani by location`, 2 subcats) |
| Categories that have subcats | 8 |

**813 is a sum of overlapping category-file counts, not a count of unique
images.** It is an upper bound on file *slots*, and a lower bound on what a
deeper traversal would find.

---

## 3. Files actually audited — measured

| Metric | Value |
|---|---|
| Categories captured per-file | 2 |
| Raw rows across captured categories | 93 |
| **Unique Commons files** | **93** |
| Unique page ids | 93 |
| Unique SHA1 values | 93 |
| Files in more than one captured category | **0** |
| Exact-SHA1 duplicate groups | **0** |
| Exact-SHA1 duplicate files | 0 |
| Duplicate normalised-title groups | 0 |

Captured: `Hyderabadi chicken biryani` (23 files, 23/23 complete) and
`Mutton biryani` (70 files, 70/70 complete).

**Interpretation, carefully:** zero multi-category files and zero SHA1 duplicates
is a fact about *this 93-file sample only*. It does **not** show that the biryani
tree has no duplicates. The categories captured are disjoint by construction
(a mutton dish vs a Hyderabadi chicken dish), so overlap would be surprising.
Whether `Hyderabadi chicken biryani` files also appear in `Chicken biryani` and
`Hyderabadi biryani` — which the tree structure makes very likely — **cannot be
determined without capturing those categories**. That is the single most
important unmeasured question, because it directly affects the raw-vs-unique gap
of 813.

---

## 4. Licence audit — declared only

| Declared class | Files | Share |
|---|---|---|
| `CC_BY_SA` | **89** | 95.7% |
| `CC_BY` | 2 | 2.2% |
| `CC0_PD` | 2 | 2.2% |
| `NC_RESTRICTED` | 0 | — |
| `ND_RESTRICTED` | 0 | — |
| `UNKNOWN_MISSING` | 0 | — |
| `OTHER_REVIEW` | 0 | — |
| **Preliminarily acceptable** | **93** | 100% |
| **Unknown or unsuitable** | **0** | 0% |

Metadata gaps across the 93 files: **none**. Every file carries a SHA1,
dimensions, a licence string, and an artist.

### What this table does and does not mean

**It does not mean 93 images are licensed for our use.** It means 93 file pages
*declare* a licence that does not obviously forbid commercial reuse of the image.

- **`verification: declared_only`** on every record. An uploader's declaration is
  not proof of ownership; Commons has a noticeboard precisely because
  misattributions happen. **Verified rights ≠ declared licence**, and only the
  latter is measured here.
- **95.7% CC BY-SA is the headline risk.** Share-alike attaches to the *image*.
  Whether it reaches trained model weights is **legally unsettled and is not
  decided here** — it is flagged for human/legal review. It is also, in effect,
  a single-licence corpus: any change in that legal position affects almost every
  file at once, which is a concentration risk worth stating before building.
- **Attribution is an obligation, not a formality.** Every CC file here requires
  attribution; a distributable dataset must carry per-image artist + licence +
  source URL. That is straightforward to generate and is planned, not done.
- **Not legally cleared.** No part of this dataset should be described that way.

---

## 5. Count potential

Using the agreed planning bands on **unique candidates**:

| Basis | Count | Band |
|---|---|---|
| Unique files captured | 93 | `limited` (50–99) |
| With preliminarily acceptable licence | 93 | `limited` (50–99) |
| All 813 direct file-slots (upper bound, not unique) | 813 | *not a valid count* |

**Bands are planning thresholds, not readiness verdicts.** Nothing here is
training-ready: relevance, visual quality, near-duplicates and label correctness
have not been inspected, and no image bytes were ever downloaded.

A 93-file sample with 100% acceptable licence is **not** evidence that the
`biryani` class reaches the 200-image target. The 813 slot count suggests the
headroom exists; the sample neither confirms nor refutes it.

---

## 6. Corrections surfaced by real data

Two findings that a purely category-name-based audit would have missed:

1. **`Category:Biryani making` (22 files) is process photography, not the dish.**
   It sits inside `Category:Biryani` and would be swept up by a naive recursion.
   Its files must be reviewed for relevance, not counted as biryani.
2. **The `Mutton biryani` sample contains food that is not obviously biryani.**
   `Murgh Mussallam` (a whole roast chicken dish) and `Mutton Chanp` (mutton
   chops) are filed in `Mutton biryani` but are different preparations. Roughly
   2 of 70 files are questionable on name alone.

Root cause of both: **Commons category membership is a human act of curation, not
a label.** It is neither complete nor exclusive. This is the concrete
justification for keeping `usable_for_training: false` on every record rather
than promoting files on the strength of their licence and category.

The sample also shows heavy single-contributor concentration: `Miansari66` and
`Rameshng` appear repeatedly across the wider biryani tree. Many uploads are
one-person photography series rather than independent examples — a systematic
risk for a classifier that dedupe-by-SHA1 will not catch, since the images differ
in bytes while sharing subject, lighting and framing.

---

## 7. What is unmeasured (and must not be inferred)

- **The remaining ~720 direct file-slots** across the biryani tree were not
  fetched. `Biryani` (207 files) alone is ~13 response chunks.
- **Deeper descendants** — subcategories of `Biryani by location`,
  `Mutton biryani`, `Vegetarian biryani`, `Chicken Mandi in India` — were not
  enumerated. The tree is certainly larger than 28 categories.
- **Cross-category overlap** between `Hyderabadi chicken biryani` and its two
  parents — likely, unmeasured, and material to the raw-vs-unique gap.
- **`Permission` field content** for these files (boilerplate excluded from
  queries).
- **Image relevance, quality, framing, resolution adequacy.**
- **Perceptual / near-duplicate rate** — needs bytes.
- **Label correctness and class separability** (mutton vs chicken vs veg biryani).
- **Whether any file is legally cleared for redistribution.**

---

## 8. Measured / inferred / unknown

**Measured (real API data this session)**
- 3 taxonomy root counts: 207 / 199 / 62 — independently corroborating the V3
  research.
- 28-category depth-2 census; 813 direct file-slots; 8 categories with subcats.
- 93 unique files fully captured from 2 categories, all pageid- and SHA1-unique.
- Licence distribution 89 / 2 / 2 (CC BY-SA / CC BY / CC0); 0 NC, 0 ND, 0 unknown.
- 0 metadata gaps; 0 exact-SHA1 duplicates; 0 multi-category files *in this sample*.

**Inferred (plausible, unverified)**
- The biryani tree likely contains 400–700 unique files once overlap is removed —
  a guess from the 813 slot count, **not** a measurement.
- The ~95% CC BY-SA share is likely to hold across the rest of the tree, given
  the uploader overlap — an extrapolation from two categories.
- A meaningful minority of files will fail relevance review (`Biryani making` 22
  files plus ~2/70 in the mutton sample).

**Unknown**
- True unique-file count for the whole class.
- Whether `biryani` can reach 200 *usable* images.
- Perceptual duplicate rate.
- The legal position on CC BY-SA and model weights.

---

## 9. Reproducing this

```bash
# Rebuild the manifest and summary from the stored transcriptions (no network)
python3 training/build_biryani_pilot.py

# Outputs
#   data/v3/commons_pilot/biryani_manifest.json        93 records
#   data/v3/commons_pilot/biryani_pilot_summary.json   aggregates
#   data/v3/commons_pilot/category_census.json         28-category census
#   data/v3/commons_pilot/raw/*.json                   verbatim API transcriptions

# Re-verify any single file, without this tool:
#   https://commons.wikimedia.org/wiki/File:<title>
# Match on pageid and sha1 recorded in the manifest.
```

To complete the pilot once `commons.wikimedia.org` is allowlisted, run the full
auditor — it already handles pagination, dedupe and licence classification:

```bash
python training/commons_audit.py \
    --taxonomy data/v3/taxonomy_100_proposed.json \
    --only-class biryani --depth 3 \
    --delay 1.0 --out data/v3/commons_audit/biryani
```

**Do not extrapolate from this pilot to all 100 classes.** It covers one class,
two categories, and 93 files. Its main value is negative and methodological: it
proved that category membership is not a label, that a 100%-acceptable licence
sample can still be a single-licence corpus, and that real measurement is
possible the moment egress is opened.
