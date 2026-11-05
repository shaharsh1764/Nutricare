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

### 3a. `models/food_classifier.pt` — 20 Indian classes — ⚠️ NOT CLEARED

Source: https://github.com/dhruvk2002/food-classifier, which in turn names the
Kaggle "Indian Food Classification" dataset (`l33tc0d3r`).

**This repository declares no licence.** Its `LICENSE` file does not exist; the
Kaggle listing says "Data files © Original Authors", and published work using
the same set states the images were extracted from Google. No permission to
train, redistribute, or distribute a derivative model has been established.

**Do not redistribute this checkpoint commercially.** It is retained only as a
research artifact and for comparison. See `docs/LICENSING_AUDIT.md`.

### 3b. `models/food_classifier_cc0.pt` — 12 classes — CLEARED (default model)

| | |
|---|---|
| Source | https://github.com/Ishmam97/Bangladeshi-Food-Dataset |
| Licence | **CC0 1.0 Universal** (public domain dedication) |
| Classes | chicken biryani, chole, chomchom, curd/dahi, jalebi, kheer, khichdi, morog polao, pakora, pani puri, paratha, rasgulla |
| Images used | 2,573 after de-duplication, from 3,247 offered; `Train/` split, mapped to 12 NutriCare classes |

CC0 waives copyright and related rights worldwide, permitting use, reproduction,
modification and distribution — including commercially and including derivative
works — without attribution. Attribution is given here as good practice.

This checkpoint is the **default** model shipped by the application.

**Caveat, stated plainly:** CC0 can only waive rights the dedicator actually
holds. The dataset README describes images "collected from ... online
platforms", so chain-of-title is asserted, not proven. This is the strongest
position available without commissioned photography, and is materially better
than an explicitly rights-reserved source.

---

## 4. Nutrition data

`data/foods.json` values are sourced from **IFCT 2017** (Indian Food Composition
Tables, NIN Hyderabad) and **USDA FoodData Central**, per-row `source` and
`source_id` fields. See `data/SOURCES.md`.

---

## 5. Fonts

The UI references **Plus Jakarta Sans** via Google Fonts. It is not vendored;
it is loaded under the SIL Open Font License 1.1 at runtime.
