# Provenance Investigation: SohlHealth `enhanced-indian-food-classification`

**Date:** 2026-11-07
**Question:** Do the 15,404 images carry a valid CC-BY-4.0 grant?
**Answer:** **No.** The images originate from a research dataset that is
published under a **fair-use / non-commercial-research** statement, from images
the authors **crawled from Google and Bing**. The CC-BY-4.0 tag on Hugging Face
is not backed by any rights the uploader holds.

**Status:** Research only. No training. No bulk download.

---

## 0. Summary of findings

| Question | Finding |
|---|---|
| Original source | **IndianFoodNet-30** dataset (Agarwal et al., IJCMEM 2023) on Roboflow |
| Collection method | **Google + Bing image crawl** via JavaScript queries |
| Originators' licence | **"Fair use" / non-commercial research only** — explicitly *not* CC-BY |
| Does CC-BY-4.0 cover the photos? | **No.** The grant is unfounded; the uploader holds no rights to grant |
| 43 classes explained? | **39 of 43** are the union of two *separately scraped* sets |
| README vs `dataset_info.json` | `dataset_info.json` is a leftover from the **object-detection** stage; boxes were flattened away |
| Why 14 classes have exactly 200 | A **cap**, not augmentation — and those 14 classes have **zero** val/test images |
| Split quality | test and validation contain the **same 22 of 43 classes**; 14 classes are untestable |
| Recommended action | **Reject this dataset.** See §8 for the legitimate alternatives |

---

## 1. The original source — found

The provenance is now fully traced. It is **not** an original dataset.

### 1.1 The paper

**IndianFoodNet: Detecting Indian Food Items Using Deep Learning**
Ritu Agarwal, Tanupriya Choudhury, Neelu J. Ahuja, Tanmay Sarkar
*International Journal of Computational Methods and Experimental Measurements*, 11(3), 221–232
DOI: [10.18280/ijcmem.110403](https://doi.org/10.18280/ijcmem.110403) · Received 14 Sep 2023, published 30 Dec 2023

From the paper's methodology (§5.1), verbatim:

> "All relevant food images were gathered in the earlier stage **from the web
> using Google and Bing**. Then, bounding boxes around the measurements of the
> food items were added to them."

> "our dataset, IndianFoodNet, constitutes of more than 5500 images of spreading
> beyond thirty classes of popular Indian food items. Besides, each image in the
> dataset is **resized to 640×640**."

### 1.2 The authors' own dataset page

`https://universe.roboflow.com/indianfoodnet/indianfoodnet` — **IndianFoodNet-30**, created by
Ritu Agarwal, Nikunj Bansal, Tanupriya Choudhury, Tanmay Sarkar, Neelu Jyothi Ahuja.
Dataset v1 = **13,036 images**.

Their stated collection method, verbatim:

> "We used search engines (**Google and Bing**) to crawl and look for suitable
> images using JavaScript queries for each food item … The images with incomplete
> RGB channels were removed … We deployed the EAST text detector to segregate
> such images [with a lot of text]. Finally, a comprehensive manual inspection
> was conducted."

### 1.3 The decisive statement — fair use, not open licence

From the same page, verbatim:

> "**Fair use** — This dataset contains **some copyrighted material whose use has
> not been specifically authorized by the copyright owners**. In an effort to
> advance scientific research, we make this material available for academic
> research. **If you wish to use copyrighted material in our dataset for purposes
> of your own that go beyond non-commercial research and academic purposes, you
> must obtain permission directly from the copyright owner.** We believe this
> constitutes a 'fair use' …"

This is decisive. The people who actually assembled the images say they do **not**
own them and do **not** license them beyond non-commercial research.

---

## 2. Does CC-BY-4.0 genuinely cover the photographs?

**No.** The chain of title breaks at the first link.

```
Photographers (unknown, rights reserved)
        │  crawled without permission
        ▼
IndianFoodNet-30 (Agarwal et al.)  ──► declares FAIR USE / non-commercial research
        │  re-uploaded by an unrelated account
        ▼
SohlHealth/enhanced-indian-food-classification ──► asserts CC-BY-4.0
```

A CC-BY-4.0 licence is a positive grant of rights. The uploader claims to license
redistribution and derivative works. But:

1. The originators state the images are **copyrighted material used under fair use**.
2. The images were **crawled from search engines**, not licensed from photographers.
3. The uploader is **not** the originators (see §3) and therefore holds no rights at all.

So the CC-BY tag is not merely "unverified" — it is **contradicted by the
documented position of the source it came from**. Relying on it would mean
relying on a grant whose issuer had nothing to grant, while the actual rights
holders' terms forbid exactly what we would do (commercial, redistributable
derivative model).

**This is materially worse than the CC0-declared Bangladeshi dataset**, where the
publisher at least made a CC0 dedication. Here the upstream source explicitly says
it is fair use only.

---

## 3. The uploader is not the originator

Commit history of the HF dataset — **8 commits in under 2 hours, one day**:

| Time (2025-08-12) | Commit |
|---|---|
| 18:18 | initial commit |
| 18:29 | Upload README.md |
| 18:29 | Upload dataset_info.json |
| 18:29 | Upload statistics/dataset_stats.json |
| 19:08 | *(repeat)* Upload dataset / card |
| 19:08 | *(repeat)* Upload dataset / card |
| 20:00 | *(repeat)* Upload dataset / card |
| 20:00 | *(repeat)* Upload dataset / card |

No paper, no source link, no attribution, no description of collection. The pattern
is the Hugging Face **web "upload files" flow**, and the author metadata shows
`no-auth` avatar paths.

The account's other dataset, `SohlHealth/sohl-multidish-yolo-dataset`, claims
**MIT over 377 Indian food photographs** with the author given as "SOHL AI Team",
again with no provenance. **A party that applies MIT to photographs it did not
take, and `no-auth` metadata on a second upload, is not a reliable licensor.**

---

## 4. Why the README and `dataset_info.json` disagree

They describe **two different stages of a conversion pipeline**, and the YOLO file
was left behind uncleaned.

| File | Says | Reality |
|---|---|---|
| `README.md` | 15,404 images, 43 classes, `image-classification`, train/val/test | Accurate for the parquet files |
| `dataset_info.json` | `"Indian Food Detection Dataset"`, `"task": "object-detection"`, `"format": "YOLO"`, **`"total_images": 0`**, splits all 0 | Stale leftover from the **detection** stage |

The explanation is structural, not mysterious:

- IndianFoodNet is an **object-detection** dataset — bounding boxes, multiple
  dishes per image.
- To make a *classification* dataset, the boxes must be **discarded** and each
  image assigned a single label.
- `dataset_info.json` is the detection-stage manifest that was never updated.
  Its `total_images: 0` confirms it was never populated with the converted counts.

**Consequence that matters for us:** the bounding-box annotations — and therefore
any genuine multi-food information — were **thrown away**. Images that originally
contained several dishes are now single-labelled. So this dataset cannot support
plate-level (multi-food) recognition either. That is a capability loss, not just a
bookkeeping error.

The `"unified_classes"` key confirms multiple sources were merged into one label
space, which is exactly what §5 shows.

---

## 5. What the 43 classes actually are — 39/43 explained

Comparing the class list against the two scraped sources:

| Source | Classes | Licence | Overlap |
|---|---|---|---|
| IndianFoodNet-30 (paper / Roboflow) | 30 | **fair use, non-commercial** | **26 direct matches** in SohlHealth |
| Kaggle "indian_food_images" (`rajistics`, 20 classes) | 20 | **none**; self-described "extracted from google" | **15 of the 19 extra** classes |
| Unexplained remainder | — | — | 4 (`chicken_curry`, `chole`, `kebab`, `modak` — all near-matches in one of the two) |

**39 of 43 classes** are accounted for as the union of two independently scraped
sets. Neither upstream set carries a licence that permits redistribution.
(The paper's 4 apparent misses — `bhatura`, `kabeb`, `onion pakoda`, `cheela` —
are naming variants of `batter_naan`/`butter_naan`, `kebab`, `pakode`, and an
absent class respectively; so the true overlap is 30/30 or near it.)

---

## 6. Why 14 classes have exactly 200 images

Measured from the Hugging Face datasets-server statistics endpoints (no download):

### 6.1 The 200s are a cap, not augmentation

`dataset_stats.json` gives `total_images: 15404`, and the 43 class counts **sum
exactly to 15,404** — I verified this by summing them myself. So the file is
self-consistent. But its per-class numbers are dataset-wide, and **all 200 of
each capped class sit in `train`**:

| Split | Classes present | Rows |
|---|---|---|
| train | **43** | 13,311 |
| validation | **22** | 1,067 |
| test | **22** | 1,026 |

The 14 classes at exactly 200 (`kebab, chicken_curry, kheer, dum_aloo, ras_malai,
coconut_chutney, green_chutney, aloo_gobi, mutton_curry, ghevar, aloo_masala,
rajma_curry, lassi, fish_curry`) appear **only in train**, with **zero** images in
validation or test. A dataset-wide total of exactly 200 with all 200 in train
means the split stage never touched them.

### 6.2 Augmentation vs duplication — what the evidence supports

Image **dimensions** argue against standard augmentation. If `RandomResizedCrop`
or flips-to-fixed-size had been used to inflate a class, dimensions would be
uniform. They are not:

| Split | min | median | max | images ≥1,592 px |
|---|---|---|---|---|
| train | 148 | **640** | 7,360 | ~250 (4%) |
| validation | 167 | 720 | 7,257 | ~21 |
| test | 190 | 721 | 7,360 | ~17 |

The strong 640 mode matches the paper's "each image resized to 640×640"; the
taller median in val/test matches the second source. This is a **mixture of two
natural image distributions**, not a synthetic one. So the 200s look like a
**subsample/cap at 200 per class**, applied to classes drawn from a source that
had few images.

### 6.3 What I cannot rule out

Dimension statistics **cannot detect byte-identical or near-identical
duplicates**. Confirming "no duplication was used to reach 200" requires hashing
the actual pixels (MD5 + dHash), which needs the image bytes. I am not claiming
that check has been done — it has not, and it is listed in §8 as a precondition
if anyone ever reconsiders this dataset.

**Either way the split is unusable for evaluation:** 14 of 43 classes have no
validation and no test images, so their accuracy could never be measured, and the
provided test split covers only 22 classes.

---

## 7. Practical acquisition without circumventing anything

You asked how to get the parquet files legitimately. Three routes, in order of
practicality. **None of them require circumventing the network policy.**

### Option A — allowlist the CDN hosts (recommended if we ever use it)

`huggingface.co` alone is not enough; image bytes come from the CDN. All of these
must be allowed:

```
huggingface.co
datasets-server.huggingface.co
cdn-lfs.huggingface.co
cdn-lfs-us-1.hf.co
cas-bridge.xethub.hf.co
transfer.xethub.hf.co
```

Parquet shards: `train` ×3 (453 + 489 + 634 MB), `validation` (262 MB),
`test` (259 MB) — ~2.1 GB total. Disk is not a problem (20 GB free).

### Option B — transfer via GitHub (works today, with a real limitation)

- `codeload.github.com` is reachable; I have **admin** on the repo.
- **`objects.githubusercontent.com` is blocked**, so GitHub **Release assets cannot
  be fetched**. Only files committed into a repository *tree* work.
- GitHub rejects files >100 MB, so each parquet shard must be split into ~100 MB
  parts and reassembled by checksum. Use a **disposable scratch repo**, never the
  project repo.

This is workable but wasteful for 2.1 GB, and it would mean you uploading files.

### Option C — no bulk download needed to keep investigating

Worth knowing: I have already read per-split row counts, full per-class
frequencies, per-class image-dimension histograms, and sample image bytes, all
through the public `datasets-server` HTTP API. **Small, targeted verification does
not require the 2.1 GB.** Only training does.

### Bottom line on acquisition

**Do not transfer this dataset.** The blocker is not bandwidth or access — it is
§2. Spending effort to obtain 2.1 GB we cannot lawfully train on would be wasted.

---

## 8. Recommendation

**Reject `SohlHealth/enhanced-indian-food-classification`.**

Reasons, in order of severity:

1. **The licence is contradicted by the source.** Upstream declares fair use /
   non-commercial research only. A downstream CC-BY tag cannot cure that.
2. **The uploader is not the rights holder** and shows other signs of careless
   licensing (MIT over photos in a second dataset, `no-auth` metadata, 8 commits
   in 2 hours, no provenance).
3. **The dataset is structurally broken for evaluation** even setting law aside:
   14/43 classes have no val/test images; the test split covers 22 classes.
4. **It cannot support multi-food recognition** — the bounding boxes were
   discarded in conversion.

### Legitimate routes from here

| Route | What it needs | Assessment |
|---|---|---|
| **A. Build from Wikimedia Commons** | egress to `commons.wikimedia.org` + `upload.wikimedia.org` | **Best option.** Per-file licence metadata (CC0 / CC BY / CC BY-SA), real Indian dish photos, verifiable attribution. Would allow a *defensible* dataset. Requires egress. |
| **B. Ask the IndianFoodNet authors** | email to the corresponding author (`agarwalritu7@gmail.com`) | They can permit academic use, but **cannot** grant commercial redistribution of Google-crawled photos. Useful only for research-only deployment. |
| **C. Accept documented risk** | your explicit sign-off | Would mean shipping a model whose images are known fair-use-only. **I do not recommend it** and it differs in kind from the CC0 case: there, a dedicator at least asserted public domain; here the source says the opposite. |
| **D. License images commercially** | budget + a provider reachable from here | Clean but out of scope. |

**My recommendation: Route A.** Wikimedia Commons is the only path I can see to an
Indian food dataset whose image-level licensing is genuinely verifiable, because
every file page carries an explicit licence and an attributable author. It also
naturally supports a per-class provenance record, which is what your brief asked
for in the first place. It will not reach 150 classes — realistically 30–60
dishes with enough photos each — but it would be *true*.

If you can open egress to `commons.wikimedia.org` and `upload.wikimedia.org`, I
will build and audit that dataset and report exact per-class counts before any
training.

---

## 9. Explicit statements

- **No training has been run.**
- **No bulk download occurred.** All evidence comes from public metadata APIs and
  three sample image responses read over HTTP; nothing was saved to disk.
- The 12-class CC0 model is **untouched** and still the default.
- Prior research (`docs/DATASET_AUDIT_V2.md`, `docs/HF_INDIAN_DATASETS_AUDIT.md`)
  is preserved unmodified.
- I have **not** verified duplicate images in this dataset (§6.3) and make no
  claim about it.
