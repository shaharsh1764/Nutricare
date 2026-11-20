"""Server-side state and validation for the option-based Health Assistant flow.

The browser renders the questions, but the expected step, accepted answer, and
final assessment payload are independently verified and held in the signed
Flask session. Free-text symptom recognition reuses the guided UI's existing
explicit matchers; it does not translate or guess unfamiliar symptom wording.
"""
from __future__ import annotations

import re
from typing import Any

from . import assistant


class FlowStateError(ValueError):
    """The request does not match the server's current guided-flow state."""


class InvalidAnswerError(ValueError):
    """The answer is not valid for the current guided-flow step."""


SYMPTOM_LABELS = {
    "feeling_good": "Feeling good",
    "fatigue": "Feeling tired",
    "headache": "Headache",
    "fever": "Fever",
    "dizziness": "Dizziness",
    "nausea": "Nausea",
    "body_pain": "Body pain",
    "stress_anxiety": "Stressed or anxious",
    "low_mood": "Feeling low",
}

# These patterns are the existing free-text Other matchers from the guided UI.
# Keep this list deliberately aligned; do not add transliterations or guesses.
GUIDED_TEXT_SYMPTOM_MATCHERS = (
    ("fatigue", re.compile(r"\b(tired|fatigue|exhausted|low energy|sleepy)\b", re.I)),
    ("headache", re.compile(r"\b(headache|migraine)\b", re.I)),
    ("fever", re.compile(r"\b(fever|high temperature)\b", re.I)),
    ("dizziness", re.compile(r"\b(dizz(?:y|iness)|lightheaded|vertigo)\b", re.I)),
    ("nausea", re.compile(r"\b(nausea|nauseous|vomit(?:ing)?)\b", re.I)),
    ("body_pain", re.compile(r"\b(body pain|muscle aches?|joint pain|aches?)\b", re.I)),
    ("stress_anxiety", re.compile(r"\b(stress(?:ed)?|anxious|anxiety)\b", re.I)),
    ("low_mood", re.compile(r"\b(low mood|feeling low|feel low|sad|depressed)\b", re.I)),
    ("feeling_good", re.compile(r"\b(feeling good|feel good|feeling well|feel well)\b", re.I)),
)

DURATION_VALUES = ("just_started", "morning", "yesterday", "two_three_days", "more_three_days")
SEVERITY_VALUES = ("2", "5", "8", "10")
CONDITION_LABELS = {
    "none": "None",
    "diabetes": "Diabetes",
    "pre_diabetes": "Pre-diabetes",
    "high_cholesterol": "High cholesterol",
    "hypertension": "Hypertension",
    "pcos": "PCOS",
    "thyroid": "Thyroid condition",
    "sleep_problems": "Sleep problems",
    "anxiety_depression": "Anxiety or depression",
    "other": "Other",
}

# Each step's accepted option values and input semantics mirror the guided UI.
STEP_OPTIONS: dict[str, tuple[str, ...]] = {
    "safety": ("none", "worst_headache", "chest_pain", "breathing", "stroke",
               "faint_seizure", "confusion", "anaphylaxis", "self_harm"),
    "headache_duration": DURATION_VALUES,
    "headache_severity": SEVERITY_VALUES,
    "headache_location": ("forehead", "temples", "back", "one_side", "whole_head"),
    "headache_associated": ("nausea", "light_sensitivity", "neck_stiffness", "vision_speech", "none"),
    "fatigue_duration": DURATION_VALUES,
    "fatigue_sleep": ("well", "somewhat", "poorly", "very_poorly"),
    "fatigue_severity": SEVERITY_VALUES,
    "fatigue_associated": ("fever_chills", "headache", "dizziness", "short_breath", "none"),
    "fever_duration": DURATION_VALUES,
    "fever_temperature": ("not_measured", "under_38", "38_39_5", "above_39_5"),
    "fever_associated": ("chills", "cough", "body_pain", "stiff_neck_rash", "none"),
    "fever_fluids": ("yes", "some", "no"),
    "dizziness_duration": DURATION_VALUES,
    "dizziness_severity": SEVERITY_VALUES,
    "dizziness_associated": ("fainting", "chest_pain", "breathing", "none"),
    "nausea_duration": DURATION_VALUES,
    "nausea_severity": SEVERITY_VALUES,
    "nausea_fluids": ("yes", "some", "no"),
    "body_pain_duration": DURATION_VALUES,
    "body_pain_severity": SEVERITY_VALUES,
    "body_pain_location": ("muscles", "joints", "all_over", "other_location"),
    "wellbeing_duration": DURATION_VALUES,
    "wellbeing_severity": SEVERITY_VALUES,
    "wellbeing_safety": ("self_harm", "none"),
    "conditions": tuple(CONDITION_LABELS),
}

MULTIPLE_STEPS = {
    "safety", "headache_associated", "fatigue_associated", "fever_associated",
    "dizziness_associated", "wellbeing_safety", "conditions",
}
OPTIONAL_STEPS = {"conditions"}
NONE_VALUE = {
    "safety": "none", "headache_associated": "none", "fatigue_associated": "none",
    "fever_associated": "none", "dizziness_associated": "none",
    "wellbeing_safety": "none", "conditions": "none",
}
WARNING_VALUE_IDS = {
    "worst_headache": "worst_headache", "chest_pain": "chest_pain",
    "breathing": "breathing", "stroke": "stroke", "faint_seizure": "faint_seizure",
    "confusion": "confusion", "anaphylaxis": "anaphylaxis", "self_harm": "self_harm",
    "vision_speech": "stroke", "short_breath": "breathing", "stiff_neck_rash": "fever_neck",
    "fainting": "faint_seizure", "no": "no_fluids",
}

OPTION_LABELS = {
    **CONDITION_LABELS,
    "none": "None",
    "just_started": "Just started", "morning": "Since this morning",
    "yesterday": "Since yesterday", "two_three_days": "2–3 days",
    "more_three_days": "More than 3 days",
    "2": "1–3: Mild", "5": "4–6: Moderate", "8": "7–8: Severe", "10": "9–10: Extremely severe",
    "forehead": "Forehead", "temples": "Temples", "back": "Back of head",
    "one_side": "One side", "whole_head": "Whole head", "nausea": "Nausea",
    "light_sensitivity": "Light sensitivity", "neck_stiffness": "Stiff neck",
    "vision_speech": "Vision or speech changes", "well": "Well", "somewhat": "Not as well as usual",
    "poorly": "Poorly", "very_poorly": "Very poorly", "fever_chills": "Fever or chills",
    "headache": "Headache", "dizziness": "Dizziness", "short_breath": "Severe breathing difficulty",
    "not_measured": "Not measured", "under_38": "Below 38°C", "38_39_5": "38°C to 39.5°C",
    "above_39_5": "Above 39.5°C", "chills": "Chills", "cough": "Cough",
    "body_pain": "Body pain", "stiff_neck_rash": "Stiff neck or rash", "yes": "Yes",
    "some": "Only small amounts", "no": "No, I cannot keep fluids down",
    "fainting": "Fainting or loss of consciousness", "chest_pain": "Chest pain or pressure",
    "breathing": "Severe breathing difficulty", "muscles": "Muscles", "joints": "Joints",
    "all_over": "All over", "other_location": "Another area", "self_harm": "Thoughts of self-harm",
    "worst_headache": "Sudden, worst-ever headache", "confusion": "New confusion or hard to wake",
    "anaphylaxis": "Severe allergic reaction or throat/facial swelling", "stroke": "Possible stroke signs",
}


def normalize_text(text: Any) -> str:
    """Only trim/collapse whitespace and case-fold; never translate or infer."""
    return re.sub(r"\s+", " ", str(text or "").strip()).casefold()


def guided_symptoms_from_text(text: Any) -> list[str]:
    normalized = normalize_text(text)
    return list(dict.fromkeys(
        symptom for symptom, pattern in GUIDED_TEXT_SYMPTOM_MATCHERS if pattern.search(normalized)
    ))


def build_step_ids(symptoms: list[str]) -> list[str]:
    """Produce the same ordered guided steps as the existing UI builder."""
    steps = ["symptoms"]
    needs_safety = any(symptom != "feeling_good" for symptom in symptoms)
    if needs_safety:
        steps.append("safety")
    if "headache" in symptoms:
        steps.extend(("headache_duration", "headache_severity", "headache_location", "headache_associated"))
    if "fatigue" in symptoms:
        steps.extend(("fatigue_duration", "fatigue_sleep", "fatigue_severity", "fatigue_associated"))
    if "fever" in symptoms:
        steps.extend(("fever_duration", "fever_temperature", "fever_associated", "fever_fluids"))
    if "dizziness" in symptoms:
        steps.extend(("dizziness_duration", "dizziness_severity", "dizziness_associated"))
    if "nausea" in symptoms:
        steps.extend(("nausea_duration", "nausea_severity", "nausea_fluids"))
    if "body_pain" in symptoms:
        steps.extend(("body_pain_duration", "body_pain_severity", "body_pain_location"))
    if "stress_anxiety" in symptoms or "low_mood" in symptoms:
        steps.extend(("wellbeing_duration", "wellbeing_severity", "wellbeing_safety"))
    steps.extend(("conditions", "review"))
    return steps


def initial_state(user_id: int) -> dict:
    return {"user_id": user_id, "step_ids": ["symptoms"], "index": 0,
            "symptoms": [], "answers": {}}


def state_for_user(state: Any, user_id: int) -> dict:
    if not isinstance(state, dict) or state.get("user_id") != user_id:
        raise FlowStateError("Start a new guided assessment before answering.")
    step_ids = state.get("step_ids")
    index = state.get("index")
    if not isinstance(step_ids, list) or not isinstance(index, int) or not 0 <= index < len(step_ids):
        raise FlowStateError("The guided assessment state is invalid. Please restart it.")
    return state


def _values_and_other(answer: Any) -> tuple[list[str], str]:
    if not isinstance(answer, dict):
        raise InvalidAnswerError("Please answer the current question before continuing.")
    values = answer.get("values", [])
    other = answer.get("other", "")
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise InvalidAnswerError("The answer format does not match this question.")
    if not isinstance(other, str) or len(other) > 400:
        raise InvalidAnswerError("Additional details must be 400 characters or fewer.")
    return list(dict.fromkeys(values)), other.strip()


def validate_answer(step_id: str, answer: Any) -> dict:
    """Validate and sanitize a single answer for its exact current step."""
    values, other = _values_and_other(answer)
    if step_id == "symptoms":
        unknown = [value for value in values if value not in (*SYMPTOM_LABELS, "other")]
        if unknown:
            raise InvalidAnswerError("Select a symptom from the supported choices.")
        typed_matches = guided_symptoms_from_text(other) if other else []
        if other and not typed_matches:
            raise InvalidAnswerError(
                "I couldn't recognize that symptom. Please select a supported symptom "
                "or try describing it using different wording. I can't safely assess "
                "a symptom I don't understand."
            )
        symptoms = [value for value in values if value != "other"]
        symptoms.extend(value for value in typed_matches if value not in symptoms)
        if "other" in values and not other:
            raise InvalidAnswerError(
                "I couldn't recognize that symptom. Please select a supported symptom "
                "or try describing it using different wording. I can't safely assess "
                "a symptom I don't understand."
            )
        if not symptoms:
            raise InvalidAnswerError("Select a supported symptom or describe one the assistant recognizes.")
        if "feeling_good" in symptoms and len(symptoms) > 1:
            raise InvalidAnswerError("Feeling good cannot be selected together with other symptoms.")
        return {"values": symptoms, "other": ""}

    options = STEP_OPTIONS.get(step_id)
    if options is None:
        raise FlowStateError("This question is not part of the guided assessment.")
    if any(value not in options for value in values):
        raise InvalidAnswerError("Choose an answer shown for the current question.")
    if step_id not in MULTIPLE_STEPS and len(values) > 1:
        raise InvalidAnswerError("Choose one answer for the current question.")
    none_value = NONE_VALUE.get(step_id)
    if none_value and none_value in values and (len(values) > 1 or other):
        raise InvalidAnswerError("The ‘None’ answer cannot be combined with other selections or details.")
    if not values and step_id not in OPTIONAL_STEPS:
        raise InvalidAnswerError("Select an answer shown for this question before continuing.")
    return {"values": values, "other": other}


def _answer_text(answer: Any) -> tuple[str, list[str]]:
    """Extract emergency-screen text and explicit warning ids from raw input."""
    if not isinstance(answer, dict):
        return "", []
    values = answer.get("values", [])
    if not isinstance(values, list):
        values = []
    text = answer.get("other", "")
    if not isinstance(text, str):
        text = ""
    warning_ids = [WARNING_VALUE_IDS[value] for value in values
                   if isinstance(value, str) and value in WARNING_VALUE_IDS]
    return " ".join([text, *(str(value) for value in values)]), warning_ids


def emergency_for_answer(state: dict, answer: Any) -> list[dict]:
    prior_text: list[str] = []
    prior_warning_ids: list[str] = []
    for prior in state.get("answers", {}).values():
        text, warning_ids = _answer_text(prior)
        prior_text.append(text)
        prior_warning_ids.extend(warning_ids)
    current_text, current_warning_ids = _answer_text(answer)
    return assistant.screen_red_flags(
        " ".join([*prior_text, current_text]),
        [*prior_warning_ids, *current_warning_ids],
    )


def accept_answer(state: dict, step_id: str, answer: Any) -> tuple[dict, str]:
    """Enforce expected step, validate its answer, then advance exactly once."""
    expected = state["step_ids"][state["index"]]
    if step_id != expected:
        raise FlowStateError(f"Expected the ‘{expected}’ step, not ‘{step_id}’.")
    if expected == "review":
        raise FlowStateError("Confirm the completed review instead of submitting another answer.")
    clean = validate_answer(expected, answer)
    if expected == "symptoms":
        state = dict(state)
        state["symptoms"] = clean["values"]
        state["step_ids"] = build_step_ids(clean["values"])
        state["answers"] = {"symptoms": clean}
        state["index"] = 1
    else:
        answers = dict(state.get("answers", {}))
        answers[expected] = clean
        state = dict(state, answers=answers, index=state["index"] + 1)
    return state, state["step_ids"][state["index"]]


def go_back(state: dict, step_id: str) -> dict:
    if state["index"] <= 0:
        raise FlowStateError("There is no earlier question in this assessment.")
    target_index = state["index"] - 1
    expected_target = state["step_ids"][target_index]
    if step_id != expected_target:
        raise FlowStateError("The requested previous question does not match the guided flow.")
    if expected_target == "symptoms":
        return initial_state(state["user_id"])
    answers = dict(state.get("answers", {}))
    for discarded in state["step_ids"][target_index + 1:]:
        answers.pop(discarded, None)
    return dict(state, answers=answers, index=target_index)


def assessment_payload(state: dict) -> dict:
    """Build final data only from backend-validated, question-scoped answers."""
    symptom_values = state["symptoms"]
    primary = "; ".join(SYMPTOM_LABELS[value] for value in symptom_values)
    answers = state.get("answers", {})
    duration_steps = [step for step in state["step_ids"] if step.endswith("_duration")]
    duration_value = answers.get(duration_steps[0], {}).get("values", [""])[0] if duration_steps else ""
    duration = {
        "just_started": "today", "morning": "today", "yesterday": "2-3d",
        "two_three_days": "2-3d", "more_three_days": "3-5d",
    }.get(duration_value, "today")
    severity_steps = [step for step in state["step_ids"] if step.endswith("_severity")]
    severity_value = answers.get(severity_steps[0], {}).get("values", [""])[0] if severity_steps else "3"
    try:
        severity = int(severity_value)
    except (TypeError, ValueError):
        severity = 3

    associated: list[str] = []
    notes: list[str] = []
    for step_id in state["step_ids"]:
        answer = answers.get(step_id, {})
        if answer.get("other"):
            notes.append(f"{step_id}: {answer['other']}")
        if ("associated" in step_id or step_id.endswith(("_location", "_sleep", "_fluids"))
                or step_id == "fever_temperature"):
            associated.extend(OPTION_LABELS.get(value, value) for value in answer.get("values", [])
                              if value != "none")
    condition_answer = answers.get("conditions", {"values": [], "other": ""})
    conditions = [CONDITION_LABELS[value] for value in condition_answer.get("values", [])
                  if value not in {"none", "other"}]
    if condition_answer.get("other"):
        conditions.append(condition_answer["other"])
    if conditions:
        notes.append(f"Reported existing conditions: {', '.join(conditions)}")

    warning_signs = []
    for answer in answers.values():
        for value in answer.get("values", []):
            warning_id = WARNING_VALUE_IDS.get(value)
            if warning_id and warning_id not in warning_signs:
                warning_signs.append(warning_id)
    return {
        "primary": primary,
        "duration": duration,
        "severity": severity,
        "associated": associated,
        "warning_signs": warning_signs,
        "notes": " | ".join(notes)[:400],
        "existing_conditions": conditions,
    }


def complete(state: dict) -> None:
    if state["step_ids"][state["index"]] != "review":
        raise FlowStateError("Complete each validated assessment question before confirming.")
    required = [step for step in state["step_ids"] if step not in OPTIONAL_STEPS | {"symptoms", "review"}]
    missing = [step for step in required if not state.get("answers", {}).get(step, {}).get("values")]
    if missing:
        raise FlowStateError("The guided assessment is missing a required validated answer.")
    if not state.get("symptoms"):
        raise FlowStateError("A supported symptom is required before the assessment can be completed.")
