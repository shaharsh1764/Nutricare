"""Locked local OTC medicine education rules for the Health Assistant.

This module deliberately has a very small scope.  It reads a versioned local
reference file; it does not fetch web pages, call an AI service, infer a
condition, check interactions, or construct a dose.  A source-cited reference
is released only after the client has collected each required *option* and this
module has repeated the emergency and safety checks on the server.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import assistant

REFERENCE_PATH = Path(__file__).parent.parent / "data" / "otc_medication_references.json"
CATALOG = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
MEDICATIONS = CATALOG["medications"]

TOPICS = {"fever", "mild_pain", "allergy_symptoms", "other"}
AGE_GROUPS = {"under_2", "age_2_to_5", "age_6_to_11", "age_12_to_15", "age_16_plus", "not_sure", "prefer_not"}
YES_NO_UNKNOWN = {"no", "yes", "not_sure", "prefer_not"}
PREGNANCY_STATUS = {"not_applicable", "no", "pregnant", "breastfeeding", "not_sure", "prefer_not"}
CONDITIONS = {"none", "liver_condition", "kidney_condition", "regular_alcohol_use", "low_body_weight", "other_condition", "not_sure", "prefer_not"}
FEVER_DURATIONS = {"under_24_hours", "one_two_days", "three_days_or_more", "not_sure", "prefer_not"}
FEVER_LEVELS = {"not_measured", "not_high", "very_high_or_worsening", "not_sure", "prefer_not"}
KNOWN_WARNING_IDS = {sign["id"] for sign in assistant.WARNING_SIGNS}

TOPIC_TO_MEDICINE = {
    "fever": "paracetamol",
    "mild_pain": "paracetamol",
    "allergy_symptoms": "cetirizine",
}


def _choice(payload: dict[str, Any], key: str, allowed: set[str]) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{key} must be one of the predefined options")
    return value


def _conditions(payload: dict[str, Any]) -> list[str]:
    value = payload.get("conditions")
    if not isinstance(value, list) or not value or len(value) > len(CONDITIONS):
        raise ValueError("conditions must be a non-empty list of predefined options")
    if any(not isinstance(item, str) or item not in CONDITIONS for item in value):
        raise ValueError("conditions must contain only predefined options")
    unique = list(dict.fromkeys(value))
    if "none" in unique and len(unique) != 1:
        raise ValueError("conditions cannot combine None with another option")
    return unique


def _warning_signs(payload: dict[str, Any]) -> list[str]:
    value = payload.get("warning_signs", [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("warning_signs must be a list of predefined options")
    if any(item not in KNOWN_WARNING_IDS for item in value):
        raise ValueError("warning_signs contains an unknown option")
    return list(dict.fromkeys(value))


def _public_reference(medicine: dict[str, Any]) -> dict[str, Any]:
    """Information that is safe to show even when specific guidance is blocked.

    Dosing is deliberately omitted here.  Only the fully cleared branch below
    releases a fixed, source-reviewed reference sentence.
    """
    return {
        "generic_name": medicine["generic_name"],
        "also_known_as": list(medicine.get("also_known_as") or []),
        "intended_use": medicine["intended_use"],
        "warnings": list(medicine["warnings"]),
        "professional_advice": medicine["professional_advice"],
        "sources": list(medicine["sources"]),
        "reference_last_reviewed": medicine["reference_last_reviewed"],
        "dosing": None,
    }


def _base_result(topic: str, reported: dict[str, Any]) -> dict[str, Any]:
    return {
        "engine": "local-otc-reference-v1",
        "online_ai_used": False,
        "catalog_version": CATALOG["catalog_version"],
        "topic": topic,
        "reported": reported,
        "medication": None,
        "red_flags": [],
        "emergency_actions": [],
        "seek_care": [],
        "disclaimer": (
            "This is source-cited general medicine education, not a diagnosis, "
            "prescription, interaction check, or personal treatment plan."
        ),
    }


def _emergency_result(topic: str, reported: dict[str, Any], flags: list[dict]) -> dict[str, Any]:
    result = _base_result(topic, reported)
    result.update({
        "triage": "emergency",
        "eligible": False,
        "message": "An emergency warning sign was selected. Do not use OTC guidance now; seek emergency care immediately.",
        "red_flags": [{"id": flag["id"], "label": flag["label"], "action": flag["action"]} for flag in flags],
        "emergency_actions": [assistant.EMERGENCY_ACTION] + [flag["action"] for flag in flags],
    })
    return result


def _handoff_result(topic: str, reported: dict[str, Any], medicine: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    result = _base_result(topic, reported)
    result.update({
        "triage": "pharmacist_handoff",
        "eligible": False,
        "message": "I can provide only general source information here. A pharmacist or clinician should review this before you choose or use an OTC medicine.",
        "medication": _public_reference(medicine),
        "safety_reasons": reasons,
    })
    return result


def _normalise_payload(payload: dict[str, Any]) -> tuple[str, dict[str, Any], list[str]]:
    if not isinstance(payload, dict):
        raise ValueError("a JSON object is required")
    topic = _choice(payload, "topic", TOPICS)
    signs = _warning_signs(payload)
    reported: dict[str, Any] = {"warning_signs": signs}
    if topic == "other":
        return topic, reported, signs

    reported.update({
        "age_group": _choice(payload, "age_group", AGE_GROUPS),
        "medication_allergy": _choice(payload, "medication_allergy", YES_NO_UNKNOWN),
        "conditions": _conditions(payload),
        "pregnancy_status": _choice(payload, "pregnancy_status", PREGNANCY_STATUS),
        "current_medicines": _choice(payload, "current_medicines", YES_NO_UNKNOWN),
        "already_taken": _choice(payload, "already_taken", YES_NO_UNKNOWN),
    })
    if topic == "fever":
        reported["fever_duration"] = _choice(payload, "fever_duration", FEVER_DURATIONS)
        reported["fever_level"] = _choice(payload, "fever_level", FEVER_LEVELS)
    return topic, reported, signs


def guidance(payload: dict[str, Any]) -> dict[str, Any]:
    """Return one fully deterministic, validated OTC education response.

    Every branch is intentionally conservative.  Any unknown safety answer,
    condition, medicine use, allergy, pregnancy/breastfeeding status, or prior
    dose blocks the numeric reference and hands the person to a pharmacist or
    clinician.  The server repeats the warning-sign screen so a modified client
    cannot bypass the emergency priority.
    """
    topic, reported, selected_signs = _normalise_payload(payload)
    flags = assistant.screen_red_flags("", selected_signs)
    if flags:
        return _emergency_result(topic, reported, flags)

    if topic == "other":
        result = _base_result(topic, reported)
        result.update({
            "triage": "pharmacist_handoff",
            "eligible": False,
            "message": "NutriCare has no source-reviewed OTC education for that concern. Please ask a pharmacist or clinician rather than guessing a medicine.",
            "safety_reasons": ["No supported medicine topic was selected."],
        })
        return result

    medicine = MEDICATIONS[TOPIC_TO_MEDICINE[topic]]
    # A high or persistent fever must be assessed before an OTC medicine can
    # become the focus. The medicine may reduce fever temporarily but cannot
    # determine its cause or replace the assessment.
    if topic == "fever" and (reported["fever_duration"] == "three_days_or_more"
                              or reported["fever_level"] == "very_high_or_worsening"):
        result = _base_result(topic, reported)
        result.update({
            "triage": "urgent_same_day",
            "eligible": False,
            "message": "A fever lasting several days or a very high/worsening fever needs prompt in-person medical assessment today. Paracetamol may temporarily reduce fever, but it must not delay that assessment.",
            "medication": _public_reference(medicine),
            "safety_reasons": ["The fever pattern selected needs prompt in-person assessment."],
            "seek_care": ["Arrange same-day in-person medical advice.", "Seek emergency care now if an emergency warning sign appears."],
        })
        return result

    reasons: list[str] = []
    if reported["medication_allergy"] == "yes":
        reasons.append("You reported a medication allergy.")
    elif reported["medication_allergy"] in {"not_sure", "prefer_not"}:
        reasons.append("Medication-allergy information is missing or uncertain.")
    if reported["conditions"] != ["none"]:
        if any(item in {"not_sure", "prefer_not"} for item in reported["conditions"]):
            reasons.append("Relevant medical-condition information is missing or uncertain.")
        else:
            reasons.append("You reported a medical condition, regular alcohol use, or low body weight that needs professional review.")
    if reported["pregnancy_status"] not in {"not_applicable", "no"}:
        reasons.append("Pregnancy or breastfeeding status needs professional review.")
    if reported["current_medicines"] != "no":
        reasons.append("Current-medicine information is missing, uncertain, or indicates another medicine is in use.")
    if reported["already_taken"] != "no":
        reasons.append("You may already have taken medicine for this symptom, so duplicate ingredients or doses need checking.")
    if reported["age_group"] in {"not_sure", "prefer_not"}:
        reasons.append("Age-group information is missing or uncertain.")
    if reasons:
        return _handoff_result(topic, reported, medicine, reasons)

    age_group = reported["age_group"]
    if medicine["generic_name"] == "Paracetamol" and age_group != "age_16_plus":
        result = _handoff_result(topic, reported, medicine, [
            "NutriCare does not provide a child paracetamol dose because a safe child dose requires the child-specific product, weight, and concentration."
        ])
        result["medication"]["child_guidance"] = medicine["child_guidance"]
        return result
    if medicine["generic_name"] == "Cetirizine" and age_group == "under_2":
        return _handoff_result(topic, reported, medicine, [
            "A child under 2 needs clinician advice before cetirizine is considered."
        ])

    medication = _public_reference(medicine)
    if medicine["generic_name"] == "Cetirizine" and age_group in {"age_2_to_5", "age_6_to_11", "age_12_to_15"}:
        medication["dosing"] = medicine["child_information"][age_group]
    else:
        medication["dosing"] = medicine["standard_adult_information"]

    result = _base_result(topic, reported)
    result.update({
        "triage": "otc_education",
        "eligible": True,
        "message": "Here is limited, source-cited general information. It is not a personal recommendation; follow the local product label and ask a pharmacist if anything changes or is uncertain.",
        "medication": medication,
        "safety_reasons": [],
    })
    return result
