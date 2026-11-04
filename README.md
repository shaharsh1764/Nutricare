# NutriCare — Nutrition Tracker & Personal Health Assistant

A working full-stack web app built from the Google Stitch designs in `uploads/`
(six screens: Dashboard, Nutrition Tracker, Health Profile, Health Assistant,
Reports, Settings).

* **Backend:** Python + Flask (a small, beginner-friendly web framework)
* **Database:** SQLite — a single file, no server to install
* **Frontend:** plain HTML/CSS/JavaScript served by Flask (no build step, no node needed)
* **Tests:** `pytest` (98 tests: 68 original + 30 Smart Nutrition Insights) + a Node UI smoke harness (55 checks: A–K)

---

## 1. Run it (5 minutes)

You need **Python 3.10 or newer**. Check with `python3 --version` (or `python --version` on Windows).

```bash
# 1) go to the project folder
cd nutricare

# 2) create a private Python environment (one time)
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3) install the two dependencies (one time)
pip install -r requirements.txt

# 4) create your secret settings file (one time)
cp .env.example .env               # Windows: copy .env.example .env
#    open .env in any text editor and change SECRET_KEY to any long random text

# 5) start the app
python app.py
```

Then open **http://localhost:5000** in your browser. That's it — the database
file and sample data are created automatically on first start.

Useful variants:

```bash
PORT=5001 python app.py        # if port 5000 is busy
NUTRICARE_DEMO=0 python app.py # start with an EMPTY profile (no sample day)
```

Stop the server with `Ctrl+C`.

## 2. Run the tests

```bash
python -m pytest tests/ -q        # 98 backend tests (math, safety, API, persistence, Insights)
python app.py &                   # start the server in another terminal, then:
node tests/ui_smoke.js            # 55 UI checks (workflows A–K) against the running server
```

`tests/ui_smoke.js` needs Node only for testing; the app itself does not need Node.

## 3. What is where

| Path | What it is |
|---|---|
| `app.py` | entry point (`python app.py`) |
| `nutricare/api.py` | all REST endpoints (`/api/...`) with input validation (Insights uses two read-only GETs) |
| `nutricare/nutrition.py` | calorie/macro maths (Mifflin-St Jeor, PAL factors, 4/4/9) |
| `nutricare/insights.py` | Smart Nutrition Insights analytics (read-only, pure functions) |
| `nutricare/assistant.py` | Health Assistant rule engine + emergency red-flag screen |
| `nutricare/db.py` | SQLite schema, seeding, purge |
| `static/`, `templates/` | frontend (CSS design system, JS views, SVG charts) |
| `data/foods.json` | sample food dataset (42 foods, per-100 g values) |
| `data/SOURCES.md` | **documented sources** (USDA FoodData Central, IFCT 2017) + caveats |
| `instance/nutricare.db` | **the database** (created on first run; delete to reset) |
| `tests/` | pytest suite + Node UI smoke harness |

## 4. How the numbers are calculated

* **BMR** — Mifflin-St Jeor: `10×kg + 6.25×cm − 5×age + 5 (male) / −161 (female)`
* **Daily target** — BMR × activity factor (1.2…1.9) ± goal adjustment (±300 kcal)
* **Macro grams** — calorie share (e.g. balanced = 40% carbs / 25% protein / 35% fat)
  divided by 4 / 4 / 9 kcal per gram
* **Meal nutrition** — dataset values are per 100 g; portion grams =
  servings × serving size (or grams directly), then linear scaling
* **Micronutrients** — tracked subset only: fiber, sodium, potassium, calcium, iron

## 5. Health Assistant — safety rules baked in

1. Emergency warning signs (chest pain, stroke signs, breathing trouble, self-harm…)
   are screened by an **independent function** (`screen_red_flags`) from both an
   explicit on-form checklist and all free text; they always win over everything
   else, and unticking one sign removes only that sign's flag.
2. What you reported (`reported_facts`) is displayed separately from
   `possibilities` — keyword-selected general education entries that never assert
   mechanisms (e.g. fatigue alone is never explained by glucose, deficiency or
   dehydration; tests enforce this).
3. Outputs are labelled *possibilities*, never diagnoses; **no disease
   probabilities and no medication doses are ever produced** (there are tests for this).
3. Every result carries limitations, "when to seek care" criteria, references
   (NHS / CDC / Harvard Health / AAFP) and a disclaimer.
4. The engine is honestly labelled in the UI: **offline rule-based engine**.
   No AI API is called; if you later add `ASSISTANT_API_KEY` to `.env`, the UI
   still says the local safety engine is what runs (v1 behaviour).

## 6. First run, empty states & demo mode

* A brand-new install shows the **onboarding wizard** (welcome → about you →
  consent-based optional fields → optional goals). Only the display name is
  required; everything else can be skipped and finished later in Health Profile.
  Entered values are preserved across Back/Next, and required-field and range
  checks (age 10–120, height 50–250 cm, weight 20–300 kg) block advancing with
  an inline message — without discarding anything else you typed.
* **Skip for now** opens Guest mode on a fully working dashboard immediately:
  logging, the assistant, reports and settings all function. Only personalised
  targets are missing, and the UI explains that instead of inventing numbers.
  Skipping **restores the device's existing Guest profile** (the most recent
  one, same as its "Continue as Guest" button) and creates a new Guest only if
  the device has never had one — repeated skips never pile up duplicates.
* **Finish** saves the profile on the server *first*, confirms with a toast, then
  redirects to the dashboard. **Refreshing keeps you on your profile**: the
  session cookie is `SameSite=Lax`, and if a browser (e.g. an embedded preview)
  still drops it, the app re-attaches the remembered local profile id on next
  load — no empty guest view, no loops. Returning visitors also see
  **Continue as …** buttons for existing local profiles, so reopening the app
  never orphans or overwrites saved records.
* Every new account starts **genuinely empty**: no sample meals, no fake totals,
  no prefilled symptom history. Empty logs show honest messages ("an empty log
  never means zero intake"), charts stay blank until real data exists, and
  targets appear only when age + sex + height + weight are set — labelled
  *estimates*.
* Fictional data exists **only** behind Settings → *Demo mode*, which is refused
  if the profile already has real logs and puts a persistent amber banner on the
  whole app while on.

## 7. Privacy, local profiles & honest limitations

* **Local profiles, not accounts.** Profiles (top-right avatar → *Local profiles*)
  keep each person's meals/water/symptom records separate in the SQLite file, and
  two browsers on one machine get two separate profiles via session cookies.
* **There is no authentication and no encryption.** Anyone using the same browser
  can switch profiles. This is data *organisation* for a shared device — it is
  **not** security, and the app says so in the UI (Settings and onboarding).
  The device-local "remembered profile" re-attach on refresh is a convenience,
  not a security boundary. Real multi-user protection would require login
  infrastructure this project deliberately does not fake.
* Settings → export everything as JSON; Reports → CSV export.
* Profile or Settings → **delete all my data** purges that profile's meals, water,
  assessments and profile fields (food dataset stays; it isn't personal data).
  Deleting a profile removes only that profile's rows.
* Upgrading from the old single-user version migrates existing records under
  local profile #1 automatically.

## 8. Smart Nutrition Insights

Dashboard → **Smart Nutrition Insights** appears on every logged-in dashboard view. Its numbers come only from
your own `meal_entries`/`water_logs` and the built-in food dataset — missing days are labelled **missing**, never
averaged as zero; targets stay labelled *estimates* (from `nutrition.calorie_target` / `macro_targets`); food
suggestions are only from `data/foods.json`, filtered against your recorded allergies and dietary preferences.

* **Daily metrics:** 5 cards — calories, protein, carbs, fat, water — each with value / target / % and a bar.
* **Daily insights:** protein-below / fibre-below / calcium-/iron-below / hydration / variety cards; gaps carry up to 3 dataset foods with `contribution`, `serving_desc`, `why`. Fibre/micronutrient cards require ≥1 dataset-backed meal (custom entries have no fibre data).
* **Food recommendations:** per-serving ranking from the dataset; allergy vocab covers common keywords (milk/dairy/lactose/casein/whey, egg, soy, nut/peanut, gluten) matched against food names **and** the `grp` metadata (e.g. `Dairy & Alternatives` reliably indicates dairy; `Oils & Fats` + `ghee` indicates milk-derived fat) — not name substring alone. Vegetarian is **lacto-vegetarian**: excludes meat/fish/poultry and **eggs** (eggs are classified as non-vegetarian; ovo-vegetarian users should manage eggs via allergy preferences), while allowing dairy; vegan further excludes dairy/egg/honey. Every recommendation carries its group and a `why` sentence; when every source is filtered, a note is shown instead of an unsafe suggestion.
* **Weekly summary:** averages over logged days only (7-day window, with a 14-day view for previous-week comparison), top foods, distinct food groups, pattern cards (consistently above/below thresholds — only from ≥3 logged days), and a previous-vs-current comparison table (shown only when **both** weeks have ≥3 logged days; otherwise an honest “insufficient data” note).
* **Safety wording:** no diagnosis, no deficiency claim, no prescribed diet; daily/weekly payloads carry the `disclaimer` and `missing_days_note`; `limitation_note` explains non-personalised mode when age/sex/height/weight are missing.
* **States:** empty → honest \"no records\" card; loading → placeholder; error → retry button. Water goal is the user's Settings value.

Endpoints: `GET /api/insights[?date=YYYY-MM-DD]`, `GET /api/insights/weekly` — both 401 without a session, both read-only per-user (`WHERE user_id = ?`).

## 9. Known limitations (honest list)

* **No authentication, no encryption, no network security** — local profiles only (§7).
  Do not store sensitive health details on a shared machine.
* PDF export buttons from the mockups are replaced by CSV/JSON export + browser print.
* No barcode scanning, no Apple Health / dining-hall sync (mockup decoration only).
* Profile form inputs are metric; imperial units apply to *displayed* values.
* Micronutrient coverage is a 5-nutrient subset, clearly labelled in the UI.
* Flask's built-in server is for development/demos, not public production hosting.
* Automated test runs create extra local profiles (Guest/Priya/…) in the dev
  database by design — delete any you don't want via Settings → *Manage local
  profiles*; deleting one never touches another profile's records.
* Navigation: the sidebar collapses to an icon rail on desktop (choice remembered)
  and becomes a ☰ drawer under ~860px; symptom severity uses exact radio numbers
  1–10 — no slider is used for any health input.
