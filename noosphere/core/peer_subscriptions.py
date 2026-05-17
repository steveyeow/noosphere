"""Peer subscription CRUD — L3 Networked autonomy (see docs/l3-networked.md).

A subscription is an owner-approved, persistent intent to poll a peer KB on
cadence. This module handles storage + scheduling picker; the runner lives
in core/peer_runner.py.
"""

import uuid
from datetime import datetime, timedelta, timezone

from noosphere.core.db import get_conn

VALID_MODES = ("ask", "describe", "new_documents")
VALID_AUTH_MODES = ("public", "token", "paid")
VALID_STATUSES = ("active", "paused", "failed", "revoked")

MIN_CADENCE_MIN = 60
MAX_CADENCE_MIN = 10080  # 1 week


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_run_at(cadence_minutes: int, from_time: datetime | None = None) -> str:
    base = from_time or datetime.now(timezone.utc)
    return (base + timedelta(minutes=cadence_minutes)).isoformat()


def create_subscription(
    subscriber_corpus_id: str,
    *,
    mode: str,
    target_corpus_id: str | None = None,
    target_endpoint: str | None = None,
    target_slug: str | None = None,
    query: str | None = None,
    topic_filter: str | None = None,
    cadence_minutes: int = 1440,
    max_docs_per_cycle: int = 5,
    bearer_token: str | None = None,
    auth_mode: str = "public",
    budget_cents_per_month: int | None = None,
    approved_by: str = "",
) -> dict:
    """Create an active subscription. Caller must have already verified ownership.

    Either `target_corpus_id` (local peer) or `target_endpoint` (remote peer)
    is required. Raises ValueError on invalid input.
    """
    if mode not in VALID_MODES:
        raise ValueError(f"invalid mode: {mode}")
    if auth_mode not in VALID_AUTH_MODES:
        raise ValueError(f"invalid auth_mode: {auth_mode}")
    if not target_corpus_id and not target_endpoint:
        raise ValueError("target_corpus_id or target_endpoint required")
    if mode == "ask" and not (query or "").strip():
        raise ValueError("mode='ask' requires a query")
    cadence_minutes = max(MIN_CADENCE_MIN, min(MAX_CADENCE_MIN, int(cadence_minutes)))
    max_docs_per_cycle = max(1, min(50, int(max_docs_per_cycle)))

    sub_id = uuid.uuid4().hex[:12]
    now = _now()
    # Fire-soon by default — gives the owner immediate feedback on the first tick.
    next_run = _next_run_at(1)

    conn = get_conn()
    conn.execute(
        """INSERT INTO peer_subscriptions
           (id, subscriber_corpus_id, target_corpus_id, target_endpoint, target_slug,
            mode, query, topic_filter, cadence_minutes, max_docs_per_cycle,
            bearer_token, auth_mode, budget_cents_per_month,
            status, last_run_at, next_run_at, last_error, consecutive_failures,
            created_at, approved_by)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            sub_id, subscriber_corpus_id, target_corpus_id, target_endpoint, target_slug,
            mode, query, topic_filter, cadence_minutes, max_docs_per_cycle,
            bearer_token, auth_mode, budget_cents_per_month,
            "active", None, next_run, None, 0,
            now, approved_by,
        ),
    )
    conn.commit()
    _rederive_autonomy_level(subscriber_corpus_id)
    return get_subscription(sub_id) or {}


def get_subscription(sub_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM peer_subscriptions WHERE id=?", (sub_id,)
    ).fetchone()
    return dict(row) if row else None


def list_subscriptions(corpus_id: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM peer_subscriptions WHERE subscriber_corpus_id=? ORDER BY created_at DESC",
        (corpus_id,),
    ).fetchall()
    subs = [dict(r) for r in rows]
    if subs:
        pend = conn.execute(
            "SELECT subscription_id, COUNT(*) AS n FROM peer_subscription_pending "
            "WHERE subscriber_corpus_id=? AND status='pending' GROUP BY subscription_id",
            (corpus_id,),
        ).fetchall()
        pmap = {p["subscription_id"]: int(p["n"] or 0) for p in pend}
        for s in subs:
            s["pending_count"] = pmap.get(s["id"], 0)
    return subs


def _set_status(sub_id: str, status: str) -> dict | None:
    sub = get_subscription(sub_id)
    if not sub:
        return None
    conn = get_conn()
    conn.execute("UPDATE peer_subscriptions SET status=? WHERE id=?", (status, sub_id))
    conn.commit()
    _rederive_autonomy_level(sub["subscriber_corpus_id"])
    return get_subscription(sub_id)


def pause_subscription(sub_id: str) -> dict | None:
    return _set_status(sub_id, "paused")


def resume_subscription(sub_id: str) -> dict | None:
    return _set_status(sub_id, "active")


def revoke_subscription(sub_id: str) -> bool:
    """Hard-delete a subscription (and its run history via ON DELETE CASCADE)."""
    sub = get_subscription(sub_id)
    if not sub:
        return False
    conn = get_conn()
    conn.execute("DELETE FROM peer_subscription_pending WHERE subscription_id=?", (sub_id,))
    conn.execute("DELETE FROM peer_subscription_runs WHERE subscription_id=?", (sub_id,))
    conn.execute("DELETE FROM peer_subscriptions WHERE id=?", (sub_id,))
    conn.commit()
    _rederive_autonomy_level(sub["subscriber_corpus_id"])
    return True


def update_subscription(
    sub_id: str,
    *,
    cadence_minutes: int | None = None,
    query: str | None = None,
    topic_filter: str | None = None,
    max_docs_per_cycle: int | None = None,
    budget_cents_per_month: int | None = None,
) -> dict | None:
    sub = get_subscription(sub_id)
    if not sub:
        return None
    updates: list[tuple[str, object]] = []
    if cadence_minutes is not None:
        cm = max(MIN_CADENCE_MIN, min(MAX_CADENCE_MIN, int(cadence_minutes)))
        updates.append(("cadence_minutes", cm))
    if query is not None:
        updates.append(("query", query))
    if topic_filter is not None:
        updates.append(("topic_filter", topic_filter))
    if max_docs_per_cycle is not None:
        updates.append(("max_docs_per_cycle", max(1, min(50, int(max_docs_per_cycle)))))
    if budget_cents_per_month is not None:
        updates.append(("budget_cents_per_month", int(budget_cents_per_month)))
    if not updates:
        return sub
    set_clause = ", ".join(f"{k}=?" for k, _ in updates)
    params = [v for _, v in updates] + [sub_id]
    conn = get_conn()
    conn.execute(f"UPDATE peer_subscriptions SET {set_clause} WHERE id=?", params)
    conn.commit()
    return get_subscription(sub_id)


def due_subscriptions(limit: int = 20) -> list[dict]:
    """Active subscriptions whose `next_run_at` has passed."""
    now = _now()
    rows = get_conn().execute(
        "SELECT * FROM peer_subscriptions WHERE status='active' AND next_run_at<=? "
        "ORDER BY next_run_at ASC LIMIT ?",
        (now, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_run(
    sub_id: str,
    *,
    outcome: str,
    docs_ingested: int = 0,
    chunks_ingested: int = 0,
    cents_spent: int = 0,
    latency_ms: int = 0,
    error_detail: str | None = None,
    advance_schedule: bool = True,
    run_id: str | None = None,
) -> str:
    """Append a run-log row. Optionally advances `next_run_at` / `last_run_at`.

    `run_id` may be supplied so the caller can link staged pending items to
    this run before the row exists; defaults to a fresh id.
    """
    run_id = run_id or uuid.uuid4().hex[:12]
    now = _now()
    conn = get_conn()
    conn.execute(
        """INSERT INTO peer_subscription_runs
           (id, subscription_id, ran_at, outcome, docs_ingested, chunks_ingested,
            cents_spent, latency_ms, error_detail)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (run_id, sub_id, now, outcome, docs_ingested, chunks_ingested,
         cents_spent, latency_ms, error_detail),
    )
    if advance_schedule:
        sub = get_subscription(sub_id)
        if sub:
            next_run = _next_run_at(int(sub["cadence_minutes"]))
            conn.execute(
                "UPDATE peer_subscriptions SET last_run_at=?, next_run_at=?, last_error=? WHERE id=?",
                (now, next_run, error_detail, sub_id),
            )
    conn.commit()
    return run_id


def list_runs(sub_id: str, limit: int = 50) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM peer_subscription_runs WHERE subscription_id=? "
        "ORDER BY ran_at DESC LIMIT ?",
        (sub_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def bump_failure(sub_id: str, error_detail: str) -> int:
    """Increment consecutive_failures; auto-pause after 3. Returns new count."""
    sub = get_subscription(sub_id)
    if not sub:
        return 0
    n = (sub.get("consecutive_failures") or 0) + 1
    conn = get_conn()
    if n >= 3:
        conn.execute(
            "UPDATE peer_subscriptions SET consecutive_failures=?, last_error=?, status='paused' WHERE id=?",
            (n, error_detail, sub_id),
        )
    else:
        conn.execute(
            "UPDATE peer_subscriptions SET consecutive_failures=?, last_error=? WHERE id=?",
            (n, error_detail, sub_id),
        )
    conn.commit()
    if n >= 3:
        _rederive_autonomy_level(sub["subscriber_corpus_id"])
    return n


def reset_failures(sub_id: str):
    conn = get_conn()
    conn.execute(
        "UPDATE peer_subscriptions SET consecutive_failures=0, last_error=NULL WHERE id=?",
        (sub_id,),
    )
    conn.commit()


# ── Review-before-apply: staged pending cycles ───────────────────────
#
# A subscription pulls from a corpus the owner does NOT control (possibly
# paid, possibly drifting). So the runner never writes straight into the
# corpus — it stages a cycle as `pending`, the owner sees the digest, then
# approves (ingest, provenance retained) or discards. "Human always wins"
# across the trust boundary.


def stage_pending(subscriber_corpus_id: str, sub: dict, run_id: str, docs: list[dict]) -> int:
    """Stage a cycle's docs as pending review — NOT ingested. Deduped by
    content hash against both already-ingested documents and existing
    pending rows for this subscription. Returns the number staged."""
    import hashlib
    import json
    if not docs:
        return 0
    conn = get_conn()
    now = _now()
    staged = 0
    for d in docs:
        content = d.get("content") or ""
        if not content.strip():
            continue
        h = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if conn.execute(
            "SELECT 1 FROM documents WHERE corpus_id=? AND content_hash=? LIMIT 1",
            (subscriber_corpus_id, h),
        ).fetchone():
            continue
        if conn.execute(
            "SELECT 1 FROM peer_subscription_pending WHERE subscription_id=? "
            "AND content_hash=? AND status='pending' LIMIT 1",
            (sub["id"], h),
        ).fetchone():
            continue
        meta = dict(d.get("extra_meta") or {})
        meta.update({
            "subscription_id": sub["id"],
            "peer_corpus_id": sub.get("target_corpus_id"),
            "peer_endpoint": sub.get("target_endpoint"),
        })
        conn.execute(
            "INSERT INTO peer_subscription_pending (id, subscription_id, run_id, "
            "subscriber_corpus_id, title, content, doc_type, tags_json, "
            "metadata_json, content_hash, status, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?, 'pending', ?)",
            (uuid.uuid4().hex[:12], sub["id"], run_id, subscriber_corpus_id,
             d.get("title") or "Untitled", content, d.get("doc_type") or "doc",
             json.dumps(d.get("tags") or []), json.dumps(meta), h, now),
        )
        staged += 1
    conn.commit()
    return staged


def list_pending(sub_id: str, limit: int = 200) -> list[dict]:
    """Pending items for the owner's review digest (content trimmed)."""
    rows = get_conn().execute(
        "SELECT id, run_id, title, doc_type, content, created_at FROM "
        "peer_subscription_pending WHERE subscription_id=? AND status='pending' "
        "ORDER BY created_at DESC LIMIT ?",
        (sub_id, limit),
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        c = d.pop("content", "") or ""
        d["snippet"] = c[:240]
        d["word_count"] = len(c.split())
        out.append(d)
    return out


def pending_count(sub_id: str) -> int:
    row = get_conn().execute(
        "SELECT COUNT(*) AS n FROM peer_subscription_pending "
        "WHERE subscription_id=? AND status='pending'",
        (sub_id,),
    ).fetchone()
    return int(row["n"] or 0) if row else 0


def approve_pending(sub_id: str) -> int:
    """Owner approves: ingest every pending item into the subscriber corpus
    (retaining `source_kind='peer_subscription'` provenance), mark applied.
    Returns the number ingested."""
    import json
    from noosphere.core.ingest import ingest_text
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM peer_subscription_pending WHERE subscription_id=? "
        "AND status='pending' ORDER BY created_at ASC",
        (sub_id,),
    ).fetchall()
    applied = 0
    for r in rows:
        try:
            tags = json.loads(r["tags_json"] or "[]")
        except (json.JSONDecodeError, TypeError):
            tags = []
        try:
            meta = json.loads(r["metadata_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            meta = {}
        ingest_text(
            r["subscriber_corpus_id"],
            title=r["title"] or "Untitled",
            content=r["content"] or "",
            doc_type=r["doc_type"] or "doc",
            source_kind="peer_subscription",
            tags=tags,
            metadata=meta,
        )
        conn.execute(
            "UPDATE peer_subscription_pending SET status='applied', decided_at=? WHERE id=?",
            (_now(), r["id"]),
        )
        applied += 1
    conn.commit()
    return applied


def discard_pending(sub_id: str) -> int:
    """Owner discards the staged cycle(s) — nothing enters the corpus."""
    conn = get_conn()
    n = conn.execute(
        "SELECT COUNT(*) AS n FROM peer_subscription_pending "
        "WHERE subscription_id=? AND status='pending'",
        (sub_id,),
    ).fetchone()
    conn.execute(
        "UPDATE peer_subscription_pending SET status='discarded', decided_at=? "
        "WHERE subscription_id=? AND status='pending'",
        (_now(), sub_id),
    )
    conn.commit()
    return int(n["n"] or 0) if n else 0


def has_active_subscription(corpus_id: str) -> bool:
    row = get_conn().execute(
        "SELECT COUNT(*) AS n FROM peer_subscriptions "
        "WHERE subscriber_corpus_id=? AND status='active'",
        (corpus_id,),
    ).fetchone()
    return bool(row and (row["n"] or 0) > 0)


def _rederive_autonomy_level(corpus_id: str):
    """Re-derive `corpora.autonomy_level` from current state (see §5.1).

    Phase 1: active subscription ⇒ level ≥ 3. If we previously upgraded to 3
    for subscriptions and all are now gone/paused, drop back to 0.

    We don't yet reshuffle L1/L2 based on feeds/auto-compile state — those
    pre-existing signals stay whatever the owner set. Subsequent phases can
    extend this derivation.
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT autonomy_level FROM corpora WHERE id=?", (corpus_id,)
    ).fetchone()
    if not row:
        return
    current = int(row["autonomy_level"] or 0)
    active = has_active_subscription(corpus_id)
    if active and current < 3:
        conn.execute(
            "UPDATE corpora SET autonomy_level=3, updated_at=? WHERE id=?",
            (_now(), corpus_id),
        )
        conn.commit()
    elif not active and current >= 3:
        conn.execute(
            "UPDATE corpora SET autonomy_level=0, updated_at=? WHERE id=?",
            (_now(), corpus_id),
        )
        conn.commit()
