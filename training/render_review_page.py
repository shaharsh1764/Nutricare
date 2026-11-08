#!/usr/bin/env python3
"""Render a static, offline-first human review page for the Biryani sample.

The page is a single self-contained HTML file. It shows each sampled image's
thumbnail, Commons title, page link, declared licence, artist and dimensions,
with controls for relevance, quality, and the review flags.

Thumbnails are loaded **by the reviewer's browser directly from Wikimedia**, not
from this repository: no image bytes are stored here, and nothing depends on the
sandbox being able to reach Wikimedia. If the browser cannot load a thumbnail
the page says so and still shows the Commons page link, so review can continue.

Decisions made in the page can be exported as JSON and fed into
``training/review_store.py`` so the authoritative record stays in a versioned
file rather than in browser state.

Usage
-----
    python training/render_review_page.py \
        --review-dir data/v3/commons_pilot/review \
        --out data/v3/commons_pilot/review/review_page.html
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from training.review_store import FLAG_KEYS, QUALITY_LABELS, RELEVANCE_LABELS, ReviewStore  # noqa: E402

FLAG_LABELS = {
    "possible_duplicate": "Possible duplicate",
    "watermark_or_branding": "Watermark / branding",
    "collage_or_multiple_dishes": "Collage / multiple dishes",
}


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _card(index: int, row: Dict[str, Any]) -> str:
    image = row["image"]
    decision = row["decision"] or {}
    licence = image.get("licence") or {}
    attribution = image.get("attribution") or {}
    thumb = image.get("thumbnail") or {}

    thumb_url = thumb.get("url") or ""
    status = thumb.get("retrieval_status", "")

    if thumb_url:
        thumb_html = (
            f'<img class="thumb" src="{_esc(thumb_url)}" alt="{_esc(image.get("title"))}" '
            f'loading="lazy" referrerpolicy="no-referrer" '
            f'onerror="this.style.display=\'none\';document.getElementById(\'thumbfail{index}\').style.display=\'block\'">'
            f'<div class="thumbfail" id="thumbfail{index}">Thumbnail could not be loaded in '
            f"this browser. Use the Commons page link below to view the file.</div>"
        )
    else:
        thumb_html = (
            '<div class="thumbfail" style="display:block">No thumbnail URL resolved for '
            "this record. Use the Commons page link below to view the file.</div>"
        )

    flags_html = []
    for key in FLAG_KEYS:
        stored = (decision.get("flags") or {}).get(key)
        checked = "checked" if stored is True else ""
        flags_html.append(
            f'<label class="flag"><input type="checkbox" data-pageid="{image["pageid"]}" '
            f'data-flag="{key}" {checked}> {_esc(FLAG_LABELS[key])}</label>'
        )

    def radio(name: str, value: str, stored: Optional[str]) -> str:
        checked = "checked" if stored == value else ""
        return (
            f'<label class="opt"><input type="radio" name="{name}-{image["pageid"]}" '
            f'value="{value}" data-pageid="{image["pageid"]}" data-field="{name}" '
            f'{checked}> {value}</label>'
        )

    return f"""
    <article class="card" data-pageid="{image['pageid']}" data-title="{_esc(image.get('title'))}"
             data-sha1="{_esc(image.get('sha1'))}">
      <div class="media">{thumb_html}</div>
      <div class="meta">
        <h2>{index}. {_esc(image.get('title'))}</h2>
        <p class="links">
          <a href="{_esc(image.get('description_url'))}" target="_blank" rel="noopener noreferrer">Commons page &rarr;</a>
          <span class="pageid">pageid {image['pageid']}</span>
        </p>
        <dl>
          <dt>Declared licence</dt><dd>{_esc(licence.get('short_name') or '—')}
            <span class="class">({_esc(licence.get('declared_class'))})</span></dd>
          <dt>Attribution required</dt><dd>{_esc(licence.get('attribution_required'))}
            <span class="hint">[{_esc(licence.get('attribution_required_source'))}]</span></dd>
          <dt>Artist</dt><dd>{_esc(attribution.get('artist_raw') or '—')}</dd>
          <dt>Dimensions</dt><dd>{_esc(image.get('width'))} &times; {_esc(image.get('height'))} px</dd>
          <dt>Categories</dt><dd>{_esc(', '.join(image.get('categories') or []))}</dd>
        </dl>
        <p class="warn">Declared licence only &mdash; not verified permission. Not legally cleared.</p>

        <fieldset>
          <legend>Relevance</legend>
          {''.join(radio('relevance', v, decision.get('relevance')) for v in RELEVANCE_LABELS)}
        </fieldset>
        <fieldset>
          <legend>Quality</legend>
          {''.join(radio('quality', v, decision.get('quality')) for v in QUALITY_LABELS)}
        </fieldset>
        <fieldset>
          <legend>Flags</legend>
          {''.join(flags_html)}
        </fieldset>
        <label class="notes">Notes
          <textarea data-pageid="{image['pageid']}" data-field="review_notes"
                    rows="2">{_esc(decision.get('review_notes', ''))}</textarea>
        </label>
        <p class="elig">usable_for_training: <strong>false</strong> &mdash; review cannot grant training permission.</p>
      </div>
    </article>"""


def render(review_dir: Path) -> str:
    store = ReviewStore(review_dir)
    sample = store.sample
    rows = list(__import__("training.review_store", fromlist=["iter_rows"]).iter_rows(store))
    cards = "".join(_card(i + 1, row) for i, row in enumerate(rows))

    blocked = sample.get("retrieval_blocked_reason") or ""
    banner = (
        f'<div class="banner"><strong>Image bytes were not downloaded by the pipeline.</strong> '
        f"{_esc(blocked)}</div>"
        if blocked
        else ""
    )

    rows_json = json.dumps(
        [
            {
                "pageid": r["image"]["pageid"],
                "title": r["image"].get("title"),
                "sha1": r["image"].get("sha1"),
                "relevance": (r["decision"] or {}).get("relevance") or None,
                "quality": (r["decision"] or {}).get("quality") or None,
                "flags": (r["decision"] or {}).get("flags") or {},
                "review_notes": (r["decision"] or {}).get("review_notes") or "",
                "usable_for_training": False,
            }
            for r in rows
        ]
    )

    return ("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NutriCare — Biryani pilot human review</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 0; padding: 24px;
         background: #f7f7f5; color: #1a1a1a; }
  header { max-width: 1100px; margin: 0 auto 20px; }
  h1 { font-size: 1.4rem; margin: 0 0 6px; }
  .sub { color: #555; font-size: .9rem; margin: 0; }
  .banner { background: #fff6e0; border: 1px solid #e0b34a; padding: 10px 12px;
             border-radius: 8px; margin: 14px 0; font-size: .88rem; }
  .card { display: grid; grid-template-columns: minmax(220px, 320px) 1fr; gap: 18px;
           background: #fff; border: 1px solid #ddd; border-radius: 10px; padding: 16px;
           margin: 0 auto 16px; max-width: 1100px; }
  .thumb { width: 100%; height: auto; border-radius: 6px; background: #eee; }
  .thumbfail { display: none; background: #eee; border-radius: 6px; padding: 24px 12px;
                font-size: .82rem; color: #555; }
  h2 { font-size: .95rem; margin: 0 0 6px; word-break: break-word; }
  .links { margin: 0 0 10px; font-size: .82rem; display: flex; gap: 12px; flex-wrap: wrap; }
  .pageid { color: #777; }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: 3px 12px;
        font-size: .82rem; margin: 0 0 10px; }
  dt { color: #666; }
  dd { margin: 0; word-break: break-word; }
  .class, .hint { color: #888; font-size: .78rem; }
  .warn { color: #8a5a00; font-size: .78rem; margin: 0 0 10px; }
  fieldset { border: 1px solid #e2e2e2; border-radius: 8px; margin: 0 0 8px; padding: 6px 10px; }
  legend { font-size: .78rem; color: #666; padding: 0 4px; }
  .opt, .flag { font-size: .82rem; margin-right: 12px; white-space: nowrap; }
  .notes { display: block; font-size: .78rem; color: #666; }
  textarea { width: 100%; font: inherit; font-size: .82rem; box-sizing: border-box;
              border: 1px solid #ddd; border-radius: 6px; padding: 6px; }
  .elig { font-size: .78rem; color: #666; margin: 8px 0 0; }
  .toolbar { position: sticky; bottom: 0; background: #fffffff2; border-top: 1px solid #ddd;
              padding: 12px; max-width: 1100px; margin: 0 auto; display: flex; gap: 12px;
              align-items: center; flex-wrap: wrap; }
  button { font: inherit; padding: 8px 14px; border-radius: 8px; border: 1px solid #bbb;
            background: #fff; cursor: pointer; }
  button.primary { background: #1f6feb; border-color: #1f6feb; color: #fff; }
  #status { font-size: .82rem; color: #555; }
</style>
</head>
<body>
<header>
  <h1>Biryani pilot &mdash; human review</h1>
  <p class="sub">{sample_size} sampled records from the Commons metadata manifest.
     Relevance and quality are human judgements; they are stored separately from source metadata.</p>
  {banner}
</header>
{cards}
<div class="toolbar">
  <button class="primary" id="export">Export decisions JSON</button>
  <button id="openjson">Open last export</button>
  <span id="status"></span>
</div>
<script>
const rows = __ROWS_JSON__;

function collect() {
  const out = {};
  rows.forEach(r => {
    out[r.pageid] = {pageid: r.pageid, title: r.title, sha1: r.sha1,
      relevance: null, quality: null, flags: {}, review_notes: "", usable_for_training: false};
  });
  document.querySelectorAll('input[type=radio]:checked').forEach(el => {
    const p = el.dataset.pageid, f = el.dataset.field;
    if (out[p]) out[p][f] = el.value;
  });
  document.querySelectorAll('input[type=checkbox]').forEach(el => {
    const p = el.dataset.pageid;
    if (out[p]) out[p].flags[el.dataset.flag] = el.checked;
  });
  document.querySelectorAll('textarea').forEach(el => {
    const p = el.dataset.pageid;
    if (out[p]) out[p].review_notes = el.value;
  });
  return Object.values(out);
}

function refresh() {
  const done = collect().filter(d => d.relevance).length;
  document.getElementById("status").textContent = done + " / " + rows.length + " reviewed";
}
document.addEventListener("change", refresh);
document.addEventListener("input", refresh);
refresh();

document.getElementById("export").onclick = () => {
  const payload = {
    schema_version: "1.0",
    exported_from: "review_page.html",
    note: "Human decisions. Source metadata is unchanged. usable_for_training is false for every record.",
    decisions: collect()
  };
  const blob = new Blob([JSON.stringify(payload, null, 1)], {type: "application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "review_export.json";
  a.click();
  URL.revokeObjectURL(a.href);
};

document.getElementById("openjson").onclick = () => {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "application/json";
  input.onchange = e => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = ev => {
      try {
        const data = JSON.parse(ev.target.result);
        const decisions = data.decisions || data;
        if (!Array.isArray(decisions)) throw new Error("expected a decisions array");
        decisions.forEach(d => {
          (d.flags ? Object.entries(d.flags) : []).forEach(([k, v]) => {
            const box = document.querySelector('input[data-pageid="' + d.pageid + '"][data-flag="' + k + '"]');
            if (box) box.checked = !!v;
          });
          ["relevance", "quality"].forEach(field => {
            if (!d[field]) return;
            const el = document.querySelector('input[data-pageid="' + d.pageid + '"][data-field="' + field + '"][value="' + d[field] + '"]');
            if (el) el.checked = true;
          });
          const ta = document.querySelector('textarea[data-pageid="' + d.pageid + '"]');
          if (ta && d.review_notes) ta.value = d.review_notes;
        });
        refresh();
        document.getElementById("status").textContent += " — loaded";
      } catch (err) {
        alert("Could not read decisions: " + err.message);
      }
    };
    reader.readAsText(file);
  };
  input.click();
};
</script>
</body>
</html>
""").replace("__ROWS_JSON__", rows_json).replace("{cards}", cards).replace(
        "{banner}", banner
    ).replace("{sample_size}", str(len(rows)))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Render the human review page.")
    parser.add_argument("--review-dir", default="data/v3/commons_pilot/review")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    review_dir = Path(args.review_dir)
    out = Path(args.out) if args.out else review_dir / "review_page.html"
    out.write_text(render(review_dir), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
