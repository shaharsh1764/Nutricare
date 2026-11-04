"""Safety-critical tests for the Health Assistant rule engine (v2)."""

import json
import re

import pytest

from nutricare import assistant


def run(primary, severity=3, duration="today", associated=None, notes="", warning_signs=None):
    return assistant.assess({"primary": primary, "severity": severity,
                             "duration": duration, "associated": associated or [],
                             "notes": notes, "warning_signs": warning_signs or []})


# ---------------------------------------------------------------- emergency screen

@pytest.mark.parametrize("text", [
    "chest pain and tightness",
    "sudden numbness in one arm and slurred speech",
    "difficulty breathing after running",
    "I passed out in class",
    "worst headache of my life",
    "swelling of throat and trouble swallowing",
    "vomiting blood",
])
def test_red_flags_trigger_emergency(text):
    result = run(text)
    assert result["triage"] == "emergency"
    assert result["red_flags"], "red flag label should be reported"
    assert result["emergency_actions"], "emergency must produce an action line"
    assert "112" in result["emergency_actions"][0] or "911" in result["emergency_actions"][0]


def test_emergency_flag_in_free_text_notes_too():
    result = run("tiredness", notes="also had chest pressure briefly")
    assert result["triage"] == "emergency"
    assert any(f["id"] == "chest_pain" for f in result["red_flags"])


def test_warning_sign_selection_triggers_emergency_despite_mild_pattern():
    """A ticked warning sign wins even when everything else looks low-risk."""
    result = run("fatigue", severity=1, duration="today", warning_signs=["chest_pain"])
    assert result["triage"] == "emergency"
    assert [f["id"] for f in result["red_flags"]] == ["chest_pain"]
    assert result["reported_facts"]["warning_signs_selected"] == [
        "Chest pain, pressure or tightness"]


def test_removing_one_warning_sign_removes_only_that_flag():
    both = run("tired", warning_signs=["chest_pain", "stroke"])
    assert {f["id"] for f in both["red_flags"]} == {"chest_pain", "stroke"}
    only_stroke = run("tired", warning_signs=["stroke"])
    assert {f["id"] for f in only_stroke["red_flags"]} == {"stroke"}
    assert only_stroke["triage"] == "emergency"  # still emergency, other flag intact
    none = run("tired", warning_signs=[])
    assert none["red_flags"] == [] and none["triage"] == "self_care"


def test_unknown_warning_sign_ids_are_ignored_safely():
    result = run("headache", warning_signs=["not_a_real_sign"])
    assert result["red_flags"] == []
    assert result["triage"] == "self_care"


def test_flag_screen_independent_of_explanation_generator():
    """'chest pain' matches no knowledge-base entry, yet the screen still fires;
    and the generator still runs (its output neither adds nor removes flags)."""
    result = run("chest pain")
    assert result["triage"] == "emergency"
    assert len(result["possibilities"]) >= 1  # generator ran independently
    mild = run("fatigue")
    assert mild["red_flags"] == []            # generator matches cannot create flags
    assert mild["triage"] == "self_care"


# ---------------------------------------------------------------- cautious wording

def test_fatigue_alone_never_infers_mechanisms():
    result = run("fatigue and mild brain fog")
    blob = json.dumps(result["possibilities"] + result["self_care"]).lower()
    for forbidden in ("glucose", "insulin", "deficien", "dehydrat", "anaemia", "anemia"):
        assert forbidden not in blob, f"mechanism inferred from fatigue alone: {forbidden}"
    assert any("single symptom with no additional context" in note
               for note in result["caution_notes"])


def test_cautious_language_no_asserted_causes():
    for primary in ["headache", "bloating", "dizziness", "nausea"]:
        blob = json.dumps(run(primary)["possibilities"]).lower()
        assert "will cause" not in blob and "is caused by" not in blob
        assert "cannot" in blob or "not possible" in blob  # uncertainty stated


def test_ambiguous_input_handled_cautiously():
    result = run("weird feeling, not sure what it is")
    assert result["triage"] == "self_care"
    assert result["red_flags"] == []
    assert any("no specific educational entry matched" in note.lower()
               for note in result["caution_notes"])
    assert result["possibilities"][0]["tag"].startswith("Possible")
    assert result["disclaimer"] and result["limitations"]


def test_multi_symptom_input_flags_ambiguity():
    result = run("fatigue plus a headache")
    assert any("several symptom areas" in note for note in result["caution_notes"])


def test_reported_facts_echoed_verbatim_and_separate():
    result = run("tired after lunch", severity=4, duration="2-3d",
                 associated=["Skipped a meal"], notes="mostly after roti",
                 warning_signs=[])
    facts = result["reported_facts"]
    assert facts["primary"] == "tired after lunch"
    assert facts["severity"] == 4 and facts["duration"] == "2-3d"
    assert facts["associated"] == ["Skipped a meal"]
    assert facts["notes"] == "mostly after roti"
    assert facts["warning_signs_selected"] == []
    # facts block must not contain explanation language
    assert "glucose" not in json.dumps(facts).lower()


# ---------------------------------------------------------------- general safety

def test_mild_symptom_is_self_care_with_possibilities():
    result = run("fatigue and mild post-lunch brain fog")
    assert result["triage"] == "self_care"
    assert len(result["possibilities"]) >= 1
    assert len(result["self_care"]) >= 1
    assert result["references"], "must cite general references"


def test_high_severity_without_red_flag_is_urgent_same_day():
    result = run("headache", severity=9)
    assert result["triage"] == "urgent_same_day"


def test_long_duration_adds_clinician_advice():
    result = run("bloating", duration=">2w")
    assert any("clinician" in line.lower() for line in result["seek_care"])


def test_no_fabricated_probabilities_anywhere():
    for primary in ["fatigue", "headache", "chest pain", "bloating", "fever"]:
        blob = json.dumps(run(primary)).lower()
        assert not re.search(r"\d+(\.\d+)?\s*(%|percent)\s*(probability|chance|risk|likelihood)",
                             blob), f"probability claim leaked for {primary}"


def test_no_medication_dosing():
    for primary in ["fatigue", "headache", "fever", "muscle ache"]:
        blob = json.dumps(run(primary)["self_care"]).lower()
        assert not re.search(r"take\s+\d+(\.\d+)?\s*(mg|mcg|iu)\b", blob)
        assert "ibuprofen" not in blob and "paracetamol" not in blob


def test_disclaimer_and_limitations_always_present():
    for primary in ["fatigue", "chest pain", "nothing matches this"]:
        result = run(primary)
        assert "not a medical diagnosis" in result["disclaimer"].lower()
        assert len(result["limitations"]) >= 3


def test_possibilities_worded_as_possibilities():
    result = run("fatigue")
    for possibility in result["possibilities"]:
        assert possibility["tag"] == "Possible — general information, not a diagnosis"


def test_validation_errors():
    with pytest.raises(ValueError):
        assistant.assess({"primary": "", "severity": 3, "duration": "today"})
    with pytest.raises(ValueError):
        assistant.assess({"primary": "headache", "severity": 42, "duration": "today"})
    with pytest.raises(ValueError):
        assistant.assess({"primary": "headache", "severity": 3, "duration": "forever"})


def test_engine_mode_is_truthful():
    mode = assistant.engine_mode()
    assert mode["online_ai_used"] is False
    assert "rule-based" in mode["label"]


def test_profile_context_is_echoed_not_invented():
    profile = {"allergies": ["Lactose intolerance"], "medications": ["Vitamin D3"]}
    result = assistant.assess({"primary": "bloating", "severity": 2, "duration": "today",
                               "associated": [], "notes": ""}, profile)
    assert any("Lactose intolerance" in note for note in result["context_notes"])
    assert any("your own reported context" in note for note in result["context_notes"])


def test_screen_red_flags_unit():
    flags = assistant.screen_red_flags("she fainted once", [])
    assert [f["id"] for f in flags] == ["faint_seizure"]
    flags = assistant.screen_red_flags("", ["breathing", "bleeding"])
    assert [f["id"] for f in flags] == ["breathing", "bleeding"]
    assert assistant.screen_red_flags("all good", []) == []
