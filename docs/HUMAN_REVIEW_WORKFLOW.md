# Human review workflow — Biryani pilot

How to inspect the sampled Biryani images and record relevance and quality
judgements **before** any future training decision.

---

## What this workflow is, and is not

**Is:** a controlled way for a human to look at real Commons images and record
whether each one is actually biryani, whether it looks usable, and whether it has
problems (watermark, collage, possible duplicate).

**Is not:** permission to train on anything. Every stored decision carries
`usable_for_training: false`, unconditionally. There is no flag, option or code
path that changes it.

---

## 1. Current status — what worked and what was blocked

| Step | Status |
|---|---|
| Sample selection (10 of 93 records) | ✅ Works |
| Thumbnail **URL** resolution | ✅ Works — 10/10 resolved from the live Commons API |
| Image **bytes** into the sandbox | ❌ **Blocked** |
| Review page rendering | ✅ Works (self-contained HTML) |
| Decision storage + validation | ✅ Works |

### The blocker, precisely

```
$ curl https://upload.wikimedia.org/.../512px-Mutton_Biryani.jpg
curl: (35) OpenSSL SSL_connect: SSL_ERROR_SYSCALL
```

Both `upload.wikimedia.org` and `thumb.wikimedia.org` fail at the TLS handshake
from the sandbox. DNS resolves; TCP connects; the handshake is dropped. Unchanged
from previous phases.

### Why the workflow still functions

**Nothing is downloaded into this repository.** The review page contains
`<img src="https://thumb.wikimedia.org/...">` tags, so the **reviewer's browser**
fetches the thumbnails from Wikimedia when they open the page. That is an
ordinary page view of a Wikimedia-hosted file — the same thing that happens when
anyone reads a Commons page — not a bulk download and not a proxy.

If a thumbnail fails to load, the card still shows the Commons page link, the
licence, the artist and the dimensions, so review can continue.

**Still unverified:** whether those thumbnails actually render in your browser.
I could not confirm this from the sandbox. The URL pattern is correct — an
independent image search successfully retrieved a `thumb.wikimedia.org/.../960px-`
URL during this session — but the final visual check is yours.

---

## 2. The sample

`data/v3/commons_pilot/review/review_sample.json` — **10 records**, hard-capped.

Selection is deterministic and **licence-diverse**: it walks the manifest ordered
by Commons page id and picks round-robin across declared licence classes,
rarest first. That guarantees the two CC0 files and the CC BY files appear, even
though they are a tiny minority of the 93.

| Licence class | In sample |
|---|---|
| `CC_BY_SA` | 6 |
| `CC_BY` | 2 |
| `CC0_PD` | 2 |

Each entry records page id, SHA1, title, Commons page URL, declared licence,
artist, dimensions, categories, and a `thumbnail` block with the source URL,
`retrieval_status`, and `retrieved_utc`.

`retrieval_status` is one of:

| Value | Meaning |
|---|---|
| `url_resolved_not_downloaded` | Thumbnail URL known; bytes never fetched by this tool |
| `url_unresolved` | No URL available — **never invented** |
| `blocked` | API unreachable from this environment |

The sample also stores `source_manifest_sha256`, so anyone can prove the source
metadata was not mutated during sampling.

---

## 3. Using the review page

Open `data/v3/commons_pilot/review/review_page.html` in a browser.

For each of the 10 images you see the thumbnail, Commons title, page link,
declared licence, whether attribution is required, the artist, and the original
dimensions. Then:

- **Relevance** — `relevant` / `irrelevant` / `uncertain`
- **Quality** — `good` / `acceptable` / `poor`
- **Flags** — possible duplicate, watermark/branding, collage/multiple dishes
  (tri-state: checked, unchecked, untouched — untouched is *not* the same as
  "no", and is stored as `null`)
- **Notes** — free text

Click **Export decisions JSON** to download `review_export.json`. Use **Open last
export** to reload a previous export back into the page.

Progress is shown as `n / 10 reviewed`.

### Turning an export into the authoritative record

Browser state is not a record. The versioned file is. Feed the export through
the store:

```python
from training.review_store import ReviewStore
import json

store = ReviewStore("data/v3/commons_pilot/review")
for d in json.load(open("review_export.json"))["decisions"]:
    if not d["relevance"]:
        continue                      # skip untouched cards
    store.record(
        d["pageid"],
        relevance=d["relevance"],
        quality=d["quality"],
        review_notes=d.get("review_notes", ""),
        **{k: v for k, v in (d.get("flags") or {}).items() if v is not None},
    )
store.save()
```

This writes `data/v3/commons_pilot/review/review_decisions.json`.

---

## 4. Storage separation — the rule that matters

| File | Written by | Contains |
|---|---|---|
| `biryani_manifest.json` | `build_biryani_pilot.py` | Commons source metadata (93 records) |
| `review_sample.json` | `review_sample.py` | 10-record projection of the above |
| `review_decisions.json` | `review_store.py` | **Human judgements only** |

`review_store.py` will not write to the sample or manifest. A test hashes
`review_sample.json` before and after a full review cycle and asserts it is
byte-identical — the guarantee is enforced, not just documented.

Consequences:
- Source metadata can always be re-derived from Commons.
- Human judgement can always be attributed to a person and a timestamp.
- Neither can silently contaminate the other.

---

## 5. Licensing posture

- **A declared licence is not verified permission.** Every record keeps
  `verification: "declared_only"` from the Commons audit.
- **Attribution is preserved** — artist, licence and Commons page URL travel with
  every image into the review page.
- **Nothing is legally cleared.** Decisions store
  `legal_clearance: "not_verified"`.
- **Human approval does not grant training permission.** Marking an image
  `relevant` + `good` still yields `usable_for_training: false`, with the reason
  recorded alongside it.
- The CC BY-SA share-alike / model-weights question remains **open for legal
  review** and is untouched by this workflow.

---

## 6. Rebuilding

```bash
# 1. Sample (offline, from the recorded fixture — 10/10 thumbnails resolve)
python3 training/review_sample.py --limit 10 --transport mock \
    --fixture tests/fixtures/commons/thumbinfo_mock.json

#    With live network available, resolve URLs straight from Commons:
python3 training/review_sample.py --limit 10 --transport auto

# 2. Review page
python3 training/render_review_page.py --review-dir data/v3/commons_pilot/review

# 3. Tests
python -m pytest tests/test_review_workflow.py -q
```

`--transport none` builds the sample with no URL resolution at all, which is the
honest default when neither the sandbox nor a fixture is available.

---

## 7. What remains unverified

- **Whether the 10 thumbnails render** in a real browser (see §1).
- The visual content of every image — **no human has looked at these yet.** The
  relevance/quality fields are empty and waiting.
- Whether any image is **legally cleared** — still not determined.
- Perceptual duplicate detection — needs image bytes.
- Everything beyond the 10-image sample: **83 of the 93 pilot records are
  unreviewed**, and ~720 of the 813 biryani file-slots were never fetched.
