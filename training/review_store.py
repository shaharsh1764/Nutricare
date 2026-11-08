#!/usr/bin/env python3
"""Human review decisions for the Biryani pilot sample.

Hard separation rule
--------------------
Source metadata (Commons page id, SHA1, licence, artist, dimensions) is written
by ``review_sample.py`` and is **read-only** here. This module only ever writes
``data/v3/commons_pilot/review/review_decisions.json``. It refuses to open, let
alone modify, the source manifest.

Guarantees enforced in code
---------------------------
1. ``usable_for_training`` is always ``false`` on every stored decision. There is
   no parameter, option or code path that can set it true. Human relevance
   approval is not training permission.
2. A decision may only reference a page id present in the sample, so typos and
   invented records are rejected rather than silently stored.
3. Labels are validated against a fixed vocabulary. Unknown labels raise.
4. Reviewing cannot mark anything legally cleared; the stored record says
   ``legal_clearance: "not_verified"`` unconditionally.

Usage
-----
    from training.review_store import ReviewStore
    store = ReviewStore("data/v3/commons_pilot/review")
    store.record(pageid=10812474, relevance="relevant", quality="good",
                 notes="clear biryani, decent light")
    store.save()
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

#: Fixed vocabularies. Anything else is a programming error, not a data point.
RELEVANCE_LABELS = ("relevant", "irrelevant", "uncertain")
QUALITY_LABELS = ("good", "acceptable", "poor")

#: Flags are tri-state so "not yet reviewed" is never confused with "no".
FLAG_KEYS = ("possible_duplicate", "watermark_or_branding", "collage_or_multiple_dishes")

DECISIONS_FILENAME = "review_decisions.json"
SAMPLE_FILENAME = "review_sample.json"

#: The sample/manifest files this module must never write to.
_PROTECTED = {SAMPLE_FILENAME, "biryani_manifest.json", "biryani_pilot_summary.json"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def validate_labels(
    relevance: Optional[str] = None,
    quality: Optional[str] = None,
) -> None:
    """Raise ValueError for any label outside the fixed vocabularies."""
    if relevance is not None and relevance not in RELEVANCE_LABELS:
        raise ValueError(
            f"invalid relevance label {relevance!r}; expected one of {RELEVANCE_LABELS}"
        )
    if quality is not None and quality not in QUALITY_LABELS:
        raise ValueError(
            f"invalid quality label {quality!r}; expected one of {QUALITY_LABELS}"
        )


def validate_flags(flags: Dict[str, Any]) -> None:
    for key, value in flags.items():
        if key not in FLAG_KEYS:
            raise ValueError(f"unknown review flag {key!r}; expected one of {FLAG_KEYS}")
        if not isinstance(value, bool):
            raise ValueError(f"flag {key!r} must be a bool, got {type(value).__name__}")


class ReviewStore:
    """Loads a sample and holds human decisions for it, separately."""

    def __init__(self, review_dir: str | Path, *, sample_filename: str = SAMPLE_FILENAME):
        if sample_filename in _PROTECTED - {SAMPLE_FILENAME}:
            raise ValueError("refusing to open a protected source file as a decision store")
        self.review_dir = Path(review_dir)
        self.sample_path = self.review_dir / sample_filename
        self.decisions_path = self.review_dir / DECISIONS_FILENAME

        if not self.sample_path.exists():
            raise FileNotFoundError(
                f"review sample not found: {self.sample_path}. "
                "Run training/review_sample.py first."
            )
        self.sample = json.loads(self.sample_path.read_text(encoding="utf-8"))
        self._by_pageid = {
            int(image["pageid"]): image for image in self.sample.get("images", [])
        }
        self.decisions: Dict[int, Dict[str, Any]] = {}
        if self.decisions_path.exists():
            existing = json.loads(self.decisions_path.read_text(encoding="utf-8"))
            for entry in existing.get("decisions", []):
                self.decisions[int(entry["pageid"])] = entry

    # -- queries -----------------------------------------------------------
    def sample_pageids(self) -> List[int]:
        return sorted(self._by_pageid)

    def image_for(self, pageid: int) -> Dict[str, Any]:
        try:
            return self._by_pageid[int(pageid)]
        except KeyError:
            raise KeyError(
                f"pageid {pageid} is not in the review sample; refusing to invent a record"
            ) from None

    def is_reviewed(self, pageid: int) -> bool:
        return int(pageid) in self.decisions

    # -- mutations ---------------------------------------------------------
    def record(
        self,
        pageid: int,
        *,
        relevance: Optional[str] = None,
        quality: Optional[str] = None,
        review_notes: str = "",
        reviewer: str = "",
        **flags: bool,
    ) -> Dict[str, Any]:
        """Create or update one human decision.

        Merges with an existing decision so a reviewer can set relevance now and
        quality later without losing earlier input.
        """
        image = self.image_for(pageid)  # raises for unknown pageids
        validate_labels(relevance, quality)
        validate_flags(flags)

        existing = self.decisions.get(int(pageid), {})
        merged_flags = dict(existing.get("flags", {k: None for k in FLAG_KEYS}))
        for key, value in flags.items():
            merged_flags[key] = value

        decision = {
            "pageid": int(pageid),
            "title": image.get("title"),
            "sha1": image.get("sha1"),
            # Human judgement only. Kept in its own file, never merged into the
            # Commons metadata.
            "relevance": relevance if relevance is not None else existing.get("relevance"),
            "quality": quality if quality is not None else existing.get("quality"),
            "flags": merged_flags,
            "review_notes": review_notes
            if review_notes
            else existing.get("review_notes", ""),
            "reviewer": reviewer or existing.get("reviewer", ""),
            "reviewed_utc": utc_now(),
            # --- guarantees that cannot be overridden ---
            "usable_for_training": False,
            "usable_reason": "human relevance/quality review does not grant training "
            "permission; licence verification and dedupe are outstanding",
            "legal_clearance": "not_verified",
            "declared_licence_only": True,
        }
        self.decisions[int(pageid)] = decision
        return decision

    def save(self) -> Path:
        """Write decisions to their own file. Never touches the source sample."""
        self.review_dir.mkdir(parents=True, exist_ok=True)
        if self.decisions_path.name in _PROTECTED:
            raise ValueError("refusing to overwrite a protected source file")
        reviewed = [d for d in self.decisions.values() if d.get("relevance") is not None]
        payload = {
            "schema_version": "1.0",
            "updated_utc": utc_now(),
            "separation_note": "Human decisions only. Commons source metadata is "
            "held in review_sample.json and is never modified by this file.",
            "sample_path": str(self.sample_path.name),
            "sample_sha256_recorded_in_source": self.sample.get(
                "source_manifest_sha256"
            ),
            "counts": {
                "in_sample": len(self._by_pageid),
                "reviewed": len(reviewed),
                "unreviewed": len(self._by_pageid) - len(reviewed),
            },
            "training_eligibility": {
                "usable_for_training": False,
                "note": "false for every record, unconditionally",
            },
            "decisions": sorted(self.decisions.values(), key=lambda d: d["pageid"]),
        }
        self.decisions_path.write_text(
            json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return self.decisions_path

    # -- reporting ---------------------------------------------------------
    def summary(self) -> Dict[str, Any]:
        by_relevance: Dict[str, int] = {}
        by_quality: Dict[str, int] = {}
        flag_totals = {key: 0 for key in FLAG_KEYS}
        for decision in self.decisions.values():
            rel = decision.get("relevance")
            if rel:
                by_relevance[rel] = by_relevance.get(rel, 0) + 1
            qual = decision.get("quality")
            if qual:
                by_quality[qual] = by_quality.get(qual, 0) + 1
            for key, value in (decision.get("flags") or {}).items():
                if value is True:
                    flag_totals[key] = flag_totals.get(key, 0) + 1
        return {
            "in_sample": len(self._by_pageid),
            "reviewed": sum(1 for d in self.decisions.values() if d.get("relevance")),
            "by_relevance": by_relevance,
            "by_quality": by_quality,
            "flag_totals": flag_totals,
            "usable_for_training_any": any(
                d.get("usable_for_training") for d in self.decisions.values()
            ),
        }


def load_sample(review_dir: str | Path) -> Dict[str, Any]:
    path = Path(review_dir) / SAMPLE_FILENAME
    return json.loads(path.read_text(encoding="utf-8"))


def iter_rows(store: ReviewStore) -> Iterable[Dict[str, Any]]:
    """Flatten sample + decision into rows for the HTML review page."""
    for pageid in store.sample_pageids():
        image = store.image_for(pageid)
        decision = store.decisions.get(pageid, {})
        yield {
            "image": image,
            "decision": decision,
            "reviewed": bool(decision.get("relevance")),
        }
