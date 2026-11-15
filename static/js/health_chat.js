/* Persistent local Health Chat launcher and panel.
   The server provides deterministic safety-led replies. This client never
   generates health guidance itself and does not send data to a third party. */
"use strict";

const HEALTH_CHAT = {
  open: false, loading: false, sending: false, messages: [], userId: null,
  draft: "", error: "", selectedPrompt: "", historyMenu: false,
};

// The guided assessment is deliberately local and option based. It sends a
// structured final payload to NutriCare's existing rule-based assessment engine;
// it never calls an LLM or a third-party health service.
const HEALTH_ASSESSMENT = {
  active: false, loading: false, steps: [], index: 0, answers: {}, turns: [],
  emergency: null, result: null, error: null,
};

const ASSESSMENT_SYMPTOMS = [
  { value: "feeling_good", label: "Feeling good" },
  { value: "fatigue", label: "Feeling tired" },
  { value: "headache", label: "Headache" },
  { value: "fever", label: "Fever" },
  { value: "dizziness", label: "Dizziness" },
  { value: "nausea", label: "Nausea" },
  { value: "body_pain", label: "Body pain" },
  { value: "stress_anxiety", label: "Stressed or anxious" },
  { value: "low_mood", label: "Feeling low" },
  { value: "other", label: "Other" },
];

const ASSESSMENT_CONDITIONS = [
  { value: "none", label: "None" },
  { value: "diabetes", label: "Diabetes" },
  { value: "pre_diabetes", label: "Pre-diabetes" },
  { value: "high_cholesterol", label: "High cholesterol" },
  { value: "hypertension", label: "Hypertension" },
  { value: "pcos", label: "PCOS" },
  { value: "thyroid", label: "Thyroid condition" },
  { value: "sleep_problems", label: "Sleep problems" },
  { value: "anxiety_depression", label: "Anxiety or depression" },
  { value: "other", label: "Other" },
];

const DURATION_OPTIONS = [
  { value: "just_started", label: "Just started" },
  { value: "morning", label: "Since this morning" },
  { value: "yesterday", label: "Since yesterday" },
  { value: "two_three_days", label: "2–3 days" },
  { value: "more_three_days", label: "More than 3 days" },
];

const SEVERITY_OPTIONS = [
  { value: "2", label: "1–3: Mild" },
  { value: "5", label: "4–6: Moderate" },
  { value: "8", label: "7–8: Severe" },
  { value: "10", label: "9–10: Extremely severe" },
];

const GLOBAL_SAFETY_OPTIONS = [
  { value: "none", label: "None of these apply" },
  { value: "worst_headache", label: "Sudden, worst-ever headache", warning: "worst_headache" },
  { value: "chest_pain", label: "Chest pain or pressure", warning: "chest_pain" },
  { value: "breathing", label: "Severe breathing difficulty", warning: "breathing" },
  { value: "stroke", label: "Sudden weakness, numbness, facial drooping, or speech difficulty", warning: "stroke" },
  { value: "faint_seizure", label: "Fainting or loss of consciousness", warning: "faint_seizure" },
  { value: "confusion", label: "New confusion or hard to wake", warning: "confusion" },
  { value: "anaphylaxis", label: "Severe allergic reaction or throat/facial swelling", warning: "anaphylaxis" },
  { value: "self_harm", label: "Thoughts of self-harm", warning: "self_harm" },
];

function healthChatIcon(size = 20) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 18.5 3.8 21V6.5A3.5 3.5 0 0 1 7.3 3h9.4a3.5 3.5 0 0 1 3.5 3.5v6.3a3.5 3.5 0 0 1-3.5 3.5H10z"/><path d="M12 7v6M9 10h6"/></svg>`;
}

function healthChatRoot() { return $("#health-chat-root"); }

function syncHealthChatLayout(expanded) {
  // On desktop, the open panel takes a dedicated sidebar column instead of
  // floating across the current page title or controls.
  if (document.body && document.body.classList) {
    document.body.classList.toggle("health-chat-expanded", Boolean(expanded));
  }
}

function hideHealthChat() {
  const root = healthChatRoot();
  if (root) { root.hidden = true; root.innerHTML = ""; }
  HEALTH_CHAT.open = false;
  syncHealthChatLayout(false);
}

function resetHealthChatState(userId) {
  HEALTH_CHAT.userId = userId;
  HEALTH_CHAT.messages = [];
  HEALTH_CHAT.loading = false;
  HEALTH_CHAT.sending = false;
  HEALTH_CHAT.draft = "";
  HEALTH_CHAT.error = "";
  HEALTH_CHAT.selectedPrompt = "";
  HEALTH_CHAT.historyMenu = false;
  HEALTH_CHAT.open = false;
  HEALTH_ASSESSMENT.active = false;
  HEALTH_ASSESSMENT.steps = [];
  HEALTH_ASSESSMENT.answers = {};
  HEALTH_ASSESSMENT.turns = [];
  HEALTH_ASSESSMENT.emergency = null;
  HEALTH_ASSESSMENT.result = null;
  HEALTH_ASSESSMENT.error = null;
}

function ensureHealthChat() {
  const root = healthChatRoot();
  if (!root) return;
  const user = S && S.boot && S.boot.user;
  if (!user || S.onboardingActive) { hideHealthChat(); return; }
  if (HEALTH_CHAT.userId !== user.id) resetHealthChatState(user.id);
  root.hidden = false;
  renderHealthChat();
}

async function openHealthChat() {
  if (!S || !S.boot || !S.boot.user) return;
  HEALTH_CHAT.open = true;
  HEALTH_CHAT.error = "";
  renderHealthChat();
  if (HEALTH_CHAT.messages.length || HEALTH_CHAT.loading || HEALTH_CHAT.sending) {
    const input = $("#health-chat-input");
    if (input && !input.disabled) input.focus();
    return;
  }
  HEALTH_CHAT.loading = true;
  renderHealthChat();
  try {
    const data = await api("/health-chat/history");
    HEALTH_CHAT.messages = data.messages || [];
    if (!HEALTH_CHAT.messages.length) startHealthAssessment();
  } catch (error) {
    HEALTH_CHAT.error = `We could not load this local chat history. ${error.message || "Please try again."}`;
  } finally {
    HEALTH_CHAT.loading = false;
    renderHealthChat();
    const input = $("#health-chat-input");
    if (input && !input.disabled) input.focus();
  }
}

function closeHealthChat() {
  HEALTH_CHAT.open = false;
  renderHealthChat();
}

function healthChatFoodCards(recommendations) {
  if (!recommendations || !recommendations.length) return "";
  return `<section class="health-chat-foods"><b class="tiny">Documented food ideas</b>
    <p class="tiny muted mt4">These are general food options, not treatment. Check what suits you.</p>
    ${recommendations.map((food) => `<button class="health-chat-food" type="button" data-health-chat-food="${food.food_id || ""}">
      <span><b>${esc(food.name)}</b><small>${esc(food.group || "Food catalogue")} · ${esc(food.serving_desc || "documented serving")}</small></span>
      <span class="health-chat-food-action">Log food</span>
    </button>`).join("")}</section>`;
}

function healthChatGuidance(reply) {
  const guidance = reply.guidance || [];
  if (!guidance.length) return "";
  return `<div class="health-chat-guidance">${guidance.map((item) => `<div>
      <b>${esc(item.title)}</b><p>${esc(item.detail)}</p></div>`).join("")}</div>`;
}

function healthChatEmergency(reply) {
  if (reply.triage !== "emergency") return "";
  return `<div class="health-chat-emergency"><b>Emergency warning signs — act now</b>
    ${(reply.red_flags || []).length ? `<ul>${reply.red_flags.map((flag) =>
      `<li><b>${esc(flag.label)}</b> — ${esc(flag.action)}</li>`).join("")}</ul>` : ""}
    ${(reply.emergency_actions || []).map((action) => `<p>${esc(action)}</p>`).join("")}
  </div>`;
}

function healthChatAssistantMessage(entry) {
  const reply = entry.reply || { message: entry.message, triage: entry.triage || "general_guidance" };
  const triageClass = reply.triage === "emergency" ? " emergency"
    : reply.triage === "urgent_same_day" ? " urgent"
      : reply.triage === "pharmacist_handoff" ? " pharmacist" : "";
  return `<article class="health-chat-message assistant${triageClass}">
    <span class="health-chat-avatar" aria-hidden="true">${healthChatIcon(16)}</span>
    <div class="health-chat-bubble">
      <b class="health-chat-speaker">NutriCare Health Chat</b>
      <p>${esc(reply.message || entry.message)}</p>
      ${healthChatEmergency(reply)}
      ${healthChatGuidance(reply)}
      ${healthChatFoodCards(reply.food_recommendations)}
      ${reply.medication_handoff ? `<p class="health-chat-handoff"><b>Medication safety:</b> please speak with a pharmacist or clinician rather than relying on chat advice.</p>` : ""}
      ${reply.disclaimer ? `<p class="health-chat-disclaimer">${esc(reply.disclaimer)}</p>` : ""}
    </div>
  </article>`;
}

function healthChatWelcome() {
  return `<article class="health-chat-message assistant">
    <span class="health-chat-avatar" aria-hidden="true">${healthChatIcon(16)}</span>
    <div class="health-chat-bubble"><b class="health-chat-speaker">NutriCare Health Chat</b>
      <p>Hi! I’m NutriCare Health Chat. What would you like help with?</p>
      <p>I can offer general health and nutrition information, documented food ideas, and identify emergency warning signs. I cannot diagnose conditions or choose medication doses.</p>
      <p class="health-chat-disclaimer">Messages are saved only in this local profile. If you think you may have an emergency, call local emergency services now — India: 112 or ambulance 108.</p>
    </div>
  </article>`;
}

function assessmentStep(id, prompt, options, config = {}) {
  return { id, prompt, options, multiple: false, optional: false, other: true, ...config };
}

function assessmentOptions(values) {
  return values.map(([value, label, warning]) => ({ value, label, ...(warning ? { warning } : {}) }));
}

function startHealthAssessment() {
  HEALTH_ASSESSMENT.active = true;
  HEALTH_ASSESSMENT.loading = false;
  HEALTH_ASSESSMENT.steps = [assessmentStep(
    "symptoms", "Hi! How are you feeling today?", ASSESSMENT_SYMPTOMS,
    { multiple: true, otherLabel: "Describe any other symptom or concern" },
  )];
  HEALTH_ASSESSMENT.index = 0;
  HEALTH_ASSESSMENT.answers = {};
  HEALTH_ASSESSMENT.turns = [];
  HEALTH_ASSESSMENT.emergency = null;
  HEALTH_ASSESSMENT.result = null;
  HEALTH_ASSESSMENT.error = null;
}

function stopHealthAssessment() {
  HEALTH_ASSESSMENT.active = false;
  HEALTH_ASSESSMENT.loading = false;
  HEALTH_ASSESSMENT.error = null;
}

function selectedAssessmentSymptoms() {
  return (HEALTH_ASSESSMENT.answers.symptoms?.values || []).filter((value) => value !== "other");
}

function buildAssessmentSteps(symptoms) {
  const steps = [HEALTH_ASSESSMENT.steps[0]];
  const needsSafetyScreen = symptoms.some((value) => value !== "feeling_good" && value !== "other");
  if (needsSafetyScreen) {
    steps.push(assessmentStep(
      "safety", "Before we continue, do any emergency warning signs apply right now?",
      GLOBAL_SAFETY_OPTIONS, { multiple: true, noneValue: "none", other: true,
        otherLabel: "Anything else that feels urgent or worrying" },
    ));
  }
  if (symptoms.includes("headache")) {
    steps.push(
      assessmentStep("headache_duration", "How long have you had your headache?", DURATION_OPTIONS),
      assessmentStep("headache_severity", "How severe is your headache?", SEVERITY_OPTIONS),
      assessmentStep("headache_location", "Where do you feel the pain?", assessmentOptions([
        ["forehead", "Forehead"], ["temples", "Temples"], ["back", "Back of head"],
        ["one_side", "One side"], ["whole_head", "Whole head"],
      ])),
      assessmentStep("headache_associated", "Are you experiencing any other symptoms with the headache?", assessmentOptions([
        ["nausea", "Nausea"], ["light_sensitivity", "Light sensitivity"], ["neck_stiffness", "Stiff neck"],
        ["vision_speech", "Vision or speech changes", "stroke"], ["none", "None of these"],
      ]), { multiple: true, noneValue: "none" }),
    );
  }
  if (symptoms.includes("fatigue")) {
    steps.push(
      assessmentStep("fatigue_duration", "How long have you been feeling tired?", DURATION_OPTIONS),
      assessmentStep("fatigue_sleep", "How well did you sleep recently?", assessmentOptions([
        ["well", "Well"], ["somewhat", "Not as well as usual"], ["poorly", "Poorly"], ["very_poorly", "Very poorly"],
      ])),
      assessmentStep("fatigue_severity", "How severe is your tiredness?", SEVERITY_OPTIONS),
      assessmentStep("fatigue_associated", "Are you experiencing other symptoms?", assessmentOptions([
        ["fever_chills", "Fever or chills"], ["headache", "Headache"], ["dizziness", "Dizziness"],
        ["short_breath", "Severe breathing difficulty", "breathing"], ["none", "None of these"],
      ]), { multiple: true, noneValue: "none" }),
    );
  }
  if (symptoms.includes("fever")) {
    steps.push(
      assessmentStep("fever_duration", "How long have you had the fever?", DURATION_OPTIONS),
      assessmentStep("fever_temperature", "Have you measured your temperature?", assessmentOptions([
        ["not_measured", "Not measured"], ["under_38", "Below 38°C"], ["38_39_5", "38°C to 39.5°C"], ["above_39_5", "Above 39.5°C"],
      ])),
      assessmentStep("fever_associated", "Do you have chills, cough, body pain, or other symptoms?", assessmentOptions([
        ["chills", "Chills"], ["cough", "Cough"], ["body_pain", "Body pain"],
        ["stiff_neck_rash", "Stiff neck or rash", "fever_neck"], ["none", "None of these"],
      ]), { multiple: true, noneValue: "none" }),
      assessmentStep("fever_fluids", "Are you able to drink fluids?", assessmentOptions([
        ["yes", "Yes, I can drink fluids"], ["some", "Only small amounts"], ["no", "No, I cannot keep fluids down", "no_fluids"],
      ])),
    );
  }
  if (symptoms.includes("dizziness")) {
    steps.push(
      assessmentStep("dizziness_duration", "How long have you been feeling dizzy?", DURATION_OPTIONS),
      assessmentStep("dizziness_severity", "How severe is the dizziness?", SEVERITY_OPTIONS),
      assessmentStep("dizziness_associated", "Have you noticed any of these with the dizziness?", assessmentOptions([
        ["fainting", "Fainting or loss of consciousness", "faint_seizure"], ["chest_pain", "Chest pain or pressure", "chest_pain"],
        ["breathing", "Severe breathing difficulty", "breathing"], ["none", "None of these"],
      ]), { multiple: true, noneValue: "none" }),
    );
  }
  if (symptoms.includes("nausea")) {
    steps.push(
      assessmentStep("nausea_duration", "How long have you been feeling nauseous?", DURATION_OPTIONS),
      assessmentStep("nausea_severity", "How severe is the nausea?", SEVERITY_OPTIONS),
      assessmentStep("nausea_fluids", "Are you able to keep fluids down?", assessmentOptions([
        ["yes", "Yes"], ["some", "Only small amounts"], ["no", "No, I cannot keep fluids down", "no_fluids"],
      ])),
    );
  }
  if (symptoms.includes("body_pain")) {
    steps.push(
      assessmentStep("body_pain_duration", "How long have you had the body pain?", DURATION_OPTIONS),
      assessmentStep("body_pain_severity", "How severe is the body pain?", SEVERITY_OPTIONS),
      assessmentStep("body_pain_location", "Where do you feel the pain most?", assessmentOptions([
        ["muscles", "Muscles"], ["joints", "Joints"], ["all_over", "All over"], ["other_location", "Another area"],
      ])),
    );
  }
  if (symptoms.includes("stress_anxiety") || symptoms.includes("low_mood")) {
    const concern = symptoms.includes("low_mood") ? "low mood" : "stress or anxiety";
    steps.push(
      assessmentStep("wellbeing_duration", `How long have you been feeling ${concern}?`, DURATION_OPTIONS),
      assessmentStep("wellbeing_severity", `How severe does the ${concern} feel right now?`, SEVERITY_OPTIONS),
      assessmentStep("wellbeing_safety", "Do any of these apply right now?", assessmentOptions([
        ["self_harm", "Thoughts of self-harm", "self_harm"], ["none", "None of these apply"],
      ]), { multiple: true, noneValue: "none" }),
    );
  }
  steps.push(
    assessmentStep("conditions", "Do you have any existing medical conditions?", ASSESSMENT_CONDITIONS,
      { multiple: true, optional: true, noneValue: "none", otherLabel: "Describe another condition if you choose" }),
    assessmentStep("review", "Please review your answers before getting local guidance.", [], { review: true, other: false }),
  );
  return steps;
}

function assessmentCurrentStep() { return HEALTH_ASSESSMENT.steps[HEALTH_ASSESSMENT.index]; }

function assessmentAnswer(step) {
  const answer = HEALTH_ASSESSMENT.answers[step.id];
  return answer || { values: [], other: "" };
}

function assessmentOptionLabel(step, value) {
  return (step.options.find((option) => option.value === value) || { label: value }).label;
}

function assessmentAnswerText(step) {
  const answer = assessmentAnswer(step);
  const labels = answer.values.map((value) => assessmentOptionLabel(step, value));
  if (answer.other.trim()) labels.push(answer.other.trim());
  if (!labels.length) return step.optional ? "Skipped" : "Not answered";
  return labels.join("; ");
}

function updateAssessmentSelection(step, value) {
  const answer = assessmentAnswer(step);
  let values = [...answer.values];
  const checked = values.includes(value);
  if (!step.multiple) values = [value];
  else if (step.noneValue === value) values = [value];
  else if (checked) values = values.filter((item) => item !== value);
  else values = [...values.filter((item) => item !== step.noneValue), value];
  if (step.id === "symptoms" && value === "feeling_good") values = ["feeling_good"];
  if (step.id === "symptoms" && value !== "feeling_good") values = values.filter((item) => item !== "feeling_good");
  const clearsOther = step.noneValue === value || (step.id === "symptoms" && value === "feeling_good");
  HEALTH_ASSESSMENT.answers[step.id] = { ...answer, values, other: clearsOther ? "" : answer.other };
  HEALTH_ASSESSMENT.error = null;
  renderHealthChat();
}

function updateAssessmentOther(step, text) {
  const answer = assessmentAnswer(step);
  HEALTH_ASSESSMENT.answers[step.id] = { ...answer, other: text };
}

function assessmentWarningIds() {
  const ids = [];
  for (const step of HEALTH_ASSESSMENT.steps) {
    const answer = assessmentAnswer(step);
    for (const value of answer.values) {
      const option = step.options.find((item) => item.value === value);
      if (option?.warning && !ids.includes(option.warning)) ids.push(option.warning);
    }
  }
  return ids;
}

function assessmentSafetyText() {
  // Submit only what the person selected or typed. Do not send question labels
  // themselves to the emergency screen, because labels such as self-harm are
  // warning-sign phrases rather than user-reported facts.
  return HEALTH_ASSESSMENT.steps.map((step) => {
    if (step.review || !assessmentHasAnswer(step)) return "";
    return assessmentAnswerText(step);
  }).filter(Boolean).join(" | ");
}

function healthAssessmentEmergency() {
  const result = HEALTH_ASSESSMENT.emergency;
  return `<article class="health-chat-message assistant emergency">
    <span class="health-chat-avatar" aria-hidden="true">${healthChatIcon(16)}</span>
    <div class="health-chat-bubble"><b class="health-chat-speaker">NutriCare Health Assistant</b>
      <p>I noticed an emergency warning sign. Stop this assessment and seek immediate medical help.</p>
      ${healthChatEmergency({ triage: "emergency", red_flags: result.red_flags, emergency_actions: result.emergency_actions })}
      <p class="health-chat-disclaimer">${esc(result.disclaimer || "This assistant cannot provide emergency care.")}</p>
    </div>
  </article>`;
}

function healthAssessmentResult() {
  const result = HEALTH_ASSESSMENT.result;
  if (!result) return "";
  const facts = result.reported_facts || {};
  const care = (result.self_care || []).slice(0, 3).map((item) =>
    `<div><b>${esc(item.title)}</b><p>${esc(item.detail)}</p></div>`).join("");
  const seekCare = (result.seek_care || []).slice(0, 4).map((item) => `<li>${esc(item)}</li>`).join("");
  const caution = (result.caution_notes || [])[0] || "";
  return `<article class="health-chat-message assistant ${result.triage === "emergency" ? "emergency" : result.triage === "urgent_same_day" ? "urgent" : ""}">
    <span class="health-chat-avatar" aria-hidden="true">${healthChatIcon(16)}</span>
    <div class="health-chat-bubble"><b class="health-chat-speaker">NutriCare Health Assistant</b>
      <p>Thanks for confirming your answers. Here is general guidance from NutriCare’s local rule-based assessment.</p>
      <div class="health-assessment-summary"><b>Your reported summary</b>
        <p>${esc(facts.primary || "No primary symptom recorded")} · ${esc(facts.duration_label || "duration not recorded")} · severity ${esc(String(facts.severity || "not recorded"))}/10</p>
        ${facts.existing_conditions?.length ? `<p>Reported existing conditions: ${esc(facts.existing_conditions.join(", "))}</p>` : ""}</div>
      ${caution ? `<p class="health-chat-disclaimer">${esc(caution)}</p>` : ""}
      ${result.triage === "emergency" ? healthChatEmergency(result) : ""}
      ${care ? `<div class="health-chat-guidance">${care}</div>` : ""}
      ${seekCare ? `<div class="health-assessment-seek"><b>Seek professional care if:</b><ul>${seekCare}</ul></div>` : ""}
      <p class="health-chat-disclaimer">${esc(result.disclaimer || "")}</p>
    </div>
  </article>`;
}

function healthAssessmentQuestion() {
  const step = assessmentCurrentStep();
  if (!step) return "";
  if (step.review) return healthAssessmentReview();
  const answer = assessmentAnswer(step);
  const position = Math.min(HEALTH_ASSESSMENT.index + 1, HEALTH_ASSESSMENT.steps.length);
  const isSelected = (value) => answer.values.includes(value);
  const choices = step.options.map((option) => `<button class="health-assessment-option" type="button"
      data-assessment-option="${esc(option.value)}" aria-pressed="${isSelected(option.value)}">
      <span class="health-assessment-indicator" aria-hidden="true"></span><span>${esc(option.label)}</span></button>`).join("");
  const otherLabel = step.otherLabel || "Additional information (optional)";
  return `<article class="health-chat-message assistant">
    <span class="health-chat-avatar" aria-hidden="true">${healthChatIcon(16)}</span>
    <div class="health-chat-bubble health-assessment-question"><b class="health-chat-speaker">NutriCare Health Assistant</b>
      <div class="health-assessment-progress"><span>Step ${position} of ${HEALTH_ASSESSMENT.steps.length}</span><i style="width:${Math.round((position / HEALTH_ASSESSMENT.steps.length) * 100)}%"></i></div>
      <p>${esc(step.prompt)}</p>
      ${step.multiple ? `<p class="health-assessment-help">Select all that apply.</p>` : ""}
      ${choices ? `<div class="health-assessment-options" role="${step.multiple ? "group" : "radiogroup"}" aria-label="${esc(step.prompt)}">${choices}</div>` : ""}
      ${step.other ? `<label class="health-assessment-other"><span>${esc(otherLabel)}</span><textarea id="health-assessment-other" rows="2" maxlength="400" placeholder="Optional details in your own words">${esc(answer.other)}</textarea></label>` : ""}
      ${HEALTH_ASSESSMENT.error ? `<div class="health-chat-error" role="alert">${esc(HEALTH_ASSESSMENT.error)}</div>` : ""}
      <div class="health-assessment-actions"><button class="btn btn-ghost btn-sm" id="health-assessment-back" type="button" ${HEALTH_ASSESSMENT.index === 0 || HEALTH_ASSESSMENT.loading ? "disabled" : ""}>Back</button>
        ${step.optional ? `<button class="btn btn-ghost btn-sm" id="health-assessment-skip" type="button" ${HEALTH_ASSESSMENT.loading ? "disabled" : ""}>Skip</button>` : ""}
        <button class="btn btn-primary btn-sm" id="health-assessment-continue" type="button" ${HEALTH_ASSESSMENT.loading ? "disabled" : ""}>${HEALTH_ASSESSMENT.loading ? "Checking…" : "Continue"}</button></div>
    </div>
  </article>`;
}

function healthAssessmentReview() {
  const reviewSteps = HEALTH_ASSESSMENT.steps.filter((step) => !step.review);
  return `<article class="health-chat-message assistant">
    <span class="health-chat-avatar" aria-hidden="true">${healthChatIcon(16)}</span>
    <div class="health-chat-bubble health-assessment-question"><b class="health-chat-speaker">NutriCare Health Assistant</b>
      <div class="health-assessment-progress"><span>Review</span><i style="width:100%"></i></div>
      <p>Please review your answers. You can go back to correct anything before you confirm.</p>
      <div class="health-assessment-review">${reviewSteps.map((step) => `<div><b>${esc(step.prompt)}</b><p>${esc(assessmentAnswerText(step))}</p></div>`).join("")}</div>
      ${HEALTH_ASSESSMENT.error ? `<div class="health-chat-error" role="alert">${esc(HEALTH_ASSESSMENT.error)}</div>` : ""}
      <div class="health-assessment-actions"><button class="btn btn-ghost btn-sm" id="health-assessment-back" type="button" ${HEALTH_ASSESSMENT.loading ? "disabled" : ""}>Back</button>
        <button class="btn btn-primary btn-sm" id="health-assessment-confirm" type="button" ${HEALTH_ASSESSMENT.loading ? "disabled" : ""}>${HEALTH_ASSESSMENT.loading ? "Preparing…" : "Confirm and get guidance"}</button></div>
    </div>
  </article>`;
}

function healthAssessmentConversation() {
  if (HEALTH_ASSESSMENT.emergency) return healthAssessmentEmergency();
  const transcript = HEALTH_ASSESSMENT.turns.map((turn) => `<article class="health-chat-message assistant">
      <span class="health-chat-avatar" aria-hidden="true">${healthChatIcon(16)}</span><div class="health-chat-bubble"><b class="health-chat-speaker">NutriCare Health Assistant</b><p>${esc(turn.question)}</p></div></article>
      <article class="health-chat-message user"><div class="health-chat-bubble"><p>${esc(turn.answer)}</p></div></article>`).join("");
  return transcript + (HEALTH_ASSESSMENT.result ? healthAssessmentResult() : healthAssessmentQuestion());
}

function assessmentHasAnswer(step) {
  const answer = assessmentAnswer(step);
  return answer.values.length > 0 || Boolean(answer.other.trim());
}

async function screenHealthAssessment() {
  const data = await api("/assistant/screen", {
    method: "POST",
    body: { text: assessmentSafetyText(), warning_signs: assessmentWarningIds() },
  });
  if (data.emergency) HEALTH_ASSESSMENT.emergency = data;
  return data;
}

function assessmentDuration() {
  const durationStep = HEALTH_ASSESSMENT.steps.find((step) => step.id.endsWith("_duration"));
  const value = durationStep ? assessmentAnswer(durationStep).values[0] : "";
  return ({ just_started: "today", morning: "today", yesterday: "2-3d", two_three_days: "2-3d", more_three_days: "3-5d" })[value] || "today";
}

function assessmentSeverity() {
  const severityStep = HEALTH_ASSESSMENT.steps.find((step) => step.id.endsWith("_severity"));
  const value = severityStep ? Number(assessmentAnswer(severityStep).values[0]) : 3;
  return Number.isInteger(value) && value >= 1 && value <= 10 ? value : 3;
}

function assessmentPayload() {
  const symptomAnswer = assessmentAnswer(HEALTH_ASSESSMENT.steps[0]);
  const symptomLabels = symptomAnswer.values.filter((value) => value !== "other")
    .map((value) => (ASSESSMENT_SYMPTOMS.find((option) => option.value === value) || { label: value }).label);
  const primary = [...symptomLabels, symptomAnswer.other.trim()].filter(Boolean).join("; ") || "Health concern";
  const associated = [];
  const notes = [];
  const existingConditions = [];
  for (const step of HEALTH_ASSESSMENT.steps) {
    const answer = assessmentAnswer(step);
    if (answer.other.trim()) notes.push(`${step.prompt}: ${answer.other.trim()}`);
    if (step.id.includes("associated") || step.id.endsWith("_location") || step.id.endsWith("_sleep") || step.id.endsWith("_fluids") || step.id === "fever_temperature") {
      for (const value of answer.values.filter((item) => item !== "none")) associated.push(assessmentOptionLabel(step, value));
    }
    if (step.id === "conditions") {
      for (const value of answer.values.filter((item) => item !== "none" && item !== "other")) {
        existingConditions.push(assessmentOptionLabel(step, value));
      }
      if (answer.other.trim()) existingConditions.push(answer.other.trim());
    }
  }
  if (existingConditions.length) notes.push(`Reported existing conditions: ${existingConditions.join(", ")}`);
  return {
    primary,
    duration: assessmentDuration(),
    severity: assessmentSeverity(),
    associated,
    warning_signs: assessmentWarningIds(),
    notes: notes.join(" | ").slice(0, 400),
    existing_conditions: existingConditions,
  };
}

async function continueHealthAssessment(skip = false) {
  const step = assessmentCurrentStep();
  if (!step || HEALTH_ASSESSMENT.loading) return;
  if (skip) HEALTH_ASSESSMENT.answers[step.id] = { values: [], other: "" };
  if (!step.optional && !assessmentHasAnswer(step)) {
    HEALTH_ASSESSMENT.error = "Select an option or add details before continuing.";
    renderHealthChat();
    return;
  }
  const initialAnswer = assessmentAnswer(step);
  if (step.id === "symptoms" && initialAnswer.other.trim() && !initialAnswer.values.includes("other")) {
    HEALTH_ASSESSMENT.answers[step.id] = { ...initialAnswer, values: [...initialAnswer.values, "other"] };
  }
  HEALTH_ASSESSMENT.error = null;
  HEALTH_ASSESSMENT.loading = true;
  renderHealthChat();
  try {
    const screen = await screenHealthAssessment();
    if (screen.emergency) return;
    const current = assessmentCurrentStep();
    HEALTH_ASSESSMENT.turns.push({ question: current.prompt, answer: assessmentAnswerText(current) });
    if (current.id === "symptoms") {
      HEALTH_ASSESSMENT.steps = buildAssessmentSteps(selectedAssessmentSymptoms());
      HEALTH_ASSESSMENT.index = 1;
    } else {
      HEALTH_ASSESSMENT.index += 1;
    }
  } catch (error) {
    HEALTH_ASSESSMENT.error = error.message || "The safety check could not be completed. Please try again.";
  } finally {
    HEALTH_ASSESSMENT.loading = false;
    renderHealthChat();
  }
}

function backHealthAssessment() {
  if (HEALTH_ASSESSMENT.loading || HEALTH_ASSESSMENT.index <= 0) return;
  HEALTH_ASSESSMENT.index -= 1;
  HEALTH_ASSESSMENT.turns.pop();
  HEALTH_ASSESSMENT.error = null;
  renderHealthChat();
}

async function finishHealthAssessment() {
  if (HEALTH_ASSESSMENT.loading) return;
  HEALTH_ASSESSMENT.error = null;
  HEALTH_ASSESSMENT.loading = true;
  renderHealthChat();
  try {
    const screen = await screenHealthAssessment();
    if (screen.emergency) return;
    const result = await api("/assistant/assess", { method: "POST", body: assessmentPayload() });
    if (result.triage === "emergency") HEALTH_ASSESSMENT.emergency = result;
    else HEALTH_ASSESSMENT.result = result;
  } catch (error) {
    HEALTH_ASSESSMENT.error = error.message || "The assessment could not be completed. Please try again.";
  } finally {
    HEALTH_ASSESSMENT.loading = false;
    renderHealthChat();
  }
}

function bindHealthAssessment() {
  const step = assessmentCurrentStep();
  if (!step || HEALTH_ASSESSMENT.emergency || HEALTH_ASSESSMENT.result) return;
  $$("[data-assessment-option]").forEach((button) => button.onclick = () => updateAssessmentSelection(step, button.dataset.assessmentOption));
  const other = $("#health-assessment-other");
  if (other) other.oninput = () => updateAssessmentOther(step, other.value);
  const back = $("#health-assessment-back");
  if (back) back.onclick = backHealthAssessment;
  const skip = $("#health-assessment-skip");
  if (skip) skip.onclick = () => continueHealthAssessment(true);
  const next = $("#health-assessment-continue");
  if (next) next.onclick = () => continueHealthAssessment(false);
  const confirm = $("#health-assessment-confirm");
  if (confirm) confirm.onclick = finishHealthAssessment;
}

function healthChatMessages() {
  if (HEALTH_CHAT.loading) {
    return `<div class="health-chat-loading" role="status">Loading your local chat history…</div>`;
  }
  if (HEALTH_ASSESSMENT.active) return healthAssessmentConversation();
  const items = HEALTH_CHAT.messages.length
    ? HEALTH_CHAT.messages.map((entry) => entry.role === "user"
      ? `<article class="health-chat-message user${entry.pending ? " pending" : ""}"><div class="health-chat-bubble"><p>${esc(entry.message)}</p></div></article>`
      : healthChatAssistantMessage(entry)).join("")
    : healthChatWelcome();
  const pending = HEALTH_CHAT.sending
    ? `<div class="health-chat-loading" role="status">NutriCare Health Chat is preparing a local safety-led response…</div>` : "";
  const error = HEALTH_CHAT.error
    ? `<div class="health-chat-error" role="alert"><b>Message not sent.</b> ${esc(HEALTH_CHAT.error)}</div>` : "";
  return items + pending + error;
}

function renderHealthChat() {
  const root = healthChatRoot();
  if (!root || root.hidden) {
    syncHealthChatLayout(false);
    return;
  }
  const expanded = HEALTH_CHAT.open;
  syncHealthChatLayout(expanded);
  const busy = HEALTH_CHAT.loading || HEALTH_CHAT.sending;
  const guided = HEALTH_ASSESSMENT.active;
  root.innerHTML = `
    <button class="health-chat-launcher" id="health-chat-launcher" type="button" aria-label="Open Health Assistant" aria-expanded="${expanded}" aria-controls="health-chat-panel">
      ${healthChatIcon(22)}<span>Health assistant</span>
    </button>
    ${expanded ? `<section class="health-chat-panel" id="health-chat-panel" role="dialog" aria-modal="false" aria-label="NutriCare Health Assistant">
      <header class="health-chat-header"><div class="row" style="gap:9px"><span class="health-chat-avatar" aria-hidden="true">${healthChatIcon(16)}</span><div><b>Health assistant</b><small>Local safety-led guidance</small></div></div>
        <div class="row" style="gap:4px">${guided ? `<button class="btn btn-ghost btn-sm health-chat-clear" id="health-assessment-restart" type="button">Restart</button><button class="btn btn-ghost btn-sm health-chat-clear" id="health-assessment-free-text" type="button">Free text</button>` : `<button class="btn btn-ghost btn-sm health-chat-clear" id="health-assessment-start" type="button">Assessment</button>`}<button class="btn btn-ghost btn-sm health-chat-clear" id="health-chat-history" type="button" aria-expanded="${HEALTH_CHAT.historyMenu}" aria-controls="health-chat-history-menu">History</button>
        <button class="icon-btn" id="health-chat-close" type="button" aria-label="Close Health Assistant" title="Close">×</button></div></header>
      ${HEALTH_CHAT.historyMenu ? `<section class="health-chat-history-menu" id="health-chat-history-menu" aria-label="Local assistant history options"><b>Local assistant history</b><div><button class="btn btn-ghost btn-sm" id="health-chat-export-json" type="button">Export JSON</button><button class="btn btn-ghost btn-sm" id="health-chat-export-csv" type="button">Export CSV</button><button class="btn btn-danger-soft btn-sm" id="health-chat-clear" type="button">Delete chat history</button></div><p>Exports include saved chat messages and completed guided assessments for this local profile.</p></section>` : ""}
      <div class="health-chat-safety"><b>Emergency?</b> Call 112 in India or your local emergency number now. This assistant cannot replace emergency care.</div>
      <div class="health-chat-messages" id="health-chat-messages" aria-live="polite">${healthChatMessages()}</div>
      ${guided ? "" : `<form class="health-chat-form" id="health-chat-form">
        <label class="sr-only" for="health-chat-input">Write a health or nutrition question</label>
        <textarea id="health-chat-input" maxlength="800" rows="2" placeholder="Write a health or nutrition question" ${busy ? "disabled" : ""} required>${esc(HEALTH_CHAT.draft)}</textarea>
        <div class="row spread mt8"><span class="tiny muted">Health and nutrition questions only</span><button class="btn btn-primary btn-sm" id="health-chat-send" type="submit" ${busy ? "disabled" : ""}>${HEALTH_CHAT.sending ? "Sending…" : "Send"}</button></div>
      </form>`}
    </section>` : ""}`;
  $("#health-chat-launcher").onclick = () => expanded ? closeHealthChat() : openHealthChat();
  if (!expanded) return;
  $("#health-chat-close").onclick = closeHealthChat;
  const history = $("#health-chat-history");
  if (history) history.onclick = () => { HEALTH_CHAT.historyMenu = !HEALTH_CHAT.historyMenu; renderHealthChat(); };
  const clear = $("#health-chat-clear");
  if (clear) clear.onclick = clearHealthChat;
  const exportJson = $("#health-chat-export-json");
  if (exportJson) exportJson.onclick = () => { location.href = "/api/health-chat/export.json"; };
  const exportCsv = $("#health-chat-export-csv");
  if (exportCsv) exportCsv.onclick = () => { location.href = "/api/health-chat/export.csv"; };
  const restart = $("#health-assessment-restart");
  if (restart) restart.onclick = () => { startHealthAssessment(); renderHealthChat(); };
  const startAssessment = $("#health-assessment-start");
  if (startAssessment) startAssessment.onclick = () => { startHealthAssessment(); renderHealthChat(); };
  const freeText = $("#health-assessment-free-text");
  if (freeText) freeText.onclick = () => { stopHealthAssessment(); renderHealthChat(); $("#health-chat-input").focus(); };
  if (guided) {
    bindHealthAssessment();
  } else {
    const form = $("#health-chat-form");
    const input = $("#health-chat-input");
    form.onsubmit = sendHealthChatMessage;
    input.oninput = () => { HEALTH_CHAT.draft = input.value; };
    input.onkeydown = (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendHealthChatMessage(event);
      }
    };
    $$("[data-health-chat-food]").forEach((button) => button.onclick = () => {
      closeHealthChat();
      location.hash = "#/tracker";
      toast("Search the documented food catalogue to choose a portion before logging.");
    });
  }
  const messages = $("#health-chat-messages");
  if (messages) messages.scrollTop = messages.scrollHeight;
}

async function sendHealthChatMessage(event) {
  event.preventDefault();
  if (HEALTH_CHAT.sending || HEALTH_CHAT.loading) return;
  const input = $("#health-chat-input");
  const message = input ? input.value.trim() : HEALTH_CHAT.draft.trim();
  if (!message) {
    HEALTH_CHAT.error = "Write a health or nutrition question before sending.";
    renderHealthChat();
    return;
  }
  const confirmedMessages = HEALTH_CHAT.messages;
  HEALTH_CHAT.messages = [...confirmedMessages, { role: "user", message, pending: true }];
  HEALTH_CHAT.draft = "";
  HEALTH_CHAT.selectedPrompt = "";
  HEALTH_CHAT.error = "";
  HEALTH_CHAT.sending = true;
  renderHealthChat();
  try {
    const data = await api("/health-chat/messages", { method: "POST", body: { message } });
    HEALTH_CHAT.messages = data.messages || [];
  } catch (error) {
    // Do not replace confirmed conversation history with the welcome state when
    // a request fails. Restore the unsent text so the person can retry it.
    HEALTH_CHAT.messages = confirmedMessages;
    HEALTH_CHAT.draft = message;
    HEALTH_CHAT.error = error.message || "The message could not be sent. Please try again.";
  } finally {
    HEALTH_CHAT.sending = false;
    renderHealthChat();
    const nextInput = $("#health-chat-input");
    if (nextInput && !nextInput.disabled) nextInput.focus();
  }
}

async function clearHealthChat() {
  const ok = await confirmModal("Delete saved chat history?",
    "This permanently removes the saved chat messages for the current local profile. This cannot be undone.", "Delete history");
  if (!ok) return;
  try {
    await api("/health-chat/history", { method: "DELETE" });
    HEALTH_CHAT.messages = [];
    HEALTH_CHAT.draft = "";
    HEALTH_CHAT.selectedPrompt = "";
    HEALTH_CHAT.error = "";
    HEALTH_CHAT.historyMenu = false;
    startHealthAssessment();
    renderHealthChat();
    toast("Saved chat history deleted; a new local health assessment has started");
  } catch (error) {
    HEALTH_CHAT.error = error.message || "The local chat history could not be cleared.";
    renderHealthChat();
  }
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && HEALTH_CHAT.open && !$("#modal-root").classList.contains("open")) closeHealthChat();
});
