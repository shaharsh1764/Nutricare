/* Health Profile + Health Assistant views. */
"use strict";

/* ============================================================ PROFILE */
async function renderProfile() {
  const data = await api("/profile");
  const p = data.profile;
  const t = data.targets;
  $("#view").innerHTML = `
  <div class="page-head">
    <div><h2>Personal Health Profile</h2>
      <p class="sub">Only what the app actually uses for calculations and safety context is collected.
      Everything stays in your local database and can be deleted at any time. <b>Nothing here is
      required to log food</b> — targets appear once age, sex, height, weight and activity are set,
      and they are always labelled estimates.</p></div>
    <div class="row">
      ${t ? `<span class="pill pill-mint">Target ${fmt(t.kcal)} kcal/day</span>` : `<span class="pill pill-amber">Profile incomplete</span>`}
      <button class="btn btn-primary" id="p-save">Save Profile</button>
    </div>
  </div>

  <div class="grid cols-2" style="align-items:start">
    <div class="card">
      <div class="card-head"><span class="card-title">1 · Biometrics & energy</span>
        <span class="icon-pill tint-teal">📐</span></div>
      <div class="grid cols-2">
        <div class="field"><span class="label">Display name</span><input class="input" id="p-name" value="${esc(S.boot.user ? S.boot.user.name : "")}" maxlength="60">
          <p class="form-hint">Stored only in this device's local database.</p></div>
        <div class="field"><span class="label">Age (years)</span><input class="input" id="p-age" type="number" min="10" max="120" value="${p.age ?? ""}"></div>
        <div class="field"><span class="label">Biological sex (for formulas)</span>
          <select class="select" id="p-sex">
            <option value="">—</option>
            <option value="female" ${p.sex === "female" ? "selected" : ""}>Female</option>
            <option value="male" ${p.sex === "male" ? "selected" : ""}>Male</option>
            <option value="other" ${p.sex === "other" ? "selected" : ""}>Other / prefer not to say</option>
          </select></div>
        <div class="field"><span class="label">Height (cm)</span><input class="input" id="p-height" type="number" min="50" max="250" step="0.1" value="${p.height_cm ?? ""}"></div>
        <div class="field"><span class="label">Weight (kg)</span><input class="input" id="p-weight" type="number" min="20" max="300" step="0.1" value="${p.weight_kg ?? ""}"></div>
        <div class="field"><span class="label">Activity level</span>
          <select class="select" id="p-activity">
            ${Object.entries({ sedentary: "Sedentary (desk study)", light: "Light (1-3 d/wk)",
              moderate: "Moderate (3-5 d/wk)", active: "Active (6-7 d/wk)",
              very_active: "Very active (physical job)" })
              .map(([k, v]) => `<option value="${k}" ${p.activity === k ? "selected" : ""}>${v}</option>`).join("")}
          </select></div>
        <div class="field"><span class="label">Goal</span>
          <select class="select" id="p-goal">
            <option value="maintain" ${p.goal === "maintain" ? "selected" : ""}>Maintain weight</option>
            <option value="mild_loss" ${p.goal === "mild_loss" ? "selected" : ""}>Mild loss (−300 kcal)</option>
            <option value="mild_gain" ${p.goal === "mild_gain" ? "selected" : ""}>Mild gain (+300 kcal)</option>
          </select></div>
        <div class="field"><span class="label">Macro model</span>
          <select class="select" id="p-macro">
            <option value="balanced" ${p.macro_model === "balanced" ? "selected" : ""}>Balanced 40/25/35</option>
            <option value="high_protein" ${p.macro_model === "high_protein" ? "selected" : ""}>High protein 30/35/35</option>
            <option value="low_carb" ${p.macro_model === "low_carb" ? "selected" : ""}>Lower carb 25/35/40</option>
          </select></div>
      </div>
      ${t ? `<div class="selfcare-card mt8"><b class="small">Calculated energy profile (Mifflin-St Jeor × activity factor)</b>
        <div class="row wrap mt8">
          <span class="pill pill-slate">BMR ${fmt(t.bmr)} kcal</span>
          <span class="pill pill-teal">Target ${fmt(t.kcal)} kcal/day</span>
          <span class="pill pill-mint">P ${fmt(t.protein_g)}g</span>
          <span class="pill pill-sky">C ${fmt(t.carbs_g)}g</span>
          <span class="pill pill-amber">F ${fmt(t.fat_g)}g</span>
        </div></div>` : ""}
    </div>

    <div class="grid" style="gap:16px">
      <div class="card">
        <div class="card-head"><span class="card-title">2 · Dietary preferences & allergies</span>
          <span class="icon-pill tint-amber">🥗</span></div>
        <div class="field"><span class="label">Dietary preferences (comma separated)</span>
          <input class="input" id="p-prefs" value="${esc((p.dietary_prefs || []).join(", "))}" placeholder="Vegetarian, nut-friendly…"></div>
        <div class="field"><span class="label">Allergies / intolerances (comma separated)</span>
          <input class="input" id="p-allergies" value="${esc((p.allergies || []).join(", "))}" placeholder="Lactose intolerance, peanuts…"></div>
        <p class="tiny muted">Used only as context reminders (e.g. the Health Assistant shows them back to you). Never shared externally.</p>
      </div>
      <div class="card">
        <div class="card-head"><span class="card-title">3 · Medications & history</span>
          <span class="icon-pill tint-rose">💊</span></div>
        <div class="field"><span class="label">Current medications / supplements (comma separated)</span>
          <input class="input" id="p-meds" value="${esc((p.medications || []).join(", "))}" placeholder="Vitamin D3…"></div>
        <div class="field"><span class="label">Relevant medical history (optional, free text)</span>
          <textarea class="input" id="p-history" rows="3" maxlength="500" placeholder="Optional — only what you want the assistant to keep in mind.">${esc(p.medical_history || "")}</textarea></div>
        <p class="tiny muted">Optional fields. Leave blank if you prefer — the app works without them.</p>
      </div>
      <div class="card" style="border-color:var(--rose-border);background:var(--warning-bg)">
        <div class="card-head"><span class="card-title" style="color:var(--rose)">Data control</span>
          <span class="icon-pill tint-rose">${ICONS.shield}</span></div>
        <p class="small muted">Delete every meal, water log, symptom assessment and profile detail from the
        database. The food dataset itself is kept (it is not personal data).</p>
        <div class="row mt12">
          <button class="btn btn-danger" id="p-purge"> Delete all my data</button>
          <button class="btn btn-ghost" id="p-export">${ICONS.download} Export my data (JSON)</button>
        </div>
      </div>
    </div>
  </div>`;

  $("#p-save").onclick = async (ev) => withBusy(ev.currentTarget, async () => {
    const split = (id) => $(id).value.split(",").map((s) => s.trim()).filter(Boolean);
    const body = {
      sex: $("#p-sex").value || null,
      activity: $("#p-activity").value, goal: $("#p-goal").value,
      macro_model: $("#p-macro").value, medical_history: $("#p-history").value,
      dietary_prefs: split("#p-prefs"), allergies: split("#p-allergies"), medications: split("#p-meds"),
    };
    const age = $("#p-age").value, height = $("#p-height").value, weight = $("#p-weight").value;
    if (age !== "") body.age = Number(age);
    if (height !== "") body.height_cm = Number(height);
    if (weight !== "") body.weight_kg = Number(weight);
    try {
      const newName = $("#p-name").value.trim();
      if (newName && newName !== S.boot.user.name) {
        S.boot = await api("/users/me", { method: "PUT", body: { name: newName } });
      }
      const res = await api("/profile", { method: "PUT", body });
      S.boot.profile = res.profile; S.boot.targets = res.targets;
      toast("Profile saved"); renderProfile(); refreshSideGoal(); refreshBanners();
    } catch (e) { toast(e.message, true); }
  });
  $("#p-purge").onclick = async () => {
    const ok = await confirmModal("Delete ALL personal data?",
      "Meals, water logs, symptom assessments and profile details will be permanently removed from the local database. This cannot be undone.",
      "Yes, delete everything");
    if (!ok) return;
    await api("/profile/purge", { method: "POST" });
    toast("All personal data deleted");
    S.boot = await api("/bootstrap");
    location.hash = "#/dashboard"; refreshView();
  };
  $("#p-export").onclick = () => location.href = "/api/export.json";
}

/* ============================================================ ASSISTANT */
const SYMPTOM_TILES = ["Fatigue / brain fog", "Headache", "Bloating", "Sore throat",
  "Muscle ache", "Nausea", "Poor sleep", "Dizziness"];
const ASSOC_OPTIONS = ["Slight afternoon headache", "Sluggishness after meals",
  "Fever or chills", "Cough", "Poor sleep last night", "Recent heavy exercise",
  "Skipped a meal", "Long screen / study session"];

async function renderAssistant() {
  const [history, signs] = await Promise.all([
    api("/assistant/history"), api("/assistant/warning-signs")]);
  $("#view").innerHTML = `
  <div class="safety-banner">
    <span class="icon-pill tint-teal" style="width:38px;height:38px">${ICONS.shield}</span>
    <div>
      <div class="row wrap" style="gap:8px">
        <b class="small" style="color:var(--primary-deep)">MEDICAL SAFETY & EVIDENCE FRAMEWORK</b>
        <span class="pill pill-slate">${esc(S.boot.assistant.engine)}</span>
        <span class="pill pill-amber">Limited offline engine — no AI API call</span>
      </div>
      <p class="small muted mt8">NutriCare Health Assistant provides <b>evidence-based educational
      insights and self-care suggestions only</b>. It is not a clinical diagnosis and not a substitute
      for professional medical care. If you are experiencing chest pain, difficulty breathing, or severe
      sudden symptoms, immediately call your local emergency number (India 112 · US 911) or visit the
      nearest emergency department.</p>
    </div>
  </div>

  <div class="grid cols-21 mt16" style="align-items:start">
    <form class="card" id="a-form" novalidate>
      <div class="card-head"><div><span class="tiny muted" style="font-weight:700;letter-spacing:.08em">TRIAGE MODULE</span>
        <h3 style="font-size:18px">Symptom Assessment</h3></div>
        <span class="pill pill-slate">structured form</span></div>

      <fieldset class="form-section">
        <legend>1 · Primary symptom</legend>
        <label class="label" for="a-primary">Describe it in your own words</label>
        <input class="input" id="a-primary" name="primary" maxlength="200"
          placeholder="e.g. tiredness and trouble concentrating after lunch" autocomplete="off">
        <p class="form-hint">…or pick one common option (single choice):</p>
        <div class="tile-grid mt8" role="radiogroup" aria-label="Common primary symptoms">
          ${SYMPTOM_TILES.map((t) => `<label class="tile"><input type="radio"
            name="primary-tile" value="${esc(t)}"><span>${esc(t)}</span></label>`).join("")}
        </div>
      </fieldset>

      <fieldset class="form-section">
        <legend>2 · Duration</legend>
        <div class="seg" role="radiogroup" aria-label="How long have you had it?">
          ${[["today", "Today"], ["2-3d", "2-3 days"], ["3-5d", "3-5 days"],
             ["1-2w", "1-2 weeks"], [">2w", "> 2 weeks"]]
            .map(([v, l], i) => `<label class="tile"><input type="radio" class="dur-radio"
              name="duration" value="${v}" ${i === 0 ? "checked" : ""}><span>${l}</span></label>`).join("")}
        </div>
      </fieldset>

      <fieldset class="form-section">
        <legend>3 · Severity right now (pick an exact number)</legend>
        <div class="sev-grid" role="radiogroup" aria-label="Severity, 1 to 10">
          ${[1,2,3,4,5,6,7,8,9,10].map((n) => `<label class="tile sev-tile">
            <input type="radio" class="sev-radio" name="severity" value="${n}"
              ${n === 3 ? "checked" : ""} aria-label="Severity ${n} of 10"><span>${n}</span></label>`).join("")}
        </div>
        <p class="form-hint mt8" id="a-sev-hint">Selected: <b id="a-sev-label">3/10 — Mild</b>
          · bands: 1-3 mild · 4-6 moderate · 7-8 severe · 9-10 emergency-level.
          Exact numbers only — no slider, so the value you pick is the value sent.</p>
      </fieldset>

      <fieldset class="form-section">
        <legend>4 · Associated symptoms & context (optional, multi-select)</legend>
        <div class="choice-grid">
          ${ASSOC_OPTIONS.map((a) => `<label class="choice"><input type="checkbox"
            class="assoc-check" value="${esc(a)}"><span>${esc(a)}</span></label>`).join("")}
        </div>
        <p class="form-hint">These add context only. They never override the warning-sign check below.</p>
      </fieldset>

      <fieldset class="form-section warn-section">
        <legend>5 · Emergency warning signs — tick any that apply RIGHT NOW</legend>
        <p class="form-hint" style="margin:0 0 10px">This check runs independently of everything
        else. Ticking any box always produces urgent guidance, even if the rest of your answers
        look mild — and unticking one removes only that sign.</p>
        <div class="choice-grid">
          ${signs.warning_signs.map((s) => `<label class="choice choice-warn"><input
            type="checkbox" class="ws-check" value="${esc(s.id)}"
            aria-label="${esc(s.label)}"><span>${esc(s.label)}</span></label>`).join("")}
        </div>
      </fieldset>

      <fieldset class="form-section">
        <legend>6 · Anything else? (free text)</legend>
        <label class="label" for="a-notes">Optional details — timing, triggers, what makes it better/worse</label>
        <textarea class="input" id="a-notes" rows="3" maxlength="400"
          placeholder="Emergency wording typed here is also detected by the warning-sign screen."></textarea>
      </fieldset>

      <button type="submit" class="btn btn-deep" style="width:100%;justify-content:center"
        id="a-run">🩺 Analyze Symptoms & Generate Guidance</button>
      <p class="tiny faint mt8" style="text-align:center">Private & local · rule-based engine ·
        zero third-party data sharing</p>
    </form>

    <div>
      <div id="a-result"><div class="card"><div class="card-head"><span class="card-title">Guidance appears here</span></div>
        <p class="small muted">The assistant first screens your warning-sign ticks and free text for
        emergency signs. Then it shows <i>your reported facts</i> separately from
        <i>possible general explanations</i>, followed by self-care information, when-to-seek-care
        criteria and its limitations. It never names a diagnosis or gives odds.</p>
        ${history.history.length ? `<div class="mt16"><span class="label">Recent checks</span>
          ${history.history.slice(0, 5).map((h) => `<div class="row spread small mt8">
            <span>${esc(h.primary).slice(0, 40)}</span>
            <span class="pill ${h.emergency ? "pill-rose" : "pill-slate"}">${h.emergency ? "warning signs flagged" : "logged"}</span></div>`).join("")}</div>` : ""}
      </div></div>
    </div>
  </div>`;

  /* tile ↔ free-text sync (keyboard friendly: tiles are real radios) */
  $$('input[name="primary-tile"]').forEach((r) => r.addEventListener("change", () => {
    if (r.checked) $("#a-primary").value = r.value;
  }));
  $("#a-primary").addEventListener("input", () => {
    $$('input[name="primary-tile"]').forEach((r) => { r.checked = (r.value === $("#a-primary").value); });
  });
  const sevLabel = () => {
    const checked = $$(".sev-radio:checked")[0] || document.querySelector('input[name="severity"]:checked');
    const v = checked ? Number(checked.value) : 3;
    const band = v <= 3 ? "Mild" : v <= 6 ? "Mild to moderate" : v <= 8 ? "Severe" : "Emergency-level";
    $("#a-sev-label").textContent = `${v}/10 — ${band}`;
  };
  $$(".sev-radio").forEach((r) => { r.onchange = sevLabel; r.onclick = sevLabel; });
  sevLabel();

  $("#a-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const primary = $("#a-primary").value.trim();
    if (!primary) { toast("Please describe your primary symptom first (section 1)", true);
      $("#a-primary").focus(); return; }
    const selectedDuration = $$(".dur-radio:checked")[0];
    const payload = {
      primary,
      duration: selectedDuration ? selectedDuration.value : "today",
      severity: Number(($$(".sev-radio:checked")[0]
        || document.querySelector('input[name="severity"]:checked') || { value: 3 }).value),
      associated: $$(".assoc-check:checked").map((c) => c.value),
      warning_signs: $$(".ws-check:checked").map((c) => c.value),
      notes: $("#a-notes").value.trim(),
    };
    $("#a-result").innerHTML = `<div class="card"><p class="muted small">Screening warning signs and analyzing with the local rule-based engine…</p></div>`;
    await withBusy($("#a-run"), async () => {
      try {
        const result = await api("/assistant/assess", { method: "POST", body: payload });
        renderAssessment(result);
      } catch (e) {
        $("#a-result").innerHTML = `<div class="card"><p class="small" style="color:var(--rose)">${esc(e.message)}</p></div>`;
      }
    });
  });
}

function renderAssessment(r) {
  const facts = r.reported_facts || {};
  const factsCard = `
    <div class="card">
      <div class="card-head"><h3 style="font-size:16px">What you reported</h3>
        <span class="pill pill-slate">your facts, verbatim — not interpretations</span></div>
      <div class="grid cols-2" style="gap:8px 18px">
        <div class="small"><span class="tiny muted">PRIMARY SYMPTOM</span><br><b>${esc(facts.primary)}</b></div>
        <div class="small"><span class="tiny muted">DURATION</span><br><b>${esc(facts.duration_label || facts.duration)}</b></div>
        <div class="small"><span class="tiny muted">SEVERITY</span><br><b>${esc(facts.severity)}/10</b></div>
        <div class="small"><span class="tiny muted">ASSOCIATED (selected)</span><br>
          ${(facts.associated || []).length ? esc((facts.associated || []).join(", ")) : "none selected"}</div>
      </div>
      <div class="small mt12"><span class="tiny muted">WARNING SIGNS TICKED</span><br>
        ${(facts.warning_signs_selected || []).length
          ? `<b style="color:var(--rose)">${esc((facts.warning_signs_selected || []).join(" · "))}</b>`
          : "none selected"}</div>
      ${facts.notes ? `<div class="small mt12"><span class="tiny muted">YOUR NOTES</span><br>${esc(facts.notes)}</div>` : ""}
    </div>`;

  const emergencyTop = r.triage === "emergency" ? `
    <div class="emergency-banner mt16">
      <div class="row" style="gap:10px"><span class="icon-pill tint-rose" style="width:38px;height:38px">${ICONS.alert}</span>
        <b style="color:var(--rose-ink);font-size:15px">EMERGENCY WARNING FLAGS — ACT NOW</b></div>
      <ul class="tight mt12" style="color:var(--rose-deep)">${r.red_flags.map((f) =>
        `<li><b>${esc(f.label)}</b>${f.action ? ` — ${esc(f.action)}` : ""}</li>`).join("")}</ul>
      ${r.emergency_actions.map((a) => `<p class="small mt8" style="color:var(--rose-deep)"><b>${esc(a)}</b></p>`).join("")}
      <p class="tiny mt12" style="color:var(--rose-ink)">This screen runs independently of the rest of the
      assessment and is never suppressed by an otherwise low-risk pattern. Do not wait for the
      sections below.</p>
    </div>` : r.triage === "urgent_same_day" ? `
    <div class="emergency-banner mt16" style="border-color:var(--amber-strong-border);border-left-color:var(--amber);background:var(--amber-soft)">
      <b style="color:var(--amber-ink)">High severity reported — seek same-day medical evaluation.</b>
      <p class="small mt8" style="color:var(--amber-ink)">No emergency warning signs were ticked or detected,
      but severity ≥ 8/10 deserves an in-person check today (campus health centre or a clinician).</p>
    </div>` : `
    <div class="poss-card mt16" style="border-left:5px solid var(--emerald-bright)">
      <div class="row spread"><b class="small" style="color:var(--success)">Warning-sign check completed — none triggered</b>
      <span class="pill pill-mint">Non-emergency pattern</span></div>
      <p class="tiny muted mt8">Independent screen result: ${r.red_flags.length} warning sign(s)
      ticked or detected in text. This does not mean "nothing is wrong" — it means no automatic
      emergency flag applied to what you entered. If a warning sign appears later, re-run the check.</p>
    </div>`;

  $("#a-result").innerHTML = `
    ${factsCard}
    ${emergencyTop}
    <div class="card mt16">
      <div class="card-head"><h3 style="font-size:16px">Possible explanations — general education, not a diagnosis</h3>
        <span class="tiny muted">keyword-selected entries</span></div>
      ${(r.caution_notes || []).length ? `<div class="selfcare-card" style="background:var(--amber-soft);border-color:var(--amber-border)">
        <b class="tiny" style="color:var(--amber-ink)">READ FIRST — HOW TO INTERPRET THIS SECTION</b>
        <ul class="tight small mt8" style="color:var(--amber-ink)">${r.caution_notes.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></div>` : ""}
      <div class="grid mt12" style="gap:10px">
        ${r.possibilities.map((p, i) => `<div class="poss-card">
          <div class="row spread"><b class="small">${i + 1}. ${esc(p.title)}</b>
          <span class="pill pill-slate">${esc(p.tag)}</span></div>
          <p class="small muted mt8">${esc(p.detail)}</p></div>`).join("")}
      </div>
      ${r.context_notes.length ? `<div class="selfcare-card mt12">
        <b class="tiny" style="color:var(--primary-deep)">FROM YOUR PROFILE (your own reported context)</b>
        <ul class="tight small muted">${r.context_notes.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></div>` : ""}
    </div>
    <div class="card mt16">
      <div class="card-head"><h3 style="font-size:16px">General self-care information</h3>
        <span class="pill pill-teal">not treatment advice</span></div>
      <div class="grid cols-2" style="gap:10px">
        ${r.self_care.map((s) => `<div class="selfcare-card"><b class="small">${esc(s.title)}</b>
          <p class="tiny muted mt8">${esc(s.detail)}</p></div>`).join("")}
      </div>
    </div>
    <div class="card mt16">
      <div class="card-head"><h3 style="font-size:16px">When to seek professional medical care</h3>
        <span class="icon-pill tint-rose">🚩</span></div>
      <ul class="tight small muted">${r.seek_care.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>
    </div>
    <div class="card mt16">
      <div class="card-head"><h3 style="font-size:16px">Limitations of this feature</h3></div>
      <ul class="tight small muted">${r.limitations.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>
      <div class="mt12"><span class="label">General references</span>
        <ul class="tight tiny muted">${r.references.map((ref) =>
          `<li>${esc(ref.name)} — <a href="${esc(ref.url)}" target="_blank" rel="noopener">${esc(ref.url)}</a></li>`).join("")}</ul></div>
      <p class="tiny mt12" style="color:var(--amber);background:var(--amber-soft);padding:8px 10px;border-radius:8px">${esc(r.disclaimer)}</p>
    </div>`;
}
