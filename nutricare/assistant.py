"""NutriCare Health Assistant — offline rule-based triage & education engine.

SAFETY DESIGN (read this before touching the file):
  * This module NEVER diagnoses, NEVER outputs disease probabilities, and NEVER
    recommends medication doses.
  * The emergency warning-sign screen (`screen_red_flags`) is a SEPARATE function
    from the explanation generator (`explain_possibilities`). Flags are evaluated
    from (a) explicitly selected warning signs and (b) raw text, and they always
    win: a low-risk-looking overall pattern never suppresses them, and the
    explanation generator can neither add nor remove flags.
  * User-reported facts are echoed back verbatim in `reported_facts` and are kept
    strictly separate from `possibilities`, which are general educational entries
    selected by keyword and always labelled as possibilities.
  * Wording rule: no mechanism may be asserted from limited input. In particular
    fatigue alone must not be explained by blood-glucose changes, nutrient
    deficiencies, dehydration or any other medical condition.
  * References are general public-health education pages (NHS, CDC, Harvard
    Health Publishing, AAFP), cited as sources of general information only.
"""

from __future__ import annotations

import os
import re
from datetime import datetime

ENGINE_VERSION = "rule-based-v2"

DURATIONS = ("today", "2-3d", "3-5d", "1-2w", ">2w")
DURATION_LABELS = {"today": "Today", "2-3d": "2-3 days", "3-5d": "3-5 days",
                   "1-2w": "1-2 weeks", ">2w": "More than 2 weeks"}

DISCLAIMER = ("NutriCare Health Assistant provides general educational information only. "
              "It is not a medical diagnosis, not a substitute for professional medical "
              "advice, and it cannot examine you or see your test results.")

LIMITATIONS = [
    "This is a rule-based educational tool, not a diagnostic device and not a doctor.",
    "It cannot examine you, run tests, or confirm or rule out any condition.",
    "It does not estimate probabilities of disease and does not prescribe or dose medications.",
    "Educational entries are picked by simple keyword matching from what you type; that is not individualised clinical reasoning.",
    "Symptoms with many possible causes can look identical here; only a clinician can differentiate them.",
    "If anything feels seriously wrong, trust your judgement and seek urgent care regardless of what this tool says.",
]

REFERENCES = [
    {"name": "NHS (UK) — self-care and symptom overview pages", "url": "https://www.nhs.uk"},
    {"name": "CDC — hydration, sleep and general health guidance", "url": "https://www.cdc.gov"},
    {"name": "Harvard Health Publishing — consumer health education", "url": "https://www.health.harvard.edu"},
    {"name": "American Academy of Family Physicians (AAFP) — patient education", "url": "https://www.aafp.org"},
]

# ------------------------------------------------------------------ warning signs
# Independent emergency screen. Each sign can trigger either by being explicitly
# selected in the checklist (id) or by appearing in any free text (regex).
# Removing one selected sign removes only that sign's flag; others stay.
WARNING_SIGNS = [
    {"id": "chest_pain", "label": "Chest pain, pressure or tightness",
     "regex": r"chest (pain|pressure|tightness|crush)",
     "action": "Chest pain can be a sign of a heart emergency. Get emergency care now."},
    {"id": "breathing", "label": "Difficulty breathing or severe shortness of breath",
     "regex": r"(difficulty|trouble) breath|shortness of breath|can'?t breathe|cannot breathe",
     "action": "Breathing difficulty needs immediate emergency assessment."},
    {"id": "stroke", "label": "Stroke signs: sudden numbness/weakness, face droop, speech or vision change",
     "regex": r"sudden (numbness|weakness)|face droop|drooping face|slurred speech|trouble speaking|sudden (vision loss|blindness)|one[- ]sided weakness",
     "action": "These are possible stroke signs. Emergency treatment is time-critical — call now."},
    {"id": "faint_seizure", "label": "Fainting, loss of consciousness or a seizure",
     "regex": r"faint|passed out|lost consciousness|seizure|convulsion",
     "action": "Loss of consciousness or a seizure needs urgent medical evaluation."},
    {"id": "confusion", "label": "New confusion or being hard to wake",
     "regex": r"confusion|disoriented|hard to wake",
     "action": "New confusion is a medical emergency sign."},
    {"id": "worst_headache", "label": "Sudden 'worst ever' headache",
     "regex": r"worst headache|thunderclap headache",
     "action": "A sudden worst-ever headache needs emergency assessment."},
    {"id": "bleeding", "label": "Vomiting or coughing blood, blood in stool, black tarry stool",
     "regex": r"vomit(ing)? blood|cough(ing)? (up )?blood|blood in stool|black tarry stool",
     "action": "Possible internal bleeding needs emergency care."},
    {"id": "fever_neck", "label": "Fever together with a stiff neck or a rash",
     "regex": r"stiff neck (with|and) fever|fever (with|and) (stiff neck|rash)",
     "action": "This combination can indicate a serious infection; get emergency care."},
    {"id": "self_harm", "label": "Thoughts of self-harm or suicide",
     "regex": r"suicid|self[- ]harm|kill myself|hurt myself",
     "action": "Please contact emergency services or a crisis helpline now. You deserve immediate support."},
    {"id": "anaphylaxis", "label": "Swelling of face/throat/tongue, trouble swallowing, suspected severe allergy",
     "regex": r"swell(ing|en)? (of|in) (face|throat|tongue|lips)|anaphylax|trouble swallowing|throat closing",
     "action": "Facial/throat swelling with breathing trouble is an emergency."},
    {"id": "severe_abdominal", "label": "Severe abdominal (stomach) pain",
     "regex": r"severe abdominal pain|severe stomach pain",
     "action": "Severe abdominal pain needs same-day emergency evaluation."},
    {"id": "no_fluids", "label": "Unable to keep fluids down",
     "regex": r"unable to keep (fluids|food|water) down|cannot keep (fluids|water) down",
     "action": "Risk of dangerous dehydration — seek urgent care today."},
]

EMERGENCY_ACTION = ("Stop using this app for guidance and call your local emergency number "
                    "now (India: 112 · US: 911 · EU: 112), or have someone take you to the "
                    "nearest emergency department.")

# ------------------------------------------------------------------ knowledge base
# General educational entries, selected by keyword. Wording rule: describe areas
# to OBSERVE or patterns that may COINCIDE; never assert a mechanism or infer a
# condition (glucose, deficiency, dehydration, …) from the symptom alone.
SYMPTOM_KB = {
    "fatigue": {
        "match": r"fatigue|tired|exhaust|low energy|brain fog|sleepy|sluggish",
        "possibilities": [
            {"title": "Everyday load and recovery patterns",
             "detail": "Tiredness is very common and its pattern often varies with sleep, workload, stress and activity. With limited information it is not possible to say whether any of these is relevant in your case — this entry is general education, not an inference about you."},
            {"title": "A non-specific, often short-lived feeling",
             "detail": "Many episodes of tiredness have no identifiable cause and settle on their own. Not finding an explanation here is not evidence that something is medically wrong — and equally not a guarantee that nothing is."},
            {"title": "Something to review with a clinician if it persists",
             "detail": "If fatigue lasts for weeks, worsens, or interferes with daily life, an in-person evaluation is the only way to identify or rule out medical causes. This tool cannot do that."},
        ],
        "self_care": [
            {"title": "Keep a simple pattern log",
             "detail": "For a week, note sleep hours, meal times, activity and when the tiredness is strongest. Your own pattern data helps you (and any clinician) more than guesses."},
            {"title": "Protect the basics",
             "detail": "Regular sleep and wake times, regular meals, and steady fluid intake across the day are general wellbeing habits suitable for most people."},
            {"title": "Pace demanding tasks",
             "detail": "Where possible, spread intense study or exercise through the day with short breaks. This is a general comfort strategy, not a treatment."},
        ],
    },
    "headache": {
        "match": r"headache|head pain|migraine",
        "possibilities": [
            {"title": "A common, usually non-specific headache",
             "detail": "Most everyday headaches are short-lived. They may coincide with long screen time, posture, stress or irregular sleep — coincidence is not proof of cause, and this tool cannot identify your trigger."},
            {"title": "A pattern worth observing in your own data",
             "detail": "Some people notice their headaches clustering around certain days, foods, fluids or sleep patterns. Tracking your own pattern is more useful than assuming a mechanism."},
        ],
        "self_care": [
            {"title": "Take regular screen and posture breaks",
             "detail": "Brief breaks (e.g. every 20 minutes, look away for 20 seconds) and gentle neck/shoulder stretches are general comfort measures."},
            {"title": "Keep meals, fluids and sleep regular",
             "detail": "Regular routines are a general baseline that makes patterns easier to notice; they are not a cure."},
            {"title": "Note timing and context",
             "detail": "A simple headache diary (time, duration, what was happening) is useful information for a clinician if headaches repeat."},
        ],
    },
    "bloating": {
        "match": r"bloat|gas|fullness|distend",
        "possibilities": [
            {"title": "Meal-size or eating-speed coincidence",
             "detail": "Bloating is commonly reported after large or rich meals and fast eating. Whether that applies to you cannot be determined here."},
            {"title": "A food-specific pattern worth observing",
             "detail": "If bloating follows the same food every time, that pattern is worth discussing with a clinician; intolerances can only be evaluated properly by professionals, not by this tool."},
        ],
        "self_care": [
            {"title": "Smaller, slower meals",
             "detail": "Eating slower and in smaller portions is a general comfort measure many people try first."},
            {"title": "Track meals alongside symptoms",
             "detail": "Logging what you ate with the symptom (your tracker already does the food side) turns guesses into observable patterns."},
            {"title": "Gentle movement after eating",
             "detail": "A short walk after meals is a common general comfort measure."},
        ],
    },
    "sore_throat": {
        "match": r"sore throat|throat pain|scratchy throat",
        "possibilities": [
            {"title": "A short-lived everyday irritation",
             "detail": "Many sore throats are mild and settle within about a week. The cause (viral, dry air, voice strain…) cannot be identified here."},
        ],
        "self_care": [
            {"title": "Warm fluids and salt-water gargle",
             "detail": "A general comfort measure: half a teaspoon of salt in a glass of warm water, gargled, not swallowed."},
            {"title": "Honey in warm water",
             "detail": "A traditional soothing measure for adults (never for infants under 1 year)."},
        ],
    },
    "muscle_ache": {
        "match": r"muscle ache|body ache|sore muscles|muscle pain",
        "possibilities": [
            {"title": "Often follows new or heavier activity",
             "detail": "Everyday muscle soreness frequently appears after unaccustomed exercise or carrying loads — but it can also appear without an obvious reason, and this tool cannot tell which is your case."},
        ],
        "self_care": [
            {"title": "Rest and gentle movement",
             "detail": "Light stretching and easing off heavy loads for a day or two are general comfort measures."},
            {"title": "Keep sleep and meals regular",
             "detail": "General recovery basics; useful as a baseline rather than a treatment."},
        ],
    },
    "nausea": {
        "match": r"nausea|nauseous|queasy|want to vomit",
        "possibilities": [
            {"title": "A common, usually temporary feeling",
             "detail": "Nausea is often reported around rich meals, travel or long gaps between meals. The actual cause in your case cannot be determined here."},
        ],
        "self_care": [
            {"title": "Small, frequent sips of fluid",
             "detail": "Gentler than large volumes at once; a general comfort measure."},
            {"title": "Plain, small meals",
             "detail": "Plain rice, toast or banana are common bland choices while nausea settles."},
        ],
    },
    "insomnia": {
        "match": r"insomnia|can'?t sleep|cannot sleep|trouble sleeping|poor sleep",
        "possibilities": [
            {"title": "Schedule and habit patterns often coincide",
             "detail": "Difficulty sleeping frequently coincides with late caffeine, bright evening screens or shifting bedtimes. Which (if any) applies to you is for you to observe and a clinician to assess."},
        ],
        "self_care": [
            {"title": "Fixed wake-up time",
             "detail": "A consistent wake time is one of the most commonly recommended general sleep habits."},
            {"title": "Caffeine cutoff",
             "detail": "General sleep-hygiene information: many guidelines suggest avoiding caffeine within about 6-8 hours of bedtime."},
        ],
    },
    "dizziness": {
        "match": r"dizzi|lightheaded|giddy",
        "possibilities": [
            {"title": "Brief everyday episodes are common",
             "detail": "Short light-headedness on standing up quickly or in hot rooms is commonly reported and often benign. Repeated, prolonged or worsening episodes deserve a clinician's attention — this tool cannot grade the risk."},
        ],
        "self_care": [
            {"title": "Change position slowly",
             "detail": "A general safety measure to reduce fall risk during episodes."},
            {"title": "Log the episodes",
             "detail": "Note time, position, food and fluid context; patterns are what clinicians find useful."},
        ],
    },
    "fever": {
        "match": r"fever|temperature|chills",
        "possibilities": [
            {"title": "Often accompanies self-limiting illnesses",
             "detail": "Low-grade fever is frequently seen with minor viral illnesses, but the cause cannot be confirmed without examination. Persistent or high fever needs professional care."},
        ],
        "self_care": [
            {"title": "Rest and regular fluids",
             "detail": "The standard general advice while a mild febrile illness runs its course."},
            {"title": "Keep a temperature log",
             "detail": "Record readings with times so a clinician can see the pattern."},
        ],
    },
    "cough": {
        "match": r"cough",
        "possibilities": [
            {"title": "Commonly follows colds or irritant exposure",
             "detail": "Everyday coughs often linger for weeks after a cold or around dust/dry air. A cough that persists, worsens, or brings blood needs prompt medical review."},
        ],
        "self_care": [
            {"title": "Warm fluids and honey",
             "detail": "A general soothing measure for adults."},
            {"title": "Reduce irritant exposure where possible",
             "detail": "Dust, smoke and very dry air are common environmental irritants."},
        ],
    },
}

GENERIC_ENTRY = {
    "possibilities": [
        {"title": "No specific educational entry matched",
         "detail": "Many mild symptoms have ordinary, temporary explanations (sleep, stress, meals, weather, posture) — and some have none that can be identified at all. This tool cannot tell which applies to you, and it will not guess a mechanism."},
    ],
    "self_care": [
        {"title": "Track patterns instead of guessing",
         "detail": "Log the symptom alongside sleep, meals and activity for a few days; observable patterns help you and any clinician more than speculation."},
        {"title": "Keep the general basics steady",
         "detail": "Regular sleep, regular meals and steady fluids are a sensible baseline for most people while you observe."},
    ],
}

SEEK_CARE_BASE = [
    "Symptoms persist beyond 1-2 weeks, or keep returning.",
    "Symptoms worsen steadily despite self-care.",
    "You have fever above 39.5°C, or any fever lasting more than 3 days.",
    "You are pregnant, immunocompromised, or managing a chronic condition — check even mild symptoms with your clinician.",
    "You are unsure or worried about what you are feeling — uncertainty alone is a valid reason to seek professional advice.",
]


def engine_mode() -> dict:
    """Truthfully report which engine is active. Never pretend AI is present."""
    key = os.environ.get("ASSISTANT_API_KEY", "").strip()
    return {
        "engine": ENGINE_VERSION,
        "online_ai_configured": bool(key),
        "online_ai_used": False,  # safety screening always happens locally in v1
        "label": ("Offline rule-based guidance engine (no online AI call is made; "
                  "an API key is configured but v1 still uses the local safety engine)!"
                  if key else
                  "Offline rule-based guidance engine (limited alternative — no AI API configured)"),
    }


def _matches(text: str, regex: str) -> bool:
    return re.search(regex, text, re.IGNORECASE) is not None


# ------------------------------------------------------------------ independent screens

def screen_red_flags(text: str, selected_sign_ids: list[str]) -> list[dict]:
    """EMERGENCY SCREEN — independent of the explanation generator.

    A sign triggers if it was explicitly selected OR its pattern appears anywhere
    in the user's text. Each triggered sign is reported separately, so removing
    one selection removes only that sign's flag.
    """
    known = {s["id"] for s in WARNING_SIGNS}
    selected = [sid for sid in selected_sign_ids if sid in known]
    flags = []
    for sign in WARNING_SIGNS:
        if sign["id"] in selected or _matches(text or "", sign["regex"]):
            flags.append(dict(sign))
    return flags


def explain_possibilities(text: str) -> tuple[list[dict], list[dict], list[str]]:
    """GENERAL EXPLANATION GENERATOR — cannot add or remove emergency flags.

    Returns (possibilities, self_care, matched_category_names). Entries are
    educational and keyword-selected; they are never conclusions about the user.
    """
    matched = [(name, kb) for name, kb in SYMPTOM_KB.items() if _matches(text or "", kb["match"])]
    names = [name for name, _ in matched]
    if not matched:
        return list(GENERIC_ENTRY["possibilities"]), list(GENERIC_ENTRY["self_care"]), []
    possibilities, self_care = [], []
    for _name, kb in matched:
        possibilities.extend(kb["possibilities"])
        for care in kb["self_care"]:
            if care not in self_care:
                self_care.append(care)
    return possibilities[:4], self_care[:6], names


# ------------------------------------------------------------------ main entry

def assess(payload: dict, profile: dict | None = None) -> dict:
    """Run the assessment. `payload` keys:
    primary (str, required), duration (str), severity (int 1-10),
    associated (list[str]), notes (str), warning_signs (list[str] of sign ids)
    """
    primary = str(payload.get("primary") or "").strip()
    notes = str(payload.get("notes") or "").strip()
    associated = [str(a).strip() for a in (payload.get("associated") or []) if str(a).strip()]
    selected_signs = [str(s).strip() for s in (payload.get("warning_signs") or []) if str(s).strip()]
    duration = payload.get("duration") or "today"
    try:
        severity = int(payload.get("severity", 0))
    except (TypeError, ValueError):
        severity = 0
    if not primary:
        raise ValueError("primary symptom is required")
    if not 1 <= severity <= 10:
        raise ValueError("severity must be an integer from 1 to 10")
    if duration not in DURATIONS:
        raise ValueError(f"duration must be one of {DURATIONS}")

    haystack = " | ".join([primary, notes, *associated]).lower()

    # 1) emergency screen FIRST and independently of everything below
    flags = screen_red_flags(haystack, selected_signs)
    emergency = bool(flags)

    # 2) triage level
    if emergency:
        triage = "emergency"
    elif severity >= 8:
        triage = "urgent_same_day"
    else:
        triage = "self_care"

    # 3) general explanations (keyword-selected education, never conclusions)
    possibilities, self_care, matched_names = explain_possibilities(haystack)
    possibilities = [dict(p, tag="Possible — general information, not a diagnosis")
                     for p in possibilities]

    # 4) caution notes: make limited/ambiguous information explicit
    caution_notes = []
    if not associated and not notes:
        caution_notes.append(
            "You reported a single symptom with no additional context. Many different "
            "situations can produce this symptom, so nothing below is an inference about "
            "your case — it is general health education.")
    if len(matched_names) > 1:
        caution_notes.append(
            "Your description touches several symptom areas ("
            + ", ".join(matched_names) + "). General entries for each are shown side by "
            "side; only a clinician can tell which (if any) is relevant.")
    if not matched_names:
        caution_notes.append(
            "No specific educational entry matched your wording. That is not evidence "
            "that anything is wrong (or right) — it only means this tool has no general "
            "entry to show, so it will not invent one.")
    caution_notes.append(
        "Reported facts below are exactly what you entered; explanations are separate, "
        "keyword-selected educational entries and are not conclusions about you.")

    # 5) profile context (only what the user already stored, echoed as their report)
    context_notes = []
    if profile:
        if profile.get("allergies"):
            context_notes.append("Your profile notes allergies/intolerances: "
                                 + ", ".join(profile["allergies"])
                                 + ". Shown as your own reported context, not as an explanation.")
        if profile.get("medications"):
            context_notes.append("Your profile lists medications: "
                                 + ", ".join(profile["medications"])
                                 + ". This tool does not advise on medications — ask your "
                                   "pharmacist or doctor about any symptom-medication questions.")

    # 6) when to seek care
    seek_care = list(SEEK_CARE_BASE)
    if duration == ">2w":
        seek_care.insert(0, "These symptoms have lasted more than 2 weeks — book a clinician "
                            "visit rather than continuing self-care alone.")
    if severity >= 6 and not emergency:
        seek_care.insert(0, "Severity this high deserves a same-day or next-day clinician "
                            "check even without warning signs.")

    return {
        "engine": engine_mode(),
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
        "triage": triage,
        "reported_facts": {
            "primary": primary,
            "duration": duration,
            "duration_label": DURATION_LABELS[duration],
            "severity": severity,
            "associated": associated,
            "warning_signs_selected": [s["label"] for s in WARNING_SIGNS
                                       if s["id"] in selected_signs],
            "notes": notes[:300],
        },
        "red_flags": flags,
        "emergency_actions": ([EMERGENCY_ACTION] + [f["action"] for f in flags])
                             if emergency else [],
        "possibilities": possibilities,
        "self_care": self_care,
        "seek_care": seek_care,
        "caution_notes": caution_notes,
        "context_notes": context_notes,
        "limitations": LIMITATIONS,
        "references": REFERENCES,
        "disclaimer": DISCLAIMER,
        "input_echo": {"primary": primary, "duration": duration,
                       "severity": severity, "associated": associated,
                       "warning_signs": selected_signs},
    }
