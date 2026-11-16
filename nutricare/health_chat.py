"""Local, safety-led conversational health chat for NutriCare.

The module is intentionally deterministic. It does not call an online model,
does not diagnose, and does not select or dose medication from a free-text
message. A separate option-only OTC education flow is backed by a small,
source-reviewed local reference; emergency screening is shared with the
established assistant rule engine so ordinary conversation logic cannot bypass
its warning-sign policy.

The chat keeps only a small, explicit conversation state: the symptom details a
person has chosen to share and the next single follow-up question. The state is
persisted with the assistant reply by the API and is restored from local chat
history; no remote health service is contacted.
"""
from __future__ import annotations

import re
from typing import Any

from . import assistant, insights

ENGINE_VERSION = "local-health-chat-v3"
MAX_MESSAGE_CHARS = 800

DISCLAIMER = (
    "NutriCare Health Chat provides general educational information only. It is "
    "not a diagnosis, emergency service, or substitute for a clinician, pharmacist, "
    "or local emergency services."
)

# A free-text medicine request receives a pharmacist/clinician handoff rather
# than inferred selection, interaction advice, or a dose. Source-cited OTC
# education is available only through the separate option-only safety flow.
MEDICINE_PATTERN = re.compile(
    r"\b(medic(?:ine|ation)|drug|tablet|pill|dose|antibiotic|painkiller|"
    r"paracetamol|acetaminophen|ibuprofen|aspirin)\b",
    re.IGNORECASE,
)

GREETING_PATTERN = re.compile(r"^\s*(hi|hello|hey|good (morning|afternoon|evening))\b", re.IGNORECASE)
ILLNESS_PATTERN = re.compile(r"\b(sick|ill|unwell|not well|under the weather)\b", re.IGNORECASE)
GOOD_PATTERN = re.compile(r"\b(feel(?:ing)? good|feeling well|i am well|i'm well)\b", re.IGNORECASE)
DONT_KNOW_PATTERN = re.compile(r"^\s*(i\s+)?(do not|don't|dont)\s+know\b|^\s*not sure\b", re.IGNORECASE)
TEMPERATURE_PATTERN = re.compile(
    r"\b\d{2,3}(?:\.\d)?\s*(?:°\s*)?(?:c|f|celsius|fahrenheit|degrees?)\b|\b(high|low)\s+fever\b",
    re.IGNORECASE,
)
SEVERITY_PATTERN = re.compile(r"\b(10|[1-9])\b")
CORRECTION_PATTERN = re.compile(r"^\s*(actually|correction|i meant|to correct that)\b", re.IGNORECASE)
DURATION_HINT_PATTERN = re.compile(r"\b(since|for|today|yesterday|days?|weeks?|months?)\b", re.IGNORECASE)
SLEEP_ANSWER_PATTERN = re.compile(
    r"\b(sleep|slept|rest|rested|hours?|night|insomnia|wake|waking|good|well|"
    r"poor|bad|fine|okay|ok|trouble|difficult|enough|less|more)\b",
    re.IGNORECASE,
)
NO_ASSOCIATED_SYMPTOMS_PATTERN = re.compile(
    r"^\s*(no|none|nothing|not really)(?:\s+(?:other|else|additional)\s+symptoms?)?\s*[.!]?\s*$",
    re.IGNORECASE,
)

# Health/nutrition-only scope. Follow-up answers are accepted through the saved
# conversation state even when they are short (for example, "Since yesterday").
HEALTH_PATTERN = re.compile(
    r"\b(health|feel|feeling|symptom|pain|ache|tired|fatigue|weak|headache|migraine|"
    r"bloat|gas|nausea|vomit|sleep|insomnia|dizz|fever|chill|cough|throat|"
    r"breath|chest|water|hydration|food|meal|eat|diet|nutrition|hungry|"
    r"appetite|weight|stress|anxious|wellness|medicine|medication|drug|tablet|"
    r"pill|dose|allergy|allergic|sick|ill|unwell|diabetes|blood sugar)\b",
    re.IGNORECASE,
)

HYDRATION_PATTERN = re.compile(r"\b(water|hydration|hydrated|drink|fluids?)\b", re.IGNORECASE)
NUTRITION_PATTERN = re.compile(r"\b(food|meal|eat|diet|nutrition|appetite|hungry)\b", re.IGNORECASE)
DIABETES_PATTERN = re.compile(r"\b(diabetes|blood sugar|glucose)\b", re.IGNORECASE)
URGENT_PATTERN = re.compile(
    r"\b(worsening|getting worse|unbearable|very high fever|cannot function)\b",
    re.IGNORECASE,
)


def _has_urgent_wording(text: str) -> bool:
    """Recognise explicit urgent wording without treating “not severe” as urgent."""
    if URGENT_PATTERN.search(text):
        return True
    return re.search(r"(?<!not )\bsevere\b", text.lower()) is not None

# Every name is looked up in the food database at runtime. A stale or missing
# record is omitted; no food or nutrition value is invented here.
FOOD_OPTIONS = {
    "nausea": (
        ["Rice, white (cooked)", "Banana", "Oatmeal (cooked in water)", "Khichdi (cooked)"],
        "These are gentle, documented food options some people choose while they can tolerate food. Start with small amounts and use what suits you.",
    ),
    "sore_throat": (
        ["Oatmeal (cooked in water)", "Banana", "Khichdi (cooked)", "Rice, white (cooked)"],
        "Soft, familiar foods may be more comfortable if swallowing is uncomfortable; choose foods you can tolerate.",
    ),
    "cough": (
        ["Oatmeal (cooked in water)", "Banana", "Khichdi (cooked)"],
        "These are ordinary, softer food options rather than a treatment for a cough.",
    ),
    "bloating": (
        ["Rice, white (cooked)", "Banana", "Oatmeal (cooked in water)"],
        "These are neutral catalogue options to consider, not proof that another food caused bloating. A meal-and-symptom record can help reveal your own pattern.",
    ),
    "fatigue": (
        ["Oatmeal (cooked in water)", "Moong dal, cooked", "Banana", "Chana (chickpeas), cooked"],
        "These documented foods can support regular meals. They do not explain or treat fatigue, which has many possible causes.",
    ),
    "headache": (
        ["Oatmeal (cooked in water)", "Banana", "Moong dal, cooked"],
        "These are ordinary food choices for a regular meal; the chat cannot identify a headache trigger or treatment.",
    ),
    "dizziness": (
        ["Banana", "Oatmeal (cooked in water)", "Rice, white (cooked)"],
        "These are general, documented food options. Repeated, prolonged, or worsening dizziness needs clinical assessment.",
    ),
    "fever": (
        ["Khichdi (cooked)", "Rice, white (cooked)", "Banana", "Oatmeal (cooked in water)"],
        "These are mild food options if you are able to eat. Rest and steady fluids are general wellbeing measures, not a substitute for care.",
    ),
    "sleep": (
        ["Oatmeal (cooked in water)", "Banana", "Moong dal, cooked"],
        "These are regular-food ideas only. The chat does not prescribe a sleep diet or treatment.",
    ),
    "general": (
        ["Oatmeal (cooked in water)", "Moong dal, cooked", "Banana", "Spinach / palak (cooked, no added salt)"],
        "These are documented food ideas for regular meals, filtered using your recorded food preferences where possible.",
    ),
}


def engine_mode() -> dict:
    """Describe the local chat truthfully for the UI and API."""
    return {
        "engine": ENGINE_VERSION,
        "online_ai_used": False,
        "label": "Local safety-led health chat (no online AI or external health API)",
        "medication_policy": "Free-text medicine questions are handed to a pharmacist or clinician. Limited paracetamol/cetirizine education is available only through the source-cited, option-only OTC safety flow.",
    }


def _topic(text: str) -> str:
    """Select a conservative food-guidance topic from shared symptom vocabulary."""
    lowered = text.lower()
    for name, kb in assistant.SYMPTOM_KB.items():
        if assistant._matches(lowered, kb["match"]):
            return name
    return "general"


def _food_suggestions(foods: list[dict], profile: dict | None, topic: str) -> list[dict]:
    """Return up to three documented, preference-compatible foods for a topic."""
    profile = profile or {}
    allergies = profile.get("allergies") or []
    prefs = profile.get("dietary_prefs") or []
    names, note = FOOD_OPTIONS.get(topic, FOOD_OPTIONS["general"])
    by_name = {str(food.get("name")): food for food in foods if food.get("name")}
    suggested = []
    for name in names:
        food = by_name.get(name)
        if not food or insights.is_excluded(food, allergies, prefs):
            continue
        suggested.append({
            "food_id": food.get("id"),
            "name": food["name"],
            "group": food.get("grp"),
            "serving_desc": food.get("serving_desc") or "documented serving",
            "why": note,
        })
        if len(suggested) == 3:
            break
    return suggested


def _reply(
    message: str,
    *,
    triage: str = "general_guidance",
    guidance: list[dict] | None = None,
    foods: list[dict] | None = None,
    medication_handoff: bool = False,
    red_flags: list[dict] | None = None,
    emergency_actions: list[str] | None = None,
    conversation: dict | None = None,
) -> dict:
    """Use one stable response shape for every deterministic path."""
    return {
        "triage": triage,
        "message": message,
        "guidance": guidance or [],
        "food_recommendations": foods or [],
        "medication_handoff": medication_handoff,
        "red_flags": red_flags or [],
        "emergency_actions": emergency_actions or [],
        "conversation": conversation or {"mode": "none", "status": "complete"},
        "disclaimer": DISCLAIMER,
    }


def _out_of_scope_reply(conversation: dict | None = None) -> dict:
    return _reply(
        "I’m NutriCare Health Chat. I can help with general health education, "
        "symptom check-ins, food and nutrition ideas, and hydration. I can’t assist "
        "with unrelated requests. Please rephrase your message as a health or "
        "nutrition question, and I’ll do my best to help.",
        triage="out_of_scope",
        conversation=conversation,
    )


def _symptom_labels(text: str) -> list[str]:
    """Extract only explicitly written symptom labels; never infer a condition."""
    lowered = text.lower()
    labels = []
    for name, kb in assistant.SYMPTOM_KB.items():
        if assistant._matches(lowered, kb["match"]):
            labels.append(name.replace("_", " "))
    if re.search(r"\bweak(?:ness)?\b", lowered) and "weakness" not in labels:
        labels.append("weakness")
    if re.search(r"\bbody pain\b", lowered) and "body pain" not in labels:
        labels.append("body pain")
    if re.search(r"\b(stress(?:ed)?|anxious|anxiety)\b", lowered) and "stress or anxiety" not in labels:
        labels.append("stress or anxiety")
    if re.search(r"\b(feeling low|feel low|low mood|sad)\b", lowered) and "low mood" not in labels:
        labels.append("low mood")
    return labels


def _matches_follow_up_context(text: str, conversation: dict) -> bool:
    """Allow a plausible answer to the current question, not arbitrary text."""
    if DONT_KNOW_PATTERN.search(text):
        return True
    question = conversation.get("next_question")
    symptoms = _symptom_labels(text)
    if question == "symptoms":
        return bool(symptoms or HEALTH_PATTERN.search(text))
    if question == "temperature":
        return bool(TEMPERATURE_PATTERN.search(text)
                    or re.fullmatch(r"\s*\d{2,3}(?:\.\d)?\s*", text)
                    or symptoms)
    if question == "duration":
        return bool(DURATION_HINT_PATTERN.search(text) or symptoms)
    if question == "sleep":
        return bool(SLEEP_ANSWER_PATTERN.search(text) or symptoms)
    if question == "associated":
        return bool(HEALTH_PATTERN.search(text)
                    or NO_ASSOCIATED_SYMPTOMS_PATTERN.fullmatch(text))
    if question == "severity":
        return bool(SEVERITY_PATTERN.search(text) or symptoms)
    return False


def _pretty_list(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _next_after_duration(symptoms: list[str]) -> str:
    # Fever gets temperature, duration, and associated-symptom questions. For a
    # person reporting tiredness alone, sleep is a useful next detail. A headache
    # plus weakness instead proceeds to the requested severity check.
    if "fever" in symptoms:
        return "associated"
    if symptoms and set(symptoms).issubset({"fatigue", "weakness"}):
        return "sleep"
    return "severity"


def _start_symptom_conversation(symptoms: list[str]) -> dict:
    if not symptoms:
        return _reply(
            "I’m sorry you’re feeling unwell. What symptoms are you experiencing? "
            "For example, you can mention fever, headache, cough, nausea, pain, tiredness, or anything else you notice.",
            conversation={"mode": "symptom", "next_question": "symptoms", "symptoms": []},
        )
    state: dict[str, Any] = {"mode": "symptom", "symptoms": symptoms}
    if "fever" in symptoms:
        state["next_question"] = "temperature"
        return _reply(
            f"I’m sorry you’re dealing with {_pretty_list(symptoms)}. If you have a thermometer, what temperature did you measure? If not, you can say you don’t know.",
            conversation=state,
        )
    state["next_question"] = "duration"
    return _reply(
        f"I’m sorry you’re dealing with {_pretty_list(symptoms)}. How long have you been experiencing this?",
        conversation=state,
    )


def _active_symptom_state(conversation: dict | None) -> dict | None:
    if not isinstance(conversation, dict) or conversation.get("mode") != "symptom":
        return None
    if conversation.get("status") == "complete":
        return None
    if conversation.get("next_question") not in {"symptoms", "temperature", "duration", "sleep", "associated", "severity"}:
        return None
    state = dict(conversation)
    state["symptoms"] = [str(item) for item in state.get("symptoms") or [] if str(item)]
    return state


def _completed_symptom_state(conversation: dict | None) -> dict | None:
    if not isinstance(conversation, dict) or conversation.get("mode") != "symptom":
        return None
    if conversation.get("status") != "complete":
        return None
    state = dict(conversation)
    state["symptoms"] = [str(item) for item in state.get("symptoms") or [] if str(item)]
    return state


def _topic_for_symptoms(symptoms: list[str]) -> str:
    for name in symptoms:
        if name == "weakness":
            return "fatigue"
        if name.replace(" ", "_") in FOOD_OPTIONS:
            return name.replace(" ", "_")
    return "general"


def _finish_symptom_conversation(state: dict, profile: dict | None, foods: list[dict]) -> dict:
    symptoms = state.get("symptoms") or ["symptoms"]
    summary = f"You described {_pretty_list(symptoms)}"
    if state.get("duration") and state["duration"] != "not known":
        summary += f" for {state['duration']}"
    if state.get("severity") and state["severity"] != "not known":
        summary += f", with severity {state['severity']} out of 10"
    summary += "."

    topic_text = " ".join(symptoms)
    _possibilities, self_care, _matched = assistant.explain_possibilities(topic_text)
    severity = state.get("severity")
    try:
        high_severity = int(severity) >= 8
    except (TypeError, ValueError):
        high_severity = False
    state = dict(state, status="complete", next_question=None)
    if high_severity:
        message = (
            f"{summary} Because you rated it {severity} out of 10, please arrange same-day in-person medical advice. "
            "I cannot tell what is causing these symptoms in chat."
        )
        triage = "urgent_same_day"
    else:
        message = (
            f"{summary} I cannot tell what is causing it in chat. General comfort steps may help while you monitor it, "
            "but seek professional advice if it is severe, persistent, worsening, or worrying you."
        )
        triage = "general_guidance"
    return _reply(
        message,
        triage=triage,
        guidance=[{"title": item["title"], "detail": item["detail"]} for item in self_care[:3]],
        foods=_food_suggestions(foods, profile, _topic_for_symptoms(symptoms)),
        conversation=state,
    )


def _correct_completed_symptom_conversation(
    text: str, conversation: dict, profile: dict | None, foods: list[dict]
) -> dict:
    """Update an explicit correction rather than discarding a completed chat."""
    state = _completed_symptom_state(conversation)
    if not state:
        return _out_of_scope_reply()
    correction = CORRECTION_PATTERN.sub("", text).strip().lstrip(" ,:;-")
    match = SEVERITY_PATTERN.search(correction)
    if match:
        state["severity"] = match.group(1)
        return _finish_symptom_conversation(state, profile, foods)
    if DONT_KNOW_PATTERN.search(correction):
        state["severity"] = "not known"
        return _finish_symptom_conversation(state, profile, foods)
    if DURATION_HINT_PATTERN.search(correction):
        state["duration"] = correction[:120]
        return _finish_symptom_conversation(state, profile, foods)
    additions = _symptom_labels(correction)
    if additions:
        for symptom in additions:
            if symptom not in state["symptoms"]:
                state["symptoms"].append(symptom)
        return _finish_symptom_conversation(state, profile, foods)
    return _reply(
        "I can update a symptom, duration, or 1 to 10 severity that you previously shared. Please say what you want to correct.",
        conversation=state,
    )


def _continue_symptom_conversation(
    text: str, conversation: dict, profile: dict | None, foods: list[dict]
) -> dict:
    """Advance one explicit state step without guessing omitted details."""
    state = _active_symptom_state(conversation)
    if not state:
        return _start_symptom_conversation(_symptom_labels(text))
    question = state["next_question"]
    unknown = bool(DONT_KNOW_PATTERN.search(text))

    if question == "symptoms":
        symptoms = _symptom_labels(text)
        if not symptoms:
            return _reply(
                "That’s okay. Describe anything you notice in your own words, such as pain, fever, cough, nausea, tiredness, or where in your body you feel unwell.",
                conversation=state,
            )
        return _start_symptom_conversation(symptoms)

    # If a person adds a symptom while answering a later question, record that
    # explicit addition but keep the current single question rather than losing
    # the conversation path.
    for symptom in _symptom_labels(text):
        if symptom not in state["symptoms"]:
            state["symptoms"].append(symptom)

    if question == "temperature":
        if not unknown and not TEMPERATURE_PATTERN.search(text):
            return _reply(
                "If you have a thermometer, share the reading and whether it is in °C or °F. If you do not know, just say “I don’t know.”",
                conversation=state,
            )
        state["temperature"] = "not known" if unknown else text[:80]
        state["next_question"] = "duration"
        return _reply(
            "How long have you had the fever?",
            conversation=state,
        )

    if question == "duration":
        if not unknown and not DURATION_HINT_PATTERN.search(text):
            return _reply(
                "I’m not sure how long that has been happening. You can share a "
                "time period, such as “since yesterday” or “for three days,” or "
                "say “I don’t know.”",
                triage="clarification",
                conversation=state,
            )
        state["duration"] = "not known" if unknown else text[:120]
        state["next_question"] = _next_after_duration(state["symptoms"])
        if state["next_question"] == "associated":
            return _reply(
                "Besides the fever, what other symptoms have you noticed, if any? For example, cough, sore throat, rash, pain, or nausea.",
                conversation=state,
            )
        if state["next_question"] == "sleep":
            return _reply(
                "How has your sleep been recently? You can describe it in your own words.",
                conversation=state,
            )
        return _reply(
            "How severe is it on a scale of 1 to 10, where 10 is the most severe?",
            conversation=state,
        )

    if question == "sleep":
        state["sleep"] = "not known" if unknown else text[:120]
        state["next_question"] = "severity"
        return _reply(
            "How severe is the tiredness on a scale of 1 to 10, where 10 is the most severe?",
            conversation=state,
        )

    if question == "associated":
        state["associated"] = "not known" if unknown else text[:160]
        state["next_question"] = "severity"
        return _reply(
            "How severe is it on a scale of 1 to 10, where 10 is the most severe?",
            conversation=state,
        )

    # The severity question is deliberately strict: no assumed severity is
    # stored if the person gives a non-numeric answer.
    match = SEVERITY_PATTERN.search(text)
    if not unknown and not match:
        return _reply(
            "I couldn’t find a number from 1 to 10. If you are unsure, you can say “I don’t know.”",
            conversation=state,
        )
    state["severity"] = "not known" if unknown else match.group(1)
    return _finish_symptom_conversation(state, profile, foods)


def _urgent_symptom_reply(symptoms: list[str]) -> dict:
    """Give conservative same-day direction without treating it as an emergency diagnosis."""
    label = _pretty_list(symptoms or ["these symptoms"])
    return _reply(
        f"Because you described {label} as severe or worsening, please arrange same-day in-person medical care. "
        "I cannot assess the cause or seriousness through chat. If an emergency warning sign appears, call 112 in India or your local emergency number now.",
        triage="urgent_same_day",
        conversation={"mode": "none", "status": "complete", "interrupted_by": "urgent_same_day"},
    )


def _feeling_good_reply() -> dict:
    return _reply(
        "I’m glad you’re feeling well. I can still help with a general nutrition, hydration, sleep, or wellbeing question whenever you need it.",
    )


def _hydration_reply() -> dict:
    return _reply(
        "Hydration needs vary with weather, activity, illness, pregnancy, and some health conditions. "
        "For most people, drinking regularly through the day and using thirst as one cue is a reasonable general approach. "
        "If you have been told to limit fluids or have ongoing vomiting, diarrhoea, dizziness, or very little urine, contact a clinician rather than relying on chat guidance.",
        guidance=[
            {"title": "Use regular opportunities", "detail": "Have fluids with meals and keep a drink nearby if that suits your routine."},
            {"title": "Use your tracker as a record", "detail": "NutriCare’s water goal is a planning estimate, not a medical prescription."},
        ],
    )


def _nutrition_reply(text: str, profile: dict | None, foods: list[dict]) -> dict:
    topic = _topic(text)
    return _reply(
        "When you feel unwell, a cautious general approach is steady fluids and small, regular meals if you can tolerate them. "
        "I cannot choose a medical diet or tell what your symptoms mean. The documented food ideas below are ordinary options, not treatment.",
        guidance=[
            {"title": "Choose what you can tolerate", "detail": "Start with small amounts and avoid foods that you know do not suit you or conflict with your recorded allergies."},
            {"title": "Seek care when needed", "detail": "Get professional advice if symptoms are severe, persistent, worsening, or you cannot keep fluids down."},
        ],
        foods=_food_suggestions(foods, profile, topic),
    )


def _diabetes_education_reply() -> dict:
    return _reply(
        "Diabetes is a long-term condition in which the body has difficulty keeping blood glucose in its usual range. "
        "It is diagnosed with clinical assessment and tests, not from a chat or a symptom alone. General diabetes education often focuses on regular meals, activity, and following a clinician’s plan, but personal food, monitoring, or medication advice needs a qualified clinician or diabetes educator.",
        guidance=[
            {"title": "For a personal concern", "detail": "If you are worried about symptoms, a glucose result, or a diagnosis, arrange a clinician visit rather than trying to interpret it here."},
        ],
    )


def respond(
    message: str,
    profile: dict | None,
    foods: list[dict],
    conversation: dict | None = None,
) -> dict:
    """Build one local, safe response to a chat message.

    ``conversation`` is the last persisted assistant state for this local
    profile. It contains only user-provided symptom details and the next question;
    no model, remote API, or hidden clinical inference is used.
    """
    text = str(message or "").strip()
    if not text:
        raise ValueError("Write a health or nutrition question before sending.")
    if len(text) > MAX_MESSAGE_CHARS:
        raise ValueError(f"Messages must be {MAX_MESSAGE_CHARS} characters or fewer.")

    # Safety screen is always first and deliberately independent of the
    # conversation state, nutrition paths, and ordinary wording.
    flags = assistant.screen_red_flags(text, [])
    if flags:
        actions = [assistant.EMERGENCY_ACTION] + [flag["action"] for flag in flags]
        return _reply(
            "I noticed an emergency warning sign in what you wrote. Stop using the chat for guidance and call an ambulance or your local emergency number now. "
            "In India, call 112 (or medical ambulance 108); do not drive yourself if it is unsafe.",
            triage="emergency",
            red_flags=[{"id": flag["id"], "label": flag["label"], "action": flag["action"]} for flag in flags],
            emergency_actions=actions,
            conversation={"mode": "none", "status": "complete", "interrupted_by": "emergency"},
        )

    if MEDICINE_PATTERN.search(text):
        return _reply(
            "I cannot choose a medicine, recommend a personal dose, or check a medication interaction from a free-text message. For limited source-cited information on paracetamol or cetirizine, use the Assistant’s OTC info option, which asks structured safety questions first. For any other medicine question, please speak with a pharmacist or clinician. If symptoms are severe, worsening, or worrying, seek urgent in-person care.",
            triage="pharmacist_handoff",
            guidance=[{
                "title": "Medication safety",
                "detail": "Do not start, stop, combine, or change a medicine based on this chat. A pharmacist or clinician can give individual medication advice.",
            }],
            medication_handoff=True,
            conversation={"mode": "none", "status": "complete", "interrupted_by": "medication_handoff"},
        )

    # Direct education and nourishment questions deliberately interrupt a
    # pending symptom questionnaire; the person should be able to change topic.
    if DIABETES_PATTERN.search(text) and re.search(r"\b(what|tell|explain|about|is)\b", text, re.IGNORECASE):
        return _diabetes_education_reply()
    if HYDRATION_PATTERN.search(text) and re.search(r"\b(how much|how many|should i|hydration|water|drink)\b", text, re.IGNORECASE):
        return _hydration_reply()
    if NUTRITION_PATTERN.search(text) and (re.search(r"\?", text) or ILLNESS_PATTERN.search(text)):
        return _nutrition_reply(text, profile, foods)

    active_state = _active_symptom_state(conversation)
    if active_state:
        if _has_urgent_wording(text):
            return _urgent_symptom_reply(active_state.get("symptoms") or _symptom_labels(text))
        if not _matches_follow_up_context(text, active_state):
            # Do not store unrelated free text as a symptom duration/severity.
            # Preserve the current question so the person can resume it later.
            return _out_of_scope_reply(conversation=active_state)
        return _continue_symptom_conversation(text, active_state, profile, foods)
    if _completed_symptom_state(conversation) and CORRECTION_PATTERN.search(text):
        return _correct_completed_symptom_conversation(text, conversation or {}, profile, foods)

    # A greeting can accompany a symptom (for example, "Hi, I feel sick"), so
    # recognise explicit symptoms before falling back to the greeting response.
    symptoms = _symptom_labels(text)
    if symptoms:
        if _has_urgent_wording(text):
            return _urgent_symptom_reply(symptoms)
        return _start_symptom_conversation(symptoms)
    if ILLNESS_PATTERN.search(text):
        return _start_symptom_conversation([])
    if GOOD_PATTERN.search(text):
        return _feeling_good_reply()
    if GREETING_PATTERN.search(text):
        return _reply(
            "Hi! I’m NutriCare Health Chat. What would you like help with? You can describe how you feel, ask a general nutrition or hydration question, or ask for health education.",
        )
    if HYDRATION_PATTERN.search(text):
        return _hydration_reply()
    if NUTRITION_PATTERN.search(text):
        return _nutrition_reply(text, profile, foods)
    if DONT_KNOW_PATTERN.search(text):
        return _reply(
            "That’s okay. You can tell me one thing you notice, such as where you feel pain, whether you have a fever, cough, nausea, tiredness, or a food or hydration question.",
        )
    if not HEALTH_PATTERN.search(text):
        return _out_of_scope_reply()

    # A health-related message that does not match a supported rule gets a
    # clear, useful clarification instead of an unrelated or guessed answer.
    return _reply(
        "I’m not sure I understood your health or nutrition question. I can help "
        "with general health education, symptom check-ins, food and nutrition "
        "ideas, or hydration. Could you rephrase your question or tell me what "
        "kind of help you’re looking for?",
        triage="clarification",
    )
