/* Dashboard + Nutrition Tracker views. */
"use strict";

const MEAL_META = {
  breakfast: { label: "Breakfast", icon: ICONS.meal, tint: "tint-amber" },
  lunch: { label: "Lunch", icon: ICONS.meal, tint: "tint-teal" },
  dinner: { label: "Dinner", icon: ICONS.meal, tint: "tint-sky" },
  snacks: { label: "Snacks & Beverages", icon: ICONS.meal, tint: "tint-rose" },
};

/* ============================================================ DASHBOARD */
async function renderDashboard() {
  const [summary, report] = await Promise.all([api("/summary"), api("/report?days=7")]);
  const t = summary.targets;
  const profile = summary.profile || {};
  const name = (S.boot.user && S.boot.user.name) || "there";
  const consumed = summary.totals.kcal;
  const remaining = t ? Math.max(0, t.kcal - consumed) : 0;
  const units = profile.units || "metric";
  const weekEmpty = report.per_day.every((d) => (d.logged_count || 0) === 0 && !d.water_ml);
  const waterPct = summary.water_goal_ml ? Math.round(100 * summary.water_ml / summary.water_goal_ml) : 0;
  const profileLine = [
    profile.age ? `${fmt(profile.age)} yrs` : null,
    profile.sex ? esc(profile.sex) : null,
    profile.weight_kg ? `${fmt(profile.weight_kg, 1)} kg` : null,
    profile.activity ? esc(profile.activity) : null,
  ].filter(Boolean).join(" · ");

  const macroCells = t ? [
    ["Protein", summary.totals.protein_g, t.protein_g, COLORS.protein],
    ["Carbs", summary.totals.carbs_g, t.carbs_g, COLORS.carbs],
    ["Fat", summary.totals.fat_g, t.fat_g, COLORS.fat],
  ].map(([label, value, goal, color]) => {
    const pct = goal ? Math.round(100 * value / goal) : 0;
    return `<div class="audit-macro-cell"><span class="audit-macro-dot" style="background:${color}"></span>
      <span class="audit-macro-label">${label}</span><b>${fmt(value, 1)}g</b>
      <small>${pct}% of target</small></div>`;
  }).join("") : `<p class="small muted">Complete your <a href="#/profile">health profile</a> to unlock personalised macro targets.</p>`;

  const nutritionSnapshot = t && t.micro
    ? microPanel(summary.totals, t.micro)
    : `<p class="small muted">Complete your profile to compare nutrient totals with reference targets.</p>`;
  const insights = dashboardInsights(summary, t);

  $("#view").innerHTML = `
  <section class="audit-header" aria-labelledby="audit-title">
    <div class="audit-header-copy">
      <div class="audit-eyebrow">NUTRITION JOURNAL · ${esc(prettyDate(S.boot.today))}</div>
      <h2 id="audit-title">Daily Nutritional Audit <span>&amp; Dietary Intake</span></h2>
      <p class="audit-subject">${profileLine ? `For ${esc(name)} · ${profileLine}`
        : "Add your profile details to personalise daily targets and nutrition context."}</p>
    </div>
    <div class="audit-actions" aria-label="Quick actions">
      <button class="btn btn-soft" id="quick-water">${ICONS.drop} +250 ml water</button>
      <button class="btn btn-ghost" id="quick-log">${ICONS.plus} Log meals</button>
      <a class="btn btn-ghost" href="/api/report.pdf" download>${ICONS.download} Export PDF</a>
      <a class="btn btn-ghost" href="/api/report.csv?days=7" download>${ICONS.download} Export CSV</a>
      <button class="btn btn-deep" id="quick-scan">${ICONS.scanner} Scan a meal</button>
    </div>
  </section>

  <section class="audit-stat-grid" aria-label="Daily nutrition summary">
    <article class="audit-stat-card audit-energy-card">
      <div class="audit-card-label">Energy budget · daily intake <span aria-hidden="true">${ICONS.dashboard}</span></div>
      <div class="audit-energy-content">
        ${t ? ringChart(consumed / t.kcal, { size: 104, stroke: 9, label: fmt(consumed), sub: `of ${fmt(t.kcal)} kcal` })
          : `<div class="audit-energy-number">${fmt(consumed)}<small> kcal logged</small></div>`}
        <div class="audit-side-reading"><b>${t ? fmt(remaining) : "—"}</b><span>${t ? "kcal remaining" : "set a target"}</span>
          <small>${summary.logged_count ? `${summary.logged_count} entries today` : "No meals recorded"}</small></div>
      </div>
      <div class="audit-rule"></div>
      <p class="tiny muted">${t ? "Targets are personalised estimates from your profile." : "Target not set — complete your profile to personalise it."}</p>
    </article>

    <article class="audit-stat-card">
      <div class="audit-card-label">Macronutrient allocation <span aria-hidden="true">${ICONS.reports}</span></div>
      <div class="audit-macro-grid">${macroCells}</div>
      <div class="audit-rule"></div>
      <p class="tiny muted">${t ? `Protein target: ${fmt(t.protein_g)} g · balanced across your logged meals.` : "Targets appear after you complete your profile."}</p>
    </article>

    <article class="audit-stat-card">
      <div class="audit-card-label">Hydration balance <span aria-hidden="true">${ICONS.drop}</span></div>
      <div class="audit-hydration-content">
        <div><div class="audit-hydration-reading"><b>${units === "imperial" ? fmt(summary.water_ml / 29.5735, 0) + " oz" : (summary.water_ml / 1000).toFixed(1) + " L"}</b>
          <span>/ ${units === "imperial" ? fmt(summary.water_goal_ml / 29.5735, 0) + " oz" : (summary.water_goal_ml / 1000).toFixed(1) + " L"}</span></div>
          <div class="audit-water-meta"><span>${waterPct}% of goal</span><b>${Math.max(0, summary.water_goal_ml - summary.water_ml) ? UNITS.water(Math.max(0, summary.water_goal_ml - summary.water_ml), units) + " to go" : "Goal reached"}</b></div></div>
        <div class="audit-water-meter" role="progressbar" aria-label="Hydration goal progress" aria-valuemin="0" aria-valuemax="${summary.water_goal_ml}" aria-valuenow="${Math.min(summary.water_ml, summary.water_goal_ml)}" aria-valuetext="${waterPct}% of hydration goal">
          <i style="height:0"></i>
        </div>
      </div>
      <div class="audit-rule"></div>
      <p class="tiny muted">${summary.water_ml ? "Hydration is based on the water you have logged today." : "Start with one glass when you are ready."}</p>
    </article>

    <article class="audit-stat-card">
      <div class="audit-card-label">Personal targets <span aria-hidden="true">${ICONS.profile}</span></div>
      ${t ? `<div class="audit-target-row"><span>BMR (Mifflin-St Jeor)</span><b>${fmt(t.bmr)} kcal</b></div>
      <div class="audit-target-row"><span>Daily energy target</span><b>${fmt(t.kcal)} kcal</b></div>
      <div class="audit-target-row"><span>Activity</span><b>${esc(profile.activity || "not set")}</b></div>`
      : `<p class="small muted">Set your age, height, weight, and activity level to calculate personal targets.</p>`}
      <div class="audit-rule"></div>
      <p class="tiny muted">${t ? "Calculated values guide planning; they are not a medical assessment." : "Personal targets are optional and can be changed anytime."}</p>
    </article>
  </section>

  <section class="audit-workspace">
    <div class="audit-main-column">
      <article class="card audit-today-card">
        <div class="card-head audit-section-head"><div><span class="audit-section-kicker">TODAY'S TOTAL INTAKE</span>
          <h3>Calories &amp; macro distribution</h3>
          <p class="tiny muted mt8">Your logged energy and macronutrients, grouped by meal.</p></div>
          <div class="audit-status-stack"><span class="pill pill-mint">${summary.logged_count} logged ${summary.logged_count === 1 ? "entry" : "entries"}</span>
            ${t ? `<span class="pill pill-slate">Target ${fmt(t.kcal)} kcal</span>` : ""}</div></div>
        ${todayIntakeChart(summary, t)}
      </article>

      <article class="card audit-log-card">
        <div class="card-head audit-section-head"><div><span class="audit-section-kicker">DAILY FOOD LOG</span>
          <h3>Meals recorded today</h3></div>
          <button class="btn btn-soft btn-sm" id="goto-tracker">Open tracker</button></div>
        <p class="tiny muted">Items are summed from the documented food dataset and stay editable in your tracker.</p>
        <div class="audit-meal-list mt12">${dashboardMealList(summary)}</div>
      </article>
    </div>

    <aside class="audit-side-column">
      <article class="card audit-micro-card">
        <div class="card-head audit-section-head"><div><span class="audit-section-kicker">NUTRIENT OVERVIEW</span>
          <h3>Micronutrient snapshot</h3></div>
          <span class="pill pill-slate">tracked subset</span></div>
        ${nutritionSnapshot}
        <p class="tiny faint mt12">Fiber, sodium, potassium, calcium, and iron are shown when documented for your logged foods.</p>
      </article>

      <article class="card audit-insights-card">
        <div class="card-head audit-section-head"><div><span class="audit-section-kicker">GENTLE GUIDANCE</span>
          <h3>Today's nutrition notes</h3></div></div>
        <div class="grid" style="gap:10px">${insights}</div>
      </article>

      <article class="card audit-care-card">
        <span class="audit-section-kicker">HEALTH ASSISTANT</span>
        <h3>Need help making sense of a symptom?</h3>
        <p class="small muted mt8">Use a short structured check for general education, self-care, and urgent warning signs.</p>
        <button class="btn btn-ghost mt12" id="quick-symptoms">Start a check →</button>
      </article>
    </aside>
  </section>

  <div id="insights-root" class="audit-smart-root"></div>
  <footer class="audit-footer"><span>${ICONS.shield}</span><div><b>NutriCare nutrition record</b>
    <p>Your dashboard is built from the meals and water you log. Nutrition targets remain estimates, not medical advice.</p></div>
    <span class="tiny">Data sources shown with food entries</span></footer>`;

  /* Insert at zero then raise on the next frame so the vertical meter visibly
     fills when this live dashboard is rendered. */
  const fillWaterMeter = () => {
    const fill = $(".audit-water-meter i");
    if (fill) fill.style.height = `${Math.min(100, waterPct)}%`;
  };
  if (typeof requestAnimationFrame === "function") requestAnimationFrame(fillWaterMeter);
  else setTimeout(fillWaterMeter, 0);

  $("#quick-water").onclick = async () => {
    await api("/water", { method: "POST", body: { amount_ml: 250 } });
    toast("+250 ml water logged"); renderDashboard();
  };
  $("#quick-symptoms").onclick = () => location.hash = "#/assistant";
  $("#quick-log").onclick = () => location.hash = "#/tracker";
  const quickScan = $("#quick-scan");
  if (quickScan) quickScan.onclick = () => location.hash = "#/scanner";
  $("#goto-tracker").onclick = () => location.hash = "#/tracker";
  bindMealRowButtons();
  /* Smart Nutrition Insights renders into #insights-root with independent
     loading, empty, and error states so it cannot block the dashboard. The
     seven-day chart is supplied as its immediate prelude to sit above the
     weekly summary rather than interrupting today's intake and meal log. */
  if (typeof renderSmartInsights === "function") {
    renderSmartInsights("#insights-root", weeklyTrajectoryCard(report, t, weekEmpty));
  }
}

function adherencePct(report, targets) {
  if (!targets) return "—";
  const days = report.per_day.filter((d) => d.kcal > 0);
  if (!days.length) return "no logged days yet";
  const within = days.filter((d) => Math.abs(d.kcal - targets.kcal) / targets.kcal <= 0.15).length;
  return `${Math.round(100 * within / days.length)}% of logged days within ±15%`;
}

function weeklyTrajectoryCard(report, targets, weekEmpty) {
  const loggedDays = report.per_day.filter((d) => d.logged_count).length;
  return `<article class="card audit-timeline-card">
    <div class="card-head audit-section-head"><div><span class="audit-section-kicker">7-DAY OVERVIEW</span>
      <h3>Intake trajectory &amp; macro balance</h3>
      <p class="tiny muted mt8">Your recorded nutrition across the last seven days.</p></div>
      <div class="audit-status-stack"><span class="pill pill-mint">${loggedDays} logged days</span>
        ${targets ? `<span class="pill pill-slate">Target ${fmt(targets.kcal)} kcal</span>` : ""}</div></div>
    <div class="audit-chart-shell">${weekEmpty ? `<div class="empty-state"><span class="audit-empty-icon" aria-hidden="true">${ICONS.reports}</span>
      <b>Your trend will appear after your first logged day.</b>
      <p class="tiny muted mt8">NutriCare only charts food you have actually recorded.</p>
      <a class="btn btn-soft btn-sm mt12" href="#/tracker">${ICONS.plus} Log your first meal</a></div>`
      : stackedWeekChart(report.per_day, targets ? targets.kcal : null)}</div>
    <div class="audit-chart-foot"><span>Weekly target adherence: <b>${weekEmpty ? "no logged days yet" : adherencePct(report, targets)}</b></span>
      <a href="#/reports">Open detailed reports →</a></div>
  </article>`;
}

function todayIntakeChart(summary, targets) {
  const rows = Object.keys(MEAL_META).map((meal) => {
    const entries = (summary.meals && summary.meals[meal]) || [];
    return {
      meal,
      label: MEAL_META[meal].label,
      count: entries.length,
      kcal: entries.reduce((sum, entry) => sum + Number(entry.nutrients.kcal || 0), 0),
      protein: entries.reduce((sum, entry) => sum + Number(entry.nutrients.protein_g || 0), 0),
      carbs: entries.reduce((sum, entry) => sum + Number(entry.nutrients.carbs_g || 0), 0),
      fat: entries.reduce((sum, entry) => sum + Number(entry.nutrients.fat_g || 0), 0),
    };
  });
  const hasEntries = rows.some((row) => row.count > 0);
  if (!hasEntries) {
    return `<div class="empty-state audit-today-empty"><span class="audit-empty-icon" aria-hidden="true">${ICONS.meal}</span>
      <b>Nothing logged today yet.</b>
      <p class="tiny muted mt8">Add a meal to see its calories and macro distribution here.</p>
      <a class="btn btn-soft btn-sm mt12" href="#/tracker">${ICONS.plus} Log your first meal</a></div>`;
  }

  const maxKcal = Math.max(1, targets ? Number(targets.kcal || 0) : 0, ...rows.map((row) => row.kcal));
  const bar = (row) => {
    const macroParts = [
      { cls: "protein", label: "Protein", energy: row.protein * 4 },
      { cls: "carbs", label: "Carbohydrates", energy: row.carbs * 4 },
      { cls: "fat", label: "Fat", energy: row.fat * 9 },
    ];
    const macroEnergy = macroParts.reduce((sum, part) => sum + part.energy, 0);
    const scale = macroEnergy > row.kcal && macroEnergy ? row.kcal / macroEnergy : 1;
    let bottom = 0;
    const segments = macroParts.map((part) => {
      const energy = part.energy * scale;
      const height = 100 * energy / maxKcal;
      const segment = height ? `<i class="audit-intake-segment ${part.cls}" style="height:${height.toFixed(3)}%;bottom:${bottom.toFixed(3)}%" title="${part.label}: ${fmt(energy)} kcal"></i>` : "";
      bottom += height;
      return segment;
    }).join("");
    const remainingEnergy = Math.max(0, row.kcal - macroEnergy * scale);
    const remainingHeight = 100 * remainingEnergy / maxKcal;
    const other = remainingHeight ? `<i class="audit-intake-segment other" style="height:${remainingHeight.toFixed(3)}%;bottom:${bottom.toFixed(3)}%" title="Other documented energy: ${fmt(remainingEnergy)} kcal"></i>` : "";
    return `<div class="audit-intake-column">
      <b>${fmt(row.kcal)}<small> kcal</small></b>
      <div class="audit-intake-track" aria-label="${row.label}: ${fmt(row.kcal)} kilocalories, ${fmt(row.protein, 1)} grams protein, ${fmt(row.carbs, 1)} grams carbohydrates, ${fmt(row.fat, 1)} grams fat">${segments}${other}</div>
      <span>${row.label}</span><small>${row.count} ${row.count === 1 ? "entry" : "entries"}</small>
    </div>`;
  };
  return `<div class="audit-today-chart">
    <div class="audit-macro-legend" aria-label="Macronutrient colour legend"><span><i class="protein"></i>Protein</span>
      <span><i class="carbs"></i>Carbs</span><span><i class="fat"></i>Fat</span></div>
    <div class="audit-intake-bars">${rows.map(bar).join("")}</div>
    <div class="audit-today-totals"><span><i class="protein"></i><b>${fmt(summary.totals.protein_g, 1)} g</b> protein</span>
      <span><i class="carbs"></i><b>${fmt(summary.totals.carbs_g, 1)} g</b> carbs</span>
      <span><i class="fat"></i><b>${fmt(summary.totals.fat_g, 1)} g</b> fat</span>
      <span class="audit-total-energy"><b>${fmt(summary.totals.kcal)} kcal</b> total energy</span></div>
    <p class="tiny faint mt12">Bars show logged calories by meal. Colours show the documented energy contribution of protein, carbohydrates, and fat.</p>
  </div>`;
}

function dashboardInsights(summary, t) {
  if (summary.logged_count === 0 && summary.water_ml === 0) {
    return [`<div class="selfcare-card"><div class="row" style="gap:8px"><span class="audit-insight-icon">${ICONS.leaf}</span>
      <b class="small">Start here</b></div>
      <p class="tiny muted mt8">Your account is genuinely empty. Log your first meal in the tracker,
      add water as you drink it, and this panel will switch to observations based only on your own data.</p></div>`];
  }
  const tips = [];
  if (summary.water_ml < summary.water_goal_ml * 0.6) {
    tips.push([ICONS.drop, "Hydration pace", `You're at ${fmt(100 * summary.water_ml / summary.water_goal_ml)}% of your fluid goal. Spreading sips across the afternoon is a common general strategy.`]);
  } else {
    tips.push([ICONS.drop, "Hydration on track", "Nice — your logged intake is above 60% of goal with the day still running."]);
  }
  if (t && summary.totals.protein_g < t.protein_g * 0.6) {
    tips.push([ICONS.meal, "Protein pacing", "Protein is behind target. Curd, dal, eggs, paneer or grilled chicken at the next meal are common whole-food options."]);
  }
  if (t && summary.totals.fat_g > t.fat_g) {
    tips.push([ICONS.reports, "Fat over goal", "Today's fat is above target — mostly a heads-up for meal planning, not a problem in itself."]);
  }
  tips.push([ICONS.leaf, "Fiber check", "Reports tracks your daily fiber against a 28 g reference. Whole grains, dal and vegetables are the usual contributors."]);
  return tips.map(([icon, title, body]) => `
    <div class="selfcare-card"><div class="row" style="gap:8px"><span class="audit-insight-icon">${icon}</span>
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
        <span class="audit-empty-icon" aria-hidden="true">${ICONS.meal}</span><b>Your food log for ${prettyDate(date)} is empty.</b>
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
      : (pct >= 100 ? `<span class="pill pill-mint">${pct}%</span>` : `<span class="pill pill-slate">${pct}%</span>`);
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
    chooseMealForFood(JSON.parse(row.dataset.food)));
}

/* ---------------- modals ---------------- */
function mealOptions(selected) {
  return Object.entries(MEAL_META).map(([key, m]) =>
    `<option value="${key}" ${key === selected ? "selected" : ""}>${m.label}</option>`).join("");
}

/* A catalogue result never assumes a meal category. The person makes this
   choice before the portion form opens; Skip simply closes the flow and writes
   nothing to the food log. */
function chooseMealForFood(food) {
  openModal(`
    <h3>Add ${esc(food.name)} to a meal</h3>
    <p class="tiny muted mt8">Choose when you had it. You will review the portion before anything is added to your log.</p>
    <div class="tile-grid mt16 meal-choice-grid" role="group" aria-label="Choose meal category">
      ${Object.entries(MEAL_META).map(([meal, meta]) => `<button class="tile-btn" type="button" data-meal-choice="${meal}">
        <span class="meal-choice-icon ${meta.tint}" aria-hidden="true">${meta.icon}</span>
        <b>${meal === "snacks" ? "Snacks" : meta.label}</b></button>`).join("")}
    </div>
    <div class="row mt20" style="justify-content:flex-end">
      <button class="btn btn-ghost" type="button" data-close>Skip for now</button></div>`);
  $$("[data-meal-choice]").forEach((button) => button.onclick = () => {
    const meal = button.dataset.mealChoice;
    closeModal();
    openFoodSearchModal(meal, food);
  });
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
