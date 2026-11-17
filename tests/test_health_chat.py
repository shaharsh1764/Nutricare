"""Unit tests for the local bottom-left Health Chat safety engine."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from nutricare import health_chat


FOODS = json.loads((Path(__file__).parents[1] / "data" / "foods.json").read_text())["foods"]


def ask(message: str, conversation: dict | None = None):
    return health_chat.respond(message, {}, FOODS, conversation=conversation)


def test_emergency_wording_always_wins_and_has_local_protocol():
    reply = ask("I have chest pain and pressure")
    assert reply["triage"] == "emergency"
    assert reply["red_flags"]
    assert "112" in reply["message"]
    assert reply["food_recommendations"] == []
    assert reply["conversation"]["interrupted_by"] == "emergency"


@pytest.mark.parametrize("message", [
    "I have severe breathing difficulty",
    "My face is swelling after a severe allergic reaction",
    "I suddenly have one-sided weakness and trouble speaking",
    "I want to hurt myself",
])
def test_other_emergency_warning_signs_override_conversation(message):
    reply = ask(message, {"mode": "symptom", "next_question": "duration", "symptoms": ["headache"]})
    assert reply["triage"] == "emergency"
    assert "112" in reply["message"]


def test_free_text_medication_question_stays_handed_to_a_pharmacist_and_does_not_dose():
    reply = ask("What tablet and dose should I take for a headache?")
    text = json.dumps(reply).lower()
    assert reply["triage"] == "pharmacist_handoff"
    assert reply["medication_handoff"] is True
    assert "pharmacist" in text and "otc info" in text
    assert not re.search(r"\b\d+(?:\.\d+)?\s*mg\b", text)


def test_sick_starts_symptom_conversation_without_repeating_welcome():
    reply = ask("I am sick")
    assert reply["conversation"]["next_question"] == "symptoms"
    assert "what symptoms" in reply["message"].lower()
    assert "what would you like help with" not in reply["message"].lower()


def test_greeting_is_friendly_and_does_not_hide_a_symptom():
    greeting = ask("Hi")
    assert greeting["message"].startswith("Hi!")
    symptomatic_greeting = ask("Hi, I am sick")
    assert symptomatic_greeting["conversation"]["next_question"] == "symptoms"
    feeling_good = ask("I am feeling good")
    assert "glad" in feeling_good["message"].lower()


def test_text_only_quick_start_mood_and_body_pain_messages_start_a_safe_follow_up():
    for message, label in [("I have body pain", "body pain"),
                           ("I feel stressed or anxious", "stress or anxiety"),
                           ("I am feeling low", "low mood")]:
        reply = ask(message)
        assert reply["conversation"]["next_question"] == "duration"
        assert label in reply["conversation"]["symptoms"]


def test_headache_and_weakness_follow_up_remembers_answers():
    sick = ask("sick")
    symptoms = ask("I have a headache and feel weak", sick["conversation"])
    assert symptoms["conversation"]["next_question"] == "duration"
    assert "how long" in symptoms["message"].lower()

    duration = ask("Since yesterday", symptoms["conversation"])
    assert duration["conversation"]["duration"] == "Since yesterday"
    assert duration["conversation"]["next_question"] == "severity"
    assert "scale of 1 to 10" in duration["message"].lower()

    complete = ask("6", duration["conversation"])
    assert complete["conversation"]["status"] == "complete"
    assert "headache and weakness" in complete["message"].lower()
    assert "since yesterday" in complete["message"].lower()
    assert "cannot tell what is causing" in complete["message"].lower()  # no diagnosis claim

    corrected = ask("Actually, since today", complete["conversation"])
    assert corrected["conversation"]["duration"] == "since today"
    assert "since today" in corrected["message"].lower()


def test_fever_flow_asks_temperature_then_duration_and_other_symptoms():
    fever = ask("I have a fever")
    assert fever["conversation"]["next_question"] == "temperature"
    assert "thermometer" in fever["message"].lower()

    duration = ask("38.4 C", fever["conversation"])
    assert duration["conversation"]["next_question"] == "duration"
    associated = ask("Since yesterday", duration["conversation"])
    assert associated["conversation"]["next_question"] == "associated"
    assert "other symptoms" in associated["message"].lower()


def test_unclear_follow_up_asks_for_clarification_without_inventing_symptoms():
    reply = ask("I don't know", {"mode": "symptom", "next_question": "symptoms", "symptoms": []})
    assert reply["conversation"]["next_question"] == "symptoms"
    assert "describe" in reply["message"].lower()
    assert reply["conversation"]["symptoms"] == []


def test_nutrition_and_hydration_questions_receive_relevant_safe_guidance():
    nutrition = ask("What should I eat when I feel nauseous?")
    assert nutrition["triage"] == "general_guidance"
    assert nutrition["food_recommendations"]
    dataset_names = {food["name"] for food in FOODS}
    assert all(food["name"] in dataset_names for food in nutrition["food_recommendations"])

    hydration = ask("How much water should I drink?")
    assert "hydration needs vary" in hydration["message"].lower()
    assert hydration["guidance"]


def test_education_question_is_answered_without_diagnosing():
    reply = ask("What is diabetes?")
    assert "long-term condition" in reply["message"].lower()
    assert "diagnosed" in reply["message"].lower()
    assert reply["triage"] == "general_guidance"


def test_new_conversation_state_does_not_reuse_previous_answers():
    prior = {"mode": "symptom", "next_question": "severity", "symptoms": ["headache"], "duration": "yesterday"}
    reply = ask("I feel tired", conversation=None)
    assert reply["conversation"]["next_question"] == "duration"
    assert reply["conversation"]["symptoms"] == ["fatigue"]
    assert "yesterday" not in reply["message"].lower()
    assert prior["duration"] == "yesterday"  # no mutation of saved prior state


def test_non_health_prompt_gets_professional_out_of_scope_redirect():
    reply = ask("Write a poem about a mountain")
    assert reply["triage"] == "out_of_scope"
    assert "can’t assist with unrelated requests" in reply["message"].lower()
    assert "health education" in reply["message"].lower()
    assert "rephrase" in reply["message"].lower()
    assert reply["guidance"] == []
    assert reply["food_recommendations"] == []


def test_unrecognized_symptom_wording_gets_rephrase_prompt_without_guidance():
    reply = ask("sar dard")
    assert reply["guidance"] == []
    assert reply["food_recommendations"] == []
    assert "rephrase" in reply["message"].lower()
    assert reply["triage"] == "out_of_scope"


def test_unmatched_health_language_gets_default_clarification_not_a_guessed_answer():
    reply = ask("My wellness energy feels unusual")
    assert reply["triage"] == "clarification"
    assert "not sure i understood" in reply["message"].lower()
    assert "rephrase your question" in reply["message"].lower()
    assert reply["guidance"] == []
    assert reply["food_recommendations"] == []


def test_unrelated_custom_message_during_follow_up_gets_scope_redirect_without_losing_state():
    started = ask("I have a headache")
    reply = ask("Write a poem about it", started["conversation"])

    assert reply["triage"] == "out_of_scope"
    assert "can’t assist with unrelated requests" in reply["message"].lower()
    assert reply["conversation"] == started["conversation"]

    resumed = ask("Since yesterday", reply["conversation"])
    assert resumed["conversation"]["duration"] == "Since yesterday"
    assert resumed["conversation"]["next_question"] == "severity"


def test_severe_non_flagged_wording_gets_same_day_direction():
    reply = ask("I have a severe headache that is getting worse")
    assert reply["triage"] == "urgent_same_day"
    assert "same-day" in reply["message"]


@pytest.mark.parametrize("message", ["", " " * 4, "a" * 801])
def test_message_validation(message):
    with pytest.raises(ValueError):
        ask(message)


def test_engine_mode_is_explicitly_local():
    mode = health_chat.engine_mode()
    assert mode["online_ai_used"] is False
    assert "pharmacist" in mode["medication_policy"].lower()
