"""Unit tests for the local bottom-left Health Chat safety engine."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from nutricare import health_chat


FOODS = json.loads((Path(__file__).parents[1] / "data" / "foods.json").read_text())["foods"]


def test_emergency_wording_always_wins_and_has_local_protocol():
    reply = health_chat.respond("I have chest pain and pressure", {}, FOODS)
    assert reply["triage"] == "emergency"
    assert reply["red_flags"]
    assert "112" in reply["message"]
    assert reply["food_recommendations"] == []


def test_medication_question_is_handed_to_a_pharmacist_without_a_drug_choice():
    reply = health_chat.respond("What tablet and dose should I take for a headache?", {}, FOODS)
    text = json.dumps(reply).lower()
    assert reply["triage"] == "pharmacist_handoff"
    assert reply["medication_handoff"] is True
    assert "pharmacist" in text
    assert "ibuprofen" not in text and "paracetamol" not in text


def test_nausea_food_options_come_from_catalogue_and_respect_preferences():
    reply = health_chat.respond("I feel nauseous today", {"allergies": [], "dietary_prefs": ["vegan"]}, FOODS)
    assert reply["triage"] == "general_guidance"
    assert reply["food_recommendations"]
    dataset_names = {food["name"] for food in FOODS}
    assert all(food["name"] in dataset_names for food in reply["food_recommendations"])
    assert all(food["name"] != "Curd / dahi (plain, whole milk)" for food in reply["food_recommendations"])


def test_non_health_prompt_is_refused_to_keep_chat_in_scope():
    reply = health_chat.respond("Write a poem about a mountain", {}, FOODS)
    assert reply["triage"] == "out_of_scope"
    assert "health and nutrition" in reply["message"].lower()


def test_severe_non_flagged_wording_gets_same_day_direction():
    reply = health_chat.respond("I have a severe headache that is getting worse", {}, FOODS)
    assert reply["triage"] == "urgent_same_day"
    assert "same-day" in reply["message"]


@pytest.mark.parametrize("message", ["", " " * 4, "a" * 801])
def test_message_validation(message):
    with pytest.raises(ValueError):
        health_chat.respond(message, {}, FOODS)


def test_engine_mode_is_explicitly_local():
    mode = health_chat.engine_mode()
    assert mode["online_ai_used"] is False
    assert "pharmacist" in mode["medication_policy"].lower()
