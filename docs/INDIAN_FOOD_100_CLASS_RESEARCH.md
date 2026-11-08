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

**Yes for a smaller, genuinely licensed dataset. No for 100 classes at the
200–500 images/class target — not with Wikimedia Commons alone, and not within
reach of any source currently accessible from the sandbox.**

Every count below is **direct files in the Commons category only**, *excluding*
subcategories. So each figure is a **lower bound** — but also an **upper bound on
what could be downloaded today**, because the image hosts are blocked (§5).

Two rollups are used, and they differ on purpose.

**(a) Raw Commons categories measured — 116 categories, 8,906 direct files**

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
| < 50 direct files | **41** |
| not yet measured | **3** |

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

### 2.1 Why it is the right primary source

- **Per-file licence metadata.** Every file page carries an explicit licence
  template, the author (`Artist`), and whether attribution is required — the
  opposite of the scraped datasets rejected earlier.
- **Licences are compatible with a commercial product.** CC0, public domain,
  CC BY 4.0 and CC BY-SA 4.0 all permit **commercial use and modification**
  (SA adds an obligation on the *image*, discussed in §3.3).
- **No `NC`/`ND` contamination** if filtering is enforced, unlike Khana.
- **Attribution is tractable** — one record per image, harvested from the API.

Sampled proof (three real files via `extmetadata`):

| File | Licence | Artist | Attribution required |
|---|---|---|---|
| `Havelock Island, Indian food, Andamans.jpg` | CC BY 4.0 | Vyacheslav Argenberg | yes |
| `A Bonda tribe of Odisha drinking Mahua drink.jpg` | CC BY-SA 4.0 | Suresh Kumar Vakalapudi | yes |
| `Enjoyed food at nandos.jpg` | CC BY-SA 4.0 | Rehansha41 | yes |

Note the third: an "indian food" search returned a **Nando's** meal. Search is
noisy; category-based harvesting plus manual review is mandatory.

### 2.2 Verified class counts — strongest

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
`verified_direct_files`, `has_subcategories`, `bucket`, `sufficient_data`,
`licence_verified`, `count_note`.

### 4.1 Honest bucketing

| Bucket | Count | Definition |
|---|---|---|
| **A. Ready** (≥150 verified direct files) | **17** | Could train and evaluate now |
| **B. Viable** (50–149) | **39** | Usable with augmentation; thin test set |
| **C. Marginal** (<50) | **41** | Not enough for train/val/test |
| **D. Unmeasured** | **3** | Commons category not identified/verified |

**17 classes are solid, 56 reach ≥50 images, only 9 reach the 200-image floor.
100 classes is not currently supportable at 200–500 images each.**

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

**Build 40–60 classes, not 100.**

- **Tier A now (17 classes, ≥150 files)** — solid train/val/test.
- **Tier B (39 classes, 50–149 files)** — viable; smaller, noisier classes.
  Realistically **~50 classes** retain ≥100 images after dedupe and contamination
  filtering (assume 10–20% loss; 13.2% was measured on the 80-class set from
  duplicates alone).
- **Do not include Tier C (<50 files)** merely to reach a round number. That is
  precisely the "unsuitable data to hit the target" trap the brief warns against.

**What would close the gap to 100:**

1. **Subcategory expansion** — 79 measured categories have subcategories whose
   files I could not count (hosts blocked). This is the most likely source of the
   missing images and the first thing to measure once egress opens.
2. A second permissively licensed source with verifiable per-image terms.
3. Accepting ~50–100 images for tail classes, with the smaller count documented.

**What I will not do:** claim 100 classes are feasible, pad classes with
near-duplicates, or count augmented copies as independent images — the exact
failure mode of the SohlHealth dataset (`docs/SOHLHEALTH_PROVENANCE.md` §6).

---

## 8. Fact / estimate / inference / unknown

**Verified facts**
- 116 Commons category counts measured via API; 8,906 direct files.
- 9 categories ≥200 files, 16 ≥150, 29 ≥100, 62 ≥50; 54 categories <50.
- Rolled up to 100 proposed classes: 9 ≥200, 17 ≥150, 56 ≥50, 41 <50, 3 unmeasured.
- Per-file licence/author/permission metadata exists and is populated.
- All Wikimedia hosts are blocked from the sandbox (`000`).
- 79 measured categories have uncounted subcategories.

**Estimates**
- ~2 GB for 20,000 thumbnails; ~15–25 GB for originals.
- 10–20% further loss from dedupe + contamination filtering.
- ~50 classes will retain ≥100 usable images.

**Inferences**
- Subcategory expansion will raise most mid-tier counts substantially.
- Search-based harvesting is much noisier than category-based (the Nando's result).
- CC BY-SA is *probably* acceptable for model weights, but this is unsettled law.

**Unknown / not measured**
- Whether image download works at all (host blocked) — **the biggest unknown**.
- Actual licence distribution across the corpus.
- Duplicate / near-duplicate rate.
- True totals once subcategories are counted.
- Whether 100 classes can reach 200–500 images each. **I do not know, and I will
  not assert it either way.**

---

## 9. Explicit statements

- **No model was trained. No images were downloaded. No application code changed.
  The 12-class model is untouched.**
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
