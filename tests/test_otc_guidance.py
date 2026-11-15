"""Safety tests for the locked local OTC education reference."""
from __future__ import annotations

import pytest

from nutricare import otc_guidance


def screened_payload(topic: str, **overrides):
    payload = {
        "topic": topic,
        "warning_signs": [],
        "age_group": "age_16_plus",
        "medication_allergy": "no",
        "conditions": ["none"],
        "pregnancy_status": "not_applicable",
        "current_medicines": "no",
        "already_taken": "no",
    }
    if topic == "fever":
        payload.update({"fever_duration": "under_24_hours", "fever_level": "not_high"})
    payload.update(overrides)
    return payload


def test_fever_releases_source_cited_paracetamol_information_only_after_screening():
    result = otc_guidance.guidance(screened_payload("fever"))
    assert result["triage"] == "otc_education"
    assert result["eligible"] is True
    assert result["medication"]["generic_name"] == "Paracetamol"
    assert "500 mg" in result["medication"]["dosing"]
    assert "liver" in " ".join(result["medication"]["warnings"]).lower()
    assert len(result["medication"]["sources"]) >= 2
    assert all(source["source_last_reviewed"] for source in result["medication"]["sources"])


def test_common_allergy_symptoms_release_source_cited_cetirizine_information():
    result = otc_guidance.guidance(screened_payload("allergy_symptoms"))
    assert result["triage"] == "otc_education"
    assert result["medication"]["generic_name"] == "Cetirizine"
    text = " ".join(result["medication"]["warnings"]).lower()
    assert "drows" in text and "drive" in text
    assert "10 mg once a day" in result["medication"]["dosing"].lower()


def test_children_never_receive_adult_paracetamol_dosing():
    result = otc_guidance.guidance(screened_payload("fever", age_group="age_6_to_11"))
    assert result["triage"] == "pharmacist_handoff"
    assert result["eligible"] is False
    assert result["medication"]["dosing"] is None
    assert "child-specific" in result["medication"]["child_guidance"].lower()
    assert "500 mg" not in str(result["medication"]["child_guidance"]).lower()


def test_child_cetirizine_uses_the_age_matched_reference_not_the_adult_reference():
    result = otc_guidance.guidance(screened_payload("allergy_symptoms", age_group="age_2_to_5"))
    assert result["triage"] == "otc_education"
    assert "2.5 mg twice" in result["medication"]["dosing"].lower()
    assert "adult" not in result["medication"]["dosing"].lower()


@pytest.mark.parametrize("field,value", [
    ("medication_allergy", "yes"),
    ("medication_allergy", "not_sure"),
    ("current_medicines", "yes"),
    ("current_medicines", "not_sure"),
    ("already_taken", "yes"),
    ("pregnancy_status", "pregnant"),
])
def test_missing_or_risky_safety_answers_block_medication_specific_instruction(field, value):
    result = otc_guidance.guidance(screened_payload("fever", **{field: value}))
    assert result["triage"] == "pharmacist_handoff"
    assert result["eligible"] is False
    assert result["medication"]["dosing"] is None
    assert result["safety_reasons"]


def test_relevant_medical_condition_triggers_warning_and_blocks_dosing():
    result = otc_guidance.guidance(screened_payload("allergy_symptoms", conditions=["kidney_condition"]))
    assert result["triage"] == "pharmacist_handoff"
    assert result["medication"]["dosing"] is None
    assert "condition" in " ".join(result["safety_reasons"]).lower()


def test_persistent_or_high_fever_takes_priority_over_paracetamol_information():
    result = otc_guidance.guidance(screened_payload(
        "fever", fever_duration="three_days_or_more", fever_level="very_high_or_worsening"
    ))
    assert result["triage"] == "urgent_same_day"
    assert result["eligible"] is False
    assert result["medication"]["dosing"] is None
    assert "prompt in-person" in result["message"].lower()


def test_emergency_warning_sign_takes_priority_over_every_otc_branch():
    result = otc_guidance.guidance(screened_payload("allergy_symptoms", warning_signs=["anaphylaxis"]))
    assert result["triage"] == "emergency"
    assert result["medication"] is None
    assert result["emergency_actions"]


def test_unsupported_concern_never_invents_an_otc_option():
    result = otc_guidance.guidance({"topic": "other", "warning_signs": []})
    assert result["triage"] == "pharmacist_handoff"
    assert result["medication"] is None
    assert "no source-reviewed" in result["message"].lower()


def test_only_predefined_options_are_accepted():
    with pytest.raises(ValueError):
        otc_guidance.guidance(screened_payload("fever", age_group="25 years old"))
    with pytest.raises(ValueError):
        otc_guidance.guidance(screened_payload("fever", conditions=["none", "liver_condition"]))
    with pytest.raises(ValueError):
        otc_guidance.guidance(screened_payload("fever", warning_signs=["made_up"]))
