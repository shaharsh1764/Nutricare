# Hugging Face Indian Food Dataset Audit

**Date:** 2026-11-07
**Purpose:** Determine whether Indian food image datasets can be obtained from
Hugging Face, and whether their images may lawfully be used for training and for
shipping a derivative model.
**Status:** Research only. **No training has run. No images downloaded.**

---

## 0. Two separate access questions

These are often confused, so they are answered separately:

| Question | Answer |
|---|---|
| Can the **Arena sandbox** reach `huggingface.co`? | **No.** Blocked at TLS. Evidence in §1. |
| Can I **read HF dataset cards and metadata**? | **Yes** — via my research/web tooling, which runs outside the sandbox. All figures below come from that. |
| Did I **download any images**? | **No.** Not possible from the sandbox, and not attempted through workarounds. |

This means the dataset cards, licences, class lists and image counts below are
**verified from Hugging Face itself**, but the *pixels* have not been inspected.
That distinction matters for §4 and I have kept it explicit.

---

## 1. Direct access test (sandbox → Hugging Face)

Not a guess — measured:

```
huggingface.co                        000
hf.co                                 000
datasets-server.huggingface.co        000
cdn-lfs.huggingface.co                000
cdn-lfs-us-1.hf.co                    000
cas-bridge.xethub.hf.co               000
transfer.xethub.hf.co                 000
xethub.hf.co                          000
```

The failure mode is specific and rules out a DNS or IPv6 problem:

```
$ curl -4 -sv https://huggingface.co/api/datasets
*   Trying 99.86.101.56:443...
* Connected to huggingface.co (99.86.101.56) port 443 (#0)
* ALPN: offers h2,http/1.1
* TLSv1.3 (OUT), TLS handshake, Client hello (1):
* OpenSSL SSL_connect: SSL_ERROR_SYSCALL in connection to huggingface.co:443
```

TCP connects, the TLS `ClientHello` goes out, then the connection is dropped.
IPv4 and IPv6 both fail identically; GitHub works fine from the same shell. This
is an **SNI-level egress filter**, i.e. a network policy, not something code can
fix. `git ls-remote https://huggingface.co/...` fails the same way
(`gnutls_handshake() failed`), so no alternate HTTPS route exists.

I did not attempt to bypass, tunnel, or proxy around it — that would be
circumventing a deliberate control.

---

## 2. Candidate datasets found

| # | Dataset | Licence declared | Classes | Images | Splits | Real photos? |
|---|---|---|---|---|---|---|
| 1 | `bharat-raghunathan/indian-foods-dataset` | **CC0-1.0** | 15 | 4,770 (3,809 train / 961 test) | train, test | Yes — but **Google-scraped** |
| 2 | `SohlHealth/enhanced-indian-food-classification` | **CC-BY-4.0** | 43 | **15,404** | train, val, test | Stated yes; **provenance not documented** |
| 3 | `kidKrish/...` (duplicate of #2) | CC-BY-4.0 | 43 | same | same | mirror — no independent value |
| 4 | `rajistics/indian_food_images` | **none declared** | 20 | ~5.3k | — | **Google-extracted**, self-admitted |
| 5 | `shardulkamde/indian-foods-dataset` | CC0-1.0 | 15 | duplicate of #1 | — | mirror |
| 6 | `Codatta/MM-Food-100K` | OpenRAIL-M | 100k rows | global, not Indian | — | **non-commercial** — unsuitable |
| 7 | `ethz/food101` | **unknown / not owned by ETHZ** | 101 | 101,000 | — | images belong to Foodspotting users |

Others surfaced by search (`SunnyAgarwal4274/Food_and_Vegetables`, stock-market
and recipe-text datasets) are **not Indian food photographs** and are excluded —
ingredients/fruits or text corpora, not dishes.

---

## 3. Dataset-by-dataset findings

### 3.1 `bharat-raghunathan/indian-foods-dataset` — the one you named

**Verified from the dataset card:**

- Licence: `cc0-1.0` (tag + explicit "CC0: Public Domain").
- Splits: train 3,809 / test 961 → **4,770 images**. Your reported figure was
  right.
- 15 classes: `biryani, cholebhature, dabeli, dal, dhokla, dosa, jalebi,
  kathiroll, kofta, naan, pakora, paneer, panipuri, pavbhaji, vadapav`.
- Images resized to 300×300.
- Origin: `kaggle.com/datasets/anshulmehtakaggl/themassiveindianfooddataset`.

**The card states its own collection method:**

> "Collection by Scraping data from Google Images + Leveraging some JS Functions."

This is the decisive fact. A CC0 dedication is only valid if the dedicator
actually holds the rights. Google Image results are overwhelmingly third-party
photographs; a scraper cannot transfer rights it never had. So the CC0 label is a
**publisher declaration, not a verified chain of title** — the same conclusion
already recorded for the Bangladeshi dataset in `docs/LICENSING_AUDIT.md` §5.2.

**Coverage value: low.** Of its 15 classes, **13 are already in NutriCare's
existing 70-slug taxonomy**; only `dabeli` and `kofta` would be new. Training to
add 2 classes is a poor use of the remaining time.

### 3.2 `SohlHealth/enhanced-indian-food-classification` — the most substantial

**Verified:**

- Licence: `cc-by-4.0`.
- **15,404 images across 43 classes**; card figure and the per-class statistics
  file agree exactly (I summed all 43 class counts myself: 15,404 — match).
- Files: 5 parquet shards, ~2.1 GB total (train ×3, validation, test).
- Class counts range **130 – 811**.
- Classes span curries, breads, rice, snacks, sweets, drinks, chutneys.

**Problems found, all verifiable from the repo:**

1. **No provenance statement at all.** The card says only "CC-BY-4.0" and
   nothing about where the images came from, who curated them, or on what basis
   the uploader may license them. There is no source URL, no collection method,
   no attribution file.
2. **Internal inconsistency.** `dataset_info.json` calls it an *"Indian Food
   Detection Dataset … with YOLO annotations"*, sets `"task": "object-detection"`,
   and records `"total_images": 0` — while the card and statistics describe a
   15,404-image *classification* set. Both cannot be right.
3. **Signs of multi-source consolidation.** The statistics file names its label
   map `unified_classes`, implying several source datasets were merged. If so, a
   single CC-BY grant from one uploader cannot cover images whose rights sit
   with other parties.
4. **Suspicious uniformity.** **14 of 43 classes have exactly 200 images.**
   Round numbers like that usually mean a cap was applied, or augmented copies
   were added to reach a target. Your brief explicitly forbids counting
   augmented images as independent photographs, so this must be checked on the
   real files before any split — a class of 200 augmented-from-50 is not a class
   of 200 photographs.
5. **Account is new and thin** (2 likes, ~254 downloads, created 2025). Less
   concerning than the above, but it is not an institution.

**Verdict:** the most useful dataset available, and CC-BY-4.0 at least *permits*
derivative works with attribution — but the licence grant rests on an uploader
whose basis for granting it is undocumented. I would not ship a model on it
without §6 being resolved.

### 3.3 `rajistics/indian_food_images` — rejected

Self-described: *"All the images are extracted from google."* No licence field
at all. 20 classes, ~5.3k images. Same rights problem as §3.1 with no licence
claim to weigh, and 17 of 20 classes already covered.

### 3.4 `Codatta/MM-Food-100K` — rejected

OpenRAIL-M, **non-commercial only**, and global rather than Indian. A
commercial-use restriction conflicts with shipping in NutriCare. Excluded on the
same principle as Khana.

### 3.5 `ethz/food101` — rejected

Its own card is unusually candid: the images *"are not property of the Federal
Institute of Technology Zurich (ETHZ). Any use beyond scientific fair use must
be negotiated with the respective picture owners."* Not Indian either. Excluded.

---

## 4. Can these images lawfully be used to train and ship a derivative model?

| Dataset | Train? | Ship derivative model? | Why |
|---|---|---|---|
| `bharat-raghunathan` (CC0) | Legally plausible | Plausible, **but grant is unsupported** | CC0 permits both; however images were Google-scraped, so the dedicator likely lacked the rights to grant |
| `SohlHealth` (CC-BY-4.0) | Yes, with attribution | Yes, with attribution + notice | CC-BY-4.0 explicitly permits derivatives and commercial use; **provenance is the open risk, not the licence text** |
| `rajistics` | No | No | No licence; Google-extracted |
| `Codatta` | Non-commercial only | No | OpenRAIL-M |
| `ethz/food101` | Scientific fair use only | No | ETHZ disclaims ownership |

Two honest caveats:

- **A licence tag is a claim, not a title deed.** This is the position already
  taken in `THIRD_PARTY_NOTICES.md` for the CC0 models. A permissive tag on a
  scraped set does not cure a defective chain of title.
- **I have not seen the pixels.** Everything in §3 is from cards, metadata and
  file listings. Contamination (watermarks, stock photos, collages, brand
  packaging) — which I *did* find in the GitHub-hosted Indian set — cannot be
  ruled out here. It must be measured before training, using the audit script
  already written (`training/audit_indian_dataset.py`).

---

## 5. Coverage against the 150-class target

| Source | Classes | Already in NutriCare | Genuinely new |
|---|---|---|---|
| `bharat-raghunathan` | 15 | 13 | **2** |
| `SohlHealth` | 43 | 29 | **14** |
| Both combined (deduped) | ~58 | ~31 | **~16** |

Realistic ceiling from all reachable, plausibly-licensed Indian sources:
**~58 Indian classes total**, of which ~16 would be new work. **150 is not
reachable**, and 120 Indian is not either. Adding the 30 international classes
would need Food-101-style data, whose licensing is worse, not better.

Exact new-class candidates from `SohlHealth`: `aloo_masala, chicken_curry,
coconut_chutney, dum_aloo, fish_curry, ghevar, green_chutney, gulab_jamun,
kebab, lassi, modak, mutton_curry, ras_malai, shahi_paneer`.

---

## 6. What access is needed, and how to transfer an approved archive

### Option A — unblock Hugging Face (recommended, cheapest)

Allowlist **all** of these; blocking only `huggingface.co` is not enough, because
image bytes are served from the CDN:

```
huggingface.co
cdn-lfs.huggingface.co
cdn-lfs-us-1.hf.co
cas-bridge.xethub.hf.co
transfer.xethub.hf.co
```

The parquet shards are 258–633 MB, so the CDN hosts are mandatory. With these
open I can download, audit the real pixels, dedupe, split and train — the whole
pipeline already exists.

### Option B — transfer via GitHub (works today, with a size catch)

`codeload.github.com` is reachable, and I have admin rights on
`shaharsh1764/Nutricare`. Practical constraint: **`objects.githubusercontent.com`
is blocked**, so GitHub *Release assets* cannot be downloaded by me. A file
committed into a repository tree *can* be fetched via codeload.

Limits to respect:

- GitHub rejects individual files over **100 MB**. The train shards would have to
  be split into ~100 MB parts and reassembled by checksum.
- Bulk image data should not be committed to the project repo. Use a **separate
  scratch repository** for the transfer, then delete it.
- Even then, ~2.1 GB of parquet through a git repo is slow and fragile.

**My recommendation: Option A.** Option B is a fallback that works but is
genuinely awkward at this volume.

### Option C — you verify provenance

Fastest route to a *defensible* decision, independent of transfer: check whether
`SohlHealth` states its sources anywhere (a linked GitHub repo, paper, or
Kaggle origin). If the images trace to a source with an explicit image-level
licence, the CC-BY grant stops being unsupported and this becomes the right
dataset to build on.

---

## 7. Recommendation

**Do not train yet.** My recommendation, in priority order:

1. **Prefer `SohlHealth` over the CC0 15-class set** — 43 classes vs 15, and only
   14 genuinely new either way, but far better class diversity (curries, chutneys,
   drinks, sweets). CC-BY-4.0 permits training, derivatives and commercial use;
   the blocker is undocumented provenance, not the licence text.
2. **Treat the `bharat-raghunathan` CC0 as a supplementary set at most.** Two new
   classes do not justify a training run, and its own card admits Google scraping.
3. **Resolve provenance before shipping a model.** Ask for Option A access or
   Option C verification.
4. **Keep the 12-class CC0 model as the shipped default** until a new model beats
   it on an independent test set with a clean provenance record.

If you want to proceed on the CC-BY dataset with the provenance caveat
documented as a known risk — the same disclosure style already used for the CC0
models — say so explicitly and I will start with the pixel audit (not training),
report contamination and per-class counts, and then train only if the data
survives that audit.

---

## 8. Explicit statements

- **No training has been performed** for V2 on any Indian dataset.
- **No images were downloaded** from Hugging Face; the sandbox cannot reach it.
- **No accuracy figure is claimed** anywhere in this report.
- The 80-class Kaggle-derived GitHub set remains **unused**, as you instructed.
- The existing 12-class model is **untouched** and still the default.
