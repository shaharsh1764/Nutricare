# NutriCare Food Dataset — Sources, Coverage & Caveats

## What this file is
`data/foods.json` is the **food dataset** shipped with NutriCare (v2.0, ~196 foods, up from 42).
It is loaded into the SQLite `foods` table on first run (see `nutricare/db.py`).
Stable `id` values (1..196) are preserved across releases — meal records reference `food_id`, so original 1–42 remain unchanged.

Every nutrient value is expressed **per 100 g of edible portion** unless the `state` field says otherwise
(`raw` / `dry` / `cooked` / `prepared` explicitly distinguished). Serving sizes
(`serving_desc`, `serving_g`) are common household references used only to pre-fill the
portion input in the UI; all maths is done per-gram (see `nutricare/nutrition.py`).

Each entry also carries:
- `dietary`: explicit booleans for `vegan`, `lacto_vegetarian`, `ovo_vegetarian`, `lacto_ovo_vegetarian`, `non_vegetarian` (eggs classified as non-vegetarian per documented lacto-vegetarian default)
- `allergens`: explicit list from 9 codes (`milk`, `peanut`, `tree_nut`, `soy`, `wheat`, `fish`, `shellfish`, `egg`, `sesame`); missing/ambiguous is never assumed safe
- `source_id`: specific table/ID within the source
- `quality`: `verified` (direct table match) or `approximate` (recipe varies, nearest match)

## Coverage (v2.0)
~196 foods across 10 groups: Breads & Grains (26), Legumes (23), Vegetables (36), Fruits (26), Dairy & Alternatives (19), Protein Foods (22), Indian Prepared (19), Nuts & Seeds (16), Oils & Fats (6), Other (3).
Designed for Indian diet diversity: millets (bajra/jowar/ragi), dals (masoor/moong/urad/toor/chana/moth/horse gram), leafy veg, gourd veg, seasonal fruits, dairy, meat/fish/eggs, and common prepared dishes (sambar/rasam/pav bhaji etc.).

## Sources
| Tag in dataset | Source |
|---|---|
| `USDA FDC` | USDA FoodData Central, https://fdc.nal.usda.gov (SR Legacy / Foundation foods) |
| `IFCT 2017` | Indian Food Composition Tables 2017, National Institute of Nutrition (NIN), Hyderabad, https://www.nin.india.in |
| `... (approx)` | Value rounded/approximated from the nearest matching entry in the source table (e.g. cooked prepared dishes such as idli, dosa, samosa, biryani where home recipes vary) |
| `source_id` field | e.g. `USDA FDC: 168878` or `IFCT 2017: G-12` — specific entry within source |

## Important caveats (also shown in the app UI)
1. Values are **educational approximations**, not laboratory analyses. Prepared Indian dishes vary a lot by recipe, oil amount and brand. `quality: approximate` flags such entries — they are not claimed as verified.
2. Raw vs cooked explicitly distinguished via `state`; do not compare without conversion.
3. The dataset is **not medical or clinical guidance** and must not be used for therapeutic diet planning.
4. Micronutrients tracked are a deliberate small subset (fiber, sodium, potassium, calcium, iron) so the Reports page can demonstrate adequacy maths without pretending to cover all micronutrients.
5. Dietary/allergen metadata is explicit per food; if `allergens` is missing or ambiguous, the insights engine excludes the food when the user's allergy cannot be ruled out — never assumes allergen-free.
6. To extend the dataset, add rows to `foods.json` with new `id` and restart the app; seeding inserts only where `name` not already present and backfills metadata for existing foods.
