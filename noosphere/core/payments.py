"""Stripe payment integration for paid corpus access.

Self-hosted creators use their own Stripe keys and keep 100% of revenue.
Supports two pricing models:
  - per_query: one-time payment grants N queries (stored as a payment record)
  - subscription: recurring monthly access (Stripe subscription)
"""

import json
import logging
import uuid
from datetime import datetime, timezone

import stripe

from noosphere.core.config import STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_SUCCESS_URL, STRIPE_CANCEL_URL
from noosphere.core.db import get_conn

log = logging.getLogger(__name__)


class PaymentError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _ensure_stripe():
    """Check that Stripe is configured."""
    if not STRIPE_SECRET_KEY:
        raise PaymentError(
            "Stripe is not configured. Set STRIPE_SECRET_KEY to enable paid access.",
            status_code=503,
        )
    stripe.api_key = STRIPE_SECRET_KEY


def get_pricing(corpus: dict) -> dict | None:
    """Parse pricing config from corpus pricing_json field.

    Expected format:
    {
        "type": "per_query" | "subscription",
        "amount_cents": 500,        # $5.00 for per_query, or monthly price for subscription
        "currency": "usd",
        "queries_per_payment": 100,  # only for per_query
        "stripe_price_id": "..."     # only for subscription (created via Stripe dashboard)
    }
    """
    raw = corpus.get("pricing_json")
    if not raw:
        return None
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    return raw


def create_checkout_session(
    corpus: dict,
    *,
    success_url: str = "",
    cancel_url: str = "",
    payer_email: str = "",
    agent_id: str = "",
) -> dict:
    """Create a Stripe Checkout session for a paid corpus.

    Returns dict with session_id, checkout_url, and payment record id.
    """
    _ensure_stripe()

    pricing = get_pricing(corpus)
    if not pricing:
        raise PaymentError("This corpus has no pricing configured")

    pricing_type = pricing.get("type", "per_query")
    amount_cents = pricing.get("amount_cents", 0)
    currency = pricing.get("currency", "usd")

    if amount_cents <= 0:
        raise PaymentError("Invalid price configured")

    corpus_id = corpus["id"]
    corpus_name = corpus.get("name", "Knowledge Base")
    payment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    s_url = success_url or STRIPE_SUCCESS_URL or "http://localhost:8420/payment/success"
    c_url = cancel_url or STRIPE_CANCEL_URL or "http://localhost:8420/payment/cancel"

    # Add payment_id to success URL so the frontend can confirm
    if "?" in s_url:
        s_url += f"&payment_id={payment_id}"
    else:
        s_url += f"?payment_id={payment_id}"

    session_params = {
        "mode": "subscription" if pricing_type == "subscription" else "payment",
        "success_url": s_url,
        "cancel_url": c_url,
        "metadata": {
            "corpus_id": corpus_id,
            "payment_id": payment_id,
            "agent_id": agent_id,
        },
    }

    if payer_email:
        session_params["customer_email"] = payer_email

    if pricing_type == "subscription":
        # Subscription uses a pre-created Stripe Price
        price_id = pricing.get("stripe_price_id")
        if not price_id:
            raise PaymentError("Subscription pricing requires stripe_price_id")
        session_params["line_items"] = [{"price": price_id, "quantity": 1}]
    else:
        # One-time payment
        session_params["line_items"] = [{
            "price_data": {
                "currency": currency,
                "unit_amount": amount_cents,
                "product_data": {
                    "name": f"Access: {corpus_name}",
                    "description": f"{pricing.get('queries_per_payment', 100)} queries",
                },
            },
            "quantity": 1,
        }]

    session = stripe.checkout.Session.create(**session_params)

    # Record the pending payment
    conn = get_conn()
    conn.execute(
        """INSERT INTO payments
           (id, corpus_id, stripe_session_id, payment_type, amount_cents, currency,
            status, payer_email, payer_agent_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
        (payment_id, corpus_id, session.id, pricing_type, amount_cents, currency,
         payer_email, agent_id, now),
    )
    conn.commit()

    return {
        "payment_id": payment_id,
        "session_id": session.id,
        "checkout_url": session.url,
        "pricing_type": pricing_type,
        "amount_cents": amount_cents,
        "currency": currency,
    }


def handle_webhook_event(payload: bytes, sig_header: str) -> dict:
    """Process a Stripe webhook event. Returns action taken.

    Handles:
    - checkout.session.completed — mark payment as completed, create subscription record
    - customer.subscription.deleted — deactivate subscription
    - charge.refunded — mark payment as refunded
    """
    _ensure_stripe()

    if STRIPE_WEBHOOK_SECRET:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    else:
        event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        return _handle_checkout_completed(data)
    elif event_type == "customer.subscription.deleted":
        return _handle_subscription_cancelled(data)
    elif event_type == "charge.refunded":
        return _handle_refund(data)

    return {"action": "ignored", "event_type": event_type}


def _handle_checkout_completed(session) -> dict:
    """Mark payment as completed. For subscriptions, also create subscription record."""
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()

    session_id = session.get("id", "")
    metadata = session.get("metadata", {})
    corpus_id = metadata.get("corpus_id", "")
    payment_id = metadata.get("payment_id", "")
    customer_id = session.get("customer", "")
    customer_email = session.get("customer_details", {}).get("email", "")

    # Update payment record
    conn.execute(
        """UPDATE payments SET status='completed', stripe_payment_intent=?,
           stripe_customer_id=?, payer_email=COALESCE(NULLIF(payer_email,''), ?),
           completed_at=? WHERE stripe_session_id=?""",
        (session.get("payment_intent", ""), customer_id, customer_email, now, session_id),
    )

    # For subscriptions, create subscription record
    subscription_id = session.get("subscription")
    if subscription_id and corpus_id:
        sub_id = str(uuid.uuid4())
        conn.execute(
            """INSERT OR REPLACE INTO subscriptions
               (id, corpus_id, stripe_subscription_id, stripe_customer_id,
                payer_email, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'active', ?)""",
            (sub_id, corpus_id, subscription_id, customer_id, customer_email, now),
        )

    conn.commit()
    log.info(f"Payment completed: session={session_id} corpus={corpus_id}")
    return {"action": "payment_completed", "corpus_id": corpus_id, "payment_id": payment_id}


def _handle_subscription_cancelled(subscription) -> dict:
    """Mark subscription as cancelled."""
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    sub_stripe_id = subscription.get("id", "")

    conn.execute(
        "UPDATE subscriptions SET status='cancelled', cancelled_at=? WHERE stripe_subscription_id=?",
        (now, sub_stripe_id),
    )
    conn.commit()
    log.info(f"Subscription cancelled: {sub_stripe_id}")
    return {"action": "subscription_cancelled", "stripe_subscription_id": sub_stripe_id}


def _handle_refund(charge) -> dict:
    """Mark the related payment as refunded."""
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    payment_intent = charge.get("payment_intent", "")

    conn.execute(
        "UPDATE payments SET status='refunded', completed_at=? WHERE stripe_payment_intent=?",
        (now, payment_intent),
    )
    conn.commit()
    log.info(f"Payment refunded: intent={payment_intent}")
    return {"action": "refunded", "payment_intent": payment_intent}


def verify_paid_access(corpus_id: str, bearer_token: str | None = None, agent_id: str = "") -> bool:
    """Check if a requester has valid paid access to a corpus.

    Access is granted if:
    1. There's an active subscription for this corpus matching the customer, OR
    2. There's a completed per_query payment with remaining query budget

    For per_query: the bearer_token is the payment_id returned at checkout.
    For subscription: the bearer_token is the stripe_customer_id or payer_email.
    """
    conn = get_conn()

    if not bearer_token:
        return False

    # Check subscriptions — token could be customer_id or email
    sub = conn.execute(
        """SELECT id FROM subscriptions
           WHERE corpus_id=? AND status='active'
           AND (stripe_customer_id=? OR payer_email=?)""",
        (corpus_id, bearer_token, bearer_token),
    ).fetchone()
    if sub:
        return True

    # Check per-query payments — token is the payment_id
    payment = conn.execute(
        """SELECT id, payment_type, amount_cents, metadata_json
           FROM payments
           WHERE corpus_id=? AND id=? AND status='completed'""",
        (corpus_id, bearer_token),
    ).fetchone()
    if payment:
        pricing = get_pricing_for_corpus(corpus_id)
        if not pricing:
            return True  # No pricing means free after payment

        queries_allowed = pricing.get("queries_per_payment", 100)
        used = conn.execute(
            "SELECT COUNT(*) as n FROM query_logs WHERE corpus_id=? AND token_id=?",
            (corpus_id, bearer_token),
        ).fetchone()["n"]

        if used < queries_allowed:
            return True

    return False


def get_pricing_for_corpus(corpus_id: str) -> dict | None:
    """Load pricing config for a corpus by ID."""
    conn = get_conn()
    row = conn.execute("SELECT pricing_json FROM corpora WHERE id=?", (corpus_id,)).fetchone()
    if not row or not row["pricing_json"]:
        return None
    try:
        return json.loads(row["pricing_json"])
    except (json.JSONDecodeError, TypeError):
        return None


def get_revenue_stats(corpus_id: str) -> dict:
    """Revenue dashboard data for a corpus."""
    conn = get_conn()

    payments = conn.execute(
        """SELECT COUNT(*) as count, COALESCE(SUM(amount_cents), 0) as total_cents
           FROM payments WHERE corpus_id=? AND status='completed'""",
        (corpus_id,),
    ).fetchone()

    active_subs = conn.execute(
        "SELECT COUNT(*) as n FROM subscriptions WHERE corpus_id=? AND status='active'",
        (corpus_id,),
    ).fetchone()["n"]

    recent = conn.execute(
        """SELECT id, payment_type, amount_cents, currency, status, payer_email, created_at, completed_at
           FROM payments WHERE corpus_id=? ORDER BY created_at DESC LIMIT 20""",
        (corpus_id,),
    ).fetchall()

    return {
        "corpus_id": corpus_id,
        "total_payments": payments["count"],
        "total_revenue_cents": payments["total_cents"],
        "active_subscriptions": active_subs,
        "recent_payments": [dict(r) for r in recent],
    }
