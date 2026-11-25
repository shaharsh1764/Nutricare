# NutriCare UI design system

**Status:** implemented in `static/css/style.css` (single stylesheet, no build step)
**Scope:** visual language only — no route, API, data-model or interaction change

NutriCare is a personal nutrition record, not a marketing product. The interface
is therefore styled as a calm clinical journal: warm oat paper, forest ink, and a
single violet accent used only where an action or a figure deserves attention.

## 1. Colour

Three roles, defined once as custom properties in `:root` and overridden in
`html[data-theme="dark"]`.

| Role | Tokens | Used for |
|---|---|---|
| Structure | `--primary`, `--primary-deep`, `--line`, `--surface*`, `--sidebar` | sidebar, table rules, card surfaces |
| Accent | `--accent`, `--accent-fill`, `--accent-ink`, `--accent-soft`, `--accent-rule` | the one primary action per section, page kickers, key figures |
| Data | `--success`, `--carb`, `--fat`, `--amber`, `--rose`, `--sky` | macro series, status pills, charts |

The accent is deliberately split into four values because a filled button, a
text label and a 3px rule have different contrast needs:

* `--accent-fill` — background of the primary button (light `#5B3BD6`, dark `#8C6FFF`)
* `--on-accent` — label on that fill (light `#FBFAFF`, dark `#12101C`)
* `--accent-ink` — accent-coloured text on a page surface (≥ 8:1 in both themes)
* `--accent-rule` — decorative rules, bars and markers (`#5B3BD6` light, `#B9A4FF` dark)

Measured contrast (WCAG 2.1):

| Pair | Ratio |
|---|---|
| `--ink` on `--card` (light) | 16.6:1 |
| `--muted` on `--card` (light) | 7.1:1 |
| `--faint` on `--surface-muted` (light) | 5.0:1 |
| `--accent-ink` on `--surface` (light) | 9.3:1 |
| `--on-accent` on `--accent-fill` (light) | 6.7:1 |
| `--on-accent` on `--accent-fill` (dark) | 5.2:1 |
| `--accent-fill` vs `--canvas` (dark) | 4.7:1 |
| `--accent-rule` vs `--surface` (dark) | 6.0:1 |
| pill ink on pill soft background (all six pills) | 6.9–8.5:1 |

`--faint` was darkened from `#727973` to `#606963` because the original value
measured 4.18:1 on the canvas, below AA for the 9–11px metadata it is used on.

## 2. Type

* `--font-editorial` (Newsreader, fallback Georgia) — page headings, section
  headings inside cards, and numeric figures (`.stat`, `.audit-banner-value`).
* `--font` (Plus Jakarta Sans, fallback system sans) — everything else, i.e. all
  dense UI: tables, forms, buttons, labels.

Newsreader is chosen over a neutral grotesque so headings read editorially;
Plus Jakarta Sans keeps small text legible at 11–13px. Inter is not used.

**Both families are self-hosted.** `static/fonts/` holds latin-subset woff2 for
Newsreader 400/500/600 and Plus Jakarta Sans 400/500/600/700/800 (8 files,
156 kB), with the SIL OFL 1.1 licence text beside them, and `style.css` opens
with the matching `@font-face` rules. The page therefore makes **no external
request**; the two most-used faces (PJS 400, Newsreader 500) are preloaded and
everything else uses `font-display:swap`, so text paints immediately in the
fallback and swaps when the face arrives. The static files carry no `opsz`
axis, so `font-optical-sizing` has no effect — sizes are tuned by hand instead.

Metadata labels (`.card-title`, `.nav-label`, `.audit-card-label`,
`.audit-banner-label`, `.page-kicker`) are ALL-CAPS at 9.5–10px with
`.1–.14em` tracking and `--faint`/`--accent-ink` colour — small, but never
below AA. Form labels are *not* uppercased: they carry meaning, so they are
11.5px sentence case in `--ink-subtle`.

## 3. Shape and spacing

One radius scale, applied by element size rather than by asset:

| Token | Value | Used for |
|---|---|---|
| `--r-xs` | 6px | inline chips, small markers |
| `--r-sm` | 10px | inputs, icon boxes, list rows, secondary cards |
| `--r-md` | 14px | cards, meal blocks, panels |
| `--r-lg` | 20px | modals, hero media, the stat banner |
| `--r-pill` | 999px | pills, bars, the health-chat launcher |

`--r-card` (14px) and `--r-ctl` (10px) remain as aliases so the existing
markup keeps working. Nothing is max-rounded except true pills.

Spacing is a 4px grid: `--s-1` 4 · `--s-2` 8 · `--s-3` 12 · `--s-4` 16 ·
`--s-5` 20 · `--s-6` 24 · `--s-7` 32 · `--s-8` 40. Component padding uses these
tokens; no component defines its own spacing constants.

## 4. Elevation and decoration

Three shadows only (`--shadow-sm/md/xl`) — a hairline rest state, a lifted
hover, and an overlay. There are no glows other than `--glow-accent`, which is
applied to primary buttons and the health-chat launcher.

Depth is otherwise carried by two decorative washes (`--blob-a` violet,
`--blob-b` mint). A page gets **one** of them, at one place:

* Dashboard — behind the page header only (`.audit-header:before`), clipped to
  the header box and re-inset below 860px so it can never widen the page.
* Care card — a single radial inside the forest surface.
* Landing — the two editorial photographs act as the depth cue instead.

## 5. Motion

`--dur-fast` 120ms, `--dur` 180ms, `--dur-slow` 280ms, all on
`--ease` (`cubic-bezier(.22,.61,.36,1)`). Motion is used only for:

* loading (`@keyframes loading-pulse` on the view skeleton, `scan-spin`)
* notifications (`@keyframes pop` on toasts)
* interaction feedback (button/drop-zone/tile hover and press, modal entrance)

`@media (prefers-reduced-motion: reduce)` collapses every animation and
transition to 0.01ms globally, so nothing depends on motion to be understood.

## 6. Component rules

* **One dominant action per section.** `.btn-deep`/`.btn-primary` (violet) is
  the only filled button in a given section; `.btn-soft` is the tinted
  secondary and `.btn-ghost` the quiet tertiary. `.btn-accent` exists solely
  for the primary action placed on the dark care card.
* **Every section states its purpose** in one sentence
  (`.audit-purpose`, `.audit-section-purpose`).
* **One icon system.** All icons are inline SVG from `ICONS` in
  `static/js/util.js`; there are no emoji in the UI (the smoke harness fails
  the build if one appears).
* **Icon boxes** are all 32px with `--r-sm`, tinted by category
  (`.tint-teal`, `.tint-mint`, `.tint-sky`, `.tint-amber`, `.tint-rose`); each
  tint pairs an ink colour with a soft background.
* **Pill kicker above a heading** (`.page-kicker`, `.page-head`) names the page
  in one phrase.
* **Focus is always visible**: a 2px `--accent` outline with 2px offset on
  every control, including composite cards via `:has(input:focus-visible)`.
* **No fabricated proof.** There are no testimonials, star ratings, user counts
  or review quotes anywhere in the UI; the stat banner only ever shows figures
  summed from the person's own logged meals.

## 7. Verifying a change

```bash
.venv/bin/python -m pytest -q                    # 1195 tests
node tests/ui_smoke.js http://127.0.0.1:5055     # renders every view in Node
```

`tests/ui_smoke.js` pins the copy, ids and class hooks the design must preserve
(including two byte-exact CSS substrings for the expanded health-chat panel).
Run it after any stylesheet or view change.
