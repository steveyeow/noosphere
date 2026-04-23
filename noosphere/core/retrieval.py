"""Hybrid search engine — keyword (FTS5) + vector + RRF fusion.

Provides both direct (local) access and an abstract client interface
that consumers like Feynman can use. The client defaults to local mode
(direct SQLite queries) but can be switched to remote mode (HTTP API)
for distributed deployments — same interface, different backend.
"""

import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

import numpy as np

from noosphere.core.db import get_conn, is_pg
from noosphere.core.embeddings import get_embedder, blob_to_vector


RRF_K = 60
SIMILARITY_DEDUP_THRESHOLD = 0.90
TYPE_DIVERSITY_CAP = 0.60
FRESHNESS_BOOST_PER_YEAR = 0.02
FRESHNESS_BOOST_MAX = 0.10
COMPILED_TRUTH_BOOST = 0.08  # Score boost for compiled concept notes (distilled knowledge)

# Caller identity gates source_kind filtering (Phase 1a: external callers only see originals).
# See project_noosphere_ingestion memory Principle 3.
# Allow-list semantics: anything not listed here is hidden from external callers.
# That means external_public, external_subscription, and peer_subscription
# (L3 Networked — can't resell content learned from peer KBs) are all filtered.
CALLER_OWNER = "owner"
CALLER_EXTERNAL = "external"
EXTERNAL_ALLOWED_SOURCE_KINDS = {"user_original", "user_capture"}


# ── Abstract interface ──────────────────────────────────────────────

class RetrievalEngine(ABC):
    """Abstract retrieval interface — local or remote, same API."""

    @abstractmethod
    def search(self, corpus_id: str, query: str, *, top_k: int = 5, caller: str = "owner") -> dict:
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

    def search(self, corpus_id: str, query: str, *, top_k: int = 5, caller: str = CALLER_OWNER) -> dict:
        return search_corpus(corpus_id, query, top_k=top_k, provider=self._provider, caller=caller)

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

    def search(self, corpus_id: str, query: str, *, top_k: int = 5, caller: str = "owner") -> dict:
        import httpx
        body: dict = {"query": query, "top_k": top_k}
        # Remote servers enforce caller server-side based on auth; the caller
        # hint here is advisory only (present for RetrievalEngine parity).
        if caller != "owner":
            body["caller"] = caller
        resp = httpx.post(
            f"{self._base}/api/v1/corpora/{corpus_id}/search",
            headers=self._headers(),
            json=body,
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


# ── Keyword search (FTS5 / tsvector) ───────────────────────────────

def _fts_available(conn) -> bool:
    """Check if full-text search is available."""
    if is_pg():
        # PG: check if tsv column exists on chunks
        try:
            row = conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='chunks' AND column_name='tsv'",
                (),
            ).fetchone()
            return row is not None
        except Exception:
            return False
    else:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts'"
        ).fetchone()
        return row is not None


def _keyword_search(corpus_id: str, query: str, *, limit: int = 30) -> list[dict]:
    """Full-text keyword search over chunks. Returns ranked chunk dicts."""
    conn = get_conn()
    if not _fts_available(conn):
        return []

    try:
        if is_pg():
            rows = conn.execute(
                """
                SELECT c.*, ts_rank(c.tsv, plainto_tsquery('english', ?)) AS fts_rank
                FROM chunks c
                WHERE c.corpus_id = ?
                  AND c.tsv @@ plainto_tsquery('english', ?)
                ORDER BY fts_rank DESC
                LIMIT ?
                """,
                (query, corpus_id, query, limit),
            ).fetchall()
        else:
            fts_query = _build_fts_query(query)
            rows = conn.execute(
                """
                SELECT c.*, chunks_fts.rank AS fts_rank
                FROM chunks_fts
                JOIN chunks c ON c.rowid = chunks_fts.rowid
                WHERE chunks_fts MATCH ?
                  AND c.corpus_id = ?
                ORDER BY chunks_fts.rank
                LIMIT ?
                """,
                (fts_query, corpus_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _build_fts_query(query: str) -> str:
    """Build an FTS5 query: quote individual terms and OR them."""
    tokens = query.strip().split()
    if not tokens:
        return '""'
    escaped = ['"' + t.replace('"', '""') + '"' for t in tokens]
    return " OR ".join(escaped)


# ── Vector search ───────────────────────────────────────────────────

def _vector_search(
    corpus_id: str,
    query_vec: np.ndarray,
    query_norm: float,
    *,
    limit: int = 30,
) -> list[dict]:
    """Cosine similarity search over chunk embeddings."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM chunks WHERE corpus_id=?", (corpus_id,)
    ).fetchall()

    if not rows:
        return []

    scored = []
    for row in rows:
        chunk_vec = blob_to_vector(row["vector"], row["dim"])
        chunk_norm = row["norm"]
        if chunk_norm == 0:
            continue
        score = float(np.dot(query_vec, chunk_vec) / (query_norm * chunk_norm))
        scored.append((score, dict(row)))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"_vector_score": s, **r} for s, r in scored[:limit]]


# ── RRF Fusion ──────────────────────────────────────────────────────

def _rrf_fuse(keyword_results: list[dict], vector_results: list[dict], *, k: int = RRF_K) -> list[dict]:
    """Reciprocal Rank Fusion: combine two ranked lists by chunk id."""
    scores: dict[str, float] = {}
    chunks: dict[str, dict] = {}

    for rank, item in enumerate(keyword_results):
        cid = item["id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
        chunks[cid] = item

    for rank, item in enumerate(vector_results):
        cid = item["id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
        if cid not in chunks:
            chunks[cid] = item

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    results = []
    for cid, score in ranked:
        entry = chunks[cid]
        entry["_rrf_score"] = round(score, 6)
        results.append(entry)

    return results


# ── Deduplication ───────────────────────────────────────────────────

def _deduplicate(
    results: list[dict],
    top_k: int,
    *,
    per_doc_chunks: int = 1,
) -> list[dict]:
    """Four-layer dedup: best-per-doc, cosine similarity, type diversity, freshness boost."""
    if not results:
        return []

    # Layer 1: best chunk per document
    doc_best: dict[str, dict] = {}
    for r in results:
        did = r["document_id"]
        if did not in doc_best:
            doc_best[did] = []
        doc_best[did].append(r)

    kept = []
    for did, doc_chunks in doc_best.items():
        doc_chunks.sort(key=lambda x: x.get("_rrf_score", 0), reverse=True)
        kept.extend(doc_chunks[:per_doc_chunks])

    kept.sort(key=lambda x: x.get("_rrf_score", 0), reverse=True)

    # Layer 2: cosine similarity dedup (compare chunk text embeddings)
    deduped = []
    seen_vecs = []
    for r in kept:
        if "vector" in r and r.get("dim"):
            try:
                vec = blob_to_vector(r["vector"], r["dim"])
                duplicate = False
                for sv in seen_vecs:
                    sim = float(np.dot(vec, sv) / (np.linalg.norm(vec) * np.linalg.norm(sv) + 1e-10))
                    if sim > SIMILARITY_DEDUP_THRESHOLD:
                        duplicate = True
                        break
                if duplicate:
                    continue
                seen_vecs.append(vec)
            except Exception:
                logger.debug("Cosine dedup skipped for chunk (vector decode failed)", exc_info=True)
        deduped.append(r)

    # Layer 3: type diversity cap
    type_counts: dict[str, int] = {}
    diverse = []
    max_per_type = max(1, int(top_k * TYPE_DIVERSITY_CAP))
    for r in deduped:
        doc_type = r.get("_doc_type", "")
        type_counts[doc_type] = type_counts.get(doc_type, 0) + 1
        if type_counts[doc_type] <= max_per_type:
            diverse.append(r)

    return diverse[:top_k]


# ── Freshness scoring ──────────────────────────────────────────────

def _apply_freshness(results: list[dict], corpus_updated_at: str, stale_threshold_days: int) -> list[dict]:
    """Add freshness metadata and optional score boost."""
    now = datetime.now(timezone.utc)
    try:
        datetime.fromisoformat(corpus_updated_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        pass

    for r in results:
        doc_date_str = r.get("_doc_date", "")
        freshness = {"corpus_last_updated": corpus_updated_at}

        if doc_date_str:
            try:
                doc_dt = datetime.fromisoformat(doc_date_str.replace("Z", "+00:00"))
                if doc_dt.tzinfo is None:
                    doc_dt = doc_dt.replace(tzinfo=timezone.utc)
                age_days = (now - doc_dt).days
                freshness["document_date"] = doc_date_str
                freshness["age_days"] = age_days
                freshness["stale"] = age_days > stale_threshold_days

                years_fresh = max(0, (stale_threshold_days - age_days) / 365.0)
                boost = min(years_fresh * FRESHNESS_BOOST_PER_YEAR, FRESHNESS_BOOST_MAX)
                r["_rrf_score"] = r.get("_rrf_score", 0) + boost
            except (ValueError, TypeError):
                freshness["stale"] = False
        else:
            freshness["stale"] = False

        r["_freshness"] = freshness

    return results


# ── Multi-query expansion ──────────────────────────────────────────

def _expand_query(query: str) -> list[str]:
    """Use a cheap LLM to generate 2-3 alternative phrasings of the query."""
    from noosphere.core.config import GEMINI_API_KEY, OPENAI_API_KEY

    prompt = (
        "Generate 2-3 alternative search queries for the following question. "
        "Return ONLY the queries, one per line, no numbering, no explanation.\n\n"
        f"Original: {query}"
    )

    if GEMINI_API_KEY:
        return _expand_via_gemini(prompt)
    if OPENAI_API_KEY:
        return _expand_via_openai(prompt)
    return []


def _expand_via_gemini(prompt: str) -> list[str]:
    import httpx
    from noosphere.core.config import GEMINI_API_KEY
    try:
        resp = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=10,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return [line.strip() for line in text.strip().split("\n") if line.strip()][:3]
    except Exception:
        return []


def _expand_via_openai(prompt: str) -> list[str]:
    import httpx
    from noosphere.core.config import OPENAI_API_KEY
    try:
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
                "temperature": 0.7,
            },
            timeout=10,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        return [line.strip() for line in text.strip().split("\n") if line.strip()][:3]
    except Exception:
        return []


# ── Main search function ───────────────────────────────────────────

def search_corpus(
    corpus_id: str,
    query: str,
    *,
    top_k: int = 5,
    include_context: bool = True,
    provider: str = "",
    agent_id: str = "",
    token_id: str | None = None,
    expand: bool = True,
    detail: str = "medium",
    caller: str = CALLER_OWNER,
    action: str = "ask",
) -> dict:
    """Hybrid search over a corpus: keyword + vector + RRF fusion + dedup + freshness.

    detail levels:
      low    — keyword-only, no expansion, fast
      medium — hybrid keyword+vector, expansion if corpus is large (default)
      high   — hybrid + forced expansion + more results + full context

    caller (Phase 1a source_kind filter):
      owner    — full access to all source_kinds (default, backward-compat)
      external — only user_original + user_capture chunks are returned;
                 external_public, external_subscription, and peer_subscription
                 (L3 Networked) are filtered out
    """
    start = time.time()
    conn = get_conn()

    # Normalize detail level
    detail = detail.lower() if detail else "medium"
    if detail not in ("low", "medium", "high"):
        detail = "medium"

    # Detail-level overrides
    if detail == "low":
        expand = False
        include_context = False
    elif detail == "high":
        expand = True
        include_context = True
        top_k = max(top_k, 10)

    corpus_row = conn.execute(
        "SELECT embedding_model, updated_at, stale_threshold_days FROM corpora WHERE id=?",
        (corpus_id,),
    ).fetchone()

    if not provider and corpus_row and corpus_row["embedding_model"]:
        model = corpus_row["embedding_model"]
        if "gemini" in model:
            provider = "gemini"
        elif model == "embedding-3" or "zhipu" in model or "glm" in model:
            provider = "zhipu"
        elif "openai" in model or "text-embedding" in model:
            provider = "openai"

    corpus_updated_at = corpus_row["updated_at"] if corpus_row else ""
    stale_threshold = (corpus_row["stale_threshold_days"] if corpus_row else None) or 365

    chunk_count = conn.execute(
        "SELECT COUNT(*) as n FROM chunks WHERE corpus_id=?", (corpus_id,)
    ).fetchone()["n"]

    if chunk_count == 0:
        _log_query(corpus_id, query, 0, 0, agent_id=agent_id, token_id=token_id, action=action)
        return {"results": [], "usage": {"latency_ms": 0, "chunks_searched": 0, "detail": detail}}

    queries = [query]
    if detail == "low":
        pass  # no expansion
    elif detail == "high" and chunk_count > 10:
        expansions = _expand_query(query)
        queries.extend(expansions)
    elif expand and top_k >= 3 and chunk_count > 50:
        expansions = _expand_query(query)
        queries.extend(expansions)

    fetch_limit = top_k * 3

    all_keyword = []
    all_vector = []

    use_vectors = detail != "low"
    has_embedder = False
    if use_vectors:
        try:
            embedder = get_embedder(provider)
            has_embedder = True
        except ValueError:
            pass

    for q in queries:
        kw = _keyword_search(corpus_id, q, limit=fetch_limit)
        all_keyword.extend(kw)

        if has_embedder:
            q_vec = embedder.embed([q])[0]
            q_norm = float(np.linalg.norm(q_vec))
            if q_norm > 0:
                vec = _vector_search(corpus_id, q_vec, q_norm, limit=fetch_limit)
                all_vector.extend(vec)

    # Deduplicate inputs by chunk id (keep highest-scoring occurrence)
    all_keyword = _dedup_by_id(all_keyword, score_key="fts_rank", lower_is_better=True)
    all_vector = _dedup_by_id(all_vector, score_key="_vector_score", lower_is_better=False)

    if all_keyword or all_vector:
        fused = _rrf_fuse(all_keyword, all_vector)
    elif all_keyword:
        fused = all_keyword
        for i, r in enumerate(fused):
            r["_rrf_score"] = 1.0 / (RRF_K + i + 1)
    else:
        fused = all_vector
        for i, r in enumerate(fused):
            r["_rrf_score"] = 1.0 / (RRF_K + i + 1)

    doc_cache: dict[str, dict] = {}
    for r in fused:
        did = r["document_id"]
        if did not in doc_cache:
            doc_row = conn.execute(
                "SELECT title, doc_type, date, source_kind FROM documents WHERE id=?", (did,)
            ).fetchone()
            doc_cache[did] = dict(doc_row) if doc_row else {}
        info = doc_cache[did]
        r["_doc_type"] = info.get("doc_type", "")
        r["_doc_date"] = info.get("date", "")
        r["_doc_title"] = info.get("title", "")
        r["_source_kind"] = info.get("source_kind", "user_original")

    # Caller-aware filter: external callers never see external_* content.
    # Post-filter (after scoring) is simpler than JOINing in SQL; fetch_limit
    # already over-fetches top_k * 3 so there's headroom for filtering.
    if caller != CALLER_OWNER:
        fused = [r for r in fused if r.get("_source_kind") in EXTERNAL_ALLOWED_SOURCE_KINDS]

    fused = _apply_freshness(fused, corpus_updated_at, stale_threshold)

    # Compiled truth boost: concept notes (distilled knowledge) rank higher
    for r in fused:
        if r.get("_doc_type") == "concept":
            r["_rrf_score"] = r.get("_rrf_score", 0) + COMPILED_TRUTH_BOOST

    fused.sort(key=lambda x: x.get("_rrf_score", 0), reverse=True)
    final = _deduplicate(fused, top_k)

    results = []
    for r in final:
        citation = {
            "document_title": r.get("_doc_title", ""),
            "document_id": r["document_id"],
            "document_type": r.get("_doc_type", ""),
            "date": r.get("_doc_date", ""),
            "char_range": [r.get("char_start", 0), r.get("char_end", 0)],
        }

        meta = {}
        if r.get("metadata_json"):
            try:
                meta = json.loads(r["metadata_json"])
            except (json.JSONDecodeError, TypeError):
                pass

        result = {
            "chunk_id": r["id"],
            "score": round(r.get("_rrf_score", 0), 4),
            "text": r["text"],
            "citation": citation,
        }

        if r.get("_freshness"):
            result["freshness"] = r["_freshness"]

        if include_context and meta.get("section"):
            result["section"] = meta["section"]

        results.append(result)

    latency = int((time.time() - start) * 1000)
    _log_query(corpus_id, query, len(results), latency, agent_id=agent_id, token_id=token_id, action=action)

    return {
        "results": results,
        "usage": {
            "latency_ms": latency,
            "chunks_searched": chunk_count,
            "queries_executed": len(queries),
            "detail": detail,
        },
    }


def _dedup_by_id(items: list[dict], *, score_key: str, lower_is_better: bool) -> list[dict]:
    """Keep the best-scoring item per chunk id."""
    best: dict[str, dict] = {}
    for item in items:
        cid = item.get("id", "")
        if not cid:
            continue
        if cid not in best:
            best[cid] = item
        else:
            old = best[cid].get(score_key, 0)
            new = item.get(score_key, 0)
            if lower_is_better:
                if new < old:
                    best[cid] = item
            else:
                if new > old:
                    best[cid] = item
    return list(best.values())


# ── Lower-level search for library consumers ────────────────────────

def search_chunks(corpus_id: str, query_vec: np.ndarray, top_k: int = 5) -> list[dict]:
    """Lower-level vector search for library consumers."""
    query_norm = float(np.linalg.norm(query_vec))
    if query_norm == 0:
        return []
    results = _vector_search(corpus_id, query_vec, query_norm, limit=top_k)
    return [{"score": r.pop("_vector_score", 0), **r} for r in results]


# ── Query logging ──────────────────────────────────────────────────

def _log_query(
    corpus_id: str,
    query_text: str,
    result_count: int,
    latency_ms: int,
    *,
    agent_id: str = "",
    token_id: str | None = None,
    action: str = "ask",
):
    try:
        conn = get_conn()
        conn.execute(
            "INSERT INTO query_logs (id, corpus_id, query_text, result_count, token_id, agent_id, latency_ms, action, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (uuid.uuid4().hex[:12], corpus_id, query_text, result_count,
             token_id or "", agent_id or "", latency_ms, action,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    except Exception:
        logger.warning("Failed to log query for corpus %s", corpus_id, exc_info=True)


log_query = _log_query
