"""Render llms.txt / llms-full.txt for a corpus.

Per https://llmstxt.org — a small open standard for letting any LLM consume
a site or knowledge base in one fetch. We expose two views per public corpus:

- ``llms.txt``       — markdown index (corpus header + document list)
- ``llms-full.txt``  — full-text dump (header + every document concatenated)

Both views always render the externally-visible content slice — same filter
external API callers see in retrieval (``EXTERNAL_ALLOWED_SOURCE_KINDS``).
Externally-imported material (``external_*``) and auto-generated system docs
are excluded; only user-originated and user-captured content is published.

Renderers are pure: pass a corpus dict + documents list, get back a string.
No DB calls, no FastAPI imports — keeps route handlers thin and lets the
formatters be unit-tested without a request context.
"""

from __future__ import annotations

from noosphere.core.retrieval import EXTERNAL_ALLOWED_SOURCE_KINDS


def _publishable(documents: list[dict]) -> list[dict]:
    out: list[dict] = []
    for d in documents:
        sk = d.get("source_kind") or "user_original"
        if sk not in EXTERNAL_ALLOWED_SOURCE_KINDS:
            continue
        # The manifest doc is auto-derived from corpus metadata (name,
        # description, task_types, samples) and would duplicate content that
        # already appears in the llms.txt header. Modern manifests use
        # source_kind='system' (already filtered), but legacy rows occasionally
        # land as user_original — skip by doc_type so both shapes are covered.
        if (d.get("doc_type") or "") == "manifest":
            continue
        out.append(d)
    return out


def _header_lines(corpus: dict) -> list[str]:
    lines: list[str] = [f"# {corpus.get('name') or 'Untitled corpus'}"]
    desc = (corpus.get("description") or "").strip()
    if desc:
        lines.append("")
        for line in desc.splitlines():
            lines.append(f"> {line}" if line else ">")
    meta_bits: list[str] = []
    author = (corpus.get("author_name") or "").strip()
    author_url = (corpus.get("author_url") or "").strip()
    if author:
        meta_bits.append(f"- Author: {author}" + (f" <{author_url}>" if author_url else ""))
    elif author_url:
        meta_bits.append(f"- Author: <{author_url}>")
    license_ = (corpus.get("license") or "").strip()
    if license_:
        meta_bits.append(f"- License: {license_}")
    language = (corpus.get("language") or "").strip()
    if language:
        meta_bits.append(f"- Language: {language}")
    return lines, meta_bits


def render_llms_index(corpus: dict, documents: list[dict], *, base_path: str = "") -> str:
    """Render the `llms.txt` markdown index.

    `base_path` is prepended to document links so served URLs can be absolute
    (e.g. "https://noosphere.example.com") or relative ("" / "/api/v1").
    """
    head_lines, meta_bits = _header_lines(corpus)
    docs = _publishable(documents)
    body: list[str] = list(head_lines)
    if meta_bits:
        body.append("")
        body.extend(meta_bits)
    body.append("")
    body.append(f"- Documents: {len(docs)}")
    body.append("")
    body.append("## Documents")
    body.append("")
    if not docs:
        body.append("_No documents yet._")
    else:
        corpus_id = corpus.get("id") or ""
        for d in docs:
            title = (d.get("title") or "Untitled").strip()
            doc_id = d.get("id") or ""
            date = (d.get("date") or "").strip()
            link = f"{base_path}/corpora/{corpus_id}/documents/{doc_id}"
            line = f"- [{title}]({link})"
            if date:
                line += f" — {date}"
            body.append(line)
    body.append("")
    return "\n".join(body)


def render_site_index(corpora: list[dict]) -> str:
    """Render the site-level `llms.txt` — Noosphere instance's discovery entry point.

    Per llmstxt.org, a site root `llms.txt` lists the resources an LLM can
    consume. We list every public corpus with a link to its own per-corpus
    `llms.txt`. Token/paid/private corpora are filtered upstream — by the
    time a list reaches here, every entry is publicly fetchable without auth.
    """
    body: list[str] = [
        "# Noosphere",
        "",
        "> A smart knowledge layer for the agent internet. Personal and team "
        "knowledge bases that any AI agent can read, query, and learn from.",
        "",
        "## Knowledge bases",
        "",
    ]
    if not corpora:
        body.append("_No public corpora yet._")
        body.append("")
        return "\n".join(body)
    for c in corpora:
        slug = (c.get("slug") or "").strip()
        if not slug:
            continue
        name = (c.get("name") or "Untitled").strip()
        desc = (c.get("description") or "").strip().replace("\n", " ")
        line = f"- [{name}](/c/{slug}/llms.txt)"
        if desc:
            line += f": {desc}"
        body.append(line)
    body.append("")
    return "\n".join(body)


def render_llms_full(corpus: dict, documents: list[dict]) -> str:
    """Render the `llms-full.txt` dump — header + every publishable document inlined."""
    head_lines, meta_bits = _header_lines(corpus)
    docs = _publishable(documents)
    body: list[str] = list(head_lines)
    if meta_bits:
        body.append("")
        body.extend(meta_bits)
    body.append("")
    body.append(f"- Documents: {len(docs)}")
    body.append("")
    if not docs:
        body.append("_No documents yet._")
        body.append("")
        return "\n".join(body)
    for d in docs:
        body.append("---")
        body.append("")
        title = (d.get("title") or "Untitled").strip()
        date = (d.get("date") or "").strip()
        body.append(f"## {title}")
        if date:
            body.append("")
            body.append(f"_{date}_")
        body.append("")
        content = (d.get("content") or "").rstrip()
        if content:
            body.append(content)
        body.append("")
    return "\n".join(body)
