/* First-run onboarding wizard (a focused, one-question-at-a-time flow).

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
  ["sedentary", "Mostly sitting", "Seated work or study; little planned activity."],
  ["light", "Lightly active", "Easy movement or exercise 1–3 days each week."],
  ["moderate", "Moderately active", "Regular movement or exercise 3–5 days each week."],
  ["active", "Very active", "Hard exercise most days of the week."],
  ["very_active", "Physical work + training", "A physically demanding job alongside regular training."],
];

// The welcome page is separate. These eight screens collect only the profile
// information NutriCare can actually store and explain each optional input.
const OB_TOTAL_STEPS = 9;

/* Read the active screen before moving. Values live in OB.data so Back/Next
   never discards a response. */
function obRead() {
  const value = (selector, key) => {
    const field = $(selector);
    return field ? field.value : OB.data[key];
  };
  if (OB.step === 2) OB.data.name = value("#ob-name", "name");
  if (OB.step === 3) OB.data.age = value("#ob-age", "age");
  if (OB.step === 4) OB.data.sex = value("#ob-sex", "sex");
  if (OB.step === 5) OB.data.height = value("#ob-height", "height");
  if (OB.step === 6) OB.data.weight = value("#ob-weight", "weight");
  if (OB.step === 7) OB.data.activity = value("#ob-activity", "activity");
  if (OB.step === 8) {
    OB.data.prefs = value("#ob-prefs", "prefs");
    OB.data.allergies = value("#ob-allergies", "allergies");
    OB.data.meds = value("#ob-meds", "meds");
    OB.data.history = value("#ob-history", "history");
  }
  if (OB.step === 9) {
    OB.data.goal = value("#ob-goal", "goal");
    OB.data.macro = value("#ob-macro", "macro");
    OB.data.water = value("#ob-water", "water");
  }
}

function obShowProblems(problems) {
  const box = $("#ob-err");
  if (!box) return problems.length === 0;
  box.hidden = problems.length === 0;
  box.innerHTML = problems.map((problem) => `<div>• ${esc(problem)}</div>`).join("");
  return problems.length === 0;
}

function obRangeProblem(label, value, minimum, maximum) {
  if (value === "" || value === null || value === undefined) return null;
  const number = Number(value);
  return isNaN(number) || number < minimum || number > maximum
    ? `${label} must be between ${minimum} and ${maximum}, or left blank.` : null;
}

function obValidateCurrent() {
  const problems = [];
  if (OB.step === 2 && !OB.data.name.trim()) {
    problems.push("Display name is required (or choose “Skip setup”).");
  }
  if (OB.step === 3) {
    const problem = obRangeProblem("Age", OB.data.age, 10, 120); if (problem) problems.push(problem);
  }
  if (OB.step === 5) {
    const problem = obRangeProblem("Height", OB.data.height, 50, 250); if (problem) problems.push(problem);
  }
  if (OB.step === 6) {
    const problem = obRangeProblem("Weight", OB.data.weight, 20, 300); if (problem) problems.push(problem);
  }
  if (OB.step === 9) {
    const problem = obRangeProblem("Water goal", OB.data.water, 500, 6000); if (problem) problems.push(problem);
  }
  return obShowProblems(problems);
}

function obValidateAll() {
  const problems = [];
  if (!OB.data.name.trim()) problems.push("Display name is required.");
  [["Age", OB.data.age, 10, 120], ["Height", OB.data.height, 50, 250],
    ["Weight", OB.data.weight, 20, 300], ["Water goal", OB.data.water, 500, 6000]]
    .forEach(([label, value, minimum, maximum]) => {
      const problem = obRangeProblem(label, value, minimum, maximum);
      if (problem) problems.push(problem);
    });
  return obShowProblems(problems);
}

async function renderOnboarding() {
  const view = $("#view");
  document.body.classList.toggle("landing-active", OB.step === 1);
  if (OB.step === 1) {
    const nextAppearance = currentTheme() === "dark" ? "light" : "dark";
    view.innerHTML = `<div class="landing">
      <header class="landing-nav" aria-label="NutriCare welcome">
        <div class="landing-nav-inner">
          <a class="landing-brand" href="#landing-top" aria-label="NutriCare welcome page">
            <span class="landing-brand-mark"><img src="/static/images/nutricare-mark.png" alt=""></span>
            <span><b>NutriCare</b><small>NOURISHMENT JOURNAL</small></span>
          </a>
          <div class="landing-nav-actions">
            <a class="landing-nav-link" href="#landing-details">How it works</a>
            <button class="landing-theme-toggle" id="ob-theme-toggle" type="button"
              aria-label="Switch to ${nextAppearance} appearance" title="Switch to ${nextAppearance} appearance">
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>
              <span id="ob-theme-label">Switch to ${nextAppearance} appearance</span>
            </button>
            <div class="landing-account-actions">
              <button class="btn btn-deep landing-primary-action" id="ob-start">Create a new profile</button>
              <button class="btn btn-ghost landing-secondary-action" id="ob-skip-all">Open guest dashboard</button>
            </div>
          </div>
        </div>
      </header>

      <main id="landing-top">
        <section class="landing-hero" aria-labelledby="landing-title">
          <div class="landing-hero-copy">
            <p class="landing-kicker"><span aria-hidden="true"></span> A local journal for everyday nourishment</p>
            <h1 id="landing-title">Keep the nutrition record that fits your real day.</h1>
            <p class="landing-lede">NutriCare helps you log meals and water, review the calories and nutrients attached to what you record, and keep your own data close at hand. Personal targets appear only when you provide the details needed for an estimate.</p>
            <p class="landing-local-note"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/></svg> Local profiles organise records on this device. They are not password-protected or encrypted.</p>
          </div>
          <figure class="landing-hero-media">
            <img src="/static/images/landing-cooking.jpg" alt="Vegetables cooking in a pan on a stovetop" fetchpriority="high">
            <div class="landing-photo-caption">A daily record starts with the meal in front of you.</div>
            <figcaption>Editorial photograph. NutriCare does not identify, weigh, or calculate this pictured meal.</figcaption>
          </figure>
        </section>

        <section class="landing-start-panel" aria-labelledby="landing-start-title">
          <div>
            <p class="landing-section-kicker">Start with what you need</p>
            <h2 id="landing-start-title">Use a profile for saved preferences, or begin as a guest.</h2>
          </div>
          <div class="landing-start-copy">
            <p>A profile can hold the optional details you choose to add. Guest mode still lets you log food, water, reports, and health-assistant entries; it simply leaves personal targets off until enough profile details are available.</p>
            <a href="#landing-details">See what NutriCare records <span aria-hidden="true">→</span></a>
          </div>
        </section>

        <div id="ob-existing" class="landing-existing-slot" aria-live="polite"></div>

        <section class="landing-details" id="landing-details" aria-labelledby="landing-details-title">
          <div class="landing-section-intro">
            <p class="landing-section-kicker">Useful, clear, and limited on purpose</p>
            <h2 id="landing-details-title">A journal for information you can check.</h2>
            <p>Every feature is designed around an explicit record, a stated calculation, or a clear limit. NutriCare does not fill an empty log with sample intake or turn a missing detail into a health claim.</p>
          </div>
          <div class="landing-feature-grid">
            <article class="landing-feature-card">
              <span class="landing-feature-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v7a4 4 0 004 4h1V3"/><path d="M7 3v11"/><path d="M14 3v8a3 3 0 003 3h1V3"/><path d="M18 14v7"/></svg></span>
              <h3>Record meals and water</h3>
              <p>Organise food into Breakfast, Lunch, Snacks, and Dinner; search the documented catalogue or add a custom item, then log hydration alongside it.</p>
            </article>
            <article class="landing-feature-card">
              <span class="landing-feature-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M22 20H2"/></svg></span>
              <h3>Review recorded nutrition</h3>
              <p>Daily and weekly views derive calories, macros, hydration, and a tracked micronutrient subset from your saved entries. Calculated calorie and macro targets are labelled estimates.</p>
            </article>
            <article class="landing-feature-card">
              <span class="landing-feature-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14a2 2 0 002-2v-3"/><path d="M3 16v3a2 2 0 002 2"/></svg></span>
              <h3>Export what you entered</h3>
              <p>Download a daily PDF nutrition record, a food-log CSV, or a complete JSON export of the current local profile whenever you need a copy.</p>
            </article>
            <article class="landing-feature-card">
              <span class="landing-feature-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h3l2-2h6l2 2h3v12H4z"/><circle cx="12" cy="13" r="3"/></svg></span>
              <h3>Confirm photo suggestions</h3>
              <p>The food scanner suggests one dominant dish from a photo, then asks you to confirm it, set a portion, and choose a meal. It names unavailable nutrition instead of inventing it.</p>
            </article>
            <article class="landing-feature-card">
              <span class="landing-feature-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M8 12h8M12 8v8"/></svg></span>
              <h3>Use a safety-led health assistant</h3>
              <p>A structured symptom check screens for emergency warning signs and offers general education. It never diagnoses, gives odds, or prescribes treatment.</p>
            </article>
            <article class="landing-feature-card">
              <span class="landing-feature-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 018 0v3"/></svg></span>
              <h3>Keep the limits visible</h3>
              <p>Profiles are local rather than secure accounts. Anyone using this browser can switch them, so avoid sensitive details on a shared device.</p>
            </article>
          </div>
        </section>

        <section class="landing-method" aria-labelledby="landing-method-title">
          <figure class="landing-method-photo">
            <img src="/static/images/landing-thali.jpg" alt="An Indian thali with rice, curry, and flatbread">
            <figcaption>Editorial photograph. Portions and recipes vary; log the food and amount you actually had.</figcaption>
          </figure>
          <div class="landing-method-copy">
            <p class="landing-section-kicker">Documented sources, explained limits</p>
            <h2 id="landing-method-title">Nutrition values are useful only when their basis is clear.</h2>
            <p>NutriCare’s built-in food catalogue records values per 100 g and distinguishes raw, cooked, and prepared states where documented. Its sources are identified in the product data, including IFCT 2017 and USDA FoodData Central.</p>
            <ul class="landing-method-list">
              <li><b>Recipe variation is real.</b> Prepared dishes can vary by ingredients, oil, brand, and serving size. Approximate and recipe-derived values are marked as such.</li>
              <li><b>Targets are estimates, not instructions.</b> When enough optional profile fields are supplied, NutriCare uses a stated Mifflin–St Jeor calculation and the activity level you select.</li>
              <li><b>Micronutrient coverage is focused.</b> Reports track fiber, sodium, potassium, calcium, and iron rather than claiming a complete clinical analysis.</li>
            </ul>
          </div>
        </section>

        <section class="landing-safety" aria-labelledby="landing-safety-title">
          <div>
            <p class="landing-section-kicker">Read before you add sensitive details</p>
            <h2 id="landing-safety-title">NutriCare supports a personal record. It is not a medical service.</h2>
          </div>
          <div class="landing-safety-copy">
            <p>Use urgent local services for emergency symptoms. For individual dietary, medical, or medication decisions, speak with a qualified clinician or dietitian.</p>
            <p>Only add optional health context if you are comfortable keeping it in a local, unencrypted profile on this device.</p>
          </div>
        </section>
      </main>

      <footer class="landing-footer">
        <div class="landing-footer-inner">
          <div class="landing-brand landing-footer-brand"><span class="landing-brand-mark"><img src="/static/images/nutricare-mark.png" alt=""></span><span><b>NutriCare</b><small>NOURISHMENT JOURNAL</small></span></div>
          <p>Food, hydration, and health notes remain separate for each local profile. No account sign-in is required.</p>
          <p class="landing-photo-credits">Real editorial photography from <a href="https://www.pexels.com/photo/cooking-vegetables-on-a-pot-and-pan-15257786/" target="_blank" rel="noreferrer">Pexels</a> and <a href="https://www.pexels.com/photo/traditional-indian-thali-meal-with-naan-bread-29148133/" target="_blank" rel="noreferrer">Pexels</a>.</p>
        </div>
      </footer>
    </div>`;
    $("#ob-start").onclick = () => { OB.step = 2; renderOnboarding(); };
    $("#ob-skip-all").onclick = (e) => withBusy(e.currentTarget,
      () => obEnterGuest(),
      "Guest dashboard ready — add a profile anytime for personal targets.");
    $("#ob-theme-toggle").onclick = () => {
      const next = currentTheme() === "dark" ? "light" : "dark";
      setTheme(next);
      const label = $("#ob-theme-label");
      const button = $("#ob-theme-toggle");
      const future = next === "dark" ? "light" : "dark";
      if (label) label.textContent = `Switch to ${future} appearance`;
      if (button) {
        button.setAttribute("aria-label", `Switch to ${future} appearance`);
        button.setAttribute("title", `Switch to ${future} appearance`);
      }
    };
    // Progressive: returning profiles are offered without delaying the landing page.
    api("/users").then((data) => {
      const slot = $("#ob-existing");
      if (!slot || !(data.users || []).length || OB.step !== 1) return;
      slot.innerHTML = `<section class="landing-existing" aria-labelledby="landing-existing-title">
        <div><p class="landing-section-kicker">Welcome back</p><h2 id="landing-existing-title">Continue with a saved local profile.</h2></div>
        <div><p>Your saved records stay with the profile you choose. Starting a new profile creates a separate, empty record.</p>
          <div class="landing-profile-buttons">${data.users.slice(0, 6).map((u) =>
            `<button class="btn btn-soft ob-continue" data-uid="${u.id}">Continue as ${esc(u.name)}</button>`).join("")}</div>
        </div>
      </section>`;
      $$(".ob-continue").forEach((b) => b.onclick = async (e) => {
        await withBusy(e.currentTarget, async () => {
          S.boot = await api("/users/switch", { method: "POST", body: { id: Number(b.dataset.uid) } });
          lsSetLocalUid();
          await enterAppFresh();
        });
      });
    }).catch(() => { /* Offline: the new-profile and guest paths still work. */ });
    return;
  }

  renderProfileWizard();
}

function renderProfileWizard() {
  if (OB.step === 2) {
    obWizardPage({
      eyebrow: "Profile setup",
      title: "What should we call you?",
      description: "This is the only detail needed to create a local profile. You can add or change the rest later.",
      content: `<label class="ob-field-label" for="ob-name">Display name</label>
        <input class="ob-large-input" id="ob-name" maxlength="60" value="${esc(OB.data.name)}"
          placeholder="Your name" autocomplete="off">`,
      validate: obValidateCurrent,
    });
    return;
  }

  if (OB.step === 3) {
    obWizardPage({
      eyebrow: "Optional profile detail",
      title: "What is your age?",
      description: "Age is used only when all formula inputs are present to calculate a labelled energy estimate.",
      content: obWheelField("ob-age", "Age in years", OB.data.age, "years", 10, 120, 1, 30),
      validate: obValidateCurrent,
      bind: obBindNumberWheels,
    });
    return;
  }

  if (OB.step === 4) {
    obWizardPage({
      eyebrow: "Optional formula input",
      title: "Which formula input should we use?",
      description: "Female and male select the standard Mifflin–St Jeor constants. Prefer not to say uses its documented midpoint; this does not describe your gender.",
      content: `<input id="ob-sex" type="hidden" value="${esc(OB.data.sex)}">
        <div class="ob-choice-grid" role="group" aria-label="Sex for energy formula">
          ${obFormulaChoice("female", "Female", "Uses the female formula constant")}
          ${obFormulaChoice("male", "Male", "Uses the male formula constant")}
          ${obFormulaChoice("other", "Prefer not to say", "Uses the documented midpoint")}
        </div>`,
      validate: obValidateCurrent,
      bind: () => obBindChoiceButtons(".ob-sex-choice", "#ob-sex"),
    });
    return;
  }

  if (OB.step === 5) {
    obWizardPage({
      eyebrow: "Optional profile detail",
      title: "How tall are you?",
      description: "Enter your height in centimetres. This stays editable in My Profile.",
      content: obWheelField("ob-height", "Height in centimetres", OB.data.height, "cm", 50, 250, 1, 170),
      validate: obValidateCurrent,
      bind: obBindNumberWheels,
    });
    return;
  }

  if (OB.step === 6) {
    obWizardPage({
      eyebrow: "Optional profile detail",
      title: "What is your current weight?",
      description: "Enter kilograms if you want an energy estimate. NutriCare does not calculate or claim an ideal weight range.",
      content: obWheelField("ob-weight", "Current weight in kilograms", OB.data.weight, "kg", 20, 300, 0.1, 70),
      validate: obValidateCurrent,
      bind: obBindNumberWheels,
    });
    return;
  }

  if (OB.step === 7) {
    obWizardPage({
      eyebrow: "Daily routine",
      title: "How active are you most weeks?",
      description: "Choose the description closest to your usual routine. You can update it later; it is only used for an optional energy estimate.",
      content: `<input id="ob-activity" type="hidden" value="${esc(OB.data.activity)}">
        <div class="ob-activity-list" role="group" aria-label="Activity level">
          ${OB_ACTIVITY.map(([value, title, detail]) => obActivityChoice(value, title, detail)).join("")}
        </div>`,
      validate: obValidateCurrent,
      bind: () => obBindChoiceButtons(".ob-activity-choice", "#ob-activity"),
    });
    return;
  }

  if (OB.step === 8) {
    obWizardPage({
      eyebrow: "Optional context",
      title: "Anything you want your journal to remember?",
      description: "Dietary preferences can help filter food suggestions. Health notes are off by default and are never required for logging food or water.",
      content: `<div class="ob-compact-field"><label class="ob-field-label" for="ob-prefs">Dietary preferences</label>
          <input class="input" id="ob-prefs" value="${esc(OB.data.prefs)}" placeholder="Vegetarian, lactose-free, sesame allergy…">
          <p>Optional, comma-separated. Check entries before relying on any food suggestion.</p></div>
        <div class="ob-consent-stack">
          ${obConsent("allergies", "Allergies & intolerances",
            "Shows your own notes back to you when relevant; it does not certify food as safe.",
            `<input class="input" id="ob-allergies" value="${esc(OB.data.allergies)}" placeholder="e.g. lactose intolerance, peanuts">`)}
          ${obConsent("medications", "Medications / supplements",
            "Stored only as context. NutriCare never advises on medications.",
            `<input class="input" id="ob-meds" value="${esc(OB.data.meds)}" placeholder="e.g. Vitamin D3">`)}
          ${obConsent("history", "Relevant health notes",
            "Free text you control. Leave this off if you prefer.",
            `<textarea class="input" id="ob-history" rows="3" maxlength="500">${esc(OB.data.history)}</textarea>`)}
        </div>`,
      validate: obValidateCurrent,
      bind: obBindConsentControls,
    });
    return;
  }

  obWizardPage({
    eyebrow: "Optional targets",
    title: "Set the starting preferences you want.",
    description: "These settings stay editable. Any target NutriCare can calculate is an estimate, not medical advice.",
    content: `<div class="ob-goal-fields">
      <div class="ob-compact-field"><label class="ob-field-label" for="ob-goal">Goal</label>
        <select class="select" id="ob-goal">
          <option value="maintain" ${OB.data.goal === "maintain" ? "selected" : ""}>Maintain weight (default)</option>
          <option value="mild_loss" ${OB.data.goal === "mild_loss" ? "selected" : ""}>Mild loss (−300 kcal) — my choice</option>
          <option value="mild_gain" ${OB.data.goal === "mild_gain" ? "selected" : ""}>Mild gain (+300 kcal) — my choice</option>
        </select></div>
      <div class="ob-compact-field"><label class="ob-field-label" for="ob-macro">Macro model</label>
        <select class="select" id="ob-macro">
          <option value="balanced" ${OB.data.macro === "balanced" ? "selected" : ""}>Balanced 40/25/35</option>
          <option value="high_protein" ${OB.data.macro === "high_protein" ? "selected" : ""}>Higher protein 30/35/35</option>
          <option value="low_carb" ${OB.data.macro === "low_carb" ? "selected" : ""}>Lower carb 25/35/40</option>
        </select></div>
      <div class="ob-compact-field"><label class="ob-field-label" for="ob-water">Daily water goal</label>
        <div class="ob-unit-input"><input class="input" id="ob-water" type="number" min="500" max="6000" step="100" value="${esc(OB.data.water)}"><span>ml</span></div>
        <p>Optional. Enter 500–6000 ml, or leave it blank.</p></div>
      </div>
      <div class="ob-storage-note"><b>Stored locally</b><span>Your profile keeps only the information you choose above, plus empty meal, water, and health-assistant records. Local profiles are not password-protected or encrypted.</span></div>`,
    validate: () => obValidateCurrent() && obValidateAll(),
    final: true,
  });
}

function obWizardPage({ eyebrow, title, description, content, validate, bind, final = false }) {
  const view = $("#view");
  const primaryLabel = final ? "Save and open dashboard" : "Next";
  view.innerHTML = `<div class="onb onb-wizard">
    <div class="ob-wizard-card">
      <div class="ob-wizard-top">
        ${obProgress()}
        <button class="ob-skip-setup" type="button" id="ob-skip">Skip setup</button>
      </div>
      <section class="ob-question" aria-labelledby="ob-question-title">
        <p class="ob-question-kicker">${esc(eyebrow)}</p>
        <h2 id="ob-question-title">${esc(title)}</h2>
        <p class="ob-question-description">${esc(description)}</p>
        <div class="ob-error" id="ob-err" hidden role="alert"></div>
        <div class="ob-question-content">${content}</div>
      </section>
      ${obWizardNav(primaryLabel)}
    </div>
  </div>`;
  if (bind) bind();
  obBindWizard(validate, final);
}

function obProgress() {
  const current = OB.step - 1;
  return `<div class="ob-progress-wrap"><div class="ob-progress" role="progressbar" aria-valuemin="1" aria-valuemax="${OB_TOTAL_STEPS - 1}" aria-valuenow="${current}" aria-label="Profile setup step ${current} of ${OB_TOTAL_STEPS - 1}">
    ${Array.from({ length: OB_TOTAL_STEPS - 1 }, (_, index) => `<i class="${index < current ? "done" : ""}${index + 1 === current ? " current" : ""}" aria-hidden="true"></i>`).join("")}
  </div><span>Step ${current} of ${OB_TOTAL_STEPS - 1}</span></div>`;
}

function obWizardNav(primaryLabel) {
  return `<footer class="ob-wizard-footer">
    <button class="ob-footer-action ob-footer-back" id="ob-back" type="button"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>Back</button>
    <button class="ob-footer-action ob-footer-next" id="ob-next" type="button">${esc(primaryLabel)}<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg></button>
  </footer>`;
}

function obWheelNumber(value, step) {
  return step < 1 ? Number(value).toFixed(1) : String(Math.round(Number(value)));
}

function obWheelRows(current, minimum, maximum, step, selected) {
  return [-2, -1, 0, 1, 2].map((offset) => {
    const value = Math.max(minimum, Math.min(maximum, current + offset * step));
    const kind = offset === 0 ? (selected ? "is-selected" : "is-suggested") : `is-offset-${Math.abs(offset)}`;
    return `<span class="ob-wheel-value ${kind}" aria-hidden="true">${obWheelNumber(value, step)}</span>`;
  }).join("");
}

function obWheelArrow(direction) {
  const path = direction < 0 ? "m14 6-6 6 6 6" : "m10 6 6 6-6 6";
  return `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${path}"/></svg>`;
}

function obWheelField(id, label, value, unit, minimum, maximum, step, fallback) {
  const selected = value !== "" && value !== null && value !== undefined;
  const current = selected ? Number(value) : fallback;
  const selectedText = selected ? `Selected ${obWheelNumber(current, step)} ${unit}` : `No ${label.toLowerCase()} selected`;
  return `<div class="ob-wheel-field">
    <span class="ob-field-label" id="${id}-label">${esc(label)} <em>optional</em></span>
    <input id="${id}" type="hidden" value="${selected ? esc(value) : ""}">
    <div class="ob-wheel-shell">
      <button class="ob-wheel-arrow" type="button" data-wheel-for="${id}" data-wheel-change="-1" aria-label="Decrease ${esc(label)}">${obWheelArrow(-1)}</button>
      <div class="ob-wheel-picker" id="${id}-wheel" tabindex="0" role="spinbutton" aria-labelledby="${id}-label" aria-describedby="${id}-hint" aria-valuemin="${minimum}" aria-valuemax="${maximum}" aria-valuenow="${current}" aria-valuetext="${esc(selectedText)}"
        data-number-wheel data-input="${id}" data-minimum="${minimum}" data-maximum="${maximum}" data-step="${step}" data-fallback="${fallback}" data-unit="${esc(unit)}" data-label="${esc(label.toLowerCase())}">
        <div class="ob-wheel-values" id="${id}-values">${obWheelRows(current, minimum, maximum, step, selected)}</div>
      </div>
      <button class="ob-wheel-arrow" type="button" data-wheel-for="${id}" data-wheel-change="1" aria-label="Increase ${esc(label)}">${obWheelArrow(1)}</button>
    </div>
    <div class="ob-wheel-actions"><small id="${id}-hint">Use the arrows, swipe the wheel, or use the arrow keys. Leave it untouched to keep this detail blank.</small>
      <span class="ob-wheel-unit" aria-hidden="true">${esc(unit)}</span>
      <button class="ob-wheel-clear" id="${id}-clear" type="button" ${selected ? "" : "hidden"}>Clear</button></div>
  </div>`;
}

function obBindNumberWheels() {
  $$("[data-number-wheel]").forEach((wheel) => {
    const input = $(`#${wheel.dataset.input}`);
    if (!input) return;
    const minimum = Number(wheel.dataset.minimum);
    const maximum = Number(wheel.dataset.maximum);
    const step = Number(wheel.dataset.step);
    const fallback = Number(wheel.dataset.fallback);
    const factor = 10 ** ((String(step).split(".")[1] || "").length);
    const current = () => input.value === "" ? fallback : Number(input.value);
    const selected = () => input.value !== "";
    const redraw = () => {
      const value = current();
      const rows = $(`#${input.id}-values`);
      const clear = $(`#${input.id}-clear`);
      if (rows) rows.innerHTML = obWheelRows(value, minimum, maximum, step, selected());
      if (clear) clear.hidden = !selected();
      wheel.setAttribute("aria-valuenow", String(value));
      wheel.setAttribute("aria-valuetext", selected()
        ? `Selected ${obWheelNumber(value, step)} ${wheel.dataset.unit}`
        : `No ${wheel.dataset.label} selected. Choose a value or continue without it.`);
    };
    const change = (direction) => {
      const next = Math.max(minimum, Math.min(maximum,
        Math.round((current() + direction * step) * factor) / factor));
      input.value = obWheelNumber(next, step);
      redraw();
    };
    $$(`[data-wheel-for="${input.id}"]`).forEach((button) => {
      button.onclick = () => change(Number(button.dataset.wheelChange));
    });
    wheel.onkeydown = (event) => {
      if (["ArrowUp", "ArrowRight"].includes(event.key)) { event.preventDefault(); change(1); }
      if (["ArrowDown", "ArrowLeft"].includes(event.key)) { event.preventDefault(); change(-1); }
      if (event.key === "Home") { event.preventDefault(); input.value = obWheelNumber(minimum, step); redraw(); }
      if (event.key === "End") { event.preventDefault(); input.value = obWheelNumber(maximum, step); redraw(); }
    };
    wheel.addEventListener("wheel", (event) => {
      event.preventDefault();
      change(event.deltaY > 0 ? -1 : 1);
    }, { passive: false });
    let startY = null;
    wheel.addEventListener("pointerdown", (event) => { startY = event.clientY; });
    wheel.addEventListener("pointerup", (event) => {
      if (startY === null) return;
      const distance = event.clientY - startY;
      startY = null;
      if (Math.abs(distance) >= 20) change(distance < 0 ? 1 : -1);
    });
    const clear = $(`#${input.id}-clear`);
    if (clear) clear.onclick = () => { input.value = ""; redraw(); wheel.focus(); };
    redraw();
  });
}

function obFormulaChoice(value, title, detail) {
  const selected = OB.data.sex === value;
  return `<button class="ob-select-card ob-sex-choice ${selected ? "selected" : ""}" type="button" data-ob-value="${value}" aria-pressed="${selected ? "true" : "false"}">
    <span class="ob-choice-glyph" aria-hidden="true">${value === "female"
      ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="9" r="5"/><path d="M12 14v8M8.5 18H15.5"/></svg>`
      : value === "male" ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="9" cy="15" r="5"/><path d="m12.5 11.5 6-6M14.5 5.5h4v4"/></svg>`
      : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="10" r="5"/><path d="M12 15v7M8.5 18H15.5"/></svg>`}</span>
    <b>${esc(title)}</b><small>${esc(detail)}</small></button>`;
}

function obActivityChoice(value, title, detail) {
  const selected = OB.data.activity === value;
  return `<button class="ob-activity-choice ${selected ? "selected" : ""}" type="button" data-ob-value="${value}" aria-pressed="${selected ? "true" : "false"}">
    <span class="ob-activity-mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 18h14"/><path d="M7 14h10"/><path d="M9 10h6"/><path d="M12 4v6"/></svg></span><span><b>${esc(title)}</b><small>${esc(detail)}</small></span>
  </button>`;
}

function obBindChoiceButtons(selector, inputSelector) {
  $$(selector).forEach((button) => button.onclick = () => {
    const input = $(inputSelector);
    if (input) input.value = button.dataset.obValue;
    obRead();
    renderOnboarding();
  });
}

function obBindConsentControls() {
  $$(".ob-consent").forEach((toggle) => {
    toggle.checked = OB.consent[toggle.dataset.consent];
    const box = $(`#ob-box-${toggle.dataset.consent}`);
    if (box) box.style.display = toggle.checked ? "block" : "none";
    toggle.onchange = () => {
      OB.consent[toggle.dataset.consent] = toggle.checked;
      const nextBox = $(`#ob-box-${toggle.dataset.consent}`);
      if (nextBox) nextBox.style.display = toggle.checked ? "block" : "none";
    };
  });
}

function obConsent(key, title, why, inputs) {
  return `<div class="ob-consent-card">
    <div><b>${esc(title)}</b><p>${esc(why)}</p></div>
    <label class="switch"><input type="checkbox" class="ob-consent" data-consent="${key}" aria-label="I choose to add ${esc(title)}"><span class="track"></span></label>
    <div class="ob-consent-input" id="ob-box-${key}" style="display:none">${inputs}</div>
  </div>`;
}

function obBindWizard(validate, final = false) {
  $("#ob-back").onclick = () => { obRead(); OB.step = Math.max(1, OB.step - 1); renderOnboarding(); };
  $("#ob-skip").onclick = (event) => withBusy(event.currentTarget,
    () => collectAndSubmit(true), "Guest dashboard ready — add a profile anytime.");
  $("#ob-next").onclick = (event) => {
    obRead();
    if (!validate()) return;
    if (final) {
      withBusy(event.currentTarget, () => collectAndSubmit(false), "Profile saved — welcome to your dashboard!");
      return;
    }
    OB.step = Math.min(OB_TOTAL_STEPS, OB.step + 1);
    renderOnboarding();
  };
}

function lsSetLocalUid() {
  if (S.boot && S.boot.user) lsSet(LS_UID, String(S.boot.user.id));
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
    if (!obValidateAll()) return Promise.resolve(false);
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
