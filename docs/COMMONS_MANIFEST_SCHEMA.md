# Commons metadata manifest schema (v1.0)

Defines the JSON contract produced by `training/commons_audit.py`. This phase
collects **metadata only** — no image binary is downloaded, hashed perceptually,
or inspected for relevance.

> **Nothing in this manifest is training-ready, verified, or legally cleared.**
> A record says a Commons file *page* exists, what it *declares* about its
> licence, and which categories reference it. It says nothing about whether the
> picture shows the right dish, is good enough, or is unique.

---

## Files

| File | Contents |
|---|---|
| `commons_manifest.json` | One record per unique Commons file (the inventory) |
| `commons_audit_summary.json` | Aggregate counts, per-class rollup, warnings, unknowns |
| `COMMONS_AUDIT_REPORT.md` | Human-readable rendering of the summary |

---

## `commons_manifest.json`

Top level:

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | string | `"1.0"` |
| `source_mode` | string | `network:commons.wikimedia.org` or `fixture:<path>` |
| `note` | string | Standing disclaimer about verification |
| `files` | array | File records, **one per unique file title** |

### File record

| Field | Type | Meaning |
|---|---|---|
| `pageid` | int \| null | MediaWiki page id; the stable identity of the file page |
| `title` | string | Canonical title, e.g. `File:Jalebi.jpg` |
| `normalized_title` | string | Case-folded, underscore-free title used for dedupe |
| `sha1` | string \| null | **Commons-reported** SHA1 of the file bytes |
| `url` | string \| null | Original image URL (recorded, **not fetched**) |
| `description_url` | string \| null | Commons file page URL, for attribution |
| `width`, `height` | int \| null | Pixel dimensions from `imageinfo` |
| `mime` | string \| null | MIME type, e.g. `image/jpeg` |
| `mediatype` | string \| null | `BITMAP`, `DRAWING`, `VIDEO`, … |
| `size_bytes` | int \| null | Original file size |
| `licence` | object | Declared-licence block (below) |
| `attribution` | object | `artist_raw`, `credit`, `attribution_required` |
| `permission` | string | The `Permission` field text (may be empty) |
| `categories` | string[] | **Every** Commons category this file was found in |
| `classes` | string[] | Every taxonomy slug those categories map to |
| `in_multiple_categories` | bool | `len(categories) > 1` |
| `in_multiple_classes` | bool | `len(classes) > 1` — needs a decision before splitting |
| `metadata_gaps` | string[] | Which required fields were missing (below) |
| `usable_for_training` | bool | **Always `false`** in this phase |
| `usable_reason` | string | Why it is not a usability verdict |

### `licence` block

| Field | Type | Meaning |
|---|---|---|
| `declared_class` | string | One of the seven buckets below |
| `short_name` | string | Raw `LicenseShortName` text |
| `licence_url` | string | Raw `LicenseUrl` |
| `usage_terms` | string | Raw `UsageTerms` |
| `attribution_required` | bool | From `AttributionRequired` |
| `verification` | string | Always `"declared_only"` |
| `requires_human_review` | bool | Always `true` |
| `preliminarily_acceptable` | bool | Passes the *preliminary* screen only |
| `share_alike` | bool | CC BY-SA present — **flagged, not resolved** |
| `review_reason` | string | Why review is needed |

#### Declared-licence buckets

| Bucket | Meaning | Auto-includable now? |
|---|---|---|
| `CC0_PD` | CC0 or public domain | preliminarily yes |
| `CC_BY` | CC BY any version | preliminarily yes |
| `CC_BY_SA` | CC BY-SA any version | preliminarily yes, **flagged** for share-alike review |
| `NC_RESTRICTED` | Non-commercial restriction | **never** |
| `ND_RESTRICTED` | No-derivatives restriction | **never** |
| `UNKNOWN_MISSING` | No licence field present | **never** |
| `OTHER_REVIEW` | Unrecognised, fair use, GFDL, all rights reserved | **never** |

Restrictive modifiers are matched **before** permissive bases, so
`CC BY-NC-SA` can never be mistaken for `CC BY-SA`.

#### `metadata_gaps` vocabulary

`no_imageinfo`, `missing_licence`, `missing_artist`, `missing_permission`,
`missing_image_url`, `missing_dimensions`.

---

## `commons_audit_summary.json`

| Section | Key fields |
|---|---|
| `categories` | `requested`, `requested_missing[]`, `discovered_including_subcategories`, `with_subcategories`, `max_depth_traversed` |
| `files` | `raw_category_file_sum`, `unique_file_titles`, `overlap_entries_collapsed`, `files_in_multiple_categories`, `files_in_multiple_classes`, `exact_sha1_duplicate_groups`, `exact_sha1_duplicate_files`, `duplicate_normalized_title_groups`, `files_without_imageinfo` |
| `licences` | `by_declared_class{}`, `preliminarily_acceptable`, `unknown_or_unsuitable`, `note` |
| `metadata_gaps` | `{gap_name: file_count}` |
| `per_class[]` | per-slug rollup, see below |
| `categories_with_subcategories[]` | `category`, `subcategories`, `depth` |
| `storage_estimate` | future 512px thumbnail projection (**labelled an estimate**) |
| `warnings` | every truncation or anomaly, never silent |
| `unknowns` | what the audit explicitly did **not** determine |

### `per_class[]` row

| Field | Meaning |
|---|---|
| `slug`, `canonical` | Taxonomy identity |
| `categories_requested` / `categories_found` / `categories_missing` | Mapping outcome |
| `raw_category_file_sum` | Sum over categories — **double-counts overlap** |
| `unique_files` | De-duplicated file count for this class |
| `unique_files_acceptable_licence` | Subset passing the preliminary licence screen |
| `files_nc_or_nd_or_other` | Excluded by restriction |
| `files_unknown_licence` | Missing licence — excluded |
| `files_missing_attribution` | No `Artist` field |
| `count_potential_by_unique_files` | `strong` / `moderate` / `limited` / `insufficient` / `unknown_or_unassessed` |
| `count_potential_by_acceptable_licence` | Same band, licence-filtered |
| `training_ready` | **Always `false`** |
| `training_ready_reason` | Why the band is not a readiness verdict |

### Count-potential bands

Planning thresholds on **candidate counts**, never on readiness:

| Band | Unique candidates |
|---|---|
| `strong` | 200+ |
| `moderate` | 100–199 |
| `limited` | 50–99 |
| `insufficient` | 1–49 |
| `unknown_or_unassessed` | 0 or unmeasured |

---

## Duplicate handling in this phase

| Signal | Performed? | Meaning |
|---|---|---|
| Unique page id / title | ✅ | One record per file page, regardless of how many categories reference it |
| Normalised-title grouping | ✅ | Catches case/underscore variants |
| Commons-reported SHA1 grouping | ✅ | **Exact byte identity only**, as reported by the API |
| Perceptual / near-duplicate | ❌ | Requires image bytes; **not performed** |
| Visual or label review | ❌ | **Not performed** |

The SHA1 grouping is an exact-identity signal from Commons metadata. It is *not*
pixel hashing and must not be described as perceptual deduplication.

### Forward path for perceptual dedupe

Once image access is approved, add `perceptual` fields to each record —
`phash`, `dhash`, `ahash`, `phash_cluster`, `near_duplicate_of` — and keep the
existing `sha1` untouched so exact identity remains traceable. The manifest is
deliberately a flat list keyed by `pageid`, so a hashing pass can annotate
records without restructuring.

---

## Design constraints

- **512px thumbnails by default.** Originals are recorded as URLs but the future
  fetch stage should request thumbnails (`iiurlwidth=512`) to fit ~20 GB.
- **Never silently truncate.** Depth, category and file limits all emit warnings.
- **Preserve licence strings verbatim.** Raw text is stored alongside the
  classification so a file can be re-bucketed later without re-fetching.
- **Attribution stays attached to the file**, so a future `ATTRIBUTIONS.md` can be
  generated from the manifest alone.
