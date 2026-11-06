# Third-party notices

NutriCare bundles or derives from the following third-party works. Licence texts
are reproduced here as those licences require.

---

## 1. MobileNetV3 PyTorch pretrained weights

**Used for:** the ImageNet-pretrained backbone of `models/food_classifier*.pt`.

| | |
|---|---|
| Source | https://github.com/d-li14/mobilenetv3.pytorch |
| File | `pretrained/mobilenetv3-small-55df8e1f.pth` |
| Licence | **MIT** |
| Copyright | © 2019 Duo Li |

Modifications made by this project: the checkpoint was converted from the
author's key layout into torchvision's layout, and 18 1×1 convolutions stored as
`nn.Linear` were reshaped to `nn.Conv2d` form (`training/load_imagenet_backbone.py`).
The classification head was then replaced and fine-tuned on food images.

```
MIT License

Copyright (c) 2019 Duo Li

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

**Reference:** A. Howard et al., *Searching for MobileNetV3*, ICCV 2019.

---

## 2. PyTorch / torchvision / Pillow

Runtime dependencies (`requirements-ml.txt`), used unmodified under their own
licences: PyTorch (BSD-3-Clause), torchvision (BSD-3-Clause), Pillow (MIT-CMU).
Not vendored into this repository.

---

## 3. Training image datasets

### 3a. 20-class model — REMOVED, not distributed

Source: https://github.com/dhruvk2002/food-classifier, which in turn names the
Kaggle "Indian Food Classification" dataset (`l33tc0d3r`).

**This repository declares no licence.** Its `LICENSE` file does not exist; the
Kaggle listing says "Data files © Original Authors", and published work using
the same set states the images were extracted from Google. No permission to
train, redistribute, or distribute a derivative model has been established.

The checkpoint trained on those images (`models/food_classifier.pt`) has been
**removed from this repository and from its git history**. It is not distributed
here in any form. The note is kept so the decision is auditable rather than
silent. See `docs/LICENSING_AUDIT.md`.

Two checkpoints trained on a CC0-declared dataset are shipped. Both derive from
the same source and carry the same position, which is stated precisely once here
and applied identically below.

### What "CC0-declared" does and does not mean

**What we verified:** the dataset repository
(`github.com/Ishmam97/Bangladeshi-Food-Dataset`) contains a CC0 1.0 Universal
dedication covering the dataset, and its own README describes how the images
were collected. That is the publisher's declaration.

**What we did NOT verify:** that the publisher held the rights to every
underlying photograph. The README says images were collected from "diverse
real-world sources (homes, restaurants, markets, and online platforms)". CC0 can
only waive rights the dedicator actually holds, and we have no chain-of-title
evidence for individual photographs, no contributor agreements, and no
independent confirmation of authorship.

So the accurate statement is:

> The dataset publisher declares CC0 1.0. Underlying image ownership and the
> publisher's authority to dedicate those rights have **not** been independently
> verified.

Practical consequence, stated plainly:

- NutriCare holds a documented, publisher-level public-domain dedication — a
  materially better position than an unlicensed scrape, and the strongest
  position available without commissioning photography.
- That is **not** a guarantee that redistribution is lawful, and **not** a
  statement that legal risk is zero.
- Anyone redistributing these models **commercially** should treat this as an
  unresolved chain-of-title question and obtain their own assurance.

### 3b. `models/food_classifier_cc0.pt` — 12 classes — CC0-DECLARED (default model)

| | |
|---|---|
| Source | https://github.com/Ishmam97/Bangladeshi-Food-Dataset |
| Licence | **CC0 1.0 Universal — declared by the dataset publisher** (not independently verified at image level) |
| Classes | chicken biryani, chole, chomchom, curd/dahi, jalebi, kheer, khichdi, morog polao, pakora, pani puri, paratha, rasgulla |
| Images used | 2,573 after de-duplication, from 3,247 offered; `Train/` split, mapped to 12 NutriCare classes |

CC0 1.0 waives copyright and related rights worldwide, permitting use,
reproduction, modification and distribution including commercially, without
attribution. That is what the licence *says*; whether the dedicator had the
authority to apply it to every image is the unverified part described above.
Attribution is given here as good practice.

This checkpoint is the **default** model shipped by the application.

**Caveat, stated plainly:** see "What CC0-declared does and does not mean"
above. Chain-of-title is asserted by the publisher, not proven by us.

### 3c. `models/food_classifier_cc0_7class.pt` — 7 classes — CC0-DECLARED (alternative)

The first CC0 run, kept for comparison and reachable with
`NUTRICARE_MODEL=models/food_classifier_cc0_7class.pt`.

| | |
|---|---|
| Source | https://github.com/Ishmam97/Bangladeshi-Food-Dataset |
| Licence | **CC0 1.0 Universal — declared by the dataset publisher** (not independently verified at image level) |
| Classes | chicken biryani, curd/dahi, jalebi, khichdi, pakora, pani puri, paratha |
| Images used | 2,083 from the `Train/` split, mapped to 7 NutriCare classes |

Same position as 3b, including the unverified-authority caveat.

---

## 4. Nutrition data

`data/foods.json` values are sourced from **IFCT 2017** (Indian Food Composition
Tables, NIN Hyderabad) and **USDA FoodData Central**, per-row `source` and
`source_id` fields.

Seven rows are tagged `Recipe-derived (NutriCare)` and `quality: approximate`.
For these dishes **no IFCT/USDA entry for the finished dish exists**, so the
value is computed from a stated home recipe using the IFCT/USDA-cited ingredient
rows already in this dataset. The full recipe and the arithmetic are recorded in
each row's `source_id`, and the app shows an "Approximation" notice with an
`approx_note`.

| id | Row | kcal / 100 g | Reference serving |
|---|---|---|---|
| 197 | Kheer, milk-rice (prepared) | 180 | 1 bowl (150 g) |
| 198 | Rasgulla / rosogolla (prepared) | 186 | 2 pieces (100 g) |
| 199 | Pakora / bhajji (mixed vegetable, fried) | 294.4 | 4 pieces (80 g) |
| 200 | Pani puri (assembled, with filling and water) | 308.9 | 6 puris (120 g) |
| 201 | Jalebi (fried, syrup-soaked) | 408.7 | 2 pieces (60 g) |
| 202 | Morog polao (Bengali chicken pilaf, prepared) | 162.7 | 1 plate (200 g) |
| 203 | Chomchom (chhena sweet, prepared) | 271.2 | 1 piece (50 g) |

These are **estimates, not measurements of the dish as served**. Oil absorption,
portioning and shop-to-shop recipe variation are large; a real plate can differ
substantially. No claim is made that IFCT or USDA published these figures — they
published the *ingredient* values the estimates are built from. See
`data/SOURCES.md` for the per-row derivation.

---

## 5. Fonts

The UI references **Plus Jakarta Sans** via Google Fonts. It is not vendored;
it is loaded under the SIL Open Font License 1.1 at runtime.
