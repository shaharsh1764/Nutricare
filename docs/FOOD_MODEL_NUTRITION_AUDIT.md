# Food-model / nutrition coverage audit

**Audit date:** 2026-11-20  
**Scope:** Class labels emitted by the shipped primary scanner model and its technical fallback, compared with the documented food table.

## Findings

The active primary model is the **80-class** checkpoint `models/v2/food_classifier_indian_80_224.pt`. Its authoritative output labels are `class_names` in `models/v2/food_classifier_indian_80_224.metrics.json`; the old `trained_model_coverage` metadata in `data/food_classes.json` incorrectly described an older 20-class model.

Before this audit, only **18 of the 80 primary classes** resolved to a food row. **62 classes had no documented food or nutrition row**. Classes that did resolve could share broad proxies: for example, several different rice puddings all pointed to one kheer row, and Navrattan Korma pointed to generic mixed vegetable curry. The technical-only 12-class CC0 fallback did resolve all 12 of its outputs already.

The image classifier predicts a food label; it does **not** learn calories or nutrients. Nutrition is still looked up in `data/foods.json` and scaled by portion weight.

## Changes made

- Added 62 prepared-food rows for the previously uncovered primary classes.
- Added six class-specific rows to replace overly broad mappings for generic biryani, Chak Hao Kheer, Doodhpak, Phirni, Navrattan Korma and plain Lassi.
- Added the USDA dry-roasted peanut ingredient row used by the Chikki recipe profile.
- Updated `data/food_classes.json` to map every primary output to a named food row; corrected primary-model metadata to the actual 80-class checkpoint and recorded fallback coverage separately.
- Added `data/model_food_recipe_profiles.json`, which records each representative ingredient composition, water/salt contribution, per-100-g results and the ingredient-row IDs used.

After the update, **80/80 primary classes and 12/12 fallback classes resolve to rows containing all nine tracked nutrient fields**: energy, protein, carbohydrate, fat, fibre, sodium, potassium, calcium and iron. The food table contains 272 rows.

## Recipe-derived values and limitations

The 68 prepared-dish profiles are **approximate estimates, not direct IFCT/USDA analyses of those finished dishes**. For each profile, ingredient amounts are specified per 100 g finished food. The listed ingredient nutrients come from the existing USDA FoodData Central or IFCT 2017 rows in `data/foods.json`; salt is separately counted as sodium, and the remaining weight is treated as water. The computations are reproducible from the profile file.

Every generated dish row has `source: "Recipe-derived (NutriCare)"` and `quality: "approximate"`; each class also carries an `approx_note`. The results can differ substantially from restaurant or family recipes, especially for sweets, fried foods, cream sauces and oil/salt amounts. Use packaging or a known recipe when available. These values are not clinical or laboratory data and must not be presented as exact.

The additional peanut ingredient row is `USDA FDC 173806` (NDB 16390), dry-roasted peanuts without salt. Its nutrient values are for the ingredient itself; it does not make the Chikki recipe estimate exact.

## Primary model classes that previously had no food mapping

`adhirasam`, `aloo_matar`, `aloo_methi`, `aloo_shimla_mirch`, `aloo_tikki`, `anarsa`, `ariselu`, `bandar_laddu`, `basundi`, `bhindi_masala`, `boondi`, `butter_chicken`, `chhena_kheeri`, `chicken_razala`, `chicken_tikka`, `chicken_tikka_masala`, `chikki`, `daal_baati_churma`, `daal_puri`, `dal_makhani`, `dharwad_pedha`, `double_ka_meetha`, `dum_aloo`, `gajar_ka_halwa`, `gavvalu`, `ghevar`, `gulab_jamun`, `imarti`, `kachori`, `kadai_paneer`, `kajjikaya`, `kakinada_khaja`, `kalakand`, `karela_bharta`, `kofta`, `kuzhi_paniyaram`, `ledikeni`, `litti_chokha`, `lyangcha`, `maach_jhol`, `makki_di_roti_sarson_da_saag`, `malapua`, `misi_roti`, `misti_doi`, `modak`, `mysore_pak`, `paneer_butter_masala`, `pithe`, `poornalu`, `pootharekulu`, `qubani_ka_meetha`, `rabri`, `ras_malai`, `sandesh`, `shankarpali`, `sheer_korma`, `sheera`, `shrikhand`, `sohan_halwa`, `sohan_papdi`, `sutar_feni`, `unni_appam`.

## Model provenance caveat

The primary checkpoint metadata says the 80-class training images have unresolved rights (see `docs/LICENSING_AUDIT.md`). This coverage audit does not change or resolve that issue. The 12-class CC0 checkpoint remains a technical fallback only, not the normal scanner model.
