# NutriCare Health Assistant V2
## Clinical research, decision logic, and option-based-flow architecture

**Status:** research/architecture draft for product and clinical review — **not approved for implementation**  
**Prepared:** 12 November 2026  
**Scope:** local deterministic Health Assistant only. No LLM, external health API, diagnosis, probability, prescription, antibiotic advice, interaction checking, or model change is proposed.

> **Approval gate.** This document deliberately does not change `nutricare/assistant.py`, `static/js/health_chat.js`, routes, rules, assets, or clinical content. The V2 engine must not be implemented or the current triage engine replaced until the product owner and a suitably qualified clinical reviewer approve the unresolved items in section 14.

---

## 1. Executive conclusion

The report of “everything becomes an emergency” is **not fully explained by the basic guided examples**. Reproducing the current engine found that uncomplicated mild headache, tiredness, body pain, and short-duration fever produce `self_care`; severity 8 alone produces `urgent_same_day`, not `emergency`.

There are, however, **demonstrated paths that can create the reported experience**:

1. **A persistent, red emergency notice is rendered for every open panel**, whether or not an assessment is emergency. It says “Emergency? Call 112…” and is not connected to computed triage. This can visually be read as an emergency outcome.
2. **Every selected “warning sign” is converted to the single `emergency` result**, even when the rule’s own action says “seek urgent care today.” For example, the guided choice “No, I cannot keep fluids down” maps to `no_fluids`; the current engine returns `emergency` and emergency number wording. Established public guidance treats inability to keep fluids down as requiring urgent assessment, while emergency escalation depends on accompanying danger signs such as vomiting blood, green vomit, sudden severe pain, confusion, or severe breathing difficulty.[1](https://www.nhs.uk/symptoms/diarrhoea-and-vomiting/)
3. **The free-text chat’s broad phrase matcher escalates non-specific breathing wording.** Runtime reproduction: both `difficulty breathing after running` and `mild shortness of breath on stairs` return `emergency` because the matcher treats any “difficulty breathing” or “shortness of breath” phrase as an emergency flag. Severe breathing is an emergency; the current matcher cannot distinguish severity, onset, exertional context, or an answer of “not severe.”
4. The current normal assessment has only three outcomes. It cannot label a person who should make a normal appointment as `routine_consultation`: for example, fatigue for more than two weeks remains `self_care`, despite a “book a clinician visit” sentence. This is **under-specific classification**, not over-triage, but makes the UI’s result inconsistent with its care advice.
5. A global 1–10 score independently produces `urgent_same_day` at 8 or more. Conversely, the client sends only the **first** symptom’s duration and severity. In a multi-symptom assessment, a severe second symptom can be hidden by a mild first symptom; a severe first symptom can drive the combined result. This is not evidence-supported multi-symptom logic.

V2 should replace broad text matching and the universal severity branch with a versioned, option-ID-only, symptom-specific decision table. It should return exactly one of four distinct outcomes:

| Outcome | Meaning and UI action |
|---|---|
| `emergency` | A narrowly defined immediate-danger rule matched. Stop assessment; show the exact selected facts/rule; tell the person to call **112 in India** or **108 for a medical ambulance**, or seek the nearest emergency department. |
| `urgent_medical_assessment` | Same-day / prompt professional assessment is indicated, but the application must not present it as “call 112” unless an emergency rule also matches. |
| `routine_consultation` | Book a non-emergency clinician consultation; show the persistence/recurrence/function rule that triggered it. |
| `self_care_monitoring` | General self-care and explicit return precautions only. It is never a diagnosis or a guarantee that nothing is wrong. |

A numeric severity rating can be displayed as a reported fact and can help select a more detailed **pathway question**, but it must **never independently choose any outcome**, especially never `emergency`.

---

## 2. Safety, product, and clinical boundaries

### Non-negotiable boundaries

* The assistant is a local, deterministic routing and education tool. It does not diagnose, estimate disease probability, identify a cause, triage from prose, prescribe, calculate a dose, recommend an antibiotic, or perform an interaction check.
* The person can select more than one symptom. Each selected symptom receives its own short pathway; the engine evaluates the complete validated answer set with explicit precedence.
* The V2 guided experience is option-only. A typed message must not be used as an input to triage. The current direct-message conversation should be retired from the V2 panel rather than silently retained beside the option-only journey.
* “Other/additional information” needs a product decision because it conflicts with “all answers must be stable predefined IDs.” The recommended reconciliation is: the person may choose the stable ID `other_or_not_listed`, and may optionally attach a bounded note **that is never parsed or used by triage rules**. It is labelled “not used to decide urgency.” The server stores it only if approved by the privacy review. This preserves a communication aid without making arbitrary text an unvalidated clinical input.
* Display a compact general emergency link, but do not show a red emergency outcome/banner unless an `emergency` rule actually matched. The existing persistent safety reminder is a product-safety link, not a triage result, and must be visually separated from result status.
* India wording remains: **“For an immediate emergency in India, call 112; for a medical ambulance, call 108.”** The application cannot verify local service availability.
* V2 does not add a model, alter Food Scanner recognition, replace protected models, alter catalogue data, or send health data to a third party.

### Intended age scope

V2 must collect a required **age band** before an assessment result (with `not_sure` and `prefer_not_to_answer`). It should not infer age from a profile. The required minimum safeguards are:

* **Under 2 months:** do not present adult-style self-care triage for fever, poor feeding, breathing difficulty, lethargy, or reduced movement; route for prompt in-person assessment. India’s IMNCI chart identifies these as possible serious bacterial infection/very severe disease signs.[2](https://nhm.gov.in/images/pdf/programmes/child-health/guidelines/IMNCI-Module-2023-For-Medical-Officers/IMNCI-Chart-booklet-Medical-Officer-2023.pdf)
* **2 months to under 5 years:** use only specifically reviewed IMNCI-compatible child danger/dehydration/febrile pathways; do not reuse adult thresholds.
* **5–15 years:** use conservative child/young-person routing and do not expose adult OTC reference information.
* **16 years and over:** use the adult pathways documented below.
* **Age unknown/declined:** do not release medication-specific information. For symptoms whose safe route differs materially by age (especially fever, vomiting/diarrhoea, breathing, and severe headache), return `urgent_medical_assessment` rather than guessing.

The exact scope for 5–15-year symptom pathways needs clinical sign-off before implementation (section 14).

---

## 3. Existing implementation audit

### 3.1 Frontend: current guided assessment

| Area | Current behaviour | Finding for V2 |
|---|---|---|
| Symptom selection | `ASSESSMENT_SYMPTOMS` offers 10 values: feeling good, fatigue, headache, fever, dizziness, nausea, body pain, stress/anxiety, low mood, other. Multiple selection is supported, and `feeling_good` is exclusive. | It lacks diarrhoea, constipation, abdominal pain, cough, sore throat, back pain, joint pain, allergy symptoms, and sleep problems. Replace with the stable 18-symptom V2 dictionary in section 7. |
| Branching | `buildAssessmentSteps()` adds limited branch questions for headache, fatigue, fever, dizziness, nausea, body pain, and wellbeing. | The client contains some useful questions, but the final server payload discards most stable meaning; see “payload loss” below. |
| Global safety | All non-wellbeing symptoms start with `GLOBAL_SAFETY_OPTIONS`: sudden worst headache, chest pain, severe breathing, stroke signs, fainting/loss of consciousness, confusion, severe allergy, self-harm, and None. | A shared immediate-safety check is reasonable, but must have narrowly defined options and must not make every urgent item an emergency. It needs no raw-text “other” field. |
| Symptom safety | Some branches attach a `warning` ID: headache vision/speech, fever stiff neck/rash and no fluids, dizziness fainting/chest/breathing, fatigue severe breathing, wellbeing self-harm. | Warning IDs are a sound concept but they map to a flat global emergency registry. V2 must map each ID to its own table rule/outcome. |
| Duration and severity | All branches reuse five short duration choices and four score bands (2, 5, 8, 10). No current guided choice reaches the engine’s `>2w` duration. | Add symptom-specific duration/recurrent/function options. Do not let score select a result. |
| “Other” free text | `assessmentStep` defaults `other: true`, so arbitrary text areas appear on ordinary questions. Typed symptom text is automatically converted to the `other` symptom selection. | This is not strict option-only. See the bounded, non-triage attachment proposal above. |
| Existing conditions | Multi-select includes `none`; UI correctly makes None exclusive. It also allows a typed other condition. | Preserve mutual exclusivity server-side and add unknown/declined IDs. Do not rely on client enforcement. |
| Review/navigation | Progress, Continue, Back, Restart, review/confirmation, and answer preservation exist. | Preserve. Add edit-to-question, answer-preservation after rebuilding dynamic steps, and a non-sticky emergency reset test. |
| Panel content | The panel has a persistent “Emergency? Call 112…” safety block on every render. | Confirmed visual contributor to emergency perception. Make it neutral “Need emergency help?” utility text or place it in Help; show red emergency styling only for a result. |
| Direct chat | When not in guided/OTC mode, the panel still exposes a free-text form to `/health-chat/messages`. | It conflicts with the V2 strict option-only requirement and keeps the broad phrase matcher live. Replace it with “Start assessment”, “OTC information”, and non-triage history controls after approval. |

### 3.2 Payload and API audit

The current `assessmentPayload()` sends:

```text
primary: human labels joined with semicolons
severity: first *_severity answer only
 duration: first *_duration answer mapped to today / 2-3d / 3-5d
associated: visible labels from selected associated/location/sleep/fluid/temperature choices
warning_signs: selected warning IDs
notes: prose including all typed “Other” text and reported conditions
existing_conditions: visible labels
```

Consequences:

* It sends **labels/prose**, not a validated answer schema. A server cannot reliably distinguish IDs, translated labels, or changed presentation text.
* Multiple symptoms do not retain separate duration/severity facts. The first matching branch wins.
* Location, measured temperature, sleep quality, and “only small amounts of fluid” are flattened into labels, then ignored by the triage branch.
* `assessmentDuration()` maps `more_three_days` to `3-5d`; there is no normal UI path to the server’s `1-2w` or `>2w` categories.
* The `/assistant/screen` endpoint checks type/length only. It silently filters unknown warning IDs in `screen_red_flags()` rather than rejecting them.
* `/assistant/assess` validates only non-empty `primary`, integer severity 1–10, and one of five duration strings. It accepts arbitrary `primary`, `associated`, `notes`, `existing_conditions`, and unknown warning IDs (unknown warning IDs are silently ignored). It does not enforce the frontend’s None exclusivity.
* `/health-chat/messages` accepts arbitrary free text up to 800 characters, persists it, and calls `health_chat.respond()`.

V2 must make `/api/assistant/v2/assess` accept a versioned JSON schema of stable IDs only; reject missing, duplicate where disallowed, unknown, contradictory, unexpected, and out-of-path values with HTTP 400. The legacy assessment endpoint should remain only for old history/read compatibility until a separately approved removal plan exists.

### 3.3 Current assessment engine and outcomes

`assistant.assess()`:

1. builds a text haystack from primary, notes, and associated labels;
2. runs `screen_red_flags()` first;
3. returns `emergency` for **any** flag;
4. otherwise returns `urgent_same_day` when `severity >= 8`;
5. otherwise returns `self_care`.

The engine has no `routine_consultation` outcome and no symptom decision tables. Its educational knowledge base is separate from triage and appropriately avoids diagnosis language, but keyword matching selects education rather than clinically reviewed pathway logic.

The output contains generic self-care/seek-care content even when its outcome says `self_care`. For a symptom lasting more than two weeks, it inserts a clinician-booking sentence without changing `triage`, which creates an inconsistent semantic result.

### 3.4 Free-text local chat audit

The free-text chat shares `assistant.screen_red_flags()` and runs it before all other conversation logic. This protects against ignoring chest pain, stroke signs, severe allergy patterns, etc.; however, it is an intentionally broad regular-expression screen, not an option-based clinical assessment.

The current tests explicitly assert `difficulty breathing after running` as emergency. The regex also matches `mild shortness of breath on stairs`; both reproduce as `emergency`. That demonstrates a false-positive route for non-specific phrasing, although a person with concerning breathlessness should always seek professional help if worried. V2 removes phrase parsing from triage rather than trying to make a regex diagnose context.

### 3.5 Persistence, export, profile scope, and tests

* `assessments` are profile-scoped and the final `/assistant/assess` result is saved; the `emergency` database column is true only when the final result is `emergency`.
* `/assistant/screen` explicitly does **not** persist partial screens. This is tested.
* `/health-chat/messages` persists both user and assistant messages, including an emergency reply; local chat history is exported in JSON/CSV and purged with local profile purge.
* Current test coverage is strong for legacy emergency phrase matching, generic severity, API persistence, UI Back/review, OTC gating, history/export/purge, and general Food Scanner regressions. It does **not** have a complete option-contract suite, per-rule trace tests, the four-outcome taxonomy, every requested symptom path, age-specific rules, or a non-sticky emergency-state journey.
* `tests/ui_smoke.js` has an option-flow simulation rather than a browser/visual assertion; it proves selected frontend state and API calls but cannot prove that red styling is not misleading.

### 3.6 Existing OTC guidance audit

The separate `POST /api/assistant/otc-guidance` engine is the most schema-strict component today:

* It validates topic, age band, allergy, conditions, pregnancy/breastfeeding, current medicines, previous medicine use, fever duration/level, and known warning IDs.
* It rejects an unknown option and makes `none` exclusive in condition selection.
* Emergency warning IDs outrank all medicine output; high/persistent fever prevents reference dosing; unknown/risky facts hand off to a pharmacist/clinician.
* It uses the local versioned paracetamol/cetirizine reference catalogue with source URLs and review dates.

Compatibility issue for review: the current catalogue releases NHS age-matched **cetirizine** reference wording for ages 2–15, while it blocks child paracetamol numeric information. The user’s new boundary expressly prohibits supplying adult dosing to children, but a decision is still needed on whether any pediatric cetirizine numeric reference should remain in V2 (recommended default: do not expand it; retain only after paediatric/pharmacy approval).

---

## 4. Demonstrated root-cause traces

The following traces were executed directly against the checked-out current branch before any V2 change:

| Input/path | Observed current result | Interpretation |
|---|---|---|
| mild headache; today; severity 2; no flags | `self_care` | Disproves the broad claim that mild headache always becomes emergency. |
| ordinary tiredness; today; severity 2; no flags | `self_care` | Disproves a blanket tiredness-to-emergency path in the normal assessment engine. |
| body pain; today; severity 3; no flags | `self_care` | Same. |
| fever; today; severity 3; no flags | `self_care` | Same. |
| headache; today; severity 8; no flags | `urgent_same_day` | The current numeric score can force urgency, but not emergency. |
| nausea/vomiting route; select `no_fluids` | `emergency`; flag `no_fluids`; emergency number action | Confirmed inappropriate flattening of an urgent dehydration concern into emergency. This is a principal over-triage defect. |
| direct chat: `difficulty breathing after running` | `emergency`; flag `breathing` | Confirmed broad free-text false-positive route. |
| direct chat: `mild shortness of breath on stairs` | `emergency`; flag `breathing` | Same. |
| fatigue; duration `>2w`; no flags | `self_care` plus “book a clinician visit” text | Confirmed missing routine-consultation category / outcome-content mismatch. |
| explicit chest pain selection | `emergency` | Expected and should remain emergency. |

The persistent panel notice is independently visible in every expanded-panel render. It is a **usability contributor**, not a computed-engine defect. No claim is made that it alone explains any individual report.

---

## 5. Evidence method and source register

### Method

Rules below are drawn from public, established guidance. India MoHFW/NHM and ICMR sources are preferred for paediatric danger signs and fever/diarrhoea context; WHO, NICE, and NHS provide established symptom-routing material where a directly comparable Indian public triage source was not found. Sources were checked on **12 November 2026**. The V2 table must retain rule ID, source ID, source URL, exact section, publication/update date, and clinical-review status in code/data — not merely in documentation.

These sources describe public guidance or professional referral pathways; they do **not** validate NutriCare as a medical device. Where a source says “consider referral,” V2 uses a conservative `urgent_medical_assessment` or `routine_consultation` only after clinical review; it must not claim a diagnosis.

| ID | Authority, date, exact supporting section | Applied use / important difference |
|---|---|---|
| S1 | India MoHFW/NHM, **IMNCI Chart Booklet for Medical Officers (2023)**, sick young infant possible serious bacterial infection; child general danger signs; diarrhoea, fever/dengue charts; “When to return.” [2](https://nhm.gov.in/images/pdf/programmes/child-health/guidelines/IMNCI-Module-2023-For-Medical-Officers/IMNCI-Chart-booklet-Medical-Officer-2023.pdf) | Primary Indian paediatric source. It applies to young infants and children up to five years, not adults; V2 must not transplant its temperature/management thresholds into adult rules. |
| S2 | ICMR, **Treatment Guidelines for Antimicrobial Use in Common Syndromes (2019)**, section 3.1 acute undifferentiated febrile illness; severity/localisation features and day 1–2 / day 3–4 investigation context. [3](https://www.icmr.gov.in/icmrobject/custom_data/pdf/resource-guidelines/Treatment_Guidelines_2019_Final.pdf) | Supports no automatic antibiotic advice and that fever requires context. It is professional management guidance, not a direct consumer emergency threshold. |
| S3 | NHS, **Diarrhoea and vomiting**, last reviewed **21 Dec 2023**, “Urgent advice: Call 111” and “Immediate action required.” [1](https://www.nhs.uk/symptoms/diarrhoea-and-vomiting/) | Separates cannot keep fluid down and bloody diarrhoea (urgent) from vomiting blood, green vomit, sudden severe headache/abdominal pain, severe breathing difficulty, and confusion (immediate). Directly exposes the current `no_fluids` flattening defect. |
| S4 | NHS, **Anaphylaxis**, last reviewed **21 Jun 2023**, “Symptoms” and “Immediate action required.” [4](https://www.nhs.uk/conditions/anaphylaxis/) | Supports emergency only for acute airway/breathing/circulation/severe responsiveness signs; a generic mild allergy symptom is not the same rule. |
| S5 | NICE CG150, **Headaches in over 12s**, published **19 Sep 2012**, last updated **3 Jun 2025**, recommendations **1.1.1–1.1.4**. [5](https://www.nice.org.uk/guidance/cg150/chapter/recommendations) | Supports evaluating/referring headache with sudden maximal onset, fever worsening, neurological/cognitive change, impaired consciousness, trauma, exertional/postural trigger, substantial change; it does not say a number on a 1–10 scale alone determines emergency. |
| S6 | NICE NG127, **Suspected neurological conditions**, published **1 May 2019**, last updated **2 Oct 2023**, **1.1.1–1.1.2** and **1.2.1–1.2.10**. [6](https://www.nice.org.uk/guidance/ng127/chapter/recommendations-for-adults-aged-over-16) | Supports immediate referral for acute dizziness with focal neurological deficit/acute vestibular syndrome where appropriate; notes dizziness without imbalance/focal deficit is unlikely serious. It also distinguishes some blackouts that need urgent assessment from clear vasovagal features. V2 cannot perform HINTS, so it must not pretend to rule out stroke. |
| S7 | NHS, **High temperature (fever) in adults**, last reviewed **19 Oct 2026**, “When and where to get medical help.” [7](https://www.nhs.uk/symptoms/fever-in-adults/) | Supports self-care for many short fevers and urgent advice when not improving/worsening; contrasts with a blanket high-temperature emergency rule. |
| S8 | NHS, **Meningitis**, last reviewed **12 Jun 2026**, “Symptoms” and “Immediate action required.” [8](https://www.nhs.uk/conditions/meningitis/) | Supports immediate route for a concerning fever/neck/neurological/rash pattern; it says not every sign is required. Use a conservative, explicit danger set — not the current combined regex alone. |
| S9 | NHS, **Stomach ache**, last reviewed **20 Oct 2026**, “Urgent advice” and “Immediate action required.” [9](https://www.nhs.uk/symptoms/stomach-ache/) | Supports sudden severe abdominal pain, GI bleeding/black stool, inability to pee or pass stool/wind, non-blanching rash, breathing difficulty as emergency; pregnancy, worsening pain, blood in stool, and persistent vomiting/diarrhoea as urgent. |
| S10 | NHS, **Cough**, last reviewed **8 Dec 2023**, “Non-urgent advice” and “Urgent advice.” [10](https://www.nhs.uk/symptoms/cough/) and **Bronchitis**, last reviewed **18 Aug 2026**, “Immediate action required.” [11](https://www.nhs.uk/conditions/bronchitis/) | Supports routine review for cough >3 weeks and urgent review for cough blood/chest pain/hard breathing. The bronchitis page limits emergency wording to struggling to breathe/blue-grey-pale skin/confusion, which is narrower than current free-text matching. |
| S11 | NHS, **Sore throat**, last reviewed **8 Apr 2024**, urgent and immediate action sections. [12](https://www.nhs.uk/symptoms/sore-throat/) | Supports emergency route for unable to breathe/swallow, drooling, stridor, rapidly worsening severe symptoms; not every ordinary sore throat. |
| S12 | NHS, **Dizziness**, last reviewed **21 Apr 2023**, routine review signs. [13](https://www.nhs.uk/symptoms/dizziness/) | Supports conservative routine review for recurrent/non-resolving dizziness and associated visual, speech, weakness, fainting/collapse, headache or vomiting symptoms; NICE NG127 is the higher-level source for acute neurological patterns. |
| S13 | NHS, **Tiredness and fatigue**, last reviewed **2 Jun 2023**, “See a GP if…” [14](https://www.nhs.uk/symptoms/tiredness-and-fatigue/) | Supports routine consultation when unexplained fatigue lasts weeks, affects daily life, or has weight/mood/sleep-breathing features; it does not justify diagnosing a cause. |
| S14 | NHS, **Insomnia**, last reviewed **19 Mar 2024**, “See a GP if…” [15](https://www.nhs.uk/conditions/insomnia/) | Supports self-care for short-term sleep difficulty and routine review after months/when daily coping is affected. |
| S15 | NHS, **Joint pain**, last reviewed **26 Feb 2026**, urgent and immediate action sections. [16](https://www.nhs.uk/symptoms/joint-pain/) | Supports urgent review of hot/swollen joint/systemic symptoms and emergency route after injury where unable to bear weight, deformity, or loss of feeling. |
| S16 | NHS, **Back pain**, last reviewed **5 Mar 2026**, urgent/immediate action sections; NICE NG59, last updated **29 Jul 2026**, assessment and self-management **1.1.1–1.2.1**. [17](https://www.nhs.uk/conditions/back-pain/) [18](https://www.nice.org.uk/guidance/ng59/chapter/recommendations) | Supports emergency assessment for bilateral leg neurological symptoms, saddle sensory change or new bladder/bowel/sexual-function change; urgent for systemic illness/rapidly worsening severe back pain; normal activity/self-management where serious causes are not indicated. |
| S17 | NHS, **Constipation**, last reviewed **26 Oct 2023**, self-care and GP advice. [19](https://www.nhs.uk/conditions/constipation/) | Supports simple measures in uncomplicated adult constipation and routine review if persistent/recurring, blood, weight loss, tiredness or abdominal pain. Emergency obstruction signs come from S9, not a generic “constipation equals emergency” rule. |
| S18 | NHS Every Mind Matters, **Low mood and depression**, page retrieved 12 Nov 2026, “Signs of low mood,” “Support,” and “Urgent support.” [20](https://www.nhs.uk/every-mind-matters/mental-health-issues/low-mood/) | Supports routine help after roughly two weeks/persistent functional impact and urgent support for self-harm/safety concerns. It is not a suicide risk-assessment tool. |
| S19 | India MoHFW, **Tele-MANAS**, current official service page, retrieved 12 Nov 2026. [21](https://telemanas.mohfw.gov.in/home) | India-specific non-emergency mental-health support signpost: **14416** or **1-800-891-4416**. It supplements, never replaces, immediate 112/108 escalation where someone cannot stay safe. |

### Important source differences to retain in rule metadata

* **Adults vs children:** NHS adult pages are not appropriate for young infants/under-fives. S1 must take precedence for those groups.
* **Urgent vs emergency:** S3 explicitly makes persistent vomiting/cannot keep fluid down urgent, while separate immediate signs determine emergency. This supports a split outcome, not the current single registry.
* **Headache/dizziness referral language:** NICE refers to professional assessment/investigation; it does not license an app to diagnose migraine, posterior stroke, BPPV, or dehydration. V2 must route conservatively and state its limits.
* **Fever duration:** S2 discusses clinical investigation timing, S7 routes based on not improving/worsening, and S1 uses child-specific criteria. Exact adult duration cut-offs must be reviewed locally rather than copied as a universal rule.

---

## 6. V2 deterministic architecture

### 6.1 Components and data flow

```text
option-only UI
  -> schema validator (server; reject unknown/contradictory/out-of-path IDs)
  -> rule-table evaluator (versioned table; no NLP)
      1. emergency rules
      2. urgent rules
      3. routine rules
      4. self-care default only when all required path answers are safe
  -> structured result: outcome, matched_rule_ids, reported_option_ids,
                        safe next actions, limitations, source IDs/version
  -> profile-scoped, completed-assessment history/export
```

* There is no free-text-to-triage transformation. The engine receives IDs only.
* Every rule includes `id`, `symptom`, `priority`, `all_of`, `any_of`, `exclusions`, `outcome`, user-facing action, source IDs/sections, source date, evidence status, and clinical review version/date.
* Rule evaluation is deterministic, side-effect-free, and unit-testable. It returns the highest-precedence valid outcome and **all matched rule IDs** for audit; the UI shows a short, non-diagnostic explanation of the winning condition.
* A risk factor/condition must never be silently inferred from profile data. If relevant to a rule, it must be explicitly chosen in the assessment.
* Emergency mode is a render state for the current assessment only. Restart/new assessment clears it. A past completed emergency assessment may be retained in history/export as an auditable record, but it must not make a later assessment emergency.

### 6.2 Strict server contract

Proposed envelope (illustrative; exact JSON Schema is an implementation deliverable after approval):

```json
{
  "schema_version": "health-assessment-v2",
  "age_band": "age_16_to_64",
  "pregnancy_status": "not_applicable",
  "symptoms": ["headache", "nausea_vomiting"],
  "answers": {
    "headache_onset": ["gradual_or_usual"],
    "headache_neuro_warning": ["none"],
    "nausea_vomiting_fluids": ["keeping_fluids_down"]
  },
  "additional_note": null
}
```

Validation requirements:

1. Reject unknown top-level keys unless explicitly versioned/allowed.
2. Reject non-string IDs, unknown IDs, duplicated single-select values, empty required arrays, and IDs that do not belong to a selected symptom path.
3. Enforce `none`/`not_applicable`/`not_sure` mutual-exclusion rules on the server.
4. Require age band; require pregnancy status for the relevant groups/pathways, with `not_sure` and `prefer_not_to_answer` permitted but safety-gated.
5. Require all necessary branch answers before a final result. A missing essential safety answer yields an explanatory blocked screen, not a self-care default.
6. Allow `other_or_not_listed` only as an option ID. If the optional note is retained, limit it (for example 400 characters), escape it on output, exclude it from rule input, and preserve it only with the user’s approved privacy policy.
7. Return a stable `rule_table_version` and `assessment_schema_version` with every result.

### 6.3 Outcome precedence

1. **Emergency**: narrow immediate-danger option combinations. Never suppressed by a lower pathway rule or OTC path.
2. **Urgent medical assessment**: source-supported same-day/prompt patterns without an immediate emergency condition.
3. **Routine consultation**: persistence, recurrence, or functional-impact patterns documented for that symptom.
4. **Self-care and monitoring**: only after all required pathway safety answers are present and no higher rule matches.

The UI should use “Emergency help now,” “Urgent medical assessment,” “Routine consultation,” and “Self-care and monitoring” as the visible headings. It must not use “urgent” styling/action for a `self_care_monitoring` result merely because the person chose a high number on a scale.

---

## 7. Stable option dictionaries

Labels are presentation-only. IDs below are persisted and evaluated. Every non-medication question has `not_sure` and `prefer_not_to_answer` where an unknown answer changes safety; a required unknown may route to urgent assessment instead of forcing a guess.

### 7.1 Shared dictionary

| Question | Type | Stable values |
|---|---|---|
| `age_band` | single | `under_2_months`, `age_2_months_to_4_years`, `age_5_to_11`, `age_12_to_15`, `age_16_to_64`, `age_65_plus`, `not_sure`, `prefer_not_to_answer` |
| `pregnancy_status` | single where applicable | `pregnant_or_possible`, `postpartum_under_6_weeks`, `not_pregnant`, `not_applicable`, `not_sure`, `prefer_not_to_answer` |
| `symptoms` | multi, `feeling_well` exclusive | `fever`, `headache`, `fatigue_tiredness`, `dizziness`, `nausea_vomiting`, `diarrhoea`, `constipation`, `abdominal_pain`, `cough`, `sore_throat`, `body_muscle_pain`, `back_pain`, `joint_pain`, `allergy_symptoms`, `sleep_problems`, `stress_anxiety`, `low_mood`, `other_or_not_listed`, `feeling_well` |
| `duration_short` | single | `under_24_hours`, `one_to_two_days`, `three_to_seven_days`, `one_to_two_weeks`, `over_two_weeks`, `not_sure`, `prefer_not_to_answer` |
| `duration_long` | single | `first_episode_under_two_weeks`, `two_to_four_weeks`, `over_four_weeks`, `recurrent_or_comes_back`, `longstanding_changed_or_worse`, `not_sure`, `prefer_not_to_answer` |
| `impact` | single | `not_stopping_usual_activities`, `affecting_some_activities`, `cannot_manage_usual_activities`, `not_sure`, `prefer_not_to_answer` |
| `severity_reported` | single, informational only | `mild`, `moderate`, `severe`, `very_severe`, `not_sure`, `prefer_not_to_answer` |
| `global_immediate_danger` | multi; `none` exclusive | `severe_breathing_now`, `blue_grey_pale_skin_or_lips`, `central_chest_pain_or_pressure`, `new_one_sided_weakness_face_speech_or_vision_change`, `unconscious_or_cannot_be_woken`, `new_seizure`, `severe_allergy_airway_or_collapse`, `vomiting_or_coughing_blood`, `black_sticky_stool_or_heavy_rectal_bleeding`, `immediate_self_harm_risk`, `none` |
| `existing_conditions` | multi; `none` exclusive | `diabetes`, `heart_or_lung_condition`, `kidney_or_liver_condition`, `immune_suppression_or_cancer_treatment`, `neurological_condition`, `pregnancy_related_condition`, `other_or_not_listed`, `none`, `not_sure`, `prefer_not_to_answer` |

The UI presents only options relevant to the selected path. It must not ask every person a full universal medical questionnaire.

### 7.2 Symptom-path option groups

| Symptom | Required route-specific option IDs (single unless noted) |
|---|---|
| Fever | `fever_measured_band`: `not_measured`, `under_38_c`, `38_to_39_4_c`, `39_5_c_or_higher`, `not_sure`; `fever_course`: `improving`, `not_improving_or_worse`, `not_sure`; `fever_danger_features` multi: `stiff_neck`, `non_blanching_rash`, `confusion_or_hard_to_wake`, `new_seizure`, `none`; `fever_fluids`: `drinking_normally`, `small_sips_only`, `cannot_keep_fluids_down`, `not_sure`. |
| Headache | `headache_onset`: `sudden_maximum_within_5_minutes`, `new_and_unusual`, `gradual_or_usual`, `not_sure`; `headache_warning_features` multi: `fever_and_worsening_headache`, `new_neurological_change`, `new_cognitive_or_personality_change`, `impaired_consciousness`, `recent_head_injury`, `triggered_by_cough_exertion_or_posture`, `new_vomiting_without_clear_cause`, `substantial_pattern_change`, `none`; `headache_duration_pattern`: shared long-duration choices. |
| Fatigue/tiredness | `fatigue_duration`: shared long duration; `fatigue_function`: shared impact; `fatigue_concerns` multi: `unintentional_weight_loss`, `mood_change`, `sleep_gasping_or_choking`, `none`, `not_sure`. |
| Dizziness | `dizziness_timing`: `sudden_now`, `on_standing_or_position_change`, `recurrent`, `persistent`, `not_sure`; `dizziness_features` multi: `new_unsteadiness`, `new_hearing_change`, `new_focal_neurological_change`, `altered_consciousness`, `none`; `dizziness_function`: shared impact. |
| Nausea/vomiting | `vomiting_present`: `nausea_only`, `vomiting_once_or_twice`, `repeated_vomiting`, `not_sure`; `nausea_vomiting_fluids`: `keeping_fluids_down`, `small_sips_only`, `cannot_keep_fluids_down`, `not_sure`; `vomit_features` multi: `blood_or_coffee_grounds`, `green_vomit`, `sudden_severe_headache_or_abdominal_pain`, `confusion_or_not_responding`, `none`. |
| Diarrhoea | `diarrhoea_duration`: `under_48_hours`, `three_to_six_days`, `seven_days_or_more`, `not_sure`; `diarrhoea_hydration`: `drinking_and_urinating_usually`, `some_dehydration_signs`, `cannot_keep_fluids_down`, `not_sure`; `diarrhoea_features` multi: `blood_or_bleeding`, `vomit_blood`, `sudden_severe_pain`, `confusion_or_not_responding`, `none`. |
| Constipation | `constipation_duration`: shared long duration; `constipation_features` multi: `blood_in_stool`, `unintentional_weight_loss`, `persistent_abdominal_pain`, `sudden_change_in_bowel_habit`, `unable_to_pass_stool_or_wind`, `none`; `constipation_self_care_tried`: `not_tried`, `tried_without_improvement`, `not_sure`. |
| Abdominal pain | `abdominal_onset`: `sudden_and_severe`, `sudden_worsening`, `gradual_or_mild`, `not_sure`; `abdominal_features` multi: `vomiting_blood_or_coffee_grounds`, `green_vomit`, `black_sticky_or_heavy_bloody_stool`, `cannot_pee`, `cannot_pass_stool_or_wind`, `non_blanching_rash`, `persistent_vomiting_or_diarrhoea`, `pregnancy_or_possible_pregnancy`, `none`. |
| Cough | `cough_duration`: `under_three_weeks`, `three_weeks_or_more`, `not_sure`; `cough_features` multi: `struggling_to_breathe`, `blue_grey_pale_skin_or_lips`, `confusion`, `coughing_blood`, `chest_pain`, `hard_to_breathe`, `none`; `cough_risk_group`: `none_known`, `pregnant`, `age_65_plus`, `long_term_heart_lung_kidney_condition`, `weakened_immune_system`, `not_sure`. |
| Sore throat | `throat_duration`: `under_one_week`, `one_week_or_more`, `recurrent`, `not_sure`; `throat_features` multi: `unable_to_breathe`, `unable_to_swallow`, `drooling`, `stridor`, `rapidly_worsening_severe_symptoms`, `very_high_temperature_or_shivery`, `dehydration_signs`, `none`. |
| Body/muscle pain | `body_pain_duration`: shared short duration; `body_pain_context` multi: `fever_or_shivers`, `recent_heat_exposure`, `new_weakness_or_numbness`, `none`; `body_pain_function`: shared impact. No diagnosis-specific inference is permitted. |
| Back pain | `back_pain_course`: `new_mild_or_improving`, `sudden_severe_or_rapidly_worse`, `not_improving_after_weeks`, `not_sure`; `back_red_flags` multi: `both_legs_weak_numb_or_tingling`, `saddle_or_genital_numbness`, `new_bladder_or_bowel_change`, `serious_accident`, `fever_or_feeling_unwell`, `none`. |
| Joint pain | `joint_pain_context`: `minor_overuse_or_no_injury`, `fall_or_injury`, `not_sure`; `joint_features` multi: `hot_swollen_skin`, `fever_or_shivery_or_unwell`, `unable_to_walk_or_bear_weight`, `joint_out_of_place`, `numb_or_no_feeling_after_injury`, `none`; `joint_duration`: `under_two_weeks`, `two_weeks_or_more`, `recurring_or_worse`, `not_sure`. |
| Allergy symptoms | `allergy_features` multi: `itchy_eyes_sneezing_or_runny_nose`, `hives_or_itchy_rash_only`, `lip_or_face_swelling_without_airway_symptoms`, `throat_tongue_swelling`, `trouble_breathing_or_swallowing`, `faint_or_collapse`, `none`; `allergy_onset`: `sudden_after_possible_trigger`, `not_sure`. |
| Sleep problems | `sleep_duration`: `under_one_month`, `one_to_three_months`, `three_months_or_more`, `not_sure`; `sleep_impact`: shared impact; `sleep_breathing`: `none_known`, `loud_snoring_gasping_or_choking`, `not_sure`. |
| Stress/anxiety | `stress_duration`: `recent_under_two_weeks`, `two_weeks_or_more`, `recurring_or_worse`, `not_sure`; `stress_impact`: shared impact; `mental_safety` single: `can_keep_myself_safe`, `self_harm_thoughts_but_no_immediate_intent`, `cannot_keep_myself_safe_or_may_act_now`, `not_sure`, `prefer_not_to_answer`. |
| Low mood | `low_mood_duration`: `under_two_weeks`, `two_weeks_or_more`, `not_sure`; `low_mood_impact`: shared impact; `mental_safety`: same controlled choices as stress/anxiety. |

---

## 8. Proposed rule tables

**Legend:** `E` emergency; `U` urgent medical assessment; `R` routine consultation; `S` self-care/monitoring. “Established” means a directly applicable established source supports the escalation shape; “clinical review required” means the exact app phrasing/threshold or India localisation needs sign-off. These are proposed rules, not yet deployed clinical content.

### 8.1 Cross-symptom and child rules

| Rule ID | Conditions and exclusions | Outcome / action | Evidence and status |
|---|---|---|---|
| E-GLOBAL-01 | Any `global_immediate_danger` other than `none`; do not trigger from a severity number or note text. | E. Stop flow; show selected danger fact; call 112 / medical ambulance 108. | S4, S9, S10, S11, S16. Established for listed immediate signs; exact India wording clinical review required. |
| E-MH-01 | `mental_safety = cannot_keep_myself_safe_or_may_act_now` or `immediate_self_harm_risk`. | E. Ask the person to contact 112/108 or go to emergency care; offer Tele-MANAS as additional support, never as a substitute for immediate help. | S18, S19. Clinical review required for safeguarding wording and youth flow. |
| U-MH-01 | `self_harm_thoughts_but_no_immediate_intent`; not E-MH-01. | U. Encourage immediate trusted-person/professional contact and Tele-MANAS 14416 / 1-800-891-4416; do not label it self-care. | S18, S19. Clinical review required. |
| U-AGE-01 | `under_2_months` with fever, feeding concern, breathing concern, lethargy/reduced movement, vomiting/diarrhoea; no E condition already matched. | U, urgent in-person paediatric assessment. | S1 possible serious bacterial infection chart. Established for guarded scope. |
| U-AGE-02 | age under 5 with fever/diarrhoea/cough and an IMNCI danger/dehydration answer not already emergency; or age is unknown for a child-sensitive branch. | U. Caregiver should obtain prompt paediatric advice; no adult self-care/dosing result. | S1. Exact age/UI wording clinical review required. |
| R-OTHER-01 | Only `other_or_not_listed`, no danger selection, and optional note unused by rules. | R or a safe “we cannot assess this listed concern” handoff — **not self-care by default**. | Product safety decision; clinical review required. |

### 8.2 Fever, headache, fatigue, and dizziness

| Rule ID | Conditions and exclusions | Outcome / action | Evidence/status |
|---|---|---|---|
| E-FEVER-01 | Fever with confusion/hard to wake, new seizure, non-blanching rash, or concerning stiff-neck/neurological pattern. | E. Immediate emergency care. | S1, S8. Established, but actual child/adult wording must preserve “not every symptom is necessary.” |
| U-FEVER-01 | Fever is not improving/worse; no E-FEVER-01; adult/appropriate age path. | U. Prompt in-person assessment; no antibiotics/diagnosis advice. | S7; S2 contextual support. Established direction, timing wording clinical review required. |
| S-FEVER-01 | Short fever, drinking normally, no pathway danger/urgent options, not a guarded child/unknown-age path. | S. Rest, fluids, monitor; show return precautions. | S7. Established for general adult self-care. |
| U-HEAD-01 | Sudden maximum intensity within 5 minutes, new neurological/cognitive change, impaired consciousness, recent head trauma, exertional/postural/cough trigger, worsening headache with fever, or new vomiting without clear cause; if E-GLOBAL also matches, E wins. | U (or E when global immediate sign matches). Prompt medical assessment; no migraine diagnosis. | S5 1.1.1–1.1.2. Clinical review required to decide which non-global patterns need emergency vs urgent action locally. |
| R-HEAD-01 | Substantial pattern change, recurrent/chronic headache or headaches affecting activity without U/E features. | R. Book clinician review; offer a non-diagnostic diary. | S5 1.1.1, 1.1.3–1.1.4. Established. |
| S-HEAD-01 | Gradual/usual short headache; no flags; normal function. | S. General comfort/monitoring; return precautions. | S5 supports diary/assessment boundaries; self-care wording needs clinical review. |
| R-FATIGUE-01 | Unexplained fatigue for weeks, affecting daily life, or with selected weight/mood/sleep-breathing concern; no E/U global condition. | R. Book clinician consultation; no inferred anaemia/diabetes/thyroid explanation. | S13. Established. |
| S-FATIGUE-01 | Short-lived tiredness without listed concerning feature/function impact. | S. General rest/sleep routine/monitoring only. | S13. Clinical review of exact content required. |
| E-DIZZY-01 | Sudden dizziness with selected focal neurological change/new unsteadiness/new hearing change, or acute vestibular pattern with inability to walk safely; no app HINTS test is attempted. | E. Immediate assessment for possible stroke pathway. | S6 1.2.1–1.2.4. Established conservative route. |
| R-DIZZY-01 | Recurrent/persistent dizziness, hearing/speech/vision change, fainting/collapse, headache or vomiting with no E condition. | R or U depending on selected acute feature; proposed default U for recent worsening/altered consciousness. | S6 1.2.10; S12. Clinical review required for final split. |
| S-DIZZY-01 | Brief dizziness without imbalance/focal sign and no recurrence/impact. | S. Safety advice (avoid driving/heights while dizzy) and monitoring. | S6 1.2.5; S12. Established direction. |

### 8.3 Gastrointestinal pathways

| Rule ID | Conditions and exclusions | Outcome / action | Evidence/status |
|---|---|---|---|
| E-VOMIT-01 | Vomit blood/coffee grounds, green vomit, sudden severe abdominal pain/headache, confusion/not responding, severe breathing danger, or global E sign. | E. Immediate emergency care. | S3. Established. |
| U-VOMIT-01 | Repeated vomiting or `cannot_keep_fluids_down`, no E-VOMIT-01. | U. Prompt same-day assessment; do **not** tell the person to call 112 solely for this answer. | S3. Established; fixes current no-fluids false emergency. |
| S-VOMIT-01 | Nausea/limited vomiting, keeping fluids down, no E/U feature. | S. Small sips/monitoring, no medication suggestion. | S3. Established general direction. |
| E-DIARR-01 | Vomit blood, sudden severe abdominal pain, confusion/not responding, severe breathing danger, or global E sign. | E. Immediate emergency care. | S3. Established. |
| U-DIARR-01 | Cannot keep fluids down; persistent dehydration signs despite rehydration; bloody diarrhoea; diarrhoea >7 days; vomiting >2 days; guarded child rule; no E condition. | U. Prompt assessment. | S3; S1 for children under 5. Established. |
| S-DIARR-01 | Short episode, able to drink, no blood/danger/dehydration concern. | S. Fluids, hygiene, continue appropriate feeding; return precautions. | S3; S1. Established with age-specific content review. |
| E-ABDO-01 | Sudden severe pain; vomiting blood/coffee grounds/green vomit; black sticky/heavy bloody stool; cannot pee; cannot pass stool/wind; non-blanching rash; struggling to breathe; or global E sign. | E. Immediate emergency care. | S9. Established. |
| U-ABDO-01 | Pain suddenly worsens, pregnancy/possible pregnancy, blood in stool, or persistent vomiting/diarrhoea without E condition. | U. Prompt assessment. | S9. Established direction; pregnancy wording needs local clinical review. |
| R-ABDO-01 | Recurrent/non-resolving mild abdominal pain/bloating/indigestion with no U/E feature. | R. Clinician consultation. | S9. Established. |
| S-ABDO-01 | Mild, short-lived abdominal discomfort without flags and normal function. | S. Monitoring only, no diagnosis. | S9. Clinical review of content required. |
| E-CONST-01 | Constipation with inability to pass stool/wind plus severe/sudden abdominal danger; or global E sign. | E. Immediate emergency care. | S9. Established combination; not constipation alone. |
| R-CONST-01 | Constipation not improving/recurring, blood, weight loss, persistent pain, tiredness or sudden bowel change; no E condition. | R. Routine clinician review. | S17. Established. |
| S-CONST-01 | Uncomplicated short-term adult constipation, no flags. | S. Lifestyle/fluids/fibre information; medication questions stay in OTC/pharmacist route. | S17. Established for adults only. |

### 8.4 Respiratory, throat, body pain, back, joint, and allergy pathways

| Rule ID | Conditions and exclusions | Outcome / action | Evidence/status |
|---|---|---|---|
| E-COUGH-01 | Struggling/gasping/unable to speak, blue-grey-pale skin/lips, sudden confusion, or global E sign. | E. Immediate emergency care. | S11, S10. Established. |
| U-COUGH-01 | Coughing blood, chest pain, hard breathing, very bad/rapidly worsening cough, feels very unwell, or high-risk group; no E condition. | U. Prompt assessment. | S10. Established. |
| R-COUGH-01 | Cough ≥3 weeks without U/E feature. | R. Clinician consultation. | S10. Established. |
| S-COUGH-01 | Short uncomplicated cough, no U/E feature. | S. Rest/fluids/monitoring, no antibiotic recommendation. | S10; S2. Established direction. |
| E-THROAT-01 | Unable to breathe/swallow, drooling, stridor, or rapidly worsening severe symptoms. | E. Immediate emergency care. | S11. Established. |
| U-THROAT-01 | Very high temperature/shivery, dehydration signs, weakened immune system, no E condition. | U. Prompt assessment. | S11. Established. |
| R-THROAT-01 | Not improving after one week or recurrent. | R. Routine consultation. | S11. Established. |
| S-THROAT-01 | Ordinary sore throat <1 week without flags. | S. Fluids/rest/monitoring. | S11. Established direction. |
| U-BODY-01 | Body/muscle pain with selected fever/shivers or heat-exposure concern, or new weakness/numbness; no E global rule. | U. Prompt assessment; no named disease inference. | S1/S2 for febrile context; S16 for neurological concerns. Clinical review required: no stand-alone body-ache consumer decision table was found. |
| S-BODY-01 | Short mild body/muscle pain with no concerning associated option/function impact. | S. General rest/monitoring. | Clinical review required. This rule is intentionally limited. |
| E-BACK-01 | Bilateral leg neurological symptoms, saddle/genital numbness, new bladder/bowel/sexual-function change, serious accident, chest pain, or global E sign. | E. Immediate emergency care. | S16. Established. |
| U-BACK-01 | Fever/feeling unwell with back pain, sudden severe pain, or rapid worsening; no E condition. | U. Prompt assessment. | S16. Established. |
| R-BACK-01 | Not improving after weeks, limits normal activities, concerning persistence/night change without U/E feature. | R. Routine consultation. | S16; S18. Established direction. |
| S-BACK-01 | New mild/improving back pain without flags. | S. Stay active within capability/monitor; no medication instruction. | S16, S18. Established. |
| E-JOINT-01 | Severe joint pain after fall/injury with unable to bear weight, deformity/out of place, or numb/no feeling; or global E sign. | E. Immediate emergency care. | S15. Established. |
| U-JOINT-01 | Hot/swollen joint or joint pain with fever/shivery/generally unwell; no E injury condition. | U. Prompt assessment. | S15. Established. |
| R-JOINT-01 | Pain/swelling >2 weeks, recurring/worsening, sleep/activity impact. | R. Routine consultation. | S15. Established. |
| S-JOINT-01 | Mild joint pain after overuse, no injury/danger/fever/hot swelling. | S. Rest/avoid complete immobilisation/monitor. | S15. Clinical review of consumer wording required. |
| E-ALLERGY-01 | Throat/tongue swelling, difficulty breathing/swallowing, blue-grey-pale skin, faint/collapse/confusion after possible trigger. | E. Immediate emergency care. | S4. Established. |
| U-ALLERGY-01 | Face/lip swelling without listed airway/circulation concern or symptoms getting worse; no E condition. | U. Prompt assessment. | S4 distinguishes severe symptoms; final threshold needs allergy clinician review. |
| S-ALLERGY-01 | Limited sneezing/itchy eyes/runny nose or hives-only option without escalation; no E/U feature. | S. General avoidance/monitoring; OTC education remains separately gated. | S4. Clinical review required for final content. |

### 8.5 Sleep, stress/anxiety, and low mood

| Rule ID | Conditions and exclusions | Outcome / action | Evidence/status |
|---|---|---|---|
| R-SLEEP-01 | Sleep problem for months, daily-life coping impact, or reported loud snoring/gasping/choking; no E/U mental/global condition. | R. Clinician consultation; do not suggest prescription sleeping medication. | S14. Established. |
| S-SLEEP-01 | Short-term sleep trouble without safety/function concern. | S. Sleep-routine information and monitoring. | S14. Established. |
| R-STRESS-01 | Stress/anxiety ≥2 weeks/recurring and affecting usual functioning, while `mental_safety = can_keep_myself_safe`. | R. Routine mental-health/primary-care support; show Tele-MANAS. | S18, S19. Clinical review required for exact duration threshold. |
| R-LOWMOOD-01 | Low mood ≥2 weeks or affects daily life; able to stay safe. | R. Routine professional support; show Tele-MANAS. | S18, S19. Established direction. |
| S-MOOD-01 | Recent low mood/stress, able to stay safe, no major functional impact. | S. Non-diagnostic wellbeing support/monitoring; show clear route to help if it persists/worsens. | S18. Clinical review required. |

---

## 9. Interaction design

1. **Start:** “Choose all that apply today.” Multi-select symptom pills with circular indicators; `feeling_well` exclusive. No emoji, photographic people, chatbot text box, diagnosis language, or decorative illustration.
2. **Immediate safety:** A short, controlled option set appears only when symptoms need it. It says “These questions help choose the right level of care; selecting one does not diagnose a condition.” A neutral Help link displays 112/108 at all times.
3. **Dynamic symptom sections:** Keep one branch per selected symptom. Question IDs, values, and answers are preserved when the person goes Back/edits the symptom list. Remove answers only for paths no longer selected, with a clear confirmation.
4. **Shared context:** age band first; pregnancy/medical-context prompts only where relevant; existing-condition multi-select with strict None exclusivity.
5. **Review:** Show the human labels and all selected symptoms, but submit IDs. Each question has an Edit button. Confirm text says “Get general guidance,” not “diagnosis.”
6. **Result:** One outcome heading, concise matched facts, safe action, return precautions, limitations, and source/review information. Do not show the red emergency visual treatment for urgent/routine/self-care results.
7. **Restart:** Explicitly clears only the in-progress assessment result/state. The prior completed history entry remains history; it cannot preselect danger answers or block a new safe assessment.
8. **Accessibility:** keyboard-operable pill controls, `aria-pressed`, visible focus/selected state, contrast checks, small-screen vertical flow, no reliance on colour alone, no decorative emoji.

---

## 10. OTC reference boundary

The V2 triage outcome is decided **before** any medicine education. Medication information never suppresses an emergency/urgent result.

| Boundary | V2 requirement |
|---|---|
| Medicines in scope | Only the existing local, versioned references for **paracetamol** and **cetirizine**; do not broaden to antibiotics, combinations, supplements, or a free-text drug search. |
| Trigger | A person deliberately starts the separate `otc_information` option journey. A symptom assessment must not automatically “recommend” a medicine. |
| Inputs | Stable-ID topic, age band, medicine allergy, liver/kidney/other conditions, pregnancy/breastfeeding, current medicines, previously taken product, and relevant symptom safety questions. Unknown/declined/concerning answers block numeric medicine reference. |
| Precedence | `emergency` → no OTC output; `urgent_medical_assessment` → no OTC output that could delay care; `routine_consultation` → general pharmacist/clinician handoff; only a cleared `self_care_monitoring` route may show tightly bounded source-cited education. |
| Children | Never show adult information to a child. Retain the current no-child-paracetamol-calculation guard. Do not expand paediatric cetirizine wording until pharmacy/paediatric clinical review decides whether to retain, remove, or revise the existing age-matched source reference. |
| Output | “Source-cited general information, not a personal recommendation.” Include source URL, source date, local reference version/review date, warnings, and pharmacist handoff. No interaction assurance and no personalised plan. |
| Data sources | Preserve the existing catalogue’s NHS and MedlinePlus URLs/review dates; review them on a scheduled cadence and on material safety notices. |

This maintains the existing strict OTC endpoint’s valuable server-side validation while making triage precedence explicit.

---

## 11. Comprehensive test matrix

Every implemented rule requires a unit test named by its stable rule ID, source version, and expected outcome. The table below is the minimum acceptance matrix; it does not replace clinical review.

| Test group | Required cases |
|---|---|
| Schema/contract | Valid minimal envelope; required-field missing; empty list; unknown ID; malformed types; duplicate single value; None plus another value; unknown question ID; value from an unselected path; unexpected top-level property; schema-version mismatch; Unicode/escaped optional note; optional note not fed into rules. |
| Outcome precedence | Each E rule; each U rule with no E rule; each R rule with no E/U; each S default; a simultaneous E+U+R returns E and records all matched IDs; a U+R returns U; source/rule version present. |
| Severity guard | Each severity value with otherwise identical safe answer returns the same S result; severity cannot alone produce E/U/R; severe symptom-specific option combinations still work only via their named rule. |
| Fever | Adult short uncomplicated S; not-improving/worse U; fever with each selected immediate danger E; no-fluid U rather than E; child/young-infant guard paths; unknown age safety gate; fever combined with headache/cough/diarrhoea. |
| Headache | Usual short S; each CG150 warning option U/E as table specifies; sudden maximum-onset path; neurological global E; recurrence/pattern change R; high numeric severity alone no escalation. |
| Fatigue | Short uncomplicated S; weeks/function impact R; weight/mood/sleep-breathing R; combinations with fever/dizziness/headache obey higher rule. |
| Dizziness | Brief no focal sign S; persistent/recurrent R; sudden focal/new unsteadiness E; altered consciousness path; no HINTS/diagnosis statement emitted. |
| Nausea/vomiting | Nausea-only S; cannot keep fluid U; blood/green vomit/sudden severe pain/confusion E; child and pregnancy-sensitive paths. |
| Diarrhoea | Short/fluid-tolerant S; cannot keep fluid/dehydration/blood/persistence U; E combinations; child IMNCI route. |
| Constipation/abdominal pain | Simple constipation S; persistent/red-flag R; obstruction/bleeding/sudden severe/pregnancy U or E as table; each abdominal danger option. |
| Cough/sore throat | Short uncomplicated S; cough >3 weeks R; cough blood/chest/hard breath U; struggling/blue/confusion E; throat >1 week R; dehydration/high fever U; unable swallow/drool/stridor E. |
| Body/muscle/back/joint | Body-pain limited safe path and required clinician-review absence; back cauda-equina choices E; systemic/rapid worsening U; persistent R; joint hot/swollen/fever U; injury unable weight/deformity/no feeling E; uncomplicated overuse S. |
| Allergy | Mild listed symptoms S; worsening face/lip swelling U; all anaphylaxis IDs E; OTC result cannot appear when U/E. |
| Sleep/stress/low mood | Short sleep/mood S; insomnia months/function R; mood ≥2 weeks R; self-harm thought no immediate intent U with Tele-MANAS; cannot keep safe E; emergency wording no longer appears on routine result. |
| Multi-symptom | At least every pair involving fever, headache, dizziness, abdominal pain, cough, and low mood; answers retained per symptom; removing one symptom removes only its branch; rule precedence deterministic; no first-duration/first-severity collapse. |
| Navigation/state | Back/edit preserves answers; review shows all IDs/labels; restart clears transient outcome; safe reassessment after an emergency works; historic emergency does not set current assessment emergency; completed assessment history/export remains profile-scoped; profile purge deletes it. |
| OTC | Existing paracetamol/cetirizine tests retained; all invalid values rejected; age unknown/risky safety answers hand off; no adult child wording; no output on E/U; reference source/review metadata present. |
| UI/accessibility | No text message box in V2; no emoji; visible selected indicators; keyboard/Enter/Space; focus order; contrast; responsive panel; review/edit; progress; source link labels; visual regression proves red emergency panel appears only for actual E result. |
| Regression | Full pytest and UI smoke; Food Scanner model hashes before/after; food recognition/API/catalogue/logging/navigation/onboarding/account switching/themes/mobile/keyboard/contrast unchanged. |

Suggested implementation test artefacts after approval:

* `tests/test_assistant_v2_schema.py`
* `tests/test_assistant_v2_rules.py` (one test per rule ID, table-driven)
* `tests/test_assistant_v2_api.py`
* `tests/test_assistant_v2_history.py`
* `tests/ui_health_assistant_v2.js`
* a checked-in, human-reviewed `data/health_assistant_v2_rules.json` or Python equivalent with source metadata and review status.

---

## 12. Outcome audit and change-control plan

1. **Rule trace in every result:** store schema version, rule-table version, matched rule IDs, selected IDs, outcome, and timestamp. Do not store derived diagnosis/probability because none is produced.
2. **Privacy:** keep history profile-scoped, exportable, and purgeable. If an optional note is retained, document it as local sensitive content and exclude it from rule evaluation. No third-party telemetry or remote clinical API.
3. **Aggregate audit (only if user-approved local analytics exists):** count outcome/rule distributions, unknown/declined safety answers, abandoned path step, restart after emergency, and reclassification after edit. Do not infer a medical truth label from app use.
4. **Clinical review queue:** allow only an authorised clinical reviewer to propose a rule/source update; record reviewer, rationale, source section/date, effective version, tests added, and rollback plan.
5. **Safety review triggers:** immediate review on a credible false-negative/false-positive report, source change, emergency-contact change, a new paediatric rule, a medication-reference change, or any rule that materially changes escalation volume.
6. **Release gates:** approved rule table, 100% rule-ID tests passing, manual UI/accessibility review, full existing regression suite, protected-model hash verification, and PR review. Never learn or auto-tune rules from chat history.

---

## 13. Approved-implementation sequence (only after the gate)

1. Obtain written product/clinical answers to section 14; freeze a source-reviewed rule-table version.
2. Add the V2 stable schema and pure evaluator beside the legacy engine; unit-test every table rule before UI switch-over.
3. Build the new option-only UI behind the current Health Assistant launcher; preserve history/export/purge, Back/review/restart and profile scoping.
4. Remove/hide free-text input from the V2 product surface; retain old message records for export compatibility but do not route new V2 input through regex triage.
5. Move the persistent emergency notice to neutral Help treatment; introduce outcome-specific status views.
6. Integrate unchanged OTC reference flow with V2 outcome precedence.
7. Run complete test matrix and Food Scanner integrity checks; update README and PR #16 description only after approved implementation.

No merge to `main` is proposed. Changes remain on `arena/5dab7076-nutricare` and update PR #16 only.

---

## 14. Required clinical/product decisions before implementation

1. **Clinical ownership:** identify the qualified India-relevant clinician/pharmacy reviewer who will approve source interpretation, language, child safety scope, and release changes.
2. **Paediatric scope:** approve whether V2 covers 5–15-year-olds beyond a guarded referral route, and which exact India/local sources govern each pathway. Under-2-month and under-5 IMNCI guards must remain conservative.
3. **Emergency vs urgent split:** approve the exact disposition for sudden severe headache, fainting/blackout, facial/lip swelling without airway symptoms, severe abdominal pain, and acute dizziness without a clinician-performed exam. The report intentionally does not convert every such option into 112.
4. **Fever thresholds:** approve adult and child duration/temperature wording for local deployment. ICMR/NHM/NHS sources differ in target population and purpose; no universal numeric rule should be invented.
5. **Mental-health safety:** approve age-appropriate immediate-risk, non-immediate self-harm, trusted-person, Tele-MANAS, and emergency-service copy; determine whether youth safeguarding/local resources must be added.
6. **“Other” conflict:** approve either (a) zero arbitrary text in V2, or (b) the proposed non-triage bounded attachment with clear privacy disclosure. It must never drive a rule.
7. **OTC paediatric cetirizine:** approve whether existing numeric child source wording remains; the safe default is to hand off rather than add/expand it.
8. **Persistence:** confirm that historical completed emergency results may appear in local history/export while no emergency state persists into a new assessment. If the product instead requires deleting emergency history, reconcile that with audit/history requirements.
9. **Routine outcome copy:** approve the local phrasing and services (“GP/clinic/PHC”, pharmacy, clinician) appropriate for India, without claiming the app books or verifies a service.
10. **Clinical audit process:** approve reviewer cadence, issue intake, release sign-off, and rollback owner.

---

## 15. Report completion checklist

* [x] Existing frontend, backend, API, local chat, OTC flow, persistence, and tests inspected.
* [x] Over-triage claims separated into reproduced behaviour, likely UI contributor, and non-confirmed hypotheses.
* [x] India MoHFW/NHM/ICMR, NICE, NHS, WHO-compatible evidence hierarchy considered; source URLs, dates, sections, differences, and unresolved review points recorded.
* [x] All requested symptom pathways have an evidence-supported proposed path or are explicitly limited pending clinical review.
* [x] Four outcomes, stable option IDs, multi-symptom design, validation, medication boundaries, test matrix, audit plan, and clinical questions specified.
* [x] No V2 triage implementation or protected-model change made.
