"""Corpus CRUD operations."""

import json
import re
import uuid
from datetime import datetime, timezone

from noosphere.core.db import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


def create_corpus(
    name: str,
    *,
    description: str = "",
    author_name: str = "",
    author_url: str = "",
    language: str = "en",
    license_: str = "personal-use",
    tags: list[str] | None = None,
    access_level: str = "public",
    source_type: str = "manual",
    source_url: str = "",
    embedding_model: str = "",
    embedding_dim: int = 0,
) -> dict:
    conn = get_conn()
    corpus_id = uuid.uuid4().hex[:12]
    slug = _slugify(name)

    existing = conn.execute("SELECT id FROM corpora WHERE slug=?", (slug,)).fetchone()
    if existing:
        slug = f"{slug}-{corpus_id[:6]}"

    now = _now()
    conn.execute(
        """INSERT INTO corpora
           (id, name, slug, description, author_name, author_url,
            language, license, tags, access_level,
            source_type, source_url,
            embedding_model, embedding_dim,
            status, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            corpus_id, name, slug, description, author_name, author_url,
            language, license_, json.dumps(tags or []), access_level,
            source_type, source_url,
            embedding_model, embedding_dim,
            "draft", now, now,
        ),
    )
    conn.commit()
    return get_corpus(corpus_id)


def get_corpus(corpus_id: str) -> dict | None:
    row = get_conn().execute("SELECT * FROM corpora WHERE id=?", (corpus_id,)).fetchone()
    if not row:
        return None
    return _row_to_dict(row)


def get_corpus_by_slug(slug: str) -> dict | None:
    row = get_conn().execute("SELECT * FROM corpora WHERE slug=?", (slug,)).fetchone()
    if not row:
        return None
    return _row_to_dict(row)


def list_corpora() -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM corpora WHERE access_level != 'private' ORDER BY updated_at DESC"
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_corpus(corpus_id: str, **fields) -> dict | None:
    conn = get_conn()
    allowed = {
        "name", "description", "author_name", "author_url",
        "language", "license", "tags", "access_level", "status",
        "document_count", "chunk_count", "word_count",
        "embedding_model", "embedding_dim",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_corpus(corpus_id)

    if "tags" in updates and isinstance(updates["tags"], list):
        updates["tags"] = json.dumps(updates["tags"])

    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [corpus_id]
    conn.execute(f"UPDATE corpora SET {set_clause} WHERE id=?", values)
    conn.commit()
    return get_corpus(corpus_id)


def delete_corpus(corpus_id: str) -> bool:
    conn = get_conn()
    conn.execute("DELETE FROM chunks WHERE corpus_id=?", (corpus_id,))
    conn.execute("DELETE FROM documents WHERE corpus_id=?", (corpus_id,))
    conn.execute("DELETE FROM access_tokens WHERE corpus_id=?", (corpus_id,))
    conn.execute("DELETE FROM query_logs WHERE corpus_id=?", (corpus_id,))
    cur = conn.execute("DELETE FROM corpora WHERE id=?", (corpus_id,))
    conn.commit()
    return cur.rowcount > 0


def _row_to_dict(row) -> dict:
    d = dict(row)
    for key in ("tags",):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return d
