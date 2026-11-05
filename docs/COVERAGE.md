# Indian food class coverage — what is supported, and on what evidence

This document is the honest answer to "which of the requested Indian dishes can
NutriCare actually recognise, and why are the rest missing?"

Three different things get confused, so they are separated throughout:

| Term | Meaning here |
|---|---|
| **In taxonomy** | The dish exists as a class `nutricare/vision.py` knows about, with a label and a nutrition link. Does **not** imply the model can recognise it. |
| **In a shipped model** | A trained checkpoint outputs that class. |
| **Licence-cleared** | The training images for that class have verified rights permitting both training and redistribution of the derived model. |

A class only counts as *supported* when all three are true.

---

## 1. Environment constraint that shapes everything below

Every image host except GitHub is network-blocked in the build environment used
for this work. Verified unreachable (`000`, i.e. no route):

```
commons.wikimedia.org   upload.wikimedia.org   api.openverse.org   openverse.org
flickr.com              live.staticflickr.com  pixabay.com         pexels.com
unsplash.com            images.pexels.com      cdn.pixabay.com     kaggle.com
gitlab.com              archive.org            zenodo.org          data.gov.in
huggingface.co          raw.githubusercontent.com   download.pytorch.org
```

Reachable: `github.com`, `codeload.github.com`, `api.github.com`.

Practical consequence: Wikimedia Commons alone holds thousands of CC BY / CC0
photographs of exactly the missing dishes (idli, dosa, poha, upma, sambar,
naan, pulao…). Those are the right long-term source, and they are **one network
allowlist entry away**. They could not be fetched here, so no coverage is
claimed for them. This is an infrastructure limit, not a finding that such
images don't exist.

---

## 2. Requested classes — actual status

Legend: ✅ supported (trained + licensed) · ⚠️ trained but thin · ⛔ blocked

| Requested dish | Class status | Evidence |
|---|---|---|
| **Roti / chapati / phulka** | ⛔ blocked | Taxonomy has `roti`. The 20-class model knows it, but that model's images are unlicensed. No CC0 source for roti. |
| **Naan** | ⛔ blocked | Taxonomy has `naan`; no licensed images obtained. |
| **Paratha** | ✅ supported | 441 licensed images (CC0 `Porota`). |
| **Rice** | ⛔ blocked | Taxonomy has `rice_white` / `rice_brown`; no licensed images. |
| **Pulao** | ⛔ blocked | `pulao` in taxonomy. `Morog_polao` is a *chicken* pilaf and was kept as its own class rather than mislabelled as vegetable pulao. |
| **Khichdi** | ✅ supported | 398 licensed images (CC0 `Khichuri`). |
| **Idli** | ⛔ blocked | No licensed source reachable. |
| **Dosa** | ⛔ blocked | No licensed source reachable. |
| **Masala dosa** | ⛔ blocked | No licensed source reachable. |
| **Poha** | ⛔ blocked | No licensed source reachable. |
| **Upma** | ⛔ blocked | No licensed source reachable. |
| **Uttapam** | ⛔ blocked | No licensed source reachable. |
| **Dal** | ⛔ blocked | No licensed source reachable. |
| **Rajma** | ⛔ blocked | No licensed source reachable. |
| **Chole** | ✅ supported | 99 licensed images (CC0 `Chola_bhuna`). Smallest fully-supported curry; watch it. |
| **Paneer dishes** | ⛔ blocked | No licensed source reachable. |
| **Aloo gobi** | ⛔ blocked | No licensed source reachable. |
| **Mixed vegetable sabzi** | ⛔ blocked | No licensed source reachable. |
| **Sambar** | ⛔ blocked | No licensed source reachable. |
| **Biryani** | ✅ supported | 290 licensed images (CC0 `Biryani`). Mapped to `chicken_biryani` because Bangladeshi biryani is a meat biryani. |
| **Samosa** | ⛔ blocked | No licensed source reachable. |
| **Pakora** | ✅ supported | 222 licensed images (CC0 `Beguni` — besan fritter, same family). |
| **Dhokla** | ⛔ blocked | No licensed source reachable. |
| **Kachori** | ⛔ blocked | No licensed source reachable. |
| **Pav bhaji** | ⛔ blocked | No licensed source reachable. |
| **Pani puri** | ✅ supported | 282 licensed images (CC0 `Phuchka`, the Bengali name for the same dish). |
| **Bhel puri** | ⛔ blocked | No licensed source reachable. |

### Also supported (not on the requested list, but licensed and useful)

| Dish | Images after de-dupe | Source folder |
|---|---|---|
| Rasgulla / rosogolla | 444 | `Rosogolla` |
| Curd / dahi | 160 | `Doi` |
| Morog polao (Bengali chicken pilaf) | 128 | `Morog_polao` |
| Chomchom (chhena sweet) | 65 | three chomchom variants merged |
| Kheer / payesh | 21 | `Payesh` |
| Jalebi | 23 | `Jilapi` |

**Supported Indian food classes: 12.** All 12 are licence-cleared CC0 and all 12
are in the shipped default checkpoint:

```
chicken biryani · chole · chomchom · curd/dahi · jalebi · kheer
khichdi · morog polao · pakora · pani puri · paratha · rasgulla
```

Not the 27 requested. Twelve is what the evidence supports, and no more is
claimed. Coverage of the *requested* list is 7 of 27:

| Requested dish | Supported |
|---|---|
| Paratha | ✅ |
| Khichdi | ✅ |
| Chole | ✅ |
| Biryani | ✅ |
| Pakora | ✅ |
| Pani puri | ✅ |
| **Roti, naan, rice, pulao, idli, dosa, masala dosa, poha, upma, uttapam, dal, rajma, paneer, aloo gobi, mixed veg, sambar, samosa, dhokla, kachori, pav bhaji, bhel puri** | ⛔ blocked (§3) |

### Warning: three classes have very thin test support

| Class | Test images | Reported F1 |
|---|---|---|
| chomchom | **4** | 1.000 |
| jalebi | **3** | 1.000 |
| kheer | **3** | 1.000 |

A 3- or 4-image test set cannot support an F1 of 1.000. These three classes each
had only 21–65 images after de-duplication, so the 15% test split left almost
nothing. They are shipped because the dishes are genuinely recognised in
practice, but **no accuracy claim is made for them** and the overall macro F1 is
flattered by their perfect scores. Treat chomchom, jalebi and kheer as
"recognised, not yet measured".

---

## 3. Why the rest are blocked, and exactly what would unblock them

Ranked by effort, easiest first:

1. **Allowlist Wikimedia Commons** (`commons.wikimedia.org`,
   `upload.wikimedia.org`) in the build environment. Their API returns
   licence metadata per file, and most food photographs there are CC BY-SA 4.0
   or CC0. That single change would plausibly cover idli, dosa, masala dosa,
   poha, upma, uttapam, sambar, samosa, dhokla, kachori, pav bhaji, bhel puri,
   naan and pulao. **This is the highest-value next step, and it is
   infrastructure, not research.**
2. **Commission photographs** — roughly 120 images per dish, shot on a phone
   under domestic lighting (which is what the model must handle anyway).
   Cost is the only blocker, and the rights are then unambiguous because
   NutriCare owns them.
3. **Written permission** from a photographer who shoots Indian food, covering:
   training, derivative model distribution, and commercial use if the app is
   ever monetised.

What will *not* unblock anything: another permissively-licensed GitHub repo
full of scraped images. That is exactly the failure mode this project already
paid for once.

---

## 4. Datasets investigated and rejected

Each rejection is a decision, not an oversight.

| Dataset | Declared licence | Why rejected |
|---|---|---|
| `dhruvk2002/food-classifier` (20-class, in the current default model) | **none** | No LICENSE file. Upstream Kaggle listing says "Data files © Original Authors"; published work on the same set says images were "extracted from google". Unresolved — see `LICENSING_AUDIT.md`. |
| `soumen7saha/IndFood-Dataset` (131 classes) | GPL-3.0 on repo | Images derive from Khana, which is **CC BY-NC-ND 4.0** — forbids derivatives and commercial use. A repo-level GPL cannot license third-party photos. |
| `prabhuomkar/Khana` | none | Images crawled from search engines and Swiggy/Zomato. No licence file. |
| `pranavuppuluri/Cooked-Food-Recognition-and-Classification` (8,395 images, 37 Indian dishes) | MIT | The MIT text covers "the Software". The README documents 8,395 images and states **no provenance, no source, no permission** for them. Tempting and unusable — this is the trap the brief warns about. |
| `iamsouravbanerjee/indian-food-images-dataset` (Kaggle) | unverified | Host unreachable for licence inspection; sibling Kaggle food sets are rights-reserved. |
| `Ishmam97/Bangladeshi-Food-Dataset` (44 classes, 8,444 images) | **CC0-1.0** | ✅ **Accepted** — the only source here with an image-level licence permitting commercial use and derivatives. Caveat recorded in §5. |

---

## 5. The accepted source, and its one honest caveat

`github.com/Ishmam97/Bangladeshi-Food-Dataset` — CC0 1.0 Universal, full legal
text committed in the repository.

| Requirement | Position |
|---|---|
| Original source / creator | The repository owner, Ishmam; published as a Bangladeshi food image dataset |
| Licence on the **images** | CC0 1.0 (the repo's `LICENSE` applies to the dataset itself, and CC0 is a public-domain dedication rather than a code licence) |
| Commercial use | Permitted |
| Derivatives / model distribution | Permitted |
| Attribution required | None (given anyway, as good practice) |
| Redistribution of images | Permitted |

### How much of it was actually used

```
Train/ split available                     8,444 images / 44 classes
mapped to a NutriCare class                3,247 images / 12 classes
after global de-duplication                2,573 images  (dropped 170 exact
                                                         + 504 near-duplicate)
final split                                train 1,778 · val 380 · test 380
```

De-duplication removed **21%** of the mapped images. That is not housekeeping —
those were redundant frames of the same plate, and leaving them in is exactly
what inflated the earlier 7-class model by ~+0.007.

**Caveat, stated rather than buried:** CC0 can only waive rights the dedicator
actually holds. The README describes images "collected from diverse real-world
sources (homes, restaurants, markets, and online platforms)", so chain-of-title
is asserted by the publisher, not proven by them. This is still materially
stronger than every alternative here: an explicit public-domain dedication is a
representation the publisher is accountable for, whereas an unlicensed scrape is
nobody's promise at all.

---

## 6. Historical checkpoint

The first CC0 model (`models/food_classifier_cc0_7class.pt`) is retained for
comparison: 7 classes, 0.8609 test accuracy, 0.8539 on its leak-free subset,
160 px input. It was superseded by the 12-class model and is **not** the default,
but nothing was deleted — reproduce or compare it with
`NUTRICARE_MODEL=models/food_classifier_cc0_7class.pt`.

## 7. Nutrition coverage for the supported classes

Recognition and nutrition are separate. No value is invented anywhere.

| Class | Documented nutrition row | Behaviour when scanned |
|---|---|---|
| Paratha | `Paratha, plain (cooked)` — IFCT 2017 | calories shown |
| Khichdi | `Khichdi (cooked)` — IFCT 2017 | calories shown |
| Chole | `Chole / chana masala (prepared)` — IFCT 2017 | calories shown |
| Chicken biryani | `Chicken biryani` — IFCT 2017 | calories shown |
| Curd / dahi | `Curd / dahi (plain, whole milk)` — IFCT 2017 | calories shown |
| Rasgulla | `Rasgulla / rosogolla (prepared)` — **approximate**, recipe-derived | calories shown, flagged approximate |
| Pani puri | none | **asks the user** for values |
| Pakora | none | **asks the user** |
| Chomchom | none | **asks the user** |
| Morog polao | none | **asks the user** (deliberately not mapped to vegetable pulao) |

Portion weight is never inferred from the image; it stays user-adjustable.
