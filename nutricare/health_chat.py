"""Local, safety-led health chat responses for NutriCare.

This module is intentionally deterministic. It does not call an online model,
does not diagnose, and does not select or dose medication.  Emergency screening
is shared with the established assistant rule engine so a chat message cannot
bypass its warning-sign policy.

The chat may suggest only foods from the application's documented food catalogue
and filters them through the user's recorded allergies and dietary preferences.
Those suggestions support ordinary nourishment; they are not treatment claims.
"""
from __future__ import annotations

import re

from . import assistant, insights

ENGINE_VERSION = "local-health-chat-v1"
MAX_MESSAGE_CHARS = 800

DISCLAIMER = (
    "NutriCare Health Chat provides general educational information only. It is "
    "not a diagnosis, emergency service, or substitute for a clinician, pharmacist, "
    "or local emergency services."
)

# Kept deliberately broad: a medicine request gets a safe pharmacist handoff
# rather than an inferred diagnosis or a personalised drug recommendation.
MEDICINE_PATTERN = re.compile(
    r"\b(medic(?:ine|ation)|drug|tablet|pill|dose|antibiotic|painkiller|"
    r"paracetamol|acetaminophen|ibuprofen|aspirin)\b",
    re.IGNORECASE,
)

# The chat is health/nutrition-only. A greeting remains in scope so the launcher
# can naturally open with "How are you feeling today?".
HEALTH_PATTERN = re.compile(
    r"\b(health|feel|feeling|symptom|pain|ache|tired|fatigue|headache|migraine|"
    r"bloat|gas|nausea|vomit|sleep|insomnia|dizz|fever|chill|cough|throat|"
    r"breath|chest|water|hydration|food|meal|eat|diet|nutrition|hungry|"
    r"appetite|weight|stress|anxious|wellness|medicine|medication|drug|tablet|"
    r"pill|dose|allergy|allergic)\b",
    re.IGNORECASE,
)

URGENT_PATTERN = re.compile(
    r"\b(severe|worsening|getting worse|unbearable|very high fever|cannot function)\b",
    re.IGNORECASE,
)

# Every name is looked up in the food database at runtime. A stale or missing
# record is simply omitted; no food or nutrition value is invented here.
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
        "medication_policy": "Medication questions are directed to a pharmacist or clinician; no medicine selection or dosing is provided.",
    }


def _topic(text: str) -> str:
    """Select a conservative food-guidance topic from existing symptom vocabulary."""
    lowered = text.lower()
    for name, kb in assistant.SYMPTOM_KB.items():
        if assistant._matches(lowered, kb["match"]):  # shared, tested keyword policy
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


def _out_of_scope_reply() -> dict:
    return {
        "triage": "out_of_scope",
        "message": (
            "I’m NutriCare’s health and nutrition chat. I can help you describe how "
            "you feel, review general food and hydration ideas, and identify emergency "
            "warning signs. Please ask a health or nutrition question."
        ),
        "guidance": [],
        "food_recommendations": [],
        "medication_handoff": False,
        "red_flags": [],
        "emergency_actions": [],
        "disclaimer": DISCLAIMER,
    }


def respond(message: str, profile: dict | None, foods: list[dict]) -> dict:
    """Build one safe, deterministic response to a local health-chat message.

    The caller persists the raw user message and this response separately. This
    pure function never writes data, calls a remote service, or accesses Flask.
    """
    text = str(message or "").strip()
    if not text:
        raise ValueError("Write a health or nutrition question before sending.")
    if len(text) > MAX_MESSAGE_CHARS:
        raise ValueError(f"Messages must be {MAX_MESSAGE_CHARS} characters or fewer.")

    flags = assistant.screen_red_flags(text, [])
    if flags:
        actions = [assistant.EMERGENCY_ACTION] + [flag["action"] for flag in flags]
        return {
            "triage": "emergency",
            "message": (
                "I noticed an emergency warning sign in what you wrote. Stop using the "
                "chat for guidance and call an ambulance or your local emergency number now. "
                "In India, call 112 (or medical ambulance 108); do not drive yourself if it is unsafe."
            ),
            "guidance": [],
            "food_recommendations": [],
            "medication_handoff": False,
            "red_flags": [{"id": flag["id"], "label": flag["label"], "action": flag["action"]}
                          for flag in flags],
            "emergency_actions": actions,
            "disclaimer": DISCLAIMER,
        }

    if MEDICINE_PATTERN.search(text):
        return {
            "triage": "pharmacist_handoff",
            "message": (
                "I can’t choose a medicine, recommend a dose, or check whether a medication "
                "is right for you. A pharmacist or clinician can review your symptoms, current "
                "medicines, allergies, and relevant conditions safely. If symptoms are severe, "
                "worsening, or you are worried, seek urgent in-person care."
            ),
            "guidance": [{
                "title": "Until you speak with a professional",
                "detail": "Use only medicines already directed for you by a qualified professional or follow the product label. Do not combine or start medicines based on this chat.",
            }],
            "food_recommendations": [],
            "medication_handoff": True,
            "red_flags": [],
            "emergency_actions": [],
            "disclaimer": DISCLAIMER,
        }

    if not HEALTH_PATTERN.search(text):
        return _out_of_scope_reply()

    topic = _topic(text)
    possibilities, self_care, _matched = assistant.explain_possibilities(text)
    urgent = bool(URGENT_PATTERN.search(text))
    food_recommendations = _food_suggestions(foods, profile, topic)
    first = possibilities[0]["detail"] if possibilities else (
        "Many symptoms have more than one possible cause, and this chat cannot determine which applies to you."
    )
    prefix = (
        "Because you describe severe or worsening symptoms, arrange same-day in-person medical care. "
        if urgent else ""
    )
    return {
        "triage": "urgent_same_day" if urgent else "general_guidance",
        "message": prefix + first,
        "guidance": [
            {"title": item["title"], "detail": item["detail"]}
            for item in self_care[:3]
        ],
        "food_recommendations": food_recommendations,
        "medication_handoff": False,
        "red_flags": [],
        "emergency_actions": [],
        "disclaimer": DISCLAIMER,
    }
