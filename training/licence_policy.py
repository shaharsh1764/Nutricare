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

Separate decisions that must never be collapsed
-----------------------------------------------
Five different questions are answered at five different stages. Passing one does
not imply passing the next:

1. **Licence-policy eligibility** (:func:`classify_rights`) — does the declared
   licence permit the intended use? Produces ``rights_tier``.
2. **Provenance classification** (:func:`classify_provenance`) — how much does
   the surrounding credit/permission text actually tell us? Produces
   ``provenance_strength``. This is **audit information, not a confidence
   ladder**: except for ``scrape_risk`` it does not change ``rights_tier``, and
   ``unknown`` is no worse than ``independent_review`` for eligibility.
3. **Human visual approval** (``training/review_store.py``) — has a person
   confirmed the image shows the labelled dish at acceptable quality?
4. **Technical validity** (``training/prepare_v2_dataset.py``) — does the file
   decode, is it large enough, is it a duplicate?
5. **Final training eligibility** — ``training_usable`` is true only when *all*
   of the above pass. It is the only count that may be called a training image.

The rights tiers
----------------
``TRAINING_APPROVED``
    The declared licence permits training use. CC0 needs no author; CC BY
    requires one. This is a *licence-policy* verdict only: it is not legal
    clearance, not human review, and not training eligibility.

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

#: Permitted in principle but held pending the share-alike question.
#:
#: Note: there is deliberately no ``_APPROVED_CLASSES`` set. Coupling CC0/PD with
#: CC BY in one set is what originally applied CC BY's author requirement to CC0
#: and silently dropped anonymous public-domain files. Each licence is now
#: tiered explicitly in :func:`classify_rights`.
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
#: Explicit permission / release language.
#:
#: A bare licence name is deliberately NOT permission evidence: an echo such as
#: ``Permission = "CC BY-SA 2.0"`` restates the licence tag, which says nothing
#: about whether the uploader had the right to grant it. Only language that
#: asserts a *grant* counts.
_PERMISSION_EVIDENCE = re.compile(
    r"(\bpermission (to use|to publish|granted|is granted|was granted|has been granted)\b"
    r"|\bused with permission\b"
    r"|\bwith (the )?permission of\b"
    r"|\b(written|explicit|express) permission\b"
    r"|\breleased (under|to the public domain)\b"
    r"|\blicensed (to|for) (use|reuse)\b)",
    re.IGNORECASE,
)

#: Text that is only a licence label (possibly with a version), with no grant
#: language. Used to recognise and explicitly reject licence echoes.
_LICENCE_LABEL_ONLY = re.compile(
    r"^\s*(cc[\s-]?by([\s-]?sa)?([\s-]?nc)?([\s-]?nd)?"
    r"|cc0|cc[\s-]?zero"
    r"|creative commons( attribution)?( (share[- ]?alike|international))?"
    r"|attribution( \d\.\d)?( international)?"
    r"|public domain|pd[\s-][\w-]+"
    r"|gfdl|fal)"
    r"[\s\d.,/-]*$",
    re.IGNORECASE,
)


def is_licence_label_only(text: str) -> bool:
    """True when ``text`` just restates a licence name.

    ``"CC BY-SA 2.0"`` -> True; ``"Permission granted to use this image"`` ->
    False; ``"CC BY 4.0 photo taken in Kerala"`` -> False (has other content).
    """
    text = _coerce_text(text).strip()
    if not text:
        return False
    return bool(_LICENCE_LABEL_ONLY.match(text))

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

#: Search engines. Naming one as the *source* of an image is inherently a
#: scraping indicator: there is no legitimate way to obtain a licensed original
#: "from Google".
_SEARCH_ENGINE = re.compile(
    r"(\bgoogle\b|\bbing\b|\byandex\b|\bduckduckgo\b|\bask\.com\b|\bbaidu\b"
    r"|google\.[a-z]{2,3}\b|images?\.[a-z.]*bing\.|\/search\?)",
    re.IGNORECASE,
)
#: Social / image-sharing platforms. A mention alone is NOT scraping: a credit
#: line may legitimately name the host the photographer used.
_SOCIAL_PLATFORM = re.compile(
    r"(facebook|instagram|pinterest|reddit|tumblr|tiktok|imgur|weheartit"
    r"|flickr|twitter)",
    re.IGNORECASE,
)
#: Unambiguous scraping vocabulary: a hit is sufficient on its own.
_SCRAPE_WORD = re.compile(
    r"(\bscraped?\b|\bscraping\b|\bhotlink(ed|ing)?\b|\bclip ?art\b"
    r"|\brehosted\b|\bre-hosted\b|\bre-?uploaded\b)",
    re.IGNORECASE,
)
#: Verbs that turn any source mention into evidence of copying.
#: A *source object*: the kind of thing an image is copied out of.
#:
#: Used only to disambiguate the everyday verbs below. It is an inclusion list on
#: purpose: "taken from a website" is copying, "taken from above" is a camera
#: angle, and only the object can tell them apart.
_SOURCE_OBJECT = (
    r"(?:the\s+|a\s+|an\s+)?"
    r"(web|internet|online|web\s?site|site|web\s?page|page|blog|forum"
    r"|google|bing|yandex|duckduckgo|baidu|search|image\s+search"
    r"|facebook|instagram|flickr|imgur|photobucket|pinterest|reddit|tumblr"
    r"|tiktok|twitter|youtube|wikipedia|wikimedia|commons"
    r"|book|magazine|newspaper|article|journal|publication|menu\s+card"
    r"|video|film|movie|tv|television|stream|scan|album|post|tweet|profile"
    r"|account|channel|pdf|document|source|news)\b"
)

#: Verbs that assert an act of copying regardless of what follows.
_UNAMBIGUOUS_COPY = r"(?:copied|ripped|downloaded|hotlinked|re-?uploaded|scraped|sourced)"

#: Everyday photography verbs. "Taken from above", "pulled from the tandoor" and
#: "retrieved from the menu" describe how a picture was *made*, not copied, so
#: these only count as copying when the object is a source to copy out of.
_AMBIGUOUS_COPY = r"(?:taken|grabbed|pulled|lifted|leached|saved|retrieved|obtained)"

#: Non-verb scraping evidence: screenshot capture of a media work, screen grabs,
#: search engines, and re-uploads to anonymous hosts.
#:
#: A screenshot is an image *type*. Capturing a user interface ("Screenshot of a
#: website", "Screenshot of the app", "Screenshot of the menu") is a legitimate
#: way to depict a screen, so the bare noun and UI objects are descriptive and
#: must NOT be treated as evidence of unauthorised copying. Capturing a *media
#: work* (film, broadcast, video, stream) is evidence, and so is an explicit
#: capture verb.
#:
#: Hosting verbs name a destination, which is evidence of re-upload only when the
#: destination is an anonymous image dump. "Uploaded to Commons" is legitimate,
#: and Flickr is deliberately absent: Commons' Flickr review bot imports under
#: exactly the credit line "uploaded to Flickr by <author>", so flagging that
#: phrasing would reject a large, licensed, legitimately-sourced slice of the
#: corpus. Imgur/Photobucket have no such attribution route.
_OTHER_SCRAPE_EVIDENCE = (
    r"|\bscreenshot\b\s*(from|of)\s+(a\s+|the\s+)?"
    r"(film|movie|video|tv|television|youtube|stream|episode|documentary)"
    r"|\bscreenshot(s|ed)?\s+(taken|grabbed|captured)\s+(from|of)"
    r"|\bscreen\s?grab\b"
    r"|\bcaptured\s+from\s+(a\s+)?(video|film|movie|tv|youtube|stream)"
    r"|\bimage\s+search\b|\breverse\s+image\s+search\b"
    r"|\bfound\s+(on|via)\s+the\s+(web|internet)\b"
    r"|\bfrom\s+the\s+(web|internet)\b"
    r"|\b(hosted|uploaded|posted|published)\s+(on|to)\s+"
    r"(imgur|photobucket|tinypic|postimg|imgbb|a\s+blog|the\s+web|the\s+internet"
    r"|a\s+(website|forum|blog))"
)

#: Assembled from the shared pieces so the source-object list has exactly one
#: definition. Duplicating it inline previously let the documented example
#: ("menu card") be present in ``_SOURCE_OBJECT`` but absent from the regex.
_COPY_VERB = re.compile(
    r"("
    # Unambiguous copying: any object will do.
    r"\b" + _UNAMBIGUOUS_COPY + r"\b\s+(from|off|via)"
    # Ambiguous verbs: only when a source object follows.
    + r"|\b" + _AMBIGUOUS_COPY + r"\b\s+(from|off|via)\s+" + _SOURCE_OBJECT
    + _OTHER_SCRAPE_EVIDENCE
    + r")",
    re.IGNORECASE,
)
#: Explicitly unknown provenance.
#: Explicitly unknown provenance.
#:
#: Phrasing is anchored rather than loose: "no source of information about the
#: dish" and "unknown source of the spice" are legitimate food descriptions, not
#: provenance statements. Bare ``unknown source`` must therefore be the whole
#: field, and the other forms are unambiguous.
_UNKNOWN_SOURCE = re.compile(
    r"(^\s*unknown source\s*$|\bsource unknown\b|\bsource\s*:\s*unknown\b"
    r"|\bno source (given|provided|known|information)\b"
    r"|\bsourced from the web\b|\bprovenance unknown\b"
    r"|\bunknown provenance\b|\borigin unknown\b)",
    re.IGNORECASE,
)


def scrape_signals(*texts: str) -> List[str]:
    """Return the *scraping* indicators found in ``texts``.

    Rules are layered so a **mention** is never confused with **evidence of
    copying**:

    * unambiguous scraping vocabulary matches alone (``scraped``, ``clip art``,
      ``hotlinked``, ``re-uploaded``);
    * a copy verb matches alone, because the verb already asserts the act
      (``copied from``, ``downloaded from``, ``screenshot of``);
    * a **search engine** named any way matches: there is no legitimate route to
      a licensed original "from Google" or "from Bing";
    * a **social platform** named alone does **not** match. "Flickr" or
      "Instagram" in a credit line is a host the photographer used, not proof of
      copying. It only becomes scraping when a copy verb accompanies it, which
      the copy-verb rule already covers.

    An empty list means "no scraping evidence found", which the caller must treat
    as *unknown*, never as *safe*.

    Platform-only mentions are surfaced separately via :func:`platform_mentions`
    so an auditor can see them without them affecting the tier.
    """
    combined = " ".join(_coerce_text(t) for t in texts if t)
    if not combined:
        return []
    found: List[str] = []
    if _SCRAPE_WORD.search(combined):
        found.append("scrape_vocabulary")
    if _COPY_VERB.search(combined):
        found.append("copy_verb")
    if _UNKNOWN_SOURCE.search(combined):
        found.append("unknown_source")
    if _SEARCH_ENGINE.search(combined):
        found.append("search_engine_source")
    return found


def platform_mentions(*texts: str) -> List[str]:
    """Names of social/image platforms mentioned, for auditing only.

    Deliberately advisory: this returns a list so a reader can see that a batch
    of credits came from one platform, but the value never affects the rights
    tier. "Most of our photos say Flickr" is a provenance observation, not a
    licence judgement.
    """
    combined = " ".join(_coerce_text(t) for t in texts if t)
    if not combined:
        return []
    return sorted({m.group(0).lower() for m in _SOCIAL_PLATFORM.finditer(combined)})


#: Retained for callers that only want a boolean; ``scrape_signals`` is the
#: authoritative implementation.
_SCRAPE_RISK = _SCRAPE_WORD


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

#: Words that contradict, restrict or qualify a CC0 dedication.
#:
#: A CC0 label is only an unconditional dedication when nothing else in the
#: string attaches conditions to it. Community relabelling such as
#: ``"CC0 but no commercial use"`` or ``"CC0 with restrictions"`` claims CC0
#: while imposing extra terms the licence does not contain, which is a
#: self-contradiction rather than a dedication we can rely on. Such a string must
#: never be auto-approved, and it must not be deferred to review either (that
#: would let a later reviewer wave it through): it is excluded.
_RESTRICTIVE_MODIFIER = re.compile(
    r"(\bnc\b|non[-\s]?commercial"
    r"|\bnd\b|no[-\s]?deriv|noderivs|no derivatives"
    r"|\bsa\b|share[-\s]?alike|sharealike"
    r"|restrict|additional (condition|term|restriction)|extra (condition|term)"
    r"|but not|except|no (commercial|derivative|modif|redistribut)"
    r"|not for (commercial|profit|resale)|non[-\s]?free"
    r"|permission (required|needed)|used with permission"
    r"|all rights reserved)",
    re.IGNORECASE,
)

#: Trailing content that disqualifies a bare CC0 dedication.
#:
#: A genuine dedication is the label alone, optionally with a version and a
#: jurisdiction qualifier (``"CC0 1.0 Universal"``, ``"CC0 1.0 Universal
#: (CC0 1.0) Public Domain Dedication"``). Anything else trailing the label is
#: an added condition we have not assessed, so it disqualifies the dedication
#: rather than being silently ignored as prefix matching would do.
_CC0_TRAILING_OK = re.compile(
    r"^[\s\d.,()]*((universal|dedication|public\s+domain\s+dedication"
    r"|legal\s+code|cc0)[\s\d.,()]*)*$",
    re.IGNORECASE,
)


def is_bare_cc0(text: str) -> bool:
    """True only for an *unconditional* CC0 dedication.

    ``"CC0 1.0 Universal"`` -> True. ``"CC0 but no commercial use"`` -> False;
    ``"CC0 with restrictions"`` -> False. Adding a restriction while claiming
    CC0 is a contradiction, and the restrictive reading wins.
    """
    text = _coerce_text(text).strip()
    if not text:
        return False
    match = _CC0_SHORT.match(text)
    if not match:
        return False
    if has_restrictive_modifier(text):
        return False
    return bool(_CC0_TRAILING_OK.match(text[match.end():]))


def has_restrictive_modifier(text: str) -> bool:
    """True when ``text`` attaches terms that contradict a permissive licence.

    ``"CC0 with restrictions"`` -> True; ``"CC0 1.0 Universal"`` -> False.
    """
    text = _coerce_text(text).strip()
    if not text:
        return False
    return bool(_RESTRICTIVE_MODIFIER.search(text))


#: Placeholder author values that name no actual person or organisation.
#:
#: CC BY and CC BY-SA require attribution *to a named party*. ``"N/A"`` names
#: nobody, so such a file cannot satisfy its own licence and must not be
#: approved on the strength of a non-empty string. Compared case-insensitively
#: after stripping punctuation and invisible characters.
_PLACEHOLDER_AUTHORS = frozenset(
    {
        "unknown",
        "unknown author",
        "unknown artist",
        "unknown photographer",
        "anonymous",
        "anon",
        "na",
        "none",
        "nil",
        "-",
        "\u2014",
        "\u2013",
        "null",
        "not applicable",
        "not known",
        "not stated",
        "not specified",
        "no author",
        "no name",
        "unnamed",
        "tbd",
        "todo",
    }
)

#: Zero-width and other invisible characters. ``"\u200b"`` is visually empty but
#: truthy as a string, so it would otherwise satisfy the attribution test.
_INVISIBLE = re.compile("[\u200b-\u200f\u2060\ufeff\u00ad]")

#: ``N/A``-shaped placeholders. Handled separately from the word list so that a
#: legitimate initials-only attribution such as ``"N A"`` is not rejected, while
#: the slash form (which is unambiguously a placeholder) still is.
#: Any Unicode letter or digit. Used to require that an "author" actually
#: contains something attributable rather than punctuation or symbols alone.
_ALNUM = re.compile(r"[^\W_]", re.UNICODE)

_PLACEHOLDER_SLASH = re.compile(
    r"^\s*(n\s*/\s*a|n\.\s*a\.?|none\s*/\s*none|not\s*/\s*applicable)\s*$",
    re.IGNORECASE,
)


def is_placeholder_author(text: str) -> bool:
    """True when ``text`` is empty, invisible, or a placeholder identity.

    An identity must contain at least one letter or digit. An enumeration of
    punctuation cannot be complete (``--``, ``?``, ``...``, ``==``, ``[]``, ``""``
    all name nobody), so the rule is stated positively: no alphanumeric character
    means no identity. This generalises the earlier ``-``/``—`` entries instead of
    chasing each new spelling.

    Legitimate names are never matched: ``"Anonymous"`` is a placeholder but
    ``"Anonymouse"`` (a real Commons username) is not, because comparison is
    against the whole normalised string rather than a substring. Punctuation
    *around* a name is fine — ``"-John-"`` and ``"O'Brien, Sean"`` both keep their
    letters.
    """
    cleaned = _INVISIBLE.sub("", _coerce_text(text)).strip()
    if not cleaned:
        return True
    # No letter and no digit anywhere: there is nothing to attribute to.
    if not _ALNUM.search(cleaned):
        return True
    if _PLACEHOLDER_SLASH.match(cleaned):
        return True
    normalised = re.sub(r"\s+", " ", cleaned).strip().lower()
    return normalised in _PLACEHOLDER_AUTHORS

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


def _coerce_text(value: Any) -> str:
    """Coerce an arbitrary extmetadata value to safe text.

    Commons extmetadata values are normally strings, but a malformed or
    hand-edited record can carry ``None``, a list, a dict, or a number. Calling
    ``.strip()`` on those raises ``AttributeError``, which upstream would abort
    collection of an entire class. Returning ``""`` instead makes the record fail
    closed: it is treated as "no text supplied" rather than crashing or being
    trusted.

    Deliberately does **not** stringify arbitrary objects into something that
    could be mistaken for attribution.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, dict):
        # extmetadata sometimes nests {"value": "..."}; accept only that shape.
        inner = value.get("value")
        return inner if isinstance(inner, str) else ""
    if isinstance(value, (list, tuple)):
        # Deliberately NOT joined. A multi-valued field where a single author is
        # expected is a malformed record, and silently concatenating it would
        # turn arbitrary objects into trusted attribution. Reject by returning
        # empty text so the record fails closed.
        return ""
    return ""


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
    permission_text = _coerce_text(permission_text).strip()
    credit_text = _coerce_text(credit_text).strip()
    signals: List[str] = []
    reasons: List[str] = []

    if not permission_text and not credit_text:
        reasons.append(
            "no permission/credit text captured; provenance strength unknown"
        )
        return {"strength": "unknown", "signals": signals, "reasons": reasons}

    combined = f"{permission_text} {credit_text}".strip()

    # 1. Scraping risk dominates: it disqualifies regardless of other text.
    scrape = scrape_signals(permission_text, credit_text)
    if scrape:
        reasons.append(
            "provenance text suggests a scraped, copied or re-hosted source "
            f"({', '.join(scrape)}); downloadable is not the same as licensed"
        )
        return {"strength": "scrape_risk", "signals": scrape, "reasons": reasons}

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
    #
    # A licence-name echo is rejected first. "Permission = CC BY-SA 2.0" merely
    # restates the tag already recorded elsewhere, so it is not independent
    # evidence and must not be upgraded to permission_asserted.
    if permission_text and is_licence_label_only(permission_text):
        signals.append("permission_licence_echo")
        reasons.append(
            "Permission field only restates the licence name; a licence echo is "
            "not independent evidence of permission"
        )
    elif _PERMISSION_EVIDENCE.search(permission_text):
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


#: How a Commons ``Restrictions`` field is treated.
#:
#: The field is overloaded. It carries genuine licence restrictions ("no
#: commercial use"), non-copyright caveats that do not block a research dataset
#: ("personality rights", "trademarked"), and free descriptive prose. Treating
#: every value as a licence term would reject legitimate material; ignoring it,
#: as the pipeline did before, means a restricted file is approved on the
#: strength of its ``short_name`` alone. The two cases must therefore be named
#: separately rather than collapsed into one bucket.

#: Restrictions that contradict or narrow the declared licence.
_RESTRICTION_LICENCE = re.compile(
    r"(non[-\s]?commercial|\bnc\b|no commercial|not for commercial"
    r"|no derivative|no derivatives|\bnd\b|no modif|no redistribution"
    r"|all rights reserved|used with permission|permission required"
    r"|\bfair use\b|copyrighted|non[-\s]?free|credit required"
    r"|attribution required|no\s+reuse|not for reuse)",
    re.IGNORECASE,
)

#: Restrictions that are real caveats but not copyright-licence terms.
#: They do not block use here, but they must stay visible to a human reviewer.
#:
#: Every alternative here must name an actual non-copyright concern. Punctuation
#: and separators are deliberately absent: a comma is not evidence that a
#: restriction is harmless, and treating it as such let unassessed text slip
#: through to ``TRAINING_APPROVED`` (finding C-1).
_RESTRICTION_OTHER = re.compile(
    r"(trademark|personality rights|\bprivacy\b|moral rights"
    r"|insulting|defam|\blibel)",
    re.IGNORECASE,
)


#: Separators that may delimit independent restriction clauses.
#:
#: Commons uploaders frequently list several concerns in one field
#: ("Trademarked, see below"). Splitting first lets each clause be judged on its
#: own merits; only afterwards is the most restrictive outcome applied. A
#: separator is never itself evidence that a clause is harmless.
_RESTRICTION_SEPARATOR = re.compile(
    r"\s*[;,|]\s*"              # comma, semicolon, pipe
    r"|\s*/\s*"                  # slash
    r"|\s+&\s+"                   # ampersand
    r"|\s+(?:-|\u2013|\u2014)\s+"      # spaced dash
    r"|\s+(?:and|plus|including)\s+(?=\w)",
    re.IGNORECASE,
)

#: Severity order for restriction kinds: the most restrictive wins.
_RESTRICTION_SEVERITY = {"none": 0, "other": 1, "text": 2, "licence": 3}


#: Vocabulary that may legitimately surround a non-copyright concern without
#: introducing a new condition. Everything else in the clause is a content word,
#: and a content word that names no recognised concern means the clause carries
#: something we have not assessed.
#:
#: This replaces an earlier character-ratio heuristic, which mis-scored clauses
#: such as "defamatory or otherwise unlawful use prohibited" (the concern was
#: matched, but most of the clause was connective prose) and so could not tell
#: harmless padding from a hidden second condition.
#: Negation and prohibition words are deliberately ABSENT from the filler set.
#:
#: They were previously listed here, which made "Trademarked no use" and
#: "Trademarked use prohibited" classify as a harmless caveat: the words that
#: express the restriction were the exact words being filtered out. A word that
#: flips the polarity of a clause is never padding.
_RESTRICTION_FILLER = frozenset(
    """
    a an the this that these those it its of in on at to for from by with
    and or any all some other otherwise else plus including also
    is are was were be been being may might must should can could will would
    apply applies applied use used using usage permitted
    allowed requires require required restriction restrictions restricted
    image images file files work works content media material see below above
    note notes respect respects regarding concerning per under terms condition
    conditions on upon same such more most less least very please ask asks
    noted note notes as above below stated mentioned given specified here
    """.split()
)

#: Explicit prohibition or negation language.
#:
#: Removing these words from the filler set is what actually fixes the bypass:
#: they now survive as residue, which forces ``text``. This pattern is a second,
#: intentional layer so that a future edit to ``_RESTRICTION_FILLER`` cannot
#: silently reopen the hole by re-absorbing a negation word.
#:
#: It is currently redundant by construction — every word it matches is also
#: residue, so no test can distinguish its presence behaviourally. That is
#: recorded here rather than dressed up as covered: it is defence in depth, and
#: a reviewer seeing zero mutation coverage for it should read this note.
_RESTRICTION_NEGATION = re.compile(
    r"(\bnot\b|\bno\b|\bnor\b|\bnever\b|\bcannot\b|\bcan\s?not\b"
    r"|\bwithout\b|\bprohibit\w*|\bforbid\w*|\bbann?ed\b|\bunlawful\b"
    r"|\billegal\b|\bunauthori[sz]ed\b|\bstrictly\b|\bonly\b"
    r"|\bmust\s+not\b|\bdo\s+not\b|\bdon't\b|\bnot\s+for\b)",
    re.IGNORECASE,
)


#: Punctuation and whitespace that may be ignored when looking for content.
#:
#: Deliberately narrow: only characters that carry no meaning on their own are
#: dropped. Symbols such as ``©``, ``⛔`` and ``✖`` are content, not punctuation,
#: because on a licence field they signal a reserved right or a prohibition.
_RESTRICTION_PUNCTUATION = frozenset(" \t\r\n.,;:!?()[]{}\"'`<>/\\|-–—_+=*&^%$#@~")

#: Words the recognised-concern matcher is allowed to explain away. Removed
#: before residue extraction so that "trademarked" does not count as content.
_CONCERN_VOCABULARY = re.compile(
    r"\b(trademark\w*|personality|privacy|moral|insult\w*|defam\w*"
    r"|libel\w*|slander\w*|rights?)\b",
    re.IGNORECASE,
)


def _tokenize_restriction(text: str) -> List[str]:
    """Split restriction text into tokens without discarding any language.

    A token is a maximal run of characters that are neither whitespace nor
    punctuation. This is script-agnostic on purpose: an earlier ASCII-only
    ``[a-z]+`` tokeniser made every non-Latin word invisible, so
    ``"Trademarked 禁止商用"`` (no commercial use) was approved while its English
    equivalent was excluded. Digits are tokens too — "2030" in a restriction is
    a date, not padding.
    """
    tokens: List[str] = []
    current: List[str] = []
    for char in text:
        if char.isspace() or char in _RESTRICTION_PUNCTUATION:
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(char)
    if current:
        tokens.append("".join(current))
    return tokens


def _clause_residue(clause: str) -> List[str]:
    """Content tokens in ``clause`` not explained by a recognised concern.

    Anything the parser cannot account for is residue, and residue forces the
    clause to ``text`` (held for review). Silence is never treated as consent:
    a token in an unfamiliar script, a number, or a symbol all count.
    """
    text = _coerce_text(clause)
    # Remove the concern vocabulary so "trademarked" is not itself content.
    text = _CONCERN_VOCABULARY.sub(" ", text)
    for match in _RESTRICTION_OTHER.finditer(text):
        text = text.replace(match.group(0), " ")

    residue: List[str] = []
    for token in _tokenize_restriction(text):
        lowered = token.lower()
        if lowered in _RESTRICTION_FILLER:
            continue
        residue.append(token)
    return residue


def _classify_restriction_clause(clause: str) -> str:
    """Classify a single restriction clause as ``licence``, ``other`` or ``text``.

    ``other`` is the only non-empty kind that leaves a file eligible, so it is
    reserved for clauses the parser fully understands: a named non-copyright
    concern, no prohibition, and no unaccounted-for content.
    """
    if _RESTRICTION_LICENCE.search(clause):
        return "licence"
    if _RESTRICTION_OTHER.search(clause):
        # A named concern never makes a prohibition harmless, and never excuses
        # content the parser cannot read.
        if _RESTRICTION_NEGATION.search(clause):
            return "text"
        return "other" if not _clause_residue(clause) else "text"
    return "text"


def classify_restrictions(text: str) -> Dict[str, Any]:
    """Sort a Commons ``Restrictions`` value into one of four kinds.

    ``kind`` is one of:

    * ``"none"`` — the field is empty;
    * ``"licence"`` — a copyright restriction that contradicts or narrows the
      licence; the file must not be auto-approved;
    * ``"other"`` — a non-copyright caveat (trademark, personality rights). Not a
      licence term, but carried into the reasons so a human sees it;
    * ``"text"`` — free descriptive text we cannot classify. Held for review
      rather than assumed benign, because the pipeline cannot tell an
      unassessed condition from a remark.

    The field may list several concerns at once, so it is split into clauses and
    each clause is classified independently. The **most restrictive** clause
    determines the result: a field containing both a trademark caveat and an
    unassessed clause is ``text`` (held), not ``other`` (approved). Punctuation
    alone never makes a clause harmless.

    Returns the ``kind`` plus the original ``text`` unchanged, so the raw Commons
    value is never lost, along with the individual clause verdicts for audit.
    """
    text = _coerce_text(text).strip()
    if not text:
        return {"kind": "none", "text": "", "reason": "", "clauses": []}

    clauses = [c.strip() for c in _RESTRICTION_SEPARATOR.split(text) if c and c.strip()]
    if not clauses:
        clauses = [text]

    verdicts = [(_classify_restriction_clause(c), c) for c in clauses]
    worst_kind, worst_clause = max(
        verdicts, key=lambda pair: _RESTRICTION_SEVERITY[pair[0]]
    )

    if worst_kind == "licence":
        reason = (
            f"Commons Restrictions field carries a licence restriction "
            f"{worst_clause!r} (in {text!r})"
        )
    elif worst_kind == "other":
        reason = (
            f"Commons Restrictions field carries a non-copyright caveat "
            f"{text!r}; retained for human review, not a licence term"
        )
    else:
        reason = (
            f"Commons Restrictions field is unclassified text {worst_clause!r} "
            f"(in {text!r}); deferred to human review"
        )

    return {
        "kind": worst_kind,
        "text": text,
        "reason": reason,
        "clauses": [{"text": c, "kind": k} for k, c in verdicts],
    }


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
        artist = _coerce_text(licence.get("artist_raw"))
    artist = _coerce_text(artist).strip()
    attribution_required = licence.get("attribution_required")
    short_name = _coerce_text(licence.get("short_name")).strip()
    restriction = classify_restrictions(licence.get("restrictions"))
    # ``classify_licence`` can bucket a file as CC0_PD from UsageTerms/License
    # while LicenseShortName is empty, so fall back to that text rather than
    # discarding a real designation. If neither is present, there is genuinely
    # no basis to decide and the file fails closed below.
    designation_text = short_name or _coerce_text(licence.get("usage_terms")).strip()
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
    # A non-empty string is not necessarily an identity: "N/A" and a
    # zero-width space both name nobody, so neither can satisfy an
    # attribution obligation.
    artist_is_placeholder = is_placeholder_author(artist)
    attribution_sufficient = bool(artist) and not artist_is_placeholder

    if restriction["kind"] == "licence":
        # A recorded restriction that narrows or contradicts the licence beats
        # any permissive label: the restrictive reading wins.
        tier = EXCLUDED
        reasons.append(restriction["reason"])
    elif restriction["kind"] == "text":
        # Unclassified text is not assumed benign, and not assumed restrictive
        # either: hold it for a human rather than guessing in either direction.
        tier = REVIEW_REQUIRED
        reasons.append(restriction["reason"])
    elif provenance_strength == "scrape_risk":
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
        elif has_restrictive_modifier(designation_text):
            # A CC0 label carrying added restrictions ("CC0 but no commercial
            # use", "CC0 with restrictions") is self-contradictory. The
            # restrictive reading wins, and the file is excluded rather than
            # deferred: deferring would let a later reviewer approve it on the
            # strength of the CC0 prefix alone.
            tier = EXCLUDED
            reasons.append(
                f"CC0_PD bucket but short_name {designation_text!r} attaches "
                "restrictive conditions to a CC0 label; a contradiction cannot be "
                "resolved in favour of the permissive reading"
            )
        elif is_bare_cc0(designation_text):
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

    if restriction["kind"] == "other" and restriction["reason"]:
        # A caveat that is not a licence term. It must not change the tier, but
        # it must reach the reviewer rather than disappear.
        reasons.append(restriction["reason"])

    return {
        "rights_tier": tier,
        "declared_class": declared,
        "verification": "declared_only",
        "provenance_strength": provenance_strength,
        "provenance_signals": provenance["signals"],
        "public_domain_designation": pd_designation,
        "restrictions": restriction["text"],
        "restrictions_kind": restriction["kind"],
        "attribution_sufficient": attribution_sufficient,
        "author_is_placeholder": artist_is_placeholder,
        "short_name": short_name,
        "designation_text": designation_text,
        # NAMING NOTE: despite the name, this means "the declared licence policy
        # permits training use". It does NOT mean the image is approved for
        # training: that requires human review plus technical checks, and is
        # computed as ``training_usable`` in prepare_v2_dataset.py. Renaming it
        # would touch downstream manifests, so the meaning is pinned here and in
        # docs/V2_LICENCE_PROVENANCE_INVESTIGATION.md instead.
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
