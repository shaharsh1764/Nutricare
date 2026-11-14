/* Reports + Settings views. */
"use strict";

async function renderReports() {
  const days = S.reportDays || 7;
  const r = await api(`/report?days=${days}`);
  const t = r.targets;
  const avg = r.averages;
  const macroKcal = { protein: avg.protein_g * 4, carbs: avg.carbs_g * 4, fat: avg.fat_g * 4 };
  const macroSum = macroKcal.protein + macroKcal.carbs + macroKcal.fat || 1;
  const rangeHead = `<div class="page-head">
    <div><h2>Nutrition & Health Reports</h2>
      <p class="sub">Daily and weekly summaries compiled from your continuous logs. Charts are
      interactive summaries of your own data — exportable for the selected period as PDF, CSV, or JSON.</p></div>
    <div class="row">
      ${[7, 30, 90].map((d) => `<button class="btn btn-sm ${d === days ? "btn-deep" : "btn-ghost"}" data-days="${d}">${d} Days</button>`).join("")}
      <a class="btn btn-ghost btn-sm" href="/api/report.pdf?days=${days}" download title="Download a ${days}-day nutrition summary as a PDF">${ICONS.download} ${days}-day PDF</a>
      <a class="btn btn-ghost btn-sm" href="/api/report.csv?days=${days}" download>${ICONS.download} ${days}-day CSV</a>
      <a class="btn btn-primary btn-sm" href="/api/export.json" download>${ICONS.download} Full JSON</a>
    </div>
  </div>`;
  if (!r.logged_days) {
    $("#view").innerHTML = rangeHead + `
      <div class="empty-state" style="padding:48px 26px"><span class="audit-empty-icon" aria-hidden="true">${ICONS.reports}</span>
        <b style="font-size:16px">No logged days in this window yet.</b>
        <p class="small muted mt8" style="max-width:460px">Reports stay empty until real data exists —
        showing averages of nothing would be misleading, and an empty log is never treated as
        "zero calories eaten". Log meals or water and come back.</p>
        <div class="row mt16" style="justify-content:center">
          <button class="btn btn-deep" id="rep-log">Log your first meal</button>
          <a class="btn btn-ghost" href="#/tracker">Open tracker</a></div></div>`;
    $$("[data-days]").forEach((b) => b.onclick = () => { S.reportDays = Number(b.dataset.days); renderReports(); });
    $("#rep-log").onclick = () => location.hash = "#/tracker";
    return;
  }
  const adherence = t ? Math.round(100 * Math.min(avg.protein_g / t.protein_g, 1) * 0.34
    + 100 * Math.min(avg.carbs_g / t.carbs_g, 1) * 0.33
    + 100 * Math.min(avg.fat_g / t.fat_g, 1) * 0.33) : null;

  const microRows = t ? [
    ["Fiber", r.micro_avg.fiber_g, t.micro.fiber_g, "g"],
    ["Potassium", r.micro_avg.potassium_mg, t.micro.potassium_mg, "mg"],
    ["Calcium", r.micro_avg.calcium_mg, t.micro.calcium_mg, "mg"],
    ["Iron", r.micro_avg.iron_mg, t.micro.iron_mg, "mg"],
    ["Sodium (upper limit)", r.micro_avg.sodium_mg, t.micro.sodium_mg, "mg", true],
  ].map(([label, val, max, unit, upper]) => {
    const pct = Math.round(100 * val / max);
    const ok = upper ? val <= max : pct >= 80;
    return `<div class="mt12"><div class="row spread small"><b>${label}</b>
      <span class="pill ${ok ? "pill-mint" : "pill-amber"}">${pct}%${upper ? " of limit" : ""}</span></div>
      <div class="bar mt8"><i style="width:${Math.min(100, pct)}%;background:${ok ? "var(--success)" : "var(--amber)"}"></i></div>
      <div class="tiny muted mt8">avg ${fmt(val, 1)}${unit} / day vs ${fmt(max)}${unit}</div></div>`;
  }).join("") : `<p class="small muted">Complete your profile to compare against reference intakes.</p>`;

  $("#view").innerHTML = rangeHead + `

  <div class="grid cols-4">
    <div class="card"><div class="card-head"><span class="card-title">Avg daily intake</span><span class="icon-pill tint-teal">${ICONS.dashboard}</span></div>
      <div class="stat">${fmt(avg.kcal)}<small> kcal/day</small></div>
      <p class="tiny muted mt8">${t ? `${Math.round(100 * avg.kcal / t.kcal)}% of ${fmt(t.kcal)} kcal target` : "no target set"}</p>
      <div class="bar mt8"><i style="width:${t ? Math.min(100, 100 * avg.kcal / t.kcal) : 0}%;background:var(--primary-deep)"></i></div></div>
    <div class="card"><div class="card-head"><span class="card-title">Macro compliance</span><span class="icon-pill tint-mint" style="background:var(--success-soft);color:var(--success)">${ICONS.shield}</span></div>
      <div class="stat">${adherence ?? "—"}<small> /100</small></div>
      <p class="tiny muted mt8">Weighted attainment of protein / carb / fat gram targets</p></div>
    <div class="card"><div class="card-head"><span class="card-title">Average hydration</span><span class="icon-pill tint-sky">${ICONS.drop}</span></div>
      <div class="stat">${fmt(avg.water_ml)}<small> ml/day</small></div>
      <p class="tiny muted mt8">${Math.round(100 * avg.water_ml / (S.boot.settings.water_goal_ml || 2800))}% of fluid goal</p></div>
    <div class="card"><div class="card-head"><span class="card-title">Meal consistency</span><span class="icon-pill tint-amber">${ICONS.meal}</span></div>
      <div class="stat">${r.meal_consistency_pct}%<small> of days</small></div>
      <p class="tiny muted mt8">Days with ≥ 3 distinct meal categories logged</p></div>
  </div>

  <div class="grid cols-21 mt16">
    <div class="card">
      <div class="card-head"><div><h3 style="font-size:16px">Calorie intake vs personalised target</h3>
        <p class="tiny muted mt8">Daily energy variance against your metabolic maintenance target.</p></div></div>
      ${barsChart(r.per_day, t ? t.kcal : null)}
      <p class="tiny muted mt8">*Days with no logs count as 0 — log meals to make trends meaningful.</p>
    </div>
    <div class="card">
      <div class="card-head"><span class="card-title">Macronutrients</span><span class="pill pill-slate">avg share</span></div>
      <div style="display:flex;justify-content:center">${donutChart([
        { value: macroKcal.protein, color: COLORS.protein },
        { value: macroKcal.carbs, color: COLORS.carbs },
        { value: macroKcal.fat, color: COLORS.fat }],
        `${Math.round(100 * macroKcal.protein / macroSum)}%`, "protein share")}</div>
      <div class="legend mt12" style="justify-content:center">
        <span><span class="dot" style="background:${COLORS.protein}"></span>P ${fmt(avg.protein_g, 1)}g</span>
        <span><span class="dot" style="background:${COLORS.carbs}"></span>C ${fmt(avg.carbs_g, 1)}g</span>
        <span><span class="dot" style="background:${COLORS.fat}"></span>F ${fmt(avg.fat_g, 1)}g</span></div>
      <div class="mt16"><span class="label">Top nutrient-dense foods (${days}d)</span>
        ${r.top_foods.length ? r.top_foods.map((f) => `<div class="row spread small mt8">
          <span>${esc(f.name)}</span><span class="pill pill-slate">${f.times}×</span></div>`).join("")
          : `<p class="tiny muted">No logged foods in this window.</p>`}</div>
    </div>
  </div>

  <div class="grid cols-2 mt16">
    <div class="card"><div class="card-head"><span class="card-title">Micronutrient adequacy (daily avg)</span>
      <span class="tiny muted">tracked subset</span></div>${microRows}</div>
    <div class="card"><div class="card-head"><span class="card-title">Daily log table (last ${days} days)</span></div>
      <div style="max-height:340px;overflow:auto">
      <table class="table"><thead><tr><th>Date</th><th>kcal</th><th>P</th><th>C</th><th>F</th><th>Water</th></tr></thead>
      <tbody>${r.per_day.slice().reverse().map((d) => `<tr><td>${prettyDate(d.date)}</td>
        <td><b>${fmt(d.kcal)}</b></td><td>${fmt(d.protein_g, 1)}</td><td>${fmt(d.carbs_g, 1)}</td>
        <td>${fmt(d.fat_g, 1)}</td><td>${fmt(d.water_ml)}</td></tr>`).join("")}</tbody></table></div></div>
  </div>`;

  $$("[data-days]").forEach((b) => b.onclick = () => { S.reportDays = Number(b.dataset.days); renderReports(); });
}

/* ============================================================ SETTINGS */
async function renderSettings() {
  const p = S.boot.profile;
  const set = S.boot.settings;
  const theme = currentTheme();
  $("#view").innerHTML = `
  <div class="page-head"><div><h2>Account & Application Settings</h2>
    <p class="sub">Appearance, units, calculation model, hydration goal, privacy switches and data controls.
    Secrets (if any) live in environment variables, never in the UI.</p></div></div>

  <div class="grid cols-2" style="align-items:start">
    <div class="grid" style="gap:16px">
      <div class="card">
        <div class="card-head"><span class="card-title">Appearance</span><span class="icon-pill tint-teal">${ICONS.sun}</span></div>
        <p class="small muted">Choose the display that feels most comfortable. This preference is remembered in this browser and stays the same when switching local profiles.</p>
        <div class="theme-options mt12" role="group" aria-label="Colour theme">
          <button class="theme-choice ${theme === "light" ? "active" : ""}" id="s-theme-light" type="button" aria-pressed="${theme === "light"}">
            <span class="theme-icon">${ICONS.sun}</span><span><b>Light mode</b><small>Bright, clean workspace</small></span></button>
          <button class="theme-choice ${theme === "dark" ? "active" : ""}" id="s-theme-dark" type="button" aria-pressed="${theme === "dark"}">
            <span class="theme-icon">${ICONS.moon}</span><span><b>Dark mode</b><small>Comfortable in low light</small></span></button>
        </div>
        <p class="tiny faint mt12">If you have not chosen a mode, NutriCare follows your operating system preference.</p>
      </div>
      <div class="card">
        <div class="card-head"><span class="card-title">Units & measurement</span><span class="icon-pill tint-teal">${ICONS.settings}</span></div>
        <div class="grid cols-2">
          <div class="field"><span class="label">Unit system</span>
            <select class="select" id="s-units">
              <option value="metric" ${p.units === "metric" ? "selected" : ""}>Metric (kg, cm, ml)</option>
              <option value="imperial" ${p.units === "imperial" ? "selected" : ""}>Imperial (lb, ft, oz)</option>
            </select></div>
          <div class="field"><span class="label">Daily water goal (ml)</span>
            <input class="input" id="s-water" type="number" min="500" max="6000" step="100" value="${set.water_goal_ml}"></div>
        </div>
        <button class="btn btn-primary btn-sm" id="s-save-units">Save preferences</button>
      </div>
      <div class="card">
        <div class="card-head"><span class="card-title">Privacy & data governance</span><span class="icon-pill tint-sky">${ICONS.shield}</span></div>
        ${[["privacy_sync", "Local device sync of logs", "Keep meals/water synced in the local SQLite database (required for tracking)."],
           ["privacy_ai", "On-device assistant analysis", "Symptom assessments are processed locally by the rule-based engine; nothing leaves your machine."],
           ["privacy_research", "Contribute anonymised statistics (off by default)", "Placeholder for a future opt-in research mode. Currently stored only, never transmitted."]]
          .map(([key, title, sub]) => `<div class="row spread mt12">
            <div style="flex:1"><b class="small">${title}</b><p class="tiny muted">${sub}</p></div>
            <label class="switch"><input type="checkbox" data-privacy="${key}" ${set[key] ? "checked" : ""} ${key === "privacy_sync" ? "disabled" : ""}><span class="track"></span></label>
          </div>`).join("")}
        <p class="tiny faint mt12">This build has no third-party analytics, no ads and no external API calls from the assistant.</p>
      </div>
      <div class="card">
        <div class="card-head"><span class="card-title">Health Assistant engine</span></div>
        <div class="selfcare-card"><b class="small">${esc(S.boot.assistant.label)}</b>
          <p class="tiny muted mt8">Engine: <code>${esc(S.boot.assistant.engine)}</code> ·
          online AI configured: ${S.boot.assistant.online_ai_configured ? "yes (unused in v1)" : "no"} ·
          online AI used: <b>no</b>. The app never pretends an AI is answering.</p></div>
      </div>
    </div>

    <div class="grid" style="gap:16px">
      <div class="card">
        <div class="card-head"><span class="card-title">Data portability</span><span class="icon-pill tint-teal">${ICONS.download}</span></div>
        <p class="small muted">Download everything the app stores about you in human-readable JSON,
        or your meal log as CSV from Reports.</p>
        <div class="row mt12"><a class="btn btn-ghost btn-sm" href="/api/export.json" download>Export archive (.json)</a>
        <a class="btn btn-ghost btn-sm" href="/api/report.csv?days=90" download>Export 90-day CSV</a></div>
      </div>
      <div class="card">
        <div class="card-head"><span class="card-title">Demo mode (labelled fictional data)</span>
          <span class="pill ${S.boot.demo_mode ? "pill-amber" : "pill-slate"}">${S.boot.demo_mode ? "ON" : "off"}</span></div>
        <p class="small muted">Loads an invented sample day for demos. It is refused if this profile
        already has real logs (fictional and real data never mix), and a persistent banner labels the
        whole app while it is on.</p>
        ${S.boot.demo_mode
          ? `<button class="btn btn-danger-soft btn-sm mt12" id="s-demo-clear">Clear demo data</button>`
          : `<button class="btn btn-soft btn-sm mt12" id="s-demo-load">Load labelled demo day</button>`}
      </div>
      <div class="card">
        <div class="card-head"><span class="card-title">Local profiles & identity limits</span>
          <span class="icon-pill tint-sky">${ICONS.user}</span></div>
        <p class="small muted">NutriCare has <b>no passwords and no encryption</b>. Profiles keep
        records separate on this device and let household members share one install, but anyone with
        access to this browser can switch profiles. That is organisation, not security — real
        multi-user protection would require authentication this project deliberately does not claim.</p>
        <button class="btn btn-ghost btn-sm mt12" id="s-users">Manage local profiles</button>
      </div>
      <div class="card" style="border-color:var(--rose-border);background:var(--warning-bg)">
        <div class="card-head"><span class="card-title" style="color:var(--rose)">Danger zone: deletion & purge</span>
          <span class="icon-pill tint-rose">${ICONS.alert}</span></div>
        <p class="small muted">Permanently delete all personal entries: biometric records, symptom
        assessments, meal and hydration logs. The action cannot be reversed.</p>
        <button class="btn btn-danger mt12" id="s-purge">Permanently delete my data</button>
      </div>
      <div class="card">
        <div class="card-head"><span class="card-title">About the dataset</span></div>
        <p class="small muted">Food values: USDA FoodData Central & Indian Food Composition Tables 2017
        (approximations, per 100 g). Formulas: Mifflin-St Jeor BMR × PAL activity factors;
        4/4/9 kcal macro factors. See <code>data/SOURCES.md</code> in the project folder.</p>
      </div>
    </div>
  </div>`;

  ["light", "dark"].forEach((choice) => {
    const button = $(`#s-theme-${choice}`);
    if (button) button.onclick = () => {
      setTheme(choice);
      toast(`${choice === "dark" ? "Dark" : "Light"} mode enabled`);
    };
  });

  $("#s-save-units").onclick = async () => {
    try {
      const prof = await api("/profile", { method: "PUT", body: { units: $("#s-units").value } });
      const settings = await api("/settings", { method: "PUT", body: { water_goal_ml: Number($("#s-water").value) } });
      S.boot.profile = prof.profile; S.boot.settings = settings;
      toast("Preferences saved"); refreshView();
    } catch (e) { toast(e.message, true); }
  };
  $$("[data-privacy]").forEach((t) => t.onchange = async () => {
    try {
      S.boot.settings = await api("/settings", { method: "PUT", body: { [t.dataset.privacy]: t.checked } });
      toast("Privacy preference saved");
    } catch (e) { toast(e.message, true); t.checked = !t.checked; }
  });
  const demoLoad = $("#s-demo-load");
  if (demoLoad) demoLoad.onclick = async () => {
    try {
      S.boot = await api("/demo/load", { method: "POST" });
      toast("Labelled demo day loaded"); refreshBanners(); refreshView(); refreshSideGoal();
    } catch (e) { toast(e.message, true); }
  };
  const demoClear = $("#s-demo-clear");
  if (demoClear) demoClear.onclick = async () => {
    const ok = await confirmModal("Clear demo data?",
      "Removes the fictional sample day from this profile and turns demo mode off.", "Clear demo data");
    if (!ok) return;
    S.boot = await api("/demo/clear", { method: "POST" });
    toast("Demo data cleared"); refreshBanners(); refreshView(); refreshSideGoal();
  };
  $("#s-users").onclick = openUserModal;
  $("#s-purge").onclick = async () => {
    const ok = await confirmModal("Permanently delete all data?",
      "Profile details, meals, water logs and symptom assessments will be erased from the database.",
      "Delete everything");
    if (!ok) return;
    await api("/profile/purge", { method: "POST" });
    S.boot = await api("/bootstrap");
    toast("All personal data deleted"); refreshView(); refreshSideGoal();
  };
}
