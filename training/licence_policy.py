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

#: Machine-readable markers that suggest an independent provenance check.
_STRONG_PROVENANCE = re.compile(
    r"(flickr (upload|review) bot|review bot|confirmed to be licensed|"
    r"originally posted to flickr|transferred from|verified by)",
    re.IGNORECASE,
)
#: Markers that suggest low provenance confidence.
_WEAK_PROVENANCE = re.compile(
    r"(own work|self[- ]photographed|self[- ]made)", re.IGNORECASE
)
#: Anything suggesting a scraped or re-hosted source.
_SCRAPE_RISK = re.compile(
    r"(google (image|search)|bing|scraped|clip ?art|pinterest|wallpaper|"
    r"unknown source|source unknown|no source)",
    re.IGNORECASE,
)


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
    reasons: List[str] = []

    provenance_text = f"{permission_text} {credit_text}".strip()
    provenance_strength = "unknown"
    if provenance_text:
        if _SCRAPE_RISK.search(provenance_text):
            provenance_strength = "scrape_risk"
            reasons.append(
                "provenance text suggests a scraped or re-hosted source; "
                "downloadable is not the same as licensed"
            )
        elif _STRONG_PROVENANCE.search(provenance_text):
            provenance_strength = "external_review"
            reasons.append("provenance text indicates an independent licence review")
        elif _WEAK_PROVENANCE.search(provenance_text):
            provenance_strength = "self_declared"
            reasons.append("provenance rests on an uploader 'own work' claim")
    else:
        reasons.append("no permission/credit text captured; provenance strength unknown")

    # --- tiering ---------------------------------------------------------
    if declared in _APPROVED_CLASSES:
        if not artist:
            tier = EXCLUDED
            reasons.append("attribution-bearing licence but no author recorded")
        elif provenance_strength == "scrape_risk":
            tier = EXCLUDED
            reasons.append("permitted licence but provenance indicates scraping")
        else:
            tier = TRAINING_APPROVED
            reasons.append(
                f"{declared} permits commercial use and modification; author recorded"
            )
    elif declared in _REVIEW_CLASSES:
        tier = REVIEW_REQUIRED
        reasons.append(
            "CC BY-SA: share-alike obligations on derived artefacts are unsettled; "
            "held out of the training-approved set pending legal review"
        )
    else:
        tier = EXCLUDED
        reasons.append(f"{declared} is not usable for training")

    return {
        "rights_tier": tier,
        "declared_class": declared,
        "verification": "declared_only",
        "provenance_strength": provenance_strength,
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
