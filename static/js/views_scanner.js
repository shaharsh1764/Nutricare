/* AI Food Scanner view — camera capture, upload, prediction, portion editing,
   and logging into the EXISTING meal log.

   Honesty rules enforced in this file:
   - There is no client-side "pretend" prediction. If the server reports
     model_unavailable, the UI says photo recognition is switched off and
     offers manual logging instead.
   - Confidence is always shown. Below the server-provided threshold the result
     is presented as "not sure" and the user is asked to pick the food
     themselves rather than being handed a confident-looking guess.
   - Nutrition numbers displayed always come from the server (dataset values
     scaled by the portion the user chose). Nothing is invented here.
   - The photo itself is sent once for analysis and never stored by the app.
*/
"use strict";

const SCAN = {
  file: null,
  previewUrl: null,
  result: null,
  slug: null,
  grams: null,
  meal: null,
  stream: null,
  candidates: [],
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
function scanReset() {
  if (SCAN.previewUrl) { try { URL.revokeObjectURL(SCAN.previewUrl); } catch { /* noop */ } }
  scanStopCamera();
  SCAN.file = null; SCAN.previewUrl = null; SCAN.result = null;
  SCAN.slug = null; SCAN.grams = null; SCAN.candidates = []; SCAN.manualValues = {};
}

function scanStopCamera() {
  if (SCAN.stream) {
    SCAN.stream.getTracks().forEach((t) => t.stop());
    SCAN.stream = null;
  }
  const video = $("#scan-video");
  if (video) { try { video.pause(); } catch { /* noop */ } }
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
  scanShowPreview(sourceLabel || "Selected photo");
}

function scanShowPreview(label) {
  const box = $("#scan-drop");
  if (!box) return;
  box.innerHTML = `
    <img class="scan-preview" src="${SCAN.previewUrl}" alt="Selected meal photo">
    <div class="scan-preview-meta">
      <span class="pill pill-teal">${esc(label || "photo")}</span>
      <span class="tiny muted">${esc(SCAN.file.name || "camera capture")} · ${fmt(SCAN.file.size / 1024)} KB</span>
    </div>
    <div class="row wrap mt12" style="justify-content:center">
      <button class="btn btn-primary" id="scan-analyze">${ICONS.search} Analyze meal</button>
      <button class="btn btn-ghost btn-sm" id="scan-change">Change image</button>
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
    <p class="tiny muted mt8">The photo is analysed on this server and is not stored.
    If your browser blocks the camera, use “Upload image” instead.</p>
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
    msg.innerHTML = "<b>Camera not supported in this browser.</b> Use “Upload image” instead.";
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
        : `Camera could not be started (${esc(err && err.name || "unknown error")}). Upload a photo instead.`;
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
  box.innerHTML = `
    <div class="scan-busy">
      <div class="scan-spinner" aria-hidden="true"></div>
      <b>Analyzing your meal…</b>
      <p class="tiny muted mt8">Running the food-recognition model on your photo.</p>
    </div>`;
  const form = new FormData();
  form.append("image", SCAN.file);
  let res;
  try {
    /* The server uses its fixed 80-class-primary recognition policy. */
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
      <div class="empty-state">
        <span style="font-size:28px">🔌</span>
        <b>Photo recognition is not available right now.</b>
        <p class="tiny muted mt8">${esc((data && data.error) || "No trained model is installed.")}</p>
        <p class="tiny muted mt8">NutriCare will not guess a food name. You can still log this
        meal by choosing the food yourself.</p>
        <div class="row mt12" style="justify-content:center">
          <button class="btn btn-deep btn-sm" id="scan-manual">Choose food manually</button>
          <button class="btn btn-ghost btn-sm" id="scan-retry">Try another photo</button>
        </div>
      </div>`;
    const m = $("#scan-manual");
    if (m) m.onclick = () => { closeModal(); openFoodSearchModal(SCAN.meal || "lunch"); };
    const r = $("#scan-retry");
    if (r) r.onclick = () => { scanReset(); renderScanner(); };
    return;
  }
  if (!res.ok) {
    box.innerHTML = `<div class="empty-state"><b>That photo could not be analysed.</b>
      <p class="tiny muted mt8">${esc((data && data.error) || "Unknown error")}</p>
      <button class="btn btn-ghost btn-sm mt12" id="scan-retry">Try another photo</button></div>`;
    const r = $("#scan-retry");
    if (r) r.onclick = () => { scanReset(); renderScanner(); };
    return;
  }

  SCAN.result = data;
  SCAN.candidates = data.candidates || [];
  const top = data.candidates && data.candidates[0];
  if (top) {
    SCAN.slug = top.slug;
    SCAN.grams = (top.nutrition && top.nutrition.grams) || 100;
  }
  scanShowResult();
}

function scanConfidencePill(confidence, low) {
  const pct = Math.round(confidence * 100);
  if (low) return `<span class="pill pill-rose">${pct}% · not sure</span>`;
  if (pct >= 70) return `<span class="pill pill-mint">${pct}% confident</span>`;
  return `<span class="pill pill-amber">${pct}% confident</span>`;
}

/* Nutrition line for an alternative prediction.
   A missing dataset entry must NEVER render as "0 kcal" — that reads as a real
   measurement of zero energy. Genuine zeros (e.g. fat in jalebi's flour) are
   shown as 0; absent data is named as absent. */
function scanAltNutrition(c) {
  const est = c && c.nutrition;
  if (!est || est.nutrition_available === false || !est.nutrients) {
    return `${esc(c.label)} — no documented nutrition; you enter values yourself`;
  }
  // `grams` is top-level on the estimate payload; fall back through the
  // candidate itself for the alternatives list.
  const grams = (est.grams != null) ? est.grams : c.grams;
  return `${fmt(est.nutrients.kcal)} kcal at ${fmt(grams)} g`;
}

function scanShowResult() {
  const box = $("#scan-drop");
  const result = SCAN.result;
  const top = SCAN.candidates[0];
  const low = result.low_confidence;
  const alternatives = SCAN.candidates.slice(1).map((c) => `
    <button class="result-row" data-alt="${c.slug}" style="width:100%;text-align:left">
      <span style="flex:1"><b class="small">${esc(c.label)}</b>
        <div class="tiny muted">${scanAltNutrition(c)}</div></span>
      <span class="pill pill-slate">${Math.round(c.confidence * 100)}%</span>
    </button>`).join("");

  box.innerHTML = `
    <div class="row spread wrap" style="align-items:flex-start">
      <div style="display:flex;gap:12px;align-items:flex-start">
        <img class="scan-thumb" src="${SCAN.previewUrl}" alt="Your meal">
        <div>
          <div class="tiny muted">${low ? "Best guess — low confidence" : "Food identified"}</div>
          <h3 style="font-size:20px;margin-top:2px">${esc(top.label)}</h3>
          <div class="row mt8" style="gap:6px">
            ${scanConfidencePill(top.confidence, low)}
            <span class="pill pill-slate">${esc(SCAN_GROUPS[top.group] || top.group)}</span>
          </div>
        </div>
      </div>
      <button class="btn btn-ghost btn-sm" id="scan-change">Change image</button>
    </div>

    ${low ? `<div class="scan-warn mt12">
        <b>The model is not confident about this photo.</b>
        <p class="tiny mt8">Below ${Math.round(result.threshold * 100)}% confidence NutriCare
        will not claim to know the food. Please pick the right dish below, or enter it manually.</p>
      </div>` : ""}

    ${alternatives ? `<div class="mt16">
      <span class="label">Other possible predictions</span>
      <div class="scan-alts">${alternatives}</div>
      <p class="tiny faint mt8">Wrong food? Tap another suggestion to use its nutrition instead.</p>
    </div>` : ""}

    <div class="mt16" id="scan-nutrition"></div>

    <div class="row wrap mt16" style="justify-content:space-between">
      <button class="btn btn-ghost btn-sm" id="scan-pick">Use a different food</button>
      <div class="row">
        <button class="btn btn-ghost" id="scan-remove">Remove</button>
        <button class="btn btn-primary" id="scan-log">${ICONS.plus} Add to meal log</button>
      </div>
    </div>`;

  if ($("#scan-change")) $("#scan-change").onclick = () => $("#scan-file").click();
  if ($("#scan-remove")) $("#scan-remove").onclick = () => { scanReset(); renderScanner(); };
  $("#scan-pick").onclick = () => openVisionPicker();
  $("#scan-log").onclick = scanAskMeal;
  $$("[data-alt]").forEach((b) => b.onclick = () => {
    SCAN.slug = b.dataset.alt;
    const picked = SCAN.candidates.find((c) => c.slug === b.dataset.alt);
    SCAN.grams = (picked.nutrition && picked.nutrition.grams) || SCAN.grams;
    scanShowResult();
  });
  scanRenderNutrition();
}

/* Portion editor + nutrient table. All numbers come from /api/vision/estimate. */
async function scanRenderNutrition() {
  const host = $("#scan-nutrition");
  if (!host || !SCAN.slug) return;
  host.innerHTML = `<p class="muted small">Calculating nutrition…</p>`;
  let est;
  try {
    est = await api("/vision/estimate", { method: "POST",
      body: { slug: SCAN.slug, grams: SCAN.grams } });
  } catch (e) {
    host.innerHTML = `<div class="empty-state"><b>Nutrition unavailable.</b>
      <p class="tiny muted mt8">${esc(e.message)}</p></div>`;
    return;
  }
  SCAN.grams = est.grams;
  const n = est.nutrients;

  const stepper = `
    <div class="scan-portion">
      <div class="field" style="margin:0">
        <span class="label">Portion weight (grams)</span>
        <div class="row" style="gap:8px">
          <button class="btn btn-ghost btn-sm" data-step="-10" aria-label="decrease">−</button>
          <input class="input" id="scan-grams" type="number" min="1" max="3000" step="5"
                 value="${est.grams}" style="width:110px;text-align:center">
          <button class="btn btn-ghost btn-sm" data-step="10" aria-label="increase">+</button>
          <button class="btn btn-soft btn-sm" data-step="reset">Reset to ${fmt(est.default_grams)} g</button>
        </div>
      </div>
      <p class="tiny faint mt8">${esc(est.portion_note)}</p>
    </div>`;

  if (!est.nutrition_available || !n) {
    host.innerHTML = stepper + `
      <div class="scan-warn mt12">
        <b>No documented nutrition for ${esc(est.label)}.</b>
        <p class="tiny mt8">${esc(est.unavailable_reason || "This food has no dataset entry.")}</p>
        <p class="tiny mt8">You can still log it by entering the values from your own
        packaging or recipe when you add it to the log.</p>
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
    if (step === "reset") { apply(SCAN.result ? SCAN.candidates
      .find((c) => c.slug === SCAN.slug).nutrition.default_grams : 100); return; }
    apply((SCAN.grams || 0) + Number(step));
  });
}

/* Pick a different food from the full class list (the "model was wrong" path). */
function openVisionPicker() {
  const groups = {};
  const modelInstalled = !!SCAN.coverage.model_installed;
  /* Only offer foods the model can actually recognise. Showing all 65 taxonomy
     entries would imply support the checkpoint does not have. Without a model,
     everything is a manual entry and the full list is legitimate. */
  const all = (SCAN.allClasses || []).filter((c) => !modelInstalled || c.trained);
  all.forEach((c) => { (groups[c.group] = groups[c.group] || []).push(c); });
  openModal(`
    <h3>Which food is this?</h3>
    <p class="tiny muted mt8">Pick the correct dish. Nutrition comes from the same
    documented dataset the manual logger uses.</p>
    <div class="mt12" style="max-height:52vh;overflow:auto">
      ${Object.entries(SCAN_GROUPS).map(([key, label]) => {
        const items = (groups[key] || []).map((c) => `
          <button class="result-row" data-pick="${c.slug}" style="width:100%;text-align:left">
            <span style="flex:1"><b class="small">${esc(c.label)}</b>
              <div class="tiny muted">${c.nutrition_available
                ? "nutrition available" : "no dataset entry — enter values yourself"}</div></span>
            ${c.nutrition_available ? '<span class="pill pill-teal">select</span>'
              : '<span class="pill pill-amber">manual</span>'}
          </button>`).join("");
        return items ? `<div class="mt12"><span class="label">${esc(label)}</span>${items}</div>` : "";
      }).join("")}
    </div>
    <div class="row mt16" style="justify-content:flex-end">
      <button class="btn btn-ghost" data-close>Cancel</button></div>`);
  $$("[data-pick]").forEach((b) => b.onclick = async () => {
    const slug = b.dataset.pick;
    const cls = (SCAN.allClasses || []).find((c) => c.slug === slug);
    SCAN.slug = slug;
    SCAN.grams = (cls && cls.default_grams) || 100;
    SCAN.candidates = [{ slug, label: cls ? cls.label : slug, group: cls ? cls.group : "",
      confidence: 0, confidence_pct: 0 }];
    closeModal();
    scanShowResult();
  });
}

/* ---------------------------------------------------------------- meal + save */
function scanAskMeal() {
  openModal(`
    <h3>When did you have this meal?</h3>
    <p class="tiny muted mt8">Choose a meal category to add it to your food diary.</p>
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
    scanSave();
  });
}

async function scanSave() {
  if (!SCAN.meal) { scanAskMeal(); return; }
  const cls = (SCAN.allClasses || []).find((c) => c.slug === SCAN.slug);
  const needsManual = cls && !cls.nutrition_available;
  const body = {
    slug: SCAN.slug,
    grams: SCAN.grams,
    meal: SCAN.meal,
    date: S.trackerDate || S.boot.today,
  };
  if (needsManual) {
    const values = SCAN.manualValues || {};
    if (values.custom_kcal === undefined) { scanAskManualValues(cls); return; }
    Object.assign(body, values);
  }
  try {
    const res = await api("/vision/log", { method: "POST", body });
    toast(`Added to ${MEAL_META[SCAN.meal].label} · ${fmt(res.totals.kcal)} kcal logged today`);
    const meal = SCAN.meal;
    scanReset();
    toast(`Saved to ${meal === "snacks" ? "Snacks" : MEAL_META[meal].label}`);
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
    <p class="tiny muted mt8">NutriCare has no documented dataset entry for this food, so it
    cannot estimate it. Enter the values for the portion (${fmt(SCAN.grams)} g) from your
    packaging, restaurant information or recipe.</p>
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
    await scanSave();
  };
}

/* ---------------------------------------------------------------- view */
async function renderScanner() {
  let status = null;
  try { status = await api("/vision/status"); } catch { /* offline */ }
  /* Recognition uses an 80-class primary and only uses its 12-class model
     after a technical primary failure. */
  const modelReady = !!((status && status.models
    && status.models.some((m) => m.present))
    || (status && status.model && status.model.model_present));
  if (!SCAN.allClasses) {
    try {
      const coverage = await api("/vision/classes");
      SCAN.allClasses = coverage.classes;
      SCAN.coverage = coverage;
    } catch { SCAN.allClasses = []; SCAN.coverage = {}; }
  }
  if (!SCAN.meal) SCAN.meal = "breakfast";

  const modelInstalled = !!SCAN.coverage.model_installed;
  const trainedCount = SCAN.coverage.trained_count || 0;
  const classesWithNutrition = (SCAN.allClasses || []).filter((c) => c.nutrition_available).length;
  const trainedWithNutrition = (SCAN.allClasses || [])
    .filter((c) => c.trained && c.nutrition_available).length;

  $("#view").innerHTML = `
  <div class="page-head">
    <div><h2>AI Food Scanner</h2>
      <p class="sub">Photograph your meal and let the recognition model identify it.
      Nutrition is then looked up in the same documented food dataset the manual
      logger uses — nothing is invented.</p></div>
    <div class="row">
      <a class="btn btn-ghost btn-sm" href="#/tracker">${ICONS.tracker} Open tracker</a>
    </div>
  </div>

  <div class="grid cols-21" style="align-items:start">
    <div class="card">
      <div class="card-head">
        <span class="card-title">Scan your meal</span>
        <span class="pill ${modelReady ? "pill-mint" : "pill-amber"}">
          ${modelReady ? "model installed" : "recognition off"}</span>
      </div>

      <p class="tiny faint mt12">NutriCare uses its 80-class Indian food recognition model by default.
      The older 12-class model is used only if the primary model encounters a technical
      error. Predictions are suggestions and should be confirmed before logging.</p>

      <div class="row wrap" style="gap:10px">
        <button class="btn btn-deep" id="scan-camera">📷 Take Photo</button>
        <button class="btn btn-ghost" id="scan-upload">⬆ Upload Image</button>
        <input type="file" id="scan-file" accept="image/jpeg,image/png,image/webp"
               capture="environment" hidden>
      </div>
      <p class="tiny muted mt8">JPG, PNG or WebP · up to 8 MB. Your photo is analysed on
      this server and is never stored or sent to a third party.</p>

      <div id="scan-drop" class="scan-drop mt16">
        <div class="empty-state">
          <span style="font-size:30px">🍱</span>
          <b>No photo yet</b>
          <p class="tiny muted mt8">Take a photo of your plate or upload one you already have.</p>
        </div>
      </div>

      ${modelReady ? "" : `
      <div class="scan-warn mt16">
        <b>Photo recognition is switched off on this installation.</b>
        <p class="tiny mt8">${esc((status && status.model && status.model.detail) || "")}</p>
        <p class="tiny mt8">This is deliberate: NutriCare will not guess a food name.
        Everything else — searching, portion entry and logging — works now.
        See <code>docs/MODEL.md</code> to install a trained model.</p>
      </div>`}
    </div>

    <div class="grid" style="gap:16px">
      <div class="card">
        <div class="card-head"><span class="card-title">How it works</span></div>
        <div class="how-step"><b>1.</b> Take or upload a photo of one dish.</div>
        <div class="how-step"><b>2.</b> The model ranks the most likely foods.</div>
        <div class="how-step"><b>3.</b> Adjust the portion in grams.</div>
        <div class="how-step"><b>4.</b> Pick Breakfast, Lunch, Snacks or Dinner.</div>
        <div class="how-step"><b>5.</b> It appears in your tracker and dashboard.</div>
      </div>
      <div class="card">
        <div class="card-head"><span class="card-title">Coverage</span>
          <span class="pill pill-slate">${modelInstalled
            ? trainedCount + " recognisable"
            : (SCAN.allClasses || []).length + " foods"}</span></div>
        <p class="small muted">${modelInstalled
          ? `The installed model recognises <b>${trainedCount}</b> foods; nutrition is documented for ${trainedWithNutrition} of them, and for the rest you enter values yourself.`
          : `${classesWithNutrition} of ${(SCAN.allClasses || []).length} foods in the taxonomy have documented nutrition. No model is installed, so nothing is auto-recognised.`}</p>
        <p class="tiny faint mt8">${esc((status && status.single_label_note) || "")}</p>
      </div>
    </div>
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
