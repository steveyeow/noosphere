"""Quota enforcement for Noosphere Cloud Free/Pro tiers.

Free tier limits encourage upgrade to Pro ($9/month). All limits are
enforced per-user. Self-hosted users never hit this code.

Quota checks are called from route handlers, not as middleware —
this allows granular per-action enforcement.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from noosphere.cloud.db import (
    count_usage_today,
    count_user_corpora,
    count_corpus_documents,
    count_queries_this_month,
    record_usage,
)

# Daily action limits
QUOTA_LIMITS = {
    "free": {
        "search": 50,            # queries per day
        "ingest_url": 5,         # URL ingestions per day
        "ingest_feed": 1,        # feed ingestions per day
        "compile": 2,            # manual one-off compile: Free tier gets a small allowance to
                                 # try synthesis. Continuous / auto-refresh compile is Pro
                                 # (front-end gates the auto-refresh checkbox).
        "chat": 20,              # chat messages per day
        "ask": 20,               # KB-as-agent synthesized answers — same LLM cost as chat
        "preview_ask": 100,      # free evaluation query; generous to support discovery
        "extract_entities": 0,   # entity extraction is Pro-only (LLM-heavy, N calls per doc)
        "index": 3,              # ingest operations (chunk + embed); each covers many chunks
        "manifest_suggest": 0,   # manifest auto-fill is Pro-only (LLM cost); Free gets 1 auto-apply at corpus creation
    },
    "pro": {
        "search": 10000,
        "ingest_url": 100,
        "ingest_feed": 20,
        "compile": 50,
        "chat": 500,
        "ask": 500,
        "preview_ask": 2000,
        "extract_entities": 20,
        "index": 100,
        "manifest_suggest": 50,
    },
}

# Resource limits (not daily — total)
RESOURCE_LIMITS = {
    "free": {
        # 5 corpora gives Free users genuine room to dogfood the product
        # — first KB might not be the keeper, and product-of-record
        # workflows (work / reading / project) need a few slots in
        # parallel. The previous limit of 1 punished early experimentation
        # and triggered the Pro upsell before the user had felt the value.
        "corpora": 5,
        "documents_per_corpus": 100,
        "queries_per_month": 1000,
    },
    "pro": {
        "corpora": -1,              # unlimited
        "documents_per_corpus": -1,  # unlimited
        "queries_per_month": 100000,
    },
}


def check_quota(request: Request, action: str) -> None:
    """Check if the user has remaining daily quota for the given action.

    Raises HTTP 429 if quota exceeded. No-op if auth is not enabled
    (user_id not set on request).
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return

    tier = getattr(request.state, "tier", "free")
    limits = QUOTA_LIMITS.get(tier, QUOTA_LIMITS["free"])
    limit = limits.get(action)

    if limit is None:
        return

    used = count_usage_today(user_id, action)
    if used >= limit:
        # pro_only=True when limit=0 — the action is gated entirely behind Pro,
        # not a daily cap. Frontend uses this to render the paywall modal's
        # headline ("Compile is a Pro feature") vs daily-cap messaging
        # ("You've used your 20 chats today").
        pro_only = (limit == 0)
        if pro_only:
            msg = f"{action.replace('_', ' ').capitalize()} is a Pro feature. Upgrade to unlock."
        else:
            msg = f"Daily {action} limit reached ({limit}). Upgrade to Pro for higher limits."
        raise HTTPException(
            status_code=429,
            detail={
                "code": "quota_exceeded",
                "action": action,
                "limit": limit,
                "used": used,
                "tier": tier,
                "pro_only": pro_only,
                "message": msg,
            },
        )


def check_corpus_limit(request: Request) -> None:
    """Check if the user can create another corpus. Raises 429 if at limit."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return

    tier = getattr(request.state, "tier", "free")
    limit = RESOURCE_LIMITS.get(tier, RESOURCE_LIMITS["free"])["corpora"]
    if limit == -1:
        return

    current = count_user_corpora(user_id)
    if current >= limit:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "corpus_limit_reached",
                "limit": limit,
                "used": current,
                "tier": tier,
                "message": f"Corpus limit reached ({current}/{limit}). Upgrade to Pro for unlimited corpora.",
            },
        )


def check_document_limit(request: Request, corpus_id: str) -> None:
    """Check if a corpus can accept more documents. Raises 429 if at limit."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return

    tier = getattr(request.state, "tier", "free")
    limit = RESOURCE_LIMITS.get(tier, RESOURCE_LIMITS["free"])["documents_per_corpus"]
    if limit == -1:
        return

    current = count_corpus_documents(corpus_id)
    if current >= limit:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "document_limit_reached",
                "limit": limit,
                "used": current,
                "tier": tier,
                "message": f"Document limit reached ({current}/{limit}). Upgrade to Pro for unlimited documents.",
            },
        )


def check_monthly_queries(request: Request) -> None:
    """Check monthly query quota. Raises 429 if exceeded."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return

    tier = getattr(request.state, "tier", "free")
    limit = RESOURCE_LIMITS.get(tier, RESOURCE_LIMITS["free"])["queries_per_month"]
    if limit == -1:
        return

    used = count_queries_this_month(user_id)
    if used >= limit:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "monthly_query_limit",
                "limit": limit,
                "used": used,
                "tier": tier,
                "message": f"Monthly query limit reached ({used}/{limit}). Upgrade to Pro for higher limits.",
            },
        )


def track_usage(request: Request, action: str, tokens_used: int = 0) -> None:
    """Record usage for the current user. No-op if auth is not enabled."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return
    record_usage(user_id, action, tokens_used)


async def quota_middleware(request: Request, call_next):
    """Lightweight middleware — just ensures cloud DB tables exist on first request.

    Actual quota checks are done per-route via check_quota() / check_corpus_limit()
    so each endpoint can enforce the right action type.
    """
    # Ensure cloud tables exist (idempotent)
    if not getattr(quota_middleware, "_initialized", False):
        from noosphere.cloud.db import init_cloud_tables
        init_cloud_tables()
        quota_middleware._initialized = True

    return await call_next(request)
