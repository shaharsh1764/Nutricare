/* NutriCare frontend utilities: tiny DOM helpers, API client, units, modals. */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmt(n, digits = 0) {
  if (n === null || n === undefined || isNaN(n)) return "—";
  return Number(n).toLocaleString("en-IN", { maximumFractionDigits: digits,
    minimumFractionDigits: 0 });
}

const todayISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const shiftDate = (iso, days) => {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const prettyDate = (iso) => {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
};

/* ---------------- application theme ----------------
   Theme is intentionally device/browser-wide rather than profile-specific:
   local profiles organise health data, while display comfort belongs to the
   person using this browser. The tiny inline head script applies this same
   preference before the stylesheet paints; these helpers keep it in sync once
   the app is running. */
const THEME_STORAGE_KEY = "nutricare_theme";
const THEMES = ["light", "dark"];

function storedTheme() {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY);
    return THEMES.includes(value) ? value : null;
  } catch { return null; }
}

function systemTheme() {
  try {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark" : "light";
  } catch { return "light"; }
}

function currentTheme() {
  const active = document.documentElement && document.documentElement.dataset
    ? document.documentElement.dataset.theme : null;
  return THEMES.includes(active) ? active : (storedTheme() || systemTheme());
}

function syncThemeControls() {
  ["light", "dark"].forEach((theme) => {
    const control = $(`#s-theme-${theme}`);
    if (!control) return;
    const selected = currentTheme() === theme;
    control.setAttribute("aria-pressed", selected ? "true" : "false");
    control.classList.toggle("active", selected);
  });
}

function applyTheme(theme, persist = false) {
  const next = THEMES.includes(theme) ? theme : systemTheme();
  const root = document.documentElement;
  if (root) {
    if (root.dataset) root.dataset.theme = next;
    if (root.style) root.style.colorScheme = next;
  }
  if (persist) {
    try { localStorage.setItem(THEME_STORAGE_KEY, next); } catch { /* private mode */ }
  }
  syncThemeControls();
  return next;
}

function initializeTheme() {
  return applyTheme(storedTheme() || systemTheme());
}

function setTheme(theme) {
  return applyTheme(theme, true);
}

/* Follow a system change only until the person makes an explicit choice. */
try {
  const themeMedia = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)");
  if (themeMedia && themeMedia.addEventListener) {
    themeMedia.addEventListener("change", (event) => {
      if (!storedTheme()) applyTheme(event.matches ? "dark" : "light");
    });
  }
} catch { /* matchMedia is optional */ }

/* ---------------- API client ---------------- */
async function api(path, { method = "GET", body } = {}) {
  const options = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) options.body = JSON.stringify(body);
  const res = await fetch("/api" + path, options);
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON (csv) */ }
  if (!res.ok) {
    const message = (data && data.error) || `Request failed (${res.status})`;
    const error = new Error(message);
    error.status = res.status;
    throw error;
  }
  return data;
}

function toast(message, isErr = false) {
  const box = $("#toast");
  const el = document.createElement("div");
  el.className = "toast" + (isErr ? " err" : "");
  el.textContent = message;
  box.appendChild(el);
  setTimeout(() => el.remove(), 3800);
}

/* ---------------- modal ---------------- */
let backdropHandler = null;
function openModal(html) {
  const root = $("#modal-root");
  root.innerHTML = `<div class="modal">${html}</div>`;
  root.classList.add("open");
  if (backdropHandler) root.removeEventListener("click", backdropHandler);
  backdropHandler = (e) => { if (e.target.id === "modal-root") closeModal(); };
  root.addEventListener("click", backdropHandler);
  $$(".modal [data-close]", root).forEach((b) => b.addEventListener("click", closeModal));
  return root;
}
function closeModal() {
  const root = $("#modal-root");
  root.classList.remove("open");
  root.innerHTML = "";
  if (backdropHandler) { root.removeEventListener("click", backdropHandler); backdropHandler = null; }
}
function confirmModal(title, message, confirmLabel = "Confirm", danger = true) {
  return new Promise((resolve) => {
    openModal(`
      <h3>${esc(title)}</h3>
      <p class="muted mt8">${esc(message)}</p>
      <div class="row mt20" style="justify-content:flex-end">
        <button class="btn btn-ghost" id="modal-cancel">Cancel</button>
        <button class="btn ${danger ? "btn-danger" : "btn-primary"}" id="modal-ok">${esc(confirmLabel)}</button>
      </div>`);
    $("#modal-ok").addEventListener("click", () => { closeModal(); resolve(true); });
    $("#modal-cancel").addEventListener("click", () => { closeModal(); resolve(false); });
  });
}

/* ---------------- units (metric / imperial display) ---------------- */
const UNITS = {
  weight: (kg, units) => units === "imperial" ? `${fmt(kg * 2.20462, 1)} lb` : `${fmt(kg, 1)} kg`,
  height: (cm, units) => {
    if (units !== "imperial") return `${fmt(cm, 0)} cm`;
    const inches = cm / 2.54;
    return `${Math.floor(inches / 12)}'${Math.round(inches % 12)}"`;
  },
  water: (ml, units) => units === "imperial" ? `${fmt(ml / 29.5735, 1)} oz` : `${fmt(ml)} ml`,
};

/* ---------------- async button states (loading / success / error) ---------------- */
async function withBusy(btn, fn, successMessage) {
  if (!btn) return fn();
  const original = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = "Working…";
  try {
    const result = await fn();
    if (successMessage) toast(successMessage);
    return result;
  } finally {
    btn.disabled = false;
    btn.innerHTML = original;
  }
}

/* ---------------- shared SVG icons ---------------- */
const ICONS = {
  dashboard: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="8" height="18" rx="2"/><rect x="13" y="3" width="8" height="8" rx="2"/><rect x="13" y="13" width="8" height="8" rx="2"/></svg>',
  tracker: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 11l18-8-8 18-2-8-8-2z"/></svg>',
  profile: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>',
  assistant: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 012-2h4a2 2 0 012 2v2M12 11v5M9.5 13.5h5"/></svg>',
  reports: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"/><path d="M7 14l4-4 3 3 5-6"/></svg>',
  settings: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 11-4 0v-.09a1.65 1.65 0 00-1-1.51 1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 110-4h.09a1.65 1.65 0 001.51-1 1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06a1.65 1.65 0 001.82.33h0a1.65 1.65 0 001-1.51V3a2 2 0 114 0v.09a1.65 1.65 0 001 1.51h0a1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82v0a1.65 1.65 0 001.51 1H21a2 2 0 110 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>',
  scanner: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 8a2 2 0 012-2h2l1.5-2h7L17 6h2a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><circle cx="12" cy="13" r="3.2"/></svg>',
  upload: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 16V3M7 8l5-5 5 5M5 14v5a2 2 0 002 2h10a2 2 0 002-2v-5"/></svg>',
  meal: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 13h16l-1 4a3 3 0 01-3 2H8a3 3 0 01-3-2z"/><path d="M7 13a5 5 0 0110 0M9 8V5M12 8V3M15 8V5"/></svg>',
  leaf: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M20 4C11 4 5 8.5 5 15a5 5 0 005 5c6.5 0 10-6 10-16z"/><path d="M4 20c4-5 8-8 13-11"/></svg>',
  user: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0116 0"/></svg>',
  capsule: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7.5 4.5a4.5 4.5 0 016.4 0l5.6 5.6a4.5 4.5 0 01-6.4 6.4l-5.6-5.6a4.5 4.5 0 010-6.4z"/><path d="M8 16l8-8"/></svg>',
  calendar: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18"/></svg>',
  phone: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 16.9v3a2 2 0 01-2.2 2A19.8 19.8 0 012 4.2 2 2 0 014 2h3a2 2 0 012 1.7l.5 2.6a2 2 0 01-.6 1.8l-1.8 1.8a16 16 0 006 6l1.8-1.8a2 2 0 011.8-.6l2.6.5A2 2 0 0122 16.9z"/></svg>',
  drop: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2.7l5.7 5.7a8 8 0 11-11.4 0z"/></svg>',
  plus: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M12 5v14M5 12h14"/></svg>',
  edit: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.8 2.8 0 114 4L7.5 20.5 2 22l1.5-5.5z"/></svg>',
  trash: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/></svg>',
  cup: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 2h12l-2 20H8z"/><path d="M7 10h10"/></svg>',
  search: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>',
  shield: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
  alert: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z"/><path d="M12 9v4M12 17h.01"/></svg>',
  download: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>',
  sun: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>',
  moon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12.8A8.5 8.5 0 1111.2 3 6.7 6.7 0 0021 12.8z"/></svg>',
};
