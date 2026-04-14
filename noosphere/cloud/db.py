"""Cloud-specific database tables and helpers.

These tables only exist when ENABLE_CLOUD=true. They extend the core
noosphere.db schema with multi-tenant user management.
"""

import logging
from datetime import datetime, timezone

from noosphere.core.db import get_conn

log = logging.getLogger(__name__)

CLOUD_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE,
    tier TEXT DEFAULT 'free',
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    subscription_status TEXT,
    subscription_ended_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_stripe ON users(stripe_customer_id);

CREATE TABLE IF NOT EXISTS usage_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id),
    action TEXT NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_user_action ON usage_logs(user_id, action, created_at);
"""


def init_cloud_tables():
    """Create cloud-specific tables. Called during lifespan when ENABLE_CLOUD=true."""
    conn = get_conn()
    conn.executescript(CLOUD_SCHEMA)
    log.info("Cloud tables initialized")


def get_or_create_user(user_id: str, email: str = "") -> dict:
    """Get an existing user or create a new one from Supabase JWT claims."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if row:
        return dict(row)

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users (id, email, tier, created_at, updated_at) VALUES (?, ?, 'free', ?, ?)",
        (user_id, email, now, now),
    )
    conn.commit()
    return {"id": user_id, "email": email, "tier": "free", "created_at": now}


def get_user(user_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def find_user_by_stripe_customer(customer_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE stripe_customer_id=?", (customer_id,)).fetchone()
    return dict(row) if row else None


def update_user_tier(
    user_id: str,
    tier: str,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    subscription_status: str | None = None,
    subscription_ended_at: str | None = None,
):
    """Update a user's tier and Stripe subscription info."""
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()

    updates = {"tier": tier, "updated_at": now}
    if stripe_customer_id is not None:
        updates["stripe_customer_id"] = stripe_customer_id
    if stripe_subscription_id is not None:
        updates["stripe_subscription_id"] = stripe_subscription_id
    if subscription_status is not None:
        updates["subscription_status"] = subscription_status
    if subscription_ended_at is not None:
        updates["subscription_ended_at"] = subscription_ended_at

    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [user_id]
    conn.execute(f"UPDATE users SET {set_clause} WHERE id=?", values)
    conn.commit()


def count_usage_today(user_id: str, action: str) -> int:
    """Count how many times a user has performed an action today."""
    conn = get_conn()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT COUNT(*) as n FROM usage_logs WHERE user_id=? AND action=? AND created_at >= ?",
        (user_id, action, today),
    ).fetchone()
    return row["n"]


def count_user_corpora(user_id: str) -> int:
    """Count corpora owned by a user."""
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as n FROM corpora WHERE owner_id=?", (user_id,)
    ).fetchone()
    return row["n"]


def count_corpus_documents(corpus_id: str) -> int:
    """Count documents in a corpus."""
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as n FROM documents WHERE corpus_id=?", (corpus_id,)
    ).fetchone()
    return row["n"]


def record_usage(user_id: str, action: str, tokens_used: int = 0):
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO usage_logs (user_id, action, tokens_used, created_at) VALUES (?, ?, ?, ?)",
        (user_id, action, tokens_used, now),
    )
    conn.commit()


def count_queries_this_month(user_id: str) -> int:
    """Count queries received across all user's corpora this month."""
    conn = get_conn()
    month_start = datetime.now(timezone.utc).strftime("%Y-%m-01")
    row = conn.execute(
        """SELECT COUNT(*) as n FROM query_logs
           WHERE corpus_id IN (SELECT id FROM corpora WHERE owner_id=?)
           AND created_at >= ?""",
        (user_id, month_start),
    ).fetchone()
    return row["n"]
