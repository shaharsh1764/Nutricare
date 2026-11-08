#!/usr/bin/env python3
"""Build human-review batches across several V2 classes at once.

The Biryani pilot's first review sample is a closed artefact: it and its
decisions must never be rewritten. This tool therefore only ever writes into a
**new** directory per class, and refuses any target that already contains a
sample or decisions file unless ``--force`` is given for an untouched batch.

Selection differs from the pilot on purpose
-------------------------------------------
The pilot had 93 files from one class and sampled round-robin across licence
classes. For V2 we have far more classes than reviewers, so each batch is built
to be *worth a reviewer's time*:

1. Prefer rights-supported files (CC0 / PD / CC BY). Reviewing a file we can
   never train on is wasted effort.
2. Include a slice of CC BY-SA files, because that pool is where most of the
   volume is and a legal decision may open it later.
3. Aim for diversity across Commons authors, so a batch is not ten photos by
   one uploader.
4. Cap the batch so a reviewer can actually finish it.

Every entry keeps ``usable_for_training: false``. Reviewing never approves
anything by itself: approval is a separate recorded decision.

Usage
-----
    python training/build_v2_review_batches.py --classes-dir data/v4/classes \
        --out data/v4/review --per-class 10 --classes roti naan biryani

    python training/build_v2_review_batches.py --self-test
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

TRAINING_DIR = Path(__file__).resolve().parent
PROJECT = TRAINING_DIR.parent
sys.path.insert(0, str(TRAINING_DIR))

from licence_policy import REVIEW_REQUIRED, TRAINING_APPROVED  # noqa: E402

#: Any directory whose contents must never be regenerated.
PROTECTED_DIRS = (
    PROJECT / "data/v3/commons_pilot/review",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _author(record: Dict[str, Any]) -> str:
    return ((record.get("attribution") or {}).get("artist_raw") or "").strip()


def select_batch(
    files: Sequence[Dict[str, Any]],
    *,
    limit: int = 10,
    cc_by_share: float = 0.3,
) -> List[Dict[str, Any]]:
    """Pick a licence-weighted, author-diverse, deterministic batch."""
    if limit <= 0:
        raise ValueError("limit must be positive")

    supported = sorted(
        [f for f in files if (f.get("rights") or {}).get("rights_tier") == TRAINING_APPROVED
         and not f.get("technical_flags")],
        key=lambda f: f.get("pageid") or 0,
    )
    share_alike = sorted(
        [f for f in files if (f.get("rights") or {}).get("rights_tier") == REVIEW_REQUIRED
         and not f.get("technical_flags")],
        key=lambda f: f.get("pageid") or 0,
    )

    quota_sa = int(round(limit * cc_by_share))
    quota_supported = limit - quota_sa

    def pick(pool: List[Dict[str, Any]], count: int) -> List[Dict[str, Any]]:
        """Round-robin by author so one uploader cannot dominate a batch."""
        by_author: Dict[str, List[Dict[str, Any]]] = {}
        for record in pool:
            by_author.setdefault(_author(record) or "<unknown>", []).append(record)
        order = sorted(by_author, key=lambda a: (len(by_author[a]), a))
        chosen: List[Dict[str, Any]] = []
        while len(chosen) < count and any(by_author[a] for a in order):
            for author in order:
                if by_author[author] and len(chosen) < count:
                    chosen.append(by_author[author].pop(0))
        return chosen

    batch = pick(supported, quota_supported)
    if len(batch) < limit:
        # Not enough permissive files: top up from the share-alike pool rather
        # than silently returning a short batch.
        batch += pick(share_alike, limit - len(batch))
    return sorted(batch, key=lambda f: f.get("pageid") or 0)


def build_batch_doc(
    class_doc: Dict[str, Any],
    entries: List[Dict[str, Any]],
    *,
    limit: int,
) -> Dict[str, Any]:
    licences = Counter(
        (e.get("licence") or {}).get("declared_class") or "UNKNOWN" for e in entries
    )
    tiers = Counter((e.get("rights") or {}).get("rights_tier") for e in entries)
    return {
        "schema_version": "4.0",
        "generated_utc": utc_now(),
        "class": class_doc["class"],
        "canonical": class_doc.get("canonical", class_doc["class"]),
        "batch_limit": limit,
        "batch_size": len(entries),
        "selection_method": "rights-supported first (author round-robin), then a "
        "CC BY-SA slice; ordered by Commons page id",
        "source_collection_utc": class_doc.get("collected_utc"),
        "image_bytes_downloaded": False,
        "licence_mix": dict(licences),
        "rights_tier_mix": {str(k): v for k, v in tiers.items()},
        "licence_reminder": "A declared Commons licence is not independently verified "
        "permission. Nothing here is legally cleared, and usable_for_training is "
        "false for every record until a human records a decision.",
        "images": entries,
    }


def prepare_entries(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Copy only the fields a reviewer needs, defaulting training to false."""
    out = []
    for record in records:
        out.append({
            "pageid": record.get("pageid"),
            "title": record.get("title"),
            "sha1": record.get("sha1"),
            "width": record.get("width"),
            "height": record.get("height"),
            "mime": record.get("mime"),
            "description_url": record.get("description_url"),
            "licence": record.get("licence"),
            "attribution": record.get("attribution"),
            "rights": record.get("rights"),
            "categories": record.get("categories"),
            "metadata_gaps": record.get("metadata_gaps", []),
            "technical_flags": record.get("technical_flags", []),
            "thumbnail": {
                "url": "",
                "retrieval_status": "url_unresolved",
                "retrieval_note": "Resolve with a fresh imageinfo iiurlwidth call; "
                "no bytes were downloaded by the collector.",
            },
            # Reviewing is not approving.
            "usable_for_training": False,
        })
    return out


def _is_protected(out_dir: Path) -> bool:
    target = out_dir.resolve()
    for protected in PROTECTED_DIRS:
        try:
            target.relative_to(protected.resolve())
            return True
        except ValueError:
            continue
        if target == protected.resolve():
            return True
    return False


def write_batch(out_dir: Path, doc: Dict[str, Any], *, force: bool = False) -> Path:
    out_dir = Path(out_dir)
    if _is_protected(out_dir):
        raise SystemExit(
            f"refusing to write into protected review directory: {out_dir}. "
            "The first Biryani review sample and its decisions must not be overwritten."
        )
    path = out_dir / "review_sample.json"
    if path.exists() and not force:
        raise SystemExit(
            f"{path} already exists. Reviewing is not repeatable by regeneration; "
            "pass --force only if this batch was never distributed."
        )
    if (out_dir / "review_decisions.json").exists():
        raise SystemExit(
            f"{out_dir / 'review_decisions.json'} exists: this batch has real human "
            "decisions and must not be regenerated."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def plan_classes(docs: Sequence[Dict[str, Any]], limit: int, minimum: int) -> Dict[str, Any]:
    """Rank classes by how much reviewable material they actually have."""
    ranked = []
    for doc in docs:
        records = doc.get("files", [])
        supported = sum(
            1 for r in records
            if (r.get("rights") or {}).get("rights_tier") == TRAINING_APPROVED
            and not r.get("technical_flags")
        )
        sa = sum(
            1 for r in records
            if (r.get("rights") or {}).get("rights_tier") == REVIEW_REQUIRED
            and not r.get("technical_flags")
        )
        ranked.append({
            "class": doc["class"],
            "rights_supported": supported,
            "review_required_cc_by_sa": sa,
            "reviewable_total": supported + sa,
            "worth_a_batch": (supported + sa) >= minimum,
        })
    ranked.sort(key=lambda r: (-r["reviewable_total"], r["class"]))
    return {
        "classes": ranked,
        "classes_worth_a_batch": [r["class"] for r in ranked if r["worth_a_batch"]],
        "note": "reviewable_total counts candidate files, not approved images",
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def self_test() -> int:
    import tempfile

    failures: List[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    def rec(pageid, tier, author, flags=None):
        return {
            "pageid": pageid,
            "title": f"File:T{pageid}.jpg",
            "sha1": f"s{pageid}",
            "width": 1000,
            "height": 800,
            "mime": "image/jpeg",
            "description_url": f"https://commons.wikimedia.org/wiki/File:T{pageid}.jpg",
            "licence": {"declared_class": "CC0_PD" if tier == TRAINING_APPROVED else "CC_BY_SA"},
            "attribution": {"artist_raw": author},
            "rights": {"rights_tier": tier},
            "technical_flags": flags or [],
            "metadata_gaps": [],
            "categories": ["Category:X"],
        }

    files = (
        [rec(i, TRAINING_APPROVED, "AuthorA") for i in range(1, 7)]
        + [rec(i, TRAINING_APPROVED, "AuthorB") for i in range(7, 13)]
        + [rec(i, REVIEW_REQUIRED, "AuthorC") for i in range(13, 21)]
        + [rec(99, TRAINING_APPROVED, "AuthorZ", flags=["below_min_edge"])]
    )

    batch = select_batch(files, limit=8, cc_by_share=0.25)
    check(len(batch) == 8, f"expected a batch of 8, got {len(batch)}")
    check(len({b["pageid"] for b in batch}) == len(batch), "batch must not repeat a file")
    check(all(99 != b["pageid"] for b in batch),
          "a technically unusable file must never enter a review batch")
    tiers = Counter(b["rights"]["rights_tier"] for b in batch)
    check(tiers[TRAINING_APPROVED] >= 5,
          "the batch should be weighted toward rights-supported files")
    check(tiers[REVIEW_REQUIRED] >= 1, "the batch should include a CC BY-SA slice")
    authors = Counter(_author(b) for b in batch)
    check(max(authors.values()) <= 4,
          f"author round-robin failed: {dict(authors)}")

    # Determinism.
    check([b["pageid"] for b in batch] == [b["pageid"] for b in select_batch(files, limit=8)],
          "batch selection must be deterministic")

    # Top-up path: not enough permissive files.
    scarce = [rec(1, TRAINING_APPROVED, "A")] + [rec(i, REVIEW_REQUIRED, "B") for i in range(2, 12)]
    topped = select_batch(scarce, limit=6, cc_by_share=0.2)
    check(len(topped) == 6, "a short permissive pool must be topped up, not returned short")

    doc = {"class": "demo", "canonical": "Demo"}
    entries = prepare_entries(batch)
    batch_doc = build_batch_doc(doc, entries, limit=8)
    check(all(e["usable_for_training"] is False for e in entries),
          "no review entry may be usable_for_training")
    check(batch_doc["image_bytes_downloaded"] is False, "no bytes may be downloaded")
    check("licence_reminder" in batch_doc, "the licence reminder must be present")

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "roti"
        path = write_batch(target, batch_doc)
        check(path.exists(), "batch file must be written")
        check(write_batch.__name__ == "write_batch", "sanity")
        try:
            write_batch(target, batch_doc)
            check(False, "re-writing an existing batch must be refused")
        except SystemExit:
            pass
        # With decisions present, even --force must refuse.
        (target / "review_decisions.json").write_text('{"decisions": []}', encoding="utf-8")
        try:
            write_batch(target, batch_doc, force=True)
            check(False, "a batch with decisions must never be regenerated")
        except SystemExit:
            pass

    check(_is_protected(PROJECT / "data/v3/commons_pilot/review") is True,
          "the original Biryani review dir must be protected")
    check(_is_protected(PROJECT / "data/v3/commons_pilot/review/nested") is True,
          "subdirectories of the protected dir must be protected")
    check(_is_protected(PROJECT / "data/v4/review/roti") is False,
          "a new V2 review dir must not be protected")

    plan = plan_classes(
        [
            {"class": "rich", "files": [rec(i, TRAINING_APPROVED, "A") for i in range(1, 6)]},
            {"class": "poor", "files": [rec(1, REVIEW_REQUIRED, "B")]},
        ],
        limit=10, minimum=5,
    )
    check(plan["classes_worth_a_batch"] == ["rich"],
          f"only well-supplied classes should get a batch: {plan['classes_worth_a_batch']}")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        print(f"self-test FAILED ({len(failures)} checks)", file=sys.stderr)
        return 1
    print("self-test passed: batch selection, protections and defaults OK")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--classes-dir", type=Path, default=PROJECT / "data/v4/classes")
    parser.add_argument("--out", type=Path, default=PROJECT / "data/v4/review")
    parser.add_argument("--classes", nargs="*", default=None)
    parser.add_argument("--per-class", type=int, default=10)
    parser.add_argument("--cc-by-share", type=float, default=0.3)
    parser.add_argument("--min-reviewable", type=int, default=6)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    classes_dir = Path(args.classes_dir)
    docs = [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(classes_dir.glob("*.json"))]
    if not docs:
        raise SystemExit(f"no class manifests in {classes_dir}; run collect_v2.py first")

    plan = plan_classes(docs, args.per_class, args.min_reviewable)
    if args.plan:
        print(json.dumps(plan, indent=1))
        return 0

    wanted = args.classes or plan["classes_worth_a_batch"]
    if not wanted:
        print("No class has enough reviewable material for a batch. "
              "Collect more classes first.", file=sys.stderr)
        return 1

    built = []
    for doc in docs:
        if doc["class"] not in wanted:
            continue
        records = doc.get("files", [])
        chosen = select_batch(records, limit=args.per_class, cc_by_share=args.cc_by_share)
        if not chosen:
            print(f"{doc['class']}: no reviewable files, skipped", file=sys.stderr)
            continue
        path = write_batch(
            Path(args.out) / doc["class"],
            build_batch_doc(doc, prepare_entries(chosen), limit=args.per_class),
            force=args.force,
        )
        built.append({"class": doc["class"], "size": len(chosen), "path": str(path)})
        print(f"{doc['class']}: {len(chosen)} files -> {path}", file=sys.stderr)

    print(json.dumps({"batches": built, "note": "reviewing is not approving"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
