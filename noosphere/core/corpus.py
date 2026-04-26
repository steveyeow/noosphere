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


LOCAL_OWNER_ID = "local"  # sentinel owner_id for self-hosted single-user mode


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
    owner_id: str = "",
    org_id: str = "",
) -> dict:
    """Create a corpus. Owner XOR org scope — exactly one must be set.

    If both ``owner_id`` and ``org_id`` are empty, defaults to the self-hosted
    sentinel owner (``LOCAL_OWNER_ID``) so the row satisfies the corpora XOR
    constraint. Pass ``org_id`` (and leave ``owner_id`` empty) to create a
    team-scoped corpus.
    """
    if owner_id and org_id:
        raise ValueError("create_corpus: owner_id and org_id are mutually exclusive")
    if not owner_id and not org_id:
        owner_id = LOCAL_OWNER_ID

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
            owner_id, org_id, status, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            corpus_id, name, slug, description, author_name, author_url,
            language, license_, json.dumps(tags or []), access_level,
            source_type, source_url,
            embedding_model, embedding_dim,
            owner_id or None, org_id or None, "draft", now, now,
        ),
    )
    conn.commit()
    # Profile embedding for the discovery graph. Best-effort: fires off
    # an embed call against the configured provider so the new corpus
    # gets edges in the network view immediately. Never raises into the
    # create path — if the embedder is misconfigured / network is down,
    # the corpus is still created and graph just falls back to tag
    # overlap until the next backfill / update. See corpus_embedding.py.
    try:
        from noosphere.core.corpus_embedding import update_corpus_embedding
        update_corpus_embedding(corpus_id)
    except Exception:
        pass
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


def list_corpora(*, include_private: bool = False) -> list[dict]:
    if include_private:
        rows = get_conn().execute(
            "SELECT * FROM corpora ORDER BY updated_at DESC"
        ).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT * FROM corpora WHERE access_level != 'private' ORDER BY updated_at DESC"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_user_corpora(owner_id: str) -> list[dict]:
    """List corpora owned by a specific user (cloud multi-tenant)."""
    rows = get_conn().execute(
        "SELECT * FROM corpora WHERE owner_id=? ORDER BY updated_at DESC",
        (owner_id,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_corpus(corpus_id: str, **fields) -> dict | None:
    conn = get_conn()
    allowed = {
        "name", "description", "author_name", "author_url",
        "language", "license", "tags", "access_level", "status",
        "document_count", "chunk_count", "word_count",
        "embedding_model", "embedding_dim",
        "chunk_strategy", "stale_threshold_days", "pricing_json",
        "owner_id", "owned_handles",
        "task_types", "samples", "autonomy_level",
        "calibration_policy", "license_terms",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_corpus(corpus_id)

    for list_key in ("tags", "owned_handles", "task_types", "samples"):
        if list_key in updates and isinstance(updates[list_key], list):
            updates[list_key] = json.dumps(updates[list_key])
    for dict_key in ("calibration_policy", "license_terms"):
        if dict_key in updates and isinstance(updates[dict_key], dict):
            updates[dict_key] = json.dumps(updates[dict_key])

    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [corpus_id]
    conn.execute(f"UPDATE corpora SET {set_clause} WHERE id=?", values)
    conn.commit()
    # Recompute the corpus profile embedding when fields that feed the
    # profile text change — name, description, tags. Other column edits
    # (status flips, document_count, etc.) don't change the corpus's
    # semantic identity, so skip the embed call to save the API hit.
    _profile_fields = {"name", "description", "tags"}
    if _profile_fields & set(updates.keys()):
        try:
            from noosphere.core.corpus_embedding import update_corpus_embedding
            update_corpus_embedding(corpus_id)
        except Exception:
            pass
    return get_corpus(corpus_id)


def delete_corpus(corpus_id: str) -> bool:
    conn = get_conn()
    session_ids = conn.execute(
        "SELECT id FROM chat_sessions WHERE corpus_id=?", (corpus_id,)
    ).fetchall()
    for row in session_ids:
        conn.execute("DELETE FROM chat_messages WHERE session_id=?", (row["id"],))
    conn.execute("DELETE FROM chat_sessions WHERE corpus_id=?", (corpus_id,))
    conn.execute("DELETE FROM chunks WHERE corpus_id=?", (corpus_id,))
    conn.execute("DELETE FROM documents WHERE corpus_id=?", (corpus_id,))
    conn.execute("DELETE FROM access_tokens WHERE corpus_id=?", (corpus_id,))
    conn.execute("DELETE FROM query_logs WHERE corpus_id=?", (corpus_id,))
    cur = conn.execute("DELETE FROM corpora WHERE id=?", (corpus_id,))
    conn.commit()
    return cur.rowcount > 0


def _row_to_dict(row) -> dict:
    d = dict(row)
    for key in ("tags", "owned_handles", "task_types", "samples"):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    for key in ("calibration_policy", "license_terms"):
        if key in d and isinstance(d[key], str) and d[key]:
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    # The corpus profile vector + norm are backend-only fields used by
    # the discovery graph. Returning the raw bytes from /corpora makes
    # FastAPI's JSON encoder choke (it tries to UTF-8 decode the float32
    # blob), and the frontend has no use for them anyway. Strip here so
    # every consumer of `get_corpus` / `list_corpora` gets a clean dict.
    # `load_corpus_vectors` queries the column directly with explicit SQL
    # so this strip doesn't affect the graph computation path.
    d.pop("corpus_vector", None)
    d.pop("corpus_vector_norm", None)
    return d


def source_composition(corpus_id: str) -> dict[str, float]:
    """Rollup of documents by source_kind. Returns ratios that sum to 1.0.

    External-only documents (source_kind starting with 'external_') and
    owner-authored documents are both counted — this is a provenance signal
    about the corpus mix, not a visibility filter.
    """
    rows = get_conn().execute(
        "SELECT source_kind, COUNT(*) AS n FROM documents "
        "WHERE corpus_id=? GROUP BY source_kind",
        (corpus_id,),
    ).fetchall()
    total = sum(r["n"] for r in rows) or 0
    if total == 0:
        return {}
    return {r["source_kind"] or "unknown": round(r["n"] / total, 4) for r in rows}
