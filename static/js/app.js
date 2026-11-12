/* NutriCare shell: router, sidebar (collapsible + mobile drawer), topbar,
   banners, local-user switcher, bootstrap with refresh-safe re-attach.

   Identity reminder (shown in the UI): local profiles + session cookie only.
   The localStorage uid is a convenience so a refresh restores the same local
   profile; it is NOT authentication and NOT security. */
"use strict";

const S = { boot: null, trackerDate: null, reportDays: 7, lastMeal: "breakfast",
  shellBuilt: false, onboardingActive: false };
const LS_UID = "nutricare_uid";
const LS_SIDE = "nutricare_side";

const ROUTES = {
  dashboard: { title: "Dashboard", render: renderDashboard },
  tracker: { title: "Nutrition Tracker", render: renderTracker },
  /* The scanner is reachable from the Dashboard ("Scan a Meal"), not from the
     sidebar. `nav: false` keeps the route (so #/scanner still works) while
     omitting it from the navigation list. */
  scanner: { title: "AI Food Scanner", render: renderScanner, nav: false },
  profile: { title: "My Profile", render: renderProfile },
  assistant: { title: "Health Assistant", render: renderAssistant },
  reports: { title: "Reports", render: renderReports },
  settings: { title: "Settings", render: renderSettings },
};

const lsGet = (k) => { try { return localStorage.getItem(k); } catch { return null; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } };
const lsDel = (k) => { try { localStorage.removeItem(k); } catch { /* ignore */ } };

function currentRoute() {
  const key = (location.hash || "#/dashboard").replace("#/", "").split("?")[0];
  return ROUTES[key] ? key : "dashboard";
}

async function refreshView() {
  if (S.onboardingActive || !S.boot || !S.boot.user) { await renderOnboarding(); return; }
  const key = currentRoute();
  $$(".nav-item").forEach((n) => n.classList.toggle("active", n.dataset.route === key));
  $("#crumb-page").textContent = ROUTES[key].title;
  $("#view").innerHTML = `<div class="card"><p class="muted small">Loading ${ROUTES[key].title}…</p></div>`;
  try {
    await ROUTES[key].render();
  } catch (e) {
    $("#view").innerHTML = `<div class="card"><p style="color:var(--rose)">Failed to load view: ${esc(e.message)}</p>
      <p class="tiny muted mt8">Is the server still running? Try reloading.</p></div>`;
  }
}

function refreshBanners() {
  const demo = $("#demo-banner"), profile = $("#profile-banner");
  if (demo) demo.hidden = !(S.boot && S.boot.demo_mode);
  if (profile) profile.hidden = !(S.boot && S.boot.user && !S.boot.targets);
}

async function refreshSideGoal() {
  const summary = await api(`/summary?date=${S.boot.today}`);
  const t = summary.targets;
  const pct = t ? Math.round(100 * summary.totals.kcal / t.kcal) : 0;
  $("#side-goal").innerHTML = `
    <div class="row spread"><span>Daily Goal</span><b>${t ? pct + "%" : "—"}</b></div>
    <div class="bar mt8"><i style="width:${Math.min(100, pct)}%;background:var(--primary-deep)"></i></div>
    <p class="tiny mt8" style="color:var(--primary-deep)">${t
      ? `${fmt(summary.totals.kcal)} of ${fmt(t.kcal)} kcal recorded`
      : summary.logged_count ? "Recorded intake — target not set" : "Empty log · guest mode ok"}</p>`;
  const name = S.boot.user ? S.boot.user.name : "Guest";
  $("#user-name").textContent = name;
  $("#user-sub").textContent = S.boot.targets ? "local profile"
    : (name === "Guest" ? "guest — add profile anytime" : "profile incomplete");
  $("#avatar-initials").textContent = name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase() || "GU";
}

/* ---------------- shell (built exactly once per page load) ---------------- */
function ensureShell() {
  if (S.shellBuilt) return;
  S.shellBuilt = true;
  $("#nav-links").innerHTML = Object.entries(ROUTES)
    .filter(([, r]) => r.nav !== false).map(([key, r]) => `
    <button class="nav-item" data-route="${key}" aria-label="${r.title}">
      ${ICONS[key]}<span class="nav-text">${r.title}</span></button>`).join("");
  $$(".nav-item").forEach((b) => b.onclick = () => {
    location.hash = "#/" + b.dataset.route;   // navigates only — never collapses the rail
    if (typeof setDrawer === "function") setDrawer(false);  // close drawer (mobile) after choosing
  });
  $("#top-search").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { location.hash = "#/tracker"; setTimeout(() => {
      const input = $("#food-search"); if (input) { input.value = e.target.value; input.oninput(); } }, 250); }
  });
  $("#user-chip").onclick = openUserModal;
  $("#demo-clear").onclick = async () => {
    const ok = await confirmModal("Clear demo data?",
      "Removes the fictional sample day (meals + water) from this profile and turns demo mode off.",
      "Clear demo data");
    if (!ok) return;
    S.boot = await api("/demo/clear", { method: "POST" });
    refreshBanners(); await refreshSideGoal(); await refreshView();
  };
  /* collapsible sidebar (desktop) + drawer (mobile).
     Drawer mode = the ≤860px media query is active: there the panel icon acts
     as the drawer's close control; on desktop it collapses/expands the rail. */
  const drawerMode = () => {
    try { return window.matchMedia("(max-width: 860px)").matches; } catch { return false; }
  };
  const applySide = () => {
    const rail = lsGet(LS_SIDE) === "rail";
    document.body.classList.toggle("side-rail", rail);
    const t = $("#side-toggle");
    if (t && t.setAttribute) {
      const label = rail ? "Expand sidebar" : "Collapse sidebar";
      t.setAttribute("aria-expanded", rail ? "false" : "true");
      t.setAttribute("title", label);
      t.setAttribute("aria-label", label);
    }
  };
  const setDrawer = (open) => {
    document.body.classList.toggle("side-open", open);
    const m = $("#menu-btn");
    if (m && m.setAttribute) m.setAttribute("aria-expanded", open ? "true" : "false");
  };
  $("#side-toggle").onclick = () => {
    if (drawerMode()) { setDrawer(false); return; }
    if (document.body.classList.contains("side-rail")) lsDel(LS_SIDE); else lsSet(LS_SIDE, "rail");
    applySide();
  };
  $("#menu-btn").onclick = () => setDrawer(!document.body.classList.contains("side-open"));
  $("#side-scrim").onclick = () => setDrawer(false);
  window.addEventListener("keydown", (e) => { if (e.key === "Escape") setDrawer(false); });
  /* crossing the breakpoint while the drawer is open must not leave a stuck state */
  try {
    window.matchMedia("(max-width: 860px)").addEventListener("change", (e) => {
      if (!e.matches) setDrawer(false);
    });
  } catch { /* older browsers: harmless */ }
  applySide();
  window.addEventListener("hashchange", refreshView);
}

/* ---------------- local user switcher (no auth — labelled honestly) ---------------- */
async function openUserModal() {
  const data = await api("/users");
  openModal(`
    <h3>Local profiles</h3>
    <p class="tiny muted mt8">${esc(data.note)}</p>
    <div class="grid mt12" style="gap:8px">
      ${data.users.map((u) => `<div class="row spread selfcare-card">
        <span class="small"><b>${esc(u.name)}</b> ${u.id === data.current ? '<span class="pill pill-teal">current</span>' : ""}</span>
        ${u.id !== data.current ? `<button class="btn btn-soft btn-sm" data-switch="${u.id}">Switch</button>` : ""}
      </div>`).join("") || `<p class="small muted">No profiles yet.</p>`}
    </div>
    <div class="selfcare-card mt16">
      <b class="small">Add another local profile</b>
      <p class="tiny muted mt8">Use the same guided setup as a first-time profile. It saves a separate profile and never changes this one.</p>
      <button class="btn btn-primary btn-sm mt8" id="u-create">Start profile setup</button>
    </div>
    <div class="row mt16" style="justify-content:space-between">
      <button class="btn btn-danger-soft btn-sm" id="u-delete">Delete current profile…</button>
      <button class="btn btn-ghost" data-close>Close</button>
    </div>`);
  $$("[data-switch]").forEach((b) => b.onclick = async () => {
    S.boot = await api("/users/switch", { method: "POST", body: { id: Number(b.dataset.switch) } });
    lsSet(LS_UID, String(S.boot.user.id));
    closeModal(); await afterUserChange();
  });
  $("#u-create").onclick = async () => {
    /* New local accounts deliberately use the original first-launch wizard.
       It performs the single user creation before writing the new session's
       profile/settings, so no current profile can be overwritten. */
    closeModal();
    obResetState();
    S.onboardingActive = true;
    document.body.classList.add("no-shell");
    await renderOnboarding();
  };
  $("#u-delete").onclick = async () => {
    const ok = await confirmModal("Delete this local profile?",
      "All meals, water logs, symptom checks and profile details for the current profile are permanently removed. Other profiles are untouched.",
      "Delete profile");
    if (!ok) return;
    await api(`/users/${S.boot.user.id}`, { method: "DELETE" });
    lsDel(LS_UID);
    S.boot = await api("/bootstrap");
    closeModal();
    if (!S.boot.user) { document.body.classList.add("no-shell"); S.shellBuilt = false; await renderOnboarding(); }
    else await afterUserChange();
  };
}

async function afterUserChange() {
  S.onboardingActive = false;
  document.body.classList.remove("no-shell");
  ensureShell();
  refreshBanners();
  await refreshSideGoal();
  await refreshView();
}

async function enterAppFresh() {
  S.boot = await api("/bootstrap");
  if (S.boot.user) lsSet(LS_UID, String(S.boot.user.id));
  S.trackerDate = S.boot.today;
  await afterUserChange();
}

/* ---------------- boot: restore session, re-attach remembered profile ---------------- */
async function boot() {
  initializeTheme();
  S.boot = await api("/bootstrap");
  if (!S.boot.user) {
    // Refresh-safe recovery: re-attach the last local profile used in this
    // browser (documented convenience, not authentication).
    const remembered = lsGet(LS_UID);
    if (remembered) {
      try {
        S.boot = await api("/users/switch", { method: "POST", body: { id: Number(remembered) } });
      } catch {
        lsDel(LS_UID);  // profile was deleted elsewhere
      }
    }
  }
  if (!S.boot.user) {
    document.body.classList.add("no-shell");
    await renderOnboarding();
    return;
  }
  lsSet(LS_UID, String(S.boot.user.id));
  S.trackerDate = S.boot.today;
  document.body.classList.remove("no-shell");
  ensureShell();
  refreshBanners();
  await refreshSideGoal();
  await refreshView();
}

document.addEventListener("DOMContentLoaded", boot);
