"""Cloud layer tests — auth, quota, Stripe Connect.

These tests verify the cloud modules work correctly without requiring
Supabase or Stripe credentials. JWT and Stripe calls are mocked.
"""

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import jwt as pyjwt
import pytest

from noosphere.cloud.db import (
    init_cloud_tables,
    get_or_create_user,
    get_user,
    update_user_tier,
    count_usage_today,
    record_usage,
    count_user_corpora,
    find_user_by_stripe_customer,
)
from noosphere.cloud.quota import (
    check_quota,
    check_corpus_limit,
    check_document_limit,
    QUOTA_LIMITS,
)
from noosphere.core.db import get_conn


@pytest.fixture(autouse=True)
def cloud_tables(isolated_db):
    """Ensure cloud tables exist for every test."""
    init_cloud_tables()
    yield


# ── DB helpers ──


def test_get_or_create_user():
    user = get_or_create_user("user-1", "alice@example.com")
    assert user["id"] == "user-1"
    assert user["email"] == "alice@example.com"
    assert user["tier"] == "free"

    # Second call returns same user
    user2 = get_or_create_user("user-1", "alice@example.com")
    assert user2["id"] == "user-1"


def test_update_user_tier():
    get_or_create_user("user-2", "bob@example.com")
    update_user_tier("user-2", "pro", stripe_customer_id="cus_123",
                     stripe_subscription_id="sub_456", subscription_status="active")

    user = get_user("user-2")
    assert user["tier"] == "pro"
    assert user["stripe_customer_id"] == "cus_123"
    assert user["subscription_status"] == "active"


def test_find_user_by_stripe_customer():
    get_or_create_user("user-3", "carol@example.com")
    update_user_tier("user-3", "pro", stripe_customer_id="cus_find_me")

    found = find_user_by_stripe_customer("cus_find_me")
    assert found is not None
    assert found["id"] == "user-3"

    not_found = find_user_by_stripe_customer("cus_nonexistent")
    assert not_found is None


def test_usage_tracking():
    get_or_create_user("user-4", "dave@example.com")

    assert count_usage_today("user-4", "search") == 0
    record_usage("user-4", "search")
    record_usage("user-4", "search")
    assert count_usage_today("user-4", "search") == 2
    # Different action is separate
    assert count_usage_today("user-4", "chat") == 0


def test_count_user_corpora():
    get_or_create_user("user-5", "eve@example.com")
    # No corpora yet
    assert count_user_corpora("user-5") == 0

    # Create a corpus with owner_id
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO corpora (id, name, slug, owner_id, created_at, updated_at)
           VALUES ('c-1', 'Test', 'test', 'user-5', ?, ?)""",
        (now, now),
    )
    conn.commit()
    assert count_user_corpora("user-5") == 1


# ── Quota checks ──


class FakeRequest:
    """Minimal request mock with state."""
    def __init__(self, user_id=None, tier="free"):
        self.state = MagicMock()
        self.state.user_id = user_id
        self.state.tier = tier


def test_check_quota_no_user():
    """No user_id = no enforcement (self-hosted mode)."""
    req = FakeRequest(user_id=None)
    check_quota(req, "search")  # Should not raise


def test_check_quota_within_limit():
    get_or_create_user("quota-1", "q1@example.com")
    req = FakeRequest(user_id="quota-1", tier="free")
    check_quota(req, "search")  # Should not raise (0 < 50)


def test_check_quota_exceeded():
    from fastapi import HTTPException

    get_or_create_user("quota-2", "q2@example.com")
    # Fill up the daily limit
    free_limit = QUOTA_LIMITS["free"]["compile"]
    for _ in range(free_limit):
        record_usage("quota-2", "compile")

    req = FakeRequest(user_id="quota-2", tier="free")
    with pytest.raises(HTTPException) as exc:
        check_quota(req, "compile")
    assert exc.value.status_code == 429
    assert "quota_exceeded" in str(exc.value.detail)


def test_check_quota_pro_has_higher_limits():
    get_or_create_user("quota-3", "q3@example.com")
    # Fill past free limit
    free_limit = QUOTA_LIMITS["free"]["search"]
    for _ in range(free_limit):
        record_usage("quota-3", "search")

    # Free tier: blocked
    from fastapi import HTTPException
    req_free = FakeRequest(user_id="quota-3", tier="free")
    with pytest.raises(HTTPException):
        check_quota(req_free, "search")

    # Pro tier: still under limit
    req_pro = FakeRequest(user_id="quota-3", tier="pro")
    check_quota(req_pro, "search")  # Should not raise


def test_check_corpus_limit_free():
    from fastapi import HTTPException

    get_or_create_user("corpus-lim-1", "cl1@example.com")
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO corpora (id, name, slug, owner_id, created_at, updated_at)
           VALUES ('cl-1', 'Full', 'full', 'corpus-lim-1', ?, ?)""",
        (now, now),
    )
    conn.commit()

    req = FakeRequest(user_id="corpus-lim-1", tier="free")
    with pytest.raises(HTTPException) as exc:
        check_corpus_limit(req)
    assert exc.value.status_code == 429


def test_check_corpus_limit_pro_unlimited():
    get_or_create_user("corpus-lim-2", "cl2@example.com")
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    for i in range(5):
        conn.execute(
            f"INSERT INTO corpora (id, name, slug, owner_id, created_at, updated_at) VALUES ('clp-{i}', 'C{i}', 'c{i}', 'corpus-lim-2', ?, ?)",
            (now, now),
        )
    conn.commit()

    req = FakeRequest(user_id="corpus-lim-2", tier="pro")
    check_corpus_limit(req)  # Should not raise — Pro is unlimited


def test_check_document_limit():
    from fastapi import HTTPException

    get_or_create_user("doc-lim-1", "dl1@example.com")
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO corpora (id, name, slug, owner_id, created_at, updated_at) VALUES ('dl-c', 'DL', 'dl', 'doc-lim-1', ?, ?)",
        (now, now),
    )
    # Insert 100 documents (free limit)
    for i in range(100):
        conn.execute(
            f"INSERT INTO documents (id, corpus_id, title, content, created_at) VALUES ('d-{i}', 'dl-c', 'Doc {i}', 'Content', ?)",
            (now,),
        )
    conn.commit()

    req = FakeRequest(user_id="doc-lim-1", tier="free")
    with pytest.raises(HTTPException) as exc:
        check_document_limit(req, "dl-c")
    assert exc.value.status_code == 429


# ── Auth middleware ──


def test_auth_middleware_public_paths():
    """Public paths should pass through without auth."""
    import asyncio
    from noosphere.cloud.auth import auth_middleware

    async def run():
        from starlette.requests import Request

        called = False

        async def mock_call_next(request):
            nonlocal called
            called = True
            from starlette.responses import JSONResponse
            return JSONResponse({"ok": True})

        # Build a minimal request for a public path
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/health",
            "headers": [],
            "query_string": b"",
        }
        request = Request(scope)
        resp = await auth_middleware(request, mock_call_next)
        assert called

    asyncio.run(run())


def test_auth_middleware_rejects_write_without_token():
    """POST to non-public path without token should return 401."""
    import asyncio
    from noosphere.cloud.auth import auth_middleware

    async def run():
        from starlette.requests import Request

        async def mock_call_next(request):
            from starlette.responses import JSONResponse
            return JSONResponse({"ok": True})

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/corpora",
            "headers": [],
            "query_string": b"",
        }
        request = Request(scope)
        resp = await auth_middleware(request, mock_call_next)
        assert resp.status_code == 401

    asyncio.run(run())


def test_auth_middleware_valid_hs256_token():
    """Valid HS256 JWT should set user context."""
    import asyncio
    from noosphere.cloud.auth import auth_middleware

    secret = "test-jwt-secret-key-for-testing"
    token = pyjwt.encode(
        {"sub": "user-jwt-1", "email": "jwt@example.com", "aud": "authenticated"},
        secret,
        algorithm="HS256",
    )

    async def run():
        from starlette.requests import Request

        captured_state = {}

        async def mock_call_next(request):
            captured_state["user_id"] = request.state.user_id
            captured_state["tier"] = request.state.tier
            from starlette.responses import JSONResponse
            return JSONResponse({"ok": True})

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/corpora",
            "headers": [
                (b"authorization", f"Bearer {token}".encode()),
            ],
            "query_string": b"",
        }
        request = Request(scope)

        with patch("noosphere.cloud.auth.SUPABASE_JWT_SECRET", secret):
            resp = await auth_middleware(request, mock_call_next)

        assert resp.status_code == 200
        assert captured_state["user_id"] == "user-jwt-1"
        assert captured_state["tier"] == "free"

    asyncio.run(run())
