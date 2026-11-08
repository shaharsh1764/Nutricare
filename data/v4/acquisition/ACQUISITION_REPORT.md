# V2 Dataset Acquisition V1 — Report

**Date:** 2026-11-05
**Branch:** `arena/9235252f-nutricare` (base: merged `main` at `3e368ae`, including PR #8)
**Status:** **No image bytes were acquired.** 0 usable images. This report explains
exactly why, what was verified instead, and what unblocks the task.

I am stating the headline first because it is the one number that must not be
softened: **0 images were downloaded.** Everything below is measured, and where
I could not measure something I say so rather than estimating it.

---

## 1. Why the count is zero

The sandbox has no general internet access. I measured this rather than assuming
it, with a TLS probe (`training/acquire_v2.py --probe`), and re-confirmed it
through the `huggingface_hub` library:

| Host | Result |
|---|---|
| `commons.wikimedia.org` | **UNREACHABLE** — `SSLZeroReturnError: TLS/SSL connection has been closed` |
| `upload.wikimedia.org` | **UNREACHABLE** — same TLS closure |
| `huggingface.co` | **UNREACHABLE** — same; `huggingface_hub` retried 5× and failed |
| `raw.githubusercontent.com` | **UNREACHABLE** — same |
| `codeload.github.com` | reachable |

DNS resolves correctly (`commons.wikimedia.org` → `198.35.26.224`, tried over
IPv4 as well), so this is a firewall blocking egress, not a resolver or IPv6
problem. Machine-readable evidence: `data/v4/acquisition/source_probe.json`.

I also tested the one out-of-sandbox channel I have (my documented web-fetch
tooling). It **can** read the Commons API — every seed in this repo came through
it — but it returns **text only**. When I pointed it at an image URL it returned
Wikimedia's HTML error page, not pixel data:

> `fetch_page("https://upload.wikimedia.org/.../Biryani.jpg")` → *"Wikimedia Error"*

So there is no route from here to image bytes. Rather than fabricate a pipeline
result, I recorded the zero.

## 2. Sources discovered

| # | Source | Reachable? | Per-image licence? | Verdict |
|---|---|---|---|---|
| 1 | **Wikimedia Commons** (API + `upload.wikimedia.org`) | API: yes (out-of-sandbox fetch only). Bytes: **no** | **Yes** — `LicenseShortName`, `Artist`, `AttributionRequired`, `Restrictions` per file | **Only compliant source.** Blocked for bytes. |
| 2 | `gnpaone/Indian-food-classification` (GitHub, 412 MB) | **Yes** (`codeload`) | **No** | **REJECTED** — see §3 |
| 3 | `iamsouravbanerjee/indian-food-images-dataset` (Kaggle) | no | unreadable | Rejected — upstream of #2, licence never verifiable |
| 4 | `Chethumuniraju/indian-food-classification` | yes | no | Rejected — duplicate of #2 |
| 5 | `Koushik1s/RASOI` | yes | no | Rejected — YOLO annotations only, no rights file |
| 6 | `Snigdha-Sinha/IndianFoodDataset` | yes | no | Rejected — scraped from archanaskitchen.com / bawarchi.com; repo has GPL-3.0, which **does not licence the photographs** |
| 7 | Hugging Face Indian-food datasets | **no** | varies | Rejected — host blocked; see `docs/HF_INDIAN_DATASETS_AUDIT.md` |
| 8 | PyPI packages (`indian-food-dataset`, etc.) | host reachable | n/a | None exist (404) |

GitHub repository search for Indian-food image sets returned only small
user-uploaded scrapes. `food101` was **not** used: those are Western dishes and
would not serve a 100-class *Indian* taxonomy.

## 3. The one dataset that *was* downloadable — and why I refused it

This is the crux of the task, so I want it on the record.

`codeload.github.com` is reachable, and I confirmed real image bytes are
obtainable there. I downloaded the archive and inspected it:

- **4,004 `*.jpg` files across 80 class folders** — genuinely Indian dishes,
  pan-regional, and they decode.
- The archive contains **only images, class folders and a README**. There is
  **no per-image licence, no author, no source URL, no annotation file**.

The README cites its origin as
`kaggle.com/datasets/iamsouravbanerjee/indian-food-images-dataset`, and states
*"4020 images belonging to 80 different classes."*

That is **exactly the Google-scraped 80-class dataset the task explicitly
forbids**, already documented and rejected in `docs/DATASET_AUDIT_V2.md` §2.4.
So despite being the only reachable source of real Indian food pixels, it fails
on every right-preservation requirement in the brief:

- no licence name or URL per image,
- no author or attribution,
- no permission/restriction metadata,
- no original source URL or identifier.

Adopting it would mean treating a repository's silence as permission. **I
discarded the archive and counted 0 images from it.** I did not weaken the
licence policy to hit a number — which is what taking these 4,004 files would
have been.

## 4. What I did instead: real, rights-checked coverage

Since the blocker is transport, I built the missing component and used it to
produce genuine, verifiable groundwork rather than another strategy document.

### 4.1 New: `training/acquire_v2.py` (the missing middle)

`collect_v2.py` ends with *"Never downloads image bytes"*; `prepare_v2_dataset.py`
can verify and split local bytes — but **nothing in the repo ever wrote bytes to
disk**. That hole is now filled. It reuses PR #8 unchanged:

| Concern | Delegated to |
|---|---|
| Rights tiering | `licence_policy.classify_rights` (PR #8, incl. the C-1a/C-1b fixes) |
| Metadata shape | `commons_audit.build_file_record` |
| Decode / dHash / near-dup | `prepare_v2_dataset.check_image_bytes`, `dhash_from_path`, `hamming` |

New behaviour is only: transfer, and then **prove what landed matches what was
described** — declared byte size must match exactly, the file must decode, and a
thumbnail URL is never accepted as the image.

### 4.2 Discovered candidates: 40 records, 7 classes

`data/v4/acquisition/commons_seeds.json` — real Commons metadata (page IDs,
sizes, SHA-1s, original URLs, licences, authors) for the classes that have
permissively-licensed files. Class-by-class attempt:
`data/v4/acquisition/ACQUISITION_ATTEMPT.md`.

| class | discovered | rights_approved | awaiting review | downloaded | **final usable** |
|---|---|---|---|---|---|
| biryani | 9 | 9 | 9 | 0 | **0** |
| naan | 9 | 7 | 9 | 0 | **0** |
| jalebi | 7 | 1 | 7 | 0 | **0** |
| gulab_jamun | 6 | 6 | 6 | 0 | **0** |
| samosa | 5 | 4 | 5 | 0 | **0** |
| idli | 3 | 1 | 3 | 0 | **0** |
| dosa | 1 | 0 | 1 | 0 | **0** |
| **total** | **40** | **28** | **40** | **0** | **0** |

`rights_approved` is a *licence* judgement. It is **not** a visual confirmation
that the photo shows the dish, and it is **not** a training count.
`final_usable` is 0 because nothing has bytes and nothing has been reviewed.

### 4.3 Coverage against the 100-class target

Measured (previously, via the same out-of-sandbox route) in
`data/v4/coverage_100.json`, and re-confirmed here on specific classes:

- 97/100 classes have a measured Commons category; 2 (`masala_dosa`,
  `matar_paneer`) have **no** category at all; 4 categories are empty.
- 8,270 direct file slots across the taxonomy — but that is a **file count**, not
  a usable-image count.
- Of 18 categories with a permissive-licence measurement, the total is
  **147 candidate files** — concentrated in Naan (30), Biryani (19), Roti (12).
- **Dosa: 1 permissive file. Dhokla: 0.** I queried `Category:Dhokla` with
  `haslicense:unrestricted` and got an empty result set.

So the 5,000-image target is **not** achievable from Commons under these rights
rules even with uninterrupted network. This needs to be said plainly: Commons
alone cannot supply 5,000 strictly-licensed Indian food images across 100
classes.

## 5. Quality findings that matter even at zero download

Reviewing the metadata already exposed label problems, which is why label
verification must stay separate from licence verification:

- **`Zoolbia Bamieh`** (a Persian/Lebanese sweet) filed under **Jalebi**.
- **`Making bread in Armote`** (an Armenian village scene) filed under **Naan**.
- **`Food Indian butter chicken`** filed under **Naan**.
- **`MyPlate gov Cultural Food`** (a USDA promotional plate) filed under **Naan**.
- **`Sanna` / `Sanna Dukra mass`** (Mangalorean Catholic idli-analogue, and a
  mass scene) filed under **Idli**.

Category membership is a *candidate* label, nothing more. A permissive licence
never implies the dish is correct.

The rights pipeline is also visibly conservative in ways that cost recall:
10 records were held because `Public domain` (generic) is **not** treated as
equivalent to CC0, and 2 because a `Restrictions: personality` value is
unclassified. That is the PR #8 policy working as designed — I did not loosen it
to gain images.

## 6. Whether an initial training subset is ready

**No.** 0 images exist on disk. There is nothing to train on.

I did not start training, and per the brief I am not recommending a training run.
The 12-class fallback is untouched: `models/food_classifier_cc0.pt` sha256 is
still `f74d10f6efe6a7848870b16388d56a570086901afa11d6ed78e7cd914f02ad87`.

## 7. Storage and compute (for when bytes are available)

Estimates, labelled as estimates:

- Commons originals here run 0.1–13 MB, many at 4896×3672. A 5,000-image set at
  ~2 MB mean ≈ **10 GB** raw; resized to 512 px on the short edge ≈ **0.6 GB**.
- `data/v4/images/` and `data/raw/` are already git-ignored, so images stay out
  of Git.
- Training a 100-class model from a frozen backbone on ~5,000 images is roughly
  **1–3 hours on a single mid-range GPU**; the compute is not the blocker.

## 8. Remaining blockers

1. **Egress (hard blocker).** Wikimedia and Hugging Face are firewalled from the
   sandbox, and the out-of-sandbox fetch tool returns text, not pixels. Bytes need
   either a network allowlist for `upload.wikimedia.org` or a run on a machine
   with normal internet.
2. **Supply (structural).** Even with access, Commons offers ~147
   permissively-licensed candidates across ~18 measured categories, with some
   classes at 0–1. Reaching 5,000 needs additional compliant sources — e.g.
   direct photographer/CC-archive outreach, Openverse/ Flickr CC harvesting with
   per-image licence capture, or the Indian regional datasets the brief lists,
   each audited per image.
3. **Human review (not started).** Legitimately 0 reviewed. No label has been
   visually confirmed.
4. **Label contamination.** The mislabels in §5 will need explicit exclusion or
   relabelling once bytes are inspectable.

## 9. Tests

- `tests/test_acquire_v2.py` — **31 tests, all passing.** They drive the real
  functions with genuine PNG bytes; none is a mock of the thing under test.
- Full suite: **1,039 passed, 7 skipped, 3 failed, 4 errored** — and **0
  non-vision failures**. The 3 failures + 4 errors are all `tests/test_vision.py`,
  which needs torch, and torch is not installed in this container. They are
  unrelated to this change.
- Mutation-tested my own new code: 6 mutants (declared-size check removed,
  undecodable file kept, thumbnail guard removed, network failure miscounted as a
  quality rejection, auto-approval, `final_usable` derived from downloads) —
  **6/6 killed.** One initially survived (`plan_record`'s pending status was
  untested); I added `test_plan_record_also_starts_pending` and it now fails.

## 10. Honest summary

| Question | Answer |
|---|---|
| Sources discovered | 8 (Commons + 5 GitHub/Kaggle + HF + PyPI) |
| Actually usable | **1** (Wikimedia Commons — but unreachable for bytes) |
| Downloaded images | **0** |
| Usable images, any class | **0** |
| Rights-approved candidates | 28 records (no bytes, unreviewed) |
| Human review progress | 0 of 40 |
| Coverage vs 100 classes | 7 classes have candidates; 2 classes have no Commons category at all |
| Initial training subset ready | **No** |
| Remaining blockers | network egress; ~147-file Commons ceiling; review; label contamination |

I did not fabricate counts, did not substitute advertised dataset totals for
verified usable ones, did not treat a repo's silence as a licence, and did not
lower the rights bar to make the numbers look better. If a network allowlist for
`upload.wikimedia.org` is opened, `training/acquire_v2.py` is ready to run and
will populate `data/v4/images/` with fully traceable, size-verified bytes on the
first attempt.
