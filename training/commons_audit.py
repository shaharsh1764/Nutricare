#!/usr/bin/env python3
"""Audit Wikimedia Commons metadata for the NutriCare Indian-food taxonomy.

This tool builds a **verifiable, image-level metadata inventory** for the
proposed V3 taxonomy (``data/v3/taxonomy_100_proposed.json``). It talks only to
the MediaWiki action API and collects **metadata**, never image binaries.

What it does
------------
1. Reads the taxonomy and every ``commons_categories`` entry per class.
2. Recursively traverses those categories and their subcategories.
3. Handles API continuation correctly, so a category larger than one API page
   (``cmlimit``) is fully enumerated rather than silently truncated.
4. Collects per-file metadata: page id, title, page URL, image URL, licence,
   artist, attribution requirement, permission, dimensions, MIME type, SHA1.
5. Keeps every category a file belongs to, and therefore every class it maps
   to, so a file appearing in several categories is counted **once** as a file
   while its full membership is preserved.
6. Classifies each file's *declared* licence into a strict set of buckets.
7. Writes a manifest plus a Markdown/JSON audit report.

What it deliberately does NOT do
--------------------------------
* It never downloads image bytes, so no perceptual hashing happens here. The
  only duplicate signal available at this stage is the SHA1 that Commons itself
  reports (an exact-byte-identity signal) plus normalised filename comparison.
* It never marks a file "usable" or "training-ready". A suitable licence and a
  category membership say nothing about relevance, quality, label correctness,
  or uniqueness of the *depiction*. Those still need review.
* It makes no statement about whether CC BY-SA reaches trained model weights.
  That question is flagged for human/legal review, not resolved here.

Licence classification is of the **declared** licence only. An uploader's
declaration is not proof of ownership, so every file carries
``licence.verification == "declared_only"`` and ``requires_human_review``.

Usage
-----
    python training/commons_audit.py \
        --taxonomy data/v3/taxonomy_100_proposed.json \
        --out data/v3/commons_audit \
        --depth 2

Offline self-test (no network at all):

    python training/commons_audit.py --fixture tests/fixtures/commons/demo_tree.json \
        --out /tmp/commons_demo

Network policy note: Wikimedia asks for a descriptive User-Agent with contact
details. Set ``--user-agent`` (or ``NUTRICARE_COMMONS_UA``) before running
against the live API.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

API_HOST = "commons.wikimedia.org"
API_PATH = "/w/api.php"
API_URL = f"https://{API_HOST}{API_PATH}"
IMAGE_HOST = "upload.wikimedia.org"
DEFAULT_UA = (
    "NutriCare-CommonsAuditor/1.0 (dataset provenance audit; "
    "https://github.com/shaharsh1764/Nutricare) python-urllib"
)

# MediaWiki caps anonymous `titles=` batches at 50.
MAX_TITLES_PER_REQUEST = 50
DEFAULT_PAGE_SIZE = 500

IIPROP = "url|size|mime|mediatype|sha1|extmetadata|canonicaltitle"

# ---------------------------------------------------------------------------
# Licence classification
# ---------------------------------------------------------------------------

#: Declared-licence buckets. Ordered from most to least permissive for our use.
CC0_PD = "CC0_PD"
CC_BY = "CC_BY"
CC_BY_SA = "CC_BY_SA"
NC_RESTRICTED = "NC_RESTRICTED"
ND_RESTRICTED = "ND_RESTRICTED"
UNKNOWN_MISSING = "UNKNOWN_MISSING"
OTHER_REVIEW = "OTHER_REVIEW"

#: Buckets that pass a *preliminary* licence screen. This is not legal advice
#: and not a clearance: it means "the declared licence does not obviously
#: forbid commercial reuse of the image".
PRELIMINARILY_ACCEPTABLE = frozenset({CC0_PD, CC_BY, CC_BY_SA})

#: Purposefully ordered: a restrictive modifier wins over a permissive base.
_RE_NC = re.compile(r"(cc[- ]?by[- ]?nc|\bby-nc\b|non[- ]?commercial|\bnc\b)")
_RE_ND = re.compile(r"(cc[- ]?by[- ]?nd|\bby-nd\b|no[- ]?deriv|noderivs|no derivatives)")
_RE_SA = re.compile(r"(cc[- ]?by[- ]?sa|\bby-sa\b|share[- ]?alike|sharealike)")
_RE_CC0 = re.compile(
    r"(cc0|cc[- ]zero|public domain|publicdomain|^\s*pd\b|\bpd[- ]|no known copyright|no restrictions)"
)
_RE_CCBY = re.compile(r"(cc[- ]?by[- ]?\d|cc[- ]by\b|\bby \d|\bby\b|attribution)")
_RE_NONFREE = re.compile(
    r"(fair[- ]?use|non[- ]?free|all rights reserved|copyrighted|used with permission)"
)
_RE_GFDL = re.compile(r"(gfdl|gpl|fal)")

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_markup(value: Optional[str]) -> str:
    """Flatten an extmetadata HTML fragment to plain text."""
    if not value:
        return ""
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", str(value)))).strip()


def em(extmetadata: Optional[Dict[str, Any]], key: str) -> str:
    """Return a stripped extmetadata value, tolerating absent/malformed keys."""
    if not extmetadata:
        return ""
    entry = extmetadata.get(key)
    if isinstance(entry, dict):
        return strip_markup(entry.get("value"))
    if entry is None:
        return ""
    return strip_markup(str(entry))


def classify_licence(extmetadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Classify the *declared* licence of one file.

    Deliberately does not verify the uploader's ownership, and does not resolve
    the share-alike/model-weights question. Restrictive modifiers are checked
    before permissive bases so ``CC BY-NC-SA`` can never be mistaken for
    ``CC BY-SA``.
    """
    short = em(extmetadata, "LicenseShortName")
    usage = em(extmetadata, "UsageTerms")
    licence_field = em(extmetadata, "License")
    licence_url = em(extmetadata, "LicenseUrl")
    attribution_required = em(extmetadata, "AttributionRequired").lower() == "true"
    restrictions = em(extmetadata, "Restrictions")

    signals = " ".join(x for x in (short, usage, licence_field) if x).lower()
    review_reason = ""

    if not signals.strip():
        if em(extmetadata, "Copyrighted"):
            review_reason = "no machine-readable licence field; Copyrighted flag present"
        else:
            review_reason = "no licence field present in extmetadata"
        declared = UNKNOWN_MISSING
    elif _RE_NC.search(signals):
        declared = NC_RESTRICTED
        review_reason = "non-commercial restriction: not usable in a commercial product"
    elif _RE_ND.search(signals):
        declared = ND_RESTRICTED
        review_reason = "no-derivatives restriction: blocks modification/augmentation"
    elif _RE_NONFREE.search(signals):
        declared = OTHER_REVIEW
        review_reason = "declared as non-free / fair use / all rights reserved"
    elif _RE_CC0.search(signals):
        declared = CC0_PD
    elif _RE_SA.search(signals):
        declared = CC_BY_SA
        review_reason = "share-alike: may impose obligations on derived artefacts"
    elif _RE_CCBY.search(signals):
        declared = CC_BY
    elif _RE_GFDL.search(signals):
        declared = OTHER_REVIEW
        review_reason = "copyleft documentation licence; compatibility not assessed"
    else:
        declared = OTHER_REVIEW
        review_reason = f"unrecognised licence string: {short or signals[:80]!r}"

    if restrictions:
        review_reason = (review_reason + "; " if review_reason else "") + (
            f"Commons Restrictions field present: {restrictions}"
        )

    return {
        "declared_class": declared,
        "short_name": short,
        "licence_url": licence_url,
        "usage_terms": usage,
        "attribution_required": attribution_required,
        # A declaration is never proof. Every file needs a human look.
        "verification": "declared_only",
        "requires_human_review": True,
        "preliminarily_acceptable": declared in PRELIMINARILY_ACCEPTABLE,
        "share_alike": declared == CC_BY_SA,
        "review_reason": review_reason,
    }


# ---------------------------------------------------------------------------
# Errors and transport
# ---------------------------------------------------------------------------


class CommonsAPIError(RuntimeError):
    """An API call failed. ``retryable`` drives the backoff loop."""

    def __init__(self, message: str, *, retryable: bool = False, code: str = ""):
        super().__init__(message)
        self.retryable = retryable
        self.code = code


class HttpTransport:
    """Minimal urllib transport with retry/backoff.

    Kept as a class so tests can substitute a recording/failing double without
    any network access.
    """

    def __init__(
        self,
        user_agent: str = DEFAULT_UA,
        *,
        timeout: float = 30.0,
        max_attempts: int = 4,
        backoff: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.backoff = backoff
        self._sleep = sleep

    def __call__(self, params: Dict[str, Any]) -> Dict[str, Any]:
        url = API_URL + "?" + urllib.parse.urlencode(params, doseq=True)
        request = urllib.request.Request(
            url, headers={"User-Agent": self.user_agent, "Accept": "application/json"}
        )
        last_error: Optional[Exception] = None
        for attempt in range(self.max_attempts):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:  # 429/5xx are worth retrying
                last_error = exc
                if exc.code not in (429, 500, 502, 503, 504):
                    raise CommonsAPIError(f"HTTP {exc.code} from Commons API", code=str(exc.code))
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                # Includes TLS handshake failures (SSL_ERROR_SYSCALL) seen when
                # the sandbox egress proxy drops the connection.
                last_error = exc
            except json.JSONDecodeError as exc:
                last_error = exc
            if attempt + 1 < self.max_attempts:
                self._sleep(self.backoff ** attempt)
        raise CommonsAPIError(
            f"Commons API unreachable after {self.max_attempts} attempts: {last_error}",
            retryable=True,
        )


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------


class CommonsClient:
    """Thin MediaWiki action-API client with continuation and retry."""

    def __init__(
        self,
        transport: Callable[[Dict[str, Any]], Dict[str, Any]],
        *,
        page_size: int = DEFAULT_PAGE_SIZE,
        maxlag: int = 5,
        max_pages: int = 500,
        delay: float = 0.0,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 4,
        backoff: float = 2.0,
    ):
        self._transport = transport
        self.page_size = page_size
        self.maxlag = maxlag
        self.max_pages = max_pages
        self.delay = delay
        self._sleep = sleep
        self.max_attempts = max_attempts
        self.backoff = backoff
        self.call_count = 0

    # -- low level ---------------------------------------------------------
    def query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """One API call, retrying maxlag/readonly and transient failures."""
        payload = {"format": "json", "formatversion": "2", "maxlag": self.maxlag}
        payload.update(params)
        last: Optional[Exception] = None
        for attempt in range(self.max_attempts):
            if self.delay:
                self._sleep(self.delay)
            self.call_count += 1
            try:
                response = self._transport(payload)
            except CommonsAPIError as exc:
                if not exc.retryable:
                    raise
                last = exc
            else:
                if "error" in response:
                    code = str(response["error"].get("code", ""))
                    if code in ("maxlag", "readonly", "ratelimited") and attempt + 1 < self.max_attempts:
                        last = CommonsAPIError(
                            f"API returned {code}", retryable=True, code=code
                        )
                    else:
                        raise CommonsAPIError(
                            f"API error {code}: {response['error'].get('info', '')}".strip(),
                            code=code,
                        )
                else:
                    return response
            if attempt + 1 < self.max_attempts:
                self._sleep(self.backoff ** attempt)
        raise CommonsAPIError(f"API call failed after retries: {last}", retryable=True)

    def query_all(self, params: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        """Yield every page of a listing, following ``continue`` correctly."""
        cont: Dict[str, Any] = {}
        pages = 0
        while True:
            request = dict(params)
            request.update(cont)
            response = self.query(request)
            pages += 1
            yield response
            cont = response.get("continue") or {}
            if not cont:
                return
            if pages >= self.max_pages:
                raise CommonsAPIError(
                    f"pagination exceeded {self.max_pages} pages; refusing to truncate silently"
                )

    # -- domain helpers ----------------------------------------------------
    def category_members(self, category: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Return (file members, subcategory names) for one category, fully paginated."""
        title = category if category.lower().startswith("category:") else f"Category:{category}"
        files: List[Dict[str, Any]] = []
        subcats: List[str] = []
        for response in self.query_all(
            {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": title,
                "cmtype": "file|subcat",
                "cmlimit": self.page_size,
            }
        ):
            for member in response.get("query", {}).get("categorymembers", []):
                ns = member.get("ns")
                name = member.get("title", "")
                if ns == 14:  # Category namespace
                    subcats.append(name.split(":", 1)[-1])
                elif ns == 6:  # File namespace
                    files.append({"title": name, "pageid": member.get("pageid")})
        return files, subcats

    def category_info(self, categories: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        """Direct file/subcategory counts for categories (``prop=categoryinfo``)."""
        info: Dict[str, Dict[str, Any]] = {}
        for batch in _batched(list(categories), MAX_TITLES_PER_REQUEST):
            titles = [
                c if c.lower().startswith("category:") else f"Category:{c}" for c in batch
            ]
            response = self.query(
                {"action": "query", "prop": "categoryinfo", "titles": "|".join(titles)}
            )
            query = response.get("query", {})
            normalized = _normalization_map(query)
            by_title = {
                page.get("title"): page for page in _pages(query) if page.get("title")
            }
            for requested in titles:
                resolved = normalized.get(requested, requested)
                page = by_title.get(resolved)
                short = requested.split(":", 1)[-1]
                if page is None or page.get("missing"):
                    info[short] = {"exists": False, "files": 0, "subcats": 0}
                else:
                    ci = page.get("categoryinfo", {}) or {}
                    info[short] = {
                        "exists": True,
                        "files": int(ci.get("files", 0)),
                        "subcats": int(ci.get("subcats", 0)),
                        "pages": int(ci.get("pages", 0)),
                    }
        return info

    def file_info(self, titles: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        """Per-file metadata for up to 50 titles per request.

        Returns ``{requested_title: page_dict}``. Titles that do not resolve are
        returned with a ``missing`` marker rather than dropped, so callers can
        record the gap.
        """
        result: Dict[str, Dict[str, Any]] = {}
        for batch in _batched(list(titles), MAX_TITLES_PER_REQUEST):
            response = self.query(
                {
                    "action": "query",
                    "prop": "imageinfo",
                    "iiprop": IIPROP,
                    "titles": "|".join(batch),
                }
            )
            query = response.get("query", {})
            normalized = _normalization_map(query)
            by_title = {
                page.get("title"): page for page in _pages(query) if page.get("title")
            }
            for requested in batch:
                page = by_title.get(normalized.get(requested, requested))
                if page is None:
                    result[requested] = {"title": requested, "missing": True}
                else:
                    result[requested] = page
        return result


def _pages(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return page objects, tolerating both formatversion 1 (dict) and 2 (list)."""
    pages = query.get("pages", [])
    if isinstance(pages, dict):
        return list(pages.values())
    return list(pages or [])


def _normalization_map(query: Dict[str, Any]) -> Dict[str, str]:
    """Map API-normalised (and redirected) titles back to the canonical title."""
    mapping: Dict[str, str] = {}
    for entry in query.get("normalized", []) or []:
        if entry.get("from") and entry.get("to"):
            mapping[entry["from"]] = entry["to"]
    for entry in query.get("redirects", []) or []:
        if entry.get("from") and entry.get("to"):
            mapping[entry["from"]] = entry["to"]
    return mapping


def _batched(items: List[Any], size: int) -> Iterator[List[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def normalize_title(title: str) -> str:
    """Normalise a Commons title for dedupe: '' namespace, single spaces, lowercase."""
    text = (title or "").replace("_", " ").strip()
    text = _WS_RE.sub(" ", text)
    return text.lower()


# ---------------------------------------------------------------------------
# Traversal
# ---------------------------------------------------------------------------


@dataclass
class CategoryNode:
    name: str
    depth: int
    parent: Optional[str]
    files: List[str] = field(default_factory=list)
    subcats: List[str] = field(default_factory=list)
    exists: bool = True


def traverse_categories(
    client: CommonsClient,
    roots: Sequence[str],
    *,
    depth: int = 2,
    max_categories: int = 4000,
) -> Tuple[Dict[str, CategoryNode], List[str]]:
    """Breadth-first traversal of ``roots`` and their subcategories.

    Returns ``(nodes, warnings)``. Cycles and diamond inheritance are handled by
    visiting each category once; ``parent`` records the first path that reached
    it. Traversal is bounded by ``depth`` and ``max_categories`` and warns when
    a bound truncates the walk rather than silently returning partial data.
    """
    warnings: List[str] = []
    nodes: Dict[str, CategoryNode] = {}
    queue: List[Tuple[str, int, Optional[str]]] = [(r, 0, None) for r in roots]
    while queue:
        name, level, parent = queue.pop(0)
        if name in nodes:
            continue
        if len(nodes) >= max_categories:
            warnings.append(
                f"max_categories={max_categories} reached; traversal truncated at {name!r}"
            )
            break
        files, subcats = client.category_members(name)
        nodes[name] = CategoryNode(
            name=name, depth=level, parent=parent,
            files=[f["title"] for f in files], subcats=subcats,
        )
        if level < depth:
            for sub in subcats:
                if sub not in nodes:
                    queue.append((sub, level + 1, name))
        elif subcats:
            warnings.append(
                f"{name!r} has {len(subcats)} subcategories not traversed (depth limit {depth})"
            )
    return nodes, warnings


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def _imageinfo(page: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    info = page.get("imageinfo")
    if isinstance(info, list):
        return info[0] if info else None
    if isinstance(info, dict):
        return info
    return None


def build_file_record(
    title: str,
    page: Dict[str, Any],
    categories: Iterable[str],
    classes: Iterable[str],
) -> Dict[str, Any]:
    """Assemble one manifest entry for a Commons file."""
    info = _imageinfo(page) or {}
    extmetadata = info.get("extmetadata") or {}
    licence = classify_licence(extmetadata)

    artist_raw = em(extmetadata, "Artist")
    credit = em(extmetadata, "Credit")
    permission = em(extmetadata, "Permission")

    gaps: List[str] = []
    if page.get("missing") or not info:
        gaps.append("no_imageinfo")
    if licence["declared_class"] == UNKNOWN_MISSING:
        gaps.append("missing_licence")
    if not artist_raw:
        gaps.append("missing_artist")
    if not permission:
        gaps.append("missing_permission")
    if not info.get("url"):
        gaps.append("missing_image_url")
    if not info.get("width") or not info.get("height"):
        gaps.append("missing_dimensions")

    cats = sorted(set(categories))
    cls = sorted(set(classes))

    return {
        "pageid": page.get("pageid"),
        "title": page.get("title") or title,
        "normalized_title": normalize_title(page.get("title") or title),
        "sha1": info.get("sha1"),
        "url": info.get("url"),
        "description_url": info.get("descriptionurl"),
        "width": info.get("width"),
        "height": info.get("height"),
        "mime": info.get("mime"),
        "mediatype": info.get("mediatype"),
        "size_bytes": info.get("size"),
        "licence": licence,
        "attribution": {
            "artist_raw": artist_raw,
            "credit": credit,
            "attribution_required": licence["attribution_required"],
        },
        "permission": permission,
        "categories": cats,
        "classes": cls,
        "in_multiple_categories": len(cats) > 1,
        "in_multiple_classes": len(cls) > 1,
        "metadata_gaps": gaps,
        # Never inferred from licence + category membership.
        "usable_for_training": False,
        "usable_reason": "not assessed: relevance, quality, duplicates and label "
        "correctness require further inspection",
    }


def count_potential_band(count: int, *, unmeasured: bool = False) -> str:
    """Planning band for a candidate count. Not a training-readiness verdict."""
    if unmeasured or count <= 0:
        return "unknown_or_unassessed"
    if count >= 200:
        return "strong"
    if count >= 100:
        return "moderate"
    if count >= 50:
        return "limited"
    return "insufficient"


def run_audit(
    client: CommonsClient,
    taxonomy: Dict[str, Any],
    *,
    depth: int = 2,
    max_categories: int = 4000,
    max_files: Optional[int] = None,
    source_mode: str = "network",
) -> Dict[str, Any]:
    """Run the full metadata audit and return ``{"manifest","summary","warnings"}``."""
    classes = taxonomy.get("classes", [])
    warnings: List[str] = []

    # ---- 1. Map taxonomy classes to their Commons categories --------------
    class_categories: Dict[str, List[str]] = {}
    for entry in classes:
        slug = entry.get("slug")
        cats = [c for c in (entry.get("commons_categories") or []) if c]
        if not slug:
            warnings.append("taxonomy entry without slug skipped")
            continue
        class_categories[slug] = cats

    all_requested: List[str] = []
    for cats in class_categories.values():
        for cat in cats:
            if cat not in all_requested:
                all_requested.append(cat)

    if not all_requested:
        warnings.append("taxonomy declared no commons_categories; nothing to traverse")

    # ---- 2. Recursive traversal ------------------------------------------
    nodes, traversal_warnings = traverse_categories(
        client, all_requested, depth=depth, max_categories=max_categories
    )
    warnings.extend(traversal_warnings)

    # ---- 3. Category statistics ------------------------------------------
    category_stats = client.category_info(list(nodes.keys())) if nodes else {}

    root_stats = client.category_info(all_requested) if all_requested else {}
    categories_missing = [c for c, s in root_stats.items() if not s.get("exists")]

    # ---- 4. Which categories reach which classes -------------------------
    # A subcategory inherits every class of the root category that reached it.
    category_classes: Dict[str, set] = {c: set() for c in nodes}
    for slug, roots in class_categories.items():
        for root in roots:
            if root not in nodes:
                continue
            stack = [(root, 0)]
            seen = set()
            while stack:
                name, level = stack.pop()
                if name in seen or name not in nodes:
                    continue
                seen.add(name)
                category_classes[name].add(slug)
                node = nodes[name]
                if level < depth:
                    for sub in node.subcats:
                        stack.append((sub, level + 1))

    # ---- 5. Collect unique file titles with full membership --------------
    title_categories: Dict[str, set] = {}
    raw_category_file_sum = 0
    for name, node in nodes.items():
        raw_category_file_sum += len(node.files)
        for title in node.files:
            title_categories.setdefault(title, set()).add(name)

    if max_files is not None and len(title_categories) > max_files:
        keep = list(title_categories)[:max_files]
        warnings.append(
            f"max_files={max_files} reached: {len(title_categories)-len(keep)} files not audited"
        )
        title_categories = {t: title_categories[t] for t in keep}

    # ---- 6. Fetch per-file metadata --------------------------------------
    pages: Dict[str, Dict[str, Any]] = {}
    titles = list(title_categories)
    for batch in _batched(titles, MAX_TITLES_PER_REQUEST):
        pages.update(client.file_info(batch))

    records: List[Dict[str, Any]] = []
    for title in titles:
        cats = title_categories[title]
        classes_for_file: set = set()
        for cat in cats:
            classes_for_file |= category_classes.get(cat, set())
        page = pages.get(title) or {"title": title, "missing": True}
        records.append(build_file_record(title, page, cats, classes_for_file))

    # ---- 7. Aggregate ----------------------------------------------------
    licence_counts: Dict[str, int] = {}
    for record in records:
        key = record["licence"]["declared_class"]
        licence_counts[key] = licence_counts.get(key, 0) + 1

    gap_counts: Dict[str, int] = {}
    for record in records:
        for gap in record["metadata_gaps"]:
            gap_counts[gap] = gap_counts.get(gap, 0) + 1

    # Exact-byte duplicates via Commons-reported SHA1. No pixels are read.
    sha1_groups: Dict[str, List[str]] = {}
    for record in records:
        if record.get("sha1"):
            sha1_groups.setdefault(record["sha1"], []).append(record["title"])
    duplicate_sha1_groups = {k: v for k, v in sha1_groups.items() if len(v) > 1}

    norm_groups: Dict[str, List[str]] = {}
    for record in records:
        norm_groups.setdefault(record["normalized_title"], []).append(record["title"])
    duplicate_title_groups = {k: v for k, v in norm_groups.items() if len(v) > 1}

    # ---- 8. Per-class rollup ---------------------------------------------
    per_class: List[Dict[str, Any]] = []
    for entry in classes:
        slug = entry.get("slug")
        if slug is None:
            continue
        cats = class_categories.get(slug, [])
        members = [
            r for r in records if slug in r["classes"]
        ]
        acceptable = [
            r for r in members if r["licence"]["preliminarily_acceptable"]
        ]
        unacceptable = [
            r for r in members
            if r["licence"]["declared_class"] in (NC_RESTRICTED, ND_RESTRICTED, OTHER_REVIEW)
        ]
        unknown = [
            r for r in members if r["licence"]["declared_class"] == UNKNOWN_MISSING
        ]
        missing_attr = [
            r for r in members if "missing_artist" in r["metadata_gaps"]
        ]
        raw_sum = sum(len(nodes[c].files) for c in cats if c in nodes)

        # A category is "found" only if Commons reports it exists. Traversal
        # also creates a node for a nonexistent category (it simply has no
        # members), so node presence alone would wrongly count it as found.
        found = [c for c in cats if root_stats.get(c, {}).get("exists")]
        missing_cats = [c for c in cats if not root_stats.get(c, {}).get("exists")]
        unmeasured = not cats or (not found and not missing_cats)

        per_class.append(
            {
                "slug": slug,
                "canonical": entry.get("canonical", slug),
                "categories_requested": cats,
                "categories_found": found,
                "categories_missing": missing_cats,
                "raw_category_file_sum": raw_sum,
                "unique_files": len(members),
                "unique_files_acceptable_licence": len(acceptable),
                "files_nc_or_nd_or_other": len(unacceptable),
                "files_unknown_licence": len(unknown),
                "files_missing_attribution": len(missing_attr),
                "count_potential_by_unique_files": count_potential_band(
                    len(members), unmeasured=unmeasured
                ),
                "count_potential_by_acceptable_licence": count_potential_band(
                    len(acceptable), unmeasured=unmeasured
                ),
                "training_ready": False,
                "training_ready_reason": "count potential only; no relevance, quality, "
                "duplicate or label review has been performed",
            }
        )

    subcat_categories = [
        {"category": n, "subcategories": len(node.subcats), "depth": node.depth}
        for n, node in sorted(nodes.items())
        if node.subcats
    ]

    summary = {
        "tool": "training/commons_audit.py",
        "source_mode": source_mode,
        "counts_are": "metadata counts from the MediaWiki API; no image bytes downloaded",
        "categories": {
            "requested": len(all_requested),
            "requested_missing": sorted(categories_missing),
            "discovered_including_subcategories": len(nodes),
            "with_subcategories": len(subcat_categories),
            "max_depth_traversed": depth,
        },
        "files": {
            "raw_category_file_sum": raw_category_file_sum,
            "unique_file_titles": len(records),
            "overlap_entries_collapsed": raw_category_file_sum - len(records)
            if raw_category_file_sum >= len(records) else 0,
            "files_in_multiple_categories": sum(
                1 for r in records if r["in_multiple_categories"]
            ),
            "files_in_multiple_classes": sum(
                1 for r in records if r["in_multiple_classes"]
            ),
            "exact_sha1_duplicate_groups": len(duplicate_sha1_groups),
            "exact_sha1_duplicate_files": sum(
                len(v) for v in duplicate_sha1_groups.values()
            ),
            "duplicate_normalized_title_groups": len(duplicate_title_groups),
            "files_without_imageinfo": gap_counts.get("no_imageinfo", 0),
        },
        "licences": {
            "by_declared_class": licence_counts,
            "preliminarily_acceptable": sum(
                1 for r in records if r["licence"]["preliminarily_acceptable"]
            ),
            "unknown_or_unsuitable": sum(
                1
                for r in records
                if not r["licence"]["preliminarily_acceptable"]
            ),
            "note": "classification is of the DECLARED licence only; uploader "
            "declarations are not proof of ownership and no file is legally cleared",
        },
        "metadata_gaps": gap_counts,
        "per_class": per_class,
        "categories_with_subcategories": subcat_categories,
        "storage_estimate": estimate_storage(len(records)),
        "warnings": warnings,
        "unknowns": [
            "whether image binaries are downloadable from this environment",
            "image relevance to the labelled dish",
            "visual quality, framing and resolution adequacy",
            "perceptual/near-duplicate rate (needs image bytes)",
            "label correctness",
            "whether CC BY-SA obligations extend to model weights (legal review)",
            "contents of categories beyond the traversal depth",
        ],
    }

    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    return {"manifest": records, "summary": summary, "warnings": warnings}


def estimate_storage(file_count: int) -> Dict[str, Any]:
    """Rough future storage need at 512px thumbnail scale.

    These are **estimates** from typical Wikimedia thumbnail sizes, not
    measurements: no image has been downloaded.
    """
    low, high = 60 * 1024, 150 * 1024  # 60-150 KB per 512px JPEG (estimate)
    return {
        "basis": "estimate, not measurement",
        "images": file_count,
        "thumbnail_512px_bytes_low": file_count * low,
        "thumbnail_512px_bytes_high": file_count * high,
        "thumbnail_512px_gib_low": round(file_count * low / 1024**3, 3),
        "thumbnail_512px_gib_high": round(file_count * high / 1024**3, 3),
        "note": "assumes 512px thumbnails are fetched instead of originals; "
        "originals would be far larger. Recompute after image access is approved.",
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

_BAND_LABEL = {
    "strong": "200+ strong",
    "moderate": "100–199 moderate",
    "limited": "50–99 limited",
    "insufficient": "1–49 insufficient",
    "unknown_or_unassessed": "0 / unmeasured",
}


def render_markdown(summary: Dict[str, Any], *, title: str = "Commons metadata audit") -> str:
    """Render the audit summary as Markdown."""
    cat = summary["categories"]
    files = summary["files"]
    lic = summary["licences"]
    lines: List[str] = []
    add = lines.append

    add(f"# {title}")
    add("")
    add(f"**Source mode:** `{summary['source_mode']}` — {summary['counts_are']}.")
    add("")
    add("> **Nothing here is training-ready.** These are metadata counts. Image")
    add("> relevance, quality, perceptual duplicates and label correctness have not")
    add("> been inspected, and no file has been legally cleared.")
    add("")

    add("## 1. Categories")
    add("")
    add("| Metric | Value |")
    add("|---|---|")
    add(f"| Categories requested | {cat['requested']} |")
    add(f"| Categories discovered (incl. subcategories) | {cat['discovered_including_subcategories']} |")
    add(f"| Categories with subcategories | {cat['with_subcategories']} |")
    add(f"| Traversal depth | {cat['max_depth_traversed']} |")
    add(f"| Requested categories not found | {len(cat['requested_missing'])} |")
    add("")
    if cat["requested_missing"]:
        add("Not found: " + ", ".join(f"`{c}`" for c in cat["requested_missing"]))
        add("")

    add("## 2. File counts — raw versus unique")
    add("")
    add("| Metric | Value |")
    add("|---|---|")
    add(f"| Raw category-file sum (double-counts overlap) | {files['raw_category_file_sum']} |")
    add(f"| **Unique Commons files** | **{files['unique_file_titles']}** |")
    add(f"| Overlapping entries collapsed | {files['overlap_entries_collapsed']} |")
    add(f"| Files in more than one category | {files['files_in_multiple_categories']} |")
    add(f"| Files in more than one class | {files['files_in_multiple_classes']} |")
    add(f"| Exact-duplicate groups (Commons SHA1) | {files['exact_sha1_duplicate_groups']} |")
    add(f"| Files sharing a SHA1 with another file | {files['exact_sha1_duplicate_files']} |")
    add(f"| Files with no imageinfo | {files['files_without_imageinfo']} |")
    add("")
    add("The raw sum counts a file once per category it appears in, so it exceeds the")
    add("unique count whenever categories overlap. Only the unique figure is a file")
    add("count.")
    add("")

    add("## 3. Declared licences")
    add("")
    add("| Declared class | Files |")
    add("|---|---|")
    for key, value in sorted(lic["by_declared_class"].items(), key=lambda kv: -kv[1]):
        add(f"| `{key}` | {value} |")
    add(f"| **Preliminarily acceptable** | **{lic['preliminarily_acceptable']}** |")
    add(f"| **Unknown or unsuitable** | **{lic['unknown_or_unsuitable']}** |")
    add("")
    add("Classification reads the **declared** licence string. It does not verify the")
    add("uploader's ownership, and it does not decide whether CC BY-SA reaches model")
    add("weights — that is flagged for review. NC, ND, unknown and unrecognised files")
    add("are never included automatically.")
    add("")

    add("## 4. Metadata gaps")
    add("")
    if summary["metadata_gaps"]:
        add("| Gap | Files |")
        add("|---|---|")
        for key, value in sorted(summary["metadata_gaps"].items(), key=lambda kv: -kv[1]):
            add(f"| `{key}` | {value} |")
    else:
        add("No gaps recorded.")
    add("")

    add("## 5. Per-class count potential")
    add("")
    add("Bands are planning thresholds on **candidate counts**, not predictions of")
    add("training readiness.")
    add("")
    add("| Class | Unique files | Acceptable licence | Band (unique) | Band (licence) | Ready |")
    add("|---|---|---|---|---|---|")
    for row in summary["per_class"]:
        add(
            f"| {row['canonical']} | {row['unique_files']} | "
            f"{row['unique_files_acceptable_licence']} | "
            f"{_BAND_LABEL[row['count_potential_by_unique_files']]} | "
            f"{_BAND_LABEL[row['count_potential_by_acceptable_licence']]} | no |"
        )
    add("")

    add("## 6. Categories with subcategories")
    add("")
    if summary["categories_with_subcategories"]:
        add("| Category | Subcategories | Depth |")
        add("|---|---|---|")
        for row in summary["categories_with_subcategories"]:
            add(f"| {row['category']} | {row['subcategories']} | {row['depth']} |")
    else:
        add("None recorded.")
    add("")

    est = summary["storage_estimate"]
    add("## 7. Future storage estimate")
    add("")
    add(f"**{est['basis']}.** For {est['images']} images as 512px thumbnails:")
    add(f"~{est['thumbnail_512px_gib_low']}–{est['thumbnail_512px_gib_high']} GiB.")
    add("")
    add(est["note"])
    add("")

    add("## 8. Still unknown")
    add("")
    for item in summary["unknowns"]:
        add(f"- {item}")
    add("")

    if summary["warnings"]:
        add("## 9. Warnings raised during the run")
        add("")
        for item in summary["warnings"]:
            add(f"- {item}")
        add("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Fixture support (offline tests / demos)
# ---------------------------------------------------------------------------


class FixtureTransport:
    """Serve pre-recorded API responses so the tool runs without network.

    The fixture maps a query signature to a canned response. Continuation is
    modelled by ``page`` keys so pagination can be exercised offline.
    """

    def __init__(self, fixture: Dict[str, Any]):
        self.fixture = fixture
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append(dict(params))
        for rule in self.fixture.get("responses", []):
            if _fixture_matches(rule.get("match", {}), params):
                cont = params.get("cmcontinue") or params.get("continue") or ""
                pages = rule.get("pages")
                if isinstance(pages, list):
                    index = 0
                    if cont:
                        token = cont.replace("||", "")
                        index = int(token) if token.isdigit() else 0
                    if index >= len(pages):
                        raise CommonsAPIError(f"fixture has no page {index}")
                    return pages[index]
                response = rule.get("response", {})
                if rule.get("filter_pages"):
                    # Real API calls batch many titles; a recording may hold the
                    # union. Restrict the response to the titles requested.
                    response = _filter_pages_to_titles(response, params.get("titles", ""))
                return response
        raise CommonsAPIError(f"no fixture rule matched params: {sorted(params)}")


def _filter_pages_to_titles(response: Dict[str, Any], titles: str) -> Dict[str, Any]:
    """Return only the pages whose title was requested (respecting normalisation)."""
    wanted = {t for t in (titles or "").split("|") if t}
    if not wanted:
        return response
    query = response.get("query", {})
    normalized = _normalization_map(query)
    resolved = set()
    for title in wanted:
        resolved.add(normalized.get(title, title))
        resolved.add(title)

    pages = query.get("pages")
    if isinstance(pages, list):
        kept = [p for p in pages if p.get("title") in resolved]
        # Explicitly record the ones that were not found, so gaps stay visible.
        present = {p.get("title") for p in kept}
        for title in resolved - present:
            if not any(normalized.get(f) == title for f in present):
                kept.append({"title": title, "missing": True})
        return {"query": {**query, "pages": kept}}
    return response


def _fixture_matches(match: Dict[str, Any], params: Dict[str, Any]) -> bool:
    for key, expected in match.items():
        actual = params.get(key)
        if isinstance(expected, list):
            if actual is None or not any(e in str(actual) for e in expected):
                return False
        elif actual != expected:
            return False
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit Wikimedia Commons metadata for the NutriCare taxonomy "
        "(metadata only; no image downloads)."
    )
    parser.add_argument(
        "--taxonomy",
        default="data/v3/taxonomy_100_proposed.json",
        help="taxonomy JSON with per-class commons_categories",
    )
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--depth", type=int, default=2, help="subcategory recursion depth")
    parser.add_argument("--max-categories", type=int, default=4000)
    parser.add_argument("--max-files", type=int, default=None, help="cap files audited")
    parser.add_argument("--delay", type=float, default=0.0, help="seconds between API calls")
    parser.add_argument(
        "--user-agent",
        default=None,
        help="descriptive User-Agent (Wikimedia policy); or set NUTRICARE_COMMONS_UA",
    )
    parser.add_argument("--fixture", default=None, help="run from a recorded fixture instead of network")
    parser.add_argument("--only-class", action="append", default=None, help="restrict to these slugs")
    args = parser.parse_args(argv)

    with open(args.taxonomy, "r", encoding="utf-8") as handle:
        taxonomy = json.load(handle)

    if args.only_class:
        wanted = set(args.only_class)
        keep = [c for c in taxonomy.get("classes", []) if c.get("slug") in wanted]
        missing = wanted - {c.get("slug") for c in keep}
        if missing:
            print(f"error: unknown slug(s): {sorted(missing)}", file=sys.stderr)
            return 2
        taxonomy = dict(taxonomy, classes=keep)

    if args.fixture:
        with open(args.fixture, "r", encoding="utf-8") as handle:
            fixture = json.load(handle)
        client = CommonsClient(FixtureTransport(fixture), delay=0.0)
        source_mode = f"fixture:{args.fixture}"
    else:
        import os

        user_agent = args.user_agent or os.environ.get("NUTRICARE_COMMONS_UA") or DEFAULT_UA
        client = CommonsClient(HttpTransport(user_agent), delay=args.delay)
        source_mode = "network:commons.wikimedia.org"

    result = run_audit(
        client,
        taxonomy,
        depth=args.depth,
        max_categories=args.max_categories,
        max_files=args.max_files,
        source_mode=source_mode,
    )

    import os

    os.makedirs(args.out, exist_ok=True)
    manifest_path = os.path.join(args.out, "commons_manifest.json")
    summary_path = os.path.join(args.out, "commons_audit_summary.json")
    report_path = os.path.join(args.out, "COMMONS_AUDIT_REPORT.md")

    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "schema_version": "1.0",
                "source_mode": source_mode,
                "note": "Metadata only. No image bytes were downloaded. "
                "No file is verified, cleared or training-ready.",
                "files": result["manifest"],
            },
            handle,
            indent=2,
            ensure_ascii=False,
        )
        handle.write("\n")
    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(result["summary"], handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write(render_markdown(result["summary"]))

    files = result["summary"]["files"]
    lic = result["summary"]["licences"]
    print(
        f"categories={result['summary']['categories']['discovered_including_subcategories']} "
        f"unique_files={files['unique_file_titles']} "
        f"acceptable_licence={lic['preliminarily_acceptable']} "
        f"warnings={len(result['warnings'])}"
    )
    print(f"wrote {manifest_path}")
    print(f"wrote {summary_path}")
    print(f"wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
