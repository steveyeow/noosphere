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
    rows = get_conn().execute(
        "SELECT * FROM peer_subscriptions WHERE subscriber_corpus_id=? ORDER BY created_at DESC",
        (corpus_id,),
    ).fetchall()
    return [dict(r) for r in rows]


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
) -> str:
    """Append a run-log row. Optionally advances `next_run_at` / `last_run_at`."""
    run_id = uuid.uuid4().hex[:12]
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
