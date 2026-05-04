"""Public-facing routes for AI/web discovery surfaces.

Mounted at the site root (not under `/api/v1`) because the standards these
endpoints implement expect to be found at conventional paths — agents and
crawlers probe well-known locations, not application-specific prefixes.

Endpoints:

- ``GET /llms.txt``                — site-level llms.txt index (llmstxt.org)
- ``GET /c/{slug}/llms.txt``       — per-corpus markdown index
- ``GET /c/{slug}/llms-full.txt``  — per-corpus full-text dump
- ``GET /sitemap.xml``             — sitemap for traditional + AI search crawlers
- ``GET /robots.txt``              — crawl directives, links to the sitemap

Slug-based URLs are stable: corpus slugs are unique and fixed at creation
(see ``corpus.create_corpus``; ``update_corpus`` does not allow re-slugging).
The existing ``/api/v1/corpora/{id}/llms.txt`` routes are kept for programmatic
callers that already have a corpus id; the UI prefers the slug form.
"""

from __future__ import annotations

from xml.sax.saxutils import escape as _xml_escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response

from noosphere.core.access import AccessDenied, check_access
from noosphere.core.access_log import log_access
from noosphere.core.corpus import get_corpus_by_slug, list_corpora
from noosphere.core.ingest import get_documents
from noosphere.core.llmstxt import (
    render_llms_full,
    render_llms_index,
    render_site_index,
)

router = APIRouter()


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def _gate(corpus: dict, request: Request) -> None:
    """Apply access gating for public llmstxt endpoints.

    Public corpora are open to anyone; token/paid require a bearer; private
    is rejected outright. We deliberately do NOT honor owner/localhost bypass
    here — these URLs are meant for external sharing, and what an external
    LLM sees should match what the URL contractually exposes regardless of
    who fetches it.
    """
    try:
        check_access(corpus, _bearer(request))
    except AccessDenied as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


def _resolve_by_slug(slug: str) -> dict:
    corpus = get_corpus_by_slug(slug)
    if not corpus:
        raise HTTPException(status_code=404, detail="Corpus not found")
    return corpus


@router.get("/llms.txt")
async def site_llms_index(request: Request):
    """Site-level llms.txt — the entry point any AI agent visits first.

    Lists every public corpus on this Noosphere instance with a link to its
    own ``/c/{slug}/llms.txt``. Token/paid/private corpora are intentionally
    omitted: agents fetching the site root cannot consume gated content
    without out-of-band credentials, so advertising them adds noise.
    """
    corpora = [c for c in list_corpora() if (c.get("access_level") or "public") == "public"]
    text = render_site_index(corpora)
    log_access(request, corpus_id=None, surface="site_llms")
    return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")


@router.get("/c/{slug}/llms.txt")
async def corpus_llms_index_by_slug(slug: str, request: Request):
    corpus = _resolve_by_slug(slug)
    _gate(corpus, request)
    docs = get_documents(corpus["id"])
    text = render_llms_index(corpus, docs, base_path="/api/v1")
    log_access(request, corpus_id=corpus["id"], surface="corpus_llms")
    return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")


@router.get("/c/{slug}/llms-full.txt")
async def corpus_llms_full_by_slug(slug: str, request: Request):
    corpus = _resolve_by_slug(slug)
    _gate(corpus, request)
    docs = get_documents(corpus["id"])
    text = render_llms_full(corpus, docs)
    log_access(request, corpus_id=corpus["id"], surface="corpus_llms_full")
    return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")


# ── /sitemap.xml + /robots.txt — traditional + AI crawler discovery ───
# Why list llms.txt URLs in the sitemap (not just an HTML page per corpus):
# the markdown views are the stable, content-bearing URLs today. AI crawlers
# (ChatGPT search, Perplexity, Anthropic web fetch) prefer markdown over
# JS-rendered HTML, and traditional crawlers (Googlebot) accept any URL.
# When a per-corpus HTML route ships, this list expands; the site-root and
# per-corpus llms.txt entries stay regardless.

def _lastmod(corpus: dict) -> str:
    """Truncate corpus.updated_at to YYYY-MM-DD for sitemap <lastmod>."""
    raw = (corpus.get("updated_at") or "").strip()
    return raw[:10] if len(raw) >= 10 else ""


@router.get("/sitemap.xml")
async def sitemap_xml(request: Request):
    base = str(request.base_url).rstrip("/")
    corpora = [c for c in list_corpora() if (c.get("access_level") or "public") == "public"]

    parts: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        f"  <url>\n    <loc>{_xml_escape(base + '/llms.txt')}</loc>\n  </url>",
    ]
    for c in corpora:
        slug = (c.get("slug") or "").strip()
        if not slug:
            continue
        lastmod = _lastmod(c)
        for path in (f"/c/{slug}/llms.txt", f"/c/{slug}/llms-full.txt"):
            block = [f"  <url>", f"    <loc>{_xml_escape(base + path)}</loc>"]
            if lastmod:
                block.append(f"    <lastmod>{lastmod}</lastmod>")
            block.append("  </url>")
            parts.append("\n".join(block))
    parts.append("</urlset>\n")
    log_access(request, corpus_id=None, surface="site_sitemap")
    return Response(content="\n".join(parts), media_type="application/xml")


@router.get("/robots.txt")
async def robots_txt(request: Request):
    base = str(request.base_url).rstrip("/")
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )
    log_access(request, corpus_id=None, surface="site_robots")
    return PlainTextResponse(body, media_type="text/plain; charset=utf-8")
