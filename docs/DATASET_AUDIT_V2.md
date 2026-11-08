# Indian Food Dataset Research Report

**Date:** 2026-11-07
**Purpose:** Evidence for choosing (or rejecting) Indian food image datasets for
Food Recognition V2. **No training has been performed.** This report exists so
the decision is made on measured facts.

---

## 0. Bottom line

| Question | Answer |
|---|---|
| Indian food image datasets usable **right now**? | **No. Zero are both reachable and properly licensed.** |
| Best Indian candidate found | 80 classes × 50 images = 4,000, publicly redistributable |
| Its image licence | **Unknown / unlicensed.** Original source is a Kaggle upload; rights not verifiable |
| Contamination in that dataset | Watermarks, brand packaging, `alamy stock photo`, `The Guardian` credit, multi-panel collages |
| Classes usable from it without legal risk | 0 as-is |
| Bangladeshi dataset status | **Stopped**, as instructed. Kept only as prior research |

**Recommendation: do not train on any Indian dataset yet.** Section 7 lists what
would unblock this.

---

## 1. What this build environment can reach

Egress is restricted to `github.com`, `codeload.github.com`, `api.github.com`,
`pypi.org`, `registry.npmjs.org`. Everything else is blocked (connection refused
/ no route, HTTP `000`):

| Host | Result | Consequence |
|---|---|---|
| `huggingface.co` | blocked | **Indian Foods Dataset (bharat-raghunathan) inaccessible** |
| `mm.cs.uec.ac.jp` | blocked | **UEC FOOD-100 inaccessible** |
| `adityaarun1.github.io` | blocked | **Indian Thali ICVGIP PDF inaccessible** |
| `kaggle.com` | blocked | Original Indian Food Images source inaccessible |
| `data.mendeley.com`, `zenodo.org` | blocked | No Mendeley/Zenodo mirrors |
| `storage.googleapis.com`, Oracle object storage | blocked | RASOI's Google Drive/OCI links inaccessible |
| `raw.githubusercontent.com` | blocked | Individual files must be fetched via codeload tarballs |
| **`github.com` / `codeload.github.com`** | **reachable** | only source of truth available |

This is the binding constraint on the whole task, and it is not something code
can work around.

---

## 2. Dataset-by-dataset audit

### 2.1 Indian Foods Dataset (bharat-raghunathan) — **INACCESSIBLE**

- Host: `huggingface.co` → blocked.
- Could **not** verify: version, image count, labels, licence. Your brief
  reported ~4,770 images / ~15 classes / CC0-1.0 declared.
- **Status: unverified.** I am not restating those figures as fact, because I
  could not confirm any of them.
- Even if reachable: a CC0 declaration by an uploader is not proof of
  chain-of-title for the underlying photographs (the same caveat that applies to
  the Bangladeshi dataset, and to `docs/LICENSING_AUDIT.md` §5.2).

### 2.2 Indian Thali Dataset (ICVGIP 2025) — **INACCESSIBLE**

- Host: `adityaarun1.github.io` → blocked. Paper PDF and any companion data not
  retrievable.
- A research *code* licence (commonly MIT) would not extend to images or
  annotations. Unresolved, and moot while unreachable.
- **Status: unverified.**

### 2.3 UEC FOOD-100 — **INACCESSIBLE**

- Host: `mm.cs.uec.ac.jp` → blocked.
- Also relevant even if reachable: UEC FOOD-100 is **Japanese** food, not
  Indian. It was specified as the international component, and its images are
  distributed under research-oriented terms that typically do **not** grant
  unrestricted redistribution.
- **Status: unverified and likely unsuitable for redistribution.**

### 2.4 Indian Food Images Dataset (80 classes) — **REACHABLE, LICENCE UNCLEAR**

The only substantial Indian image set obtainable here. Found via
`gnpaone/Indian-food-classification` (~412 MB, 80 class folders).

**Measured facts** (see `data/v2/indian_audit.json` and
`training/audit_indian_dataset.py`):

| Property | Value |
|---|---|
| Classes | 80 |
| Images per class | exactly 50 (suspiciously uniform) |
| Total images | 4,000 raw |
| Integrity failures | 0 (all decode) |
| Exact duplicates | 24 |
| Near-duplicates (dHash ≤ 2) | 502 |
| Cross-class duplicates | 27 |
| **After dedupe** | **3,474** |
| Images per class after dedupe | 27–50 (`chicken_tikka_masala` worst at 27) |
| Colour modes | 100% RGB |
| Median longest side | ~401 px |
| Distinct resolutions | many (183×275, 225×225, 259×194, 1280×720 …) |

**Provenance.** The repository's own README cites the origin as
`kaggle.com/datasets/iamsouravbanerjee/indian-food-images-dataset`. That host is
blocked, so the dataset's licence terms **could not be read or verified**.

**Licence status: UNVERIFIED → treated as unusable for redistribution.**

The repository redistributes the images with **no licence covering them** (the
repo has no LICENCE file). Being visible on GitHub grants no reuse right.

**Contamination found by visual inspection.** I sampled images across classes
and built contact sheets. Observed directly:

- `alamy stock photo` watermark — **commercial stock imagery**
- `The Guardian` logo on a collage panel
- vendor watermarks: `Vahchef`, `MARIA'S KITCHEN`, `@pankajkohli`
- `©2018` credit, `alamy stock photo` strip
- brand **packaging** photographed as the class image (e.g. "Babasins Thakur
  Pedha" box)
- multi-panel **collages** mixing several dishes in one file

These are rights problems *and* training problems: a collage of four dishes
labelled as one class teaches the wrong thing, and a packaging shot is a picture
of a box, not of the food.

Heuristic scan (`collage` gutter test, near-white background, extreme aspect
ratio) flags **412 suspected collages** alone. That is a **lower bound** — no
heuristic here detects a watermark or logo on an otherwise normal photo, which
is exactly the contamination seen above.

**Verdict: not usable as-is.** Both the legal position and the visual quality
block it.

### 2.5 RASOI (Indian thali, multi-food) — **IMAGES NOT IN REPO**

Attractive because it is the only multi-food/thali source found, with bounding
box annotations — the right shape of data for plate-level recognition.

Measured from `Koushik1s/RASOI`:

| Property | Value |
|---|---|
| Annotation file | `train_data.csv`, 1,510 annotation rows |
| Format | VIA-style rectangles (`region_shape_attributes`) |
| Classes referenced | ~63 dish labels |
| Image location | **`Datasets/train` contains a Google Drive link, not images** |
| Sample class counts | Chutney 145, Salad 175, Biryani 42, Bhatura 16, Chilli Potato 3 |

**Status: annotations only, images unreachable** (Drive blocked). Class
distribution is also severely imbalanced (3–175 annotations). No licence file
covering the images.

### 2.6 Smaller / weaker candidates (all rejected)

| Repository | Classes / images | Licence | Why rejected |
|---|---|---|---|
| `dhruvk2002/food-classifier` | 20 classes, local images | NONE | No licence; **previously excluded in this project** |
| `SoumyaXD/Indian-Food-Classifier` | 80 classes, 4,077 files | NONE | Same 80-class set, mirrors the Kaggle origin |
| `Snigdha-Sinha/IndianFoodDataset` | ingredient detection, images by numeric ID | GPL-3.0 | Images **scraped from archanaskitchen.com + bawarchi.com**; GPL on repo does not license the photos |
| `AdityaKr015/Indian-Food-Classification` | 634 images total | AGPL-3.0 | Too few images per class; YOLO-classification layout |
| `Sarthak-1408/Indian-Food-Classification` | notebook only | NONE | No images committed |
| `Chethumuniraju/...` | 20 classes | GPL-3.0 | Duplicate of the `gnpaone` `.h5`; thin class coverage |

`kanishk307/IndianFoodDatasetGeneration` is a **recipe text** corpus, not images
— irrelevant to recognition.

---

## 3. Class coverage reality check

The 80-class set is genuinely Indian and pan-regional — a real spread of sweets,
breads, dals, regional dishes:

```
adhirasam, aloo_gobi, aloo_matar, aloo_methi, aloo_shimla_mirch, aloo_tikki,
anarsa, ariselu, bandar_laddu, basundi, bhatura, bhindi_masala, biryani, boondi,
butter_chicken, chak_hao_kheer, cham_cham, chana_masala, chapati, chhena_kheeri,
chicken_razala, chicken_tikka, chicken_tikka_masala, chikki, daal_baati_churma,
daal_puri, dal_makhani, dal_tadka, dharwad_pedha, doodhpak, double_ka_meetha,
dum_aloo, gajar_ka_halwa, gavvalu, ghevar, gulab_jamun, imarti, jalebi, kachori,
kadai_paneer, kadhi_pakoda, kajjikaya, kakinada_khaja, kalakand, karela_bharta,
kofta, kuzhi_paniyaram, lassi, ledikeni, litti_chokha, lyangcha, maach_jhol,
makki_di_roti_sarson_da_saag, malapua, misi_roti, misti_doi, modak, mysore_pak,
naan, navrattan_korma, palak_paneer, paneer_butter_masala, phirni, pithe, poha,
poornalu, pootharekulu, qubani_ka_meetha, rabri, ras_malai, rasgulla, sandesh,
shankarpali, sheer_korma, sheera, shrikhand, sohan_halwa, sohan_papdi,
sutar_feni, unni_appam
```

Notable skew: roughly **half are sweets/desserts**. Savoury main dishes and
dals are under-represented. That is a taxonomy imbalance worth knowing before
any training, independent of the licence issue.

**Overlap with NutriCare's existing 70-slug taxonomy: 13 classes** — `aloo_gobi`,
`bhatura`, `bhindi_masala`, `dal_makhani`, `dal_tadka`, `jalebi`, `kachori`,
`kadai_paneer`, `naan`, `palak_paneer`, `paneer_butter_masala`, `poha`,
`rasgulla`. The other 67 would be new.

---

## 4. Would this reach 150 classes?

**No.** Arithmetic, not opinion:

- 80 classes exist in the only reachable Indian set. Even every one being
  lawfully usable gives **80**, not 150.
- 13 already exist → at most **67 new** classes.
- After deduplication the smallest class holds 27 images — workable but thin.
- Reaching 120 Indian + 30 international would need **additional licensed
  sources**, of which zero are reachable.

---

## 5. What I would need to proceed

Any **one** of these unblocks real training:

1. **Egress** to `huggingface.co` (for bharat-raghunathan/indian-foods-dataset),
   or
2. A **licence statement** for the 80-class Indian set — i.e. the actual Kaggle
   dataset page terms, so I can confirm redistribution and derivative-model
   rights, or
3. You host an approved Indian image archive somewhere reachable from
   `github.com`, or
4. You approve a **different** Indian source that already carries an explicit
   image-level licence.

Option 2 is the cheapest: if that Kaggle dataset permits derivative works, the
80 classes become viable immediately, and the pipeline (taxonomy builder,
dedupe, leakage-safe split) is already written and tested against real data.

---

## 6. What already exists and is reusable

Built and run, not speculative:

- `training/build_taxonomy_v2.py` — generates a taxonomy from real folders and
  **fails** if any folder is unmapped (verified: it caught a phantom folder).
- `training/prepare_dataset_v2.py` — integrity → global dedupe → stratified
  split → independent leakage re-audit.
- `training/audit_indian_dataset.py` — the script that produced §2.4 numbers.
- `training/load_imagenet_backbone.py` — proven to load real ImageNet
  MobileNetV3 weights from a GitHub-hosted checkpoint (244 tensors, strict).
- Data: `data/v2/taxonomy_v2.json`, `data/v2/indian_audit.json`.

These are dataset-agnostic: pointing them at a licensed Indian archive is a
config change, not a rewrite.

---

## 7. Explicit statements

- **No Indian model has been trained.**
- **No accuracy figure is claimed** anywhere in this report.
- The Bangladeshi preprocessing run was **stopped** on instruction; nothing was
  trained on it, and no splits were materialised.
- The existing 12-class CC0 model is **untouched** and remains the default.
