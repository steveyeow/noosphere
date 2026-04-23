"""Index a corpus: chunk all documents and generate embeddings.

Supports incremental indexing via content hashes — only re-embeds
documents whose content has changed since last indexing.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

import numpy as np

from noosphere.core.db import get_conn, is_pg, pg_binary
from noosphere.core.corpus import update_corpus, get_corpus
from noosphere.core.chunker import chunk_document
from noosphere.core.embeddings import get_embedder, vector_to_blob


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def index_corpus(
    corpus_id: str,
    *,
    provider: str = "",
    on_progress=None,
    force: bool = False,
    chunk_strategy: str = "",
) -> dict:
    """Chunk and embed documents in a corpus.

    Args:
        corpus_id: The corpus to index.
        provider: Embedding provider name (auto-detect if empty).
        on_progress: Optional callback(stage, current, total).
        force: If True, re-index all documents regardless of content hash.
        chunk_strategy: Override the corpus chunk_strategy setting.

    Returns:
        dict with chunk_count, skipped, and embedding stats.
    """
    conn = get_conn()
    update_corpus(corpus_id, status="indexing")

    if not chunk_strategy:
        corpus = get_corpus(corpus_id)
        chunk_strategy = (corpus.get("chunk_strategy") if corpus else None) or "paragraph"

    # Skip source_kind='system' — auto-generated metadata (manifest doc)
    # isn't retrieval fodder; its purpose is display in the Wiki section and
    # exposure via /describe. Indexing it would surface it in ask/search
    # results, which pollutes answers with "here's what this KB is about"
    # text instead of actual content.
    docs = conn.execute(
        "SELECT id, title, content, doc_type, date, content_hash, indexed_at FROM documents "
        "WHERE corpus_id=? AND COALESCE(source_kind,'user_original') != 'system'",
        (corpus_id,),
    ).fetchall()

    if not docs:
        update_corpus(corpus_id, status="ready", chunk_count=0)
        return {"chunk_count": 0, "skipped": 0}

    # Indexing: probe for a working provider (primary Gemini → OpenAI → Zhipu).
    # Retrieval passes an explicit provider (from corpus.embedding_model) so the
    # probe is skipped there and dim compatibility is preserved.
    embedder = get_embedder(provider)
    now = _now()

    docs_to_index = []
    skipped = 0
    for doc in docs:
        current_hash = _content_hash(doc["content"])
        if not force and doc["content_hash"] == current_hash and doc["indexed_at"]:
            skipped += 1
            continue
        docs_to_index.append((doc, current_hash))

    if force:
        conn.execute("DELETE FROM chunks WHERE corpus_id=?", (corpus_id,))
        _sync_fts_delete_corpus(conn, corpus_id)
        conn.commit()

    all_chunks = []
    for doc, doc_hash in docs_to_index:
        conn.execute("DELETE FROM chunks WHERE document_id=?", (doc["id"],))
        _sync_fts_delete_doc(conn, doc["id"])

        chunks = chunk_document(doc["content"], strategy=chunk_strategy)
        for ch in chunks:
            ch["document_id"] = doc["id"]
            ch["document_title"] = doc["title"]
            ch["document_type"] = doc["doc_type"] or ""
            ch["document_date"] = doc["date"] or ""
            ch["_content_hash"] = doc_hash
        all_chunks.extend(chunks)

    conn.commit()

    if on_progress:
        on_progress("chunking", len(all_chunks), len(all_chunks))

    if not all_chunks:
        total = conn.execute(
            "SELECT COUNT(*) as n FROM chunks WHERE corpus_id=?", (corpus_id,)
        ).fetchone()["n"]
        update_corpus(corpus_id, status="ready", chunk_count=total,
                      embedding_model=embedder.model_name(), embedding_dim=embedder.dim())
        if on_progress:
            on_progress("done", 0, 0)
        return {"chunk_count": total, "skipped": skipped, "embedded": 0,
                "embedding_model": embedder.model_name(), "dim": embedder.dim()}

    texts = [ch["text"] for ch in all_chunks]
    batch_size = 100
    all_vectors = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        vecs = embedder.embed(batch)
        all_vectors.append(vecs)
        if on_progress:
            on_progress("embedding", min(i + batch_size, len(texts)), len(texts))

    vectors = np.vstack(all_vectors)
    norms = np.linalg.norm(vectors, axis=1)
    dim = embedder.dim()

    hashes_to_update: dict[str, str] = {}

    for idx, ch in enumerate(all_chunks):
        chunk_id = uuid.uuid4().hex[:12]
        meta = {
            "section": "",
            "document_title": ch["document_title"],
            "document_date": ch["document_date"],
        }
        conn.execute(
            """INSERT INTO chunks
               (id, corpus_id, document_id, chunk_index, text,
                char_start, char_end, vector, dim, norm, metadata_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                chunk_id, corpus_id, ch["document_id"], ch["chunk_index"],
                ch["text"], ch["char_start"], ch["char_end"],
                pg_binary(vector_to_blob(vectors[idx])), dim, float(norms[idx]),
                json.dumps(meta), now,
            ),
        )
        _sync_fts_insert(conn, chunk_id, ch["text"])
        hashes_to_update[ch["document_id"]] = ch["_content_hash"]

    for doc_id, doc_hash in hashes_to_update.items():
        conn.execute(
            "UPDATE documents SET content_hash=?, indexed_at=? WHERE id=?",
            (doc_hash, now, doc_id),
        )

    conn.commit()

    total_chunks = conn.execute(
        "SELECT COUNT(*) as n FROM chunks WHERE corpus_id=?", (corpus_id,)
    ).fetchone()["n"]

    update_corpus(
        corpus_id,
        status="ready",
        chunk_count=total_chunks,
        embedding_model=embedder.model_name(),
        embedding_dim=dim,
    )

    # Post-indexing hook: auto-fill manifest if it's still empty. Fires once
    # per corpus (no-op if `task_types` is already set), so owner customizations
    # are preserved. Silent on LLM failure — indexing itself already succeeded.
    try:
        from noosphere.core.manifest_autofill import autofill_if_empty
        autofill_if_empty(corpus_id)
    except Exception:
        pass

    if on_progress:
        on_progress("done", len(all_chunks), len(all_chunks))

    return {
        "chunk_count": total_chunks,
        "embedded": len(all_chunks),
        "skipped": skipped,
        "embedding_model": embedder.model_name(),
        "dim": dim,
    }


# ── FTS sync helpers ────────────────────────────────────────────────
# SQLite: maintain FTS5 virtual table (chunks_fts)
# PostgreSQL: maintain tsvector column (chunks.tsv)

def _sync_fts_insert(conn, chunk_id: str, text: str):
    """Update full-text index after inserting a chunk."""
    try:
        if is_pg():
            conn.execute(
                "UPDATE chunks SET tsv = to_tsvector('english', ?) WHERE id=?",
                (text, chunk_id),
            )
        else:
            row = conn.execute("SELECT rowid FROM chunks WHERE id=?", (chunk_id,)).fetchone()
            if row:
                conn.execute("INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)", (row["rowid"], text))
    except Exception:
        logger.warning("FTS insert failed for chunk %s", chunk_id, exc_info=True)


def _sync_fts_delete_doc(conn, doc_id: str):
    """Remove FTS entries for all chunks of a document."""
    if is_pg():
        return  # PG: chunks are deleted directly, tsv goes with them
    try:
        rows = conn.execute("SELECT rowid, text FROM chunks WHERE document_id=?", (doc_id,)).fetchall()
        for r in rows:
            conn.execute(
                "INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', ?, ?)",
                (r["rowid"], r["text"]),
            )
    except Exception:
        logger.warning("FTS delete failed for document %s", doc_id, exc_info=True)


def _sync_fts_delete_corpus(conn, corpus_id: str):
    """Remove FTS entries for all chunks of a corpus."""
    if is_pg():
        return  # PG: chunks are deleted directly, tsv goes with them
    try:
        rows = conn.execute("SELECT rowid, text FROM chunks WHERE corpus_id=?", (corpus_id,)).fetchall()
        for r in rows:
            conn.execute(
                "INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', ?, ?)",
                (r["rowid"], r["text"]),
            )
    except Exception:
        logger.warning("FTS delete failed for corpus %s", corpus_id, exc_info=True)
