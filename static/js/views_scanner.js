/* Food Scanner view — camera capture, upload, suggestion, portion editing,
   and logging into the existing meal log.

   Honesty rules enforced in this file:
   - There is no client-side "pretend" suggestion. If the server cannot return
     a suggestion, the UI offers manual food selection instead.
   - Every food suggestion remains unconfirmed until the person confirms or
     corrects it before nutrition/logging controls appear.
   - Nutrition for suggested foods comes from the server; catalogue corrections
     use only their documented catalogue values, scaled by the chosen portion.
     Nothing is invented here.
   - The photo itself is sent once for analysis and never stored by the app.
*/
"use strict";

const SCAN = {
  file: null,
  previewUrl: null,
  result: null,
  slug: null,
  catalogueFood: null,
  grams: null,
  defaultGrams: null,
  meal: null,
  stream: null,
  candidates: [],
  selection: null,
  confirmed: false,
  manualValues: {},
  coverage: {},
};

const SCAN_GROUPS = {
  indian_staple: "Indian staples",
  indian_breakfast: "Indian breakfast",
  indian_curry: "Indian curries & vegetables",
  indian_rice: "Indian rice dishes",
  indian_snack: "Indian snacks",
  international: "International foods",
};

/* ---------------------------------------------------------------- helpers */
function scanClearSelection() {
  SCAN.slug = null;
  SCAN.catalogueFood = null;
  SCAN.grams = null;
  SCAN.defaultGrams = null;
  SCAN.selection = null;
  SCAN.confirmed = false;
  SCAN.manualValues = {};
}

function scanReset() {
  if (SCAN.previewUrl) { try { URL.revokeObjectURL(SCAN.previewUrl); } catch { /* noop */ } }
  scanStopCamera();
  SCAN.file = null; SCAN.previewUrl = null; SCAN.result = null;
  SCAN.candidates = [];
  scanClearSelection();
}

function scanStopCamera() {
  if (SCAN.stream) {
    SCAN.stream.getTracks().forEach((t) => t.stop());
    SCAN.stream = null;
  }
  const video = $("#scan-video");
  if (video) { try { video.pause(); } catch { /* noop */ } }
}

function scanMarkDropActive(box) {
  if (box && box.classList) box.classList.remove("scan-drop-empty");
}

function scanAccept(file) {
  const ok = ["image/jpeg", "image/png", "image/webp", "image/jpg"];
  if (!ok.includes((file.type || "").toLowerCase())) {
    toast("Please choose a JPG, PNG or WebP image", true);
    return false;
  }
  if (file.size > 8 * 1024 * 1024) {
    toast("Image is larger than 8 MB — choose a smaller photo", true);
    return false;
  }
  return true;
}

function scanSetFile(file, sourceLabel) {
  if (!scanAccept(file)) return;
  scanStopCamera();
  if (SCAN.previewUrl) { try { URL.revokeObjectURL(SCAN.previewUrl); } catch { /* noop */ } }
  SCAN.file = file;
  SCAN.previewUrl = URL.createObjectURL(file);
  SCAN.result = null;
  SCAN.candidates = [];
  scanClearSelection();
  scanShowPreview(sourceLabel || "Selected photo");
}

function scanShowPreview(label) {
  const box = $("#scan-drop");
  if (!box) return;
  scanMarkDropActive(box);
  box.innerHTML = `
    <img class="scan-preview" src="${SCAN.previewUrl}" alt="Selected meal photo">
    <div class="scan-preview-meta">
      <span class="pill pill-teal">${esc(label || "photo")}</span>
      <span class="tiny muted">${esc(SCAN.file.name || "camera capture")} · ${fmt(SCAN.file.size / 1024)} KB</span>
    </div>
    <div class="row wrap mt12" style="justify-content:center">
      <button class="btn btn-primary" id="scan-analyze">${ICONS.search} Get food suggestion</button>
      <button class="btn btn-ghost btn-sm" id="scan-change">Choose another photo</button>
      <button class="btn btn-ghost btn-sm" id="scan-retake">Retake photo</button>
      <button class="btn btn-ghost btn-sm" id="scan-remove">Remove</button>
    </div>`;
  $("#scan-analyze").onclick = scanAnalyze;
  $("#scan-change").onclick = () => $("#scan-file").click();
  $("#scan-retake").onclick = scanOpenCamera;
  $("#scan-remove").onclick = () => { scanReset(); renderScanner(); };
}

/* ---------------------------------------------------------------- camera */
async function scanOpenCamera() {
  openModal(`
    <h3>Take a photo of your meal</h3>
    <p class="tiny muted mt8">Your photo is used to suggest a food and is not stored.
    If your browser blocks the camera, use “Upload a photo” instead.</p>
    <div class="scan-cam-wrap mt12">
      <video id="scan-video" class="scan-video" autoplay playsinline muted></video>
      <p class="tiny muted" id="scan-cam-msg">Requesting camera permission…</p>
    </div>
    <div class="row mt16" style="justify-content:flex-end">
      <button class="btn btn-ghost" data-close>Cancel</button>
      <button class="btn btn-primary" id="scan-shutter" disabled>📸 Capture</button>
    </div>`);

  const video = $("#scan-video");
  const msg = $("#scan-cam-msg");
  const shutter = $("#scan-shutter");
  const closeBtn = document.querySelector(".modal [data-close]");
  if (closeBtn) closeBtn.addEventListener("click", scanStopCamera);

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    msg.innerHTML = "<b>Camera is not supported in this browser.</b> Use “Upload a photo” instead.";
    return;
  }
  try {
    SCAN.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 } },
      audio: false,
    });
    video.srcObject = SCAN.stream;
    await video.play().catch(() => {});
    msg.textContent = "Frame the whole plate, then tap Capture.";
    shutter.disabled = false;
  } catch (err) {
    const reason = err && err.name === "NotAllowedError"
      ? "Camera permission was denied. You can allow it in your browser settings, or upload a photo instead."
      : err && err.name === "NotFoundError"
        ? "No camera was found on this device. Upload a photo instead."
        : "Camera could not be started. Upload a photo instead.";
    msg.innerHTML = `<b>${reason}</b>`;
  }

  shutter.onclick = () => {
    const w = video.videoWidth, h = video.videoHeight;
    if (!w || !h) { toast("Camera is not ready yet", true); return; }
    const canvas = document.createElement("canvas");
    canvas.width = w; canvas.height = h;
    canvas.getContext("2d").drawImage(video, 0, 0, w, h);
    canvas.toBlob((blob) => {
      if (!blob) { toast("Could not capture the photo", true); return; }
      const file = new File([blob], `meal-${Date.now()}.jpg`, { type: "image/jpeg" });
      scanStopCamera();
      closeModal();
      scanSetFile(file, "camera photo");
    }, "image/jpeg", 0.9);
  };
}

/* ---------------------------------------------------------------- analyze */
async function scanAnalyze() {
  if (!SCAN.file) return;
  const box = $("#scan-drop");
  scanMarkDropActive(box);
  box.innerHTML = `
    <div class="scan-busy" role="status" aria-live="polite">
      <div class="scan-spinner" aria-hidden="true"></div>
      <b>Looking at your meal…</b>
      <p class="tiny muted mt8">We’ll suggest a food for you to check.</p>
    </div>`;
  const form = new FormData();
  form.append("image", SCAN.file);
  let res;
  try {
    /* The server retains its fixed primary/fallback recognition policy. */
    res = await fetch("/api/vision/predict?top_k=3", { method: "POST", body: form });
  } catch {
    box.innerHTML = `<div class="empty-state"><b>Could not reach the server.</b>
      <p class="tiny muted mt8">Check your connection and try again.</p></div>`;
    return;
  }
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON */ }

  if (res.status === 503) {
    box.innerHTML = `
      <div class="scan-empty">
        <span class="scan-empty-icon" aria-hidden="true">🍽</span>
        <b>We can’t suggest a food from this photo right now.</b>
        <p class="tiny muted mt8">You can still choose a food yourself and add this meal to your tracker.</p>
        <div class="row mt12" style="justify-content:center">
          <button class="btn btn-deep btn-sm" id="scan-manual">Choose food manually</button>
          <button class="btn btn-ghost btn-sm" id="scan-retry">Choose another photo</button>
        </div>
      </div>`;
    const m = $("#scan-manual");
    if (m) m.onclick = () => openFoodSearchModal(
      SCAN.meal || "lunch", null, scanSelectCatalogueFood);
    const r = $("#scan-retry");
    if (r) r.onclick = () => { scanReset(); renderScanner(); };
    return;
  }
  if (!res.ok) {
    box.innerHTML = `<div class="scan-empty"><span class="scan-empty-icon" aria-hidden="true">📷</span>
      <b>We couldn’t use that photo.</b>
      <p class="tiny muted mt8">Try another clear photo of one dish, or choose the food yourself.</p>
      <button class="btn btn-ghost btn-sm mt12" id="scan-retry">Choose another photo</button></div>`;
    const r = $("#scan-retry");
    if (r) r.onclick = () => { scanReset(); renderScanner(); };
    return;
  }

  SCAN.result = data;
  SCAN.candidates = data.candidates || [];
  scanClearSelection();
  scanShowResult();
}

/* Nutrition line for an alternative prediction.
   A missing dataset entry must NEVER render as "0 kcal" — that reads as a real
   measurement of zero energy. Genuine zeros (e.g. fat in jalebi's flour) are
   shown as 0; absent data is named as absent. */
function scanAltNutrition(c) {
  const est = c && c.nutrition;
  if (!est || est.nutrition_available === false || !est.nutrients) {
    return `${esc(c.label)} — nutrition information isn't available; you may need to enter it manually`;
  }
  // `grams` is top-level on the estimate payload; fall back through the
  // candidate itself for the alternatives list.
  const grams = (est.grams != null) ? est.grams : c.grams;
  return `${fmt(est.nutrients.kcal)} kcal at ${fmt(grams)} g`;
}

function scanSelectClass(candidate, source) {
  if (!candidate || !candidate.slug) return;
  SCAN.slug = candidate.slug;
  SCAN.catalogueFood = null;
  SCAN.defaultGrams = (candidate.nutrition &&
    (candidate.nutrition.default_grams || candidate.nutrition.grams)) || 100;
  SCAN.grams = SCAN.defaultGrams;
  SCAN.selection = { source, label: candidate.label || candidate.slug };
  SCAN.confirmed = true;
  SCAN.manualValues = {};
  scanShowResult();
}

function scanSelectCatalogueFood(food, selectedGrams = null) {
  if (!food || !food.id) return;
  SCAN.slug = null;
  SCAN.catalogueFood = food;
  SCAN.defaultGrams = Number(food.serving_g) || 100;
  SCAN.grams = Number(selectedGrams) || SCAN.defaultGrams;
  SCAN.selection = { source: "catalogue", label: food.name };
  SCAN.confirmed = true;
  SCAN.manualValues = {};
  scanShowResult();
}

function scanShowResult() {
  if (SCAN.confirmed) {
    scanShowSelectedFood();
  } else {
    scanShowConfirmation();
  }
}

function scanShowConfirmation() {
  const box = $("#scan-drop");
  const result = SCAN.result || {};
  const top = SCAN.candidates[0];
  if (!box || !top) {
    if (box) box.innerHTML = `<div class="empty-state"><b>No food suggestion was returned.</b>
      <button class="btn btn-ghost btn-sm mt12" id="scan-choose-food">Choose food manually</button></div>`;
    const choose = $("#scan-choose-food");
    if (choose) choose.onclick = scanShowAlternatives;
    return;
  }
  const low = result.low_confidence;
  box.innerHTML = `
    <div class="row spread wrap" style="align-items:flex-start">
      <div style="display:flex;gap:12px;align-items:flex-start">
        <img class="scan-thumb" src="${SCAN.previewUrl}" alt="Your meal">
        <div>
          <div class="tiny muted">Suggested food</div>
          <h3 style="font-size:20px;margin-top:2px">${esc(top.label)}</h3>
          ${top.group ? `<div class="row mt8" style="gap:6px">
            <span class="pill pill-slate">${esc(SCAN_GROUPS[top.group] || top.group)}</span>
          </div>` : ""}
        </div>
      </div>
      <button class="btn btn-ghost btn-sm" id="scan-change">Change image</button>
    </div>
    <div class="scan-warn mt16">
      <b>Is this the correct food?</b>
      <p class="tiny mt8">Please check the suggestion before using its nutrition information.</p>
      ${low ? `<p class="tiny mt8">This suggestion may not be right, so please double-check it or choose another food.</p>` : ""}
      <div class="row wrap mt12">
        <button class="btn btn-primary" id="scan-confirm-yes">Yes, correct</button>
        <button class="btn btn-ghost" id="scan-confirm-no">No, choose another food</button>
      </div>
    </div>`;
  $("#scan-change").onclick = () => $("#scan-file").click();
  $("#scan-confirm-yes").onclick = () => scanSelectClass(top, "prediction");
  $("#scan-confirm-no").onclick = scanShowAlternatives;
}

function scanShowAlternatives() {
  const box = $("#scan-drop");
  if (!box) return;
  const alternatives = SCAN.candidates.slice(1);
  box.innerHTML = `
    <div class="row spread wrap" style="align-items:flex-start">
      <div><div class="tiny muted">Choose the correct food</div>
        <h3 style="font-size:20px;margin-top:2px">Other suggestions</h3></div>
      <button class="btn btn-ghost btn-sm" id="scan-back-confirm">Back to suggestion</button>
    </div>
    <p class="tiny muted mt8">Choose another suggestion below, or search the food catalogue.</p>
    ${alternatives.length ? `<div class="scan-alts mt12">${alternatives.map((c) => `
      <button class="result-row" data-scan-alternative="${esc(c.slug)}" style="width:100%;text-align:left">
        <span style="flex:1"><b class="small">${esc(c.label)}</b>
          <div class="tiny muted">${scanAltNutrition(c)}</div></span>
      </button>`).join("")}</div>` : `<div class="empty mt12">No other suggestions were returned.</div>`}
    <div class="row wrap mt16">
      <button class="btn btn-deep" id="scan-search-catalogue">${ICONS.search} Search food catalogue</button>
      <button class="btn btn-ghost" id="scan-change">Choose another photo</button>
    </div>`;
  $("#scan-back-confirm").onclick = scanShowConfirmation;
  $("#scan-change").onclick = () => $("#scan-file").click();
  $("#scan-search-catalogue").onclick = () => openFoodSearchModal(
    SCAN.meal || "breakfast", null, scanSelectCatalogueFood);
  $$("[data-scan-alternative]").forEach((button) => {
    button.onclick = () => scanSelectClass(
      SCAN.candidates.find((candidate) => candidate.slug === button.dataset.scanAlternative),
      "alternative");
  });
}

function scanShowSelectedFood() {
  const box = $("#scan-drop");
  if (!box || !SCAN.confirmed) return;
  const candidate = SCAN.candidates.find((item) => item.slug === SCAN.slug);
  const isCatalogueFood = !!SCAN.catalogueFood;
  const label = isCatalogueFood ? SCAN.catalogueFood.name
    : (candidate && candidate.label) || SCAN.slug;
  const group = isCatalogueFood ? SCAN.catalogueFood.grp
    : (candidate && candidate.group);
  const source = SCAN.selection && SCAN.selection.source === "prediction"
    ? "You confirmed this suggestion"
    : (SCAN.selection && SCAN.selection.source === "alternative"
      ? "You chose another suggestion"
      : "You selected this food from the catalogue");
  box.innerHTML = `
    <div class="row spread wrap" style="align-items:flex-start">
      <div style="display:flex;gap:12px;align-items:flex-start">
        <img class="scan-thumb" src="${SCAN.previewUrl}" alt="Your meal">
        <div>
          <div class="tiny muted">${esc(source)}</div>
          <h3 style="font-size:20px;margin-top:2px">${esc(label)}</h3>
          ${group ? `<div class="row mt8" style="gap:6px">
            <span class="pill pill-slate">${esc(SCAN_GROUPS[group] || group)}</span>
          </div>` : ""}
        </div>
      </div>
      <button class="btn btn-ghost btn-sm" id="scan-change">Change image</button>
    </div>
    <div class="mt16" id="scan-nutrition"></div>
    <div class="row wrap mt16" style="justify-content:space-between">
      <button class="btn btn-ghost btn-sm" id="scan-pick">Choose a different food</button>
      <div class="row">
        <button class="btn btn-ghost btn-sm" id="scan-remove">Remove</button>
        <button class="btn btn-primary" id="scan-log">${ICONS.plus} Add to meal log</button>
      </div>
    </div>`;
  $("#scan-change").onclick = () => $("#scan-file").click();
  $("#scan-remove").onclick = () => { scanReset(); renderScanner(); };
  $("#scan-pick").onclick = scanShowAlternatives;
  $("#scan-log").onclick = scanAskMeal;
  scanRenderNutrition();
}

/* Portion editor + nutrient table. Class selections use /vision/estimate;
   catalogue corrections use the documented food record returned by /foods. */
function scanPortionEditor(defaultGrams, note) {
  return `
    <div class="scan-portion">
      <div class="field" style="margin:0">
        <span class="label">Portion weight (grams)</span>
        <div class="row" style="gap:8px">
          <button class="btn btn-ghost btn-sm" data-step="-10" aria-label="decrease">−</button>
          <input class="input" id="scan-grams" type="number" min="1" max="3000" step="5"
                 value="${fmt(SCAN.grams)}" style="width:110px;text-align:center">
          <button class="btn btn-ghost btn-sm" data-step="10" aria-label="increase">+</button>
          <button class="btn btn-soft btn-sm" data-step="reset">Reset to ${fmt(defaultGrams)} g</button>
        </div>
      </div>
      <p class="tiny faint mt8">${esc(note || "Documented portion information.")}</p>
    </div>`;
}

function scanRenderCatalogueNutrition(host) {
  const food = SCAN.catalogueFood;
  if (!food) return;
  const grams = Math.max(1, Math.min(3000, Number(SCAN.grams) || SCAN.defaultGrams || 100));
  SCAN.grams = grams;
  const scale = grams / 100;
  const value = (field) => {
    const raw = food[field];
    return raw === null || raw === undefined || raw === "" ? NaN : Number(raw) * scale;
  };
  const rows = [
    ["Calories", value("kcal"), "kcal", 0],
    ["Protein", value("protein_g"), "g", 1],
    ["Carbohydrates", value("carbs_g"), "g", 1],
    ["Total fat", value("fat_g"), "g", 1],
    ["Dietary fibre", value("fiber_g"), "g", 1],
    ["Calcium", value("calcium_mg"), "mg", 0],
    ["Iron", value("iron_mg"), "mg", 1],
  ].filter(([, amount]) => Number.isFinite(amount)).map(([label, amount, unit, dp]) => `
    <div class="row spread small" style="padding:7px 0;border-bottom:1px solid var(--line)">
      <span class="muted">${label}</span><b>${fmt(amount, dp)} ${unit}</b></div>`).join("");
  host.innerHTML = scanPortionEditor(SCAN.defaultGrams || 100,
    `${food.serving_desc || "Documented serving"} · values scale from the food catalogue.`) + `
    <div class="row spread mt12">
      <span class="card-title">Documented nutrition</span>
      <span class="pill pill-slate">${fmt(grams)} g portion</span>
    </div>
    <div class="mt8">${rows}</div>
    <p class="tiny faint mt8">Source: ${esc(food.source || "documented food catalogue")} · ${esc(food.name)}</p>`;
  bindStepper();
}

async function scanRenderNutrition() {
  const host = $("#scan-nutrition");
  if (!host || (!SCAN.slug && !SCAN.catalogueFood)) return;
  if (SCAN.catalogueFood) { scanRenderCatalogueNutrition(host); return; }
  host.innerHTML = `<p class="muted small">Calculating nutrition…</p>`;
  let est;
  try {
    est = await api("/vision/estimate", { method: "POST",
      body: { slug: SCAN.slug, grams: SCAN.grams } });
  } catch {
    host.innerHTML = `<div class="empty-state"><b>Nutrition information is unavailable right now.</b>
      <p class="tiny muted mt8">Try again or choose another food from the catalogue.</p></div>`;
    return;
  }
  SCAN.grams = est.grams;
  SCAN.defaultGrams = est.default_grams || SCAN.defaultGrams || 100;
  const n = est.nutrients;
  const stepper = scanPortionEditor(SCAN.defaultGrams, est.portion_note);

  if (!est.nutrition_available || !n) {
    host.innerHTML = stepper + `
      <div class="scan-warn mt12">
        <b>Nutrition information isn't available for ${esc(est.label)}.</b>
        <p class="tiny mt8">Nutrition information is available for selected foods. If information isn't available for your selection, you may need to enter it manually.</p>
        <p class="tiny mt8">Use the values from your packaging or recipe when you add this food to your tracker.</p>
      </div>`;
    bindStepper();
    return;
  }

  const rows = [
    ["Calories", n.kcal, "kcal", 0],
    ["Protein", n.protein_g, "g", 1],
    ["Carbohydrates", n.carbs_g, "g", 1],
    ["Total fat", n.fat_g, "g", 1],
    ["Dietary fibre", n.fiber_g, "g", 1],
    ["Calcium", n.calcium_mg, "mg", 0],
    ["Iron", n.iron_mg, "mg", 1],
  ].map(([label, value, unit, dp]) => `
    <div class="row spread small" style="padding:7px 0;border-bottom:1px solid var(--line)">
      <span class="muted">${label}</span><b>${fmt(value, dp)} ${unit}</b></div>`).join("");

  host.innerHTML = stepper + `
    <div class="row spread mt12">
      <span class="card-title">Estimated nutrition</span>
      <span class="pill pill-slate">${fmt(est.grams)} g portion</span>
    </div>
    <div class="mt8">${rows}</div>
    ${est.range ? `<p class="tiny muted mt8">Roughly <b>${fmt(est.range.kcal_low)}–${fmt(est.range.kcal_high)} kcal</b>
      (${esc(est.range.explanation)})</p>` : ""}
    ${est.approx_note ? `<div class="scan-warn mt12"><b>Approximation.</b>
      <p class="tiny mt8">${esc(est.approx_note)}</p></div>` : ""}
    <p class="tiny faint mt8">${esc(est.estimate_note)}</p>
    <p class="tiny faint mt4">Source: ${esc(est.food ? est.food.source : "—")} ·
      ${esc(est.food ? est.food.name : "")}</p>`;
  bindStepper();
}

function bindStepper() {
  const input = $("#scan-grams");
  if (!input) return;
  const apply = (value) => {
    const grams = Math.max(1, Math.min(3000, Math.round(value)));
    SCAN.grams = grams;
    scanRenderNutrition();
  };
  input.onchange = () => apply(parseFloat(input.value) || SCAN.grams);
  $$("[data-step]").forEach((b) => b.onclick = () => {
    const step = b.dataset.step;
    if (step === "reset") { apply(SCAN.defaultGrams || 100); return; }
    apply((SCAN.grams || 0) + Number(step));
  });
}

/* ---------------------------------------------------------------- meal + save */
function scanNeedsManualValues() {
  if (!SCAN.slug) return false;
  const cls = (SCAN.allClasses || []).find((c) => c.slug === SCAN.slug);
  return !!(cls && !cls.nutrition_available);
}

function scanSelectedLabel() {
  if (SCAN.catalogueFood) return SCAN.catalogueFood.name;
  const candidate = SCAN.candidates.find((item) => item.slug === SCAN.slug);
  const cls = (SCAN.allClasses || []).find((item) => item.slug === SCAN.slug);
  return (candidate && candidate.label) || (cls && cls.label) || SCAN.slug || "this food";
}

function scanAskMeal() {
  if (!SCAN.confirmed || (!SCAN.slug && !SCAN.catalogueFood)) {
    toast("Confirm or choose a food before adding it to your meal log", true);
    return;
  }
  openModal(`
    <h3>When did you have this meal?</h3>
    <p class="tiny muted mt8">Choose a meal category, then review the completed entry before it is saved.</p>
    <div class="seg mt16">
      ${Object.entries(MEAL_META).map(([key, m]) => `
        <button class="tile tile-btn" data-meal="${key}">
          <span style="font-size:20px">${m.icon}</span>
          <b>${key === "snacks" ? "Snacks" : m.label}</b></button>`).join("")}
    </div>
    <div class="row mt20" style="justify-content:flex-end">
      <button class="btn btn-ghost" data-close>Cancel</button></div>`);
  $$("[data-meal]").forEach((b) => b.onclick = () => {
    SCAN.meal = b.dataset.meal;
    closeModal();
    scanConfirmSave();
  });
}

function scanConfirmSave() {
  if (!SCAN.confirmed || !SCAN.meal || (!SCAN.slug && !SCAN.catalogueFood)) return;
  if (scanNeedsManualValues() && SCAN.manualValues.custom_kcal === undefined) {
    const cls = (SCAN.allClasses || []).find((item) => item.slug === SCAN.slug);
    scanAskManualValues(cls);
    return;
  }
  const category = MEAL_META[SCAN.meal];
  openModal(`
    <h3>Confirm meal entry</h3>
    <p class="tiny muted mt8">Review this completed entry. It will not be added until you confirm.</p>
    <div class="selfcare-card mt12">
      <b>${esc(scanSelectedLabel())}</b>
      <p class="tiny muted mt8">${fmt(SCAN.grams)} g · ${esc(category.label)}</p>
    </div>
    <div class="row mt16" style="justify-content:flex-end">
      <button class="btn btn-ghost" data-close>Back</button>
      <button class="btn btn-primary" id="scan-final-save">Confirm & add to ${esc(category.label)}</button>
    </div>`);
  $("#scan-final-save").onclick = () => scanSave();
}

async function scanSave() {
  if (!SCAN.confirmed || (!SCAN.slug && !SCAN.catalogueFood)) {
    toast("Confirm or choose a food before saving", true);
    return;
  }
  if (!SCAN.meal) { scanAskMeal(); return; }
  const needsManual = scanNeedsManualValues();
  if (needsManual) {
    const values = SCAN.manualValues || {};
    if (values.custom_kcal === undefined) {
      const cls = (SCAN.allClasses || []).find((item) => item.slug === SCAN.slug);
      scanAskManualValues(cls);
      return;
    }
  }
  try {
    let saved;
    if (SCAN.catalogueFood) {
      saved = await api("/meals", { method: "POST", body: {
        date: S.trackerDate || S.boot.today,
        meal: SCAN.meal,
        food_id: SCAN.catalogueFood.id,
        quantity: SCAN.grams,
        unit: "g",
      } });
    } else {
      const body = {
        slug: SCAN.slug,
        grams: SCAN.grams,
        meal: SCAN.meal,
        date: S.trackerDate || S.boot.today,
      };
      if (needsManual) Object.assign(body, SCAN.manualValues);
      saved = await api("/vision/log", { method: "POST", body });
    }
    closeModal();
    const meal = SCAN.meal;
    const kcal = saved && saved.totals ? ` · ${fmt(saved.totals.kcal)} kcal logged today` : "";
    toast(`Saved to ${meal === "snacks" ? "Snacks" : MEAL_META[meal].label}${kcal}`);
    scanReset();
    await refreshSideGoal();
    await refreshView();
  } catch (e) {
    if (e.status === 409) { toast(e.message, true); return; }
    toast(e.message, true);
  }
}

function scanAskManualValues(cls) {
  openModal(`
    <h3>Enter nutrition for ${esc(cls.label)}</h3>
    <p class="tiny muted mt8">Nutrition information isn't available for this food. Enter the values
    for this portion (${fmt(SCAN.grams)} g) from your packaging, restaurant information or recipe.</p>
    <div class="grid cols-2 mt12">
      <div class="field"><span class="label">Calories (kcal) *</span>
        <input class="input" id="scan-kcal" type="number" min="0" step="1" placeholder="e.g. 250"></div>
      <div class="field"><span class="label">Protein (g)</span>
        <input class="input" id="scan-protein" type="number" min="0" step="0.1"></div>
      <div class="field"><span class="label">Carbohydrates (g)</span>
        <input class="input" id="scan-carbs" type="number" min="0" step="0.1"></div>
      <div class="field"><span class="label">Total fat (g)</span>
        <input class="input" id="scan-fat" type="number" min="0" step="0.1"></div>
    </div>
    <div class="row mt16" style="justify-content:flex-end">
      <button class="btn btn-ghost" data-close>Cancel</button>
      <button class="btn btn-primary" id="scan-values-ok">Save values</button></div>`);
  $("#scan-values-ok").onclick = async () => {
    const kcal = parseFloat($("#scan-kcal").value);
    if (!(kcal >= 0)) { toast("Enter at least the calories", true); return; }
    SCAN.manualValues = {
      custom_kcal: kcal,
      custom_protein_g: parseFloat($("#scan-protein").value) || undefined,
      custom_carbs_g: parseFloat($("#scan-carbs").value) || undefined,
      custom_fat_g: parseFloat($("#scan-fat").value) || undefined,
    };
    closeModal();
    scanConfirmSave();
  };
}

/* ---------------------------------------------------------------- view */
async function renderScanner() {
  /* Class metadata is used only to guide the manual-nutrition path after a
     person has chosen a food; it is never presented as model coverage. */
  if (!SCAN.allClasses) {
    try {
      const coverage = await api("/vision/classes");
      SCAN.allClasses = coverage.classes || [];
      SCAN.coverage = coverage;
    } catch { SCAN.allClasses = []; SCAN.coverage = {}; }
  }
  if (!SCAN.meal) SCAN.meal = "breakfast";

  $("#view").innerHTML = `
  <div class="page-head">
    <div><h2>Food Scanner</h2>
      <p class="sub">Take a photo of your meal and discover its nutritional information.</p></div>
    <div class="row">
      <a class="btn btn-ghost btn-sm" href="#/tracker">${ICONS.tracker} Open tracker</a>
    </div>
  </div>

  <div class="grid cols-21 scan-layout" style="align-items:start">
    <section class="card scan-capture-card" aria-labelledby="scan-capture-title">
      <div class="scan-capture-intro">
        <span class="scan-capture-icon" aria-hidden="true">📷</span>
        <div><h3 id="scan-capture-title">Add a meal photo</h3>
          <p class="small muted mt4">Start with one clear photo of one dish.</p></div>
      </div>
      <div class="scan-actions mt16">
        <button class="btn btn-deep" id="scan-camera">📷 Take a photo</button>
        <button class="btn btn-primary" id="scan-upload">⬆ Upload a photo</button>
        <input type="file" id="scan-file" accept="image/jpeg,image/png,image/webp"
               capture="environment" hidden>
      </div>
      <p class="tiny muted mt12">JPG, PNG or WebP · up to 8 MB</p>
      <p class="tiny faint mt4">Your photo is used to suggest a food and is not stored.</p>

      <div id="scan-drop" class="scan-drop scan-drop-empty mt16">
        <div class="scan-empty">
          <span class="scan-empty-icon" aria-hidden="true">🍱</span>
          <h3>Ready when you are</h3>
          <p class="tiny muted mt8">Take a photo of one dish or choose a photo from your device.</p>
        </div>
      </div>
    </section>

    <aside class="grid" style="gap:16px">
      <section class="card" aria-labelledby="scan-how-title">
        <div class="card-head"><span class="card-title" id="scan-how-title">How it works</span></div>
        <div class="how-step"><b>1.</b> Take a photo of one dish.</div>
        <div class="how-step"><b>2.</b> We'll suggest what your food might be.</div>
        <div class="how-step"><b>3.</b> Confirm or correct the suggested food.</div>
        <div class="how-step"><b>4.</b> Enter your portion size.</div>
        <div class="how-step"><b>5.</b> Choose your meal category.</div>
        <div class="how-step"><b>6.</b> Review your nutrition information and add it to your tracker.</div>
      </section>
      <section class="card scan-help-card" aria-labelledby="scan-tips-title">
        <div class="card-head"><span class="card-title" id="scan-tips-title">Helpful tips</span></div>
        <p class="small muted">For the best results, photograph one dish at a time. If your plate contains several different dishes, add them separately.</p>
        <div class="scan-help-divider"></div>
        <p class="small muted">Nutrition information is available for selected foods. If information isn't available for your selection, you may need to enter it manually.</p>
      </section>
    </aside>
  </div>`;

  $("#scan-camera").onclick = scanOpenCamera;
  $("#scan-upload").onclick = () => $("#scan-file").click();
  $("#scan-file").onchange = (e) => {
    const file = e.target.files && e.target.files[0];
    if (file) scanSetFile(file, "uploaded photo");
    e.target.value = "";
  };

  if (SCAN.file && SCAN.previewUrl) {
    if (SCAN.result) scanShowResult();
    else scanShowPreview("selected photo");
  }
}

/* Drag and drop onto the preview area (desktop convenience). */
document.addEventListener("DOMContentLoaded", () => {
  document.addEventListener("dragover", (e) => {
    const drop = $("#scan-drop");
    if (!drop || !drop.contains(e.target)) return;
    e.preventDefault();
  });
  document.addEventListener("drop", (e) => {
    const drop = $("#scan-drop");
    if (!drop || !drop.contains(e.target)) return;
    e.preventDefault();
    const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (file) scanSetFile(file, "dropped photo");
  });
});
