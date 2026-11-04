/* Smart Nutrition Insights — dashboard section (isolated feature module).

   Renders ONLY from the read-only /api/insights + /api/insights/weekly
   endpoints, which are computed from the user's own logged records. Has its
   own loading / empty / error states and never touches existing dashboard
   code: renderDashboard() just leaves an empty #insights-root container and
   calls renderSmartInsights(). */
"use strict";

async function renderSmartInsights(rootSel = "#insights-root") {
  const root = $(rootSel);
  if (!root) return;
  root.innerHTML = `<div class="card"><p class="muted small">Loading Smart Nutrition Insights
    (from your own logged records)…</p></div>`;
  let daily, weekly;
  try {
    [daily, weekly] = await Promise.all([api("/insights"), api("/insights/weekly")]);
  } catch (e) {
    root.innerHTML = `<div class="card"><div class="card-head"><span class="card-title">Smart
      Nutrition Insights</span><span class="pill pill-rose">Could not load</span></div>
      <p class="small muted">${esc(e.message)}</p>
      <button class="btn btn-soft btn-sm mt12" id="insights-retry">Try again</button></div>`;
    const retry = $("#insights-retry");
    if (retry) retry.onclick = () => renderSmartInsights(rootSel);
    return;
  }

  const emptyWeek = !weekly.current_week;
  if (daily.logged_count === 0 && daily.water_ml === 0 && emptyWeek) {
    root.innerHTML = `<div class="card">
      <div class="card-head"><div><h3 style="font-size:17px">Smart Nutrition Insights</h3>
        <p class="tiny muted mt8">Built only from your real records — never from invented data.</p></div>
        <span class="pill pill-slate">Nothing to analyse yet</span></div>
      <div class="empty-state"><span style="font-size:30px">🔎</span>
        <b>No insights yet — and that is the honest answer.</b>
        <p class="tiny muted mt8">Insights compare your logged meals and water against your
        targets/references. An empty log never means zero intake, so nothing is guessed.
        Log your first meal and this section fills with observations about your own data.</p>
        <button class="btn btn-soft btn-sm mt12" id="insights-log-cta">${ICONS.plus} Log food</button></div>
    </div>`;
    const cta = $("#insights-log-cta");
    if (cta) cta.onclick = () => { location.hash = "#/tracker"; };
    return;
  }

  const levelPill = { gap: ["pill-amber", "GAP"], good: ["pill-mint", "ON TRACK"],
    info: ["pill-slate", "OBSERVATION"] };

  const metrics = daily.metrics.map((m) => {
    const pctv = m.pct === null || m.pct === undefined ? null : Math.min(100, m.pct);
    const color = m.key === "protein_g" ? COLORS.protein : m.key === "carbs_g" ? COLORS.carbs
      : m.key === "fat_g" ? COLORS.fat : m.key === "water_ml" ? "#0284C7" : "#0F766E";
    return `<div class="card insight-metric">
      <span class="tiny muted" style="font-weight:700">${esc(m.label)}</span>
      <div class="stat" style="font-size:22px">${fmt(m.value)}<small> / ${
        m.target === null || m.target === undefined ? "—" : fmt(m.target)} ${esc(m.unit)}</small></div>
      <div class="bar mt8"><i style="width:${pctv === null ? 0 : pctv}%;background:${color}"></i></div>
      <p class="tiny faint mt8">${m.target === null || m.target === undefined
        ? "no personalised target — profile incomplete" : `${m.pct}% of ${
          m.key === "water_ml" ? "your selected goal" : "estimate"}`}</p>
    </div>`;
  }).join("");

  const insightCards = daily.insights.map((ins) => {
    const [cls, label] = levelPill[ins.level] || levelPill.info;
    const recs = (ins.recommendations || []).map((r) => `<div class="rec-row mt8">
        <div><b class="tiny">${esc(r.name)}</b>
          <p class="tiny muted">${esc(r.contribution)}</p>
          <p class="tiny faint mt8">${esc(r.why)}</p></div>
        <span class="pill pill-slate">${esc(r.serving_desc)}</span></div>`).join("");
    return `<div class="card insight-card ${ins.level}">
      <div class="row spread"><b class="small">${esc(ins.title)}</b><span class="pill ${cls}">${label}</span></div>
      <p class="tiny muted mt8">${esc(ins.detail)}</p>
      ${recs}
      ${ins.recommendations_note ? `<p class="tiny faint mt8">${esc(ins.recommendations_note)}</p>` : ""}
    </div>`;
  }).join("");

  const wk = weekly.current_week;
  const weeklyCard = wk ? `
    <div class="card">
      <div class="card-head"><div><span class="card-title">Weekly summary (last 7 days)</span>
        <p class="tiny muted mt8">${wk.logged_days} logged day(s) · ${wk.missing_days} day(s) with
        no records — ${esc(weekly.missing_days_note)}</p></div>
        <span class="pill ${weekly.personalized ? "pill-teal" : "pill-slate"}">${
          weekly.personalized ? "Estimate-based targets" : "Non-personalised"}</span></div>
      <div class="grid cols-4 mt12">
        <div class="selfcare-card"><span class="tiny muted">Avg calories / logged day</span>
          <div class="stat" style="font-size:20px">${fmt(wk.averages.kcal)}<small> kcal</small></div></div>
        <div class="selfcare-card"><span class="tiny muted">Avg protein</span>
          <div class="stat" style="font-size:20px">${fmt(wk.averages.protein_g)}<small> g</small></div></div>
        <div class="selfcare-card"><span class="tiny muted">Avg carbs / fat</span>
          <div class="stat" style="font-size:20px">${fmt(wk.averages.carbs_g)}<small> g</small> /
            ${fmt(wk.averages.fat_g)}<small> g</small></div></div>
        <div class="selfcare-card"><span class="tiny muted">Avg water</span>
          <div class="stat" style="font-size:20px">${(wk.averages.water_ml / 1000).toFixed(1)}<small> L</small>
            <span class="tiny muted">/ ${(wk.water_goal_ml / 1000).toFixed(1)} L goal</span></div></div>
      </div>
      ${wk.averages.fiber_g === null ? "" : `<p class="tiny muted mt8">Avg fibre (dataset entries
        only): <b>${fmt(wk.averages.fiber_g)} g</b></p>`}
      <div class="row wrap mt12">${wk.top_foods.map((f) =>
        `<span class="pill pill-slate">${esc(f.name)} ×${f.times}</span>`).join("")}</div>
      ${(weekly.comparison && weekly.comparison.rows.length) ? `
        <div class="form-section mt12"><b class="tiny" style="color:#0F766E">VS PREVIOUS WEEK</b>
        ${weekly.comparison.rows.map((r) => `<div class="row spread small mt8">
          <span class="muted">${esc(r.metric)}</span>
          <b>${fmt(r.previous)} → ${fmt(r.current)} ${esc(r.unit)}
            <span style="color:${r.direction === "up" ? "#B45309" : r.direction === "down" ? "#0F766E" : "#64748B"}">${
              r.delta_pct === null ? "n/a" : (r.delta_pct > 0 ? "+" : "") + r.delta_pct + "%"}</span></b>
        </div>`).join("")}
        <p class="tiny faint mt8">${esc(weekly.comparison.note)}</p></div>`
      : `<p class="tiny faint mt12">${esc(weekly.comparison ? weekly.comparison.note
          : "No previous-week data.")}</p>`}
      ${wk.patterns.map((p) => {
        const [cls2, label2] = levelPill[p.level] || levelPill.info;
        return `<div class="insight-card ${p.level} card mt12" style="padding:12px 14px">
          <div class="row spread"><b class="tiny">${esc(p.title)}</b><span class="pill ${cls2}">${label2}</span></div>
          <p class="tiny muted mt8">${esc(p.detail)}</p></div>`;
      }).join("")}
    </div>` : `
    <div class="card"><div class="card-head"><span class="card-title">Weekly summary</span></div>
      <p class="small muted">No records in the last 7 days. Missing days are never averaged as
      zero — log meals and the weekly picture builds from real data only.</p></div>`;

  root.innerHTML = `
  <div class="card" style="background:linear-gradient(120deg,#F0FDFA,#F8FAFC);border-color:#CCFBF1">
    <div class="card-head spread"><div>
      <h3 style="font-size:17px">Smart Nutrition Insights</h3>
      <p class="tiny muted mt8">Every number below comes from your own logged meals and water —
      nothing is estimated from missing data. ${esc(daily.date)}${
        daily.personalized ? " · targets are estimates from your profile" : ""}</p></div>
      <span class="pill ${daily.personalized ? "pill-teal" : "pill-amber"}">${
        daily.personalized ? "Personalised (estimates)" : "Non-personalised"}</span></div>
    ${!daily.personalized ? `<p class="tiny mt8" style="color:#92400E">${esc(daily.limitation_note)}
      </p>` : ""}
    <div class="metric-grid mt12">${metrics}</div>
    <div class="insight-grid mt16">${insightCards}</div>
    <p class="tiny faint mt12">${esc(daily.disclaimer)}</p>
  </div>
  <div class="mt16">${weeklyCard}</div>`;
}
