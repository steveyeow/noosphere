"""Ingestion pipeline — read files, fetch URLs, store as documents."""

import hashlib
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


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


SUPPORTED_FILE_EXTENSIONS = (".md", ".txt", ".text", ".pdf", ".docx", ".csv", ".json", ".jsonl", ".html", ".htm")


def _extract_pdf_text(raw: bytes) -> str:
    import fitz
    doc = fitz.open(stream=raw, filetype="pdf")
    pages = [page.get_text() for page in doc]
    doc.close()
    return "\n\n".join(pages)


def _extract_docx_text(raw: bytes) -> str:
    import io as _io
    from docx import Document
    doc = Document(_io.BytesIO(raw))
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _extract_csv_text(content: str) -> str:
    import csv
    import io as _io
    reader = csv.reader(_io.StringIO(content))
    rows = list(reader)
    if not rows:
        return ""
    header = rows[0]
    lines = []
    for row in rows[1:]:
        entry = "; ".join(f"{header[i]}: {row[i]}" for i in range(min(len(header), len(row))) if row[i].strip())
        if entry:
            lines.append(entry)
    return "\n".join(lines)


def _extract_json_text(content: str) -> str:
    data = json.loads(content)
    if isinstance(data, list):
        parts = []
        for item in data:
            if isinstance(item, dict):
                parts.append("\n".join(f"{k}: {v}" for k, v in item.items() if isinstance(v, (str, int, float))))
            else:
                parts.append(str(item))
        return "\n\n".join(parts)
    elif isinstance(data, dict):
        return "\n".join(f"{k}: {v}" for k, v in data.items() if isinstance(v, (str, int, float)))
    return str(data)


def ingest_directory(
    corpus_id: str,
    directory: str | Path,
    *,
    doc_type: str = "doc",
    file_extensions: tuple[str, ...] = SUPPORTED_FILE_EXTENSIONS,
) -> list[dict]:
    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")

    files = sorted(
        f for f in directory.rglob("*")
        if f.is_file() and f.suffix.lower() in file_extensions
    )
    if not files:
        raise ValueError(f"No supported files found in {directory}")

    docs = []
    for filepath in files:
        doc = ingest_file(corpus_id, filepath, doc_type=doc_type, base_dir=directory)
        if doc:
            docs.append(doc)

    _update_corpus_counts(corpus_id)
    return docs


def ingest_file(
    corpus_id: str,
    filepath: str | Path,
    *,
    doc_type: str = "doc",
    base_dir: str | Path | None = None,
) -> dict | None:
    filepath = Path(filepath)
    if not filepath.is_file():
        return None

    ext = filepath.suffix.lower()
    title = filepath.stem
    metadata: dict = {}
    body = ""

    # Binary formats
    if ext == ".pdf":
        raw = filepath.read_bytes()
        body = _extract_pdf_text(raw)
        doc_type = doc_type if doc_type != "doc" else "paper"
    elif ext == ".docx":
        raw = filepath.read_bytes()
        body = _extract_docx_text(raw)
    elif ext == ".csv":
        content = filepath.read_text(encoding="utf-8", errors="replace")
        body = _extract_csv_text(content)
        doc_type = doc_type if doc_type != "doc" else "data"
    elif ext in (".json", ".jsonl"):
        content = filepath.read_text(encoding="utf-8", errors="replace")
        if ext == ".jsonl":
            lines = [json.loads(line) for line in content.strip().splitlines() if line.strip()]
            body = _extract_json_text(json.dumps(lines))
        else:
            body = _extract_json_text(content)
        doc_type = doc_type if doc_type != "doc" else "data"
    else:
        # Text formats (md, txt, html, etc.)
        content = filepath.read_text(encoding="utf-8", errors="replace")
        if not content.strip():
            return None
        metadata, body = _extract_markdown_metadata(content)
        title = metadata.get("title") or _extract_markdown_title(body) or filepath.stem

    if not body or not body.strip():
        return None

    date = metadata.get("date", "")
    tags = metadata.get("tags", "")
    if isinstance(tags, str) and tags:
        tags = [t.strip() for t in tags.split(",")]
    elif not tags:
        tags = []

    if base_dir:
        try:
            rel = str(filepath.relative_to(base_dir))
        except ValueError:
            rel = str(filepath)
        metadata["source_path"] = rel

    return ingest_text(corpus_id, title=title, content=body, doc_type=doc_type, date=date, tags=tags, metadata=metadata)


def ingest_text(
    corpus_id: str,
    *,
    title: str,
    content: str,
    doc_type: str = "doc",
    source_kind: str = "user_original",
    author_entity_id: str | None = None,
    participant_entity_ids: list[str] | None = None,
    date: str = "",
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> dict:
    """Ingest raw text content as a document.

    source_kind: one of "user_original", "user_capture", "external_public",
    "external_subscription". Determines access-filter behavior when a non-owner
    caller queries the corpus (see Principle 3 in project_noosphere_ingestion).
    """
    doc_id = uuid.uuid4().hex[:12]
    wc = _word_count(content)
    c_hash = _content_hash(content)
    now = _now()

    conn = get_conn()
    conn.execute(
        """INSERT INTO documents
           (id, corpus_id, title, content, doc_type, date,
            word_count, content_hash, source_kind, author_entity_id,
            participant_entity_ids, tags, metadata_json, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            doc_id, corpus_id, title, content, doc_type, date,
            wc, c_hash, source_kind, author_entity_id,
            json.dumps(participant_entity_ids or []),
            json.dumps(tags or []), json.dumps(metadata or {}), now,
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
        "source_kind": source_kind,
    }


def _url_matches_owned_handles(url: str, owned_handles: list[str]) -> bool:
    """Return True if URL matches any of the corpus owner's declared handles/domains.

    Handle forms:
      "twitter.com/username"         — match host + path prefix
      "mysite.com" or "mysite.com/*" — match host (incl. subdomains)
      "blog.me.dev"                  — match exact host
    """
    from urllib.parse import urlparse
    try:
        p = urlparse(url)
    except Exception:
        return False
    host = (p.hostname or "").lower()
    path = p.path or ""
    for handle in owned_handles or []:
        h = handle.strip().lower().rstrip("*").rstrip("/")
        if not h:
            continue
        if "/" in h:
            h_host, _, h_path = h.partition("/")
            if (host == h_host or host.endswith("." + h_host)) and path.startswith("/" + h_path):
                return True
        else:
            if host == h or host.endswith("." + h):
                return True
    return False


def ingest_url(
    corpus_id: str,
    url: str,
    *,
    doc_type: str = "blog",
    source_kind: str | None = None,
) -> dict:
    """Fetch a URL, convert HTML to markdown, and ingest as a document.

    If source_kind is None, defaults to "external_public" unless the URL
    matches the corpus owner's owned_handles list (then "user_original").
    """
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

    if source_kind is None:
        from noosphere.core.corpus import get_corpus
        corpus = get_corpus(corpus_id) or {}
        owned = corpus.get("owned_handles") or []
        if isinstance(owned, str):
            try:
                owned = json.loads(owned)
            except (json.JSONDecodeError, TypeError):
                owned = []
        source_kind = "user_original" if _url_matches_owned_handles(url, owned) else "external_public"

    # Free author detection from <meta> tags — attaches author entity for
    # external content so entity pages can aggregate "what Lenny wrote".
    author_entity_id: str | None = None
    if source_kind.startswith("external_"):
        from noosphere.core.entities import detect_html_author, upsert_entity
        author_name = detect_html_author(html)
        if author_name:
            author_entity_id = upsert_entity(corpus_id, "person", author_name)

    return ingest_text(
        corpus_id, title=title, content=body, doc_type=doc_type,
        source_kind=source_kind,
        author_entity_id=author_entity_id,
        metadata={"source_url": url},
    )



def _update_corpus_counts(corpus_id: str):
    """Recompute user-visible document/word counts for the corpus row.

    Excludes `source_kind='system'` (auto-generated manifest doc) so
    document_count reflects user-authored + imported content only. The
    manifest is still visible in listings and the Wiki pin, but it
    shouldn't inflate "you have N documents" stats shown to the owner.
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as cnt, COALESCE(SUM(word_count),0) as wc FROM documents "
        "WHERE corpus_id=? AND COALESCE(source_kind,'user_original') != 'system'",
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


# ── Incremental sync ────────────────────────────────────────────────

def sync_directory(
    corpus_id: str,
    directory: str | Path,
    *,
    doc_type: str = "doc",
    prune: bool = False,
    file_extensions: tuple[str, ...] = SUPPORTED_FILE_EXTENSIONS,
) -> dict:
    """Sync a directory to a corpus: add new files, update changed, optionally prune deleted.

    Returns dict with counts: new, updated, pruned, unchanged.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")

    conn = get_conn()

    existing_docs = conn.execute(
        "SELECT id, content_hash, metadata_json FROM documents WHERE corpus_id=?",
        (corpus_id,),
    ).fetchall()

    path_to_doc: dict[str, dict] = {}
    for doc in existing_docs:
        try:
            meta = json.loads(doc["metadata_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            meta = {}
        sp = meta.get("source_path", "")
        if sp:
            path_to_doc[sp] = dict(doc)

    files = sorted(
        f for f in directory.rglob("*")
        if f.is_file() and f.suffix.lower() in file_extensions
    )

    new_count = 0
    updated_count = 0
    unchanged_count = 0
    pruned_count = 0

    seen_paths: set[str] = set()

    for filepath in files:
        try:
            rel = str(filepath.relative_to(directory))
        except ValueError:
            rel = str(filepath)

        seen_paths.add(rel)
        content = filepath.read_text(encoding="utf-8", errors="replace")
        if not content.strip():
            continue

        file_hash = _content_hash(content)

        if rel in path_to_doc:
            existing = path_to_doc[rel]
            if existing.get("content_hash") == file_hash:
                unchanged_count += 1
                continue

            metadata, body = _extract_markdown_metadata(content)
            title = metadata.get("title") or _extract_markdown_title(body) or filepath.stem
            metadata["source_path"] = rel

            conn.execute(
                "UPDATE documents SET title=?, content=?, word_count=?, content_hash=?, "
                "metadata_json=?, indexed_at=NULL WHERE id=?",
                (title, body, _word_count(body), _content_hash(body),
                 json.dumps(metadata), existing["id"]),
            )
            conn.execute("DELETE FROM chunks WHERE document_id=?", (existing["id"],))
            conn.commit()
            updated_count += 1
        else:
            doc = ingest_file(corpus_id, filepath, doc_type=doc_type, base_dir=directory)
            if doc:
                new_count += 1

    if prune:
        for rel_path, doc in path_to_doc.items():
            if rel_path not in seen_paths:
                delete_document(doc["id"])
                pruned_count += 1

    _update_corpus_counts(corpus_id)

    return {
        "new": new_count,
        "updated": updated_count,
        "unchanged": unchanged_count,
        "pruned": pruned_count,
    }
