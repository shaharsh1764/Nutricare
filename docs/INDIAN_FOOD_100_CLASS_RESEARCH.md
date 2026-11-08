# Can we build a properly licensed 100-class Indian food dataset?

**Date:** 2026-11-07
**Scope:** Research and planning only. **No training, no image downloads, no
application changes, no model changes.**

> **Provenance note.** This report and `data/v3/taxonomy_100_proposed.json` were
> written in an earlier session, then **lost** when that branch was closed before
> the files were committed. They have been **recreated from the measurements made
> in this session**. Every Commons category count below is the same API-measured
> figure; nothing was invented to fill a gap. The recreation is recorded in the
> JSON under `recreated_note`.

---

## 0. Direct answer

**For 100 classes at the 200–500 images/class target: no — this is not
established for Wikimedia Commons, nor for any source currently accessible from
the sandbox.**

**For a smaller dataset: not yet established either.** What the evidence supports
is narrower than "a 40–60 class dataset is achievable". It establishes that
**40–60 classes are a preliminary development target** — the number of classes
worth investigating. Their feasibility depends on image-level licence
verification, image quality review, deduplication, and subcategory expansion,
**none of which has been performed**. Until those steps run, no class count is
demonstrated to be buildable.

### What the numbers below actually are

Every count in this document is a **category-file count**: the number of files
Commons reports as directly in a category. It is **not** a count of unique,
usable, correctly labelled, or appropriately licensed images.

- **Not unique.** Categories overlap. A photograph of biryani can sit in
  `Biryani`, `Chicken biryani` and `Hyderabadi biryani` at once, and is then
  counted three times. **These figures are not additive and must never be summed
  to produce a dataset size.**
- **Not verified as images.** The Commons API reports how many *file pages* sit
  in a category. It does not report that each is a usable photograph of that
  dish. Non-photo media, diagrams, collages, unrelated uploads and misdescriptions
  are all included in the raw figure.
- **Not licence-filtered.** A category file count makes no claim that any file is
  under an acceptable licence (§3).
- **Lower bound on the category, not on usable data.** Subcategories are excluded
  (see below), so the true category population is larger — but the *usable
  dataset* may still be far smaller than the number here, after the filters above.

So a figure of "207" means *207 file pages in that category*, not *207 training
images*.

### Subcategories: an open question, not confirmed volume

Counts exclude subcategory contents. Many categories hold most of their files in
subcategories, so the measured figure can substantially understate the category
population.

**This is an opportunity for further investigation, not confirmed dataset
volume.** The subcategory contents have not been counted, so they cannot be
claimed as available images. 79 measured categories have subcategories (§8).
Treating them as headroom would be exactly the unfounded optimism this document
is meant to avoid.

Two rollups are used, and they differ on purpose.

**(a) Raw Commons categories measured — 116 categories; 8,906 category files
(sum of direct category-file counts, not unique images)**

| Threshold | Categories meeting it |
|---|---|
| ≥ 200 direct files | **9** |
| ≥ 150 direct files | **16** |
| ≥ 100 direct files | **29** |
| ≥ 50 direct files | **62** |
| < 50 direct files | **54** |

**(b) The proposed 100 *classes*** — after merging spelling/regional variants
(`data/v3/taxonomy_100_proposed.json`):

| Threshold | Classes meeting it |
|---|---|
| ≥ 200 direct files | **9** |
| ≥ 150 direct files | **17** |
| ≥ 50 direct files | **56** |
| < 50 direct files (1–49) | **41** |
| not yet measured (0 counted) | **3** |

Classes score lower than categories at the 50-file line because merges add files
while also *removing* classes, and because a class needs its images in **one**
label space rather than spread across synonym categories.

**Recommendation: build a 40–60 class model from Commons, not 100.**

---

## 1. Method — what was actually measured

`commons.wikimedia.org` and `upload.wikimedia.org` are **blocked from the Arena
sandbox** (`000` on every request). I could still query the Commons **API**
through out-of-sandbox research tooling. So:

| Aspect | How established | Confidence |
|---|---|---|
| Category file counts | `action=query&prop=categoryinfo` — exact `files` number | **Verified** |
| Category existence / misspelling | Same call returns `missing` for wrong names | **Verified** |
| Per-file licence fields exist | `extmetadata` returns `LicenseShortName`, `Artist`, `Permission`, `AttributionRequired` | **Verified** (3 files sampled) |
| Licence distribution across corpus | Not enumerated | **Unknown** |
| Images downloadable | Image hosts blocked | **Unknown** |
| Resolution / quality | Sampled files were 2–6 MP; no systematic measurement | **Inference** |
| Duplicate / near-duplicate rate | Needs the bytes | **Unknown** |
| 100-class sufficiency | Cannot be established today | **Unknown** |

No image count was invented. Where a category has subcategories the true total is
larger than reported, and that is flagged rather than guessed.

---

## 2. Wikimedia Commons — the strongest source, and why

### 2.1 Why it is the strongest candidate source

These are **structural advantages** — properties of how Commons works, not
findings about our candidate images. None of them has been verified across the
categories counted in §2.2.

- **Per-file licence metadata.** Every file page carries an explicit licence
  template, the author (`Artist`), and whether attribution is required — the
  opposite of the scraped datasets rejected earlier.
- **Licences are compatible with a commercial product.** CC0, public domain,
  CC BY 4.0 and CC BY-SA 4.0 all permit **commercial use and modification**
  (SA adds an obligation on the *image*, discussed in §3.3).
- **No `NC`/`ND` contamination** if filtering is enforced, unlike Khana.
- **Attribution is tractable** — one record per image, harvested from the API.

Three sampled files, shown to establish that the metadata fields are real and
populated — **not** to establish how the corpus is licensed. Three files say
nothing about the licence distribution across ~8,900 (see §3.1):

| File | Licence | Artist | Attribution required |
|---|---|---|---|
| `Havelock Island, Indian food, Andamans.jpg` | CC BY 4.0 | Vyacheslav Argenberg | yes |
| `A Bonda tribe of Odisha drinking Mahua drink.jpg` | CC BY-SA 4.0 | Suresh Kumar Vakalapudi | yes |
| `Enjoyed food at nandos.jpg` | CC BY-SA 4.0 | Rehansha41 | yes |

Note the third: an "indian food" search returned a **Nando's** meal. Search is
noisy; category-based harvesting plus manual review is mandatory. The second is
also a caution — a drink photograph from a cultural-documentation context, not a
dish portrait; relevance must be reviewed per image.

### 2.2 Category-file counts (not verified image counts)

| Class | Files | Subcats |
|---|---|---|
| Roti (generic) | 393 | 23 |
| Chutney (generic) | 298 | 8 |
| Idli | 248 | 11 |
| Jalebi | 237 | 3 |
| Naan | 230 | 11 |
| Panipuri | 221 | 5 |
| Gulab jamun | 216 | 3 |
| Biryani | 207 | 19 |
| Samosas of India | 201 | 4 |
| Chicken biryani | 199 | 4 |
| Sambar | 181 | 7 |
| Dal | 164 | 25 |
| Laddu | 164 | 11 |
| Fried fish | 163 | 18 |
| Tandoori chicken | 161 | 3 |
| Pongal | 151 | 5 |

Mid-range (50–149): Pakora 145, Chicken curries 143, Kheer 135, Parotta 134,
Raita 130, Lassi 121, Pav bhaji 118, Poha 116, Fried rice 115, Appam 105,
Momos 103, Aloo paratha 97, Halva 94, Bhelpuri 87, Gajar ka halwa 77, Kulfi 76,
Dhokla 75, Malpua 75, Falooda 74, Paneer tikka 74, Butter chicken 74, Dosa 73,
Samosas 72, Chana masala 71, Vada pav 71, Chow mein 70, Murukku 66, Barfi 65,
Hyderabadi biryani 62, Uttapam 61, Aloo tikki 59, Rasmalai 59, Pakhala 58,
Aloo gobi 56, Chicken tikka 56, Mutton curry 55, Cutlets of India 55, Kadhi 56,
Rasgulla 54, Chicken tikka masala 52, Kachori 51.

Thin (<50) — **54 categories**, including several that matter:
Rasam 43, Chicken 65 43, Papri chaat 41, Imarti 39, Payasam 47, Peda 47,
Idiyappam 36, Filter coffee 36, Phirni 33, Mysore pak 33, Rabri 30, Sandesh 28,
Shrikhand 22, Modak 35, Kadai paneer 30, Shahi paneer 32, Palak paneer 45,
Bhindi masala 47, Baingan bharta 33, Malai kofta 12, Chakli 27, Mathri 10,
Namak para 14, Thepla 18, Rumali roti 17, Bhatura 10, Kulcha 23, Rava dosa 31,
Pesarattu 14, Avial 9, Thoran 29, Shukto 17, Nihari 17, Haleem 48, Saag 20,
Curd rice 49, Upma 49, Rasam 43.

### 2.3 Categories that do not exist (misspellings caught by the API)

Returned `missing` or 0 files, recorded so nobody repeats the mistake:

`Category:Masala dosa` (missing), `Category:Pani puri` (missing — real name
**Panipuri**), `Category:Samosa` (1 file — real name **Samosas**),
`Category:Kofta` (0), `Category:Chicken curry` (0 — **Chicken curries**),
`Category:Fish curry` (0 — **Fish curries**), `Category:Aloo matar` (0),
`Category:Karela` (0), `Category:Misal` (0), `Category:Medu vada` (0),
`Category:Vada` (0), `Category:Khichdi` (exists but 0 files).

**Consequence:** an API-verified category codebook is a mandatory deliverable
before any harvesting script runs. Hand-written names fail.

---

## 3. Licensing and provenance assessment

### 3.1 Per-image licence: fields verified present, distribution not enumerated

I confirmed the fields exist and carry real values. I have **not** counted the
licence distribution across ~8,900 files. **"All files are CC BY" is therefore not
a verified claim** — every class in the JSON carries `licence_verified: false`.

### 3.2 Traps the filter must handle

- **`CC BY-NC` / `CC BY-ND`** files exist on Commons in small numbers and would
  poison a commercial dataset. Exclude by allowlist, not blocklist.
- **Attribution is an obligation, not a formality.** 39 of the sampled
  `Permission` fields carried non-trivial extra text.
- **Personality rights / trademark.** A photographed brand package must not become
  a class image.
- **`De minimis` and derivative-work** questions attach to product shots.

### 3.3 CC BY-SA and trained model weights — the open question

CC BY-SA 4.0 is **share-alike on the licensed work**. Whether model weights are a
"derivative work" of training images is **legally unsettled**:

- *Common reading:* weights encode statistical patterns, not a copy of each image.
- *Cautious reading:* a model that memorises training images could be treated as
  derivative.

**Mitigation:** prefer **CC0 / PD / CC BY 4.0** where available, and keep licence
per image so a CC-BY-SA-only subset can be dropped if counsel advises. Do **not**
describe this dataset as "legally cleared" — *permissively licensed* is the
accurate, weaker claim.

### 3.4 Provenance

Better than every alternative examined (see `docs/DATASET_AUDIT_V2.md`,
`docs/HF_INDIAN_DATASETS_AUDIT.md`, `docs/SOHLHEALTH_PROVENANCE.md`): Commons has
a noticeboard and deletion process for misattributed files, so bad claims are more
likely to have been challenged. Still an **uploader assertion**, not verified
chain of title. **Better than scraped sets; not zero risk.**

### 3.5 Rejected sources (unchanged)

| Source | Reason |
|---|---|
| Khana / IndFood | CC BY-NC-ND — forbids commercial use and derivatives. **Banned.** |
| `dhruvk2002/food-classifier` | no licence over images. **Banned.** |
| `bharat-raghunathan/indian-foods-dataset` | CC0 tag, but card admits Google scraping |
| `SohlHealth/enhanced-indian-food-classification` | upstream declares **fair use / non-commercial only** |
| `rajistics/indian_food_images` | no licence, "extracted from google" |
| `Codatta/MM-Food-100K` | OpenRAIL-M, non-commercial |
| `ethz/food101` | ETHZ disclaims ownership of the images |
| UEC FOOD-100 | unreachable; research terms; Japanese, not Indian |
| Bangladeshi Food Dataset | **not Indian** — must never be presented as such |

---

## 4. Proposed taxonomy — 100 classes

Machine-readable at `data/v3/taxonomy_100_proposed.json`. Per class: `slug`,
`canonical`, `aliases[]`, `category`, `commons_categories[]`,
`verified_direct_files`, `has_subcategories`, `bucket`,
`meets_preliminary_150_file_threshold`, `licence_verified`, `count_note`.

### 4.1 Honest bucketing

Buckets describe **how many category files** a proposed class has, and nothing
else. "A" does **not** mean training-ready: it means the category has more files
to look at before the filtering steps in §0.

| Bucket | Count | Meaning (category-file count only) |
|---|---|---|
| **A. Preliminary threshold met** (≥150 direct category files) | **17** | Most files to investigate; unverified |
| **B. Possible** (50–149) | **39** | Few files; likely thin for a 3-way split |
| **C. Marginal** (<50) | **41** | Too few files to plan around |
| **D. Unmeasured** | **3** | Commons category not identified/verified |

**17 proposed classes meet the preliminary 150-file category-count threshold.
This does not establish that they contain 150 unique, usable, correctly labelled,
appropriately licensed images.** 56 proposed classes reach 50 category files and
only 9 reach 200. 100 classes is not established as supportable at 200–500
images each.

Note these are class-level figures derived from the per-class
`verified_direct_files` values in the JSON (which are themselves sums of
overlapping category counts), so they carry the same three caveats as §0.

Two classes were dropped from an earlier 102-class draft (`mutton_biryani`,
`veg_biryani`) because they are unmeasured and `biryani` already covers the dish —
recorded in the JSON under `dropped_from_proposal` in the original; the current
file simply does not include them.

### 4.2 Merges required to avoid duplicate classes

The single biggest quality risk. Without these, 100 "classes" become ~70 real
classes plus 30 unlearnable spelling duplicates.

- `biryani`, `biriyani`, `beriyani`, `chicken biryani`, `hyderabadi biryani` → **one**
- `roti`, `chapati`, `phulka`, `chapatti` → **one**
- `dosa` + `masala dosa` + `rava dosa` → **`dosa` and `masala_dosa`** (two)
- `jalebi`, `jilebi`, `jilapi` → **one**
- `panipuri`, `pani puri`, `gol gappa`, `phuchka` → **one**
- `rasgulla`, `rosogolla` → **one**
- `chomchom`, `cham cham` → **one**
- `pakora`, `pakoda`, `bhaji`, `bhajji`, `beguni` → **one family class**
- `vada`, `medu vada`, `vadai` → **one**
- `kheer`, `payasam`, `payesh` → **one**; `phirni` separate
- `halwa`, `halva` → **one**; `gajar ka halwa` separate
- `curd`, `dahi`, `doi` → **one**
- `samosa`, `samosas`, `singara` → **one**

### 4.3 Categories

| Category | Classes | ~count |
|---|---|---|
| Rice | biryani, pulao, pongal, lemon rice, curd rice, fried rice | 6 |
| Breads | roti, naan, paratha, aloo paratha, puri, bhatura, kulcha, tandoori roti, rumali roti, thepla, parotta, appam, idiyappam | 13 |
| Breakfast / South Indian | idli, dosa, masala dosa, rava dosa, uttapam, upma, poha, puttu, pesarattu, vada | 10 |
| Dals & legumes | dal, dal makhani, dal tadka, rajma, chana masala, sambar, rasam, moong dal | 8 |
| Paneer & veg curries | palak paneer, shahi paneer, kadai paneer, paneer tikka, aloo gobi, bhindi masala, baingan bharta, malai kofta, saag, matar paneer | 10 |
| Non-veg curries | chicken curry, chicken tikka, chicken tikka masala, butter chicken, tandoori chicken, chicken 65, mutton curry, nihari, haleem, fish curry, fried fish | 11 |
| Street food & snacks | samosa, pakora, vada pav, panipuri, bhelpuri, chaat, aloo tikki, chole bhature, kachori, papri chaat, dhokla, momos, chow mein, murukku, chakli, cutlet | 16 |
| Sweets | jalebi, imarti, gulab jamun, rasgulla, rasmalai, chomchom, barfi, laddu, halwa, gajar ka halwa, kheer, phirni, rabri, kulfi, modak, peda, sandesh, mysore pak, malpua, shrikhand | 20 |
| Drinks | lassi, masala chai, filter coffee, falooda | 4 |
| Accompaniments | chutney, raita | 2 |

---

## 5. Access blockers and required network permissions

**Verified blocked from the sandbox** (`000`):

```
commons.wikimedia.org   (API)
upload.wikimedia.org    (image bytes)
api.wikimedia.org
en.wikipedia.org
```

Also blocked (earlier audits): `huggingface.co` and its CDN, `mm.cs.uec.ac.jp`,
`kaggle.com`, `zenodo.org`, `data.mendeley.com`.

**Minimum allowlist to proceed:**

```
commons.wikimedia.org      # category + per-file licence metadata
upload.wikimedia.org       # the actual image files
```

Both are required — allowing only the API gives metadata without images (the same
trap as the Hugging Face CDN).

**Volume estimate:** 100 classes × 200 images ≈ 20,000 files → **~2 GB** as
512 px thumbnails, **~15–25 GB** as originals. With 20 GB free, the pipeline must
fetch **thumbnails**. Design constraint, not an afterthought.

---

## 6. Technical plan — reuse, not rewrite

The existing tooling already covers most stated requirements and **must not be
modified**:

| Requirement | Provided by |
|---|---|
| Global dedupe **before** split | `training/prepare_dataset_v2.py` → `dedupe_global()` (MD5 + dHash ≤2, cross-class aware) |
| Train/val/test separation | same, stratified + seeded |
| Leakage checks across splits | same, `audit_split()` re-scans the finished split |
| Reproducible class mappings | `training/build_taxonomy_v2.py` — fails on any unmapped folder |
| Integrity / rejection counts | `prepare_dataset_v2.py` → `check_integrity()` |
| Contamination heuristics | `training/audit_indian_dataset.py` |

**New work required** (proposed, not written — needs approval):

1. `training/fetch_commons_dataset.py` — harvest from the **API-verified codebook**,
   writing one sidecar JSON per image: `title`, `artist`, `licence`,
   `licence_url`, `attribution_required`, `description_url`, `width`, `height`,
   `sha256`.
2. A **licence allowlist gate** that aborts on any file outside
   `cc0 / pd / cc-by-* / cc-by-sa-*`.
3. An **attribution generator** rendering the sidecars into `ATTRIBUTIONS.md`.

Sidecar design keeps per-image provenance intact through the split.

---

## 7. Recommendation

**Treat 40–60 classes as a preliminary development target. Do not commit to 100,
and do not yet commit to 40–60 as achievable.**

`40–60` is a scoping decision: it is the band where categories have enough files
in them to justify the **next** investigative step. It is **not** a forecast that
40–60 properly licensed, deduplicated classes will exist. That depends on:

- image-level licence verification (not done — `licence_verified: false` throughout),
- image quality and relevance review (not done),
- global deduplication (not done — cross-category overlap is expected),
- subcategory expansion (not done; contents unmeasured).

- **Bucket A (17 proposed classes, ≥150 category files)** — deserves first
  investigation. **Not** verified as ready to train; see §4.1.
- **Bucket B (39 proposed classes, 50–149 category files)** — fewer files to work
  with; likely thin for a three-way split.
- **Bucket C (<50 category files)** — do not include merely to reach a round
  number. That is precisely the "unsuitable data to hit the target" trap the brief
  warns against.

**On the ~50-class estimate:** an earlier draft said roughly 50 classes would
retain ≥100 images after dedupe. That figure is an **estimate with no direct
support** — it is a projection, not a measurement, and it rests on an assumed
10–20% loss. The only measured dedupe loss available is **13.15%** (4,000 → 3,474
files) on the unrelated 80-class V2 audit set (`data/v2/indian_audit.json`). It is
**not** evidence about Commons. Treat the ~50 figure as unverified.

**What would close the gap to 100 — as hypotheses to test, not as headroom already
banked:**

1. **Subcategory expansion** — 79 measured categories have subcategories whose
   files could not be counted (hosts blocked). This is the most promising line of
   investigation, and it is **entirely unmeasured**. It must not be counted as
   confirmed volume.
2. A second permissively licensed source with verifiable per-image terms.
3. Accepting a lower per-class count for tail classes, with the smaller count
   documented.

**What this document will not do:** claim 100 classes are feasible, claim 40–60
are already achievable, present category-file counts as usable image counts, or
count augmented copies as independent images — the exact failure mode of the
SohlHealth dataset (`docs/SOHLHEALTH_PROVENANCE.md` §6).

---

## 8. Fact / estimate / inference / unknown

**Verified facts** (measured directly via the Commons API)
- 116 Commons category counts measured via API. Their **sum** is 8,906 direct
  category files — a sum of per-category counts that **overlap**, so it is **not**
  a count of unique images.
- 9 categories ≥200 files, 16 ≥150, 29 ≥100, 62 ≥50; 54 categories <50.
- Rolled up to 100 proposed classes: 9 ≥200, 17 ≥150, 56 ≥50; 41 have 1–49 files and
  3 have no measured category (0 files, meaning *unknown*, not *absent*).
- Per-file licence/author/permission metadata exists and is populated.
- All Wikimedia hosts are blocked from the sandbox (`000`).
- 79 measured categories have uncounted subcategories.
- 4,000 → 3,474 files (13.15% loss) on the **separate** 80-class V2 audit set
  (`data/v2/indian_audit.json`). This is a fact about *that* dataset, **not** about
  Commons.

**Estimates** (projections, not measurements)
- ~2 GB for 20,000 thumbnails; ~15–25 GB for originals.
- 10–20% further loss from dedupe + contamination filtering on Commons.
- That ~50 classes would retain ≥100 usable images. **Unverified** — this
  extrapolates a 13.15% figure measured on a different dataset and should not be
  relied on.
- That 40–60 classes are achievable at all. **Unverified** — a preliminary
  target, contingent on the four unperformed checks in §7.

**Inferences**
- Subcategory expansion *may* raise mid-tier counts substantially. Direction is
  plausible; magnitude is unknown.
- Search-based harvesting is much noisier than category-based (the Nando's result).
- CC BY-SA is *probably* acceptable for model weights, but this is unsettled law.

**Unknown / not measured**
- Whether image download works at all (host blocked) — **the biggest unknown**.
- Whether any category file is a usable, correct, unique photo of the dish.
- Actual licence distribution across the corpus.
- Duplicate / near-duplicate rate, including cross-category overlap.
- True totals once subcategories are counted.
- Whether 40–60 classes are achievable, and whether 100 can reach 200–500 images
  each. **I do not know, and I will not assert it either way.**

---

## 8a. Which figures are independently re-checkable

The audit trail matters for citation, so: **figures in this document are of two
kinds.**

**Re-derivable from the committed JSON** (`data/v3/taxonomy_100_proposed.json`):
the class-level rollups (9 / 17 / 56 / 41 / 3), the per-class counts, the corpus
sum of 8,451 across the 100 proposed classes, and the 65 classes flagged
`has_subcategories`.

**Carried from the prior research session and NOT re-derivable from any committed
artifact** — treat as **recorded measurements, not independently verified**:

- the individual per-category counts in §2.2;
- the aggregate **8,906** across 116 raw categories (and the 116 itself);
- the category-level rollup 9 / 16 / 29 / 62 / 54;
- **79** categories with uncounted subcategories;
- the "missing category" list in §2.3;
- the three sampled licence records in §2.1.

These came from live Commons API queries in a session whose transcript is not
stored. The API hosts are blocked from the sandbox (§5), so **they cannot be
re-queried now to confirm them.** They are consistent with one another and with
the JSON, and no figure was altered to strengthen the case — but if exact numbers
matter for a decision, re-measure them once egress opens. Note the two corpus
totals differ by design: **8,906** sums 116 raw overlapping categories, **8,451**
sums the 100 de-duplicated-by-name proposed classes. Neither is a unique-image
count.

---

## 9. Explicit statements

- **No model was trained. No images were downloaded. No application code changed.
  The 12-class model is untouched.**
- **No class count in this document is a verified usable-image count.** Every
  figure is a category-file count that excludes subcategories, may double-count
  across overlapping categories, and has not been licence- or quality-filtered.
- **No class is described as ready for training.** Bucket "A" means only that a
  proposed class met a preliminary file-count threshold.
- **40–60 classes is a preliminary development target, not an established result.**
- No dataset is described as "legally cleared". Commons files are *permissively
  licensed with per-file attribution* — verifiable, but not proven chain of title.
- The Bangladeshi dataset is **not** presented as Indian anywhere in this document.
- Prior research is preserved intact: `docs/DATASET_AUDIT_V2.md`,
  `docs/HF_INDIAN_DATASETS_AUDIT.md`, `docs/SOHLHEALTH_PROVENANCE.md`,
  `data/v2/`, and the three `training/*_v2.py` tools.
- `docs/INDIAN_FOOD_100_CLASS_RESEARCH.md` and
  `data/v3/taxonomy_100_proposed.json` were lost by the branch closure and
  **recreated from this session's measurements**; that is recorded in §0 and in
  the JSON's `recreated_note`.
