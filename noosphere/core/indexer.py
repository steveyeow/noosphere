"""Index a corpus: chunk all documents and generate embeddings."""

import json
import uuid
from datetime import datetime, timezone

import numpy as np

from noosphere.core.db import get_conn
from noosphere.core.corpus import update_corpus
from noosphere.core.chunker import chunk_document
from noosphere.core.embeddings import get_embedder, vector_to_blob


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def index_corpus(corpus_id: str, *, provider: str = "", on_progress=None) -> dict:
    """Chunk and embed all documents in a corpus.

    Args:
        corpus_id: The corpus to index.
        provider: Embedding provider name (auto-detect if empty).
        on_progress: Optional callback(stage, current, total).

    Returns:
        dict with chunk_count and embedding stats.
    """
    conn = get_conn()
    update_corpus(corpus_id, status="indexing")

    conn.execute("DELETE FROM chunks WHERE corpus_id=?", (corpus_id,))
    conn.commit()

    docs = conn.execute(
        "SELECT id, title, content, doc_type, date FROM documents WHERE corpus_id=?",
        (corpus_id,),
    ).fetchall()

    if not docs:
        update_corpus(corpus_id, status="ready", chunk_count=0)
        return {"chunk_count": 0}

    embedder = get_embedder(provider)

    all_chunks = []
    for doc in docs:
        chunks = chunk_document(doc["content"])
        for ch in chunks:
            ch["document_id"] = doc["id"]
            ch["document_title"] = doc["title"]
            ch["document_type"] = doc["doc_type"] or ""
            ch["document_date"] = doc["date"] or ""
        all_chunks.extend(chunks)

    if on_progress:
        on_progress("chunking", len(all_chunks), len(all_chunks))

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

    now = _now()
    dim = embedder.dim()

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
                vector_to_blob(vectors[idx]), dim, float(norms[idx]),
                json.dumps(meta), now,
            ),
        )

    conn.commit()

    update_corpus(
        corpus_id,
        status="ready",
        chunk_count=len(all_chunks),
        embedding_model=embedder.model_name(),
        embedding_dim=dim,
    )

    if on_progress:
        on_progress("done", len(all_chunks), len(all_chunks))

    return {"chunk_count": len(all_chunks), "embedding_model": embedder.model_name(), "dim": dim}
