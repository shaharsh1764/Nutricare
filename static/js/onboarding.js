/* First-run onboarding wizard (4 steps).

   Fixes baked in:
   * entered values survive Back/Next (OB.data), so nothing is lost or re-typed;
   * required/range validation happens inline BEFORE advancing or submitting,
     with a visible message (no dead-ends, no unrelated data lost);
   * "Skip for now" always lands on a fully working guest dashboard;
   * existing local profiles are offered as "Continue as …" so a refresh or a
     second visit never orphans or overwrites saved records;
   * Finish saves (server commits first), confirms with a toast and redirects
     to the dashboard — no loops, no stuck setup page. */
"use strict";

const OB = {
  step: 1,
  consent: { allergies: false, medications: false, history: false },
  data: { name: "", age: "", sex: "", height: "", weight: "", activity: "moderate",
    prefs: "", allergies: "", meds: "", history: "", goal: "maintain",
    macro: "balanced", water: "2800" },
};

const OB_ACTIVITY = [
  ["sedentary", "Mostly sitting (desk study)"],
  ["light", "Light exercise 1-3 days/week"],
  ["moderate", "Moderate exercise 3-5 days/week"],
  ["active", "Hard exercise 6-7 days/week"],
  ["very_active", "Physical job + training"],
];

/* read the visible inputs of the current step into OB.data (preservation) */
function obRead() {
  const v = (sel) => { const el = $(sel); return el ? el.value : OB.data[sel]; };
  if (OB.step === 2) {
    OB.data.name = v("#ob-name"); OB.data.age = v("#ob-age"); OB.data.sex = v("#ob-sex");
    OB.data.height = v("#ob-height"); OB.data.weight = v("#ob-weight");
    OB.data.activity = v("#ob-activity"); OB.data.prefs = v("#ob-prefs");
  } else if (OB.step === 3) {
    OB.data.allergies = v("#ob-allergies"); OB.data.meds = v("#ob-meds");
    OB.data.history = v("#ob-history");
  } else if (OB.step === 4) {
    OB.data.goal = v("#ob-goal"); OB.data.macro = v("#ob-macro"); OB.data.water = v("#ob-water");
  }
}

/* inline validation with a visible message; returns true when the step is ok */
function obValidateStep2() {
  const d = OB.data;
  const problems = [];
  if (!d.name.trim()) problems.push("Display name is required (or choose “Skip for now”).");
  const range = (label, value, lo, hi) => {
    if (value !== "" && value !== null && value !== undefined) {
      const n = Number(value);
      if (isNaN(n) || n < lo || n > hi) problems.push(`${label} must be between ${lo} and ${hi}, or left blank.`);
    }
  };
  range("Age", d.age, 10, 120);
  range("Height", d.height, 50, 250);
  range("Weight", d.weight, 20, 300);
  const box = $("#ob-err");
  if (box) {
    box.hidden = problems.length === 0;
    box.innerHTML = problems.map((p) => `<div>• ${esc(p)}</div>`).join("");
  }
  return problems.length === 0;
}

function obValidateStep4() {
  const problems = [];
  const w = Number(OB.data.water);
  if (OB.data.water !== "" && (isNaN(w) || w < 500 || w > 6000)) {
    problems.push("Water goal must be between 500 and 6000 ml, or left blank.");
  }
  const box = $("#ob-err");
  if (box) { box.hidden = problems.length === 0; box.innerHTML = problems.map((p) => `<div>• ${esc(p)}</div>`).join(""); }
  return problems.length === 0;
}

async function renderOnboarding() {
  const view = $("#view");
  if (OB.step === 1) {
    view.innerHTML = `<div class="onb">
      <div class="onb-card">
        <div class="row" style="gap:12px"><span class="onb-brand-mark"><img src="/static/images/nutricare-mark.png" alt="NutriCare"></span>
          <div><h2 class="editorial-heading" style="font-size:32px">Welcome to NutriCare</h2>
          <p class="tiny muted" style="letter-spacing:.08em;font-weight:700">NOURISHMENT JOURNAL</p></div></div>
        <p class="small muted mt12">NutriCare does two things:</p>
        <div class="grid cols-2 mt12">
          <div class="selfcare-card"><b class="small">1 · Tracks your nutrition</b>
            <p class="tiny muted mt8">Log meals and water, see calories and macros against a
            personalised <i>estimate</i>, and export your own data as CSV/JSON.</p></div>
          <div class="selfcare-card"><b class="small">2 · Offers general health information</b>
            <p class="tiny muted mt8">A structured symptom checklist with emergency warning-sign
            screening and educational self-care info. It never diagnoses, never gives odds,
            never prescribes.</p></div>
        </div>
        <div id="ob-existing"></div>
        <div class="selfcare-card mt12" style="background:var(--amber-soft);border-color:var(--amber-border)">
          <b class="tiny" style="color:var(--amber-ink)">BEFORE YOU START — HONEST STORAGE NOTES</b>
          <ul class="tight tiny mt8" style="color:var(--amber-ink)">
            <li>Everything stays in a local database on this device. There are <b>no passwords and no
            encryption</b>: local profiles organise data, they do not secure it.</li>
            <li>Anyone using this browser can switch local profiles — do not store sensitive
            details on a shared machine.</li>
            <li>New accounts start <b>completely empty</b>: no sample meals, no fake totals.</li>
          </ul></div>
        <div class="row mt20 wrap">
          <button class="btn btn-deep" id="ob-start">Start setup →</button>
          <button class="btn btn-ghost" id="ob-skip-all">Skip for now — open guest dashboard</button>
        </div>
      </div></div>`;
    $("#ob-start").onclick = () => { OB.step = 2; renderOnboarding(); };
    $("#ob-skip-all").onclick = (e) => withBusy(e.currentTarget,
      () => obEnterGuest(),
      "Guest dashboard ready — add a profile anytime for personal targets.");
    // progressive: inject "continue as" cards without blocking first paint
    api("/users").then((data) => {
      const slot = $("#ob-existing");
      if (!slot || !(data.users || []).length || OB.step !== 1) return;
      slot.innerHTML = `<div class="selfcare-card mt12">
        <b class="tiny" style="color:var(--primary-deep)">WELCOME BACK — LOCAL PROFILES FOUND ON THIS DEVICE</b>
        <p class="tiny muted mt8">Continue with an existing profile to keep its saved records
        (starting over would create a separate empty profile):</p>
        <div class="row wrap mt8">${data.users.slice(0, 6).map((u) =>
          `<button class="btn btn-soft btn-sm ob-continue" data-uid="${u.id}">Continue as ${esc(u.name)}</button>`).join("")}</div>
      </div>`;
      $$(".ob-continue").forEach((b) => b.onclick = async (e) => {
        await withBusy(e.currentTarget, async () => {
          S.boot = await api("/users/switch", { method: "POST", body: { id: Number(b.dataset.uid) } });
          lsSetLocalUid();
          await enterAppFresh();
        });
      });
    }).catch(() => { /* offline: skip the welcome-back card */ });
    return;
  }

  if (OB.step === 2) {
    view.innerHTML = `<div class="onb">
      <div class="onb-card">
        ${obHeader(2)}
        <div class="ob-error" id="ob-err" hidden role="alert"></div>
        <fieldset class="form-section"><legend>About you</legend>
          <div class="grid cols-2">
            <div class="field"><span class="label">Display name *</span>
              <input class="input" id="ob-name" maxlength="60" value="${esc(OB.data.name)}"
                placeholder="How should NutriCare greet you?" autocomplete="off"></div>
            <div class="field"><span class="label">Age (years, optional)</span>
              <input class="input" id="ob-age" type="number" min="10" max="120" value="${esc(OB.data.age)}" placeholder="e.g. 20"></div>
            <div class="field"><span class="label">Sex for formulas (optional)</span>
              <select class="select" id="ob-sex"><option value="">Prefer not to say</option>
                <option value="female" ${OB.data.sex === "female" ? "selected" : ""}>Female</option>
                <option value="male" ${OB.data.sex === "male" ? "selected" : ""}>Male</option>
                <option value="other" ${OB.data.sex === "other" ? "selected" : ""}>Other / intersex</option></select>
              <p class="form-hint">Used only inside the standard Mifflin-St Jeor formula.
              “Prefer not to say” uses a documented midpoint constant.</p></div>
            <div class="field"><span class="label">Height (cm, optional)</span>
              <input class="input" id="ob-height" type="number" min="50" max="250" step="0.1" value="${esc(OB.data.height)}"></div>
            <div class="field"><span class="label">Weight (kg, optional)</span>
              <input class="input" id="ob-weight" type="number" min="20" max="300" step="0.1" value="${esc(OB.data.weight)}"></div>
            <div class="field"><span class="label">Activity level</span>
              <select class="select" id="ob-activity">${OB_ACTIVITY.map(([v, l]) =>
                `<option value="${v}" ${OB.data.activity === v ? "selected" : ""}>${l}</option>`).join("")}</select></div>
          </div>
          <div class="field"><span class="label">Dietary preferences (optional, comma separated)</span>
            <input class="input" id="ob-prefs" value="${esc(OB.data.prefs)}" placeholder="Vegetarian, nut-friendly, lactose-free…"></div>
        </fieldset>
        <p class="form-hint">* only the name is required. Everything else can be added later from
        My Profile — the food tracker works without any of it.</p>
        ${obNav()}
      </div></div>`;
    obBindNav(() => { obRead(); return obValidateStep2(); });
    return;
  }

  if (OB.step === 3) {
    view.innerHTML = `<div class="onb">
      <div class="onb-card">
        ${obHeader(3)}
        <p class="small muted">These three are <b>optional and consent-based</b>. NutriCare never
        requires medical details, and the nutrition tracker works fully without them. They are only
        used as context reminders you control (for example, the Health Assistant shows your allergy
        notes back to you).</p>
        ${obConsent("allergies", "Allergies & intolerances",
          "Helps you spot relevant context when logging foods or checking symptoms.",
          `<input class="input" id="ob-allergies" value="${esc(OB.data.allergies)}" placeholder="e.g. lactose intolerance, peanuts">`)}
        ${obConsent("medications", "Current medications / supplements",
          "Shown back to you as your own context; the app never advises on medications.",
          `<input class="input" id="ob-meds" value="${esc(OB.data.meds)}" placeholder="e.g. Vitamin D3">`)}
        ${obConsent("history", "Relevant medical history",
          "Free text you control. Leave off if you prefer — nothing is inferred from its absence.",
          `<textarea class="input" id="ob-history" rows="3" maxlength="500">${esc(OB.data.history)}</textarea>`)}
        ${obNav()}
      </div></div>`;
    $$(".ob-consent").forEach((t) => {
      t.checked = OB.consent[t.dataset.consent];
      const box = $(`#ob-box-${t.dataset.consent}`);
      if (box) box.style.display = t.checked ? "block" : "none";
      t.onchange = () => {
        OB.consent[t.dataset.consent] = t.checked;
        const b2 = $(`#ob-box-${t.dataset.consent}`);
        if (b2) b2.style.display = t.checked ? "block" : "none";
      };
    });
    obBindNav(() => { obRead(); return true; });
    return;
  }

  view.innerHTML = `<div class="onb">
    <div class="onb-card">
      ${obHeader(4)}
      <div class="ob-error" id="ob-err" hidden role="alert"></div>
      <fieldset class="form-section"><legend>Nutrition goals (optional)</legend>
        <div class="grid cols-2">
          <div class="field"><span class="label">Goal</span>
            <select class="select" id="ob-goal">
              <option value="maintain" ${OB.data.goal === "maintain" ? "selected" : ""}>Maintain weight (default)</option>
              <option value="mild_loss" ${OB.data.goal === "mild_loss" ? "selected" : ""}>Mild loss (−300 kcal) — my choice</option>
              <option value="mild_gain" ${OB.data.goal === "mild_gain" ? "selected" : ""}>Mild gain (+300 kcal) — my choice</option></select>
            <p class="form-hint">NutriCare never recommends weight loss or restrictive diets.
            Loss/gain appear only because you can choose them.</p></div>
          <div class="field"><span class="label">Macro model</span>
            <select class="select" id="ob-macro">
              <option value="balanced" ${OB.data.macro === "balanced" ? "selected" : ""}>Balanced 40/25/35</option>
              <option value="high_protein" ${OB.data.macro === "high_protein" ? "selected" : ""}>Higher protein 30/35/35</option>
              <option value="low_carb" ${OB.data.macro === "low_carb" ? "selected" : ""}>Lower carb 25/35/40</option></select></div>
          <div class="field"><span class="label">Daily water goal (ml)</span>
            <input class="input" id="ob-water" type="number" min="500" max="6000" step="100" value="${esc(OB.data.water)}"></div>
        </div>
      </fieldset>
      <div class="selfcare-card"><b class="tiny" style="color:var(--primary-deep)">WHAT WILL BE STORED LOCALLY</b>
        <p class="tiny muted mt8">A local profile with your name and whatever you chose above, plus
        empty meal / water / symptom logs. Targets (if computable) are labelled estimates you can
        edit any time in My Profile or Settings.</p></div>
      <div class="row mt20 wrap">
        <button class="btn btn-deep" id="ob-finish">Save & open my dashboard ✓</button>
        <button class="btn btn-ghost" id="ob-back">Back</button>
        <button class="btn btn-ghost" id="ob-skip">Skip — open guest dashboard</button>
      </div>
    </div></div>`;
  $("#ob-back").onclick = () => { obRead(); OB.step = 3; renderOnboarding(); };
  $("#ob-finish").onclick = (e) => withBusy(e.currentTarget,
    () => collectAndSubmit(false), "Profile saved — welcome to your dashboard!");
  $("#ob-skip").onclick = (e) => withBusy(e.currentTarget,
    () => collectAndSubmit(true), "Guest dashboard ready — add a profile anytime.");
}

function lsSetLocalUid() {
  if (S.boot && S.boot.user) lsSet(LS_UID, String(S.boot.user.id));
}

function obHeader(step) {
  const labels = ["Welcome", "About you", "Optional & consent-based", "Goals"];
  return `<div class="row spread"><div class="row" style="gap:8px">
    ${labels.map((l, i) => `<span class="pill ${i + 1 === step ? "pill-teal" : "pill-slate"}">${i + 1} · ${l}</span>`).join("")}
  </div><span class="tiny muted" aria-live="polite">Step ${step} of 4</span></div>
  <h2 style="font-size:22px" class="mt12">${labels[step - 1]}</h2>`;
}

function obConsent(key, title, why, inputs) {
  return `<div class="form-section mt12">
    <div class="row spread">
      <div style="flex:1"><b class="small">${title}</b><p class="tiny muted">${why}</p></div>
      <label class="switch"><input type="checkbox" class="ob-consent" data-consent="${key}"
        aria-label="I choose to add ${esc(title)}"><span class="track"></span></label>
    </div>
    <div class="mt12" id="ob-box-${key}" style="display:none">${inputs}</div>
  </div>`;
}

function obNav() {
  return `<div class="row mt20 wrap">
    <button class="btn btn-deep" id="ob-next">Next →</button>
    <button class="btn btn-ghost" id="ob-back">← Back</button>
    <button class="btn btn-ghost" id="ob-skip">Skip for now</button></div>`;
}

function obBindNav(validate) {
  $("#ob-back").onclick = () => { obRead(); OB.step = Math.max(1, OB.step - 1); renderOnboarding(); };
  $("#ob-skip").onclick = (e) => withBusy(e.currentTarget,
    () => collectAndSubmit(true), "Guest dashboard ready — add a profile anytime.");
  $("#ob-next").onclick = () => { if (validate()) { OB.step += 1; renderOnboarding(); } };
}

function collectAndSubmit(skipOptional) {
  obRead();
  if (skipOptional) {
    const n = (OB.data.name || "").trim();
    if (!n || n.toLowerCase() === "guest") return obEnterGuest();
  }
  const name = (OB.data.name || "").trim() || "Guest";
  const body = { name };
  const profile = {};
  if (!skipOptional) {
    if (!obValidateStep2() || !obValidateStep4()) return Promise.resolve(false);
    const num = (value) => (value === "" || value === null || isNaN(Number(value)) ? null : Number(value));
    const age = num(OB.data.age), height = num(OB.data.height), weight = num(OB.data.weight);
    if (age) profile.age = age;
    if (height) profile.height_cm = height;
    if (weight) profile.weight_kg = weight;
    if (OB.data.sex) profile.sex = OB.data.sex;
    if (OB.data.activity) profile.activity = OB.data.activity;
    if (OB.data.goal) profile.goal = OB.data.goal;
    if (OB.data.macro) profile.macro_model = OB.data.macro;
    if (OB.data.prefs.trim()) {
      profile.dietary_prefs = OB.data.prefs.split(",").map((s) => s.trim()).filter(Boolean);
    }
    if (OB.consent.allergies && OB.data.allergies.trim()) {
      profile.allergies = OB.data.allergies.split(",").map((s) => s.trim()).filter(Boolean);
    }
    if (OB.consent.medications && OB.data.meds.trim()) {
      profile.medications = OB.data.meds.split(",").map((s) => s.trim()).filter(Boolean);
    }
    if (OB.consent.history) profile.medical_history = OB.data.history;
    const water = num(OB.data.water);
    if (water) OB.waterGoal = water;
  }
  return finishOnboardingSubmit(body, profile);
}

function obResetState() {
  OB.step = 1;
  OB.consent = { allergies: false, medications: false, history: false };
  OB.data = { name: "", age: "", sex: "", height: "", weight: "", activity: "moderate",
    prefs: "", allergies: "", meds: "", history: "", goal: "maintain",
    macro: "balanced", water: "2800" };
  OB.waterGoal = null;
}

/* "Skip for now": restore this device's existing Guest profile so repeated
   skips never pile up duplicate Guests; create one only if none exists.
   Uses the same open /users list as the "Continue as …" buttons. */
async function obEnterGuest() {
  let guest = null;
  try {
    const data = await api("/users");
    const guests = (data.users || []).filter((u) => String(u.name).trim().toLowerCase() === "guest");
    if (guests.length) guest = guests[guests.length - 1];   // most recent
  } catch { /* list unavailable — fall back to creating */ }
  try {
    if (guest) await api("/users/switch", { method: "POST", body: { id: guest.id } });
    else await api("/users", { method: "POST", body: { name: "Guest" } });
  } catch (e) {
    const card = $("#ob-err");
    if (card) { card.hidden = false; card.innerHTML = `<div>• ${esc(e.message)}</div>`; }
    else toast(e.message, true);
    return false;
  }
  obResetState();
  location.hash = "#/dashboard";
  await enterAppFresh();
  return true;
}

async function finishOnboardingSubmit(userBody, profileBody) {
  try {
    await api("/users", { method: "POST", body: userBody });
    if (Object.keys(profileBody).length) {
      await api("/profile", { method: "PUT", body: profileBody });  // server commits before responding
    }
    if (OB.waterGoal) {
      await api("/settings", { method: "PUT", body: { water_goal_ml: OB.waterGoal } });
    }
  } catch (e) {
    // stay on the wizard with a visible, persistent error — never a silent dead end
    const card = $("#ob-err");
    if (card) { card.hidden = false; card.innerHTML = `<div>• ${esc(e.message)}</div>`; }
    else toast(e.message, true);
    return false;
  }
  obResetState();
  location.hash = "#/dashboard";   // explicit redirect after a committed save
  await enterAppFresh();
  return true;
}
