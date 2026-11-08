#!/usr/bin/env python3
"""Build a controlled human-review sample from the Biryani pilot manifest.

This stage resolves **thumbnail URLs** for a small, deterministic sample of the
93 pilot records. It deliberately does not download image bytes: the sandbox
cannot reach ``upload.wikimedia.org`` (TLS handshake is dropped), and bulk
downloading is out of scope for this phase.

Design notes
------------
* The source manifest is opened **read-only** and never rewritten. Human review
  lives in a separate file so source metadata and human judgement can never be
  confused with one another.
* Thumbnails are preferred over originals via the API's ``iiurlwidth`` parameter.
* Every sample entry records the source URL, page id, SHA1 and a retrieval
  timestamp, plus a ``retrieval_status`` explaining what actually happened.
* If the batch API that resolves thumbnail URLs is unreachable, the tool still
  writes the sample with ``retrieval_status: "url_unresolved"`` and a documented
  reason. It never invents a URL.

Usage
-----
    python training/review_sample.py --limit 10
    python training/review_sample.py --limit 10 --transport mock
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_MANIFEST = "data/v3/commons_pilot/biryani_manifest.json"
DEFAULT_OUT = "data/v3/commons_pilot/review"

#: Content hash of the original manifest is recorded so a reviewer can prove the
#: source metadata was not mutated during review.
SOURCE_FIELDS_KEPT = (
    "pageid",
    "title",
    "sha1",
    "width",
    "height",
    "mime",
    "description_url",
    "licence",
    "attribution",
    "categories",
    # Missing-metadata markers must survive into the review view, so a reviewer
    # can see that, say, the artist is absent rather than simply not shown.
    "metadata_gaps",
    "usable_for_training",
)


def utc_now() -> str:
    """ISO-8601 UTC timestamp, seconds precision."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def select_sample(files: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
    """Choose a deterministic, licence-diverse sample.

    Deterministic so the sample is reproducible and reviewable in an audit.
    Diverse so the reviewer sees more than one licence bucket: the selection
    walks the manifest ordered by page id and picks round-robin across declared
    licence classes, which guarantees the rarer CC0 / CC BY files appear even
    though they are a tiny minority of the corpus.
    """
    if limit <= 0:
        raise ValueError("limit must be positive")
    ordered = sorted(files, key=lambda f: f.get("pageid") or 0)

    by_class: Dict[str, List[Dict[str, Any]]] = {}
    for record in ordered:
        key = (record.get("licence") or {}).get("declared_class") or "UNKNOWN"
        by_class.setdefault(key, []).append(record)

    # Rarest declared class first, so limited slots surface CC0/CC BY.
    class_order = sorted(by_class, key=lambda k: (len(by_class[k]), k))
    picked: List[Dict[str, Any]] = []
    while len(picked) < limit:
        progressed = False
        for key in class_order:
            bucket = by_class[key]
            if bucket and len(picked) < limit:
                picked.append(bucket.pop(0))
                progressed = True
        if not progressed:
            break
    return sorted(picked, key=lambda f: f.get("pageid") or 0)


def build_sample_entry(record: Dict[str, Any]) -> Dict[str, Any]:
    """Copy only source fields, leaving room for retrieval data to be added."""
    entry = {field: record[field] for field in SOURCE_FIELDS_KEPT if field in record}
    entry["thumbnail"] = {
        "url": "",
        "width": None,
        "height": None,
        "retrieval_status": "url_unresolved",
        "retrieval_note": "thumbnail URL not yet resolved",
        "retrieved_utc": None,
    }
    return entry


def apply_thumbinfo(entry: Dict[str, Any], page: Dict[str, Any], retrieved_utc: str) -> None:
    """Attach a resolved thumbnail URL from an API imageinfo page."""
    info = page.get("imageinfo")
    if isinstance(info, list):
        info = info[0] if info else None
    if not info:
        entry["thumbnail"].update(
            {
                "retrieval_status": "url_unresolved",
                "retrieval_note": "API returned no imageinfo for this title",
                "retrieved_utc": retrieved_utc,
            }
        )
        return
    thumb_url = info.get("thumburl") or ""
    entry["thumbnail"].update(
        {
            "url": thumb_url,
            "width": info.get("thumbwidth"),
            "height": info.get("thumbheight"),
            "original_url_recorded_only": info.get("url") or "",
            "retrieval_status": "url_resolved_not_downloaded" if thumb_url else "url_unresolved",
            "retrieval_note": (
                "Thumbnail URL resolved from the Commons API. Image bytes were NOT "
                "downloaded by this tool; the review page loads the thumbnail from "
                "Wikimedia's own servers in the reviewer's browser."
                if thumb_url
                else "API did not return a thumbnail URL"
            ),
            "retrieved_utc": retrieved_utc,
        }
    )


def write_sample(
    out_dir: Path,
    entries: List[Dict[str, Any]],
    *,
    source_manifest: Path,
    source_sha256: str,
    limit: int,
    retrieval_blocked_reason: Optional[str] = None,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "generated_utc": utc_now(),
        "source_manifest": str(source_manifest),
        "source_manifest_sha256": source_sha256,
        "source_manifest_read_only": True,
        "sample_limit": limit,
        "sample_size": len(entries),
        "selection_method": "deterministic, round-robin across declared licence "
        "classes, ordered by Commons page id",
        "image_bytes_downloaded": False,
        "retrieval_blocked_reason": retrieval_blocked_reason,
        "licence_reminder": "A declared Commons licence is not independently "
        "verified permission. Nothing in this sample is legally cleared, and "
        "usable_for_training is false for every record.",
        "images": entries,
    }
    path = out_dir / "review_sample.json"
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build the human-review sample.")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--transport",
        choices=("auto", "mock", "none"),
        default="none",
        help="auto: try the live API; mock: use a local fixture; none: no URL resolution",
    )
    parser.add_argument("--fixture", default=None, help="fixture JSON for --transport mock")
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)
    raw_bytes = manifest_path.read_bytes()
    import hashlib

    source_sha = hashlib.sha256(raw_bytes).hexdigest()
    manifest = json.loads(raw_bytes.decode("utf-8"))

    entries = [build_sample_entry(r) for r in select_sample(manifest["files"], args.limit)]

    blocked: Optional[str] = None
    retrieved = utc_now()

    if args.transport == "mock":
        if not args.fixture:
            print("error: --transport mock requires --fixture", file=sys.stderr)
            return 2
        fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
        pages = {p.get("title"): p for p in fixture.get("pages", [])}
        for entry in entries:
            page = pages.get(entry["title"])
            if page:
                apply_thumbinfo(entry, page, retrieved)
            else:
                entry["thumbnail"].update(
                    {
                        "retrieval_status": "url_unresolved",
                        "retrieval_note": "title absent from fixture",
                        "retrieved_utc": retrieved,
                    }
                )
    elif args.transport == "auto":
        from training.commons_audit import CommonsAPIError, CommonsClient, HttpTransport

        client = CommonsClient(HttpTransport(), delay=0.5)
        try:
            for entry in entries:
                info = client.file_info([entry["title"]])
                apply_thumbinfo(entry, info.get(entry["title"], {}), retrieved)
        except CommonsAPIError as exc:
            blocked = (
                "Commons API unreachable from this environment: "
                f"{exc}. Thumbnail URLs were therefore not resolved. "
                "No image bytes were downloaded."
            )
            for entry in entries:
                entry["thumbnail"].update(
                    {
                        "retrieval_status": "blocked",
                        "retrieval_note": "API unreachable from the sandbox",
                        "retrieved_utc": retrieved,
                    }
                )
    else:
        blocked = (
            "URL resolution not requested (--transport none). Sandbox egress to "
            "commons.wikimedia.org and upload.wikimedia.org is blocked at the TLS "
            "handshake, so no image bytes can be fetched here."
        )

    path = write_sample(
        Path(args.out),
        entries,
        source_manifest=manifest_path,
        source_sha256=source_sha,
        limit=args.limit,
        retrieval_blocked_reason=blocked,
    )

    resolved = sum(
        1 for e in entries if e["thumbnail"]["retrieval_status"] == "url_resolved_not_downloaded"
    )
    print(f"sample={len(entries)} thumbnails_resolved={resolved} wrote={path}")
    if blocked:
        print(f"blocked: {blocked}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
