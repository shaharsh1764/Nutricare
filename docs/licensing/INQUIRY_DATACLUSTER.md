# Licensing Inquiry — DataCluster Labs Pvt Ltd

**Status: DRAFT — NOT SENT.** Awaiting owner approval before any contact.
**Prepared:** 2026-11-05
**Prepared by:** NutriCare project (Indian Food Recognition V2)

---

## Vendor contact (verified from vendor's own site)

| Field | Value | Source |
|---|---|---|
| Sales email | **sales@datacluster.ai** | `datacluster.ai` footer + `/contact.html` |
| Contact page | https://www.datacluster.ai/contact.html | vendor site |
| Website | https://www.datacluster.ai | vendor site |
| Location | Bangalore, India | vendor site |
| Stated response time | "within two business days" | `/contact.html` |
| Booking link | https://calendar.app.google/frgiBFeAkemKsK7XA | vendor site |
| Legal entity | DataCluster Labs Pvt Ltd | Hugging Face org `Dataclusterlabspvtltd` |
| Kaggle | https://www.kaggle.com/dataclusterlabs | vendor |
| Hugging Face | https://huggingface.co/Dataclusterlabspvtltd | vendor |

**Recommended sender:** the project owner's own address (not an agent).
**Subject line:** `Licensing inquiry — Indian Food Image Dataset — commercial model deployment`

---

## Email body (ready to send)

> Dear DataCluster Labs team,
>
> We are building NutriCare, a mobile application that identifies Indian dishes
> from photographs to estimate nutrition. We are expanding our food-recognition
> model from 12 to a target of 100 Indian dish classes, and we need training
> imagery whose rights are unambiguous, because the resulting model will be
> distributed commercially inside the app.
>
> We are interested in your **Indian Food Image Dataset**. Before requesting a
> quote, we would like to establish whether the licence you offer meets our
> requirements. Our questions:
>
> **1. Dataset contents**
> - How many images does the full (non-sample) Indian Food Image Dataset contain?
>   Your GitHub repository describes "approx. 3500 unique images", while the
>   Kaggle card for the same dataset lists "1000+ images" and a 1.5 GB archive
>   with a 1000-file `food_dataset` folder. Which figure reflects the licensed
>   dataset today?
> - Please provide the **class list with per-class image counts**. In particular,
>   how many distinct dish classes exist, and what is the minimum/maximum image
>   count per class?
> - Are images multi-label (several dishes per photo) or single-label? Your
>   descriptions mention both "classification and detection annotations" and
>   "multiple category annotations". We would need single-dish labels, or the
>   bounding boxes necessary to derive them.
> - Which annotation formats ship with the licensed set (COCO / YOLO /
>   Pascal VOC / TF-Record)?
> - Could you share 5–10 sample images with their annotations for evaluation?
>
> **2. Licence scope — the critical questions**
> - We note that your public **sample** datasets on Hugging Face are licensed
>   **CC BY-NC-ND 4.0**, with the explicit statement *"No use in training
>   commercial ML models."* Is the same restriction applied to the Indian Food
>   Image Dataset, or can a commercial training licence be purchased for it?
> - Does a commercial licence permit **training** a model on the images?
> - Does it permit **distributing the trained model weights** (a `.onnx` /
>   `.tflite` / `.pt` artefact) inside a commercially distributed application?
> - Does it permit **deploying that model as a hosted SaaS inference endpoint**,
>   where end users send photographs to our server?
> - Are there any restrictions on **derived or modified datasets** (e.g.
>   re-cropping, relabelling, merging with our own images)?
> - Is redistribution of the original images or of derivatives permitted, or is
>   the licence limited to internal training use?
> - Is the licence **perpetual**, or time-limited and renewable?
> - Does the licence cover **worldwide** use?
> - Are the images **model-release-safe** — i.e. you can confirm you hold the
>   contributor rights necessary to grant us these permissions, given they were
>   crowdsourced from 800+ contributors?
>
> **3. Commercial terms**
> - What is the **price** for a commercial licence covering the full dataset?
>   Please quote per licence tier if pricing depends on company size, revenue or
>   deployment scope.
> - Is pricing one-off or subscription? Any annual renewal?
> - Do you offer a **discounted or staged option** for a startup/small team?
> - Is there a **custom collection** option if specific dish classes are missing?
>   If so, what is the per-image or per-class cost?
>
> **4. Attribution**
> - What attribution wording do you require in the app's credits/licences
>   screen and in any academic output?
>
> **5. Evaluation copy**
> - May we receive a small evaluation subset under the CC BY-NC-ND sample terms
>   in order to assess label quality and image relevance **without** using it for
>   training, while commercial terms are discussed?
>
> We are also open to a short call if that is easier.
>
> Thank you,
> [Name]
> [Role], NutriCare
> [Email] · [Phone]

---

## What we already know (so the reply can be checked against it)

| Claim | Evidence | Confidence |
|---|---|---|
| Images exclusively owned by DataCluster, not scraped | *"The images in this dataset are exclusively owned by Data Cluster Labs and were not downloaded from the internet."* — Kaggle + Roboflow cards | **Stated by vendor; unverified** |
| Crowd-captured by 800+ contributors, 800+ cities, mobile phones 2020–2021 | Kaggle data card | stated |
| 99% HD (1920×1080+) | Kaggle data card | stated |
| ~3,500 unique images | GitHub `datacluster-labs/Indian-Food-Image-Dataset` README | **conflicts with Kaggle's "1000+"** |
| 1000+ images, 1.5 GB, v4 | Kaggle dataset page folder listing | observational |
| Annotation formats COCO/YOLO/VOC/TF-Record | Kaggle card | stated |
| Class list | **not published anywhere** | — |
| Price | **not published anywhere** | — |
| Sample licence | CC BY-NC-ND 4.0 (vehicle, number-plate samples) | from HF cards |
| Usability rating 8.13 | Kaggle | Kaggle's own metric, not a rights signal |

**Red flags to resolve before paying:**
1. **The 3,500 vs 1,000+ discrepancy.** Two vendor-controlled pages disagree by
   3.5×. That is precisely the "advertised total ≠ usable count" trap.
2. **The sample licence forbids commercial ML training.** If the food set is
   released on the same terms, the CC BY-NC-ND label on Kaggle makes the public
   copy unusable for us regardless of what it looks like.
3. **Kaggle metadata says "Data files © Original Authors"**, not CC0 — consistent
   with the vendor retaining all rights. (Some *other* DataCluster datasets
   display "CC0: Public Domain"; that inconsistency across their own listings is
   itself a reason to get terms in writing.)
4. **Crowdsourced provenance.** "800+ contributors" means the vendor must have a
   contributor agreement assigning rights. Ask for confirmation in writing.
