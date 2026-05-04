"""Payment / Stripe integration tests.

Stripe API calls are mocked — these tests verify the payment flow logic,
DB records, access control, and API routes without hitting Stripe.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

_CORPUS_JSON = {
    "name": "Paid Corpus",
    "description": "Premium knowledge",
    "author_name": "Creator",
    "tags": ["premium"],
    "access_level": "public",
    "language": "en",
}

_PRICING = {
    "type": "per_query",
    "amount_cents": 500,
    "currency": "usd",
    "queries_per_payment": 10,
}


@pytest.fixture
def corpus(client):
    r = client.post("/api/v1/corpora", json=_CORPUS_JSON)
    assert r.status_code == 200
    return r.json()


@pytest.fixture
def paid_corpus(client, corpus):
    """A corpus with pricing set and access_level=paid."""
    r = client.post(f"/api/v1/corpora/{corpus['id']}/pricing", json=_PRICING)
    assert r.status_code == 200
    # Re-fetch to get updated fields
    r = client.get(f"/api/v1/corpora/{corpus['id']}")
    return r.json()


# ── Pricing config ──


def test_set_pricing(client, corpus):
    r = client.post(f"/api/v1/corpora/{corpus['id']}/pricing", json=_PRICING)
    assert r.status_code == 200
    body = r.json()
    assert body["pricing"]["type"] == "per_query"
    assert body["pricing"]["amount_cents"] == 500
    assert body["corpus"]["access_level"] == "paid"


def test_set_pricing_subscription_requires_price_id(client, corpus):
    r = client.post(f"/api/v1/corpora/{corpus['id']}/pricing", json={
        "type": "subscription",
        "amount_cents": 999,
    })
    assert r.status_code == 400
    assert "stripe_price_id" in r.json()["detail"]


def test_get_pricing(client, paid_corpus):
    r = client.get(f"/api/v1/corpora/{paid_corpus['id']}/pricing")
    assert r.status_code == 200
    body = r.json()
    assert body["access_level"] == "paid"
    assert body["pricing"]["amount_cents"] == 500


def test_get_pricing_no_pricing(client, corpus):
    r = client.get(f"/api/v1/corpora/{corpus['id']}/pricing")
    assert r.status_code == 200
    assert r.json()["pricing"] is None


# ── Access control for paid corpora ──


def test_paid_corpus_denies_without_token(client, paid_corpus):
    """Accessing a paid corpus without a bearer token returns 402 with an
    x402-compliant challenge body — agent payment SDKs read `accepts` to
    satisfy the challenge automatically."""
    r = client.post(
        f"/api/v1/corpora/{paid_corpus['id']}/search",
        json={"query": "test"},
        headers={"x-agent-id": "agent-1"},
    )
    assert r.status_code == 402
    body = r.json()
    assert body["x402Version"] == 1
    assert body["error"] == "payment_required"
    assert isinstance(body["accepts"], list) and len(body["accepts"]) >= 1
    accept = body["accepts"][0]
    assert accept["resource"].endswith("/search")
    assert int(accept["maxAmountRequired"]) == 500


def test_paid_corpus_denies_invalid_token(client, paid_corpus):
    """Accessing with an invalid payment token returns 402."""
    r = client.post(
        f"/api/v1/corpora/{paid_corpus['id']}/search",
        json={"query": "test"},
        headers={"x-agent-id": "agent-1", "authorization": "Bearer fake-token"},
    )
    assert r.status_code == 402


def test_paid_corpus_allows_with_valid_payment(client, paid_corpus):
    """A completed payment record grants access."""
    from noosphere.core.db import get_conn

    payment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    conn.execute(
        """INSERT INTO payments
           (id, corpus_id, stripe_session_id, payment_type, amount_cents, currency,
            status, created_at, completed_at)
           VALUES (?, ?, ?, 'per_query', 500, 'usd', 'completed', ?, ?)""",
        (payment_id, paid_corpus["id"], "sess_test", now, now),
    )
    conn.commit()

    # Use payment_id as bearer token
    r = client.post(
        f"/api/v1/corpora/{paid_corpus['id']}/search",
        json={"query": "test"},
        headers={"x-agent-id": "agent-1", "authorization": f"Bearer {payment_id}"},
    )
    # Should not be 402 — may be 200 or error from empty corpus, but not payment-denied
    assert r.status_code != 402


def test_paid_corpus_allows_with_active_subscription(client, paid_corpus):
    """An active subscription grants access."""
    from noosphere.core.db import get_conn

    sub_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    conn.execute(
        """INSERT INTO subscriptions
           (id, corpus_id, stripe_subscription_id, stripe_customer_id,
            payer_email, status, created_at)
           VALUES (?, ?, 'sub_test', 'cus_test', 'user@example.com', 'active', ?)""",
        (sub_id, paid_corpus["id"], now),
    )
    conn.commit()

    # Use customer_id as bearer token
    r = client.post(
        f"/api/v1/corpora/{paid_corpus['id']}/search",
        json={"query": "test"},
        headers={"x-agent-id": "agent-1", "authorization": "Bearer cus_test"},
    )
    assert r.status_code != 402


def test_paid_corpus_owner_bypasses_payment(client, paid_corpus):
    """Owner (localhost) can access paid corpus without payment."""
    r = client.post(
        f"/api/v1/corpora/{paid_corpus['id']}/search",
        json={"query": "test"},
    )
    # Owner request — should not get 402
    assert r.status_code != 402


# ── Checkout (mocked Stripe) ──


def test_checkout_non_paid_corpus_rejected(client, corpus):
    """Can't checkout for a non-paid corpus."""
    r = client.post(f"/api/v1/corpora/{corpus['id']}/checkout", json={})
    assert r.status_code == 400
    assert "not set to paid" in r.json()["detail"]


@patch("noosphere.core.payments.stripe")
def test_checkout_creates_session(mock_stripe, client, paid_corpus):
    """Checkout creates a Stripe session and payment record."""
    mock_session = MagicMock()
    mock_session.id = "cs_test_123"
    mock_session.url = "https://checkout.stripe.com/test"
    mock_stripe.checkout.Session.create.return_value = mock_session

    with patch("noosphere.core.payments.STRIPE_SECRET_KEY", "sk_test_xxx"):
        r = client.post(f"/api/v1/corpora/{paid_corpus['id']}/checkout", json={
            "payer_email": "buyer@example.com",
        })

    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "cs_test_123"
    assert body["checkout_url"] == "https://checkout.stripe.com/test"
    assert body["payment_id"]
    assert body["amount_cents"] == 500

    # Verify payment record created in DB
    from noosphere.core.db import get_conn
    conn = get_conn()
    row = conn.execute("SELECT * FROM payments WHERE id=?", (body["payment_id"],)).fetchone()
    assert row is not None
    assert row["status"] == "pending"
    assert row["corpus_id"] == paid_corpus["id"]


def test_checkout_no_stripe_key_returns_503(client, paid_corpus):
    """Without STRIPE_SECRET_KEY, checkout returns 503."""
    with patch("noosphere.core.payments.STRIPE_SECRET_KEY", ""):
        r = client.post(f"/api/v1/corpora/{paid_corpus['id']}/checkout", json={})
    assert r.status_code == 503


# ── Webhook handling ──


def test_webhook_checkout_completed(client, paid_corpus):
    """Webhook marks payment as completed."""
    from noosphere.core.db import get_conn

    # Insert a pending payment
    payment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    conn.execute(
        """INSERT INTO payments
           (id, corpus_id, stripe_session_id, payment_type, amount_cents, currency,
            status, created_at)
           VALUES (?, ?, 'cs_webhook_test', 'per_query', 500, 'usd', 'pending', ?)""",
        (payment_id, paid_corpus["id"], now),
    )
    conn.commit()

    event_payload = json.dumps({
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_webhook_test",
                "metadata": {
                    "corpus_id": paid_corpus["id"],
                    "payment_id": payment_id,
                },
                "customer": "cus_123",
                "customer_details": {"email": "buyer@example.com"},
                "payment_intent": "pi_123",
                "subscription": None,
            }
        }
    })

    with patch("noosphere.core.payments.STRIPE_SECRET_KEY", "sk_test_xxx"), \
         patch("noosphere.core.payments.STRIPE_WEBHOOK_SECRET", ""), \
         patch("noosphere.core.payments.stripe") as mock_stripe:
        mock_stripe.Event.construct_from.return_value = json.loads(event_payload)
        mock_stripe.api_key = "sk_test_xxx"

        r = client.post("/api/v1/stripe/webhook", content=event_payload,
                        headers={"stripe-signature": ""})

    assert r.status_code == 200
    assert r.json()["action"] == "payment_completed"

    # Verify DB updated
    row = conn.execute("SELECT status FROM payments WHERE id=?", (payment_id,)).fetchone()
    assert row["status"] == "completed"


def test_webhook_subscription_cancelled(client, paid_corpus):
    """Webhook cancels subscription."""
    from noosphere.core.db import get_conn

    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    sub_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO subscriptions
           (id, corpus_id, stripe_subscription_id, stripe_customer_id, status, created_at)
           VALUES (?, ?, 'sub_cancel_test', 'cus_456', 'active', ?)""",
        (sub_id, paid_corpus["id"], now),
    )
    conn.commit()

    event_payload = json.dumps({
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_cancel_test"}}
    })

    with patch("noosphere.core.payments.STRIPE_SECRET_KEY", "sk_test_xxx"), \
         patch("noosphere.core.payments.STRIPE_WEBHOOK_SECRET", ""), \
         patch("noosphere.core.payments.stripe") as mock_stripe:
        mock_stripe.Event.construct_from.return_value = json.loads(event_payload)
        mock_stripe.api_key = "sk_test_xxx"

        r = client.post("/api/v1/stripe/webhook", content=event_payload,
                        headers={"stripe-signature": ""})

    assert r.status_code == 200
    assert r.json()["action"] == "subscription_cancelled"

    row = conn.execute("SELECT status FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    assert row["status"] == "cancelled"


# ── Revenue dashboard ──


def test_revenue_stats(client, paid_corpus):
    """Revenue endpoint returns payment stats."""
    from noosphere.core.db import get_conn

    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    for i in range(3):
        conn.execute(
            """INSERT INTO payments
               (id, corpus_id, stripe_session_id, payment_type, amount_cents, currency,
                status, created_at, completed_at)
               VALUES (?, ?, ?, 'per_query', 500, 'usd', 'completed', ?, ?)""",
            (str(uuid.uuid4()), paid_corpus["id"], f"sess_{i}", now, now),
        )
    conn.commit()

    r = client.get(f"/api/v1/corpora/{paid_corpus['id']}/revenue")
    assert r.status_code == 200
    body = r.json()
    assert body["total_payments"] == 3
    assert body["total_revenue_cents"] == 1500
    assert len(body["recent_payments"]) == 3


def test_revenue_empty(client, paid_corpus):
    r = client.get(f"/api/v1/corpora/{paid_corpus['id']}/revenue")
    assert r.status_code == 200
    assert r.json()["total_payments"] == 0
