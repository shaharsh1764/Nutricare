# NutriCare V2 — 100-class coverage report

Measured 2026-11-05 against the Wikimedia Commons MediaWiki API. 
**No image bytes were downloaded and no model was trained from real photographs.**

## Read this before quoting any number

The counts below are in strict order of meaning. They are *not* interchangeable.

| # | Count | What it actually is |
|---|---|---|
| 1 | discovered file slots | Files and subcategory members seen in a category listing. Overlapping, unfiltered. **Never a training count.** |
| 1b | unique titles | The same, after collapsing a file listed in several categories. |
| 2 | metadata retrieved | Files whose imageinfo actually came back from the API. |
| 3 | rights-supported | Declared licence permits training use *and* an author is recorded. |
| 4 | reviewed | A human recorded a decision. |
| 5 | approved | Reviewed relevant, acceptable quality, no flags. |
| 6 | training-usable | Approved, technically valid, not a duplicate. The only training count. |

Today: **count 6 is 0 for every class**, because no revised image bytes could be
obtained in this environment and no human has reviewed the V2 batches yet. That zero
is the honest result, not a placeholder.

## Headline coverage

- Classes in the taxonomy: **100** (unchanged; nothing removed, renamed or merged)
- Classes with a measured Commons category: **97**
- Classes with no usable category reference: **3** (collection gaps)
- Direct file slots measured across all classes: **8270**

Distribution by direct-category file count:

| Band | Classes |
|---|---|
| >= 200 files | 9 |
| >= 150 files | 16 |
| >= 100 files | 26 |
| >= 50 files | 55 |
| 1–49 files | 41 |
| 0 or unmeasured | 4 |

## The finding that constrains everything

Category size is *not* the bottleneck. **Licensing is.**

A direct measurement of unrestricted-licence files (CC0 / public domain / CC BY,
excluding share-alike) inside the category itself:

`list=search&srnamespace=6&srsearch=incategory:"<category>" haslicense:unrestricted filetype:bitmap`

| Class | Category files | Unrestricted-licence files | Share usable in a training-approved set |
|---|---|---|---|
| Naan | 230 | 30 | 13% |
| Biryani | 468 | 27 | 6% |
| Roti / Chapati | 393 | 12 | 3% |
| Chutney | 298 | 11 | 4% |
| Samosa | 273 | 9 | 3% |
| Tandoori Chicken | 161 | 8 | 5% |
| Lassi | 121 | 8 | 7% |
| Butter Chicken | 74 | 7 | 9% |
| Jalebi | 237 | 7 | 3% |
| Kheer | 182 | 7 | 4% |
| Poha | 116 | 6 | 5% |
| Gulab Jamun | 216 | 6 | 3% |
| Laddu | 164 | 4 | 2% |
| Idli | 248 | 3 | 1% |
| Puri / Poori | 141 | 1 | 1% |
| Dosa (plain) | 73 | 1 | 1% |

Biryani is the clearest example. It has 207 files in its main category, and the
93-file pilot manifest was **89 CC BY-SA, 2 CC BY, 2 CC0** — about 4% permissive.
The same shape holds across classes: Commons is overwhelmingly share-alike.

Consequence: an honest CC0/CC-BY-only V2 dataset is *small*, roughly
**1–3 usable images per class at best** before review losses, not hundreds.
Only **2** measured classes reach 20 unrestricted files, and
**4** have fewer than 5. This is why the early-training
milestone has to be judged against `training_usable`, not against category size, and
why a decision on CC BY-SA is the single highest-leverage next step.

## Class-by-class candidate counts

`discovered` is the direct-category file count. `unrestricted` is the permissive-licence
measurement where taken. Neither is a training count.

| Class | Commons categories | Discovered | Unrestricted | Status |
|---|---|---|---|---|
| Biryani | Biryani, Chicken biryani, Hyderabadi biryani | 468 | 27 | strong |
| Roti / Chapati | Roti | 393 | 12 | strong |
| Chutney | Chutney | 298 | 11 | strong |
| Samosa | Samosas, Samosas of India | 273 | 9 | strong |
| Idli | Idli | 248 | 3 | strong |
| Jalebi | Jalebi | 237 | 7 | strong |
| Naan | Naan | 230 | 30 | strong |
| Pani Puri | Panipuri | 221 | not measured | strong |
| Gulab Jamun | Gulab jamun | 216 | 6 | strong |
| Kheer | Kheer, Payasam | 182 | 7 | moderate |
| Pakora / Bhajji | Pakora, Bhaji | 166 | not measured | moderate |
| Dal | Dal | 164 | not measured | moderate |
| Laddu | Laddu | 164 | 4 | moderate |
| Fried Fish | Fried fish | 163 | not measured | moderate |
| Tandoori Chicken | Tandoori chicken | 161 | 8 | moderate |
| Pongal | Pongal | 151 | not measured | moderate |
| Chaat | Chaat | 148 | not measured | moderate |
| Chicken Curry | Chicken curries | 143 | not measured | moderate |
| Puri / Poori | Puri | 141 | 1 | moderate |
| Parotta | Parotta | 134 | not measured | moderate |
| Raita | Raita | 130 | not measured | moderate |
| Lassi | Lassi | 121 | 8 | moderate |
| Poha | Poha | 116 | 6 | moderate |
| Fried Rice | Fried rice | 115 | not measured | moderate |
| Appam | Appam | 105 | not measured | moderate |
| Momos | Momos | 103 | not measured | moderate |
| Aloo Paratha | Aloo paratha | 97 | not measured | limited |
| Halwa | Halva | 94 | not measured | limited |
| Bhel Puri | Bhelpuri | 87 | not measured | limited |
| Chole Bhature | Chole bhature | 81 | not measured | limited |
| Gajar Ka Halwa | Gajar ka halwa | 77 | not measured | limited |
| Kulfi | Kulfi | 76 | not measured | limited |
| Dhokla | Dhokla | 75 | not measured | limited |
| Malpua | Malpua | 75 | not measured | limited |
| Butter Chicken | Butter chicken | 74 | 7 | limited |
| Falooda | Falooda | 74 | not measured | limited |
| Paneer Tikka | Paneer tikka | 74 | not measured | limited |
| Puttu | Puttu | 74 | not measured | limited |
| Dosa (plain) | Dosa | 73 | 1 | limited |
| Chana Masala | Chana masala | 71 | not measured | limited |
| Vada Pav | Vada pav | 71 | not measured | limited |
| Chow Mein | Chow mein | 70 | not measured | limited |
| Murukku | Murukku | 66 | not measured | limited |
| Barfi | Barfi | 65 | not measured | limited |
| Uttapam | Uttapam | 61 | not measured | limited |
| Aloo Tikki | Aloo tikki | 59 | not measured | limited |
| Rasmalai | Rasmalai | 59 | not measured | limited |
| Aloo Gobi | Aloo gobi | 56 | not measured | limited |
| Chicken Tikka | Chicken tikka | 56 | not measured | limited |
| Cutlet | Cutlets of India | 55 | not measured | limited |
| Mutton Curry | Mutton curry | 55 | not measured | limited |
| Rasgulla | Rasgulla | 54 | not measured | limited |
| Chicken Tikka Masala | Chicken tikka masala | 52 | not measured | limited |
| Kachori | Kachori | 51 | not measured | limited |
| Fish Curry | Fish curries | 50 | not measured | limited |
| Curd Rice | Curd rice | 49 | not measured | thin |
| Upma | Upma | 49 | not measured | thin |
| Haleem | Haleem | 48 | not measured | thin |
| Masala Chai | Masala chai | 48 | not measured | thin |
| Bhindi Masala | Bhindi masala | 47 | not measured | thin |
| Peda | Peda | 47 | not measured | thin |
| Tandoori Roti | Tandoori roti | 47 | not measured | thin |
| Palak Paneer | Palak paneer | 45 | not measured | thin |
| Paratha | Paratha | 44 | not measured | thin |
| Chicken 65 | Chicken 65 | 43 | not measured | thin |
| Rasam | Rasam | 43 | not measured | thin |
| Papri Chaat | Papri chaat | 41 | not measured | thin |
| Imarti | Imarti | 39 | not measured | thin |
| Indian Filter Coffee | Indian filter coffee | 36 | not measured | thin |
| Idiyappam | Idiyappam | 36 | not measured | thin |
| Modak | Modak | 35 | not measured | thin |
| Baingan Bharta | Baingan bharta | 33 | not measured | thin |
| Mysore Pak | Mysore pak | 33 | not measured | thin |
| Phirni | Phirni | 33 | not measured | thin |
| Rajma | Rajma | 32 | not measured | thin |
| Shahi Paneer | Shahi paneer | 32 | not measured | thin |
| Rava Dosa | Rava dosa | 31 | not measured | thin |
| Dal Makhani | Dal makhani | 30 | not measured | thin |
| Kadai Paneer | Kadai paneer | 30 | not measured | thin |
| Rabri | Rabri | 30 | not measured | thin |
| Sandesh | Sandesh | 28 | not measured | thin |
| Chakli | Chakli | 27 | not measured | thin |
| Chomchom | Chomchom | 26 | not measured | thin |
| Dal Tadka | Dal tadka | 26 | not measured | thin |
| Kulcha | Kulcha | 23 | not measured | thin |
| Shrikhand | Shrikhand | 22 | not measured | thin |
| Moong Dal | Moong dal | 21 | not measured | thin |
| Pulao / Pilaf | Pulao | 20 | not measured | thin |
| Saag | Saag | 20 | not measured | thin |
| Thepla | Thepla | 18 | not measured | thin |
| Nihari | Nihari | 17 | not measured | thin |
| Rumali Roti | Rumali roti | 17 | not measured | thin |
| Lemon Rice | Lemon rice | 15 | not measured | thin |
| Pesarattu | Pesarattu | 14 | not measured | thin |
| Malai Kofta | Malai kofta | 12 | not measured | thin |
| Bhatura | Bhatura | 10 | not measured | thin |
| Masala Dosa | — | 0 | not measured | **collection gap** |
| Matar Paneer | — | 0 | not measured | **collection gap** |
| Sambar | Sambar | 0 | not measured | **collection gap** (category empty) |
| Vada | Vada | 0 | not measured | **collection gap** (category empty) |

## Taxonomy discrepancies found (recorded, not silently fixed)

- **matar_paneer** — taxonomy recorded 0 direct files (bucket D unmeasured); Category:Matar paneer now measures 31 files. Action: recorded as a collection gap closed by measurement, NOT auto-approved.
- **sambar** — taxonomy requests 'Category:Sambar', which is missing/1 page; the real Commons category is 'Category:Sambhar' (8 files). Action: discrepancy recorded; taxonomy NOT renamed without approval.
- **vada** — Category:Vada has 0 files and is missing; the taxonomy has no verified Vada category. Action: remains a collection gap.

## Licence and provenance breakdown (measured sample)

From the captured two-class metadata sample used to exercise the pipeline
(`tests/fixtures/commons/v4_measured_sample.json`, 28 real files):

| Rights tier | Files |
|---|---|
| TRAINING_APPROVED | 3 |
| REVIEW_REQUIRED | 25 |
| EXCLUDED | 0 |

| Declared licence class | Files |
|---|---|
| CC_BY_SA | 25 |
| CC_BY | 3 |

Tier rules: **CC0/PD/CC BY** with a recorded author are training-approved;
**CC BY-SA** is tracked separately and held out; **NC/ND/unknown/unrecognised**
are excluded. A declared licence is never verified permission, so every record keeps
`legal_clearance: not_verified` and `usable_for_training: false` until a human approves it.

Provenance strength in the sample: unknown 28.

## Pipeline status

| Stage | Status | Evidence |
|---|---|---|
| Collection (`collect_v2.py`) | Written and self-tested; live API unreachable from this sandbox | `data/v4/demo_run/evidence.json` |
| Rights tiering (`licence_policy.py`) | Written and tested | 22 unit tests |
| Review batches (`build_v2_review_batches.py`) | **Real batches built for 2 classes** | `data/v4/review/roti/`, `data/v4/review/idli/` |
| Preparation (`prepare_v2_dataset.py`) | Written and self-tested; refuses to over-claim | 30 unit tests |
| Training (`train_v2.py`) | Written and self-tested; **no real model produced** | learns synthetic patterns 0.75 vs 0.25 baseline |

## Blockers

1. **Licensing**, as quantified above. The permissive pool is thin everywhere.
2. **No image bytes in this sandbox.** `upload.wikimedia.org` is unreachable, so no
   real image could be decoded, reviewed, or trained on here. Downloads must run locally.
3. **No human review of V2 batches yet.** Reviewer time is a real dependency; the six
   counts stay at 0 until that happens.
4. **Two taxonomy gaps** (`sambar`, `vada`) need a corrected category reference.

