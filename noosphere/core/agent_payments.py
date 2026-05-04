"""Agent payment facilitator abstraction (x402-aligned).

Noosphere does not custody agent funds or run KYC. When an agent hits a paid
corpus without valid auth, we return an x402 challenge listing every active
facilitator's payment options in the `accepts` array. The agent's payment
client picks one it supports (Coinbase x402 over USDC, Stripe Agent Toolkit
over fiat, etc.), satisfies that challenge, and re-presents the request with
`X-PAYMENT: <proof>`. We extract the `scheme` from the proof, route to the
matching facilitator's `verify()`, mint a short-lived access_token on
success, and record an audit row.

Multiple facilitators run side by side — agents pick whichever rail their
SDK speaks. Configure with:

    NOOSPHERE_PAYMENT_FACILITATORS=coinbase_x402,stripe_agent

(or the singular ``NOOSPHERE_PAYMENT_FACILITATOR`` for backwards compat).
The default ``mock`` facilitator is safe for local dev — drop it for prod.

`AigisPayFacilitator` exists as a seam for the user's own product but is
intentionally non-functional: aigis-pay's escrow + reputation model fits
high-value transactions, not per-query micropayments.

Spec: https://x402.org
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol

from noosphere.core.config import ENABLE_CLOUD, STRIPE_SECRET_KEY
from noosphere.core.db import get_conn

log = logging.getLogger(__name__)


# Cloud platform commission on agent fiat settlements. Mirrors the existing
# human-Checkout split in noosphere.cloud.stripe_connect (PLATFORM_COMMISSION_PERCENT).
# Self-hosted nodes get 100% — this only kicks in when ENABLE_CLOUD is set.
PLATFORM_FEE_PERCENT = int(os.getenv("NOOSPHERE_PLATFORM_FEE_PERCENT", "10"))


# Token TTL for the access_token minted on successful settlement. Short by
# default — the agent re-pays per-query rather than getting an unlimited pass.
ACCESS_TOKEN_TTL_SECONDS = int(os.getenv("NOOSPHERE_AGENT_ACCESS_TTL_SECONDS", "300"))


def _parse_facilitator_names() -> list[str]:
    """Resolve the active facilitators from env. Plural list wins; singular
    is a backwards-compat fallback. Empty config falls back to ['mock']."""
    plural = os.getenv("NOOSPHERE_PAYMENT_FACILITATORS", "").strip()
    if plural:
        return [n.strip().lower() for n in plural.split(",") if n.strip()]
    singular = os.getenv("NOOSPHERE_PAYMENT_FACILITATOR", "").strip().lower()
    if singular:
        return [singular]
    return ["mock"]


# Live names list — module-level so tests can monkeypatch. The functions
# below re-read this on each call so changes during a test session take
# effect without re-importing.
FACILITATOR_NAMES: list[str] = _parse_facilitator_names()
# Backwards-compat singular alias still readable by older tests.
FACILITATOR_NAME = FACILITATOR_NAMES[0] if FACILITATOR_NAMES else "mock"

# Coinbase x402 facilitator base URL + payout address (USDC on Base by default).
COINBASE_X402_FACILITATOR_URL = os.getenv(
    "NOOSPHERE_X402_FACILITATOR_URL", "https://x402.org/facilitator"
)
COINBASE_X402_PAYOUT_ADDRESS = os.getenv("NOOSPHERE_X402_PAYOUT_ADDRESS", "")
COINBASE_X402_NETWORK = os.getenv("NOOSPHERE_X402_NETWORK", "base")
# USDC on Base mainnet. Override for testnet or other stablecoins.
COINBASE_X402_ASSET = os.getenv(
    "NOOSPHERE_X402_ASSET", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
)

# Stripe Agent Toolkit facilitator. Reuses the existing STRIPE_SECRET_KEY.
# `STRIPE_AGENT_PAY_TO` is the Stripe Connect account ID where agent
# settlements should land — typically the same Connect account already used
# for human Checkout (see noosphere.cloud.stripe_connect).
STRIPE_AGENT_PAY_TO = os.getenv("NOOSPHERE_STRIPE_AGENT_PAY_TO", "")


@dataclass
class VerificationResult:
    """Outcome of a facilitator verifying an X-PAYMENT proof."""

    valid: bool
    amount_cents: int = 0
    payer_id: str = ""
    settlement_tx: str = ""
    scheme: str = ""
    network: str = ""
    asset: str = ""
    reason: str = ""


class PaymentFacilitator(Protocol):
    """Pluggable payment verifier. Implementations call out to external
    facilitators (Coinbase x402, Stripe Agent Toolkit) or — for tests —
    verify locally."""

    name: str
    schemes: tuple[str, ...]

    def accepts_for(self, corpus: dict, *, resource: str) -> list[dict]:
        """Return the x402 `accepts` entries this facilitator offers for this
        corpus. Empty list means this facilitator can't price the corpus
        (e.g. no pricing configured, or facilitator wants different metadata).
        """
        ...

    def verify(
        self,
        proof: str,
        *,
        corpus: dict,
        expected_amount_cents: int,
        resource: str,
    ) -> VerificationResult:
        """Verify a payment proof against the expected amount + resource."""
        ...


# ── Helpers ────────────────────────────────────────────────────────


def _per_query_amount_cents(corpus: dict) -> int:
    """Look up the per-query price for a corpus. Returns 0 if not configured
    or if the corpus uses subscription pricing (which doesn't fit
    per-request x402 micropayments)."""
    raw = corpus.get("pricing_json")
    if not raw:
        return 0
    try:
        pricing = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return 0
    if pricing.get("type") != "per_query":
        return 0
    try:
        return int(pricing.get("amount_cents") or 0)
    except (TypeError, ValueError):
        return 0


@dataclass
class PayoutResolution:
    """Where this corpus's agent settlements should land.

    `stripe_connect_id` is the Connect account that receives fiat settlements.
    `crypto_address` is the wallet that receives USDC/Base settlements.
    `platform_fee_cents` is the cut the cloud platform takes (always 0 in
    self-hosted mode); facilitators communicate it to the agent via the
    x402 challenge `extra` field and validate it on the way back.
    """

    stripe_connect_id: str = ""
    crypto_address: str = ""
    platform_fee_cents: int = 0


def _resolve_payout(corpus: dict) -> PayoutResolution:
    """Pick the right payout destination for a corpus.

    Self-hosted: returns the global env-var addresses (operator keeps 100%).
    Cloud: looks up the corpus's creator (owner_id → cloud users table, or
    org_id → organizations table) and uses their onboarded Stripe Connect
    account / crypto wallet, with a platform fee carved off the price.

    For unconfigured creators (haven't onboarded Stripe / haven't set a
    crypto address), the corresponding rail is silently disabled — the
    facilitator returns an empty `accepts` entry rather than routing money
    to the wrong place.
    """
    if not ENABLE_CLOUD:
        return PayoutResolution(
            stripe_connect_id=STRIPE_AGENT_PAY_TO,
            crypto_address=COINBASE_X402_PAYOUT_ADDRESS,
            platform_fee_cents=0,
        )

    stripe_id = ""
    crypto = ""
    org_id = corpus.get("org_id")
    owner_id = corpus.get("owner_id")
    if org_id:
        try:
            row = get_conn().execute(
                "SELECT stripe_connect_account_id FROM organizations WHERE id=?",
                (org_id,),
            ).fetchone()
            stripe_id = (row["stripe_connect_account_id"] or "") if row else ""
        except Exception as e:
            log.warning("org connect lookup failed: %s", e)
    elif owner_id:
        try:
            from noosphere.cloud.db import get_user

            owner = get_user(owner_id) or {}
            # Cloud reuses `users.stripe_customer_id` to store the Connect
            # account ID — see noosphere/cloud/stripe_connect.py:217.
            stripe_id = owner.get("stripe_customer_id", "") or ""
            crypto = owner.get("crypto_payout_address", "") or ""
        except ImportError:
            log.warning("cloud db unavailable but ENABLE_CLOUD is set")

    if not crypto:
        # Per-creator crypto onboarding isn't wired yet — fall back to the
        # platform's global address so deployments aren't blocked. Cloud
        # operators who don't want this can leave the env var empty.
        crypto = COINBASE_X402_PAYOUT_ADDRESS

    fee = 0
    if stripe_id and PLATFORM_FEE_PERCENT > 0:
        amount = _per_query_amount_cents(corpus)
        fee = max(0, amount * PLATFORM_FEE_PERCENT // 100)
    return PayoutResolution(
        stripe_connect_id=stripe_id,
        crypto_address=crypto,
        platform_fee_cents=fee,
    )


def _extract_scheme(proof: str) -> str:
    """Best-effort scheme detection from an X-PAYMENT proof.

    Three formats supported:
      1. Mock prefix: "mock:<amount>:<payer>" → scheme "mock"
      2. Stripe PaymentIntent ID prefix: "pi_..." → scheme "stripe-pi"
      3. Base64-encoded x402 JSON: extract the `scheme` field per spec
    """
    if not proof:
        return ""
    if proof.startswith("mock:"):
        return "mock"
    if proof.startswith("pi_"):
        return "stripe-pi"
    try:
        decoded = base64.b64decode(proof.encode(), validate=False).decode("utf-8")
        data = json.loads(decoded)
        if isinstance(data, dict):
            return str(data.get("scheme") or "").strip()
    except (binascii.Error, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        pass
    return ""


# ── Mock facilitator (default; tests, local dev) ──────────────────


class MockFacilitator:
    """Deterministic facilitator for tests and local dev.

    Accepts a proof of the form `mock:<amount_cents>:<payer_id>` — any other
    string is rejected. Always issues `accepts` entries when the corpus has
    per-query pricing configured.
    """

    name = "mock"
    schemes: tuple[str, ...] = ("mock",)

    def accepts_for(self, corpus: dict, *, resource: str) -> list[dict]:
        amount = _per_query_amount_cents(corpus)
        if amount <= 0:
            return []
        return [
            {
                "scheme": "mock",
                "network": "noosphere-test",
                "maxAmountRequired": str(amount),
                "asset": "USD-cents",
                "resource": resource,
                "payTo": "noosphere://mock",
                "description": f"Per-query access to {corpus.get('name', 'corpus')}",
                "extra": {"corpus_id": corpus["id"]},
            }
        ]

    def verify(
        self,
        proof: str,
        *,
        corpus: dict,
        expected_amount_cents: int,
        resource: str,
    ) -> VerificationResult:
        if not proof or not proof.startswith("mock:"):
            return VerificationResult(valid=False, reason="proof must start with mock:")
        parts = proof.split(":", 2)
        if len(parts) != 3:
            return VerificationResult(valid=False, reason="malformed mock proof")
        try:
            amount = int(parts[1])
        except ValueError:
            return VerificationResult(valid=False, reason="amount not integer")
        if amount < expected_amount_cents:
            return VerificationResult(
                valid=False,
                reason=f"insufficient amount: got {amount}, need {expected_amount_cents}",
            )
        return VerificationResult(
            valid=True,
            amount_cents=amount,
            payer_id=parts[2] or "mock-payer",
            settlement_tx=f"mock-tx-{secrets.token_hex(8)}",
            scheme="mock",
            network="noosphere-test",
            asset="USD-cents",
        )


# ── Coinbase x402 facilitator (crypto / USDC on Base) ──────────────


class CoinbaseX402Facilitator:
    """Calls out to the Coinbase x402 facilitator over HTTP.

    Lazy-imports `httpx` so unit tests don't need to mock it unless they
    actually exercise this facilitator. Configure with:
      NOOSPHERE_X402_FACILITATOR_URL — facilitator base URL
      NOOSPHERE_X402_PAYOUT_ADDRESS — recipient (USDC on Base default)
      NOOSPHERE_X402_NETWORK         — e.g. "base", "base-sepolia"
      NOOSPHERE_X402_ASSET           — token contract address
    """

    name = "coinbase_x402"
    schemes: tuple[str, ...] = ("exact",)

    def accepts_for(self, corpus: dict, *, resource: str) -> list[dict]:
        amount = _per_query_amount_cents(corpus)
        payout = _resolve_payout(corpus)
        if amount <= 0 or not payout.crypto_address:
            return []
        return [
            {
                "scheme": "exact",
                "network": COINBASE_X402_NETWORK,
                "maxAmountRequired": str(amount),
                "asset": COINBASE_X402_ASSET,
                "resource": resource,
                "payTo": payout.crypto_address,
                "description": f"Per-query access to {corpus.get('name', 'corpus')}",
                "extra": {
                    "corpus_id": corpus["id"],
                    "max_age_seconds": 60,
                },
            }
        ]

    def verify(
        self,
        proof: str,
        *,
        corpus: dict,
        expected_amount_cents: int,
        resource: str,
    ) -> VerificationResult:
        if not proof:
            return VerificationResult(valid=False, reason="missing proof")
        payout = _resolve_payout(corpus)
        if not payout.crypto_address:
            return VerificationResult(
                valid=False, reason="no crypto payout address configured for this corpus"
            )
        try:
            import httpx
        except ImportError:
            return VerificationResult(
                valid=False,
                reason="httpx not installed — cannot call x402 facilitator",
            )
        try:
            resp = httpx.post(
                f"{COINBASE_X402_FACILITATOR_URL.rstrip('/')}/verify",
                json={
                    "x402Version": 1,
                    "paymentPayload": proof,
                    "paymentRequirements": {
                        "scheme": "exact",
                        "network": COINBASE_X402_NETWORK,
                        "maxAmountRequired": str(expected_amount_cents),
                        "asset": COINBASE_X402_ASSET,
                        "resource": resource,
                        "payTo": payout.crypto_address,
                    },
                },
                timeout=15,
            )
        except Exception as e:
            return VerificationResult(valid=False, reason=f"facilitator error: {e}")
        if resp.status_code != 200:
            return VerificationResult(
                valid=False,
                reason=f"facilitator returned {resp.status_code}: {resp.text[:200]}",
            )
        body = resp.json() if resp.content else {}
        if not body.get("isValid"):
            return VerificationResult(
                valid=False, reason=body.get("invalidReason", "facilitator rejected")
            )
        return VerificationResult(
            valid=True,
            amount_cents=int(body.get("amount", expected_amount_cents)),
            payer_id=body.get("payer", "") or "",
            settlement_tx=body.get("transaction", "") or "",
            scheme="exact",
            network=COINBASE_X402_NETWORK,
            asset=COINBASE_X402_ASSET,
        )


# ── Stripe Agent Toolkit facilitator (fiat / cards) ────────────────


class StripeAgentToolkitFacilitator:
    """Settles via a Stripe `PaymentIntent` created by the agent's payment
    client (Stripe Agent Toolkit, OpenAI Operator with stored card, etc.).

    The agent's flow:
      1. Receives 402 with `accepts` listing scheme `stripe-pi` and our
         Connect account ID in `payTo`.
      2. Creates a `PaymentIntent` on its own Stripe SDK with
         `transfer_data.destination = payTo` and amount >= maxAmountRequired.
      3. Confirms it (off_session if pre-authorized).
      4. Sends the resulting `pi_...` ID back as `X-PAYMENT`.

    We retrieve the intent and validate status, amount, currency, and
    transfer destination before granting access. No funds touch Noosphere.

    Configure with:
      STRIPE_SECRET_KEY               — already set if human Checkout works
      NOOSPHERE_STRIPE_AGENT_PAY_TO   — Connect account ID receiving payouts
    """

    name = "stripe_agent"
    schemes: tuple[str, ...] = ("stripe-pi",)

    def accepts_for(self, corpus: dict, *, resource: str) -> list[dict]:
        amount = _per_query_amount_cents(corpus)
        payout = _resolve_payout(corpus)
        if amount <= 0 or not STRIPE_SECRET_KEY or not payout.stripe_connect_id:
            return []
        extra: dict = {
            "corpus_id": corpus["id"],
            "max_age_seconds": 600,
        }
        if payout.platform_fee_cents > 0:
            # Communicated to the agent so its Stripe Agent Toolkit / SDK
            # sets `application_fee_amount` when creating the PaymentIntent.
            # We re-validate it on verify(); under-paying the platform fee
            # is rejected, so a misbehaving agent SDK can't bypass the cut.
            extra["application_fee_amount"] = str(payout.platform_fee_cents)
        return [
            {
                "scheme": "stripe-pi",
                "network": "stripe",
                "maxAmountRequired": str(amount),
                "asset": "usd-cents",
                "resource": resource,
                "payTo": payout.stripe_connect_id,
                "description": f"Per-query access to {corpus.get('name', 'corpus')}",
                "extra": extra,
            }
        ]

    def verify(
        self,
        proof: str,
        *,
        corpus: dict,
        expected_amount_cents: int,
        resource: str,
    ) -> VerificationResult:
        if not STRIPE_SECRET_KEY:
            return VerificationResult(
                valid=False, reason="STRIPE_SECRET_KEY not configured"
            )
        intent_id = self._extract_pi_id(proof)
        if not intent_id:
            return VerificationResult(
                valid=False, reason="cannot extract PaymentIntent ID from proof"
            )
        payout = _resolve_payout(corpus)
        try:
            import stripe

            stripe.api_key = STRIPE_SECRET_KEY
            intent = stripe.PaymentIntent.retrieve(intent_id)
        except Exception as e:
            return VerificationResult(valid=False, reason=f"stripe error: {e}")
        status = getattr(intent, "status", "") or ""
        if status != "succeeded":
            return VerificationResult(
                valid=False, reason=f"intent status: {status}, expected succeeded"
            )
        amount = int(getattr(intent, "amount", 0) or 0)
        if amount < expected_amount_cents:
            return VerificationResult(
                valid=False,
                reason=f"insufficient amount: {amount} < {expected_amount_cents}",
            )
        currency = (getattr(intent, "currency", "") or "").lower()
        if currency != "usd":
            return VerificationResult(
                valid=False, reason=f"unexpected currency: {currency}"
            )
        if payout.stripe_connect_id:
            transfer_data = getattr(intent, "transfer_data", None)
            destination = (
                getattr(transfer_data, "destination", "") if transfer_data else ""
            )
            if destination and destination != payout.stripe_connect_id:
                return VerificationResult(
                    valid=False,
                    reason="payout destination mismatch",
                )
        if payout.platform_fee_cents > 0:
            actual_fee = int(getattr(intent, "application_fee_amount", 0) or 0)
            if actual_fee < payout.platform_fee_cents:
                return VerificationResult(
                    valid=False,
                    reason=(
                        f"insufficient platform fee: {actual_fee} < "
                        f"{payout.platform_fee_cents}"
                    ),
                )
        customer = getattr(intent, "customer", "") or ""
        return VerificationResult(
            valid=True,
            amount_cents=amount,
            payer_id=customer,
            settlement_tx=intent.id,
            scheme="stripe-pi",
            network="stripe",
            asset="usd-cents",
        )

    @staticmethod
    def _extract_pi_id(proof: str) -> str:
        """Accept either a bare PaymentIntent ID or a base64-wrapped x402
        payload that contains one — agents using off-the-shelf x402 SDKs
        will send the latter."""
        if not proof:
            return ""
        if proof.startswith("pi_"):
            return proof
        try:
            data = json.loads(base64.b64decode(proof.encode()).decode("utf-8"))
        except (binascii.Error, json.JSONDecodeError, UnicodeDecodeError, ValueError):
            return ""
        if not isinstance(data, dict):
            return ""
        payload = data.get("payload") or {}
        if isinstance(payload, dict):
            for key in ("payment_intent_id", "paymentIntentId", "payment_intent"):
                v = payload.get(key)
                if isinstance(v, str) and v.startswith("pi_"):
                    return v
        for key in ("payment_intent_id", "paymentIntentId", "payment_intent"):
            v = data.get(key)
            if isinstance(v, str) and v.startswith("pi_"):
                return v
        return ""


# ── Aigis-pay facilitator (stub for future) ───────────────────────


class AigisPayFacilitator:
    """Placeholder for the user's own aigis-pay product. Aigis-pay's current
    escrow + reputation model is a poor fit for per-query micropayments
    (10-second blockchain confirmation per call, no merchant API yet) — this
    stub exists so the route layer can route to it once aigis-pay grows a
    `verify` endpoint and a clear use case (likely "buy entire corpus
    license" rather than per-query).
    """

    name = "aigis_pay"
    schemes: tuple[str, ...] = ("aigis-escrow",)

    def accepts_for(self, corpus: dict, *, resource: str) -> list[dict]:
        return []  # not yet shippable — keep out of x402 challenges

    def verify(
        self,
        proof: str,
        *,
        corpus: dict,
        expected_amount_cents: int,
        resource: str,
    ) -> VerificationResult:
        return VerificationResult(
            valid=False,
            reason="aigis_pay facilitator is a stub — see noosphere/core/agent_payments.py",
        )


# ── Registry ──────────────────────────────────────────────────────


_FACILITATORS: dict[str, PaymentFacilitator] = {
    "mock": MockFacilitator(),
    "coinbase_x402": CoinbaseX402Facilitator(),
    "stripe_agent": StripeAgentToolkitFacilitator(),
    "aigis_pay": AigisPayFacilitator(),
}


def get_active_facilitators() -> list[PaymentFacilitator]:
    """Return facilitator instances for every configured name, in order.

    Skips unknown names with a warning rather than crashing — a typo in
    one entry shouldn't take down the whole payment surface. If the env
    list is empty after filtering, falls back to `[mock]`.
    """
    out: list[PaymentFacilitator] = []
    seen: set[str] = set()
    for raw in FACILITATOR_NAMES or ["mock"]:
        key = (raw or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        fac = _FACILITATORS.get(key)
        if fac is None:
            log.warning("unknown facilitator %r — skipping", key)
            continue
        out.append(fac)
    if not out:
        out.append(_FACILITATORS["mock"])
    return out


def get_facilitator(name: str | None = None) -> PaymentFacilitator:
    """Return a single facilitator. With no name: the first active one (so
    legacy single-facilitator callers keep working). With a name: that
    specific implementation, falling back to MockFacilitator if unknown."""
    if name is not None:
        key = name.strip().lower()
        return _FACILITATORS.get(key) or _FACILITATORS["mock"]
    actives = get_active_facilitators()
    return actives[0] if actives else _FACILITATORS["mock"]


def find_facilitator_for_proof(proof: str) -> PaymentFacilitator | None:
    """Pick the facilitator that handles the proof's scheme. Restricts the
    match to *active* facilitators so a stale registry entry can't be used
    to verify against a disabled rail."""
    scheme = _extract_scheme(proof)
    if not scheme:
        return None
    for fac in get_active_facilitators():
        if scheme in getattr(fac, "schemes", ()):
            return fac
    return None


def register_facilitator(facilitator: PaymentFacilitator) -> None:
    """Add or replace a facilitator. Used by tests + downstream extensions."""
    _FACILITATORS[facilitator.name] = facilitator


# ── x402 challenge construction ───────────────────────────────────


def build_x402_challenge(
    corpus: dict, *, resource: str, checkout_url: str = ""
) -> dict:
    """Assemble the JSON body returned with HTTP 402 for a paid corpus.

    The body follows the x402 v1 spec — the agent reads `accepts`, picks a
    rail it supports, satisfies the challenge, and retries with `X-PAYMENT:
    <base64 proof>`. Listing every active facilitator lets the agent choose
    crypto vs fiat without negotiating with us first. `checkout_url` keeps
    the human flow working for browser-based readers.
    """
    accepts: list[dict] = []
    for fac in get_active_facilitators():
        try:
            accepts.extend(fac.accepts_for(corpus, resource=resource))
        except Exception as e:
            log.warning("facilitator %s.accepts_for failed: %s", fac.name, e)
    body: dict = {
        "x402Version": 1,
        "accepts": accepts,
        "error": "payment_required",
    }
    if checkout_url:
        body["checkout_url"] = checkout_url
    return body


# ── Settlement recording ──────────────────────────────────────────


def record_settlement(
    corpus_id: str,
    *,
    facilitator: str,
    result: VerificationResult,
    agent_id: str = "",
    proof: str = "",
    access_token_id: str = "",
) -> str:
    """Insert a row into agent_settlements. Returns the settlement id."""
    settlement_id = str(uuid.uuid4())
    conn = get_conn()
    conn.execute(
        """INSERT INTO agent_settlements
           (id, corpus_id, facilitator, scheme, network, agent_id, payer_id,
            amount_cents, currency, asset, settlement_tx, proof_json,
            access_token_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            settlement_id,
            corpus_id,
            facilitator,
            result.scheme or "",
            result.network or "",
            agent_id or "",
            result.payer_id or "",
            int(result.amount_cents or 0),
            "usd",
            result.asset or "",
            result.settlement_tx or "",
            json.dumps({"proof_preview": proof[:64] if proof else ""}),
            access_token_id or "",
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    return settlement_id


def mint_access_token(
    corpus_id: str, *, label: Optional[str] = None, ttl_seconds: Optional[int] = None
) -> tuple[str, str]:
    """Mint a short-lived access_tokens row. Returns (token_id, raw_token).

    Reuses the existing access_tokens table. The label distinguishes
    facilitator-issued tokens from owner-issued ones — `check_access` for
    paid corpora only honors tokens carrying `AGENT_SETTLEMENT_LABEL`, so
    a regular access_token can't be used to bypass paid gating.
    """
    from noosphere.core.access import AGENT_SETTLEMENT_LABEL

    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    token_id = str(uuid.uuid4())
    expires = datetime.now(timezone.utc) + timedelta(
        seconds=ttl_seconds if ttl_seconds is not None else ACCESS_TOKEN_TTL_SECONDS
    )
    conn = get_conn()
    conn.execute(
        """INSERT INTO access_tokens
           (id, corpus_id, token_hash, label, permissions, expires_at, created_at)
           VALUES (?, ?, ?, ?, 'read', ?, ?)""",
        (
            token_id,
            corpus_id,
            token_hash,
            label or AGENT_SETTLEMENT_LABEL,
            expires.isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    return token_id, raw
