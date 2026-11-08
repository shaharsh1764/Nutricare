# NutriCare V2 — Dataset Discovery and Acquisition Report

**Date:** 2026-11-05
**Branch:** `arena/9235252f-nutricare` (base: merged `main` @ `3e368ae`)
**Status:** 0 images acquired. 0 datasets legally cleared. This report explains
why, with measured evidence, and gives the shortest path to fixing it.

---

## 0. The one-paragraph summary

I found and evaluated 13 Indian food image datasets. **Nine are unusable**
(no licence, code-licence-only, fair-use research-only, or explicit "buy a
commercial licence"). **Three need money or a Hugging Face token.** **One is
reachable and properly licensed** — Wikimedia Commons — but it provides only
~147 permissively-licensed candidate files, and its image host is firewalled
from this sandbox. Net result: **0 images downloaded, 0 classes legally
cleared.** The blocker is two independent walls (sandbox egress + licensing),
and only one of them is mine to solve.

---

## 1. Status vocabulary

The brief asks for six separate statuses. They are not interchangeable, and
almost every dataset below scores differently on each. Using them strictly:

| Status | Meaning |
|---|---|
| **Found** | I located the source and read its licence text |
| **Downloadable** | A route to the bytes exists *and works from a normal machine* |
| **Downloaded** | Bytes are on disk here, verified |
| **Audited** | Integrity, duplicates, labels actually inspected |
| **Legally cleared** | Image rights permit NutriCare's intended *commercial* use |
| **Training-ready** | Audited **and** cleared **and** sufficient volume |

**Actual tally: Found 13 · Downloaded 0 · Audited 0 · Cleared 2 (Commons, and
the "not yet verified" caveat applies) · Training-ready 0.**

---

## 2. Environment reality (measured, not assumed)

Every host below was probed from the sandbox this session:

| Host | Result | Consequence |
|---|---|---|
| `upload.wikimedia.org` | **blocked** (TLS closed) | Commons images unreachable |
| `commons.wikimedia.org` | blocked in bash; readable via my text-only fetch route | metadata only, no pixels |
| `huggingface.co`, `datasets-server.huggingface.co` | **blocked** | all HF datasets unreachable |
| `source.roboflow.com`, `api.roboflow.com` | **blocked** | all Roboflow images unreachable |
| `kaggle.com`, `www.kaggle.com` | **blocked** | all Kaggle datasets unreachable |
| `storage.googleapis.com` | blocked | most academic/GCS mirrors unreachable |
| `api.openverse.org`, `api.pexels.com`, `api.unsplash.com`, `pixabay.com` | **blocked** | no stock-photo / CC-search route |
| `media.githubusercontent.com`, `objects.githubusercontent.com` | blocked | no Git-LFS route |
| **`github.com`, `api.github.com`, `codeload.github.com`** | **reachable** | the only image-capable route |
| `pypi.org` | reachable | packages only, no image datasets |

**This is the crux.** The one host I can fetch images from is GitHub — a host
that is *specifically the worst place* to find legally usable food photographs,
because GitHub repos overwhelmingly redistribute scraped images under a
code licence. The hosts that do have clean image licensing (Wikimedia, Openverse,
Flickr CC, Pexels) are all firewalled.

I verified GitHub works for real bytes in an earlier session: I downloaded a
412 MB archive from `codeload.github.com` and inspected 4,004 decodable JPEGs.
So the route is live. There is simply nothing licensed worth pulling through it.

---

## 3. Every dataset discovered

### 3.1 Unusable — licence would not cover NutriCare's use

| # | Dataset | Images | Licence as published | Why rejected |
|---|---|---|---|---|
| 1 | **Khana** (arXiv 2509.06006) | 130K, 80 cat. | research | **Excluded by brief.** Also research-only. |
| 2 | **IndFood / Khana-related** | — | research | **Excluded by brief.** |
| 3 | **`dhruvk2002`** | — | none | **Excluded by brief.** |
| 4 | **Google-scraped 80-class Kaggle set** (`iamsouravbanerjee`), mirrored as `gnpaone/Indian-food-classification` | 4,020 / 80 | **no licence on images** | **Excluded by brief.** I re-downloaded and confirmed this session: the archive holds *only* images + README, no per-image licence, author or URL. The repo has no LICENCE file at all. |
| 5 | **Snigdha-Sinha/IndianFoodDataset** | — | GPL-3.0 (code) | Images scraped from archanaskitchen.com / bawarchi.com. GPL does **not** license photographs. |
| 6 | **Bangladeshi Food Dataset** | — | — | **Not primary per brief.** Not used at all. |
| 7 | **`datacluster-labs/Indian-Food-Image-Dataset`** (GitHub) | ~3,500 claimed | **none** (API: `license: null`) | Repo is 272 KB — it is a README stub with a `sample_datasets` folder, not the dataset. Commercial use requires purchase. |
| 8 | **IndianFood-7** (Roboflow, Ritu Agarwal et al.) | 800+, 7 classes | card says CC BY 4.0 | **Self-contradictory licence.** Same card states *"contains copyrighted material whose use has not been specifically authorized… available for academic research… beyond non-commercial research you must obtain permission."* A CC BY label cannot coexist with that text; I treat it as research-only. |
| 9 | **Roboflow "school" / "Anmol Jindal" / "Dhandeep" Indian food sets** | small, 3-7 classes | CC BY 4.0 | Scraped-source, tiny class coverage. Not worth the rights risk. |
| 10 | **`Koushik1s/RASOI`** (GitHub) | 105 MB derived | **none** (`license: null`) | README: *"Combines RASOI dataset and **web-scraped samples**"*. A derived mix with no licence and unidentified scraped content. Also merges the forbidden `iamsouravbanerjee` lineage upstream. |

### 3.2 Blocked only by money, token, or egress — potentially usable

| # | Dataset | Images | Licence | Blocker |
|---|---|---|---|---|
| 11 | **DataCluster Indian Food Image Dataset** | 5,000+ captured by 5,000+ unique users, "approx. 3,500 unique" | **Proprietary.** Their own words: *"The images in this dataset are exclusively owned by Data Cluster Labs and were not downloaded from the internet. To access a larger portion of the training dataset for research and **commercial purposes, a license can be purchased**."* | **Commercial licence is purchasable.** Also `source.roboflow.com` blocked. This is the most promising lead for a *truly* cleared commercial dataset. |
| 12 | **SOHL Multi-Dish Indian Food Detection Dataset** | **377 rows** (measured from the HF viewer), not 30K | MIT (per brief) | `huggingface.co` and `datasets-server.huggingface.co` both blocked. 377 images across 100 classes is ~4/class — far too thin anyway. Note the repo already has a `SOHLHEALTH_PROVENANCE.md`; MIT on a dataset upload still is not proof the uploader owns the photos. |
| 13 | **FoodLens** (Google Research, Hegde/Alla et al., IMPROVE 2025) | 30K, 140+ dishes | **not stated in the paper**; dataset not publicly released | Academic paper only. No download link, no licence, no data release found. Not obtainable — needs an author request. |

### 3.3 Reachable and properly licensed — but not enough

| # | Dataset | Images | Licence | Status |
|---|---|---|---|---|
| 14 | **Wikimedia Commons** | 8,270 direct file *slots* across 97 classes; **~147 permissively-licensed candidate files** in 18 measured categories | per-image CC0 / PD / CC BY, with author and attribution | The only genuinely licensed source. See §4. |

### 3.4 Additional sources found (not in the suggested list)

- **`raj-rajat/Indian-Food-Dataset`** — MIT repo, but contents are `LICENSE` +
  README + a 1.6 MB notebook. **No images.** Code licence only.
- **`dsouza-shaun/rasoi-recommender`** — MIT, `data/indian_food.csv` (104 KB).
  A nutrition/recipe table, **no images**.
- **HF `bharat-raghunathan` / `shardulkamde` `indian-foods-dataset`** — card says
  CC0, but the card *also* says **"Collection by Scraping data from Google
  Images"**. A scraper cannot grant CC0. **Rejected** — this is exactly the
  "CC0 claim is not proof of ownership" trap.
- **`bhatt-aditya03/NutriLens` → "IndianFoodDB-30"** (5,191 images, 30 classes) —
  MIT repo, but the README discloses the dataset is **derived by merging
  `iamsouravbanerjee` (the forbidden 80-class set) + `ps2004/food-dataset`**.
  Contaminated lineage. **Rejected.** Also ships only a CoreML model, no images.
- **Kaggle `aryan401/indian-food-16`** — Apache 2.0, ~275 images / 16 classes.
  Apache 2.0 on an upload is not an image grant; host blocked. Too small.
- **Indian Food 101** (`kritirathi`, `ifood_new.csv`) — image **URLs** only, and
  a CSV of dish metadata. No licence over the linked photos.

---

## 4. What Wikimedia Commons actually offers (measured)

From `data/v4/coverage_100.json` (prior session, same out-of-sandbox route),
re-confirmed this session on specific classes:

- 97/100 classes have a measured category; **2 have none** (`masala_dosa`,
  `matar_paneer`); 4 categories are empty.
- Of 18 categories with a permissive-licence measurement, **total ≈147 candidate
  files**: Naan 30, Biryani 19, Roti 12, Chutney 11, Chicken biryani 8,
  Tandoori chicken 8, Lassi 8, Jalebi 7, Butter chicken 7, Kheer 7, Poha 6,
  Gulab jamun 6, Samosas 5, Laddu 4, Samosas of India 4, Idli 3, Dosa 1, Puri 1.
- **Dosa: 1. Dhokla: 0** (queried `Category:Dhokla` + `haslicense:unrestricted`
  → empty result set).

**Conclusion: Commons cannot reach 5,000 images across 100 classes.** With
unlimited network it tops out well under 1,000 after dedupe, review and label
correction. This is a supply ceiling, not a network problem.

Label quality is also poor at the metadata level — already-visible mislabels:
*Zoolbia Bamieh* (Persian) under Jalebi, an Armenian village bread and a butter
chicken photo under Naan, *Sanna Dukra mass* (a mass scene) under Idli.

---

## 5. Licensing evidence — the commercial-use question

The brief asks specifically: **can trained weights be commercially deployed?**

| Dataset | Commercial use of weights? |
|---|---|
| Khana, IndFood, IndianFood-7, HF scraped sets | **No** — research-only or no grant |
| Google-scraped 80-class, Snigdha-Sinha, Koushik1s/RASOI | **No** — no licence exists to rely on |
| DataCluster | **Yes, only if purchased** |
| SOHL (MIT) | **Unresolved** — MIT on an upload is not proof of image ownership |
| FoodLens | **Unknown** — no licence published |
| Wikimedia Commons (CC0 / PD / CC BY) | **Yes** — CC BY requires attribution, PD/CC0 none |
| RASOI (your Drive upload) | **NO — CC BY-NC-SA 4.0 is non-commercial.** Training on NC images makes the derived weights NC in practice. |

Two things I will not do, per the brief: call a code licence an image licence,
and treat a dataset-card CC0 claim as proof of ownership. Both traps are live in
this list (items 3.4, 4, 5 and the HF sets).

---

## 6. Recommended acquisition strategy

Ranked by "chance of real, cleared images" per unit of effort:

1. **Buy a commercial licence from DataCluster** (item 11). They own their
   images outright ("exclusively owned… not downloaded from the internet"),
   they sell commercial rights, and they have ~5,000 Indian food images with
   detection annotations. **This is the single highest-value action.** It is also
   the only route that plausibly reaches 5,000 cleared images near-term.
   Contact: `www.datacluster.ai` (the Roboflow card lists a purchase-enquiry
   email; I have not scraped it as it is obfuscated — ask via the site).
2. **Open network egress for `upload.wikimedia.org`.** Then `training/acquire_v2.py`
   (already built, tested, in PR #9) downloads the ~147 Commons candidates with
   full provenance, size verification and dedupe on the first run. Good for a
   *pilot*, not for 5,000.
3. **Email the FoodLens authors** (Google Research; Hegde, Alla, Vaswani,
   Kapania, Netrapalli, Samaga) requesting the 30K/140-dish dataset and its
   licence terms. Academic datasets frequently permit commercial use on request;
   nothing else gets you 30K labelled Indian images.
4. **Commission a licensed crawl** — e.g. a paid Pexels/Unsplash/Adobe Stock
   licence covering manually curated Indian dish photos. Expensive, slow, but
   unambiguous rights.
5. **Your own photography / crowd-sourced with a signed contributor agreement.**
   The only route that is both free and clean. Slow.

**Do not** use: RASOI (NC), Koushik1s/RASOI (no licence), IndianFoodDB-30
(contaminated), HF CC0-claimed sets (scraped), IndianFood-7 (contradictory).

---

## 7. Supplementary observation on your RASOI upload

Unrelated to the 100-class target but relevant to licensing: **RASOI is
CC BY-NC-SA 4.0**. The `NC` term means weights trained on it should not be
deployed commercially, and `SA` means derivatives inherit the licence. It cannot
be your primary training source for a shippable app. It is usable for
*evaluation* and for internal research. (Its audit is still pending — the
archive exceeds the 100 MiB transfer limit; strategy in my previous message.)

---

## 8. Proposed 100-class taxonomy

Unchanged from `data/v3/taxonomy_100_proposed.json` (already in repo, 100
classes, regional spread: rice, breads, South Indian, dals, paneer, chicken,
mutton, fish, chaat, snacks, sweets, drinks, chutneys). I did **not** invent new
classes. Coverage reality per §4:

- **Adequate Commons supply (≥10 candidates):** biryani, naan, roti, chutney,
  chicken biryani, tandoori chicken, lassi.
- **Thin (1–9):** jalebi, butter chicken, kheer, poha, gulab jamun, samosa,
  laddu, idli, dosa, puri.
- **No Commons category at all:** `masala_dosa`, `matar_paneer`.
- **Commons category exists but 0 permissive files:** dhokla (measured).

The other ~84 classes have unmeasured or unviable permissive supply.

---

## 9. Recommended training strategy (for when data exists)

Not started, and correctly so — nothing is audited or cleared.

- **Backbone: MobileNetV3-Large** (transfer learning, frozen then fine-tuned).
  Best accuracy-per-millisecond for an on-device food scanner; the repo's
  existing 12-class pipeline already fits this shape.
- **ResNeXt-50 / DenseNet-121** only as a stronger offline reference point, if
  accuracy plateaus. They are ~4–8× the inference cost of MobileNetV3 and won't
  suit the app's latency budget.
- **Ensembling is not justified yet.** Ensembling helps when you have ≥100
  images/class of clean data; at 5–20/class it adds cost without signal.
- **Progressive class count:** train a 20–30 class model on well-supported
  dishes first (better per-class volume), then expand. Never present that as
  "100 classes".
- **Split discipline:** duplicate groups together, validation never trained on,
  per-class reporting of what was actually evaluated.
- The existing `training/train_v2.py` path is reusable; the 12-class fallback
  (`models/food_classifier_cc0.pt`, sha256 `f74d10f6…02ad87`) must stay default
  until a replacement beats it on a held-out set.

---

## 10. Remaining permission requirements

1. **Network egress** for `upload.wikimedia.org` → unblocks the only clean source.
2. **Purchase** DataCluster commercial licence → unblocks ~5,000 owned images.
3. **Author request** to FoodLens team → potential 30K images.
4. **Decision** on whether NC data (RASOI) may be used for *evaluation only*.

---

## 11. Honest bottom line

I did not acquire the dataset this mission needs, and I will not dress that up.
The searches were done, the licences were read, and the environment was measured
rather than guessed — but the honest finding is that **the datasets with clean
commercial rights are behind hosts I cannot reach, and the hosts I can reach
contain datasets with no rights at all.**

Success was defined as *"a substantial collection of genuine Indian food images
with defensible usage rights"*. That needs either a purchased licence
(DataCluster) or network egress (Wikimedia), and neither is available to me
inside this sandbox. Everything downstream — integrity audit, duplicates, class
balance, training — is blocked behind that.

The tooling is ready and tested (31 tests, `training/acquire_v2.py`, PR #9). It
will run the moment bytes are reachable.
