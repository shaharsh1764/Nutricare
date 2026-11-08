#!/usr/bin/env python3
"""Licence and provenance policy for the V2/V4 Indian food dataset.

Three checks that must never be conflated
-----------------------------------------
1. **Technical validity** — does the file decode as an image, is it big enough.
2. **Label correctness** — does the picture actually show the class.
3. **Rights status** — is there a defensible basis to use it.

This module owns only #3. It never inspects pixels and never judges whether a
picture shows a biryani. Keeping the three separate is the whole point: an image
can be perfectly valid and correctly labelled and still be unusable for lack of
rights, or perfectly licensed and show the wrong food.

The rights tiers
----------------
``TRAINING_APPROVED``
    CC0 / Public domain / CC BY, with an author recorded. These are the only
    files that may enter a training-approved set.

``REVIEW_REQUIRED``
    CC BY-SA. Permitted in principle, but share-alike obligations on derived
    artefacts are legally unsettled, so these are held separately and are NOT
    training-approved until that question is resolved.

``EXCLUDED``
    NC, ND, unknown, missing or unrecognised licences, and anything carrying a
    Commons ``Restrictions`` flag. Never enters a training set.

Why a declaration is not ownership
----------------------------------
``verification`` is always ``declared_only``. Commons records what the uploader
asserted; it does not verify the uploader owned the photograph. Provenance
*strength* is therefore tracked separately from licence class, because a CC BY
Flickr import with a review bot's confirmation is more defensible than a bare
"own work" claim on a professional-looking food photo.

Nothing here is legal advice, and nothing is ever reported as "cleared".
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

TRAINING_APPROVED = "TRAINING_APPROVED"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
EXCLUDED = "EXCLUDED"

#: Licence classes (as produced by training.commons_audit) that may be trained on.
_APPROVED_CLASSES = frozenset({"CC0_PD", "CC_BY"})
#: Permitted in principle but held pending the share-alike question.
_REVIEW_CLASSES = frozenset({"CC_BY_SA"})

# Provenance signalling.
#
# These four concepts are kept strictly apart. Conflating them is how a project
# ends up claiming a right it does not have:
#
#   transfer history      "Transferred from en.wikipedia"  -> NOT a review
#   attribution text      "Own work", a photo description -> NOT evidence
#   permission evidence   an explicit release/licence grant -> possibly useful
#   independent review    a licence-review bot's confirmation -> useful
#
# Only the last two may raise provenance above "unknown", and only ever to a
# *declared* strength: nothing here establishes that the uploader owned the
# work.

#: A Commons licence-review bot's confirmation. Anchored on the review bots and
#: explicit review verbs; deliberately does NOT match "transferred from", which
#: is a wiki housekeeping note describing where a file was copied from.
_INDEPENDENT_REVIEW = re.compile(
    r"(flickr\s*review"                      # {{flickrreview|bot|date}} template
    r"|flickr[\s_-]*(upload|review)[\s_-]*bot"
    r"|\breviewed by\b"
    r"|\bconfirmed to be (licensed|free|available)\b"
    r"|\blicense reviewed\b"
    r"|\bthis (file|image) (has been|was) reviewed\b)",
    re.IGNORECASE,
)

#: Explicit permission / release language. Weak on its own: it says a grant is
#: asserted, not that it was verified. Never a clearance.
_PERMISSION_EVIDENCE = re.compile(
    r"(\bpermission (to use|granted|is granted|was granted)\b"
    r"|\bused with permission\b"
    r"|\breleased under\b"
    r"|\bcc[\s-]?by\b"
    r"|\bcreative commons\b)",
    re.IGNORECASE,
)

#: Attribution-completeness signals. These describe *who to credit*, not rights.
_ATTRIBUTION_TEXT = re.compile(
    r"(own work|self[- ]photographed|self[- ]made|uploaded by|photo by"
    r"|photograph by|author name string)",
    re.IGNORECASE,
)

#: Wiki housekeeping. Records where a file came from, never a licence review.
_TRANSFER_HISTORY = re.compile(
    r"(transferred from|moved from|imported from|originally uploaded"
    r"|commonshelper|uploaded to (the )?english wikipedia)",
    re.IGNORECASE,
)

#: Anything suggesting a scraped or re-hosted source.
_SCRAPE_RISK = re.compile(
    r"(google (image|search)|bing (image|search)|scraped|clip ?art|pinterest"
    r"|wallpaper|unknown source|source unknown|no source|found (on|via) the (web|internet)"
    r"|downloaded from (a )?(website|blog|facebook|instagram))",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Public Domain designations
# ---------------------------------------------------------------------------
#
# ``commons_audit`` folds CC0 and every Public Domain template into one
# ``CC0_PD`` bucket, so the bucket alone cannot tell a voluntary CC0 dedication
# from a jurisdiction- or provenance-specific PD claim. The distinction has to
# come from ``short_name``.
#
# Accepted: a bare CC0 dedication. CC0 waives attribution, so an author name is
# not a condition of use, and anonymous CC0 material is legitimately usable.
_CC0_SHORT = re.compile(r"^\s*(cc0|cc[\s-]?zero)\b", re.IGNORECASE)

# Deferred: PD designations that are NOT automatically treated as CC0.
#
# Each of these asserts a *reason* the work is out of copyright (a government
# publication, an expired term, a non-US jurisdiction, a donor agreement). We
# have no records of these designations in the collected corpus, so no template
# is accepted yet, and none may be inferred as equivalent to CC0.
# Ordered most-specific first: "PD-Art" must not be reported as "PD-old".
_DEFERRED_PD_SHORT = {
    "pd_usgov": re.compile(r"^\s*pd[\s-]?us[-\s]?gov", re.IGNORECASE),
    "pd_art": re.compile(r"^\s*pd[\s-]?art\b", re.IGNORECASE),
    "pd_scan": re.compile(r"^\s*pd[\s-]?scan\b", re.IGNORECASE),
    "pd_old": re.compile(r"^\s*pd[\s-]?old\b", re.IGNORECASE),
    "pd_india": re.compile(r"^\s*pd[\s-]?india\b", re.IGNORECASE),
    "pd_self": re.compile(r"^\s*pd[\s-]?(self|author|user)\b", re.IGNORECASE),
    "no_known_copyright": re.compile(r"no known copyright", re.IGNORECASE),
    "public_domain_generic": re.compile(r"^\s*public\s+domain", re.IGNORECASE),
    # Catch-all must stay last so a named family always wins.
    "pd_other_template": re.compile(r"^\s*pd[\s-]", re.IGNORECASE),
}


def public_domain_designation(short_name: str) -> Optional[str]:
    """Name the Public Domain designation carried by ``short_name``.

    Returns ``None`` for a plain CC0 dedication (handled separately), otherwise
    a stable key for the PD template family. Unknown PD-looking strings return
    ``"pd_unrecognised"`` rather than being guessed into a known family.
    """
    short = (short_name or "").strip()
    if not short:
        return None
    if _CC0_SHORT.search(short):
        return None
    for key, pattern in _DEFERRED_PD_SHORT.items():
        if pattern.search(short):
            return key
    if re.search(r"\bcopyright expired\b|\bcopyright term\b", short, re.IGNORECASE):
        return "pd_unrecognised"
    return None


def classify_provenance(
    *,
    permission_text: str = "",
    credit_text: str = "",
) -> Dict[str, Any]:
    """Classify how much a file's provenance text actually tells us.

    Returns ``{"strength", "signals", "reasons"}`` where ``strength`` is one of:

    ``scrape_risk``      text indicates a scraped or re-hosted source
    ``independent_review`` text claims a licence-review bot confirmation
    ``permission_asserted`` text asserts a permission or release
    ``attribution_only`` text only describes who to credit
    ``transfer_only``    text only records a wiki transfer
    ``unknown``          nothing usable, or nothing passed in

    ``permission_text`` (the Commons ``Permission`` field) outranks
    ``credit_text``. ``Credit`` on Flickr imports is routinely just the photo's
    description, so it is the weaker signal of the two.

    Nothing here establishes ownership. A review bot confirms that the *licence
    tag* matches the source, not that the uploader owned the photograph, so the
    result is still only a declaration.
    """
    permission_text = (permission_text or "").strip()
    credit_text = (credit_text or "").strip()
    signals: List[str] = []
    reasons: List[str] = []

    if not permission_text and not credit_text:
        reasons.append(
            "no permission/credit text captured; provenance strength unknown"
        )
        return {"strength": "unknown", "signals": signals, "reasons": reasons}

    combined = f"{permission_text} {credit_text}".strip()

    # 1. Scraping risk dominates: it disqualifies regardless of other text.
    if _SCRAPE_RISK.search(combined):
        reasons.append(
            "provenance text suggests a scraped or re-hosted source; "
            "downloadable is not the same as licensed"
        )
        return {"strength": "scrape_risk", "signals": ["scrape_indicator"],
                "reasons": reasons}

    # 2. Independent review: requires a bot/review claim in Permission, or an
    #    explicit review statement. A wiki transfer never qualifies.
    if _INDEPENDENT_REVIEW.search(permission_text):
        reasons.append(
            "Permission field records a licence-review confirmation; this confirms "
            "the licence tag matched the source, not the uploader's ownership"
        )
        return {"strength": "independent_review", "signals": ["permission_review"],
                "reasons": reasons}
    if _INDEPENDENT_REVIEW.search(credit_text):
        reasons.append(
            "Credit text claims an independent review, but Credit is the weaker "
            "field; treated as asserted, not confirmed"
        )
        signals.append("credit_review_claim")

    # 3. Permission evidence: an asserted grant.
    if _PERMISSION_EVIDENCE.search(permission_text):
        reasons.append("Permission field asserts a release or permission")
        return {"strength": "permission_asserted",
                "signals": signals + ["permission_asserted"], "reasons": reasons}

    # 4. Attribution-only text describes who to credit, not rights.
    if _ATTRIBUTION_TEXT.search(combined):
        reasons.append("provenance text only describes attribution; it is not "
                       "evidence of permission")
        return {"strength": "attribution_only",
                "signals": signals + ["attribution_text"], "reasons": reasons}

    # 5. Transfer history is wiki housekeeping, never a licence review.
    if _TRANSFER_HISTORY.search(combined):
        reasons.append("provenance text records a wiki transfer; a transfer is "
                       "not a licence review and confers no permission")
        return {"strength": "transfer_only",
                "signals": signals + ["transfer_statement"], "reasons": reasons}

    # 6. Present but uninformative.
    reasons.append("provenance text present but carries no usable signal")
    return {"strength": "unknown", "signals": signals, "reasons": reasons}


def classify_rights(
    licence: Dict[str, Any],
    *,
    artist: str = "",
    permission_text: str = "",
    credit_text: str = "",
) -> Dict[str, Any]:
    """Place one file in a rights tier.

    Returns a dict that always carries ``reasons`` explaining the decision, so a
    rejection is auditable rather than a silent filter.
    """
    declared = licence.get("declared_class") or "UNKNOWN_MISSING"
    if not artist:
        # Convenience: accept the artist embedded in a commons_audit licence dict.
        artist = licence.get("artist_raw") or ""
    artist = (artist or "").strip()
    attribution_required = licence.get("attribution_required")
    short_name = (licence.get("short_name") or "").strip()
    # ``classify_licence`` can bucket a file as CC0_PD from UsageTerms/License
    # while LicenseShortName is empty, so fall back to that text rather than
    # discarding a real designation. If neither is present, there is genuinely
    # no basis to decide and the file fails closed below.
    designation_text = short_name or (licence.get("usage_terms") or "").strip()
    reasons: List[str] = []

    provenance = classify_provenance(permission_text=permission_text, credit_text=credit_text)
    provenance_strength = provenance["strength"]
    reasons.extend(provenance["reasons"])

    # --- tiering ---------------------------------------------------------
    #
    # The author requirement is applied per licence, not to a shared bucket.
    # CC0 waives attribution, so it must not require an author; CC BY and
    # CC BY-SA both impose attribution obligations, so both must.
    pd_designation: Optional[str] = None
    attribution_sufficient = bool(artist)

    if provenance_strength == "scrape_risk":
        tier = EXCLUDED
        reasons.append("permitted licence but provenance indicates scraping")
    elif declared == "CC0_PD":
        pd_designation = public_domain_designation(designation_text)
        if pd_designation is not None:
            # A Public Domain claim is not the same thing as a CC0 dedication.
            # Each family asserts a different reason the work is out of
            # copyright, and none of them has been reviewed for this corpus.
            tier = REVIEW_REQUIRED
            reasons.append(
                f"Public Domain designation {pd_designation!r} is not treated as "
                "equivalent to CC0; deferred to human review pending a per-template "
                "assessment"
            )
        elif _CC0_SHORT.search(designation_text):
            # CC0: attribution is waived, so an author name is not required.
            tier = TRAINING_APPROVED
            reasons.append(
                "CC0 dedication waives attribution; author name not required"
            )
            if not artist:
                reasons.append("no author recorded (permitted for CC0, but the "
                               "attribution record will show 'unknown')")
        else:
            # CC0_PD bucket with a short_name we cannot place. Fail closed.
            tier = EXCLUDED
            reasons.append(
                f"CC0_PD bucket but short_name {designation_text!r} is neither a "
                "CC0 dedication nor a recognised Public Domain designation"
            )
    elif declared in _REVIEW_CLASSES:
        pd_designation = public_domain_designation(designation_text)
        if not attribution_sufficient:
            # Share-alike does not excuse a missing author. Without one there is
            # nobody to attribute, so the file cannot satisfy its own licence.
            tier = EXCLUDED
            reasons.append(
                f"{declared} requires attribution but no usable author is recorded; "
                "a missing author must not be bypassed by entering the review branch"
            )
        else:
            tier = REVIEW_REQUIRED
            reasons.append(
                f"{declared}: share-alike obligations on derived artefacts are "
                "unsettled; held out of the training-approved set pending legal review"
            )
    elif declared == "CC_BY":
        if not attribution_sufficient:
            tier = EXCLUDED
            reasons.append("attribution-bearing licence but no author recorded")
        else:
            tier = TRAINING_APPROVED
            reasons.append(
                "CC BY permits commercial use and modification; author recorded"
            )
    else:
        tier = EXCLUDED
        reasons.append(f"{declared} is not usable for training")

    return {
        "rights_tier": tier,
        "declared_class": declared,
        "verification": "declared_only",
        "provenance_strength": provenance_strength,
        "provenance_signals": provenance["signals"],
        "public_domain_designation": pd_designation,
        "attribution_sufficient": attribution_sufficient,
        "short_name": short_name,
        "designation_text": designation_text,
        # Never true from metadata alone: a human must still review the image.
        "training_approved": tier == TRAINING_APPROVED,
        "human_review_required": True,
        "legal_clearance": "not_verified",
        "attribution_required": attribution_required,
        "reasons": reasons,
    }


def rights_summary(tiers: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Count tiers and explain what each count does and does not mean."""
    counts = {TRAINING_APPROVED: 0, REVIEW_REQUIRED: 0, EXCLUDED: 0}
    strengths: Dict[str, int] = {}
    for entry in tiers:
        counts[entry["rights_tier"]] = counts.get(entry["rights_tier"], 0) + 1
        key = entry.get("provenance_strength", "unknown")
        strengths[key] = strengths.get(key, 0) + 1
    return {
        "by_tier": counts,
        "by_provenance_strength": strengths,
        "note": "TRAINING_APPROVED means the DECLARED licence permits it and an author "
        "is recorded. It is not legal clearance and it is not human approval.",
        "cc_by_sa_policy": "tracked separately; excluded from training-approved sets "
        "until the share-alike question is resolved",
    }


# ---------------------------------------------------------------------------
# Attribution record generation
# ---------------------------------------------------------------------------


def attribution_record(file_entry: Dict[str, Any]) -> Dict[str, Any]:
    """Build the per-image attribution record required for redistribution."""
    licence = file_entry.get("licence") or {}
    attribution = file_entry.get("attribution") or {}
    return {
        "pageid": file_entry.get("pageid"),
        "title": file_entry.get("title"),
        "sha1": file_entry.get("sha1"),
        "source_url": file_entry.get("description_url"),
        "author": attribution.get("artist_raw") or "",
        "licence_short": licence.get("short_name") or "",
        "licence_url": licence.get("licence_url") or licence.get("licence_url_derived") or "",
        "attribution_required": licence.get("attribution_required"),
    }


def render_attributions(records: List[Dict[str, Any]], *, title: str = "Attributions") -> str:
    """Render a Markdown attribution file from per-image records."""
    lines = [
        f"# {title}",
        "",
        "Every image below is from Wikimedia Commons and is used under the licence",
        "shown. Attribution is reproduced as recorded by the Commons API.",
        "",
        "**This file is generated. Do not hand-edit.**",
        "",
        "| Image | Author | Licence | Source |",
        "|---|---|---|---|",
    ]
    for r in sorted(records, key=lambda x: (x.get("title") or "")):
        title_text = (r.get("title") or "").replace("|", r"\|")
        author = (r.get("author") or "unknown").replace("|", r"\|")
        licence = r.get("licence_short") or "unknown"
        url = r.get("licence_url") or ""
        source = r.get("source_url") or ""
        if url:
            licence = f"[{licence}]({url})"
        lines.append(f"| [{title_text}]({source}) | {author} | {licence} | Commons |")
    lines.append("")
    lines.append(
        "Nothing in this file constitutes legal clearance. Licences are as declared "
        "by the uploader and have not been independently verified."
    )
    return "\n".join(lines) + "\n"
