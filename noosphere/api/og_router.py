"""OG card rendering for social sharing of corpora and documents.

Each shareable URL surface (corpus / single document) gets an OG card sized
1200×630 — designed to be viewed standalone in a browser during development,
and (later) rendered to PNG via headless Chromium for Twitter/LinkedIn/iMessage
scrapers.

URL convention:
- ``/og-preview``                          — index of corpora with preview links
- ``/og-preview/c/{slug}``                 — corpus card
- ``/og-preview/c/{slug}/d/{doc_id}``      — content card (wiki or note)

Per-corpus accent color is hashed from ``corpus.name`` using the same PAL
palette + string-hash as the frontend network graph (``app.js`` lines 85–86),
so a shared card carries the same identity color as the in-app node.
"""

from __future__ import annotations

import hashlib
import html
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from noosphere.core.corpus import get_corpus_by_slug, list_corpora
from noosphere.core.ingest import get_document, get_documents


router = APIRouter()

_STATIC_INDEX = Path(__file__).parent / "static" / "index.html"
_OG_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "og_cache"


# ── Palette + hash (mirror of app.js lines 85–86) ─────────────────────
PAL = [
    "#e76f51", "#2a9d8f", "#264653", "#e9c46a", "#f4a261",
    "#588157", "#457b9d", "#9b2226", "#6d6875", "#b56576",
    "#355070", "#6c757d", "#e07a5f", "#3d405b", "#81b29a",
]
PRIVATE_GRAY = "#94a3b8"


def _hash_color(name: str) -> str:
    """JS-equivalent string hash → PAL palette index. Mirrors ``cC`` in app.js."""
    if not name:
        name = "?"
    h = 0
    for ch in name:
        h = ((h << 5) - h + ord(ch)) & 0xFFFFFFFF
        if h >= 0x80000000:
            h -= 0x100000000
    return PAL[abs(h) % len(PAL)]


def _accent_for(corpus: dict) -> str:
    """Per-corpus accent — name-hashed for public/paid/token, muted gray for private."""
    if (corpus.get("access_level") or "public") == "private":
        return PRIVATE_GRAY
    return _hash_color(corpus.get("name") or corpus.get("id") or "?")


def _initials(name: str) -> str:
    """First character of each whitespace-split word, max 2 chars.

    For CJK names with no internal whitespace, returns the first character only —
    matches the frontend's ``.split(/\\s+/).slice(0,2).map(w=>w[0]).join('')``.
    """
    if not name:
        return "?"
    parts = name.split()
    if not parts:
        return name[0]
    return "".join(p[0] for p in parts[:2])


# ── Excerpt + markdown helpers ────────────────────────────────────────

def _strip_markdown(text: str) -> str:
    """Light markdown cleanup for OG card excerpts. Drops formatting markers
    but preserves prose. Not a full parser — just enough to keep the card clean."""
    t = text
    t = re.sub(r"^#{1,6}\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"__([^_]+)__", r"\1", t)
    t = re.sub(r"(?<!\w)\*([^*\s][^*]*?)\*(?!\w)", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"^>\s+", "", t, flags=re.MULTILINE)
    return t


def _drop_title_echo(content: str) -> str:
    """Strip a single short leading markdown heading.

    Covers three cases at once:
      1. User-saved notes that lead with ``# <title>`` echoing the title field
      2. Compiled concept docs that lead with ``## Compiled Truth: <title>``
      3. System-generated manifest docs that lead with ``# <corpus name>``

    All three would otherwise leak into the excerpt as noise. We only strip if
    the heading is short (<= 80 chars) so we don't accidentally swallow a
    legitimate prose paragraph that happens to start with ``#``.
    """
    if not content:
        return content
    m = re.match(r"^\s*#{1,6}\s+([^\n]{1,80})\n+", content)
    return content[m.end():] if m else content


def _extract_concept_summary(content: str) -> str:
    """For compiled concept docs, prefer the Summary section.

    The compile pipeline emits ``## Compiled Truth: X`` then a sequence of
    ``### <Section>`` blocks (Summary, Details, Citations, etc.). Summary is
    the human-readable distillation; everything else is inspection cruft. For
    an OG excerpt, return the Summary body alone if present, else fall through
    to the whole content.
    """
    if not content:
        return content
    m = re.search(
        r"#{2,3}\s+Summary\s*\n+(.*?)(?=\n+#{2,3}\s+\w|\Z)",
        content,
        flags=re.DOTALL,
    )
    return m.group(1).strip() if m else content


def _clean_title(title: str) -> str:
    """Strip 'Concept: ' prefix that ships with compiled concept docs."""
    t = (title or "").strip()
    if t.startswith("Concept: "):
        t = t[len("Concept: "):]
    return t


def _smart_excerpt(text: str, max_chars: int) -> str:
    """Truncate at a sentence boundary if available, else word boundary, else hard.

    CJK sentence terminators (。！？；) and ASCII (.!?) both close a sentence.
    For prose without terminators we fall back to the last space (English) or
    a hard cut (CJK runs)."""
    if not text:
        return ""
    t = " ".join(text.split())
    if len(t) <= max_chars:
        return t
    cut = t[:max_chars]
    enders = "。！？；.!?"
    look_back = max(0, len(cut) - max(40, max_chars // 4))
    for i in range(len(cut) - 1, look_back, -1):
        if cut[i] in enders:
            return cut[: i + 1]
    for i in range(len(cut) - 1, max(0, len(cut) - 20), -1):
        if cut[i] == " ":
            return cut[:i].rstrip() + "…"
    return cut.rstrip() + "…"


# ── Card classification ───────────────────────────────────────────────

def _is_wiki(doc: dict) -> bool:
    """Wiki entries are compiled concept docs. Everything else (doc, blog,
    paper, note, capture, manifest, '') is a raw source/note."""
    return (doc.get("doc_type") or "") == "concept"


def _content_label(doc: dict) -> str:
    return "Wiki" if _is_wiki(doc) else "Note"


# ── HTML rendering ────────────────────────────────────────────────────

_BASE_STYLES = """
* { box-sizing: border-box; margin: 0; padding: 0; }

html, body { background: #e6e6ea; }

body {
  font-family: 'Libre Baskerville', 'Noto Serif SC', Georgia, serif;
  color: #1d1d1f;
  padding: 48px;
  min-height: 100vh;
}

.preview-shell {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
}

.preview-meta {
  font-family: 'Inter', sans-serif;
  font-size: 12px;
  color: #6e6e73;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.card {
  width: 1200px;
  height: 630px;
  background: #ffffff;
  position: relative;
  padding: 88px 96px 64px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 4px 32px rgba(0, 0, 0, 0.06);
  overflow: hidden;
}

.card-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  overflow: hidden;
  padding-bottom: 32px;
}

/* ── Content card — with title (wiki entries always have one) ─── */
.title {
  font-family: 'Libre Baskerville', 'Noto Serif SC', Georgia, serif;
  font-weight: 700;
  font-size: 64px;
  line-height: 1.12;
  letter-spacing: -0.022em;
  margin-bottom: 32px;
  color: #1d1d1f;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.excerpt {
  font-family: 'Libre Baskerville', 'Noto Serif SC', Georgia, serif;
  font-weight: 400;
  font-size: 28px;
  line-height: 1.55;
  color: #494949;
  display: -webkit-box;
  -webkit-line-clamp: 5;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ── Content card — no title; excerpt is hero ─────────────────── */
.quote {
  font-family: 'Libre Baskerville', 'Noto Serif SC', Georgia, serif;
  font-weight: 400;
  font-size: 38px;
  line-height: 1.45;
  color: #1d1d1f;
  padding-left: 32px;
  border-left: 2px solid #d6d6d9;
  display: -webkit-box;
  -webkit-line-clamp: 6;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ── Corpus card ──────────────────────────────────────────────── */
.x-glyph {
  width: 92px;
  height: 92px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  font-family: 'Inter', 'Noto Serif SC', sans-serif;
  font-weight: 600;
  font-size: 40px;
  letter-spacing: -0.02em;
  margin-bottom: 40px;
}

.x-name {
  font-family: 'Libre Baskerville', 'Noto Serif SC', Georgia, serif;
  font-weight: 700;
  font-size: 80px;
  line-height: 1.05;
  letter-spacing: -0.028em;
  color: #1d1d1f;
  margin-bottom: 24px;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.x-desc {
  font-family: 'Libre Baskerville', 'Noto Serif SC', Georgia, serif;
  font-weight: 400;
  font-size: 26px;
  line-height: 1.5;
  color: #494949;
  max-width: 880px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.x-meta {
  font-family: 'Libre Baskerville', 'Noto Serif SC', Georgia, serif;
  font-style: italic;
  font-weight: 400;
  font-size: 19px;
  letter-spacing: 0;
  color: #6e6e73;
  margin-top: 36px;
}

/* ── Footer (shared by all card types) ────────────────────────── */
.foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 22px;
  border-top: 1px solid rgba(0, 0, 0, 0.07);
}

.foot-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.foot-glyph {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  font-family: 'Inter', 'Noto Serif SC', sans-serif;
  font-weight: 600;
  font-size: 13px;
  letter-spacing: -0.02em;
}

.foot-meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
  line-height: 1;
}

.foot-cname {
  font-family: 'Libre Baskerville', 'Noto Serif SC', Georgia, serif;
  font-weight: 700;
  font-size: 16px;
  color: #1d1d1f;
  letter-spacing: -0.005em;
}

.foot-type {
  font-family: 'Inter', sans-serif;
  font-weight: 500;
  font-size: 11px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #86868b;
}

.foot-wm {
  font-family: 'Libre Baskerville', Georgia, serif;
  font-weight: 400;
  font-size: 18px;
  color: #1d1d1f;
  letter-spacing: -0.005em;
}

.foot-byline {
  font-family: 'Libre Baskerville', 'Noto Serif SC', Georgia, serif;
  font-style: italic;
  font-weight: 400;
  font-size: 18px;
  color: #6e6e73;
  letter-spacing: -0.005em;
}

/* ── Index page ───────────────────────────────────────────────── */
.idx {
  max-width: 760px;
  margin: 60px auto;
  font-family: 'Inter', sans-serif;
  color: #1d1d1f;
  background: #ffffff;
  padding: 48px 56px;
  box-shadow: 0 4px 32px rgba(0, 0, 0, 0.06);
}

.idx h1 {
  font-family: 'Libre Baskerville', Georgia, serif;
  font-weight: 700;
  font-size: 28px;
  letter-spacing: -0.015em;
  margin-bottom: 8px;
}

.idx .lede {
  font-size: 14px;
  color: #6e6e73;
  margin-bottom: 32px;
  line-height: 1.55;
}

.idx ul { list-style: none; }

.idx li {
  padding: 16px 0;
  border-bottom: 1px solid #e6e6ea;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.idx li:last-child { border-bottom: none; }

.idx a {
  color: #1d1d1f;
  text-decoration: none;
  font-weight: 500;
  font-size: 15px;
}

.idx a:hover { text-decoration: underline; }

.idx .row-meta {
  color: #86868b;
  font-size: 12px;
  letter-spacing: 0.04em;
}

.idx .docs {
  margin-top: 16px;
  padding-left: 16px;
  border-left: 1px solid #e6e6ea;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.idx .docs a {
  font-weight: 400;
  font-size: 13px;
  color: #6e6e73;
}

.idx .doctype {
  font-family: 'Inter', sans-serif;
  font-weight: 500;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #b0b0b6;
  margin-right: 8px;
}
"""


def _document_with_head(body_html: str, title: str = "OG Preview") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=1280">
  <title>{html.escape(title)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Libre+Baskerville:wght@400;700&family=Noto+Serif+SC:wght@400;700&display=swap">
  <style>{_BASE_STYLES}</style>
</head>
<body>
{body_html}
</body>
</html>"""


def _render_corpus_card(corpus: dict) -> str:
    """Corpus card — name as masthead, optional description, meta line.

    The accent color shows in the large top-left glyph badge; this is the
    corpus's identity moment. No small footer glyph (avoids duplication).
    """
    name = (corpus.get("name") or "").strip() or "Untitled"
    desc = (corpus.get("description") or "").strip()
    access = (corpus.get("access_level") or "public").strip()
    author = (corpus.get("author_name") or "").strip()
    accent = _accent_for(corpus)
    initials = _initials(name)
    doc_count = int(corpus.get("document_count") or 0)

    access_label = {
        "public": "Public",
        "paid": "Paid",
        "token": "Token-gated",
        "private": "Private",
    }.get(access, access.title())

    meta_line = f"{doc_count} {'document' if doc_count == 1 else 'documents'}  ·  {access_label}"

    desc_html = f'<div class="x-desc">{html.escape(desc)}</div>' if desc else ""
    foot_left_html = (
        f'<div class="foot-byline">by {html.escape(author)}</div>'
        if author else ""
    )

    return f"""
<div class="card">
  <div class="card-body">
    <div class="x-glyph" style="background: {accent};">{html.escape(initials)}</div>
    <div class="x-name">{html.escape(name)}</div>
    {desc_html}
    <div class="x-meta">{html.escape(meta_line)}</div>
  </div>
  <div class="foot">
    <div class="foot-left">{foot_left_html}</div>
    <div class="foot-wm">noosphere.wiki</div>
  </div>
</div>
"""


def _render_content_card(corpus: dict, doc: dict) -> str:
    """Content card — handles both wiki entries and raw notes.

    Two layouts driven by a single signal: whether the document has a
    meaningful title.
      - title present  →  title-led: large serif title + body excerpt
      - title absent   →  quote-led: excerpt as hero with a hairline rule

    The doc_type ('concept' = wiki, else = note) only changes the small
    footer label, not the visual layout. Same family, same template.
    """
    raw_title = _clean_title(doc.get("title", ""))
    raw_content = doc.get("content") or ""

    # For compiled wiki entries, pull the Summary section out before anything
    # else — it's the human-readable distillation; everything around it is
    # boilerplate that reads ugly as prose.
    if _is_wiki(doc):
        raw_content = _extract_concept_summary(raw_content)

    # Strip any short leading markdown heading — covers title-echoes and the
    # corpus-name heading at the start of manifest docs.
    content = _drop_title_echo(raw_content)
    content = _strip_markdown(content)
    content = content.strip()

    corpus_name = (corpus.get("name") or "").strip() or "Untitled"
    accent = _accent_for(corpus)
    initials = _initials(corpus_name)
    content_label = _content_label(doc)

    # Heuristic: "no meaningful title" = empty, or auto-generated patterns
    # like "user_original-3". We keep the title for everything else.
    auto_title_pat = re.compile(r"^(user_(original|capture)|untitled)[-_\s]?\d*$", re.I)
    has_meaningful_title = bool(raw_title) and not auto_title_pat.match(raw_title)

    if has_meaningful_title:
        excerpt = _smart_excerpt(content, max_chars=320)
        body = f"""
    <div class="title">{html.escape(raw_title)}</div>
    <div class="excerpt">{html.escape(excerpt)}</div>
"""
    else:
        excerpt = _smart_excerpt(content, max_chars=260)
        body = f"""
    <div class="quote">{html.escape(excerpt)}</div>
"""

    return f"""
<div class="card">
  <div class="card-body">{body}</div>
  <div class="foot">
    <div class="foot-left">
      <div class="foot-glyph" style="background: {accent};">{html.escape(initials)}</div>
      <div class="foot-meta">
        <div class="foot-cname">{html.escape(corpus_name)}</div>
        <div class="foot-type">{content_label}</div>
      </div>
    </div>
    <div class="foot-wm">noosphere.wiki</div>
  </div>
</div>
"""


def _wrap_preview(card_html: str, meta_line: str, title: str) -> HTMLResponse:
    body = f"""
<div class="preview-shell">
  <div class="preview-meta">{html.escape(meta_line)}</div>
  {card_html}
</div>
"""
    return HTMLResponse(content=_document_with_head(body, title=title))


# ── Routes ────────────────────────────────────────────────────────────

@router.get("/og-preview", response_class=HTMLResponse)
async def og_index():
    """Developer index: lists all corpora with links to preview each card."""
    corpora = list_corpora(include_private=True)
    items = []
    for c in corpora:
        slug = c.get("slug") or ""
        if not slug:
            continue
        name = html.escape(c.get("name") or "Untitled")
        access = html.escape((c.get("access_level") or "public").title())
        doc_count = int(c.get("document_count") or 0)
        docs = get_documents(c["id"])
        doc_links = "".join(
            f'<a href="/og-preview/c/{html.escape(slug)}/d/{html.escape(d["id"])}">'
            f'<span class="doctype">{html.escape("Wiki" if _is_wiki(d) else "Note")}</span>'
            f'{html.escape(_clean_title(d.get("title") or "(untitled)"))}'
            f'</a>'
            for d in docs[:6]
        )
        items.append(f"""
<li>
  <div style="flex:1">
    <a href="/og-preview/c/{html.escape(slug)}">{name}</a>
    <div class="docs">{doc_links}</div>
  </div>
  <span class="row-meta">{access} · {doc_count} docs</span>
</li>
""")
    body = f"""
<div class="idx">
  <h1>OG card preview</h1>
  <p class="lede">Click a corpus name to preview its corpus card, or any document below it to preview the content card. Each card renders at exactly 1200×630 — the dimensions Twitter/LinkedIn scrape.</p>
  <ul>{''.join(items) if items else '<li><span class="row-meta">No corpora yet.</span></li>'}</ul>
</div>
"""
    return HTMLResponse(content=_document_with_head(body, title="OG Preview · Noosphere"))


@router.get("/og-preview/c/{slug}", response_class=HTMLResponse)
async def og_corpus(slug: str):
    corpus = get_corpus_by_slug(slug)
    if not corpus:
        raise HTTPException(status_code=404, detail="Corpus not found")
    name = corpus.get("name") or "Untitled"
    meta = f"Corpus card  ·  {slug}  ·  1200 × 630"
    return _wrap_preview(_render_corpus_card(corpus), meta, title=f"{name} — OG Preview")


@router.get("/og-preview/c/{slug}/d/{doc_id}", response_class=HTMLResponse)
async def og_document(slug: str, doc_id: str):
    corpus = get_corpus_by_slug(slug)
    if not corpus:
        raise HTTPException(status_code=404, detail="Corpus not found")
    doc = get_document(doc_id)
    if not doc or doc.get("corpus_id") != corpus["id"]:
        raise HTTPException(status_code=404, detail="Document not found in this corpus")
    label = "Wiki" if _is_wiki(doc) else "Note"
    title = _clean_title(doc.get("title") or "") or "(untitled)"
    meta = f"{label} card  ·  {slug}  ·  {doc_id}  ·  1200 × 630"
    return _wrap_preview(_render_content_card(corpus, doc), meta, title=f"{title} — OG Preview")


# ── Server-rendered share landing pages ───────────────────────────────
#
# ``/c/{slug}`` and ``/c/{slug}/d/{doc_id}`` are the canonical shareable URLs.
# When a Twitter / LinkedIn / iMessage scraper hits one of these, it must read
# corpus- or document-specific OG meta tags directly out of the response body
# — those clients don't run JS. So FastAPI serves the SPA shell with the head
# augmented, then a tiny inline script translates the share URL into the hash
# route the SPA already understands (``#/corpus/{id}`` / ``…/doc/{doc_id}``).

def _share_describe(corpus: dict, doc: dict | None) -> tuple[str, str, str]:
    """Compute (page_title, og_title, description) for a share surface.

    ``page_title`` is the <title> shown in browser tabs; ``og_title`` is what
    appears as the headline of the social card; ``description`` is the snippet
    underneath. We keep ``og_title`` shorter than ``page_title`` because Twitter
    truncates headlines aggressively.
    """
    corpus_name = (corpus.get("name") or "Untitled").strip()
    if doc is None:
        og_title = corpus_name
        page_title = f"{corpus_name} — Corpus on Noosphere"
        description = (corpus.get("description") or "").strip()
        if not description:
            doc_count = int(corpus.get("document_count") or 0)
            noun = "document" if doc_count == 1 else "documents"
            description = f"A knowledge base on Noosphere — {doc_count} {noun}, openly queryable."
        return page_title, og_title, _smart_excerpt(description, max_chars=200)

    is_wiki = _is_wiki(doc)
    label = "Wiki" if is_wiki else "Note"
    raw_title = _clean_title(doc.get("title") or "")
    og_title = raw_title or corpus_name

    raw_content = doc.get("content") or ""
    if is_wiki:
        raw_content = _extract_concept_summary(raw_content)
    content = _strip_markdown(_drop_title_echo(raw_content)).strip()
    description = _smart_excerpt(content, max_chars=240)
    page_title = f"{og_title} — {corpus_name} on Noosphere"
    if not description:
        description = f"A {label.lower()} in {corpus_name} on Noosphere."
    return page_title, og_title, description


def _render_share_html(corpus: dict, doc: dict | None, request: Request) -> str:
    """Return ``index.html`` augmented with page-specific OG meta + a hash hand-off.

    The SPA's router (``app.js`` ``route()``) reads ``location.hash``; setting
    it before the SPA boots means ``route()``'s first call lands on the right
    view. Setting ``location.hash`` while parsing also fires a hashchange event
    too early for the SPA's listener to hear it — that's intentional: the SPA
    calls ``route()`` directly on boot in addition to listening, so the
    pre-set hash gets picked up exactly once.
    """
    template = _STATIC_INDEX.read_text(encoding="utf-8")
    base_url = str(request.base_url).rstrip("/")

    page_title, og_title, description = _share_describe(corpus, doc)
    slug = (corpus.get("slug") or "").strip()
    corpus_id = corpus["id"]

    if doc is None:
        canonical_path = f"/c/{slug}"
        hash_route = f"#/corpus/{corpus_id}"
        og_image_path = f"/og/c/{slug}.png"
    else:
        canonical_path = f"/c/{slug}/d/{doc['id']}"
        # The SPA has no dedicated single-doc view — docs render as items in
        # the corpus view. Route the share URL to the corpus so the recipient
        # at least lands on the right scope with that doc visible in the list.
        # Doc-level deep-linking is a separate SPA enhancement.
        hash_route = f"#/corpus/{corpus_id}"
        og_image_path = f"/og/c/{slug}/d/{doc['id']}.png"

    canonical_url = f"{base_url}{canonical_path}"
    og_image_url = f"{base_url}{og_image_path}"

    inject = f"""    <title>{html.escape(page_title)}</title>
    <meta name="description" content="{html.escape(description)}" />
    <link rel="canonical" href="{html.escape(canonical_url)}" />
    <meta property="og:type" content="article" />
    <meta property="og:site_name" content="Noosphere" />
    <meta property="og:title" content="{html.escape(og_title)}" />
    <meta property="og:description" content="{html.escape(description)}" />
    <meta property="og:url" content="{html.escape(canonical_url)}" />
    <meta property="og:image" content="{html.escape(og_image_url)}" />
    <meta property="og:image:width" content="1200" />
    <meta property="og:image:height" content="630" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{html.escape(og_title)}" />
    <meta name="twitter:description" content="{html.escape(description)}" />
    <meta name="twitter:image" content="{html.escape(og_image_url)}" />
    <script>if(!location.hash){{location.hash={hash_route!r}}}</script>
"""

    # Drop the static <title> and the static <meta name="description"> — both
    # are site-level fallbacks and would otherwise leave duplicate tags that
    # scrapers handle inconsistently.
    template = re.sub(r"<title>[^<]*</title>\s*", "", template, count=1)
    template = re.sub(r'<meta name="description"[^/]*/>\s*', "", template, count=1)

    return template.replace("</head>", inject + "  </head>", 1)


@router.get("/c/{slug}", response_class=HTMLResponse)
async def share_corpus(slug: str, request: Request):
    """Canonical share landing page for a corpus.

    A no-frills SPA shell with corpus-specific OG meta — Twitter and friends
    read the head, humans get the same app they'd see at the hash route.
    """
    corpus = get_corpus_by_slug(slug)
    if not corpus:
        raise HTTPException(status_code=404, detail="Corpus not found")
    return HTMLResponse(content=_render_share_html(corpus, None, request))


@router.get("/c/{slug}/d/{doc_id}", response_class=HTMLResponse)
async def share_document(slug: str, doc_id: str, request: Request):
    """Canonical share landing page for a single document inside a corpus."""
    corpus = get_corpus_by_slug(slug)
    if not corpus:
        raise HTTPException(status_code=404, detail="Corpus not found")
    doc = get_document(doc_id)
    if not doc or doc.get("corpus_id") != corpus["id"]:
        raise HTTPException(status_code=404, detail="Document not found in this corpus")
    return HTMLResponse(content=_render_share_html(corpus, doc, request))


# ── PNG rendering — what Twitter/LinkedIn/iMessage actually fetch ──────
#
# Social scrapers don't run JS or rasterize HTML themselves: they fetch the
# URL in ``og:image`` and expect a raw image back. We render the same HTML
# card the preview routes serve through headless Chrome and return PNG bytes.
#
# Cache: each (corpus, doc, updated_at) tuple gets a stable cache key; the
# first request renders + writes a file on disk, subsequent requests serve the
# file. Content edits change ``updated_at`` → cache key shifts → next request
# is a fresh render. Stale files accumulate but are tiny; no sweep yet.

def _bare_card_doc(card_html_inner: str) -> str:
    """Standalone 1200×630 HTML document for headless-Chrome screenshotting.

    Strips the preview shell (background, padding, drop-shadow) so the card
    fills the viewport exactly. Keeps the same fonts and base styles so the
    PNG matches what the preview route renders.
    """
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Libre+Baskerville:wght@400;700&family=Noto+Serif+SC:wght@400;700&display=swap">
  <style>
    {_BASE_STYLES}
    html, body {{ margin: 0; padding: 0; background: #ffffff; min-height: 0; }}
    .card {{ box-shadow: none; }}
  </style>
</head>
<body>
{card_html_inner}
</body>
</html>"""


async def _render_html_to_png(html_content: str) -> bytes:
    """Headless Chrome → 1200×630 PNG.

    Uses ``channel="chrome"`` to reuse the system Chrome install on dev (no
    150MB Chromium download). Waits on ``document.fonts.ready`` so the first
    request after a cold cache doesn't snapshot mid-font-load — Libre
    Baskerville and Noto Serif SC are both fetched from Google Fonts and the
    fallback (Georgia) looks visibly wrong if it sneaks in.

    Playwright is an optional dependency: self-hosted minimal installs that
    don't care about pretty OG cards can skip it. We surface a clear 503 so
    the meta-tag layer (which works regardless) keeps functioning and only
    the image request degrades.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="OG image rendering requires the 'playwright' package. "
                   "Install with: pip install playwright",
        )

    # Browser channel selection:
    #   Default (no env var) → Playwright's bundled Chromium (what
    #     `playwright install chromium` puts on disk; this is what the
    #     Docker image ships, so prod just works).
    #   PLAYWRIGHT_CHANNEL=chrome → reuse system Google Chrome, the dev
    #     escape hatch on a macOS laptop where downloading 150MB of
    #     bundled chromium is unnecessary.
    channel = os.getenv("PLAYWRIGHT_CHANNEL", "").strip() or None

    async with async_playwright() as p:
        browser = await (p.chromium.launch(channel=channel) if channel else p.chromium.launch())
        try:
            ctx = await browser.new_context(
                viewport={"width": 1200, "height": 630},
                device_scale_factor=1,
            )
            page = await ctx.new_page()
            await page.set_content(html_content, wait_until="networkidle")
            await page.evaluate("document.fonts.ready")
            return await page.screenshot(type="png", full_page=False)
        finally:
            await browser.close()


def _cache_key_corpus(corpus: dict) -> str:
    raw = f"corpus:{corpus['id']}:{corpus.get('updated_at') or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _cache_key_doc(corpus: dict, doc: dict) -> str:
    raw = (
        f"doc:{corpus['id']}:{doc['id']}:"
        f"{corpus.get('updated_at') or ''}:{doc.get('created_at') or ''}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _cache_path(key: str) -> Path:
    _OG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _OG_CACHE_DIR / f"{key}.png"


def _png_response(data: bytes) -> Response:
    # Scrapers cache aggressively; we lean on cache-control to let CDNs and
    # client caches hold the PNG for 5 minutes while also allowing serve-stale
    # while we re-render in background (we don't yet, but the header is right).
    return Response(
        content=data,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=300, stale-while-revalidate=86400"},
    )


@router.get("/og/c/{slug}.png")
async def og_corpus_png(slug: str):
    corpus = get_corpus_by_slug(slug)
    if not corpus:
        raise HTTPException(status_code=404, detail="Corpus not found")

    path = _cache_path(_cache_key_corpus(corpus))
    if not path.exists():
        png = await _render_html_to_png(_bare_card_doc(_render_corpus_card(corpus)))
        path.write_bytes(png)
    return _png_response(path.read_bytes())


@router.get("/og/c/{slug}/d/{doc_id}.png")
async def og_doc_png(slug: str, doc_id: str):
    corpus = get_corpus_by_slug(slug)
    if not corpus:
        raise HTTPException(status_code=404, detail="Corpus not found")
    doc = get_document(doc_id)
    if not doc or doc.get("corpus_id") != corpus["id"]:
        raise HTTPException(status_code=404, detail="Document not found in this corpus")

    path = _cache_path(_cache_key_doc(corpus, doc))
    if not path.exists():
        png = await _render_html_to_png(_bare_card_doc(_render_content_card(corpus, doc)))
        path.write_bytes(png)
    return _png_response(path.read_bytes())
