/* UI smoke harness: executes the REAL frontend JS (static/js/*.js) in Node with a
   minimal DOM stub, against a running NutriCare server. Covers workflows A-H from
   the regression list plus render-path runtime errors.

   Usage:  node tests/ui_smoke.js [baseUrl]     (server must be running) */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const BASE = process.argv[2] || "http://127.0.0.1:5000";
const JS_DIR = path.join(__dirname, "..", "static", "js");
const INDEX_TEMPLATE = fs.readFileSync(path.join(__dirname, "..", "templates", "index.html"), "utf8");
const BRAND_MARK = path.join(__dirname, "..", "static", "images", "nutricare-mark.png");
if (!fs.existsSync(BRAND_MARK) || !INDEX_TEMPLATE.includes("/static/images/nutricare-mark.png")) {
  throw new Error("The supplied NutriCare brand mark must be available to the application shell");
}
console.log("PASS  D0 supplied NutriCare brand mark is wired into the application shell");
const themeBootstrap = INDEX_TEMPLATE.indexOf("nutricare_theme");
const stylesheetLink = INDEX_TEMPLATE.indexOf('/static/css/style.css');
if (themeBootstrap < 0 || stylesheetLink < 0 || themeBootstrap > stylesheetLink) {
  throw new Error("Theme bootstrap must run before the stylesheet to prevent a startup flash");
}
console.log("PASS  T0 no-flash theme bootstrap precedes the stylesheet");
const FILES = ["util.js", "charts.js", "onboarding.js", "views_main.js",
  "views_health.js", "views_more.js", "views_insights.js", "views_scanner.js",
  "app.js"];
const UI_SOURCE = [INDEX_TEMPLATE, ...FILES.map((file) => fs.readFileSync(path.join(JS_DIR, file), "utf8"))].join("\n");
if (/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}]/u.test(UI_SOURCE)) {
  throw new Error("The customer-facing application shell must use the shared SVG icon system, not emoji glyphs");
}
console.log("PASS  D1 customer-facing UI is emoji-free");

/* ---------------- minimal DOM stub ---------------- */
const registry = new Map();
function makeEl(sel) {
  return {
    sel, innerHTML: "", textContent: "", checked: false, hidden: false,
    disabled: false, value: "",
    dataset: {}, style: {}, handlers: {},
    classList: { toggle() {}, add() {}, remove() {}, contains: () => false },
    addEventListener(type, fn) { this.handlers[type] = fn; },
    removeEventListener() {}, appendChild() {}, remove() {}, focus() {},
    click() { this.clicked = true; },
    querySelectorAll: () => [],
    setAttribute(k, v) { this[k] = String(v); },
    onclick: null, oninput: null, onchange: null,
  };
}
const documentStub = {
  body: null,
  documentElement: null,
  querySelector(sel) {
    if (!registry.has(sel)) registry.set(sel, makeEl(sel));
    return registry.get(sel);
  },
  querySelectorAll: () => [],
  addEventListener() {},
  createElement: () => makeEl("created"),
};
documentStub.body = makeEl("body");
documentStub.documentElement = makeEl("html");
const bodyClasses = new Set();
documentStub.body.classList = {
  add: (...cs) => cs.forEach((c) => bodyClasses.add(c)),
  remove: (...cs) => cs.forEach((c) => bodyClasses.delete(c)),
  toggle: (c, force) => {
    const on = force === undefined ? !bodyClasses.has(c) : !!force;
    if (on) bodyClasses.add(c); else bodyClasses.delete(c); return on;
  },
  contains: (c) => bodyClasses.has(c),
};
const windowStub = {
  addEventListener() {},
  matchMedia: (q) => ({
    matches: q.includes("prefers-color-scheme") ? globalThis.__prefersDark === true : globalThis.__mqMatches === true,
    media: q,
    addEventListener() {},
  }),
};
const locationStub = { hash: "#/dashboard", href: "" };
const storage = new Map();
const localStorageStub = {
  getItem: (k) => (storage.has(k) ? storage.get(k) : null),
  setItem: (k, v) => storage.set(k, String(v)),
  removeItem: (k) => storage.delete(k),
};

const realFetch = globalThis.fetch.bind(globalThis);
const cookieJar = new Map();
function nodeFetch(url, opts = {}) {
  const full = String(url).startsWith("http") ? String(url) : BASE + url;
  const headers = Object.assign({}, opts.headers);
  if (cookieJar.size) {
    headers.Cookie = [...cookieJar.entries()].map(([k, v]) => `${k}=${v}`).join("; ");
  }
  return realFetch(full, Object.assign({}, opts, { headers })).then((res) => {
    const cookies = typeof res.headers.getSetCookie === "function" ? res.headers.getSetCookie() : [];
    for (const cookie of cookies) {
      const [nv] = cookie.split(";");
      const i = nv.indexOf("=");
      cookieJar.set(nv.slice(0, i).trim(), nv.slice(i + 1).trim());
    }
    return res;
  });
}

/* ---------------- driver (runs inside the same scope as the app code) ---------------- */
const DRIVER = `
(async () => {
  const assert = (cond, label) => {
    if (!cond) throw new Error("ASSERT FAILED: " + label);
    console.log("  PASS  " + label);
  };
  const view = () => document.querySelector("#view").innerHTML;
  const el = (sel) => document.querySelector(sel);
  const set = (sel, v) => { el(sel).value = v; };
  const click = (sel) => { const b = el(sel); return b.onclick({ currentTarget: b, preventDefault() {} }); };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  /* ---- T: theme follows the OS until explicitly chosen, then persists ---- */
  console.log("T: light and dark theme preference…");
  storage.delete("nutricare_theme"); globalThis.__prefersDark = true;
  document.documentElement.dataset.theme = "";
  initializeTheme();
  assert(currentTheme() === "dark", "T1 no saved theme follows dark operating-system preference");
  setTheme("light");
  assert(currentTheme() === "light" && storage.get("nutricare_theme") === "light",
    "T2 explicit light selection is stored browser-wide");
  document.documentElement.dataset.theme = "";  // simulate a fresh page before boot
  initializeTheme();
  assert(currentTheme() === "light", "T3 saved theme is restored on a simulated refresh");
  setTheme("dark");
  assert(currentTheme() === "dark" && document.documentElement.style.colorScheme === "dark",
    "T4 explicit dark selection updates the document colour scheme");

  /* ---- A: new visitor sees onboarding; skip opens working guest dashboard ---- */
  console.log("A: skip onboarding -> guest dashboard…");
  cookieJar.clear(); storage.delete("nutricare_uid");
  await boot();
  assert(view().includes("Start setup"), "A1 first run shows onboarding");
  const guestsBefore = ((await (await fetch("BASE" + "/api/users")).json()).users)
    .filter((u) => u.name.trim().toLowerCase() === "guest");
  await click("#ob-skip-all");
  await sleep(400);
  assert(S.boot.user && S.boot.user.name === "Guest", "A2 skip enters guest mode");
  if (guestsBefore.length) {
    assert(S.boot.user.id === guestsBefore[guestsBefore.length - 1].id,
      "A2b existing guest profile restored instead of duplicated");
  } else {
    assert(S.boot.user.id > 0, "A2b guest profile created (device had none)");
  }
  assert(view().includes("Energy budget"), "A3 guest dashboard renders");
  assert(view().includes("Daily Nutritional Audit")
    && view().includes("Macronutrient allocation")
    && view().includes("TODAY'S TOTAL INTAKE")
    && view().includes("Calories &amp; macro distribution")
    && view().includes("Meals recorded today")
    && view().includes("Micronutrient snapshot")
    && view().includes("NutriCare nutrition record"),
  "A3b audit dashboard layout renders with today total and real nutrition sections");
  assert(el("#nav-links").innerHTML.includes('data-route="tracker"'), "A4 sidebar nav built after skip");
  assert(typeof el("#quick-water").onclick === "function", "A5 dashboard water button bound");
  assert(typeof el("#quick-log").onclick === "function", "A6 dashboard log-food button bound");
  const preSummary = await (await fetch("BASE" + "/api/summary")).json();
  if (!guestsBefore.length) {
    assert(preSummary.logged_count === 0 && preSummary.water_ml === 0,
      "A7 fresh guest starts with no fabricated meals/water/history");
  } else {
    assert((await (await fetch("BASE" + "/api/meals")).json()).logged_count === preSummary.logged_count,
      "A7 restored guest keeps its own records — entering adds/wipes nothing");
  }

  /* guest can still log (features not needing a profile work) */
  const roti = (await (await fetch("BASE" + "/api/foods?q=roti")).json()).foods[0];
  openFoodSearchModal("lunch", roti);
  set("#m-meal", "lunch"); set("#m-qty", "1"); set("#m-unit", "serving");
  await click("#m-save"); await sleep(300);
  assert((await (await fetch("BASE" + "/api/meals")).json()).logged_count === preSummary.logged_count + 1,
    "A8 guest can log meals without a profile");
  assert(view().includes("Target not set") || view().includes("target not configured"),
    "A9 missing target explained instead of invented");

  /* ---- B: complete onboarding -> saved -> dashboard -> refresh preserves ---- */
  console.log("B: complete onboarding, refresh preserves profile…");
  cookieJar.clear(); storage.delete("nutricare_uid");
  await boot();
  assert(view().includes("Start setup"), "B1 onboarding for fresh browser");
  await click("#ob-start");
  /* F: invalid input shows message, keeps other values, does not advance */
  set("#ob-name", "Priya"); set("#ob-age", "5"); set("#ob-height", "168");
  click("#ob-next");
  assert(el("#ob-err").hidden === false && el("#ob-err").innerHTML.includes("between 10 and 120"),
    "F1 invalid age shows inline validation message");
  assert(view().includes("About you"), "F2 wizard stays on the invalid step");
  /* E: back/next preserve entered values */
  set("#ob-age", "20"); set("#ob-sex", "female"); set("#ob-weight", "59.8");
  set("#ob-activity", "moderate");
  click("#ob-next");                       // -> step 3
  assert(view().includes("consent"), "E1 step 3 renders consent section");
  click("#ob-back");                       // -> step 2 again
  assert(view().includes('value="Priya"') && view().includes('value="20"')
    && view().includes('value="59.8"'), "E2 back re-renders preserved values");
  click("#ob-next"); click("#ob-next");    // -> step 4
  set("#ob-goal", "maintain"); set("#ob-macro", "balanced"); set("#ob-water", "2800");
  await click("#ob-finish");
  await sleep(500);
  assert(S.boot.user && S.boot.user.name === "Priya", "B2 profile saved and session active");
  assert(S.boot.profile.age === 20 && S.boot.profile.weight_kg === 59.8,
    "B3 profile fields committed server-side");
  assert(S.boot.targets && S.boot.targets.kcal > 0, "B4 targets computed after completion");
  assert(view().includes("Energy budget"), "B5 dashboard opens after finish");
  await boot();                            // simulate browser refresh
  assert(!view().includes("Start setup") && view().includes("Energy budget"),
    "B6 refresh does not return to onboarding");
  assert(S.boot.profile.age === 20, "B7 refresh preserves the saved profile");

  /* ---- C: existing user with saved records reopens app ---- */
  console.log("C: records survive reopen…");
  const food = (await (await fetch("BASE" + "/api/foods?q=roti")).json()).foods[0];
  openFoodSearchModal("dinner", food);
  set("#m-meal", "dinner"); set("#m-qty", "2"); set("#m-unit", "serving");
  await click("#m-save"); await sleep(300);
  await boot();                            // reopen
  location.hash = "#/tracker"; await refreshView();
  assert(view().includes(food.name), "C1 previously logged meal still listed after reopen");

  /* ---- D: profile edit persists after refresh ---- */
  console.log("D: profile edit persists…");
  location.hash = "#/profile"; await refreshView();
  set("#p-name", "Priya"); set("#p-age", "20"); set("#p-sex", "female");
  set("#p-height", "168"); set("#p-weight", "61.5"); set("#p-activity", "moderate");
  set("#p-goal", "maintain"); set("#p-macro", "balanced");
  set("#p-prefs", ""); set("#p-allergies", ""); set("#p-meds", ""); set("#p-history", "");
  await click("#p-save"); await sleep(300);
  const prof = await (await fetch("BASE" + "/api/profile")).json();
  assert(prof.profile.weight_kg === 61.5, "D1 edit committed");
  await boot();
  assert(S.boot.profile.weight_kg === 61.5, "D2 edit persists after refresh");

  /* ---- O: account switcher launches the shared full onboarding wizard ---- */
  console.log("O: new account uses shared onboarding and stays isolated…");
  const existingId = S.boot.user.id;
  const existingMealCount = (await (await fetch("BASE" + "/api/meals")).json()).logged_count;
  await openUserModal();
  assert(el("#modal-root").innerHTML.includes("Start profile setup")
    && !el("#modal-root").innerHTML.includes("u-new-name"),
  "O1 account switcher replaces name-only creation with guided setup");
  await click("#u-create");
  assert(S.onboardingActive && bodyClasses.has("no-shell") && view().includes("Start setup"),
    "O2 new account opens the same first-launch wizard");
  click("#ob-start");
  set("#ob-name", "Asha"); set("#ob-age", "29"); set("#ob-sex", "female");
  set("#ob-height", "162"); set("#ob-weight", "57.5"); set("#ob-activity", "active");
  set("#ob-prefs", "lactose-free"); click("#ob-next");
  OB.consent.allergies = true; OB.consent.medications = true; OB.consent.history = true;
  set("#ob-allergies", "soy"); set("#ob-meds", "Vitamin D3");
  set("#ob-history", "Seasonal migraines"); click("#ob-next");
  set("#ob-goal", "mild_gain"); set("#ob-macro", "high_protein"); set("#ob-water", "3200");
  await click("#ob-finish"); await sleep(500);
  assert(S.boot.user && S.boot.user.name === "Asha" && !S.onboardingActive,
    "O3 finished wizard creates and opens the new account");
  assert(S.boot.profile.age === 29 && S.boot.profile.dietary_prefs.includes("lactose-free")
    && S.boot.profile.allergies.includes("soy") && S.boot.profile.medications.includes("Vitamin D3")
    && S.boot.profile.medical_history === "Seasonal migraines"
    && S.boot.profile.goal === "mild_gain" && S.boot.profile.macro_model === "high_protein"
    && S.boot.settings.water_goal_ml === 3200,
  "O4 full optional onboarding data is saved to the new account");
  assert((await (await fetch("BASE" + "/api/meals")).json()).logged_count === 0,
    "O5 new account starts with an isolated empty meal log");
  S.boot = await api("/users/switch", { method: "POST", body: { id: existingId } });
  lsSetLocalUid(); await afterUserChange();
  assert(S.boot.user.id === existingId && S.boot.profile.weight_kg === 61.5
    && (await (await fetch("BASE" + "/api/meals")).json()).logged_count === existingMealCount,
  "O6 switching back restores the existing account without overwriting it");
  assert(currentTheme() === "dark", "O7 switching accounts does not reset the browser theme");

  location.hash = "#/settings"; await refreshView();
  assert(view().includes("Appearance") && view().includes("Light mode") && view().includes("Dark mode"),
    "T5 settings exposes accessible sun and moon appearance controls");
  click("#s-theme-light");
  assert(currentTheme() === "light" && storage.get("nutricare_theme") === "light",
    "T6 settings switches to and persists light mode");
  await refreshView();
  assert(view().includes('id="s-theme-light" type="button" aria-pressed="true"'),
    "T7 refreshed settings retains the active light-mode control");
  click("#s-theme-dark");
  assert(currentTheme() === "dark" && storage.get("nutricare_theme") === "dark",
    "T8 settings switches back to dark mode without profile writes");

  /* ---- H: navigation + interactive controls across all views ---- */
  console.log("H: navigation and controls…");
  for (const [hash, marker] of [["#/tracker", "Nutrition Tracker"], ["#/profile", "Biometrics"],
    ["#/assistant", "Symptom Assessment"], ["#/reports", "Nutrition & Health Reports"],
    ["#/settings", "Privacy & data governance"], ["#/dashboard", "Energy budget"]]) {
    location.hash = hash; await refreshView();
    assert(view().includes(marker), "H nav renders " + hash);
  }
  location.hash = "#/tracker"; await refreshView();
  assert(typeof el("#day-prev").onclick === "function"
    && typeof el("#day-next").onclick === "function", "H1 tracker date nav bound");
  assert(typeof el("#add-custom").onclick === "function", "H2 custom-item button bound");
  location.hash = "#/settings"; await refreshView();
  assert(typeof el("#s-save-units").onclick === "function", "H3 settings save bound");
  assert(typeof el("#s-users").onclick === "function", "H4 profile manager bound");
  location.hash = "#/assistant"; await refreshView();
  assert(typeof el("#a-form").handlers.submit === "function", "H5 assistant form submit bound");
  assert(view().includes('name="severity"') && !view().includes('type="range"'),
    "H6 severity uses exact radio controls, not a slider");
  assert((view().match(/type="checkbox"/g) || []).length >= 18,
    "H7 warning signs + associated render as distinct checkboxes");

  /* ---- assistant flows still safe (G: existing behaviour) ---- */
  console.log("G: assistant emergency + mild flows…");
  const form = el("#a-form");
  const submit = () => form.handlers.submit({ preventDefault() {}, target: form });
  set("#a-primary", "sudden chest pain and pressure");
  el('input[name="severity"]:checked').value = "8";
  await submit(); await sleep(300);
  assert(el("#a-result").innerHTML.includes("EMERGENCY WARNING FLAGS"),
    "G1 emergency banner shown for red-flag text");
  set("#a-primary", "mild headache after study");
  el('input[name="severity"]:checked').value = "3";
  await submit(); await sleep(300);
  const mild = el("#a-result").innerHTML;
  assert(mild.includes("Possible explanations") && mild.includes("What you reported"),
    "G2 mild case shows facts + labelled possibilities");

  /* ---- I: drawer + sidebar toggle interactions ---- */
  console.log("I: hamburger drawer and sidebar toggle…");
  globalThis.__mqMatches = true;           // pretend viewport <= 860px (drawer mode)
  click("#menu-btn");
  assert(bodyClasses.has("side-open"), "I1 hamburger opens the drawer");
  assert(el("#menu-btn")["aria-expanded"] === "true", "I2 hamburger reports expanded state");
  click("#side-scrim");
  assert(!bodyClasses.has("side-open"), "I3 clicking the overlay closes the drawer");
  click("#menu-btn"); click("#menu-btn");
  assert(!bodyClasses.has("side-open"), "I4 hamburger toggles repeatedly without sticking");
  click("#menu-btn");
  click("#side-toggle");
  assert(!bodyClasses.has("side-open") && !bodyClasses.has("side-rail"),
    "I5 in drawer mode the panel icon closes the drawer (does not toggle rail)");
  globalThis.__mqMatches = false;          // desktop mode
  click("#side-toggle");
  assert(bodyClasses.has("side-rail") && storage.get("nutricare_side") === "rail",
    "I6 desktop toggle collapses to icon rail and is remembered");
  assert(el("#side-toggle")["aria-expanded"] === "false"
    && el("#side-toggle").title === "Expand sidebar", "I7 toggle label/tooltip follow state");
  location.hash = "#/reports"; await refreshView();
  assert(bodyClasses.has("side-rail"), "I8 navigating never collapses the rail");
  click("#side-toggle");
  assert(!bodyClasses.has("side-rail") && !storage.has("nutricare_side"),
    "I9 desktop toggle expands again and clears stored state");

  /* ---- J: repeated skips must not duplicate guest profiles ---- */
  console.log("J: skip restores instead of duplicating guests…");
  const usersBeforeJ = (await (await fetch("BASE" + "/api/users")).json()).users;
  const guestsJ = usersBeforeJ.filter((u) => u.name.trim().toLowerCase() === "guest");
  cookieJar.clear(); storage.delete("nutricare_uid");
  await boot();
  assert(view().includes("Start setup"), "J1 fresh visitor state shows onboarding again");
  await click("#ob-skip-all");
  await sleep(400);
  const usersAfterJ = (await (await fetch("BASE" + "/api/users")).json()).users;
  assert(usersAfterJ.length === usersBeforeJ.length,
    "J2 skip created no new profile — existing guest restored");
  assert(S.boot.user.id === guestsJ[guestsJ.length - 1].id,
    "J3 skip lands on the most recent existing guest");

  /* ---- K: Smart Nutrition Insights renders without breaking dashboard ---- */
  console.log("K: Smart Nutrition Insights…");
  location.hash = "#/dashboard"; await refreshView();
  await sleep(700);
  const insightsHtml = () => el("#insights-root").innerHTML;
  assert(insightsHtml().includes("Smart Nutrition Insights"), "K1 insights section renders on dashboard");
  assert(insightsHtml().includes("Not medical advice") || insightsHtml().includes("General educational guidance"),
    "K2 disclaimer present");
  assert(view().includes("Energy budget"), "K2b existing dashboard still renders");
  const insightsFirst = insightsHtml();
  await boot(); location.hash = "#/dashboard"; await refreshView(); await sleep(700);
  assert(el("#insights-root").innerHTML.includes("Smart Nutrition Insights"), "K3 insights survive refresh");
  assert(el("#insights-root").innerHTML.length > 100, "K4 insights content populated");
  const orderedInsights = el("#insights-root").innerHTML;
  assert(orderedInsights.indexOf("Intake trajectory") >= 0
    && orderedInsights.indexOf("Intake trajectory") < orderedInsights.indexOf("Weekly summary"),
  "K5 seven-day trajectory is directly before the weekly summary");

  /* ---- L: Food Scanner (camera, upload, suggestion, portion, log) ----
     The recognition service can be absent in CI. The UI stays helpful without
     exposing implementation details, while API coverage verifies its honesty. */
  console.log("L: Food Scanner view…");
  cookieJar.clear(); storage.delete("nutricare_uid");
  await boot();
  if (!S.boot.user) { await click("#ob-skip-all"); await sleep(400); }
  location.hash = "#/scanner"; await refreshView(); await sleep(400);

  /* The scanner is reached from the Dashboard ("Scan a Meal"), not the sidebar.
     The route must still work when navigated to directly. */
  assert(!el("#nav-links").innerHTML.includes('data-route="scanner"'),
    "L1 Food Scanner is not in the sidebar");
  assert(el("#nav-links").innerHTML.includes('data-route="tracker"'),
    "L1b other sidebar items are untouched");
  assert(view().includes("Food Scanner")
    && view().includes("Take a photo of your meal and discover its nutritional information.")
    && el("#crumb-page").textContent === "Food Scanner",
    "L2 welcoming scanner introduction and breadcrumb render");
  assert(view().includes("Take a photo"), "L3 camera capture option present");
  assert(view().includes("Upload a photo"), "L4 upload option present");
  assert(!!el("#scan-file")
    && view().includes('accept="image/jpeg,image/png,image/webp"')
    && view().includes("JPG, PNG or WebP · up to 8 MB"),
    "L5 image formats and upload limit are visible");
  assert(view().includes("Ready when you are") && (view().includes("not stored")),
    "L6 welcoming empty state and photo privacy message render");
  assert(view().includes("Take a photo of one dish.")
    && view().includes("Confirm or correct the suggested food.")
    && view().includes("Review your nutrition information and add it to your tracker."),
    "L7 user-centred six-step guidance renders");
  assert(view().includes("For the best results, photograph one dish at a time. If your plate contains several different dishes, add them separately.")
    && view().includes("Nutrition information is available for selected foods. If information isn't available for your selection, you may need to enter it manually."),
    "L8 scanner limitations and nutrition coverage are clear");
  assert(!/(80-class|12-class|model installed|primary model|fallback model|checkpoint|classifier|ranking|inference|technical model coverage)/i.test(view()),
    "L9 scanner introduction hides recognition infrastructure details");
  assert(typeof el("#scan-camera").onclick === "function", "L10 camera capture action bound");
  await click("#scan-camera");
  assert(el("#modal-root").innerHTML.includes("Take a photo of your meal")
    && el("#scan-cam-msg").innerHTML.includes("Camera is not supported"),
    "L10b camera action opens a clear capture fallback");
  closeModal();
  assert(typeof el("#scan-upload").onclick === "function", "L11 upload action bound");
  click("#scan-upload");
  assert(el("#scan-file").clicked === true, "L12 upload action opens the photo chooser");

  const visionStatus = await (await fetch("BASE" + "/api/vision/status")).json();
  const modelReady = !!(visionStatus.model && visionStatus.model.model_present);
  if (!modelReady) {
    /* a genuinely valid 16x16 PNG, so validation passes and the service check runs */
    const VALID_PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAFklEQVR4nGM4UWFDEmIY1TCqYfhqAACRKnwQyeK93QAAAABJRU5ErkJggg==", "base64");
    const pred = await fetch("BASE" + "/api/vision/predict", {
      method: "POST", headers: { "Content-Type": "application/octet-stream" },
      body: VALID_PNG });
    assert(pred.status === 503, "L13 unavailable suggestions return an honest service response");
    const body = await pred.json();
    assert(body.model_unavailable === true && !body.predictions,
      "L14 unavailable suggestions never fabricate a food name");
  }

  /* portion adjustment + nutrition come from the documented dataset */
  const dosa = await (await fetch("BASE" + "/api/vision/estimate", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slug: "masala_dosa", grams: 150 }) })).json();
  assert(dosa.nutrients && dosa.nutrients.kcal > 0, "L15 nutrition resolved from dataset");
  const bigger = await (await fetch("BASE" + "/api/vision/estimate", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slug: "masala_dosa", grams: 300 }) })).json();
  assert(Math.abs(bigger.nutrients.kcal - 2 * dosa.nutrients.kcal) < 0.6,
    "L16 nutrients scale proportionally with portion size");
  assert(!!dosa.range && dosa.range.kcal_low < dosa.nutrients.kcal,
    "L17 uncertainty band shown, not hidden");

  /* meal-category selection for all four categories + real persistence */
  const beforeCount = (await (await fetch("BASE" + "/api/meals")).json()).logged_count;
  for (const meal of ["breakfast", "lunch", "snacks", "dinner"]) {
    const res = await fetch("BASE" + "/api/vision/log", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug: "roti", grams: 40, meal }) });
    assert(res.status === 201, "L18 " + meal + " logged via the scanner endpoint");
  }
  const after = await (await fetch("BASE" + "/api/meals")).json();
  assert(after.logged_count === beforeCount + 4, "L19 scanned meals persisted to the diary");
  assert(["breakfast", "lunch", "snacks", "dinner"].every((m) =>
    after.meals[m].some((e) => e.display_name.includes("Roti"))),
    "L20 all four meal categories accepted and grouped correctly");

  const summaryAfter = await (await fetch("BASE" + "/api/summary")).json();
  assert(summaryAfter.totals.kcal >= dosa.nutrients.kcal,
    "L21 existing dashboard totals reflect scanned meals");

  await boot(); location.hash = "#/tracker"; await refreshView(); await sleep(400);
  assert(view().includes("Roti"), "L22 scanned meal visible in the tracker log");

  /* missing meal category is refused */
  const noMeal = await fetch("BASE" + "/api/vision/log", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slug: "roti", grams: 40 }) });
  assert(noMeal.status === 400, "L23 meal category is required before saving");

  location.hash = "#/dashboard"; await refreshView(); await sleep(600);
  assert(typeof el("#quick-scan").onclick === "function",
    "L24 dashboard exposes the scanner entry point");
  /* the dashboard button must actually open the scanner route */
  el("#quick-scan").onclick();
  await sleep(50);
  assert(location.hash === "#/scanner", "L25 Scan a Meal opens the scanner route");
  await refreshView(); await sleep(400);
  assert(view().includes("Food Scanner"),
    "L26 scanner renders when opened from the dashboard");
  assert(typeof el("#scan-camera").onclick === "function",
    "L27 camera capture still bound after the sidebar change");
  assert(typeof el("#scan-upload").onclick === "function",
    "L28 upload still bound after the sidebar change");

  /* ---- M: recognition always waits for confirmation / correction / final save ---- */
  console.log("M: scanner confirmation and catalogue correction…");
  const scannerBefore = (await (await fetch("BASE" + "/api/meals")).json()).logged_count;
  SCAN.previewUrl = "data:image/png;base64,preview";
  SCAN.result = { low_confidence: false, threshold: 0.55 };
  SCAN.candidates = [
    { slug: "roti", label: "Roti", group: "indian_staple", confidence: 0.92,
      nutrition: { grams: 40, default_grams: 40, nutrition_available: true } },
    { slug: "masala_dosa", label: "Masala dosa", group: "indian_breakfast", confidence: 0.06,
      nutrition: { grams: 150, default_grams: 150, nutrition_available: true } },
  ];
  scanClearSelection(); scanShowResult();
  assert(el("#scan-drop").innerHTML.includes("Is this the correct food?")
    && el("#scan-drop").innerHTML.includes("Yes, correct")
    && el("#scan-drop").innerHTML.includes("No, choose another food"),
  "M1 suggestion is presented as an explicit confirmation choice");
  assert(!el("#scan-drop").innerHTML.includes("% confident"),
    "M2 confirmation keeps implementation scores out of the user interface");
  await sleep(100);
  assert((await (await fetch("BASE" + "/api/meals")).json()).logged_count === scannerBefore,
    "M3 a suggestion alone never writes a meal");
  click("#scan-confirm-yes"); await sleep(100);
  assert(SCAN.confirmed && SCAN.slug === "roti" && el("#scan-drop").innerHTML.includes("Add to meal log"),
    "M4 Yes accepts the suggestion and opens portion/category workflow without logging");
  assert((await (await fetch("BASE" + "/api/meals")).json()).logged_count === scannerBefore,
    "M5 accepting the suggestion still does not write a meal");

  scanClearSelection(); scanShowResult(); click("#scan-confirm-no");
  assert(el("#scan-drop").innerHTML.includes("Other suggestions")
    && el("#scan-drop").innerHTML.includes("Search food catalogue"),
  "M6 correction reveals other suggestions and a food catalogue search");
  scanSelectClass(SCAN.candidates[1], "alternative"); await sleep(100);
  assert(SCAN.confirmed && SCAN.slug === "masala_dosa"
    && el("#scan-drop").innerHTML.includes("You chose another suggestion"),
  "M7 choosing another suggestion uses it only after the correction choice");

  openFoodSearchModal("lunch", null, () => {});
  set("#m-search", "roti"); await el("#m-search").oninput();
  assert(el("#modal-root").innerHTML.includes("Search documented food catalogue")
    && el("#m-results").innerHTML.includes(roti.name),
  "M8 catalogue search returns documented foods without logging itself");
  let cataloguePicked = null;
  openFoodSearchModal("lunch", roti, (foodChoice, grams) => {
    cataloguePicked = { foodChoice, grams }; scanSelectCatalogueFood(foodChoice, grams);
  });
  assert(el("#modal-root").innerHTML.includes("Use this food")
    && !el("#modal-root").innerHTML.includes("Add to log"),
  "M9 catalogue selection stays separate from saving");
  set("#m-qty", "1"); set("#m-unit", "serving"); await click("#m-save");
  assert(cataloguePicked && SCAN.catalogueFood.id === roti.id && SCAN.confirmed
    && el("#scan-nutrition").innerHTML.includes("Documented nutrition"),
  "M10 documented catalogue selection retains portioned nutrition in the scanner");
  SCAN.meal = "lunch"; scanConfirmSave();
  assert(el("#modal-root").innerHTML.includes("Confirm meal entry")
    && el("#modal-root").innerHTML.includes("It will not be added until you confirm"),
  "M11 meal category leads to an explicit final confirmation");
  assert((await (await fetch("BASE" + "/api/meals")).json()).logged_count === scannerBefore,
    "M12 no scanner meal is saved before the final confirmation");
  await click("#scan-final-save"); await sleep(400);
  assert((await (await fetch("BASE" + "/api/meals")).json()).logged_count === scannerBefore + 1,
    "M13 final confirmation saves the documented catalogue entry exactly once");

  /* ---- N: missing nutrition must never render as 0 kcal ---- */
  const altNoData = scanAltNutrition({ label: "Paneer Butter Masala",
    confidence: 0.31, nutrition: { nutrition_available: false, nutrients: null } });
  assert(altNoData.includes("nutrition information isn\'t available"),
    "N1 unavailable nutrition explains that manual entry may be needed");
  assert(!/\b0\s*kcal/.test(altNoData),
    "N2 missing nutrition never renders as 0 kcal");
  assert(!/\d\s*kcal/.test(altNoData),
    "N3 no calorie figure at all when nutrition is unavailable");

  const altPartial = scanAltNutrition({ label: "Mystery", confidence: 0.2,
    nutrition: { nutrients: null } });
  assert(!/\bkcal/.test(altPartial),
    "N4 estimate object without nutrients also avoids a false 0 kcal");

  const altReal = scanAltNutrition({ label: "Pakora", confidence: 0.8,
    nutrition: { grams: 80, nutrition_available: true,
      nutrients: { kcal: 235.5, protein_g: 5.9 } } });
  assert(/236 kcal at 80 g/.test(altReal),
    "N5 documented nutrition still shows the real scaled figure");

  const altNoEstimate = scanAltNutrition({ label: "Blank", confidence: 0.1 });
  assert(!/\bkcal/.test(altNoEstimate),
    "N6 candidate with no nutrition object avoids a false 0 kcal");

  /* a genuine zero in another nutrient is still shown as 0 — only missing data
     is withheld, so the two cases stay distinguishable */
  const altZeroFat = scanAltNutrition({ label: "Zero fat", confidence: 0.9,
    nutrition: { grams: 100, nutrition_available: true,
      nutrients: { kcal: 0, fat_g: 0 } } });
  assert(/0 kcal/.test(altZeroFat),
    "N7 a genuine zero kcal is still displayed as 0, not hidden");

  console.log("ALL UI SMOKE CHECKS PASSED");
})().catch((e) => { console.error("UI SMOKE FAILURE:", e.message); process.exit(1); });
`.replace(/"BASE" \+/g, '"' + BASE + '" +');

const code = FILES.map((f) => fs.readFileSync(path.join(JS_DIR, f), "utf8")).join("\n;\n")
  + "\n;\n" + DRIVER;

globalThis.document = documentStub;
globalThis.window = windowStub;
globalThis.location = locationStub;
globalThis.fetch = nodeFetch;
globalThis.localStorage = localStorageStub;
globalThis.cookieJar = cookieJar;
globalThis.storage = storage;
globalThis.bodyClasses = bodyClasses;

try {
  vm.runInThisContext(code, { filename: "nutricare-ui-bundle.js" });
} catch (e) {
  console.error("UI SMOKE FAILURE (runtime error):", e.stack.split("\n").slice(0, 6).join("\n"));
  process.exit(1);
}
