"""Stripe integration for Noosphere Cloud.

Two distinct payment flows:

1. Platform subscription — creators pay $9/month for Pro tier hosting.
   Same pattern as Feynman's app/pro/stripe.py.

2. Stripe Connect — when a consumer pays for a paid corpus on the platform,
   money flows through our Stripe Connect. Creator gets 90%, platform 10%.
   Self-hosted creators bypass this entirely (they use core/payments.py
   with their own Stripe keys).
"""

from __future__ import annotations

import os
import logging

import stripe
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from noosphere.cloud.db import (
    get_user,
    find_user_by_stripe_customer,
    update_user_tier,
    count_usage_today,
    count_user_corpora,
    count_queries_this_month,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cloud", tags=["cloud"])

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
STRIPE_PRO_PRICE_ID = os.getenv("STRIPE_PRO_PRICE_ID", "").strip()
APP_URL = os.getenv("APP_URL", "http://localhost:8420").strip()

# Platform commission on paid corpus revenue via Stripe Connect
PLATFORM_COMMISSION_PERCENT = 10

stripe.api_key = STRIPE_SECRET_KEY


def _sg(obj, key, default=None):
    """Safe key access for StripeObject (lacks .get and resists dict()).

    Stripe SDK's StripeObject supports obj[key] and `in` but not .get(),
    .to_dict_recursive(), or dict(obj). Use this helper to read fields
    from event payloads defensively.
    """
    try:
        return obj[key] if key in obj else default
    except (KeyError, TypeError, AttributeError):
        return default


def _is_noosphere_subscription(data) -> bool:
    """Whether a Subscription event's items reference our Pro price.

    OriginX.AI's Stripe account hosts multiple products; Stripe broadcasts
    `customer.subscription.*` events to every endpoint subscribed to that
    type, regardless of which product the subscription belongs to. Without
    this filter, a Feynman cancellation would run through Noosphere's
    handler and could incorrectly downgrade a Noosphere user who happens
    to share a Stripe customer_id.
    """
    if not STRIPE_PRO_PRICE_ID:
        # No price filter configured — accept all (preserves prior behavior).
        return True
    items_container = _sg(data, "items")
    if items_container is None:
        return False
    items_list = _sg(items_container, "data")
    if not items_list:
        return False
    for item in items_list:
        price = _sg(item, "price")
        if price is not None and _sg(price, "id") == STRIPE_PRO_PRICE_ID:
            return True
    return False


# ── Pro subscription (creator pays platform) ──


@router.post("/create-checkout-session")
async def create_checkout_session(request: Request):
    """Create a Stripe Checkout session for Pro subscription."""
    user_id = getattr(request.state, "user_id", None)
    email = getattr(request.state, "email", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not STRIPE_SECRET_KEY or not STRIPE_PRO_PRICE_ID:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    user = get_user(user_id)
    customer_id = user.get("stripe_customer_id") if user else None

    try:
        session_params = {
            "mode": "subscription",
            "line_items": [{"price": STRIPE_PRO_PRICE_ID, "quantity": 1}],
            "success_url": f"{APP_URL}/?subscription=success",
            "cancel_url": f"{APP_URL}/?subscription=canceled",
            "metadata": {"user_id": user_id},
        }
        if customer_id:
            session_params["customer"] = customer_id
        else:
            session_params["customer_email"] = email

        session = stripe.checkout.Session.create(**session_params)
        return {"url": session.url}
    except stripe.StripeError as e:
        log.error("Stripe checkout error: %s", e)
        raise HTTPException(status_code=500, detail="Payment initialization failed")


@router.post("/create-portal-session")
async def create_portal_session(request: Request):
    """Create a Stripe billing portal session for subscription management."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    user = get_user(user_id)
    customer_id = user.get("stripe_customer_id") if user else None
    if not customer_id:
        raise HTTPException(status_code=400, detail="No active subscription")

    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{APP_URL}/",
        )
        return {"url": session.url}
    except stripe.StripeError as e:
        log.error("Stripe portal error: %s", e)
        raise HTTPException(status_code=500, detail="Portal session failed")


@router.get("/subscription")
async def get_subscription_status(request: Request):
    """Get the current user's subscription status."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    user = get_user(user_id)
    if not user:
        return {"tier": "free", "subscription_status": None}

    return {
        "tier": user.get("tier", "free"),
        "subscription_status": user.get("subscription_status"),
        "stripe_customer_id": user.get("stripe_customer_id"),
    }


# ── Stripe Connect (paid corpus revenue sharing) ──


@router.post("/connect/onboard")
async def connect_onboard(request: Request):
    """Start Stripe Connect onboarding for a creator.

    Creates a Connect account and returns an onboarding URL.
    After onboarding, the creator can receive payments for their paid corpora
    with the platform taking a 10% commission.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    user = get_user(user_id)
    email = user.get("email", "") if user else ""

    try:
        from noosphere.core.db import get_conn
        from datetime import datetime, timezone

        existing_acct = (user or {}).get("stripe_connect_account_id", "") or ""
        if existing_acct:
            account_id = existing_acct
        else:
            account = stripe.Account.create(
                type="express",
                email=email,
                metadata={"user_id": user_id},
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                },
            )
            account_id = account.id
            conn = get_conn()
            conn.execute(
                "UPDATE users SET stripe_connect_account_id=?, updated_at=? WHERE id=?",
                (account_id, datetime.now(timezone.utc).isoformat(), user_id),
            )
            conn.commit()

        link = stripe.AccountLink.create(
            account=account_id,
            refresh_url=f"{APP_URL}/?connect=refresh",
            return_url=f"{APP_URL}/?connect=complete",
            type="account_onboarding",
        )

        return {"url": link.url, "account_id": account_id}
    except stripe.StripeError as e:
        log.error("Connect onboarding error: %s – %s", type(e).__name__, e.user_message or e)
        raise HTTPException(status_code=500, detail=str(e.user_message or "Onboarding failed"))


@router.post("/connect/crypto-payout")
async def set_crypto_payout(request: Request):
    """Register a Base wallet address for receiving USDC from agent payments.

    Crypto onboarding doesn't go through Stripe — there's nothing to verify
    on our end, the address is just a routing target. The agent pays the
    creator directly on-chain via the x402 facilitator. (Per-creator on-chain
    platform fees aren't enforceable without a custom contract — for now,
    cloud creators get 100% of crypto agent revenue. Cloud's 10% cut still
    applies on the fiat rail via Stripe Connect.)
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    body = await request.json()
    address = (body.get("address") or "").strip()
    if not address:
        raise HTTPException(status_code=400, detail="address required")
    # Loose sanity check — accept anything that looks like an EVM address.
    # The on-chain transaction itself is the authority; we don't check
    # checksum or chain liveness here.
    if not (address.startswith("0x") and len(address) == 42):
        raise HTTPException(
            status_code=400, detail="address must be a 0x-prefixed 40-hex-char string"
        )

    from datetime import datetime, timezone

    from noosphere.core.db import get_conn

    conn = get_conn()
    conn.execute(
        "UPDATE users SET crypto_payout_address=?, updated_at=? WHERE id=?",
        (address, datetime.now(timezone.utc).isoformat(), user_id),
    )
    conn.commit()
    return {"address": address}


@router.post("/connect/checkout")
async def connect_checkout(request: Request):
    """Create a checkout session for a paid corpus with Stripe Connect.

    The payment goes to the creator's Connect account minus platform commission.
    This replaces core/payments.py checkout for cloud-hosted corpora.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    body = await request.json()
    corpus_id = body.get("corpus_id", "")
    if not corpus_id:
        raise HTTPException(status_code=400, detail="corpus_id required")

    from noosphere.core.corpus import get_corpus
    from noosphere.core.payments import get_pricing

    corpus = get_corpus(corpus_id)
    if not corpus:
        raise HTTPException(status_code=404, detail="Corpus not found")
    if corpus.get("access_level") != "paid":
        raise HTTPException(status_code=400, detail="Corpus is not set to paid")

    pricing = get_pricing(corpus)
    if not pricing:
        raise HTTPException(status_code=400, detail="No pricing configured")

    # Find the creator's Connect account
    owner_id = corpus.get("owner_id", "")
    if not owner_id:
        raise HTTPException(status_code=400, detail="Corpus has no owner")

    owner = get_user(owner_id)
    connect_account_id = owner.get("stripe_connect_account_id", "") if owner else ""
    if not connect_account_id:
        raise HTTPException(status_code=400, detail="Creator has not completed Stripe onboarding")

    amount_cents = pricing.get("amount_cents", 0)
    platform_fee = int(amount_cents * PLATFORM_COMMISSION_PERCENT / 100)

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": pricing.get("currency", "usd"),
                    "unit_amount": amount_cents,
                    "product_data": {
                        "name": f"Access: {corpus.get('name', 'Knowledge Base')}",
                    },
                },
                "quantity": 1,
            }],
            payment_intent_data={
                "application_fee_amount": platform_fee,
                "transfer_data": {"destination": connect_account_id},
            },
            success_url=f"{APP_URL}/?payment=success&corpus={corpus_id}",
            cancel_url=f"{APP_URL}/?payment=canceled",
            metadata={
                "corpus_id": corpus_id,
                "buyer_id": user_id,
                "owner_id": owner_id,
            },
        )
        return {"url": session.url, "session_id": session.id}
    except stripe.StripeError as e:
        log.error("Connect checkout error: %s", e)
        raise HTTPException(status_code=500, detail="Payment initialization failed")


# ── User profile & usage ──


@router.get("/me")
async def cloud_me(request: Request):
    """Get authenticated user profile with tier and usage summary."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    user = get_user(user_id)
    if not user:
        return {"user_id": user_id, "tier": "free"}

    corpora_count = count_user_corpora(user_id)
    queries_month = count_queries_this_month(user_id)

    return {
        "user_id": user["id"],
        "email": user.get("email", ""),
        "tier": user.get("tier", "free"),
        "created_at": user.get("created_at", ""),
        "corpora_count": corpora_count,
        "queries_this_month": queries_month,
        "subscription_status": user.get("subscription_status"),
    }


@router.get("/usage")
async def cloud_usage(request: Request):
    """Get detailed usage stats for the authenticated user."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    from noosphere.cloud.quota import QUOTA_LIMITS, RESOURCE_LIMITS

    user = get_user(user_id)
    tier = user.get("tier", "free") if user else "free"
    daily_limits = QUOTA_LIMITS.get(tier, QUOTA_LIMITS["free"])
    resource_limits = RESOURCE_LIMITS.get(tier, RESOURCE_LIMITS["free"])

    usage_today = {}
    for action in daily_limits:
        usage_today[action] = {
            "used": count_usage_today(user_id, action),
            "limit": daily_limits[action],
        }

    return {
        "tier": tier,
        "daily_usage": usage_today,
        "resources": {
            "corpora": {
                "used": count_user_corpora(user_id),
                "limit": resource_limits["corpora"],
            },
            "queries_this_month": {
                "used": count_queries_this_month(user_id),
                "limit": resource_limits["queries_per_month"],
            },
        },
    }


# ── Webhook ──


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events for platform subscriptions and Connect payments."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook not configured")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]
    event_id = event["id"]
    data = event["data"]["object"]

    try:
        if event_type == "checkout.session.completed":
            user_id = _sg(_sg(data, "metadata") or {}, "user_id")
            customer_id = _sg(data, "customer")
            subscription_id = _sg(data, "subscription")
            if user_id and subscription_id:
                # Platform Pro subscription
                update_user_tier(
                    user_id, "pro", customer_id, subscription_id,
                    subscription_status="active",
                )
                log.info("User %s upgraded to Pro", user_id)

        elif event_type == "customer.subscription.updated":
            if not _is_noosphere_subscription(data):
                log.debug("Ignoring subscription.updated for non-Noosphere price (event_id=%s)", event_id)
                return JSONResponse({"status": "ok", "ignored": "not Noosphere price"})
            customer_id = _sg(data, "customer")
            status = _sg(data, "status")
            user = find_user_by_stripe_customer(customer_id) if customer_id else None
            if user:
                tier = "pro" if status in ("active", "trialing") else "free"
                ended_at = None
                if status in ("canceled", "unpaid", "past_due"):
                    from datetime import datetime, timezone
                    ended_at = datetime.now(timezone.utc).isoformat()
                update_user_tier(
                    str(user["id"]), tier,
                    subscription_status=status,
                    subscription_ended_at=ended_at,
                )
                log.info("Subscription updated: user=%s status=%s tier=%s", user["id"], status, tier)

        elif event_type == "customer.subscription.deleted":
            if not _is_noosphere_subscription(data):
                log.debug("Ignoring subscription.deleted for non-Noosphere price (event_id=%s)", event_id)
                return JSONResponse({"status": "ok", "ignored": "not Noosphere price"})
            customer_id = _sg(data, "customer")
            user = find_user_by_stripe_customer(customer_id) if customer_id else None
            if user:
                from datetime import datetime, timezone
                ended_at = datetime.now(timezone.utc).isoformat()
                update_user_tier(
                    str(user["id"]), "free",
                    subscription_status="canceled",
                    subscription_ended_at=ended_at,
                )
                log.info("Subscription cancelled: user=%s", user["id"])
    except Exception:
        log.exception("Webhook handler failed: event_id=%s type=%s", event_id, event_type)
        raise

    return JSONResponse({"status": "ok"})
