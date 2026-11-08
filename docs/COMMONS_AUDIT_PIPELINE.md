# Commons audit pipeline — API access, status, and how to run it

**Date:** 2026-11-05
**Phase:** Metadata tooling only. No image downloaded, no model trained, no
application code changed, no dataset declared ready.

---

## 1. API accessibility — measured, not assumed

Tested from inside the Arena sandbox with `curl` and with the tool's own
transport.

| Host | Purpose | Result |
|---|---|---|
| `commons.wikimedia.org` | MediaWiki action API (metadata) | ❌ **BLOCKED** |
| `upload.wikimedia.org` | Image bytes / thumbnails | ❌ **BLOCKED** |
| `api.wikimedia.org` | REST API | ❌ **BLOCKED** |

### Exact failure mode

DNS resolves and TCP connects, so this is **not** a name-resolution or routing
problem. The TLS handshake is dropped by the egress layer:

```
*   Trying 198.35.26.224:443...
* Connected to commons.wikimedia.org (198.35.26.224) port 443 (#0)
* TLSv1.3 (OUT), TLS handshake, Client hello (1):
* OpenSSL SSL_connect: SSL_ERROR_SYSCALL in connection to commons.wikimedia.org:443
curl: (35)
```

`SSL_ERROR_SYSCALL` at Client Hello means the connection is closed during
handshake — characteristic of a filtering proxy that refuses these hosts without
completing TLS (the same signature seen earlier for the Hugging Face CDN).

**No API access therefore implies no image access**, but the converse is the
subtle trap worth stating: if only `commons.wikimedia.org` were allowlisted, the
tool would retrieve complete metadata and *still* be unable to fetch a single
image, because the bytes live on `upload.wikimedia.org`. **Both hosts are
required** for the eventual fetch stage.

### Why I stopped testing

Three hosts × two methods is enough to establish the block. Repeated retries
would burn time and add nothing, so the pipeline was built and tested against
**recorded fixture responses** instead. The tool has never executed a live
Commons request.

---

## 2. What was actually measured vs. what remains unknown

### Measured in this phase (reproducible offline)

| Item | Value | How |
|---|---|---|
| Live Commons metadata retrieved | **0 files** | Hosts blocked |
| Images downloaded | **0** | Out of scope |
| Tool test coverage | **69 tests, all passing** | Mocked/recorded responses |
| Existing suite | **233 tests still passing** (302 total) | No regressions |
| End-to-end demo run | Jalebi / Gulab Jamun / Rasgulla fixture | Pagination, subcategory inheritance, overlap collapse, SHA1 dedupe, NC exclusion, missing-metadata gaps all exercised |

### Unknown — cannot be established in this environment

- The **real** file counts reachable per category once egress opens.
- Whether any candidate file is a usable, correctly labelled photograph of the dish.
- Perceptual/near-duplicate rate — requires image bytes.
- Actual per-file licence distribution across the corpus.
- Contents of categories beyond the configured traversal depth.
- Whether CC BY-SA obligations reach trained model weights (**flagged for legal review; not resolved here**).

**Nothing in this phase changes any dataset figure** from
`docs/INDIAN_FOOD_100_CLASS_RESEARCH.md`. That report's counts remain
category-file counts of unverified provenance; this tooling exists to replace
them with measured per-file data once the network permits.

---

## 3. What was built

### `training/commons_audit.py`

A reusable metadata auditor. Standard library only — no new dependencies.

| Capability | Implementation |
|---|---|
| Read the 100-class taxonomy | `--taxonomy data/v3/taxonomy_100_proposed.json` |
| Recursive category traversal | BFS over `categorymembers`, cycle- and diamond-safe |
| Pagination / continuation | `query_all()` follows `continue`; **raises** rather than truncating |
| API batching | 50 titles per `imageinfo` request (MediaWiki anonymous cap) |
| Per-file metadata | page id, title, URL, dimensions, MIME, size, SHA1 |
| Licence classification | seven strict buckets; restrictive modifiers matched first |
| Attribution | `Artist`, `Credit`, `AttributionRequired` preserved raw |
| Missing metadata | explicit `metadata_gaps` list per file |
| Cross-category overlap | one record per file, **all** category memberships retained |
| Retry / backoff | transport retries transient failures and `maxlag` |
| Offline mode | `--fixture` runs entirely from recorded responses |

### Strict licence buckets

`CC0_PD` · `CC_BY` · `CC_BY_SA` · `NC_RESTRICTED` · `ND_RESTRICTED` ·
`UNKNOWN_MISSING` · `OTHER_REVIEW`

Only the first three pass a **preliminary** screen, and CC BY-SA is separately
flagged `share_alike: true`. NC, ND, unknown and unrecognised files are never
auto-included.

Two deliberate safeguards:

1. **A declaration is not proof.** Every record carries
   `verification: "declared_only"` and `requires_human_review: true`.
2. **`usable_for_training` is hard-coded `false`** for every file, with a reason
   string. Licence plus category membership cannot make something "usable".

### Duplicate handling — what is and is not claimed

| Signal | Done? | Note |
|---|---|---|
| Unique page id / title | ✅ | One record per file regardless of category count |
| Normalised-title grouping | ✅ | Case and underscore variants |
| Commons-reported SHA1 grouping | ✅ | **Exact byte identity only**, from metadata |
| Perceptual / near-duplicate | ❌ | Needs image bytes — **not performed, never claimed** |

The manifest is a flat list keyed by `pageid` so a future hashing pass can
annotate records in place. Intended future fields: `phash`, `dhash`, `ahash`,
`near_duplicate_of`.

---

## 4. Documents and artifacts

| Path | Contents |
|---|---|
| `training/commons_audit.py` | The auditor |
| `tests/test_commons_audit.py` | 69 tests, all offline |
| `tests/fixtures/commons/demo_tree.json` | Recorded-shape fixture for an offline demo |
| `docs/COMMONS_MANIFEST_SCHEMA.md` | Manifest + summary schema, field by field |
| `docs/COMMONS_AUDIT_PIPELINE.md` | This document |

---

## 5. How to run the audit once network access is available

```bash
# 1. Install (stdlib only; nothing to add beyond the existing requirements)
python3 -m venv /tmp/venv && /tmp/venv/bin/pip install -r requirements.txt

# 2. Smoke-test one class first — do not start with all 100
/tmp/venv/bin/python training/commons_audit.py \
    --taxonomy data/v3/taxonomy_100_proposed.json \
    --only-class jalebi \
    --depth 2 \
    --out data/v3/commons_audit/smoke

# 3. If that succeeds, run the full taxonomy politely
export NUTRICARE_COMMONS_UA="NutriCare-CommonsAuditor/1.0 (dataset provenance audit; contact: <your-email>)"
/tmp/venv/bin/python training/commons_audit.py \
    --taxonomy data/v3/taxonomy_100_proposed.json \
    --depth 2 \
    --delay 1.0 \
    --out data/v3/commons_audit/full

# 4. Read the output
#    data/v3/commons_audit/full/COMMONS_AUDIT_REPORT.md
#    data/v3/commons_audit/full/commons_manifest.json
#    data/v3/commons_audit/full/commons_audit_summary.json
```

`--delay 1.0` keeps the request rate at roughly one call per second, which is
well within Wikimedia's expectations alongside a descriptive User-Agent.

### Offline demo (works now, no network)

```bash
/tmp/venv/bin/python training/commons_audit.py \
    --taxonomy <small taxonomy>.json \
    --fixture tests/fixtures/commons/demo_tree.json \
    --depth 2 --out /tmp/commons_demo
```

### Network requirements to request

Both must be allowlisted, at TLS level and not just DNS:

```
commons.wikimedia.org     # action API: category tree + per-file metadata
upload.wikimedia.org      # image bytes and 512px thumbnails
```

Estimated first-run cost: one metadata-only pass over ~100 classes recursed to
depth 2. Files are fetched in batches of 50, so a corpus of tens of thousands of
files is a few hundred requests, not tens of thousands.

---

## 6. Storage planning

Disk available: **~20 GB**.

This phase stores **JSON only** — kilobytes to a few megabytes.

Future image collection should target **512px thumbnails**, not originals. The
tool reports a projection, clearly labelled an estimate because no image has been
inspected:

| Metric | Estimate |
|---|---|
| Per 512px thumbnail | 60–150 KB |
| 20,000 files | ~1.2–2.9 GiB |

That figure is in `summary.storage_estimate` and is labelled
`"basis": "estimate, not measurement"`. It must be recomputed from real
thumbnails after access is approved.

---

## 7. Honest status against the goal

The goal is 100 Indian food classes with traceable provenance, appropriate
licensing, and defensible labels.

**This phase does not move the class count.** It builds the instrument that will
produce trustworthy per-file evidence, and it replaces guesswork with a
reproducible process.

What is established:

- The pipeline is correct against recorded API shapes, including the failure
  modes that usually corrupt dataset counts (silent pagination truncation,
  double-counting files across overlapping categories, treating a category name
  as a licence).
- Licence classification is conservative: restrictive modifiers win, and
  nothing is auto-included on an uploader's say-so.

What is **not** established, and must not be implied:

- That Commons can supply 100 classes. The existing research suggests it cannot,
  and this phase added no evidence either way.
- That any specific image is usable, relevant, or correctly labelled.
- That any licence position is legally settled.

The next blocker is network access. Until `commons.wikimedia.org` **and**
`upload.wikimedia.org` are reachable, no further factual progress on dataset size
is possible — only more tooling, which has diminishing value compared with real
measurement.
