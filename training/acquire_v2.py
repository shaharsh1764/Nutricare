#!/usr/bin/env python3
"""Download real Commons image bytes for the V2 100-class dataset.

Why this file exists
--------------------
``collect_v2.py`` is explicitly *metadata only*: it ends with the line
"Never downloads image bytes." ``prepare_v2_dataset.py`` can verify and split
local bytes, but nothing in the repository ever wrote those bytes to disk. So
the pipeline had a hole in the middle: metadata in, integrity checks out, and
no actual photographs in between. This module fills exactly that hole.

Nothing here invents a new policy. Rights classification is delegated to
``licence_policy.classify_rights``; the Commons metadata shape is built by
``commons_audit.build_file_record``; integrity, perceptual hashing and
near-duplicate detection reuse ``prepare_v2_dataset``. The only new behaviour
is *transferring the file* and *proving afterwards that what landed on disk is
the thing the metadata described*.

The honesty rules
-----------------
* A record is only ever counted as a downloaded image when a file exists, is
  non-empty, decodes as an image, and matches its declared byte size.
* A thumbnail URL is never counted as an image. If the API hands back a
  scaled ``thumburl`` where the original was wanted, the download is recorded
  as ``thumb_only`` and excluded.
* Nothing is auto-approved. ``human_review_status`` starts at ``pending`` and
  only the existing review store can move it.
* A source whose images cannot reach disk is reported as unusable. It is not
  counted, estimated or extrapolated.

Usage
-----
    python training/acquire_v2.py --self-test          # offline, no network
    python training/acquire_v2.py --probe              # test source reachability
    python training/acquire_v2.py --class biryani --limit 20
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

TRAINING_DIR = Path(__file__).resolve().parent
PROJECT = TRAINING_DIR.parent
sys.path.insert(0, str(TRAINING_DIR))

from commons_audit import build_file_record  # noqa: E402
from licence_policy import (  # noqa: E402
    EXCLUDED,
    REVIEW_REQUIRED,
    TRAINING_APPROVED,
    classify_rights,
)
from prepare_v2_dataset import (  # noqa: E402
    check_image_bytes,
    dhash_from_path,
    hamming,
)

V2_DATA_DIR = PROJECT / "data" / "v4"
IMAGES_DIR = V2_DATA_DIR / "images"
MANIFESTS_DIR = V2_DATA_DIR / "acquisition"

#: Formats the rest of the pipeline can decode. Kept in step with
#: ``prepare_v2_dataset.IMAGE_SUFFIXES``.
SUFFIX_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
}

#: Minimum bytes for a plausible photograph. Anything smaller is an error page,
#: a tracking pixel or an empty response body.
MIN_BYTES = 1024

#: dHash Hamming distance at or below which two images are near duplicates.
NEAR_DUP_THRESHOLD = 6


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# Source reachability
# ---------------------------------------------------------------------------


def probe_host(host: str, *, timeout: float = 8.0) -> Dict[str, Any]:
    """Check whether ``host`` accepts a TLS connection from this sandbox.

    Returns the measured outcome. This is deliberately a *probe*, not a
    judgement: a blocked host is recorded as unreachable with the exact error,
    so a later run can tell "no images exist" from "I could not look".
    """
    import socket
    import ssl

    started = time.time()
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host) as tls:
                peer = tls.getpeercert().get("subject", [])
        return {
            "host": host,
            "reachable": True,
            "tls_subject": str(peer)[:120],
            "elapsed_s": round(time.time() - started, 3),
        }
    except Exception as exc:  # noqa: BLE001 - any failure means "cannot reach"
        return {
            "host": host,
            "reachable": False,
            "error": f"{type(exc).__name__}: {exc}"[:200],
            "elapsed_s": round(time.time() - started, 3),
        }


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def download_image(
    url: str,
    dest: Path,
    *,
    opener: Optional[Callable[[str, float], bytes]] = None,
    timeout: float = 60.0,
    expected_bytes: Optional[int] = None,
) -> Dict[str, Any]:
    """Fetch ``url`` into ``dest`` and verify the result decodes.

    ``opener`` exists so tests can supply a fake transport without network
    access. The default opener performs a real HTTPS request.

    The returned dict always carries ``ok``. On any failure the partial file is
    removed so a later run cannot mistake a truncated download for a real one.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    fetch = opener or _https_opener
    started = time.time()
    try:
        payload = fetch(url, timeout)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"fetch_failed: {type(exc).__name__}: {exc}"[:180],
                "bytes": 0, "sha256": None}

    if not payload:
        return {"ok": False, "reason": "empty_response", "bytes": 0, "sha256": None}
    if len(payload) < MIN_BYTES:
        return {"ok": False, "reason": f"too_small: {len(payload)} bytes",
                "bytes": len(payload), "sha256": None}
    if expected_bytes is not None and len(payload) != expected_bytes:
        # A truncated or substituted body is not the file the metadata
        # described, so it is rejected rather than quietly accepted.
        return {"ok": False,
                "reason": f"size_mismatch: got {len(payload)} expected {expected_bytes}",
                "bytes": len(payload), "sha256": None}

    dest.write_bytes(payload)
    sha256 = hashlib.sha256(payload).hexdigest()

    check = check_image_bytes(dest)
    if not check.get("ok"):
        reason = str(check.get("reason"))
        # Keep the file only when the problem is a *quality* judgement
        # (too small / near uniform); drop it when it does not decode at all.
        if reason.startswith("decode_failed"):
            dest.unlink(missing_ok=True)
            return {"ok": False, "reason": reason, "bytes": len(payload), "sha256": sha256}
        return {"ok": False, "reason": reason, "bytes": len(payload),
                "sha256": sha256, "width": check.get("width"), "height": check.get("height"),
                "kept_for_inspection": True}

    return {
        "ok": True,
        "reason": "ok",
        "bytes": len(payload),
        "sha256": sha256,
        "width": check.get("width"),
        "height": check.get("height"),
        "dhash": check.get("dhash"),
        "mean_rgb": check.get("mean_rgb"),
        "elapsed_s": round(time.time() - started, 3),
        "dest": str(dest),
    }


def _https_opener(url: str, timeout: float = 60.0) -> bytes:
    """Default transport: a plain HTTPS GET with a project User-Agent."""
    import urllib.request

    request = urllib.request.Request(
        url,
        headers={
            # Wikimedia asks for a descriptive UA; identifying the project is
            # also what makes the traffic auditable from their side.
            "User-Agent": "NutriCare-V2-dataset/1.0 (research; contact: repo owner)",
            "Accept": "image/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


# ---------------------------------------------------------------------------
# Record assembly
# ---------------------------------------------------------------------------


def plan_record(
    record: Dict[str, Any],
    *,
    class_slug: str,
) -> Dict[str, Any]:
    """Attach rights tier and an initial review status to a metadata record.

    The rights decision is delegated to ``classify_rights`` so this module
    cannot drift from the policy reviewed in PR #8. Review status is always
    ``pending``: a permissive licence is a precondition, never a label approval.
    """
    licence = record.get("licence") or {}
    attribution = record.get("attribution") or {}
    rights = classify_rights(
        licence,
        artist=attribution.get("artist_raw") or "",
        permission_text=record.get("permission") or "",
        credit_text=attribution.get("credit") or "",
    )
    return {
        "class": class_slug,
        "pageid": record.get("pageid"),
        "title": record.get("title"),
        "source": "wikimedia_commons",
        "source_url": record.get("url"),
        "description_url": record.get("description_url"),
        "original_identifier": record.get("pageid"),
        "declared_sha1": record.get("sha1"),
        "declared_bytes": record.get("size_bytes"),
        "licence": {
            "short_name": licence.get("short_name"),
            "declared_class": licence.get("declared_class"),
            "licence_url": licence.get("licence_url"),
            "attribution_required": licence.get("attribution_required"),
        },
        "author": attribution.get("artist_raw"),
        "permission": record.get("permission"),
        "credit": attribution.get("credit"),
        "rights_tier": rights.get("rights_tier"),
        "rights_reasons": rights.get("reasons", []),
        "human_review_status": "pending",
        "downloaded_at": None,
        "local_sha256": None,
        "integrity": None,
    }


def is_thumb_url(url: Optional[str]) -> bool:
    """True when a Commons URL points at a scaled derivative, not the original."""
    if not url:
        return True
    lowered = url.lower()
    return "/thumb/" in lowered or lowered.endswith("/thumb")


def acquire_one(
    planned: Dict[str, Any],
    *,
    images_dir: Path,
    opener: Optional[Callable[[str, float], bytes]] = None,
) -> Dict[str, Any]:
    """Download one planned record and fold the measured facts into it."""
    out = dict(planned)
    url = planned.get("source_url")

    if planned.get("rights_tier") == EXCLUDED:
        out["acquire_status"] = "skipped_rights_excluded"
        return out
    if not url:
        out["acquire_status"] = "skipped_no_url"
        return out
    if is_thumb_url(url):
        # Counting a thumbnail as the dataset image is exactly the mistake the
        # task forbids, so this is recorded as a failure, not a success.
        out["acquire_status"] = "skipped_thumb_only"
        return out

    suffix = ".jpg"
    dest = Path(images_dir) / f"{planned.get('pageid')}{suffix}"
    result = download_image(url, dest, opener=opener,
                            expected_bytes=planned.get("declared_bytes"))
    out["download"] = result

    if not result.get("ok"):
        out["acquire_status"] = "failed"
        out["failure_reason"] = result.get("reason")
        return out

    out["acquire_status"] = "downloaded"
    out["downloaded_at"] = utc_now()
    out["local_sha256"] = result.get("sha256")
    out["local_path"] = result.get("dest")
    out["integrity"] = {
        "width": result.get("width"),
        "height": result.get("height"),
        "dhash": result.get("dhash"),
        "bytes": result.get("bytes"),
    }
    return out


# ---------------------------------------------------------------------------
# Duplicate audit over downloaded rows
# ---------------------------------------------------------------------------


def audit_duplicates(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Find byte-identical and perceptually near-duplicate downloaded images.

    Both checks run only over rows that actually have bytes on disk, so an
    unreachable source cannot masquerade as "no duplicates found".
    """
    downloaded = [r for r in rows if r.get("acquire_status") == "downloaded"]

    by_sha: Dict[str, List[Any]] = {}
    for row in downloaded:
        sha = row.get("local_sha256")
        if sha:
            by_sha.setdefault(sha, []).append(row.get("pageid"))
    exact = {sha: ids for sha, ids in by_sha.items() if len(ids) > 1}

    hashed = [(r.get("pageid"), (r.get("integrity") or {}).get("dhash")) for r in downloaded]
    hashed = [(pid, h) for pid, h in hashed if h]
    near: List[Dict[str, Any]] = []
    for i in range(len(hashed)):
        for j in range(i + 1, len(hashed)):
            a, ha = hashed[i]
            b, hb = hashed[j]
            distance = hamming(ha, hb)
            if distance <= NEAR_DUP_THRESHOLD:
                near.append({"a": a, "b": b, "distance": distance})

    unique = len(downloaded) - sum(len(ids) - 1 for ids in exact.values())
    return {
        "downloaded": len(downloaded),
        "exact_duplicate_groups": exact,
        "exact_duplicate_extra_copies": sum(len(ids) - 1 for ids in exact.values()),
        "near_duplicate_pairs": near,
        "unique_by_content": unique,
    }


# ---------------------------------------------------------------------------
# Self test (offline)
# ---------------------------------------------------------------------------


def self_test() -> int:
    failures: List[str] = []

    def check(cond: bool, msg: str) -> None:
        print(("  ok   " if cond else "  FAIL ") + msg)
        if not cond:
            failures.append(msg)

    print("acquire_v2 self-test (offline, no network)\n")

    import io

    from PIL import Image

    def png_bytes(seed: int = 0, size: Tuple[int, int] = (400, 400)) -> bytes:
        img = Image.new("RGB", size, (seed % 256, 40, 90))
        for x in range(0, size[0], 7):
            for y in range(0, size[1], 11):
                img.putpixel((x, y), (255, (x + seed) % 256, y % 256))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    good = png_bytes(1)

    # --- 1. a real image transfers and verifies -------------------------
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "1.png"
        res = download_image("https://example.invalid/a.png", dest,
                             opener=lambda u, t: good, expected_bytes=len(good))
        check(res["ok"], "valid image downloads and decodes")
        check(dest.exists(), "file written to disk")
        check(res["sha256"] == hashlib.sha256(good).hexdigest(), "sha256 matches payload")

    # --- 2. empty / tiny / truncated payloads are rejected --------------
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "2.png"
        r = download_image("u", dest, opener=lambda u, t: b"")
        check(not r["ok"] and r["reason"] == "empty_response", "empty body rejected")
        check(not dest.exists(), "no file left for empty body")
        r = download_image("u", dest, opener=lambda u, t: b"x" * 10)
        check(not r["ok"] and r["reason"].startswith("too_small"), "tiny body rejected")
        r = download_image("u", dest, opener=lambda u, t: good[: len(good) // 2],
                           expected_bytes=len(good))
        check(not r["ok"] and r["reason"].startswith("size_mismatch"),
              "truncated body rejected by declared size")

    # --- 3. non-image bytes fail to decode and are deleted --------------
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "3.png"
        junk = b"<html>404 not found</html>" + b" " * 2000
        r = download_image("u", dest, opener=lambda u, t: junk)
        check(not r["ok"] and r["reason"].startswith("decode_failed"),
              "HTML error page rejected as non-image")
        check(not dest.exists(), "undecodable file removed")

    # --- 4. fetch exceptions are captured, not raised -------------------
    def boom(url: str, timeout: float) -> bytes:
        raise OSError("connection reset")

    with tempfile.TemporaryDirectory() as tmp:
        r = download_image("u", Path(tmp) / "4.png", opener=boom)
        check(not r["ok"] and r["reason"].startswith("fetch_failed: OSError"),
              "transport error captured")

    # --- 5. thumbnail URLs are never accepted as originals --------------
    check(is_thumb_url("https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/X.jpg/512px-X.jpg"),
          "thumb URL detected")
    check(is_thumb_url("https://x/thumb"), "bare /thumb detected")
    check(not is_thumb_url("https://upload.wikimedia.org/wikipedia/commons/a/ab/X.jpg"),
          "original URL not flagged")

    # --- 6. rights exclusions are skipped before any transfer -----------
    planned = plan_record(
        {"pageid": 1, "title": "File:A.jpg", "url": "https://u/a.jpg",
         "licence": {"declared_class": "NC_RESTRICTED", "short_name": "CC BY-NC"},
         "attribution": {"artist_raw": "Someone"}},
        class_slug="biryani",
    )
    check(planned["rights_tier"] == EXCLUDED, "NC licence plans as EXCLUDED")
    check(planned["human_review_status"] == "pending",
          "review status starts pending even when licence is fine")

    with tempfile.TemporaryDirectory() as tmp:
        got = acquire_one(planned, images_dir=Path(tmp))
        check(got["acquire_status"] == "skipped_rights_excluded",
              "excluded record never downloaded")

    # --- 7. a permissive licence does NOT auto-approve ------------------
    ok_plan = plan_record(
        {"pageid": 2, "title": "File:B.jpg", "url": "https://u/b.jpg",
         "licence": {"declared_class": "CC0_PD", "short_name": "CC0"},
         "attribution": {"artist_raw": "Someone"}},
        class_slug="biryani",
    )
    check(ok_plan["rights_tier"] in (TRAINING_APPROVED, REVIEW_REQUIRED),
          f"CC0 plans as {ok_plan['rights_tier']}")
    check(ok_plan["human_review_status"] == "pending",
          "CC0 record still awaiting human review")

    # --- 8. duplicate audit counts honestly -----------------------------
    img_a = png_bytes(1)
    img_b = png_bytes(2)
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        pa, pb, pc = d / "1.png", d / "2.png", d / "3.png"
        pa.write_bytes(img_a)
        pb.write_bytes(img_a)   # byte-identical copy
        pc.write_bytes(img_b)   # different image
        rows = []
        for pid, path in ((1, pa), (2, pb), (3, pc)):
            chk = check_image_bytes(path)
            rows.append({"pageid": pid, "acquire_status": "downloaded",
                         "local_sha256": chk["sha256"],
                         "integrity": {"dhash": chk["dhash"]}})
        audit = audit_duplicates(rows)
        check(audit["downloaded"] == 3, "3 downloaded rows counted")
        check(audit["exact_duplicate_extra_copies"] == 1, "1 extra exact copy identified")
        check(audit["unique_by_content"] == 2, "unique content count is 2, not 3")

    # --- 9. failed rows are excluded from duplicate accounting ----------
    audit = audit_duplicates([
        {"pageid": 1, "acquire_status": "failed", "local_sha256": "abc",
         "integrity": {"dhash": "0000000000000000"}},
        {"pageid": 2, "acquire_status": "failed", "local_sha256": "abc",
         "integrity": {"dhash": "0000000000000000"}},
    ])
    check(audit["downloaded"] == 0,
          "failed transfers contribute nothing to duplicate counts")

    # --- 10. probe reports unreachability rather than guessing ----------
    probe = probe_host("this-host-does-not-exist.invalid", timeout=2.0)
    check(probe["reachable"] is False, "unreachable host reported as unreachable")
    check("error" in probe, "probe carries the measured error")

    print()
    if failures:
        print(f"SELF-TEST FAILED: {len(failures)} check(s)")
        for f in failures:
            print("  -", f)
        return 1
    print("SELF-TEST PASSED: all acquisition checks hold")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


PROBE_HOSTS = [
    "commons.wikimedia.org",
    "upload.wikimedia.org",
    "huggingface.co",
    "raw.githubusercontent.com",
    "codeload.github.com",
]


def run_probe() -> int:
    print("Source reachability probe (measured, not assumed)\n")
    out = []
    for host in PROBE_HOSTS:
        result = probe_host(host)
        out.append(result)
        status = "REACHABLE  " if result["reachable"] else "UNREACHABLE"
        detail = result.get("error") or result.get("tls_subject", "")
        print(f"  {status} {host:32s} {str(detail)[:80]}")
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    path = MANIFESTS_DIR / "source_probe.json"
    path.write_text(json.dumps({"probed_at": utc_now(), "hosts": out}, indent=2) + "\n")
    print(f"\nwritten: {path}")
    reachable = sum(1 for r in out if r["reachable"])
    print(f"{reachable}/{len(out)} hosts reachable from this sandbox")
    return 0 if reachable else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Download Commons image bytes for V2.")
    ap.add_argument("--self-test", action="store_true", help="offline checks")
    ap.add_argument("--probe", action="store_true", help="probe source reachability")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.probe:
        return run_probe()
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ---------------------------------------------------------------------------
# Class-by-class acquisition attempt
# ---------------------------------------------------------------------------

#: Every column the task requires in the per-class report. Kept as a list so a
#: missing column is a loud KeyError rather than a silently absent number.
REPORT_COLUMNS = [
    "images_discovered",
    "images_downloaded",
    "passing_integrity",
    "exact_duplicates",
    "near_duplicates",
    "corrupt",
    "rejected_irrelevant_or_quality",
    "rights_approved",
    "awaiting_human_review",
    "final_usable",
]


def load_seeds(path: Path) -> List[Dict[str, Any]]:
    """Read a seed file of ``{class, page}`` pairs as fetched from Commons."""
    payload = json.loads(Path(path).read_text())
    return payload.get("records", payload)


def plan_from_seed(seed: Dict[str, Any]) -> Dict[str, Any]:
    """Turn one raw Commons seed into a planned acquisition record."""
    page = seed.get("page") or {}
    title = page.get("title") or "File:Untitled"
    record = build_file_record(title, page, [], [seed.get("class") or "unknown"])
    attribution = record.get("attribution") or {}
    licence = record.get("licence") or {}
    planned = {
        "class": seed.get("class"),
        "pageid": record.get("pageid"),
        "title": record.get("title"),
        "source": "wikimedia_commons",
        "source_url": record.get("url"),
        "description_url": record.get("description_url"),
        "original_identifier": record.get("pageid"),
        "declared_sha1": record.get("sha1"),
        "declared_bytes": record.get("size_bytes"),
        "declared_width": record.get("width"),
        "declared_height": record.get("height"),
        "licence": {
            "short_name": licence.get("short_name"),
            "declared_class": licence.get("declared_class"),
            "licence_url": licence.get("licence_url"),
            "attribution_required": licence.get("attribution_required"),
        },
        "author": attribution.get("artist_raw"),
        "permission": record.get("permission"),
        "credit": attribution.get("credit"),
        # Always pending. A permissive licence is a precondition for review,
        # never a substitute for it.
        "human_review_status": "pending",
        "downloaded_at": None,
        "local_sha256": None,
    }
    rights = classify_rights(
        licence,
        artist=attribution.get("artist_raw") or "",
        permission_text=record.get("permission") or "",
        credit_text=attribution.get("credit") or "",
    )
    planned["rights_tier"] = rights.get("rights_tier")
    planned["rights_reasons"] = rights.get("reasons", [])
    return planned


def _class_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute the ten report columns for one class.

    The columns are deliberately not derivable from each other: ``discovered``
    includes records that never transferred, and ``final_usable`` requires
    bytes on disk *and* a human approval, so it cannot be inferred from the
    rights tier alone.
    """
    downloaded = [r for r in rows if r.get("acquire_status") == "downloaded"]
    integrity_ok = [r for r in downloaded if (r.get("integrity") or {}).get("width")]
    corrupt = [
        r for r in rows
        if r.get("acquire_status") == "failed"
        and str(r.get("failure_reason", "")).startswith("decode_failed")
    ]
    # A transfer that never happened is NOT a quality rejection. Lumping
    # "could not reach the host" into "rejected for quality" would invent
    # judgements about images nobody ever saw, so the two are counted apart.
    quality_rejected = []
    transfer_failed = []
    for r in rows:
        if r.get("acquire_status") != "failed":
            continue
        reason = str(r.get("failure_reason", ""))
        if reason.startswith("decode_failed"):
            continue  # counted as corrupt above
        if reason.startswith("fetch_failed") or reason.startswith("empty_response"):
            transfer_failed.append(r)
        else:
            quality_rejected.append(r)
    rights_ok = [r for r in rows if r.get("rights_tier") == TRAINING_APPROVED]
    # No row is approved yet: human review has not run over any of them.
    approved = [r for r in rows if r.get("human_review_status") == "approved"]

    audit = audit_duplicates(rows)
    return {
        "images_discovered": len(rows),
        "images_downloaded": len(downloaded),
        "passing_integrity": len(integrity_ok),
        "exact_duplicates": audit["exact_duplicate_extra_copies"],
        "near_duplicates": len(audit["near_duplicate_pairs"]),
        "corrupt": len(corrupt),
        "rejected_irrelevant_or_quality": len(quality_rejected),
        "rights_approved": len(rights_ok),
        "awaiting_human_review": len([r for r in rows if r.get("human_review_status") == "pending"]),
        "final_usable": len(approved),
        "_rights_excluded": len([r for r in rows if r.get("rights_tier") == EXCLUDED]),
        "_rights_review_required": len([r for r in rows if r.get("rights_tier") == REVIEW_REQUIRED]),
        "_transfer_failed": len(transfer_failed),
        "_download_failed": len([r for r in rows if r.get("acquire_status") == "failed"]),
        "_skipped": len([r for r in rows if str(r.get("acquire_status", "")).startswith("skipped")]),
    }


def run_acquisition_attempt(
    seeds_path: Path,
    *,
    out_dir: Path,
    images_dir: Optional[Path] = None,
    opener: Optional[Callable[[str, float], bytes]] = None,
    download: bool = True,
    limit_per_class: Optional[int] = None,
) -> Dict[str, Any]:
    """Plan every seed, optionally transfer its bytes, and summarise per class.

    ``download=False`` still produces a complete report; the download columns
    are then honestly zero rather than absent. ``opener`` lets tests run the
    whole path offline.
    """
    seeds = load_seeds(seeds_path)
    by_class: Dict[str, List[Dict[str, Any]]] = {}
    for seed in seeds:
        slug = seed.get("class") or "unknown"
        bucket = by_class.setdefault(slug, [])
        if limit_per_class is not None and len(bucket) >= limit_per_class:
            continue
        bucket.append(seed)

    rows: List[Dict[str, Any]] = []
    per_class: Dict[str, Any] = {}
    for slug in sorted(by_class):
        planned_rows = []
        for seed in by_class[slug]:
            planned = plan_from_seed(seed)
            if download:
                target = (images_dir or IMAGES_DIR) / slug
                planned = acquire_one(planned, images_dir=target, opener=opener)
            else:
                planned["acquire_status"] = "not_attempted"
            planned_rows.append(planned)
        rows.extend(planned_rows)
        per_class[slug] = _class_summary(planned_rows)

    totals = {col: sum(per_class[s][col] for s in per_class) for col in REPORT_COLUMNS}
    report = {
        "schema_version": "1.0",
        "generated_utc": utc_now(),
        "seeds_path": str(seeds_path),
        "download_attempted": download,
        "images_dir": str(images_dir or IMAGES_DIR),
        "column_definitions": {
            "images_discovered": "seed records fetched from the source catalogue",
            "images_downloaded": "files that reached disk, decoded and matched declared size",
            "passing_integrity": "downloaded files that decoded with readable dimensions",
            "exact_duplicates": "extra copies sharing a SHA-256 with an earlier row",
            "near_duplicates": "pairs within dHash distance 6",
            "corrupt": "files that failed to decode",
            "rejected_irrelevant_or_quality": "transfers that completed but were rejected for size/uniformity/format; a network failure is never counted here",
            "rights_approved": "rows whose declared rights permit training (NOT visually approved)",
            "awaiting_human_review": "rows whose review status is still pending",
            "final_usable": "rows with bytes on disk AND a human approval; 0 until review runs",
        },
        "per_class": per_class,
        "totals": totals,
        "rows": rows,
    }

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "acquisition_attempt.json").write_text(json.dumps(report, indent=1) + "\n")
    return report


def render_attempt_report(report: Dict[str, Any]) -> str:
    """Render the per-class table plus a blunt statement of what is usable."""
    lines = ["# Acquisition attempt — class by class", ""]
    lines.append(f"Generated: {report['generated_utc']}  ")
    lines.append(f"Download attempted: **{report['download_attempted']}**  ")
    lines.append("")
    head = "| class | " + " | ".join(REPORT_COLUMNS) + " |"
    rule = "|---|" + "|".join(["---"] * len(REPORT_COLUMNS)) + "|"
    lines += [head, rule]
    for slug in sorted(report["per_class"]):
        row = report["per_class"][slug]
        lines.append(f"| {slug} | " + " | ".join(str(row[c]) for c in REPORT_COLUMNS) + " |")
    totals = report["totals"]
    lines.append("| **total** | " + " | ".join(f"**{totals[c]}**" for c in REPORT_COLUMNS) + " |")
    lines += [
        "",
        "`rights_approved` is a *rights* judgement about the declared licence. It is not a "
        "visual confirmation that the photograph depicts the stated dish, and it is not a "
        "training count.",
        "",
        f"**Final usable images: {totals['final_usable']}.** Nothing reaches this column "
        "until bytes exist on disk and a human has approved the label.",
        "",
    ]
    return "\n".join(lines)
