"""Tests for L3 Networked peer subscriptions.

Covers the CRUD layer (peer_subscriptions module) + the outbound runner's
happy-path against a local peer corpus. Remote HTTP paths are exercised
indirectly via the local-peer shortcut — we don't stand up a real HTTP
server here; the remote path has the same pre/post-conditions and is
covered by API smoke tests.
"""

from __future__ import annotations

import pytest

from noosphere.core.corpus import create_corpus, get_corpus
from noosphere.core.ingest import ingest_text
from noosphere.core.peer_subscriptions import (
    create_subscription,
    due_subscriptions,
    get_subscription,
    has_active_subscription,
    list_runs,
    list_subscriptions,
    pause_subscription,
    resume_subscription,
    revoke_subscription,
    update_subscription,
)


# ── CRUD ────────────────────────────────────────────────────────────


def test_create_subscription_stores_row_and_raises_autonomy_level():
    a = create_corpus("Subscriber")
    b = create_corpus("Target")
    sub = create_subscription(
        a["id"],
        mode="describe",
        target_corpus_id=b["id"],
        cadence_minutes=60,
        approved_by="user:owner",
    )
    assert sub["id"]
    assert sub["status"] == "active"
    assert sub["subscriber_corpus_id"] == a["id"]
    assert sub["target_corpus_id"] == b["id"]
    assert sub["cadence_minutes"] == 60
    # First run schedule is fire-soon so the owner gets feedback immediately.
    assert sub["next_run_at"]
    # autonomy_level auto-raised to 3 on first active subscription
    refreshed = get_corpus(a["id"])
    assert refreshed["autonomy_level"] >= 3


def test_create_subscription_validates_mode_and_auth():
    a = create_corpus("A")
    b = create_corpus("B")
    with pytest.raises(ValueError):
        create_subscription(a["id"], mode="invalid", target_corpus_id=b["id"])
    with pytest.raises(ValueError):
        create_subscription(a["id"], mode="ask", target_corpus_id=b["id"])  # missing query
    with pytest.raises(ValueError):
        create_subscription(a["id"], mode="describe", auth_mode="bogus", target_corpus_id=b["id"])
    with pytest.raises(ValueError):
        create_subscription(a["id"], mode="describe")  # no target


def test_pause_resume_revoke_cycle_updates_autonomy_level():
    a = create_corpus("A")
    b = create_corpus("B")
    sub = create_subscription(a["id"], mode="describe", target_corpus_id=b["id"])
    assert has_active_subscription(a["id"]) is True

    pause_subscription(sub["id"])
    assert get_subscription(sub["id"])["status"] == "paused"
    assert has_active_subscription(a["id"]) is False
    # autonomy_level drops back when no active subs remain
    assert get_corpus(a["id"])["autonomy_level"] == 0

    resume_subscription(sub["id"])
    assert get_subscription(sub["id"])["status"] == "active"
    assert get_corpus(a["id"])["autonomy_level"] >= 3

    revoke_subscription(sub["id"])
    assert get_subscription(sub["id"]) is None
    assert get_corpus(a["id"])["autonomy_level"] == 0


def test_list_subscriptions_returns_only_this_corpus():
    a = create_corpus("A")
    b = create_corpus("B")
    c = create_corpus("C")
    create_subscription(a["id"], mode="describe", target_corpus_id=b["id"])
    create_subscription(a["id"], mode="describe", target_corpus_id=c["id"])
    create_subscription(c["id"], mode="describe", target_corpus_id=b["id"])

    assert len(list_subscriptions(a["id"])) == 2
    assert len(list_subscriptions(c["id"])) == 1
    assert list_subscriptions(b["id"]) == []


def test_update_subscription_clamps_cadence():
    a = create_corpus("A")
    b = create_corpus("B")
    sub = create_subscription(a["id"], mode="describe", target_corpus_id=b["id"])

    # Below min → clamped up to 60
    updated = update_subscription(sub["id"], cadence_minutes=5)
    assert updated["cadence_minutes"] == 60

    # Above max → clamped down to 10080 (1 week)
    updated = update_subscription(sub["id"], cadence_minutes=99999)
    assert updated["cadence_minutes"] == 10080


def test_due_subscriptions_picks_only_active_past_due():
    from datetime import datetime, timedelta, timezone

    from noosphere.core.db import get_conn

    a = create_corpus("A")
    b = create_corpus("B")
    sub = create_subscription(a["id"], mode="describe", target_corpus_id=b["id"])

    # Force next_run_at to past so it shows up
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    get_conn().execute(
        "UPDATE peer_subscriptions SET next_run_at=? WHERE id=?", (past, sub["id"]),
    )
    get_conn().commit()

    due = due_subscriptions(limit=10)
    assert len(due) == 1
    assert due[0]["id"] == sub["id"]

    # Pausing it removes it from the due list
    pause_subscription(sub["id"])
    assert due_subscriptions(limit=10) == []


# ── Runner — local peer happy path ──────────────────────────────────


def test_run_subscription_describe_local_ingests_capability_card():
    from noosphere.core.peer_runner import run_subscription

    subscriber = create_corpus("Subscriber")
    peer = create_corpus("Peer KB", description="A peer with interesting content", tags=["ai"])
    # Give the peer some content so describe returns a non-trivial card
    ingest_text(peer["id"], title="Peer doc", content="peer content about AI and alignment", source_kind="user_original")

    sub = create_subscription(
        subscriber["id"],
        mode="describe",
        target_corpus_id=peer["id"],
        cadence_minutes=60,
    )
    result = run_subscription(sub["id"])
    assert result["outcome"] == "ok"
    assert result["docs_ingested"] == 1

    # Capability card landed in subscriber's documents
    from noosphere.core.db import get_conn
    rows = get_conn().execute(
        "SELECT title, doc_type, source_kind FROM documents WHERE corpus_id=?",
        (subscriber["id"],),
    ).fetchall()
    # 1 manifest (system) + 1 capability_card (peer_subscription)
    peer_docs = [r for r in rows if r["source_kind"] == "peer_subscription"]
    assert len(peer_docs) == 1
    assert peer_docs[0]["doc_type"] == "capability_card"
    assert peer_docs[0]["title"].startswith("Capability card:")

    runs = list_runs(sub["id"])
    assert len(runs) == 1
    assert runs[0]["outcome"] == "ok"
    assert runs[0]["docs_ingested"] == 1


def test_run_subscription_dedupes_same_content():
    """Running the same subscription twice doesn't create duplicate docs —
    content_hash dedupe kicks in and the second run records no_new_content.
    """
    from noosphere.core.peer_runner import run_subscription

    subscriber = create_corpus("S")
    peer = create_corpus("P", description="stable description")
    ingest_text(peer["id"], title="P1", content="content", source_kind="user_original")

    sub = create_subscription(
        subscriber["id"], mode="describe", target_corpus_id=peer["id"],
    )
    first = run_subscription(sub["id"])
    assert first["outcome"] == "ok"
    assert first["docs_ingested"] == 1

    second = run_subscription(sub["id"])
    # Same describe payload → content hash match → nothing new ingested
    assert second["docs_ingested"] == 0
    # Either "ok" with 0 ingested or "no_new_content" are both acceptable
    assert second["outcome"] in ("ok", "no_new_content")


def test_run_subscription_records_failure_when_target_missing():
    from noosphere.core.peer_runner import run_subscription

    subscriber = create_corpus("S")
    sub = create_subscription(
        subscriber["id"],
        mode="describe",
        target_corpus_id="nonexistent123",
        target_endpoint=None,
    )
    result = run_subscription(sub["id"])
    assert result["outcome"] == "peer_down"
    # No docs got ingested and a run row was recorded
    runs = list_runs(sub["id"])
    assert len(runs) == 1
    assert runs[0]["outcome"] == "peer_down"


# ── Access gating — peer_subscription excluded from external allowlist ──


def test_peer_subscription_not_in_external_allowed_source_kinds():
    """Guard: external callers must never see peer_subscription content via
    retrieval. The enforcement lives in retrieval.EXTERNAL_ALLOWED_SOURCE_KINDS
    (the SQL filter is test-covered by test_search_filters_external_for_external_caller
    in test_api_extended.py). Here we just assert the enum stays honest.
    """
    from noosphere.core.retrieval import EXTERNAL_ALLOWED_SOURCE_KINDS

    assert "peer_subscription" not in EXTERNAL_ALLOWED_SOURCE_KINDS
    assert "external_public" not in EXTERNAL_ALLOWED_SOURCE_KINDS
    assert "external_subscription" not in EXTERNAL_ALLOWED_SOURCE_KINDS
    assert "system" not in EXTERNAL_ALLOWED_SOURCE_KINDS
    # user content stays visible
    assert "user_original" in EXTERNAL_ALLOWED_SOURCE_KINDS
    assert "user_capture" in EXTERNAL_ALLOWED_SOURCE_KINDS
