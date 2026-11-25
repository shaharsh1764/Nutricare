# NutriCare Food Dataset — Sources, Coverage & Caveats

## Current status (2026-11-15)
`data/foods.json` now contains 313 rows: 272 from the model-coverage audit, eleven generic packaged snacks/drinks with USDA FDC values, eleven prepared dishes, and nineteen **branded** packaged foods and drinks built from published packet labels. The active 80-class primary model and the 12-class technical fallback each resolve to documented foods with nutrient values. The 68 model-coverage additions are representative recipe-derived estimates, not direct laboratory or IFCT/USDA analyses of finished dishes. See [`docs/FOOD_MODEL_NUTRITION_AUDIT.md`](../docs/FOOD_MODEL_NUTRITION_AUDIT.md) and [`model_food_recipe_profiles.json`](model_food_recipe_profiles.json) for class coverage, ingredients, calculation method and limitations. Historical counts and notes below describe earlier releases and are superseded where they conflict with this current status.

### Branded packaged foods and drinks (ids 295–313)

These are the everyday packets people actually log: chips, namkeen, biscuits, instant
noodles and soft drinks. Each row cites the packet or retailer label it was read from in
`source_id`, and each is stored as `quality: approximate` — deliberately **not**
`verified`, because a brand label is not the same evidence class as a USDA or IFCT table
value and it changes between batches, pack sizes and markets.

| Row | Brand label used | Energy per 100 g/ml |
|---|---|---|
| Lay's India's Magic Masala (potato chips) | 52 g pack, BigBasket listing | 539 kcal |
| Kurkure Masala Munch | 100 g pack (UK import of the Indian recipe) | 548 kcal |
| Too Yumm! Multigrain Chips | brand label | 475 kcal |
| Bingo! Mad Angles Achaari Masti | 20 g pack, BigBasket listing | 526 kcal |
| Haldiram's Aloo Bhujia | 200 g pack (EU import) | 554 kcal |
| Parle-G glucose biscuits | 810 g pack label | 454 kcal |
| Britannia Good Day Cashew | 72 g pack label | 517 kcal |
| Maggi 2-Minute Masala noodles | 70 g pack label (India) | 427 kcal |
| Coca-Cola Original Taste | 750 ml pack, BigBasket listing | 42 kcal / 100 ml |
| Diet Coke | 300 ml can label | 0 kcal / 100 ml |
| Coca-Cola Zero Sugar | 300 ml can label | 0 kcal / 100 ml |
| Pepsi | 750 ml pack label | 43 kcal / 100 ml |
| Pepsi Zero Sugar | 300 ml can label | 0 kcal / 100 ml |
| Thums Up | 2 L pack label | 42 kcal / 100 ml |
| Sprite | 6 x 300 ml pack label | 49 kcal / 100 ml |
| Fanta Orange | 2.25 L pack label | 52 kcal / 100 ml |
| Mirinda Orange | 1.5 L pack label | 55 kcal / 100 ml |
| Frooti mango drink | 600 ml pack label | 62.9 kcal / 100 ml |
| Sting energy drink | 250 ml pack label | 28 kcal / 100 ml |

Two honest limits are recorded in each row's `notes` field rather than hidden:

1. **Label versions disagree.** Kurkure prints 548–558 kcal and 613–950 mg sodium across
   packs; Lay's prints 531–555 kcal; Mirinda prints 38–55 kcal in different markets. The
   table stores one named label and says so — it never averages them.
2. **Some nutrients are not printed.** Fibre is absent from the Indian Parle-G, Britannia
   and Bingo panels, and sodium is absent from the Indian Fanta panel. Where a figure is
   not printed it is either stored as 0 with that stated (Bingo fibre) or held at the
   manufacturer's published mid-value and flagged (Fanta sodium). No value is invented.

Sugar-free colas (Diet Coke, Coke Zero Sugar, Pepsi Zero Sugar) are stored with genuine
`0` energy, carbohydrate and fat. Those zeros are printed label zeros, not missing data —
the app already distinguishes the two, and a test pins that behaviour.

## What this file is
`data/foods.json` is the **food dataset** shipped with NutriCare (current version 3.2, 313 foods; earlier v2.x counts are historical).
It is loaded into the SQLite `foods` table on first run (see `nutricare/db.py`).
Stable original IDs 1–203 are preserved across releases — meal records reference `food_id`; later additions use IDs 204 onward, the newest generic packaged rows use IDs 273–294 and branded packets use IDs 295–313. The generic packaged/beverage rows (273–283) are `quality: verified` USDA FDC values; the prepared-dish rows added alongside them are `quality: approximate` recipe estimates, and the branded rows (295–313) are `quality: approximate` because they cite one brand's printed label.

Every nutrient value is expressed **per 100 g of edible portion** unless the `state` field says otherwise
(`raw` / `dry` / `cooked` / `prepared` explicitly distinguished). Serving sizes
(`serving_desc`, `serving_g`) are common household references used only to pre-fill the
portion input in the UI; all maths is done per-gram (see `nutricare/nutrition.py`).

Each entry also carries:
- `dietary`: explicit booleans for `vegan`, `lacto_vegetarian`, `ovo_vegetarian`, `lacto_ovo_vegetarian`, `non_vegetarian` (eggs classified as non-vegetarian per documented lacto-vegetarian default)
- `allergens`: explicit list from 9 codes (`milk`, `peanut`, `tree_nut`, `soy`, `wheat`, `fish`, `shellfish`, `egg`, `sesame`); missing/ambiguous is never assumed safe
- `source_id`: specific table/ID within the source
- `quality`: `verified` (direct table match) or `approximate` (recipe varies, nearest match)

## Added in v2.1

Five taxonomy classes were added with the CC0 12-class model (`kheer`,
`rasgulla`, `chomchom`, `morog_polao`, `luchi`). At v2.1 only kheer and rasgulla
could be given a row; the other three were registered with
`nutrition_source: "unavailable"` so the scanner asked the user rather than
inventing a figure. **v2.2 added recipe-derived rows for chomchom and morog
polao** (see the derivation table below), leaving `luchi` as the only one of the
five mapped to an existing documented row:

| Class | Nutrition | Why |
|---|---|---|
| `kheer` | recipe-derived, approximate | No IFCT/USDA row for kheer; composed from milk + rice + sugar |
| `rasgulla` | recipe-derived, approximate | No IFCT/USDA row; composed from chhena + sugar syrup |
| `chomchom` | recipe-derived, approximate | Composed from chhena + sugar per a stated recipe (v2.2) |
| `morog_polao` | recipe-derived, approximate | Composed from rice + chicken + ghee; deliberately *not* mapped to `Pulao, vegetable`, which is a different dish (v2.2) |
| `luchi` | mapped to `Puri (fried)` + `approx_note` | Closest documented item; both are deep-fried maida/atta breads |

## Recipe-derived rows added in v2.2 (ids 199–203)

Each value is kcal per 100 g of the finished dish, computed from ingredient
weights and the IFCT/USDA-cited ingredient rows already present in
`data/foods.json` (besan 387, maida 364 USDA, potato 87, cooked chana 164,
onion 40, sunflower oil 884, ghee 900 IFCT, sugar 380, cooked rice 130,
chicken curry cut 165 IFCT, tamarind 238 IFCT, mint 44 IFCT, curd 61).

| Row | Finished weight | Composition (abbreviated) | kcal/100 g |
|---|---|---|---|
| Pakora / bhajji | 325 g | 100 g besan + 100 g onion + 50 g potato, deep-fried absorbing ~55 g oil | 294.4 |
| Pani puri (assembled) | 215 g | 100 g suji puris fried in 20 g oil + 60 g potato + 30 g cooked chana + tamarind-mint water | 308.9 |
| Jalebi | 210 g | 100 g maida + 25 g curd, fried (~30 g ghee absorbed), ~55 g sugar absorbed from syrup | 408.7 |
| Morog polao | ~1460 g | 700 g cooked rice + 500 g chicken + 60 g ghee + onion/curd/milk | 162.7 |
| Chomchom | 100 g drained | ~45 g chhena solids + ~40 g sugar | 271.2 |

**These are approximations.** The dominant uncertainty is absorbed fat and sugar,
which vary by technique and vendor; treat them as such rather than as table
values for the named dish.

## Coverage (v2.0)
~196 foods across 10 groups: Breads & Grains (26), Legumes (23), Vegetables (36), Fruits (26), Dairy & Alternatives (19), Protein Foods (22), Indian Prepared (19), Nuts & Seeds (16), Oils & Fats (6), Other (3).
Designed for Indian diet diversity: millets (bajra/jowar/ragi), dals (masoor/moong/urad/toor/chana/moth/horse gram), leafy veg, gourd veg, seasonal fruits, dairy, meat/fish/eggs, and common prepared dishes (sambar/rasam/pav bhaji etc.).

## Sources
| Tag in dataset | Source |
|---|---|
| `USDA FDC` | USDA FoodData Central, https://fdc.nal.usda.gov (SR Legacy / Foundation foods) |
| `IFCT 2017` | Indian Food Composition Tables 2017, National Institute of Nutrition (NIN), Hyderabad, https://www.nin.india.in |
| `Brand label` | The printed nutrition panel of one named brand pack or its retailer listing, named in `source_id`. Stored as `quality: approximate`: flavours, pack sizes and label versions differ, and a packet panel is not a laboratory analysis. |
| `... (approx)` | Value rounded/approximated from the nearest matching entry in the source table (e.g. cooked prepared dishes such as idli, dosa, samosa, biryani where home recipes vary) |
| `Recipe-derived (NutriCare)` | **No IFCT/USDA entry exists.** The value was computed from a stated home recipe and marked `quality: approximate`. Seven rows (ids 197–203): kheer, rasgulla, pakora, pani puri, jalebi, morog polao, chomchom — the latter five added in v2.2 so that all 12 classes of the CC0 model resolve to a documented row. The figure is an estimate for the dish, not a published value for it; what IFCT/USDA actually support are the *ingredient* values the estimate is built from. |
| `source_id` field | e.g. `USDA FDC: 168878` or `IFCT 2017: G-12` — specific entry within source |

## Important caveats (also shown in the app UI)
1. Values are **educational approximations**, not laboratory analyses. Prepared Indian dishes vary a lot by recipe, oil amount and brand. `quality: approximate` flags such entries — they are not claimed as verified. Branded rows carry the brand's own label values, which change between pack sizes, flavours and markets; always prefer the label on the packet in front of you.
2. Raw vs cooked explicitly distinguished via `state`; do not compare without conversion.
3. The dataset is **not medical or clinical guidance** and must not be used for therapeutic diet planning.
4. Micronutrients tracked are a deliberate small subset (fiber, sodium, potassium, calcium, iron) so the Reports page can demonstrate adequacy maths without pretending to cover all micronutrients.
5. Dietary/allergen metadata is explicit per food; if `allergens` is missing or ambiguous, the insights engine excludes the food when the user's allergy cannot be ruled out — never assumes allergen-free.
6. To extend the dataset, add rows to `foods.json` with new `id` and restart the app; seeding inserts only where `name` not already present and backfills metadata for existing foods.
