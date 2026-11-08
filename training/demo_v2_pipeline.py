#!/usr/bin/env python3
"""Run the V2 pipeline end to end on the measured Commons metadata fixture.

Purpose: prove that collection -> tiering -> review -> preparation -> metrics
works on **real** category metadata (real page ids, real SHA1s, real declared
licences, real dimensions) rather than only on hand-made test fixtures.

What this does NOT prove
------------------------
No image bytes exist in this environment, so there is no model and no accuracy
here. The training-usable count stays zero by design, and that zero is the
honest answer rather than a placeholder. The training path itself is verified
separately by ``train_v2.py --self-test``.

Output goes to the path given by ``--out`` (default: a temp dir) so the
generated report can be committed as evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

TRAINING_DIR = Path(__file__).resolve().parent
PROJECT = TRAINING_DIR.parent
sys.path.insert(0, str(TRAINING_DIR))

from collect_v2 import collect_class, write_class  # noqa: E402
from licence_policy import REVIEW_REQUIRED, TRAINING_APPROVED, rights_summary  # noqa: E402
from prepare_v2_dataset import (  # noqa: E402
    cross_class_duplicates,
    prepare,
    render_report,
    write_outputs,
)

DEFAULT_FIXTURE = PROJECT / "tests/fixtures/commons/v4_measured_sample.json"


class FixtureClient:
    """Replays captured API data; mirrors the CommonsClient surface we use."""

    def __init__(self, classes: Dict[str, Any]):
        self.classes = classes

    def _pages_for(self, category: str) -> List[Dict[str, Any]]:
        for entry in self.classes.values():
            if category in (entry.get("commons_categories") or []):
                return entry["files"]
        return []

    def category_members(self, category: str):
        pages = self._pages_for(category)
        return [{"title": p["title"]} for p in pages], []

    def category_info(self, categories):
        return {c: {"exists": bool(self._pages_for(c))} for c in categories}

    def file_info(self, titles):
        wanted = set(titles)
        out = {}
        for entry in self.classes.values():
            for page in entry["files"]:
                if page["title"] in wanted:
                    out[page["title"]] = {
                        "pageid": page["pageid"],
                        "title": page["title"],
                        "imageinfo": [{
                            "sha1": page["sha1"],
                            "width": page["width"],
                            "height": page["height"],
                            "mime": "image/jpeg",
                            "descriptionurl": "https://commons.wikimedia.org/wiki/"
                            + page["title"].replace(" ", "_"),
                            "extmetadata": page["extmetadata"],
                        }],
                    }
        return out


def synthetic_reviews(docs: List[Dict[str, Any]], all_files: Dict[int, Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """Preference-ordered demo decisions, clearly labelled as not human.

    These exist so the review gate and the six counts can be exercised on real
    metadata. They are written with ``source="synthetic_demonstration"`` so no
    reader can mistake them for a person's judgement, and they are never
    committed to a review_decisions.json path.
    """
    decisions: Dict[int, Dict[str, Any]] = {}
    for doc in docs:
        ordered = sorted(
            doc["files"],
            key=lambda r: (
                r["rights"]["rights_tier"] != TRAINING_APPROVED,
                r["rights"]["rights_tier"] != REVIEW_REQUIRED,
                r.get("pageid") or 0,
            ),
        )
        for rank, record in enumerate(ordered):
            pageid = record.get("pageid")
            if pageid is None:
                continue
            relevant = rank < 4 or (rank % 3 == 0)
            decisions[int(pageid)] = {
                "pageid": int(pageid),
                "relevance": "relevant" if relevant else "uncertain",
                "quality": "good" if rank % 2 == 0 else "acceptable",
                "flags": {},
                "reviewer": "synthetic-demonstration",
                "source": "synthetic_demonstration",
                "note": "NOT a human decision; used only to exercise the review gate.",
            }
    return decisions


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--out", type=Path, default=PROJECT / "data/v4/demo_run")
    args = parser.parse_args(argv)

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    client = FixtureClient(fixture["classes"])

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    classes_dir = out / "classes"

    docs = []
    for entry in fixture["classes"].values():
        tax_entry = {
            "slug": next(k for k, v in fixture["classes"].items() if v is entry),
            "canonical": next(k for k, v in fixture["classes"].items() if v is entry).title(),
            "commons_categories": entry["commons_categories"],
        }
        doc = collect_class(client, tax_entry, depth=0)
        write_class(doc, classes_dir)
        docs.append(doc)
        c = doc["counts"]
        print(f"{doc['class']}: slots={c['1_discovered_file_slots']} "
              f"meta={c['2_metadata_retrieved']} rights={c['3_rights_supported']} "
              f"cc_by_sa_held={c['3b_rights_review_required_cc_by_sa']}")

    decisions = synthetic_reviews(docs, {})
    report = prepare(docs, reviews=decisions)
    written = write_outputs(report, out / "prepared")
    (out / "prepared" / "PREPARATION_REPORT.md").write_text(render_report(report))

    all_tiers = [r["rights"] for d in docs for r in d["files"]]
    evidence = {
        "what_this_is": "Pipeline evidence run on captured Commons metadata.",
        "what_this_is_not": "Not a trained model. No image bytes were downloadable in "
        "this environment, so there is no accuracy figure anywhere in this file.",
        "fixture": str(args.fixture),
        "fixture_provenance": fixture.get("provenance"),
        "review_decisions_source": "synthetic_demonstration (NOT a human reviewer)",
        "collection": [
            {"class": d["class"], **d["counts"],
             "licences": d["licences_by_declared_class"]}
            for d in docs
        ],
        "rights_summary": rights_summary(all_tiers),
        "prepared": {
            "totals": report["totals"],
            "classes": report["classes"],
            "leakage": report["leakage"],
            "cross_class_duplicates": cross_class_duplicates(
                {d["class"]: d["files"] for d in docs}
            ),
        },
        "written": written,
    }
    (out / "evidence.json").write_text(json.dumps(evidence, indent=1) + "\n", encoding="utf-8")

    print("\n" + json.dumps(report["totals"], indent=1))
    print(f"\nwrote {out / 'evidence.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
