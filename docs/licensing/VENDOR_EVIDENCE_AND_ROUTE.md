# Vendor Evidence and Recommended Acquisition Route

**Date:** 2026-11-05
**Purpose:** Evidence pack behind the two licensing inquiries, plus a
cost-benefit recommendation for reaching 100 Indian food classes.
**Companion files:** `INQUIRY_DATACLUSTER.md`, `INQUIRY_FOODLENS.md`
**Nothing has been purchased, contacted, or trained.**

---

## 1. Priority 3 verdict first: Wikimedia Commons is not a viable route

You asked me to continue on Commons only if there is a practical way to acquire
and verify bytes. **There is not, so I stopped.**

Measured this session:

| Check | Result |
|---|---|
| `upload.wikimedia.org` (where image bytes live) | **blocked** — TLS closed, re-confirmed |
| `commons.wikimedia.org` | blocked from bash; API readable only through text-only tooling |

Even if bytes were reachable, the supply ceiling makes it the wrong investment:

- **~147 permissively-licensed candidate files** across 18 measured categories.
- **Dosa: 1 file. Dhokla: 0 files.**
- `masala_dosa` and `matar_paneer` have **no Commons category at all**.
- Mislabels already visible at metadata level (Persian *Zoolbia Bamieh* under
  Jalebi; Armenian village bread and butter chicken under Naan).

**Conclusion:** Commons can supply a small validation/pilot set for maybe 7
classes. It cannot approach 5,000 images across 100 classes under any network
conditions. Not pursued further.

---

## 2. DataCluster Labs — evidence

### 2.1 Confirmed facts

| Item | Finding |
|---|---|
| Entity | DataCluster Labs Pvt Ltd, Bangalore, India |
| Sales contact | **sales@datacluster.ai** (published on site, Kaggle, GitHub, HF) |
| Response SLA | "within two business days" |
| Food dataset locations | Kaggle `dataclusterlabs/indian-food-image-dataset`; Roboflow Universe `datacluster-labs-agryi/indian-food-image`; GitHub `datacluster-labs/Indian-Food-Image-Dataset` (README stub only) |
| Ownership claim | *"The images in this dataset are exclusively owned by Data Cluster Labs and were not downloaded from the internet."* |
| Collection method | Crowdsourced, 800+ contributors, 800+ Indian cities, mobile phones 2020–2021 |
| Resolution claim | 99% HD (1920×1080+) |
| Annotation formats | COCO, YOLO, Pascal VOC, TF-Record |
| Sample-licence precedent | **CC BY-NC-ND 4.0**, with *"❌ No use in training commercial ML models"* (their vehicle and number-plate samples on Hugging Face) |

### 2.2 The image-count problem — three vendor pages, three numbers

| Source (all vendor-controlled) | Claimed images |
|---|---|
| GitHub README | **~3,500 unique images** |
| Kaggle data card | **"1000+"** (1.5 GB, v4 archive, 1000-file `food_dataset` folder) |
| Your earlier note | "approximately 3,500" |

A 3.5× spread across the vendor's own pages. **No class list and no per-class
counts are published anywhere.** Until a quote names a figure, treat 3,500 as
unverified and 1,000 as the only number actually evidenced by a file listing.

### 2.3 Suitability for a 100-class target — the arithmetic

DataCluster's *entire* catalogue is described as 250+ classes across all their
datasets (vehicles, number plates, traffic signs, stairs, fire/smoke, bottles,
footpaths…). The **Indian Food** set is one dataset within that.

- If the food set is ~3,500 images, and the vendor's dish-class count is
  plausibly in the 20–60 range, that is **~60–175 images/class**. Workable for a
  subset, not for 100 classes.
- **100 classes × 50 images = 5,000 images minimum.** It is unclear whether
  DataCluster's Indian food set even has 100 dish classes. This is question 1 in
  the inquiry and it is decisive: if they have 40 classes, buying it does not
  reach 100 no matter the price.

### 2.4 Pricing

**No public pricing exists.** Their site is quote-only ("Contact sales"). The
business model is data collection + annotation services, so pricing is likely
scoped per engagement rather than a fixed catalogue price. I did not invent a
figure. Realistic expectations, offered as *unverified planning assumptions*:

| Model | Plausible range (assumption, not a quote) |
|---|---|
| One-off licence, small dataset (~3.5K) | low-to-mid four figures USD |
| Custom collection, 100 classes × 50 images | five figures USD (5,000 crowd images + annotation) |

Treat both rows as guesswork to be replaced by the actual quote.

### 2.5 What must come back in writing before any payment

1. Exact image count and **per-class counts** for the licensed version.
2. Confirmation that **commercial ML training** is permitted (their public sample
   terms say the opposite).
3. Explicit right to **distribute trained weights** commercially.
4. Explicit right to **hosted SaaS inference**.
5. Perpetual + worldwide, with renewal terms stated.
6. Confirmation that contributor rights are assigned to DataCluster.

---

## 3. FoodLens — evidence

| Item | Finding |
|---|---|
| Corresponding author | **Narayan Hegde**, hegde@google.com |
| Affiliation | Google Inc., Mountain View |
| Co-authors | J. Alla, Y. Samaga, A. Vaswani, P. Netrapalli, S. Kapania, P. Kumar |
| Venue | IMPROVE 2025, Springer, pp. 262–284, DOI 10.1007/978-3-032-01169-5_16 |
| Claimed size | 30K images, 140+ dishes, multi-label, hierarchical taxonomy |
| Public release | **None found** — no hosting, no licence, no data link |
| Licence | **Not stated anywhere** |
| Provenance | **Not disclosed** |

**Assessment:** the most valuable dataset on paper and the least accessible.
Even a successful reply most likely yields research-only terms, which would not
permit commercial deployment. Its taxonomy (140+ dishes mapped to a hierarchy)
is genuinely useful as a **specification** for our 100-class target even if the
images are never obtainable — that is the fallback ask in the inquiry.

---

## 4. Everything else, for completeness

| Dataset | Images | Licence reality | Commercial? |
|---|---|---|---|
| Khana | 130K | research | No — and excluded by brief |
| IndFood / dhruvk2002 / Google-scraped 80-class | — | none / excluded | No — excluded by brief |
| Snigdha-Sinha/IndianFoodDataset | — | GPL on code; scraped images | No |
| Koushik1s/RASOI | derived | none; "web-scraped samples" | No |
| IndianFood-7 (Roboflow) | 800+, 7 cls | CC BY 4.0 **and** "academic research only" — self-contradictory | No |
| HF "CC0" Indian food sets | ~4,770 | card admits *"scraping from Google Images"* | No |
| IndianFoodDB-30 | 5,191, 30 cls | derived from forbidden 80-class set | No |
| SOHL Multi-Dish | **377 measured** | MIT (upload-level, ownership unproven) | Unclear |
| Kaggle Indian Food 16 | ~275 | Apache 2.0 on upload | Unclear / too small |
| RASOI (your upload) | ~310 annotated | **CC BY-NC-SA 4.0** | **No — non-commercial** |
| **Wikimedia Commons** | ~147 candidates | genuine CC0/PD/CC BY | **Yes** (but bytes blocked) |
| **DataCluster** | ~1,000–3,500 | proprietary, purchasable | **Yes, if licensed** |
| **FoodLens** | 30K (claimed) | unknown, unreleased | Unknown |

---

## 5. Recommendation — most economical route to 100 classes

There is no cheap route to 100 Indian food classes with clean commercial rights.
Ranked by cost-effectiveness, cheapest first:

### Route A — Build the 100-class taxonomy from Commons + paid stock (lowest cash, highest effort)
Combines the ~147 Commons candidates with a modest paid stock licence
(Pexels/Adobe/Shutterstock) for the ~85 classes Commons can't cover.
- **Cash:** low hundreds of USD for stock.
- **Effort:** very high — manual curation of 5,000 images across 95+ classes,
  each needing per-image licence capture.
- **Rights:** cleanest possible (explicit per-image licences).
- **Realistic timeline:** many weeks.
- **Verdict:** cheapest in cash, most expensive in your time. Only sensible if
  your time is genuinely cheaper than a licence.

### Route B — DataCluster licence (best balance, contingent)
One payment, one contract, one provenance story, crowd-captured real-world
variety, annotations included.
- **Blocker:** unknown price, unknown class count. If they have ≥100 dish
  classes the arithmetic works; if they have 40, it does not.
- **Verdict: pursue first** — because the inquiry is free and the answer
  determines whether Routes A and C are needed at all.

### Route C — FoodLens access (highest upside, lowest probability)
30K images, 140+ dishes, hierarchical taxonomy — exactly the target shape.
- **Blocker:** unreleased, no licence, Google-internal, probably research-only.
- **Verdict: send the inquiry anyway.** Zero cost, and even a taxonomy-only reply
  is valuable. Do not build a plan that depends on it.

### Route D — Custom collection (most certain, most expensive)
Commission exactly 100 classes × 50 images to our own spec, with rights assigned
to us outright. Either DataCluster's custom service or an independent vendor.
- **Cash:** five figures, likely.
- **Rights:** unambiguous, purpose-built, no licensing ambiguity ever.
- **Verdict:** the correct choice if NutriCare is going commercial and the budget
  exists. It removes the entire rights problem permanently.

### Recommended sequence

1. **Send both inquiries** (awaiting your approval). Free.
2. **While waiting:** raise the 12-class model to a **20–30 class** model using
   Commons (once egress opens) + licensed stock, exercising the training pipeline
   on genuinely cleared data. Ships real value early and de-risks the pipeline.
3. **On DataCluster's reply:** if they confirm ≥100 dish classes and commercial
   training + weight distribution rights, buy it — that is the cheapest path to
   the full target.
4. **If DataCluster cannot cover 100 classes:** use them for the classes they
   have, and commission a custom collection (Route D) for the remainder.
5. **Treat FoodLens as upside, never as the plan.**

**Bottom line:** the single most economical action is to buy a licence that
includes commercial training and weight-distribution rights from a vendor that
owns its images outright — and DataCluster is the only such vendor identified.
Everything else costs either your time or your legal certainty.

---

## 6. Actions taken / not taken

- **No email sent. No purchase made. No contact of any kind.**
- Both inquiries exist as drafts for your review in `docs/licensing/`.
- No training started. PR #9 preserved and unmerged. `main` untouched.
- 12-class fallback untouched (`f74d10f6…02ad87`).
