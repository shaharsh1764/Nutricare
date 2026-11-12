/* Dashboard + Nutrition Tracker views. */
"use strict";

const MEAL_META = {
  breakfast: { label: "Breakfast", icon: "🌅", tint: "tint-amber" },
  lunch: { label: "Lunch", icon: "☀️", tint: "tint-teal" },
  dinner: { label: "Dinner", icon: "🌙", tint: "tint-sky" },
  snacks: { label: "Snacks & Beverages", icon: "🍎", tint: "tint-rose" },
};

/* ============================================================ DASHBOARD */
async function renderDashboard() {
  const today = S.boot.today;
  const [summary, report] = await Promise.all([
    api(`/summary?date=${today}`), api("/report?days=7")]);
  const t = summary.targets;
  const consumed = summary.totals.kcal;
  const remaining = t ? Math.max(0, t.kcal - consumed) : null;
  const hour = new Date().getHours();
  const greet = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const name = (S.boot.user && S.boot.user.name) || "there";
  const units = summary.profile.units || "metric";
  const cups = Math.floor(summary.water_ml / 250);
  const goalCups = Math.ceil(summary.water_goal_ml / 250);
  const hasLogs = summary.logged_count > 0 || summary.water_ml > 0;
  const weekEmpty = report.per_day.every((d) => (d.logged_count || 0) === 0 && !d.water_ml);

  const macroCard = t ? `
    <div class="card audit-stat">
      <div class="card-head"><span class="card-title">Macro distribution</span>
        <span class="icon-pill tint-teal">${ICONS.tracker}</span></div>
    ${hBar("Protein", summary.totals.protein_g, t.protein_g, COLORS.protein,
      `${fmt(summary.totals.protein_g)}g / ${fmt(t.protein_g)}g`)}
    ${hBar("Carbs", summary.totals.carbs_g, t.carbs_g, COLORS.carbs,
      `${fmt(summary.totals.carbs_g)}g / ${fmt(t.carbs_g)}g`)}
    ${hBar("Fat", summary.totals.fat_g, t.fat_g, COLORS.fat,
      `${fmt(summary.totals.fat_g)}g / ${fmt(t.fat_g)}g`)}
    </div>` : `<div class="card audit-stat"><div class="card-head"><span class="card-title">Macro distribution</span></div>
      <p class="muted small">Complete your <a href="#/profile">health profile</a> to unlock personalised macro targets.</p></div>`;

  let cupsHtml = "";
  for (let i = 0; i < goalCups; i++) {
    cupsHtml += `<span class="icon-pill ${i < cups ? "tint-sky" : ""}"
      style="${i < cups ? "" : "background:var(--surface-subtle);color:var(--faint)"}">${ICONS.cup}</span>`;
  }

  const insights = dashboardInsights(summary, t);

  $("#view").innerHTML = `
  <div class="card dashboard-hero" style="background:var(--dashboard-gradient);border-color:var(--primary-border)">
    <div class="row spread wrap">
      <div>
        <div class="row" style="gap:8px"><span class="pill ${hasLogs ? "pill-mint" : "pill-slate"}">${hasLogs ? "DAILY NUTRITION SUMMARY" : "FRESH START"}</span>
          <span class="tiny muted">${hasLogs ? "Updated just now" : "your account is empty — exactly as it should be"}</span></div>
        <h2 class="dashboard-title">${hasLogs ? esc(greet) + ", " : "Welcome to NutriCare, "}${esc(name)} 👋</h2>
        <p class="muted mt8 dashboard-summary">
          ${hasLogs
            ? (t ? `You are <b style="color:var(--primary-deep)">${fmt(remaining)} kcal</b> away from your daily target.
               Hydration is at <b style="color:var(--sky)">${fmt(100 * summary.water_ml / summary.water_goal_ml)}%</b> of goal.`
                 : "Log meals to build your record — then complete your profile for personalised targets.")
            : `Nothing is recorded yet — and <b>an empty log never means zero intake</b>, it simply means
               you haven't logged anything. Start with your first meal, or finish your profile first.`}</p>
      </div>
      <div class="row wrap dashboard-actions">
        <button class="btn btn-ghost" id="quick-water">${ICONS.drop} Quick Water (+250ml)</button>
        <button class="btn btn-ghost" id="quick-symptoms">🩺 Check Symptoms</button>
        <button class="btn btn-ghost" id="quick-scan">${ICONS.scanner} Scan a meal</button>
        <button class="btn btn-deep" id="quick-log">${ICONS.plus} ${hasLogs ? "Log Food" : "Log your first meal"}</button>
      </div>
    </div>
  </div>

  <div class="grid cols-4 mt16 dashboard-metrics">
    <div class="card audit-stat">
      <div class="card-head"><span class="card-title">Energy budget</span>
        <span class="icon-pill tint-teal">⚡</span></div>
      <div class="row spread">
        <div><div class="stat">${fmt(consumed)}<small> / ${t ? fmt(t.kcal) : "—"} kcal</small></div>
          <p class="tiny mt8" style="color:${t ? "var(--success)" : "var(--amber)"};font-weight:700">${
            t ? fmt(remaining) + " kcal remaining today (estimate-based target)"
              : "target not configured yet"}</p>
          ${summary.logged_count === 0 ? `<p class="tiny faint mt8">0 kcal <b>recorded</b> — nothing logged yet.
            This is not an estimate of what you actually ate.</p>` : ""}</div>
        ${t ? ringChart(consumed / t.kcal, { label: `${Math.round(100 * consumed / t.kcal)}%`, sub: "of goal" })
            : `<span class="pill pill-amber">Set profile<br>for target</span>`}
      </div>
      <div class="bar mt12"><i style="width:${t ? Math.min(100, 100 * consumed / t.kcal) : 0}%;background:var(--primary-deep)"></i></div>
    </div>
    ${macroCard}
    <div class="card audit-stat">
      <div class="card-head"><span class="card-title">Hydration index</span>
        <span class="pill pill-amber">${cups}/${goalCups} cups</span></div>
      <div class="stat">${units === "imperial" ? fmt(summary.water_ml / 29.5735, 0) + "<small> oz</small>" : (summary.water_ml / 1000).toFixed(1) + "<small> L</small>"}<small> / ${units === "imperial" ? fmt(summary.water_goal_ml / 29.5735, 0) + " oz" : (summary.water_goal_ml / 1000).toFixed(1) + " L"}</small></div>
      <p class="tiny muted mt8">${summary.water_ml === 0 ? "No water logged yet — start with one cup."
            : summary.water_goal_ml - summary.water_ml > 0 ? UNITS.water(Math.max(0, summary.water_goal_ml - summary.water_ml), units) + " left to reach goal" : "Goal reached 🎉"}</p>
      <div class="row wrap mt12">${cupsHtml}</div>
    </div>
    <div class="card audit-stat">
      <div class="card-head"><span class="card-title">Biometrics & vitals</span>
        <span class="icon-pill tint-rose">♥</span></div>
      ${t ? `<div class="row spread small mt8"><span class="muted">BMR (Mifflin-St Jeor)</span><b>${fmt(t.bmr)} kcal</b></div>
      <div class="row spread small mt8"><span class="muted">Activity level</span><b>${esc(summary.profile.activity)}</b></div>
      <div class="row spread small mt8"><span class="muted">Weight</span><b>${UNITS.weight(summary.profile.weight_kg, units)}</b></div>
      <div class="row spread small mt8"><span class="muted">Meal consistency (7d)</span><b>${report.meal_consistency_pct}%</b></div>
      <p class="tiny faint mt12">Targets computed from your profile — editable in Settings.</p>`
      : `<p class="muted small">No profile yet. <a href="#/profile">Add your details</a> (age, height, weight, activity) to personalise everything.</p>`}
    </div>
  </div>

  <div class="grid cols-21 mt16 dashboard-journal">
    <div class="card diary-card">
      <div class="card-head"><div><h3 class="journal-heading">Today's Meals & Nutrition Log</h3>
        <p class="tiny muted mt8">Logged items are summed from the documented food dataset.</p></div>
        <button class="btn btn-soft btn-sm" id="goto-tracker">Open Tracker</button></div>
      ${dashboardMealList(summary)}
    </div>
    <div class="grid" style="gap:16px;align-content:start">
      <div class="card">
        <div class="card-head"><span class="card-title">Smart insights</span>
          <span class="pill pill-slate">General tips</span></div>
        <div class="grid" style="gap:10px">${insights}</div>
      </div>
      <div class="card" style="background:var(--assistant-gradient)">
        <div class="row" style="gap:8px;color:var(--primary-deep);font-weight:800;font-size:12px">${ICONS.shield} HEALTH ASSISTANT</div>
        <h3 style="font-size:18px;margin-top:8px">Feeling off today?</h3>
        <p class="muted small mt8">Answer a short structured questionnaire. The assistant explains
          <i>possible</i> everyday causes, general self-care, and emergency warning signs — it never diagnoses.</p>
        <button class="btn btn-ghost mt12" style="width:100%;justify-content:center" id="goto-assistant">Start Check →</button>
      </div>
    </div>
  </div>

  <div class="card mt16 audit-chart">
    <div class="card-head spread"><div><span class="tiny muted" style="font-weight:700;letter-spacing:.08em">7-DAY TRAJECTORY</span>
      <h3 class="journal-heading">Weekly Caloric & Macro Balance</h3></div>
      <div class="legend"><span><span class="dot" style="background:${COLORS.protein}"></span>Protein</span>
      <span><span class="dot" style="background:${COLORS.carbs}"></span>Carbs</span>
      <span><span class="dot" style="background:${COLORS.fat}"></span>Fat</span></div></div>
    ${weekEmpty ? `<div class="empty-state"><span style="font-size:30px">📊</span>
        <b>Charts stay empty until your first logged day.</b>
        <p class="tiny muted mt8">NutriCare will not draw trends from zero data — log a meal and this
        chart fills with your real numbers only.</p>
        <button class="btn btn-soft btn-sm mt12" id="empty-log-cta">${ICONS.plus} Log your first meal</button></div>`
      : stackedWeekChart(report.per_day, t ? t.kcal : null)}
    <div class="row spread mt8"><span class="small muted">Weekly target adherence:
      <b>${weekEmpty ? "no logged days yet" : adherencePct(report, t)}</b></span>
      <a class="small" style="color:var(--primary-deep);font-weight:700" href="#/reports">Full Analytics Report →</a></div>
  </div>

  <div id="insights-root" class="mt16"></div>`;

  $("#quick-water").onclick = async () => {
    await api("/water", { method: "POST", body: { amount_ml: 250 } });
    toast("+250 ml water logged"); renderDashboard();
  };
  $("#quick-symptoms").onclick = () => location.hash = "#/assistant";
  $("#quick-log").onclick = () => location.hash = "#/tracker";
  const quickScan = $("#quick-scan");
  if (quickScan) quickScan.onclick = () => location.hash = "#/scanner";
  $("#goto-tracker").onclick = () => location.hash = "#/tracker";
  const emptyCta = $("#empty-log-cta");
  if (emptyCta) emptyCta.onclick = () => location.hash = "#/tracker";
  $("#goto-assistant").onclick = () => location.hash = "#/assistant";
  bindMealRowButtons();
  /* Smart Nutrition Insights (isolated module; renders into #insights-root
     with its own loading/empty/error states; failures never affect the rest
     of the dashboard). */
  if (typeof renderSmartInsights === "function") renderSmartInsights();
}

function adherencePct(report, targets) {
  if (!targets) return "—";
  const days = report.per_day.filter((d) => d.kcal > 0);
  if (!days.length) return "no logged days yet";
  const within = days.filter((d) => Math.abs(d.kcal - targets.kcal) / targets.kcal <= 0.15).length;
  return `${Math.round(100 * within / days.length)}% of logged days within ±15%`;
}

function dashboardInsights(summary, t) {
  if (summary.logged_count === 0 && summary.water_ml === 0) {
    return [`<div class="selfcare-card"><div class="row" style="gap:8px"><span>🌱</span>
      <b class="small">Start here</b></div>
      <p class="tiny muted mt8">Your account is genuinely empty. Log your first meal in the tracker,
      add water as you drink it, and this panel will switch to observations based only on your own data.</p></div>`];
  }
  const tips = [];
  if (summary.water_ml < summary.water_goal_ml * 0.6) {
    tips.push(["💧", "Hydration pace", `You're at ${fmt(100 * summary.water_ml / summary.water_goal_ml)}% of your fluid goal. Spreading sips across the afternoon is a common general strategy.`]);
  } else {
    tips.push(["💧", "Hydration on track", "Nice — your logged intake is above 60% of goal with the day still running."]);
  }
  if (t && summary.totals.protein_g < t.protein_g * 0.6) {
    tips.push(["🥚", "Protein pacing", "Protein is behind target. Curd, dal, eggs, paneer or grilled chicken at the next meal are common whole-food options."]);
  }
  if (t && summary.totals.fat_g > t.fat_g) {
    tips.push(["🥑", "Fat over goal", "Today's fat is above target — mostly a heads-up for meal planning, not a problem in itself."]);
  }
  tips.push(["🥦", "Fiber check", "Reports tracks your daily fiber against a 28 g reference. Whole grains, dal and vegetables are the usual contributors."]);
  return tips.map(([icon, title, body]) => `
    <div class="selfcare-card"><div class="row" style="gap:8px"><span>${icon}</span>
    <b class="small">${esc(title)}</b></div><p class="tiny muted mt8">${esc(body)}</p></div>`).join("");
}

function dashboardMealList(summary) {
  const blocks = Object.entries(summary.meals).map(([meal, entries]) => {
    const meta = MEAL_META[meal];
    const kcal = entries.reduce((s, e) => s + e.nutrients.kcal, 0);
    if (!entries.length) {
      return `<div class="meal-row"><span class="icon-pill ${meta.tint}">${meta.icon}</span>
        <div style="flex:1"><div class="nm">${meta.label}</div>
        <div class="meta">Nothing logged yet</div></div>
        <button class="btn btn-soft btn-sm" data-add-meal="${meal}">${ICONS.plus} Add</button></div>`;
    }
    return entries.map((e) => `
      <div class="meal-row">
        <span class="icon-pill ${meta.tint}">${meta.icon}</span>
        <div style="flex:1"><div class="nm">${esc(e.display_name)}
          <span class="pill pill-slate" style="margin-left:6px">${meta.label}</span></div>
          <div class="meta">P: ${fmt(e.nutrients.protein_g, 1)}g · C: ${fmt(e.nutrients.carbs_g, 1)}g · F: ${fmt(e.nutrients.fat_g, 1)}g · ${fmt(e.nutrients.grams)}g</div></div>
        <div class="kcal">${fmt(e.nutrients.kcal)} <small>kcal</small></div>
        <button class="icon-btn" data-edit-entry="${e.id}" title="Edit">${ICONS.edit}</button>
        <button class="icon-btn" data-del-entry="${e.id}" title="Delete">${ICONS.trash}</button>
      </div>`).join("") +
      `<div class="meal-row" style="border-top:1px dashed var(--line)"><span></span>
        <div style="flex:1" class="tiny muted">${meta.label} subtotal</div>
        <div class="kcal">${fmt(kcal)} <small>kcal</small></div>
        <button class="btn btn-soft btn-sm" data-add-meal="${meal}">${ICONS.plus} Add</button></div>`;
  }).join("");
  return `<div>${blocks}</div>`;
}

function bindMealRowButtons() {
  $$("[data-del-entry]").forEach((b) => b.onclick = async () => {
    if (await confirmModal("Delete meal entry?", "This removes the entry from your log permanently.")) {
      await api(`/meals/${b.dataset.delEntry}`, { method: "DELETE" });
      toast("Entry deleted"); refreshView();
    }
  });
  $$("[data-edit-entry]").forEach((b) => b.onclick = () => openEntryModal(null, Number(b.dataset.editEntry)));
  $$("[data-add-meal]").forEach((b) => b.onclick = () => openFoodSearchModal(b.dataset.addMeal));
}

/* ============================================================ TRACKER */
async function renderTracker() {
  const date = S.trackerDate || S.boot.today;
  const [meals, summary] = await Promise.all([
    api(`/meals?date=${date}`), api(`/summary?date=${date}`)]);
  const t = summary.targets;
  const units = summary.profile.units || "metric";

  $("#view").innerHTML = `
  <div class="page-head">
    <div><h2>Nutrition Tracker</h2>
      <p class="sub">Search the documented food database (incl. common Indian foods), choose portions,
      and manage meals by category. Values come from <code>data/foods.json</code> (USDA FDC / IFCT 2017).</p></div>
    <div class="row">
      <button class="btn btn-ghost btn-sm" id="day-prev">‹</button>
      <span class="date-chip">${date === S.boot.today ? "Today, " : ""}${prettyDate(date)}</span>
      <button class="btn btn-ghost btn-sm" id="day-next">›</button>
      <a class="btn btn-ghost btn-sm" href="/api/report.csv?days=7" download>${ICONS.download} CSV</a>
    </div>
  </div>

  <div class="grid cols-21" style="align-items:start">
    <div>
      <div class="card">
        <div class="searchbox" style="max-width:none;border-radius:12px">
          ${ICONS.search}<input id="food-search" placeholder="Search 40+ foods: roti, dal, paneer, rice, oats, banana…" autocomplete="off">
        </div>
        <div id="search-results"></div>
        <button class="btn btn-soft btn-sm mt12" id="add-custom">${ICONS.plus} Add custom / manual item</button>
      </div>
      ${meals.logged_count === 0 ? `<div class="empty-state mt16">
        <span style="font-size:30px">🍽</span><b>Your food log for ${prettyDate(date)} is empty.</b>
        <p class="tiny muted mt8">Empty means "nothing recorded", not "nothing eaten". Search the food
        database or add a custom item to start tracking this day.</p>
        <div class="row mt12" style="justify-content:center">
          <button class="btn btn-deep btn-sm" id="empty-add-food">${ICONS.plus} Log your first meal</button>
          <button class="btn btn-ghost btn-sm" id="empty-add-scan">${ICONS.scanner} Scan a photo</button>
          <button class="btn btn-ghost btn-sm" id="empty-add-custom">Add custom item</button>
        </div></div>` : ""}
      <div class="mt16" id="meal-sections">
        ${Object.entries(meals.meals).map(([meal, entries]) => mealSection(meal, entries, t)).join("")}
      </div>
    </div>
    <div class="grid" style="gap:16px;position:sticky;top:76px">
      <div class="card">
        <div class="card-head"><span class="card-title">Energy & macros</span>
          ${t ? `<span class="pill pill-mint">${Math.round(100 * summary.totals.kcal / t.kcal)}% of cap</span>` : ""}</div>
        <div style="display:flex;justify-content:center">
          ${t ? ringChart(summary.totals.kcal / t.kcal, { size: 132, label: fmt(Math.max(0, t.kcal - summary.totals.kcal)), sub: `of ${fmt(t.kcal)} kcal` })
              : `<div class="empty" style="padding:16px">Set profile for targets</div>`}
        </div>
        ${t ? hBar("Protein", summary.totals.protein_g, t.protein_g, COLORS.protein, `${fmt(summary.totals.protein_g, 1)}g / ${fmt(t.protein_g)}g`)
            + hBar("Carbohydrates", summary.totals.carbs_g, t.carbs_g, COLORS.carbs, `${fmt(summary.totals.carbs_g, 1)}g / ${fmt(t.carbs_g)}g`)
            + hBar("Dietary fats", summary.totals.fat_g, t.fat_g, COLORS.fat, `${fmt(summary.totals.fat_g, 1)}g / ${fmt(t.fat_g)}g`) : ""}
      </div>
      <div class="card">
        <div class="card-head"><span class="card-title">Micronutrients</span>
          <span class="tiny muted">tracked subset</span></div>
        ${t ? microPanel(summary.totals, t.micro) : `<p class="small muted">Fill your profile to compare against reference targets.</p>`}
        <p class="tiny faint mt12">Subset tracked: fiber, sodium, potassium, calcium, iron (see data/SOURCES.md).</p>
      </div>
    </div>
  </div>`;

  $("#day-prev").onclick = () => { S.trackerDate = shiftDate(date, -1); renderTracker(); };
  $("#day-next").onclick = () => { S.trackerDate = shiftDate(date, 1); renderTracker(); };
  $("#add-custom").onclick = () => openCustomModal();
  const eaf = $("#empty-add-food"); if (eaf) eaf.onclick = () => openFoodSearchModal("breakfast");
  const eac = $("#empty-add-custom"); if (eac) eac.onclick = () => openCustomModal();
  const eas = $("#empty-add-scan"); if (eas) eas.onclick = () => location.hash = "#/scanner";
  bindMealRowButtons();
  $$("#meal-sections [data-add-meal]").forEach((b) => b.onclick = () => openFoodSearchModal(b.dataset.addMeal));

  const input = $("#food-search");
  let timer = null;
  input.oninput = () => {
    clearTimeout(timer);
    timer = setTimeout(() => runFoodSearch(input.value), 220);
  };
  runFoodSearch("");
}

function microPanel(totals, micro) {
  const rows = [
    ["Dietary fiber", totals.fiber_g, micro.fiber_g, "g", COLORS.protein, false],
    ["Sodium", totals.sodium_mg, micro.sodium_mg, "mg", COLORS.fat, true],
    ["Potassium", totals.potassium_mg, micro.potassium_mg, "mg", COLORS.carbs, false],
    ["Calcium", totals.calcium_mg, micro.calcium_mg, "mg", COLORS.protein, false],
    ["Iron", totals.iron_mg, micro.iron_mg, "mg", COLORS.fat, false],
  ];
  return rows.map(([label, val, max, unit, color, isUpper]) => {
    const pct = Math.round(100 * val / max);
    const badge = isUpper
      ? (val <= max ? `<span class="pill pill-mint">within limit</span>` : `<span class="pill pill-rose">over limit</span>`)
      : (pct >= 100 ? `<span class="pill pill-mint">${pct}% ✓</span>` : `<span class="pill pill-slate">${pct}%</span>`);
    return `<div class="row spread mt12 small"><div><b>${label}</b>
      <div class="tiny muted">${fmt(val, 1)}${unit} / ${fmt(max)}${unit}${isUpper ? " (upper limit)" : ""}</div></div>${badge}</div>
      <div class="bar mt8"><i style="width:${Math.min(100, pct)}%;background:${color}"></i></div>`;
  }).join("");
}

function mealSection(meal, entries, t) {
  const meta = MEAL_META[meal];
  const kcal = entries.reduce((s, e) => s + e.nutrients.kcal, 0);
  const p = entries.reduce((s, e) => s + e.nutrients.protein_g, 0);
  const c = entries.reduce((s, e) => s + e.nutrients.carbs_g, 0);
  const f = entries.reduce((s, e) => s + e.nutrients.fat_g, 0);
  return `<div class="meal-block">
    <div class="meal-head">
      <span class="icon-pill ${meta.tint}">${meta.icon}</span>
      <div style="flex:1"><b>${meta.label}</b>
        <span class="pill pill-slate" style="margin-left:6px">${entries.length} logged</span></div>
      <span class="small muted"><b style="color:var(--ink)">${fmt(kcal)}</b> kcal ·
        <span style="color:${COLORS.protein}">${fmt(p, 1)}g P</span> ·
        <span style="color:var(--primary)">${fmt(c, 1)}g C</span> ·
        <span style="color:${COLORS.fat}">${fmt(f, 1)}g F</span></span>
    </div>
    <div class="meal-rows">
      ${entries.length ? entries.map((e) => `
        <div class="meal-row">
          <span class="food-dot" style="background:${COLORS.protein}"></span>
          <div style="flex:1"><div class="nm">${esc(e.display_name)}</div>
            <div class="meta">${fmt(e.quantity, 2)} ${e.unit === "serving" ? "× " + esc(e.food ? e.food.serving_desc : "serving") : "g"}${e.food ? " · " + esc(e.food.source || "") : ""}</div></div>
          <div class="row small muted" style="gap:12px">
            <span>P ${fmt(e.nutrients.protein_g, 1)}</span><span>C ${fmt(e.nutrients.carbs_g, 1)}</span><span>F ${fmt(e.nutrients.fat_g, 1)}</span></div>
          <div class="kcal">${fmt(e.nutrients.kcal)} <small>kcal</small></div>
          <button class="icon-btn" data-edit-entry="${e.id}">${ICONS.edit}</button>
          <button class="icon-btn" data-del-entry="${e.id}">${ICONS.trash}</button>
        </div>`).join("")
      : `<div class="empty">Nothing logged for ${meta.label.toLowerCase()} yet.</div>`}
    </div>
    <button class="add-item" data-add-meal="${meal}">⊕ Add item to ${meta.label}</button>
  </div>`;
}

/* ---------------- search ---------------- */
async function runFoodSearch(q) {
  const box = $("#search-results");
  if (!box) return;
  const data = await api(`/foods?q=${encodeURIComponent(q)}&limit=8`);
  if (!data.foods.length) {
    box.innerHTML = `<div class="results"><div class="empty">No match. Try “dal”, “roti”, “paneer”… or add a custom item.</div></div>`;
    return;
  }
  box.innerHTML = `<div class="results">` + data.foods.map((f) => `
    <div class="result-row" data-food='${JSON.stringify(f).replace(/'/g, "&#39;")}'>
      <span class="icon-pill tint-teal">${ICONS.tracker}</span>
      <div style="flex:1"><b class="small">${esc(f.name)}</b>
        <div class="tiny muted">${esc(f.grp)} · ${esc(f.serving_desc)} · ${fmt(f.kcal)} kcal/100g · ${esc(f.source)}</div></div>
      <span class="pill pill-teal">${fmt(f.kcal * f.serving_g / 100)} kcal/serving</span>
      <span class="pill pill-mint">+ Add</span>
    </div>`).join("") + `</div>`;
  $$(".result-row", box).forEach((row) => row.onclick = () =>
    openFoodSearchModal(S.lastMeal || "breakfast", JSON.parse(row.dataset.food)));
}

/* ---------------- modals ---------------- */
function mealOptions(selected) {
  return Object.entries(MEAL_META).map(([key, m]) =>
    `<option value="${key}" ${key === selected ? "selected" : ""}>${m.label}</option>`).join("");
}

/* If `onSelect` is supplied this remains a documented-food picker: it never
   writes a meal. Callers (the scanner correction flow) receive the selected
   food and portion, then show their own final review before saving. */
function openFoodSearchModal(meal, presetFood = null, onSelect = null) {
  S.lastMeal = meal;
  const pickerOnly = typeof onSelect === "function";
  openModal(`
    <h3>${pickerOnly ? "Search documented food catalogue" : `Add food to ${MEAL_META[meal].label}`}</h3>
    <p class="tiny muted">Pick a food, then set the portion. Nutrition is computed per-gram from the documented dataset.</p>
    <div class="searchbox mt12" style="max-width:none;border-radius:12px">${ICONS.search}
      <input id="m-search" placeholder="Search foods…" autocomplete="off"></div>
    <div id="m-results" style="max-height:220px;overflow:auto"></div>
    <div id="m-portion" class="mt12" style="display:${presetFood ? "block" : "none"}">
      <div class="field"><span class="label">Selected food</span><b id="m-food-name" class="small"></b></div>
      <div class="grid ${pickerOnly ? "cols-2" : "cols-3"}">
        ${pickerOnly ? "" : `<div class="field"><span class="label">Meal</span><select class="select" id="m-meal">${mealOptions(meal)}</select></div>`}
        <div class="field"><span class="label">Quantity</span><input class="input" id="m-qty" type="number" min="0.01" step="0.25" value="1"></div>
        <div class="field"><span class="label">Unit</span><select class="select" id="m-unit">
          <option value="serving">serving</option><option value="g">grams</option></select></div>
      </div>
      <p class="small muted" id="m-preview"></p>
      <div class="row mt16" style="justify-content:flex-end">
        <button class="btn btn-ghost" data-close>Cancel</button>
        <button class="btn btn-primary" id="m-save">${pickerOnly ? "Use this food" : `${ICONS.plus} Add to log`}</button></div>
    </div>`);
  let food = presetFood;
  const search = $("#m-search");
  const showResults = async () => {
    const data = await api(`/foods?q=${encodeURIComponent(search.value)}&limit=6`);
    $("#m-results").innerHTML = data.foods.map((f) => `
      <div class="result-row" data-id="${f.id}"><div style="flex:1"><b class="small">${esc(f.name)}</b>
      <div class="tiny muted">${esc(f.serving_desc)} · ${fmt(f.kcal)} kcal/100g</div></div>
      <span class="pill pill-teal">select</span></div>`).join("") || `<div class="empty">no matches</div>`;
    $$("#m-results .result-row").forEach((r) => r.onclick = () => {
      food = data.foods.find((f) => f.id === Number(r.dataset.id));
      selectFood();
    });
  };
  const preview = () => {
    if (!food) return;
    const qty = parseFloat($("#m-qty").value) || 0;
    const grams = $("#m-unit").value === "serving" ? qty * food.serving_g : qty;
    $("#m-preview").innerHTML = `≈ <b>${fmt(grams)} g</b> → <b>${fmt(food.kcal * grams / 100)} kcal</b>,
      P ${fmt(food.protein_g * grams / 100, 1)}g · C ${fmt(food.carbs_g * grams / 100, 1)}g · F ${fmt(food.fat_g * grams / 100, 1)}g`;
  };
  const selectFood = () => {
    $("#m-portion").style.display = "block";
    $("#m-food-name").textContent = `${food.name} (${food.serving_desc})`;
    preview();
  };
  search.oninput = showResults;
  $("#m-qty").oninput = preview;
  $("#m-unit").onchange = preview;
  if (food) selectFood(); else showResults();
  $("#m-save").onclick = async () => {
    if (!food) { toast("Select a food from the search results first", true); return; }
    const qty = parseFloat($("#m-qty").value);
    if (!(qty > 0)) { toast("Quantity must be greater than 0", true); return; }
    const grams = $("#m-unit").value === "serving" ? qty * food.serving_g : qty;
    if (pickerOnly) {
      closeModal();
      onSelect(food, grams);
      return;
    }
    try {
      await api("/meals", { method: "POST", body: {
        date: S.trackerDate || S.boot.today, meal: $("#m-meal").value,
        food_id: food.id, quantity: qty, unit: $("#m-unit").value } });
      closeModal(); toast("Added to log"); refreshView();
    } catch (e) { toast(e.message, true); }
  };
}

function openCustomModal() {
  openModal(`
    <h3>Add custom item</h3>
    <p class="tiny muted">For foods not in the database (e.g. home recipe with a label).
    Enter totals for the amount you ate.</p>
    <div class="grid cols-2 mt12">
      <div class="field"><span class="label">Name</span><input class="input" id="c-name" maxlength="80" placeholder="e.g. Home-made upma"></div>
      <div class="field"><span class="label">Meal</span><select class="select" id="c-meal">${mealOptions("snacks")}</select></div>
      <div class="field"><span class="label">Amount eaten (g)</span><input class="input" id="c-grams" type="number" min="1" value="100"></div>
      <div class="field"><span class="label">Calories (kcal)</span><input class="input" id="c-kcal" type="number" min="0" value="150"></div>
      <div class="field"><span class="label">Protein (g)</span><input class="input" id="c-p" type="number" min="0" step="0.1" value="4"></div>
      <div class="field"><span class="label">Carbs (g)</span><input class="input" id="c-c" type="number" min="0" step="0.1" value="25"></div>
      <div class="field"><span class="label">Fat (g)</span><input class="input" id="c-f" type="number" min="0" step="0.1" value="3"></div>
    </div>
    <div class="row mt8" style="justify-content:flex-end">
      <button class="btn btn-ghost" data-close>Cancel</button>
      <button class="btn btn-primary" id="c-save">${ICONS.plus} Add</button></div>`);
  $("#c-save").onclick = async () => {
    const body = {
      date: S.trackerDate || S.boot.today, meal: $("#c-meal").value,
      custom_name: $("#c-name").value.trim(), quantity: parseFloat($("#c-grams").value),
      unit: "g", custom_kcal: parseFloat($("#c-kcal").value) || 0,
      custom_protein_g: parseFloat($("#c-p").value) || 0,
      custom_carbs_g: parseFloat($("#c-c").value) || 0,
      custom_fat_g: parseFloat($("#c-f").value) || 0 };
    if (!body.custom_name) { toast("Please give the item a name", true); return; }
    if (!(body.quantity > 0)) { toast("Amount must be greater than 0", true); return; }
    try {
      await api("/meals", { method: "POST", body });
      closeModal(); toast("Custom item added"); refreshView();
    } catch (e) { toast(e.message, true); }
  };
}

async function openEntryModal(_unused, entryId) {
  const date = S.trackerDate || S.boot.today;
  const meals = await api(`/meals?date=${date}`);
  const entry = Object.values(meals.meals).flat().find((e) => e.id === entryId);
  if (!entry) { toast("Entry not found", true); return; }
  openModal(`
    <h3>Edit entry</h3><p class="tiny muted">${esc(entry.display_name)}</p>
    <div class="grid cols-3 mt12">
      <div class="field"><span class="label">Meal</span><select class="select" id="e-meal">${mealOptions(entry.meal)}</select></div>
      <div class="field"><span class="label">Quantity</span><input class="input" id="e-qty" type="number" min="0.01" step="0.25" value="${entry.quantity}"></div>
      <div class="field"><span class="label">Unit</span><select class="select" id="e-unit">
        <option value="serving" ${entry.unit === "serving" ? "selected" : ""} ${entry.food_id ? "" : "disabled"}>serving</option>
        <option value="g" ${entry.unit === "g" ? "selected" : ""}>grams</option></select></div>
    </div>
    <div class="row mt8" style="justify-content:flex-end">
      <button class="btn btn-ghost" data-close>Cancel</button>
      <button class="btn btn-primary" id="e-save">Save changes</button></div>`);
  $("#e-save").onclick = async () => {
    try {
      await api(`/meals/${entryId}`, { method: "PUT", body: {
        meal: $("#e-meal").value, quantity: parseFloat($("#e-qty").value),
        unit: $("#e-unit").value } });
      closeModal(); toast("Entry updated"); refreshView();
    } catch (e) { toast(e.message, true); }
  };
}
