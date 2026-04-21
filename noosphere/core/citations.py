"""Citation graph between corpora — the substrate for agent-era PageRank.

Citations are directed edges: `citing_corpus_id` references `cited_corpus_id`.
The `kind` field distinguishes where the edge came from:

- `manifest`   — owner explicitly declares "this KB builds on / cites KB X"
- `route`      — a `route` call surfaced KB X as a recommended next stop
- `query`      — this KB (as an agent) paid to query KB X and used the answer (M5)
- `derivative` — this KB's content was derived from KB X's content, with attribution

`kb_reputation` is a rolling 0.0-1.0 score per corpus. v1 formula uses only the
incoming citation graph weighted by the citing corpus's own reputation (simple
recursive PageRank approximation). M4 will extend with retention / calibration /
satisfaction terms.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone

from noosphere.core.db import get_conn


# ── Edge kinds ─────────────────────────────────────────────────────

KIND_MANIFEST = "manifest"
KIND_ROUTE = "route"
KIND_QUERY = "query"
KIND_DERIVATIVE = "derivative"

# Default weight per kind — reflects how strong a trust signal each kind is.
# Manifest is an owner's self-declared recommendation (strong).
# Query is proven usage (strong, set in M5).
# Route is a routing hint (weak — the caller may or may not have used it).
# Derivative is structural reuse (strongest).
DEFAULT_WEIGHTS = {
    KIND_MANIFEST: 1.0,
    KIND_QUERY: 1.0,
    KIND_DERIVATIVE: 1.5,
    KIND_ROUTE: 0.2,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Writes ─────────────────────────────────────────────────────────


def record_citation(
    citing_corpus_id: str,
    cited_corpus_id: str,
    kind: str,
    *,
    cited_corpus_endpoint: str = "",
    citing_doc_id: str = "",
    cited_doc_id: str = "",
    cited_chunk_id: str = "",
    context: str = "",
    weight: float | None = None,
) -> dict:
    """Record a citation edge. Returns the inserted row.

    No uniqueness constraint — the same pair can be cited multiple times with
    different kinds or in different contexts. Callers that want idempotent
    behavior (e.g. manifest-kind self-declarations) should call `remove_manifest_citation`
    first or use `upsert_manifest_citation`.
    """
    if not citing_corpus_id or not cited_corpus_id:
        raise ValueError("citing_corpus_id and cited_corpus_id are required")
    if citing_corpus_id == cited_corpus_id:
        raise ValueError("a corpus cannot cite itself")
    if kind not in DEFAULT_WEIGHTS:
        raise ValueError(f"unknown kind: {kind}")

    w = DEFAULT_WEIGHTS[kind] if weight is None else float(weight)
    row_id = uuid.uuid4().hex[:16]
    now = _now()
    get_conn().execute(
        """INSERT INTO corpus_citations
           (id, citing_corpus_id, cited_corpus_id, cited_corpus_endpoint,
            citing_doc_id, cited_doc_id, cited_chunk_id, kind, context, weight, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (row_id, citing_corpus_id, cited_corpus_id, cited_corpus_endpoint or None,
         citing_doc_id or None, cited_doc_id or None, cited_chunk_id or None,
         kind, context or None, w, now),
    )
    get_conn().commit()
    return {
        "id": row_id,
        "citing_corpus_id": citing_corpus_id,
        "cited_corpus_id": cited_corpus_id,
        "kind": kind,
        "weight": w,
        "created_at": now,
    }


def upsert_manifest_citation(
    citing_corpus_id: str, cited_corpus_id: str, *, context: str = ""
) -> dict:
    """Idempotent insert for `manifest`-kind edges (owner-declared).

    Owner-declared citations should not duplicate on repeated calls.
    """
    conn = get_conn()
    existing = conn.execute(
        "SELECT id FROM corpus_citations WHERE citing_corpus_id=? AND cited_corpus_id=? AND kind=?",
        (citing_corpus_id, cited_corpus_id, KIND_MANIFEST),
    ).fetchone()
    if existing:
        if context:
            conn.execute(
                "UPDATE corpus_citations SET context=?, weight=? WHERE id=?",
                (context, DEFAULT_WEIGHTS[KIND_MANIFEST], existing["id"]),
            )
            conn.commit()
        return {"id": existing["id"], "updated": True}
    return record_citation(citing_corpus_id, cited_corpus_id, KIND_MANIFEST, context=context)


def delete_citation(citation_id: str) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM corpus_citations WHERE id=?", (citation_id,))
    conn.commit()
    return cur.rowcount > 0


# ── Reads ──────────────────────────────────────────────────────────


def citations_out(corpus_id: str, *, kind: str | None = None) -> list[dict]:
    """List citations this corpus makes (outgoing edges)."""
    sql = "SELECT * FROM corpus_citations WHERE citing_corpus_id=?"
    params: list = [corpus_id]
    if kind:
        sql += " AND kind=?"
        params.append(kind)
    sql += " ORDER BY created_at DESC"
    rows = get_conn().execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def citations_in(corpus_id: str, *, kind: str | None = None) -> list[dict]:
    """List citations this corpus receives (incoming edges)."""
    sql = "SELECT * FROM corpus_citations WHERE cited_corpus_id=?"
    params: list = [corpus_id]
    if kind:
        sql += " AND kind=?"
        params.append(kind)
    sql += " ORDER BY created_at DESC"
    rows = get_conn().execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def citation_count_in(corpus_id: str, *, kind: str | None = None) -> int:
    sql = "SELECT COUNT(*) AS n FROM corpus_citations WHERE cited_corpus_id=?"
    params: list = [corpus_id]
    if kind:
        sql += " AND kind=?"
        params.append(kind)
    return get_conn().execute(sql, params).fetchone()["n"]


def weighted_citation_score_in(corpus_id: str) -> float:
    """Sum of incoming citation weights, each multiplied by the citing corpus's
    own kb_reputation (recursive trust weighting).

    Unknown citing corpora (remote or deleted) contribute with a small default
    weight so the score isn't entirely zero at cold-start.
    """
    conn = get_conn()
    rows = conn.execute(
        """SELECT cc.weight AS w, COALESCE(c.kb_reputation, 0.05) AS cited_by_rep
           FROM corpus_citations cc
           LEFT JOIN corpora c ON c.id = cc.citing_corpus_id
           WHERE cc.cited_corpus_id=?""",
        (corpus_id,),
    ).fetchall()
    return sum((r["w"] or 1.0) * (r["cited_by_rep"] or 0.05) for r in rows)


# ── KBR (kb_reputation) ────────────────────────────────────────────

# KBR v1: only the citation PageRank term. Placeholder weights below leave room
# for query_retention, calibration_accuracy, satisfaction_rate in M4.
KBR_WEIGHTS = {
    "citation_pagerank": 0.4,
    "query_retention": 0.3,        # not yet implemented
    "calibration_accuracy": 0.2,   # not yet implemented
    "satisfaction_rate": 0.1,      # not yet implemented
}

# Soft saturation constant: weighted score of K lifts the citation term to
# ~0.5. Tune as the network grows.
CITATION_SATURATION_K = 5.0


def citation_pagerank_score(corpus_id: str) -> float:
    """Normalize the raw weighted_citation_score_in into a 0-1 band.

    Uses a soft saturation: score / (score + K), so new KBs start near 0 and
    heavily-cited ones asymptote toward 1.
    """
    raw = weighted_citation_score_in(corpus_id)
    if raw <= 0:
        return 0.0
    return raw / (raw + CITATION_SATURATION_K)


def compute_kb_reputation(corpus_id: str) -> float:
    """KBR v1 — only the citation term is active. Other terms contribute 0 until M4."""
    citation_term = citation_pagerank_score(corpus_id)
    return round(KBR_WEIGHTS["citation_pagerank"] * citation_term, 4)


def refresh_kb_reputation(corpus_id: str) -> float:
    """Recompute KBR and persist to the corpora row. Returns the new value."""
    kbr = compute_kb_reputation(corpus_id)
    conn = get_conn()
    conn.execute(
        "UPDATE corpora SET kb_reputation=?, updated_at=? WHERE id=?",
        (kbr, _now(), corpus_id),
    )
    conn.commit()
    return kbr


def record_inter_kb_query(citing: str, cited: str, *, context: str = "") -> bool:
    """Record a `query`-kind citation when KB A queries KB B, deduped per
    (citing, cited) within a 24-hour window.

    Returns True if a new edge was inserted, False if deduped. Refreshes the
    cited corpus's kb_reputation on new insert.
    """
    from datetime import timedelta

    if not citing or not cited or citing == cited:
        return False
    conn = get_conn()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    existing = conn.execute(
        """SELECT id FROM corpus_citations
           WHERE citing_corpus_id=? AND cited_corpus_id=? AND kind=?
             AND created_at >= ?""",
        (citing, cited, KIND_QUERY, cutoff),
    ).fetchone()
    if existing:
        return False
    record_citation(citing, cited, KIND_QUERY, context=context)
    try:
        refresh_kb_reputation(cited)
    except Exception:
        pass
    return True


def refresh_all_kb_reputations() -> int:
    """Recompute KBR for all local corpora. Returns count updated.

    Called periodically (cron / on-demand) since KBR depends on other corpora's
    reputations, so a single change can ripple. v1 does a single pass; recursive
    convergence is an optimization for later.
    """
    conn = get_conn()
    ids = [r["id"] for r in conn.execute("SELECT id FROM corpora").fetchall()]
    # Two passes: pass 1 computes baseline (citing corpora default to 0.05);
    # pass 2 uses updated values for a more accurate recursive weight.
    for _ in range(2):
        for cid in ids:
            refresh_kb_reputation(cid)
    return len(ids)
