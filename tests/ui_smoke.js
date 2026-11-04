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
const FILES = ["util.js", "charts.js", "onboarding.js", "views_main.js",
  "views_health.js", "views_more.js", "views_insights.js", "app.js"];

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
    querySelectorAll: () => [],
    setAttribute(k, v) { this[k] = String(v); },
    onclick: null, oninput: null, onchange: null,
  };
}
const documentStub = {
  body: null,
  querySelector(sel) {
    if (!registry.has(sel)) registry.set(sel, makeEl(sel));
    return registry.get(sel);
  },
  querySelectorAll: () => [],
  addEventListener() {},
  createElement: () => makeEl("created"),
};
documentStub.body = makeEl("body");
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
  matchMedia: (q) => ({ matches: globalThis.__mqMatches === true, media: q, addEventListener() {} }),
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
