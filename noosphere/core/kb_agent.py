"""KB-as-agent L0 interface.

Three operations that turn every corpus from a retrieval endpoint into a
minimally-agentic interface:

- `ask`: synthesized answer with inline [N] citations, grounded in retrieved passages
- `describe`: structured capability card (machine-readable self-description)
- `preview_ask`: low-cost evaluation query — bypasses access gating, shorter response

Route handlers and MCP tools thin-wrap these. Higher autonomy levels (L1
subscribing, L2 synthesizing, L3 proactive) build on top of L0.
"""

from __future__ import annotations

from noosphere.core.corpus import get_corpus, list_corpora, source_composition
from noosphere.core.citations import citations_out, KIND_MANIFEST
from noosphere.core.db import get_conn
from noosphere.core.llm import call_llm as _call_llm
from noosphere.core.retrieval import search_corpus


ASK_SYSTEM_PROMPT = """You are a knowledge base answering questions grounded in your source material.

Rules:
- Answer based strictly on the provided sources. Do not use outside knowledge.
- Cite sources inline using [N] notation that matches the numbered source list.
- If the sources don't contain enough information, say so directly and do not speculate.
- Be concise. Match the language of the question.
"""

OUT_OF_SCOPE_MESSAGE = (
    "I don't have enough information in my corpus to answer this question."
)

PREVIEW_ASK_TRUNCATE_CHARS = 500


def ask(
    corpus_id: str,
    question: str,
    *,
    top_k: int = 5,
    caller: str = "external",
    agent_id: str = "",
    token_id: str | None = None,
    action: str = "ask",
) -> dict | None:
    """Synthesize an answer from a corpus, with inline [N] citations and capability context.

    Returns None if corpus not found. Callers are responsible for access gating
    (this function does not check `access_level` — wrap it in a route handler
    that does).
    """
    corpus = get_corpus(corpus_id)
    if not corpus:
        return None

    retrieval = search_corpus(
        corpus_id, question, top_k=top_k, caller=caller,
        agent_id=agent_id, token_id=token_id, action=action,
    )
    chunks = retrieval.get("results", [])

    if not chunks:
        return {
            "answer": OUT_OF_SCOPE_MESSAGE,
            "citations": [],
            "confidence": "low",
            "out_of_scope": True,
            "chunks_used": 0,
            "capability_context": _capability_context(corpus),
        }

    context_parts = []
    citations = []
    for i, chunk in enumerate(chunks, start=1):
        cite = chunk.get("citation", {})
        title = cite.get("document_title") or f"Source {i}"
        date = cite.get("date", "")
        label = f"[{i}] {title}" + (f" ({date})" if date else "")
        context_parts.append(f"{label}\n{chunk['text']}")
        citations.append({
            "index": i,
            "title": title,
            "document_id": cite.get("document_id", ""),
            "date": date,
            "score": chunk.get("score", 0.0),
        })

    context = "\n\n---\n\n".join(context_parts)
    messages = [
        {"role": "system", "content": ASK_SYSTEM_PROMPT},
        {"role": "user", "content": f"Sources:\n\n{context}\n\n---\n\nQuestion: {question}"},
    ]
    answer = _call_llm(messages)

    return {
        "answer": answer,
        "citations": citations,
        "confidence": _confidence(chunks),
        "out_of_scope": False,
        "chunks_used": len(chunks),
        "capability_context": _capability_context(corpus),
    }


def describe(corpus_id: str) -> dict | None:
    """Structured capability card for a corpus — the machine-readable
    "what is this KB for?" answer.

    Returns None if corpus not found. No access gating — capability cards
    are discoverable even for private corpora at the metadata level.

    Exposes three independent signal axes alongside manifest fields:
    ``kb_reputation`` (network-internal trust), ``discovery_reach`` (external
    AI surface visibility), and ``revenue_health`` (commercial traction).
    Consumers weight per task — the platform does not collapse these into a
    single score (see ``noosphere/core/access_log.py`` for the rationale).
    """
    corpus = get_corpus(corpus_id)
    if not corpus:
        return None
    from noosphere.core.access_log import discovery_reach_summary, revenue_health
    try:
        reach = discovery_reach_summary(corpus["id"])
    except Exception:
        reach = {"7d": {"score": 0.0, "ai_surfaces": 0}, "30d": {"score": 0.0, "ai_surfaces": 0}}
    try:
        rev = revenue_health(corpus["id"], window="30d")
    except Exception:
        rev = None
    return {
        "corpus_id": corpus["id"],
        "name": corpus["name"],
        "slug": corpus.get("slug", ""),
        "description": corpus.get("description", ""),
        "author": {
            "name": corpus.get("author_name", ""),
            "url": corpus.get("author_url", ""),
        },
        "tags": corpus.get("tags", []),
        "task_types": corpus.get("task_types", []),
        "samples": corpus.get("samples", []),
        "autonomy_level": corpus.get("autonomy_level", 0),
        "source_composition": source_composition(corpus["id"]),
        "calibration_policy": corpus.get("calibration_policy"),
        "license_terms": corpus.get("license_terms"),
        "access_level": corpus.get("access_level", "public"),
        "kb_reputation": corpus.get("kb_reputation", 0.0) or 0.0,
        "discovery_reach": reach,
        "revenue_health": rev,
        "quality": {
            "document_count": corpus.get("document_count", 0),
            "chunk_count": corpus.get("chunk_count", 0),
            "word_count": corpus.get("word_count", 0),
            "last_updated": corpus.get("updated_at", ""),
            "status": corpus.get("status", "draft"),
        },
    }


def preview_ask(corpus_id: str, question: str, *, agent_id: str = "") -> dict | None:
    """Low-cost evaluation query — a truncated `ask` that bypasses access gating.

    Designed for agents deciding whether to pay for full access. Returns the
    same shape as `ask` but with the answer truncated and a note flagging it
    as an evaluation. No token or payment required, even for paid corpora.

    Callers MUST still apply rate limiting (via _check_quota in the route).
    """
    # Smaller top_k + caller="external" to mirror a generic agent view.
    result = ask(
        corpus_id, question, top_k=3, caller="external",
        agent_id=agent_id, action="preview_ask",
    )
    if result is None:
        return None

    answer = result["answer"]
    truncated = len(answer) > PREVIEW_ASK_TRUNCATE_CHARS
    if truncated:
        answer = answer[: PREVIEW_ASK_TRUNCATE_CHARS - 3] + "..."

    return {
        "answer": answer,
        "truncated": truncated,
        "citations": result["citations"],
        "confidence": result["confidence"],
        "out_of_scope": result["out_of_scope"],
        "chunks_used": result["chunks_used"],
        "capability_context": result["capability_context"],
        "note": "Evaluation preview — truncated. Use `ask` (or purchase access for paid corpora) for full answers.",
    }


def route(
    corpus_id: str,
    question: str,
    *,
    limit: int = 5,
) -> dict | None:
    """Recommend other KBs that may better answer `question` than this one.

    Ranking combines three signals:
    - text relevance (name/description/tags/task_types match against question)
    - `kb_reputation` (the target KB's own score)
    - explicit manifest citation from this KB (owner endorsement)

    Returns None if the source corpus doesn't exist. Returns candidates from
    local + registered remote corpora, excluding the source and private corpora.
    """
    source = get_corpus(corpus_id)
    if not source:
        return None

    # Explicit manifest endorsements from this KB — strongest signal.
    endorsed = {
        e["cited_corpus_id"]
        for e in citations_out(corpus_id, kind=KIND_MANIFEST)
    }

    conn = get_conn()
    q_lower = question.lower()

    candidates: list[dict] = []

    # Local corpora
    for c in list_corpora():
        if c["id"] == corpus_id:
            continue
        if c.get("access_level") == "private":
            continue
        score = _relevance_score(q_lower, c)
        if score <= 0 and c["id"] not in endorsed:
            continue
        candidates.append({
            "corpus_id": c["id"],
            "name": c["name"],
            "description": c.get("description", ""),
            "author": c.get("author_name", ""),
            "tags": c.get("tags", []),
            "task_types": c.get("task_types", []),
            "kb_reputation": c.get("kb_reputation", 0.0) or 0.0,
            "access_level": c.get("access_level", "public"),
            "source": "local",
            "relevance": score,
            "endorsed": c["id"] in endorsed,
        })

    # Remote registered corpora
    try:
        rows = conn.execute(
            """SELECT corpus_id, name, description, author, tags, task_types,
                      autonomy_level, kb_reputation, access_level, node_endpoint
               FROM registered_corpora
               WHERE access_level != 'private'"""
        ).fetchall()
    except Exception:
        rows = []
    for r in rows:
        if r["corpus_id"] == corpus_id:
            continue
        import json as _json
        try:
            tags = _json.loads(r["tags"] or "[]")
        except Exception:
            tags = []
        try:
            task_types = _json.loads(r["task_types"] or "[]")
        except Exception:
            task_types = []
        pseudo = {
            "name": r["name"] or "",
            "description": r["description"] or "",
            "tags": tags,
            "task_types": task_types,
        }
        score = _relevance_score(q_lower, pseudo)
        if score <= 0 and r["corpus_id"] not in endorsed:
            continue
        candidates.append({
            "corpus_id": r["corpus_id"],
            "name": r["name"],
            "description": r["description"] or "",
            "author": r["author"] or "",
            "tags": tags,
            "task_types": task_types,
            "kb_reputation": r["kb_reputation"] or 0.0,
            "access_level": r["access_level"] or "public",
            "source": "remote",
            "endpoint": r["node_endpoint"],
            "relevance": score,
            "endorsed": r["corpus_id"] in endorsed,
        })

    for c in candidates:
        c["score"] = round(
            0.5 * c["relevance"]
            + 0.3 * c["kb_reputation"]
            + (0.2 if c["endorsed"] else 0.0),
            4,
        )
    candidates.sort(key=lambda x: x["score"], reverse=True)

    return {
        "source_corpus_id": corpus_id,
        "question": question,
        "candidates": candidates[:limit],
        "count": len(candidates[:limit]),
    }


def _relevance_score(q_lower: str, corpus_like: dict) -> float:
    """Simple keyword match across name / description / tags / task_types.

    Replaced by proper embedding match once we have a shared query-embedding
    path for discovery. This v1 is intentionally crude — good enough to
    surface obvious candidates; agent consumers re-rank anyway.
    """
    score = 0.0
    name = (corpus_like.get("name") or "").lower()
    desc = (corpus_like.get("description") or "").lower()
    tags = corpus_like.get("tags") or []
    task_types = corpus_like.get("task_types") or []

    if q_lower in name:
        score += 0.5
    if q_lower in desc:
        score += 0.3

    tokens = [t.strip() for t in q_lower.replace(",", " ").split() if len(t.strip()) >= 3]
    for tok in tokens:
        if tok in name:
            score += 0.15
        if tok in desc:
            score += 0.1
        for t in tags:
            if tok in str(t).lower():
                score += 0.2
        for tt in task_types:
            if tok in str(tt).lower():
                score += 0.15
    return min(score, 1.0)


def _capability_context(corpus: dict) -> dict:
    return {
        "corpus_id": corpus["id"],
        "corpus_name": corpus["name"],
        "source_composition": source_composition(corpus["id"]),
        "autonomy_level": corpus.get("autonomy_level", 0),
        "calibration_reported": bool(
            (corpus.get("calibration_policy") or {}).get("reports_confidence")
        ) if isinstance(corpus.get("calibration_policy"), dict) else False,
    }


def _confidence(chunks: list[dict]) -> str:
    """Simple confidence heuristic based on top chunk's retrieval score.

    L0 calibration is coarse — a better model (e.g. ensemble of score
    distribution + LLM self-report) is M4 work.
    """
    if not chunks:
        return "low"
    top_score = chunks[0].get("score", 0.0) or 0.0
    if top_score >= 0.7:
        return "high"
    if top_score >= 0.4:
        return "medium"
    return "low"
