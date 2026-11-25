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

After the update, **80/80 primary classes and 12/12 fallback classes resolve to rows containing all nine tracked nutrient fields**: energy, protein, carbohydrate, fat, fibre, sodium, potassium, calcium and iron. The food table contained 272 rows at that point; the packaged-food, prepared-dish and branded additions below bring it to 313.

## Packaged foods, drinks and extra dishes (2026-11-15 follow-up)

Two separate additions, kept deliberately distinct because their evidence differs.

### 1. Packaged snacks and drinks — published values

Eleven rows were added with `source: "USDA FDC"` and `quality: "verified"`. Each
`source_id` names the exact USDA FoodData Central SR Legacy record, so any figure can be
checked against the source table:

| Dataset row | FDC record | Energy (per 100 g or 100 ml) |
|---|---|---|
| Potato chips, plain salted (packaged snack) | `USDA FDC: 169677` | 532 kcal |
| Tortilla chips, plain salted (packaged snack) | `USDA FDC: 173143` | 497 kcal |
| Pretzels, hard salted (packaged snack) | `USDA FDC: 167555` | 384 kcal |
| Popcorn, air-popped (plain) | `USDA FDC: 167959` | 387 kcal |
| Chocolate, milk (bar) | `USDA FDC: 167587` | 535 kcal |
| Chocolate, dark 60-69% cocoa | `USDA FDC: 170272` | 579 kcal |
| Sugar, white granulated | `USDA FDC: 169655` | 387 kcal |
| Cola soft drink (regular) | `USDA FDC: 174852` | 42 kcal / 100 ml |
| Lemon-lime soft drink (regular) | `USDA FDC: 173205` | 41 kcal / 100 ml |
| Orange juice (ready to drink) | `USDA FDC: 169920` | 47 kcal / 100 ml |
| Lemon juice (fresh) | `USDA FDC: 167747` | 22 kcal / 100 ml |

Limits that are stated in the app rather than hidden: these are **generic product**
values, not a specific brand's label. Salt, fat and sugar vary between brands and between
markets, and the packaged-food group is broad on purpose. For beverages the reference is
100 ml treated as ~100 g, which is accurate to a few percent for sugary soft drinks.

### 2. Prepared dishes — recipe estimates, not measurements

Eleven prepared dishes were added so that classes which previously had **no** row — or
borrowed a less accurate one — resolve to their own row:

`masala_dosa`, `curd_rice`, `lemon_rice`, `tomato_rice`, `fried_rice`, `dhokla`,
`vada_pav`, `bhel_puri`, `chai`, `kulfi`, `kaathi_rolls` (kathi roll, paneer filling).

Masala dosa previously reused the plain-dosa row with a note that it was a lower bound.
It now has its own ingredient-based estimate (plain dosa, potato filling, oil), so the
scanner no longer under-counts the filling. All eleven carry
`source: "Recipe-derived (NutriCare)"`, `quality: "approximate"` and an `approx_note`,
and each is recorded in `data/model_food_recipe_profiles.json` with ingredient grams per
100 g, salt, water balance and the ingredient row IDs used.

**These are not laboratory analyses.** They are home-style representative recipes; oil
absorption, portion size and regional recipes change the real figure substantially.

### 2b. Branded packets and drinks — label-cited values (ids 295–313)

The generic pass above answers "what is a potato chip"; it does not answer "what is in
the packet in my hand". Nineteen everyday Indian-market packets were added, each carrying
the figures printed on a named label in `source_id`:

* **Chips / namkeen / biscuits:** Lay's India's Magic Masala, Kurkure Masala Munch,
  Too Yumm! Multigrain Chips, Bingo! Mad Angles Achaari Masti, Haldiram's Aloo Bhujia,
  Parle-G glucose biscuits, Britannia Good Day Cashew, Maggi 2-Minute Masala noodles.
* **Drinks:** Coca-Cola Original Taste, Diet Coke, Coca-Cola Zero Sugar, Pepsi,
  Pepsi Zero Sugar, Thums Up, Sprite, Fanta Orange, Mirinda Orange, Frooti, Sting.

These rows are `quality: "approximate"` on purpose, and the distinction matters:

| Evidence class | Example | `quality` |
|---|---|---|
| Laboratory/table value for the generic food | USDA FDC 169677 potato chips | `verified` |
| One brand's printed nutrition panel | Diet Coke 300 ml can | `approximate` |

A packet panel is real published evidence, but it is the evidence for *that* pack. Salt,
oil and sugar differ between flavours, pack sizes, batches and export/domestic recipes; the
same product prints 548, 555 and 558 kcal on different Kurkure labels, 531–555 kcal for
Lay's, and 38–55 kcal for Mirinda. The dataset stores one named label per row and repeats
the ranges in the row's `notes`; it never averages them into a number no label prints.

What the labels do **not** print is not invented. Fibre is absent from the Indian Parle-G,
Britannia and Bingo panels; sodium is absent from the Indian Fanta panel. Bingo fibre is
stored as 0 and said to be undeclared; Fanta sodium is held at the manufacturer's published
"less than 15 mg" mid-value and flagged as approximate. Diet Coke, Coke Zero Sugar and
Pepsi Zero Sugar carry genuine 0 kcal / 0 g carbohydrate label values — stored as `0`, not
`null`, so the UI's "missing vs zero" distinction (already covered by the UI smoke test N7)
keeps working.

Potassium, calcium and iron are not required on Indian packet labels. Those three fields
are stored as `0` for the branded rows rather than borrowed from a different product, and
the rows say so. That keeps the columns honest: a zero here means "not declared on this
label", which is why these rows stay out of the `verified` class used for micronutrient
adequacy maths.

### 3. Still unmapped

The eleven international classes (`pizza`, `burger`, `sandwich`, `pasta`, `noodles`,
`french_fries`, `fried_chicken`, `momos`, `spring_rolls`, `pancakes`, `salad`) still have
no documented row. The scanner continues to ask the person for values instead of
inventing a calorie count; that behaviour is covered by tests.

## Recipe-derived values and limitations

The 68 prepared-dish profiles are **approximate estimates, not direct IFCT/USDA analyses of those finished dishes**. For each profile, ingredient amounts are specified per 100 g finished food. The listed ingredient nutrients come from the existing USDA FoodData Central or IFCT 2017 rows in `data/foods.json`; salt is separately counted as sodium, and the remaining weight is treated as water. The computations are reproducible from the profile file.

Every generated dish row has `source: "Recipe-derived (NutriCare)"` and `quality: "approximate"`; each class also carries an `approx_note`. The results can differ substantially from restaurant or family recipes, especially for sweets, fried foods, cream sauces and oil/salt amounts. Use packaging or a known recipe when available. These values are not clinical or laboratory data and must not be presented as exact.

The additional peanut ingredient row is `USDA FDC 173806` (NDB 16390), dry-roasted peanuts without salt. Its nutrient values are for the ingredient itself; it does not make the Chikki recipe estimate exact.

## Primary model classes that previously had no food mapping

`adhirasam`, `aloo_matar`, `aloo_methi`, `aloo_shimla_mirch`, `aloo_tikki`, `anarsa`, `ariselu`, `bandar_laddu`, `basundi`, `bhindi_masala`, `boondi`, `butter_chicken`, `chhena_kheeri`, `chicken_razala`, `chicken_tikka`, `chicken_tikka_masala`, `chikki`, `daal_baati_churma`, `daal_puri`, `dal_makhani`, `dharwad_pedha`, `double_ka_meetha`, `dum_aloo`, `gajar_ka_halwa`, `gavvalu`, `ghevar`, `gulab_jamun`, `imarti`, `kachori`, `kadai_paneer`, `kajjikaya`, `kakinada_khaja`, `kalakand`, `karela_bharta`, `kofta`, `kuzhi_paniyaram`, `ledikeni`, `litti_chokha`, `lyangcha`, `maach_jhol`, `makki_di_roti_sarson_da_saag`, `malapua`, `misi_roti`, `misti_doi`, `modak`, `mysore_pak`, `paneer_butter_masala`, `pithe`, `poornalu`, `pootharekulu`, `qubani_ka_meetha`, `rabri`, `ras_malai`, `sandesh`, `shankarpali`, `sheer_korma`, `sheera`, `shrikhand`, `sohan_halwa`, `sohan_papdi`, `sutar_feni`, `unni_appam`.

## Model provenance caveat

The primary checkpoint metadata says the 80-class training images have unresolved rights (see `docs/LICENSING_AUDIT.md`). This coverage audit does not change or resolve that issue. The 12-class CC0 checkpoint remains a technical fallback only, not the normal scanner model.
