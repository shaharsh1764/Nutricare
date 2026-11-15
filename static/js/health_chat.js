/* Persistent local Health Chat launcher and panel.
   The server provides deterministic safety-led replies. This client never
   generates health guidance itself and does not send data to a third party. */
"use strict";

const HEALTH_CHAT = { open: false, loading: false, messages: [], userId: null, mounted: false };

function healthChatIcon(size = 20) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 18.5 3.8 21V6.5A3.5 3.5 0 0 1 7.3 3h9.4a3.5 3.5 0 0 1 3.5 3.5v6.3a3.5 3.5 0 0 1-3.5 3.5H10z"/><path d="M12 7v6M9 10h6"/></svg>`;
}

function healthChatRoot() { return $("#health-chat-root"); }

function hideHealthChat() {
  const root = healthChatRoot();
  if (root) { root.hidden = true; root.innerHTML = ""; }
  HEALTH_CHAT.open = false;
}

function ensureHealthChat() {
  const root = healthChatRoot();
  if (!root) return;
  const user = S && S.boot && S.boot.user;
  if (!user || S.onboardingActive) { hideHealthChat(); return; }
  if (HEALTH_CHAT.userId !== user.id) {
    HEALTH_CHAT.userId = user.id;
    HEALTH_CHAT.messages = [];
    HEALTH_CHAT.loading = false;
    HEALTH_CHAT.open = false;
  }
  root.hidden = false;
  renderHealthChat();
}

async function openHealthChat() {
  if (!S || !S.boot || !S.boot.user) return;
  HEALTH_CHAT.open = true;
  renderHealthChat();
  const input = $("#health-chat-input");
  if (input) input.focus();
  if (HEALTH_CHAT.messages.length || HEALTH_CHAT.loading) return;
  HEALTH_CHAT.loading = true;
  renderHealthChat();
  try {
    const data = await api("/health-chat/history");
    HEALTH_CHAT.messages = data.messages || [];
  } catch (error) {
    toast(error.message, true);
  } finally {
    HEALTH_CHAT.loading = false;
    renderHealthChat();
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

function healthChatMessages() {
  if (HEALTH_CHAT.loading) {
    return `<div class="health-chat-loading" role="status">Loading your local chat history…</div>`;
  }
  if (!HEALTH_CHAT.messages.length) {
    return `<article class="health-chat-message assistant">
      <span class="health-chat-avatar" aria-hidden="true">${healthChatIcon(16)}</span>
      <div class="health-chat-bubble"><b class="health-chat-speaker">NutriCare Health Chat</b>
        <p>How are you feeling today?</p>
        <p>I can offer general health and nutrition information, document food ideas, and identify emergency warning signs. I cannot diagnose conditions or choose medication doses.</p>
        <p class="health-chat-disclaimer">Messages are saved only in this local profile. If you think you may have an emergency, call local emergency services now — India: 112 or ambulance 108.</p>
      </div>
    </article>`;
  }
  return HEALTH_CHAT.messages.map((entry) => entry.role === "user"
    ? `<article class="health-chat-message user"><div class="health-chat-bubble"><p>${esc(entry.message)}</p></div></article>`
    : healthChatAssistantMessage(entry)).join("");
}

function renderHealthChat() {
  const root = healthChatRoot();
  if (!root || root.hidden) return;
  const expanded = HEALTH_CHAT.open;
  root.innerHTML = `
    <button class="health-chat-launcher" id="health-chat-launcher" type="button" aria-label="Open Health Chat" aria-expanded="${expanded}" aria-controls="health-chat-panel">
      ${healthChatIcon(22)}<span>Health chat</span>
    </button>
    ${expanded ? `<section class="health-chat-panel" id="health-chat-panel" role="dialog" aria-modal="false" aria-label="NutriCare Health Chat">
      <header class="health-chat-header"><div class="row" style="gap:9px"><span class="health-chat-avatar" aria-hidden="true">${healthChatIcon(16)}</span><div><b>Health chat</b><small>Local safety-led guidance</small></div></div>
        <div class="row" style="gap:4px"><button class="icon-btn health-chat-clear" id="health-chat-clear" type="button" title="Clear local chat history" aria-label="Clear local chat history">${ICONS.trash}</button>
        <button class="icon-btn" id="health-chat-close" type="button" aria-label="Close Health Chat" title="Close">×</button></div></header>
      <div class="health-chat-safety"><b>Emergency?</b> Call 112 in India or your local emergency number now. This chat cannot replace emergency care.</div>
      <div class="health-chat-messages" id="health-chat-messages" aria-live="polite">${healthChatMessages()}</div>
      <form class="health-chat-form" id="health-chat-form">
        <label class="sr-only" for="health-chat-input">Describe how you are feeling</label>
        <textarea id="health-chat-input" maxlength="800" rows="2" placeholder="How are you feeling today?" required></textarea>
        <div class="row spread mt8"><span class="tiny muted">Health and nutrition questions only</span><button class="btn btn-primary btn-sm" id="health-chat-send" type="submit">Send</button></div>
      </form>
    </section>` : ""}`;
  $("#health-chat-launcher").onclick = () => expanded ? closeHealthChat() : openHealthChat();
  if (!expanded) return;
  $("#health-chat-close").onclick = closeHealthChat;
  $("#health-chat-clear").onclick = clearHealthChat;
  $("#health-chat-form").onsubmit = sendHealthChatMessage;
  $$("[data-health-chat-food]").forEach((button) => button.onclick = () => {
    closeHealthChat();
    location.hash = "#/tracker";
    toast("Search the documented food catalogue to choose a portion before logging.");
  });
  const messages = $("#health-chat-messages");
  if (messages) messages.scrollTop = messages.scrollHeight;
}

async function sendHealthChatMessage(event) {
  event.preventDefault();
  const input = $("#health-chat-input");
  const send = $("#health-chat-send");
  const message = input ? input.value.trim() : "";
  if (!message) { toast("Write a health or nutrition question first", true); return; }
  if (send) { send.disabled = true; send.textContent = "Sending…"; }
  try {
    const data = await api("/health-chat/messages", { method: "POST", body: { message } });
    HEALTH_CHAT.messages = data.messages || [];
    renderHealthChat();
  } catch (error) {
    toast(error.message, true);
    if (send) { send.disabled = false; send.textContent = "Send"; }
  }
}

async function clearHealthChat() {
  const ok = await confirmModal("Clear local health chat history?",
    "This permanently removes the saved messages for the current local profile.", "Clear history");
  if (!ok) return;
  try {
    await api("/health-chat/history", { method: "DELETE" });
    HEALTH_CHAT.messages = [];
    renderHealthChat();
    toast("Local chat history cleared");
  } catch (error) { toast(error.message, true); }
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && HEALTH_CHAT.open && !$("#modal-root").classList.contains("open")) closeHealthChat();
});
