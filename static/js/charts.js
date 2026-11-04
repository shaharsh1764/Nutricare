/* Tiny dependency-free SVG chart builders. */
"use strict";

const COLORS = { protein: "#047857", carbs: "#2DD4BF", fat: "#0284C7",
  goal: "#94A3B8", water: "#0EA5E9" };

/* Progress ring (0..1) */
function ringChart(pct, { size = 108, stroke = 11, color = "#0D9488", label = "", sub = "" } = {}) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(1, pct));
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img">
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="#F1F5F9" stroke-width="${stroke}"/>
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${color}" stroke-width="${stroke}"
      stroke-linecap="round" stroke-dasharray="${c * clamped} ${c}"
      transform="rotate(-90 ${size / 2} ${size / 2})"/>
    <text x="50%" y="${sub ? "47%" : "53%"}" text-anchor="middle" font-size="${size / 5.2}"
      font-weight="800" fill="#0F172A">${esc(label)}</text>
    ${sub ? `<text x="50%" y="63%" text-anchor="middle" font-size="${size / 10.5}" fill="#64748B">${esc(sub)}</text>` : ""}
  </svg>`;
}

/* Stacked macro-calorie bars for a week + dashed kcal goal line */
function stackedWeekChart(perDay, goalKcal) {
  const W = 640, H = 210, padL = 34, padB = 26, padT = 14;
  const n = perDay.length || 1;
  const bw = Math.min(46, (W - padL - 10) / n - 14);
  const maxVal = Math.max(goalKcal || 0, ...perDay.map((d) => d.kcal || 0), 100) * 1.15;
  const y = (v) => H - padB - (v / maxVal) * (H - padB - padT);
  let bars = "";
  perDay.forEach((d, i) => {
    const x = padL + i * ((W - padL - 10) / n) + ((W - padL - 10) / n - bw) / 2;
    const pK = (d.protein_g || 0) * 4, cK = (d.carbs_g || 0) * 4, fK = (d.fat_g || 0) * 9;
    const isToday = i === perDay.length - 1;
    let yCursor = H - padB;
    [[fK, COLORS.fat], [cK, COLORS.carbs], [pK, COLORS.protein]].forEach(([val, color]) => {
      const h = (val / maxVal) * (H - padB - padT);
      yCursor -= h;
      bars += `<rect x="${x}" y="${yCursor}" width="${bw}" height="${Math.max(h - 1.5, 0)}" rx="3"
        fill="${color}" opacity="${isToday ? 1 : 0.82}"/>`;
    });
    const label = isToday ? "Today" : new Date(d.date + "T00:00:00")
      .toLocaleDateString("en-IN", { weekday: "short" });
    bars += `<text x="${x + bw / 2}" y="${H - 8}" text-anchor="middle" font-size="10.5"
      font-weight="${isToday ? 800 : 600}" fill="${isToday ? "#0F766E" : "#64748B"}">${label}</text>`;
  });
  const goalY = y(goalKcal || 0);
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img">
    ${bars}
    ${goalKcal ? `<line x1="6" x2="${W - 6}" y1="${goalY}" y2="${goalY}" stroke="${COLORS.goal}"
      stroke-dasharray="5 5" stroke-width="1.4"/>
    <text x="${W - 6}" y="${goalY - 5}" text-anchor="end" font-size="10" fill="#64748B">Goal ${fmt(goalKcal)} kcal</text>` : ""}
  </svg>`;
}

/* Simple single-series bars with goal line (reports) */
function barsChart(perDay, goalKcal, valueKey = "kcal") {
  const W = 640, H = 200, padL = 34, padB = 26, padT = 12;
  const n = perDay.length || 1;
  const slot = (W - padL - 10) / n;
  const bw = Math.min(40, slot - 10);
  const maxVal = Math.max(goalKcal || 0, ...perDay.map((d) => d[valueKey] || 0), 10) * 1.15;
  let out = "";
  perDay.forEach((d, i) => {
    const x = padL + i * slot + (slot - bw) / 2;
    const h = ((d[valueKey] || 0) / maxVal) * (H - padB - padT);
    const isToday = i === perDay.length - 1;
    const dt = new Date(d.date + "T00:00:00");
    out += `<rect x="${x}" y="${H - padB - h}" width="${bw}" height="${Math.max(h, 1)}" rx="4"
      fill="${isToday ? "#5EEAD4" : "#0F766E"}"/>`;
    const label = n > 14 ? (i % Math.ceil(n / 10) === 0 ? `${dt.getDate()}/${dt.getMonth() + 1}` : "")
      : `${dt.toLocaleDateString("en-IN", { weekday: "short" })} ${dt.getDate()}`;
    out += `<text x="${x + bw / 2}" y="${H - 8}" text-anchor="middle" font-size="9.5" fill="#64748B">${label}</text>`;
  });
  const goalY = H - padB - ((goalKcal || 0) / maxVal) * (H - padB - padT);
  if (goalKcal) {
    out += `<line x1="6" x2="${W - 6}" y1="${goalY}" y2="${goalY}" stroke="${COLORS.goal}" stroke-dasharray="5 5" stroke-width="1.3"/>`;
  }
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img">${out}</svg>`;
}

/* Donut for macro share */
function donutChart(segments, centerLabel, centerSub) {
  const size = 168, stroke = 26, r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const total = segments.reduce((s, x) => s + x.value, 0) || 1;
  let offset = 0, rings = "";
  segments.forEach((seg) => {
    const frac = seg.value / total;
    rings += `<circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${seg.color}"
      stroke-width="${stroke}" stroke-dasharray="${c * frac} ${c}" stroke-dashoffset="${-c * offset}"
      transform="rotate(-90 ${size / 2} ${size / 2})"/>`;
    offset += frac;
  });
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img">
    ${rings}
    <text x="50%" y="48%" text-anchor="middle" font-size="24" font-weight="800" fill="#0F172A">${esc(centerLabel)}</text>
    <text x="50%" y="61%" text-anchor="middle" font-size="10.5" fill="#64748B">${esc(centerSub)}</text>
  </svg>`;
}

/* Horizontal labelled progress bar */
function hBar(label, value, max, color, valueLabel) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return `<div class="mt8">
    <div class="row spread small"><span class="row" style="gap:6px"><span class="dot" style="background:${color}"></span>
      <b>${esc(label)}</b></span><span class="muted">${esc(valueLabel || fmt(value))}</span></div>
    <div class="bar mt8"><i style="width:${pct}%;background:${color}"></i></div>
  </div>`;
}
