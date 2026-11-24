# NutriCare UI/UX redesign — implementation report

**Branch:** `arena/872f2a84-nutricare`
**Base:** `71eecf9` (packaged-foods dataset commit)
**Head:** `df46953` — 14 commits, 11 files, +702 / −293
**Pull request:** #20 (still open, contains both the dataset work and this redesign)

---

## 1. What was asked for

Redesign the interface of the main dashboard, Food Scanner, prediction /
confirmation flow, nutrition and meal tracking, meal history, Health Assistant,
profile, reports and analytics, onboarding/auth, navigation and shared
components so the product reads as a deliberately designed nutrition and health
tool — **without breaking, removing or changing any existing functionality**.

Twenty principles, applied where appropriate. The two hard constraints that
shaped almost every decision were:

* functional stability outranks visual quality (no route, API, schema,
  calculation, model or safety-logic change); and
* "do not claim that a test passed unless it was actually executed".

---

## 2. Files and components modified

| File | Change | Functional impact |
|---|---|---|
| `static/css/style.css` | design-token layer rewritten (colour, radius, spacing, elevation, motion); every component restyled onto it | none — CSS only |
| `static/js/views_main.js` | dashboard: stat banner, purpose lines, label semantics; tracker: page kicker + one primary header action; meal-choice modal polish | **added** one button wired to the existing `openFoodSearchModal("breakfast")`; nothing removed |
| `static/js/views_more.js` | reports kicker/purpose lines, accent rule, `icon-pill` cleanup | none |
| `static/js/views_health.js` | profile page kicker, triage module heading/purpose line, readable disclaimer ink | none |
| `static/js/views_scanner.js` | page kicker, one primary capture action, meal-category dialog rebuilt on the shared tile grid | same `data-meal` handlers and ids |
| `static/js/views_insights.js` | inline accent clean-up | none |
| `static/js/app.js` | layout-preserving loading skeleton, accent sidebar goal bar | same `refreshView`/`refreshSideGoal` behaviour |
| `static/js/charts.js` | default ring colour → accent token | charts are still CSS-variable driven |
| `static/js/util.js` | *(unchanged)* | — |
| `static/js/onboarding.js` | *(unchanged markup; restyled by CSS)* | — |
| `templates/index.html` | cache-buster `editorial-v11`, preconnect to the font CDN | theme IIFE still precedes the stylesheet |
| `docs/UI_DESIGN_SYSTEM.md` | **new** — the design system, with measured contrast ratios | documentation |
| `README.md` | one row pointing at the design-system doc | documentation |

No backend file, route, schema, migration, dataset row, model file or health
rule was touched.

---

## 3. Design decisions, mapped to the twenty principles

1. **Tasteful purple gradient accent.** One accent colour family
   (`#5B3BD6` / `#4A26B8`, dark `#8C6FFF` / `#B9A4FF`) layered over the existing
   forest, oat and sage palette. It is used for the primary action, page
   kickers, key figures and the health-chat launcher — nowhere else.
2. **Gradient text only on key headings and figures.** Two places: the second
   line of "Daily Nutritional Audit & Dietary Intake", and the calories figure
   in the stat banner. Both fall back to a solid colour under
   `forced-colors: active`.
3. **Subtle glow on important interactive elements.** Exactly one glow token
   (`--glow-accent`, a 24px-spread violet shadow at ~50% alpha) on primary
   buttons and the chat launcher. No neon, no colour fringing.
4. **Subtle glossy/blob decoration.** Two radial washes (`--blob-a` violet,
   `--blob-b` mint). A page gets one, in one place: behind the dashboard header,
   and a single radial inside the dark care card. The landing page uses its two
   real photographs as the depth cue instead. The header wash is clipped to its
   own box and re-inset below 860px so it cannot widen the page.
5. **Emoji in navigation — evaluated and removed from the design.** The shipped
   UI already had zero emoji (all icons are inline SVG from `ICONS`); I kept it
   that way, and the one fullwidth `＋` glyph in the custom-food action was
   replaced with `ICONS.plus` for a single consistent icon system.
6. **Pill label above headings.** `.page-kicker` on Tracker, Reports, Profile,
   Settings and Scanner; `.ob-question-kicker` in the onboarding wizard.
7. **Every major section states its purpose.** `.audit-purpose` on the
   dashboard header and `.audit-section-purpose` on Today's intake, Meal log,
   Micronutrients, Nutrition notes, the 7-day overview, Reports energy trend and
   micronutrient card, and Symptom Assessment.
8. **No hype language.** No superlatives, no benefit claims, no urgency
   devices; every new string is descriptive ("Where today's energy came from,
   meal by meal.").
9. **Intentional alignment.** Page and card headers stay left-aligned; empty
   states, stat figures and toast/modal footers are centred; numeric columns use
   tabular figures.
10. **One dominant primary button per section.** `.btn-deep` / `.btn-primary`
    (violet, glowing) is the only filled button in a section; `.btn-soft` is the
    tinted secondary; `.btn-ghost` is the quiet tertiary. Fixed one real
    violation: on an empty day the tracker header CTA and the empty-state CTA
    were both filled, so the header now demotes to secondary and the empty state
    keeps the primary.
11. **No fabricated proof.** There are no testimonials, star ratings, review
    quotes, user counts or logos in the UI. The stat banner shows only figures
    summed from the person's own logged meals, and shows "no target set"
    instead of inventing a target.
12. **4px spacing grid.** `--s-1`…`--s-8` (4→40px). Component padding, gaps and
    the `.mt*` utilities all use it.
13. **Moderate pill corners.** Five-step radius scale (6 / 10 / 14 / 20 / 999).
    Cards are 14px, controls 10px, modals and hero media 20px; only true pills
    (badges, bars, the chat launcher) are fully rounded.
14. **Not Inter.** Newsreader (editorial serif) for headings and figures, Plus
    Jakarta Sans for dense UI, each with a full system fallback stack. Both were
    already loaded; the pairing is now enforced through two type roles instead
    of ad-hoc overrides.
15. **Stat banner for calories / protein / carbs / fat, real data only.** New
    `.audit-stat-banner` built from `summary.totals` and the user's own
    `targets`; with no target it prints "no target set" / "target optional".
    Verified live: one logged roti (80 g) rendered 211 kcal, 6.8 g protein,
    36.8 g carbs, 3.6 g fat — matching `/api/summary` exactly.
16. **Tiny ALL-CAPS metadata at readable size and contrast.** 9.5–10px with
    `.10–.14em` tracking, at `--faint` (5.0:1) or `--accent-ink` (9.3:1). Form
    labels deliberately moved to sentence case at 11.5px, because a label the
    user must read is not metadata.
17. **Consistent icon boxes.** One 32px box, `--r-sm`, tinted by category
    (`.tint-teal` / `.tint-mint` / `.tint-sky` / `.tint-amber` / `.tint-rose`);
    added the missing `.tint-mint` and moved every tint to an ink-on-soft pair
    (6.9–8.5:1).
18. **Every card says or does something.** The purpose-line pass removed the
    remaining "decorative" card headers; the one new card (stat banner) carries
    four real figures plus a provenance footnote.
19. **Subtle motion only for loading, notifications and interaction.** Three
    durations (120/180/280ms) on one easing curve, used only for loading
    skeletons and the scanner spinner, toast entrance, modal entrance and
    hover/press feedback. A global `prefers-reduced-motion` rule collapses all
    of it to 0.01 ms.
20. **One bright focal moment per page.** Dashboard: the violet-washed header +
    accent calories figure. Scanner: the accent-bordered capture card.
    Landing: the hero photograph. Reports/Profile/Settings: the single accent
    primary action.

### Accessibility and colour work

Every text token was measured against every surface token in both themes. The
audit found and fixed four real defects:

* `--faint` was 4.18:1 on the canvas (below AA for the 9–11px text it is used
  on) → darkened to `#606963` (5.0:1 on the muted surface, 5.4:1 on canvas).
* In dark mode the accent *text* colour was being reused as a button *fill*,
  producing near-white text on a pale violet fill (1.81:1) → split into
  `--accent-fill` (mid violet) + `--on-accent` (dark ink), now 5.2:1, with the
  fill itself at 4.7:1 against the dark canvas.
* Accent rules/stripes inherited the light-theme violet, which measured 1.85:1
  against dark card surfaces → dedicated `--accent-rule` that brightens in dark
  mode (6.0:1).
* Keyboard focus used the forest colour inconsistently; a single 2px
  `--accent` focus ring now covers buttons, inputs, selects, icon buttons,
  composite choice cards (`:has(input:focus-visible)`) and the landing links.

---

## 4. Tests executed (actual results)

| Suite | Command | Result |
|---|---|---|
| Backend + data | `.venv/bin/python -m pytest -q` | **1195 passed** in 19.12–22.96 s (run after every stage; final run on `df46953`) |
| Frontend smoke | `node tests/ui_smoke.js http://127.0.0.1:5055` | **ALL UI SMOKE CHECKS PASSED** (A–N, ~190 assertions, ~13 s; final run on `df46953`) |
| Stylesheet integrity | brace balance + undefined-`var()` scan | 859/859 braces balanced, **0 undefined custom properties** |
| Emoji policy | regex scan of `index.html` + all 10 JS files | **0 emoji** (the harness fails the build if any appear) |
| Contrast | WCAG 2.1 ratio computation over the token pairs | all text pairs ≥ 4.5:1; table in §3 |
| Static markup/CSS coverage | classes used in markup vs CSS rules | no unstyled functional classes remain |

### Routes and flows exercised against the live server

Server: `PORT=5055 NUTRICARE_DB=/tmp/nc/smoke.db python app.py` (binds `0.0.0.0`,
shown as the live preview).

* `GET /` → 200 with the new `editorial-v11` asset URLs.
* `/ → #/dashboard`, `#/tracker`, `#/scanner`, `#/profile`, `#/reports`,
  `#/settings` → 200; each view rendered by the smoke harness without a runtime
  error.
* `/api/bootstrap`, `/api/users` (201), `/api/summary`, `/api/report?days=7`,
  `/api/insights`, `/api/insights/weekly`, `/api/profile`, `/api/vision/classes`
  → 200 with a real profile.
* **Scanner write path:** `POST /api/vision/log` (roti, 80 g, lunch) → 201, then
  `/api/summary` returned 211.2 kcal / 6.8 P / 36.8 C / 3.6 F, 1 entry — the same
  numbers the banner renders.
* **Health Assistant safety:** `POST /api/assistant/screen` with "mild headache"
  → `emergency:false, triage:"continue"`; with "severe chest pain and cannot
  breathe" → `emergency:true, triage:"emergency", 3 emergency actions`. Rules
  untouched.
* **Theme engine:** the smoke harness toggles light/dark via
  `initializeTheme`/`setTheme`, the top-bar switch and the settings cards — all
  pass, including the pre-paint no-flash bootstrap.
* **Onboarding:** full 9-step wizard walk (name → age → formula → height →
  weight → activity → context → targets), validation errors, skip paths and
  returning-profile continuation — all pass.

---

## 5. Tests NOT executed, and why

* **Screenshots / visual browser verification: not produced.** No browser
  binary can run in this sandbox: `playwright install chromium` fails its
  download (code 1); the Debian bookworm repository in this image has no
  `chromium` package; `apt-get update` cannot write `/var/lib/apt/lists`
  (non-root); the `@sparticuz/chromium` binary dies on a missing `libnss3.so`,
  and `libnss`/`libnspr`/`libpango`/`libcairo`/`libgdk-pixbuf`/`libharfbuzz` are
  absent with an empty font cache. This was attempted and abandoned — **the
  visual claims in this report rest on code review, measured contrast maths and
  the DOM-level smoke harness, not on rendered pixels.**
* **Real-browser responsive testing (mobile/tablet/desktop) was not performed**
  for the same reason. Responsive safety was instead verified by auditing the
  stylesheet for overflow hazards (large fixed `min-width`, negative horizontal
  insets, fixed multi-column grids without breakpoints) and by re-clipping the
  one decorative layer that exceeded the mobile gutter.
* **Camera capture** (`getUserMedia`) cannot be exercised headlessly; the smoke
  harness asserts the camera path fails gracefully ("Camera is not supported")
  and the upload path is used for the end-to-end scanner tests.
* **PDF/CSV export contents** were not opened; only their route wiring and links
  are asserted by the suite.
* **Screen-reader testing** was not performed; only static accessibility
  properties were checked (focus visibility, labels on icon-only buttons, live
  regions, heading order).

---

## 6. Functionality preserved — confirmation

* No route, API contract, database schema, stored record, authentication flow,
  food-recognition behaviour, nutrition formula or Health Assistant rule was
  modified. `git diff 71eecf9..df46953 --stat` touches only CSS, view-layer JS,
  the shell template's asset query strings, and documentation.
* Every id, class hook, `data-*` attribute, handler and copy string that
  `tests/ui_smoke.js` pins is still present — including the two byte-exact CSS
  substrings for the expanded health-chat panel, the nav routes, the scanner
  confirmation wording, the six onboarding steps, and the "no fabricated data"
  guards (missing nutrition must never render as `0 kcal`).
* One button was **added** (tracker "Log food"); nothing was removed or
  rewired. The scanner meal dialog keeps its `data-meal` handlers and ids.
* Both themes work, the dark theme was re-derived rather than tinted, and the
  pre-paint theme bootstrap still precedes the stylesheet.

---

## 7. Remaining issues and honest limits

1. **No screenshots.** See §5. A reviewer with a browser should open the live
   preview and check the two editorial photographs on the landing page, the
   dashboard header wash at 1440/1024/390 px, and the dark theme on the Scanner.
2. **Google Fonts is still an external request.** In this sandbox it cannot
   load, so the preview falls back to Georgia and the system sans. If the
   project must work fully offline, self-hosting the two families is the next
   step (it would add ~200 kB of font files).
3. **Health-chat surfaces remain deliberately conservative.** That block is
   pinned by exact substrings and drives safety-critical UI, so it received the
   accent and the launcher/panel radius treatment but no structural restyling.
4. **Some inline font sizes remain in view JS** (16–22px `style` attributes on
   result-card headings). They are semantically consistent and were left alone
   rather than churning markup the tests pin; moving them to utility classes is
   cosmetic follow-up.
5. **`.landing-*` and `.ob-*` markup was not restructured** — the first-run
   landing page and wizard were restyled through CSS only, because their
   ordering and copy are pinned by the harness.
