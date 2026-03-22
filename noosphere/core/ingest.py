"""Ingestion pipeline — read files, fetch URLs, store as documents."""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from noosphere.core.db import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _word_count(text: str) -> int:
    return len(text.split())


def _extract_markdown_title(text: str) -> str:
    for line in text.split("\n", 20):
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _extract_markdown_metadata(text: str) -> tuple[dict, str]:
    """Extract YAML front-matter if present, return (metadata, body)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta = {}
    for line in parts[1].strip().split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip().strip('"').strip("'")
    return meta, parts[2]


def _html_to_markdown(html: str) -> str:
    """Convert HTML to readable markdown-like text."""
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<nav[^>]*>.*?</nav>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<footer[^>]*>.*?</footer>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<header[^>]*>.*?</header>', '', text, flags=re.DOTALL | re.IGNORECASE)

    text = re.sub(r'<h1[^>]*>(.*?)</h1>', r'\n# \1\n', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<h2[^>]*>(.*?)</h2>', r'\n## \1\n', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<h3[^>]*>(.*?)</h3>', r'\n### \1\n', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1\n', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)

    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&quot;', '"', text)
    text = re.sub(r'&#\d+;', '', text)

    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def ingest_directory(
    corpus_id: str,
    directory: str | Path,
    *,
    doc_type: str = "doc",
    file_extensions: tuple[str, ...] = (".md", ".txt", ".text"),
) -> list[dict]:
    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")

    files = sorted(
        f for f in directory.rglob("*")
        if f.is_file() and f.suffix.lower() in file_extensions
    )
    if not files:
        raise ValueError(f"No files with extensions {file_extensions} found in {directory}")

    docs = []
    for filepath in files:
        doc = ingest_file(corpus_id, filepath, doc_type=doc_type)
        if doc:
            docs.append(doc)

    _update_corpus_counts(corpus_id)
    return docs


def ingest_file(
    corpus_id: str,
    filepath: str | Path,
    *,
    doc_type: str = "doc",
) -> dict | None:
    filepath = Path(filepath)
    if not filepath.is_file():
        return None

    content = filepath.read_text(encoding="utf-8", errors="replace")
    if not content.strip():
        return None

    metadata, body = _extract_markdown_metadata(content)
    title = metadata.get("title") or _extract_markdown_title(body) or filepath.stem
    date = metadata.get("date", "")
    tags = metadata.get("tags", "")
    if isinstance(tags, str) and tags:
        tags = [t.strip() for t in tags.split(",")]
    elif not tags:
        tags = []

    return ingest_text(corpus_id, title=title, content=body, doc_type=doc_type, date=date, tags=tags, metadata=metadata)


def ingest_text(
    corpus_id: str,
    *,
    title: str,
    content: str,
    doc_type: str = "doc",
    date: str = "",
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> dict:
    """Ingest raw text content as a document."""
    doc_id = uuid.uuid4().hex[:12]
    wc = _word_count(content)
    now = _now()

    conn = get_conn()
    conn.execute(
        """INSERT INTO documents
           (id, corpus_id, title, content, doc_type, date,
            word_count, tags, metadata_json, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            doc_id, corpus_id, title, content, doc_type, date,
            wc, json.dumps(tags or []), json.dumps(metadata or {}), now,
        ),
    )
    conn.commit()
    _update_corpus_counts(corpus_id)

    return {
        "id": doc_id,
        "corpus_id": corpus_id,
        "title": title,
        "doc_type": doc_type,
        "date": date,
        "word_count": wc,
    }


def ingest_url(corpus_id: str, url: str, *, doc_type: str = "blog") -> dict:
    """Fetch a URL, convert HTML to markdown, and ingest as a document."""
    import httpx

    resp = httpx.get(url, follow_redirects=True, timeout=30, headers={
        "User-Agent": "Noosphere/0.1 (knowledge-ingestion)"
    })
    resp.raise_for_status()
    html = resp.text

    title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)
    title = title_match.group(1).strip() if title_match else url.split("/")[-1]

    body = _html_to_markdown(html)
    if not body.strip():
        raise ValueError(f"No readable content extracted from {url}")

    return ingest_text(
        corpus_id, title=title, content=body, doc_type=doc_type,
        metadata={"source_url": url},
    )



def _update_corpus_counts(corpus_id: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as cnt, COALESCE(SUM(word_count),0) as wc FROM documents WHERE corpus_id=?",
        (corpus_id,),
    ).fetchone()
    conn.execute(
        "UPDATE corpora SET document_count=?, word_count=?, updated_at=? WHERE id=?",
        (row["cnt"], row["wc"], _now(), corpus_id),
    )
    conn.commit()


def update_document(
    doc_id: str,
    *,
    title: str | None = None,
    content: str | None = None,
) -> dict | None:
    """Update a document's title and/or content. Re-calculates word count if content changes."""
    conn = get_conn()
    doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not doc:
        return None

    new_title = title if title is not None else doc["title"]
    new_content = content if content is not None else doc["content"]
    new_wc = _word_count(new_content) if content is not None else doc["word_count"]

    conn.execute(
        "UPDATE documents SET title=?, content=?, word_count=? WHERE id=?",
        (new_title, new_content, new_wc, doc_id),
    )
    conn.commit()

    if content is not None:
        conn.execute("DELETE FROM chunks WHERE document_id=?", (doc_id,))
        conn.commit()

    _update_corpus_counts(doc["corpus_id"])
    return dict(conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone())


def delete_document(doc_id: str) -> bool:
    conn = get_conn()
    doc = conn.execute("SELECT corpus_id FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not doc:
        return False
    corpus_id = doc["corpus_id"]
    conn.execute("DELETE FROM chunks WHERE document_id=?", (doc_id,))
    conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    conn.commit()
    _update_corpus_counts(corpus_id)
    return True


def get_documents(corpus_id: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM documents WHERE corpus_id=? ORDER BY date DESC, title ASC",
        (corpus_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_document(doc_id: str) -> dict | None:
    row = get_conn().execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    return dict(row) if row else None
