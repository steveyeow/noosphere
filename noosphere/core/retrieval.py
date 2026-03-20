"""Semantic search with cosine similarity and citations.

Provides both direct (local) access and an abstract client interface
that consumers like Feynman can use. The client defaults to local mode
(direct SQLite queries) but can be switched to remote mode (HTTP API)
for distributed deployments — same interface, different backend.
"""

import json
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import numpy as np

from noosphere.core.db import get_conn
from noosphere.core.embeddings import get_embedder, blob_to_vector


# ── Abstract interface ──────────────────────────────────────────────

class RetrievalEngine(ABC):
    """Abstract retrieval interface — local or remote, same API."""

    @abstractmethod
    def search(self, corpus_id: str, query: str, *, top_k: int = 5) -> dict:
        ...

    @abstractmethod
    def list_corpora(self) -> list[dict]:
        ...

    @abstractmethod
    def get_document(self, doc_id: str) -> dict | None:
        ...


# ── Local implementation (direct SQLite) ────────────────────────────

class LocalRetrieval(RetrievalEngine):
    """Direct database access — zero latency, same process."""

    def __init__(self, provider: str = ""):
        self._provider = provider

    def search(self, corpus_id: str, query: str, *, top_k: int = 5) -> dict:
        return search_corpus(corpus_id, query, top_k=top_k, provider=self._provider)

    def list_corpora(self) -> list[dict]:
        from noosphere.core.corpus import list_corpora
        return list_corpora()

    def get_document(self, doc_id: str) -> dict | None:
        from noosphere.core.ingest import get_document
        return get_document(doc_id)


# ── Remote implementation (HTTP API) ────────────────────────────────

class RemoteRetrieval(RetrievalEngine):
    """HTTP client to a remote Noosphere server."""

    def __init__(self, base_url: str, api_key: str = ""):
        self._base = base_url.rstrip("/")
        self._key = api_key

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._key:
            h["Authorization"] = f"Bearer {self._key}"
        return h

    def search(self, corpus_id: str, query: str, *, top_k: int = 5) -> dict:
        import httpx
        resp = httpx.post(
            f"{self._base}/api/v1/corpora/{corpus_id}/search",
            headers=self._headers(),
            json={"query": query, "top_k": top_k},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def list_corpora(self) -> list[dict]:
        import httpx
        resp = httpx.get(f"{self._base}/api/v1/corpora", headers=self._headers(), timeout=15)
        resp.raise_for_status()
        return resp.json()

    def get_document(self, doc_id: str, corpus_id: str = "") -> dict | None:
        import httpx
        if corpus_id:
            url = f"{self._base}/api/v1/corpora/{corpus_id}/documents/{doc_id}"
        else:
            url = f"{self._base}/api/v1/corpora/_/documents/{doc_id}"
        resp = httpx.get(url, headers=self._headers(), timeout=15)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()


# ── Factory ─────────────────────────────────────────────────────────

def get_retrieval_engine(remote_url: str = "", api_key: str = "", provider: str = "") -> RetrievalEngine:
    """Get a retrieval engine — local by default, remote if URL is provided.

    Usage by consumers (e.g. Feynman):
        from noosphere.core.retrieval import get_retrieval_engine
        engine = get_retrieval_engine()                    # local mode
        engine = get_retrieval_engine("http://noosphere:8420")  # remote mode
        results = engine.search("my-corpus", "pricing strategy")
    """
    if remote_url:
        return RemoteRetrieval(remote_url, api_key)
    return LocalRetrieval(provider)


# ── Direct functions (used by API routes and local consumers) ───────

def search_corpus(
    corpus_id: str,
    query: str,
    *,
    top_k: int = 5,
    include_context: bool = True,
    provider: str = "",
) -> dict:
    """Semantic search over a corpus. Returns ranked results with citations."""
    start = time.time()
    conn = get_conn()

    if not provider:
        corpus_row = conn.execute("SELECT embedding_model FROM corpora WHERE id=?", (corpus_id,)).fetchone()
        if corpus_row and corpus_row["embedding_model"]:
            model = corpus_row["embedding_model"]
            if "gemini" in model:
                provider = "gemini"
            elif "openai" in model or "text-embedding" in model:
                provider = "openai"

    embedder = get_embedder(provider)
    query_vec = embedder.embed([query])[0]
    query_norm = np.linalg.norm(query_vec)
    if query_norm == 0:
        return {"results": [], "usage": {"latency_ms": 0}}

    rows = conn.execute(
        "SELECT * FROM chunks WHERE corpus_id=?", (corpus_id,)
    ).fetchall()

    if not rows:
        return {"results": [], "usage": {"latency_ms": 0}}

    scored = []
    for row in rows:
        chunk_vec = blob_to_vector(row["vector"], row["dim"])
        chunk_norm = row["norm"]
        if chunk_norm == 0:
            continue
        score = float(np.dot(query_vec, chunk_vec) / (query_norm * chunk_norm))
        scored.append((score, row))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    results = []
    for score, row in top:
        doc_row = conn.execute(
            "SELECT title, doc_type, date FROM documents WHERE id=?",
            (row["document_id"],),
        ).fetchone()

        citation = {}
        if doc_row:
            citation = {
                "document_title": doc_row["title"],
                "document_id": row["document_id"],
                "document_type": doc_row["doc_type"] or "",
                "date": doc_row["date"] or "",
                "char_range": [row["char_start"], row["char_end"]],
            }

        meta = {}
        if row["metadata_json"]:
            try:
                meta = json.loads(row["metadata_json"])
            except (json.JSONDecodeError, TypeError):
                pass

        result = {
            "chunk_id": row["id"],
            "score": round(score, 4),
            "text": row["text"],
            "citation": citation,
        }
        if include_context and meta.get("section"):
            result["section"] = meta["section"]

        results.append(result)

    latency = int((time.time() - start) * 1000)

    _log_query(corpus_id, query, len(results), latency)

    return {
        "results": results,
        "usage": {"latency_ms": latency, "chunks_searched": len(rows)},
    }


def search_chunks(corpus_id: str, query_vec: np.ndarray, top_k: int = 5) -> list[dict]:
    """Lower-level vector search for library consumers."""
    conn = get_conn()
    query_norm = np.linalg.norm(query_vec)
    if query_norm == 0:
        return []

    rows = conn.execute(
        "SELECT * FROM chunks WHERE corpus_id=?", (corpus_id,)
    ).fetchall()

    scored = []
    for row in rows:
        chunk_vec = blob_to_vector(row["vector"], row["dim"])
        if row["norm"] == 0:
            continue
        score = float(np.dot(query_vec, chunk_vec) / (query_norm * row["norm"]))
        scored.append((score, dict(row)))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"score": s, **r} for s, r in scored[:top_k]]


def _log_query(corpus_id: str, query_text: str, result_count: int, latency_ms: int):
    try:
        conn = get_conn()
        conn.execute(
            "INSERT INTO query_logs (id, corpus_id, query_text, result_count, latency_ms, created_at) VALUES (?,?,?,?,?,?)",
            (uuid.uuid4().hex[:12], corpus_id, query_text, result_count, latency_ms, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    except Exception:
        pass
