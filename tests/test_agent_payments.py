"""Tests for the x402 agent-payment loop.

Covers:
  - x402-compliant 402 response body shape
  - Facilitator proof verification (valid + invalid paths) via MockFacilitator
  - End-to-end auto-pay: agent retries with X-PAYMENT and gets 200 + result
  - /settle endpoint mints an access_token usable as Bearer
  - MCP `purchase` tool: challenge fetch + proof submission
  - Aigis-pay seam: stub facilitator can be swapped via env without code change
  - Human Stripe Checkout fallback unaffected
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest

from noosphere.core import agent_payments
from noosphere.core.access import verify_facilitator_proof
from noosphere.core.agent_payments import (
    AigisPayFacilitator,
    MockFacilitator,
    VerificationResult,
    build_x402_challenge,
    get_facilitator,
)


_CORPUS_JSON = {
    "name": "Paid Corpus",
    "description": "Premium",
    "author_name": "Creator",
    "tags": ["premium"],
    "language": "en",
}

_PRICING_PER_QUERY = {
    "type": "per_query",
    "amount_cents": 500,
    "currency": "usd",
    "queries_per_payment": 10,
}


@pytest.fixture
def paid_corpus(client):
    r = client.post("/api/v1/corpora", json=_CORPUS_JSON)
    assert r.status_code == 200
    cid = r.json()["id"]
    r = client.post(f"/api/v1/corpora/{cid}/pricing", json=_PRICING_PER_QUERY)
    assert r.status_code == 200
    r = client.get(f"/api/v1/corpora/{cid}")
    return r.json()


# ── 1. Unit: facilitator verification ───────────────────────────────


def test_mock_facilitator_rejects_empty_proof():
    fac = MockFacilitator()
    result = fac.verify(
        "", corpus={"id": "c1", "name": "x"}, expected_amount_cents=500, resource="/r"
    )
    assert not result.valid
    assert "mock:" in result.reason


def test_mock_facilitator_rejects_malformed_proof():
    fac = MockFacilitator()
    result = fac.verify(
        "mock:notanumber:payer", corpus={"id": "c1", "name": "x"},
        expected_amount_cents=500, resource="/r",
    )
    assert not result.valid


def test_mock_facilitator_rejects_underpayment():
    fac = MockFacilitator()
    result = fac.verify(
        "mock:100:payer-abc",
        corpus={"id": "c1", "name": "x"},
        expected_amount_cents=500,
        resource="/r",
    )
    assert not result.valid
    assert "insufficient" in result.reason


def test_mock_facilitator_accepts_valid_proof():
    fac = MockFacilitator()
    result = fac.verify(
        "mock:500:payer-abc",
        corpus={"id": "c1", "name": "x"},
        expected_amount_cents=500,
        resource="/r",
    )
    assert result.valid
    assert result.payer_id == "payer-abc"
    assert result.amount_cents == 500
    assert result.scheme == "mock"
    assert result.settlement_tx.startswith("mock-tx-")


def test_verify_facilitator_proof_writes_audit_row(paid_corpus, client):
    """A valid proof writes an `agent_settlements` row."""
    from noosphere.core.db import get_conn

    result, settlement_id = verify_facilitator_proof(
        paid_corpus,
        "mock:500:agent-007",
        resource="/api/v1/corpora/X/search",
        agent_id="agent-007",
    )
    assert result.valid
    assert settlement_id

    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM agent_settlements WHERE id=?", (settlement_id,)
    ).fetchone()
    assert row is not None
    assert row["corpus_id"] == paid_corpus["id"]
    assert row["agent_id"] == "agent-007"
    assert row["facilitator"] == "mock"
    assert row["amount_cents"] == 500


def test_verify_facilitator_proof_rejects_when_corpus_lacks_per_query_pricing(client):
    """Subscription-priced corpora can't be paid via x402 micropayments."""
    r = client.post("/api/v1/corpora", json=_CORPUS_JSON)
    cid = r.json()["id"]
    # Mark as paid with no per_query pricing — leave pricing_json blank/subscription
    from noosphere.core.db import get_conn

    conn = get_conn()
    conn.execute(
        "UPDATE corpora SET access_level='paid', pricing_json=? WHERE id=?",
        (json.dumps({"type": "subscription", "stripe_price_id": "price_abc"}), cid),
    )
    conn.commit()
    corpus = client.get(f"/api/v1/corpora/{cid}").json()

    result, settlement_id = verify_facilitator_proof(
        corpus, "mock:500:p", resource="/r", agent_id="a",
    )
    assert not result.valid
    assert "per-query" in result.reason
    assert settlement_id == ""


# ── 2. x402 challenge body ──────────────────────────────────────────


def test_build_x402_challenge_shape(paid_corpus):
    challenge = build_x402_challenge(
        paid_corpus, resource="/api/v1/corpora/X/search"
    )
    assert challenge["x402Version"] == 1
    assert challenge["error"] == "payment_required"
    assert isinstance(challenge["accepts"], list)
    assert len(challenge["accepts"]) == 1
    a = challenge["accepts"][0]
    assert a["scheme"] == "mock"
    assert a["resource"] == "/api/v1/corpora/X/search"
    assert int(a["maxAmountRequired"]) == 500


def test_build_x402_challenge_optional_checkout_url(paid_corpus):
    c = build_x402_challenge(
        paid_corpus,
        resource="/r",
        checkout_url="https://checkout.stripe.com/abc",
    )
    assert c["checkout_url"] == "https://checkout.stripe.com/abc"


# ── 3. Integration: end-to-end x402 auto-pay via REST ────────────────


def test_paid_corpus_x_payment_header_grants_access(client, paid_corpus):
    """Agent retries with `X-PAYMENT` and the call succeeds inline."""
    r = client.post(
        f"/api/v1/corpora/{paid_corpus['id']}/search",
        json={"query": "test"},
        headers={
            "x-agent-id": "agent-007",
            "x-payment": "mock:500:agent-007",
        },
    )
    # Settles inline; not a payment-denied response.
    assert r.status_code != 402

    # Settlement audit row written
    from noosphere.core.db import get_conn

    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM agent_settlements WHERE corpus_id=?",
        (paid_corpus["id"],),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["agent_id"] == "agent-007"
    assert rows[0]["facilitator"] == "mock"


def test_paid_corpus_x_payment_underpayment_returns_x402_challenge(client, paid_corpus):
    """Insufficient proof falls through to 402 with x402 challenge body."""
    r = client.post(
        f"/api/v1/corpora/{paid_corpus['id']}/search",
        json={"query": "test"},
        headers={"x-agent-id": "agent-007", "x-payment": "mock:100:agent-007"},
    )
    assert r.status_code == 402
    body = r.json()
    assert body["x402Version"] == 1
    assert body["accepts"][0]["scheme"] == "mock"


# ── 4. /settle endpoint ─────────────────────────────────────────────


def test_settle_endpoint_mints_access_token(client, paid_corpus):
    r = client.post(
        f"/api/v1/corpora/{paid_corpus['id']}/settle",
        json={"payment_proof": "mock:500:agent-x"},
        headers={"x-agent-id": "agent-x"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["settlement_id"]
    assert body["amount_cents"] == 500
    assert body["scheme"] == "mock"
    assert body["access_token"]
    token = body["access_token"]

    # Token usable as Bearer for subsequent calls
    r2 = client.post(
        f"/api/v1/corpora/{paid_corpus['id']}/search",
        json={"query": "anything"},
        headers={"authorization": f"Bearer {token}", "x-agent-id": "agent-x"},
    )
    assert r2.status_code != 402


def test_settle_endpoint_rejects_bad_proof(client, paid_corpus):
    r = client.post(
        f"/api/v1/corpora/{paid_corpus['id']}/settle",
        json={"payment_proof": "mock:1:agent-x"},
        headers={"x-agent-id": "agent-x"},
    )
    assert r.status_code == 402


def test_settle_endpoint_rejects_non_paid(client):
    r = client.post("/api/v1/corpora", json=_CORPUS_JSON)
    cid = r.json()["id"]
    r = client.post(
        f"/api/v1/corpora/{cid}/settle",
        json={"payment_proof": "mock:500:p"},
    )
    assert r.status_code == 400


def test_settle_endpoint_requires_proof(client, paid_corpus):
    r = client.post(
        f"/api/v1/corpora/{paid_corpus['id']}/settle",
        json={},
    )
    assert r.status_code == 400


# ── 5. MCP purchase tool ────────────────────────────────────────────


def test_mcp_purchase_returns_challenge_when_no_proof(client, paid_corpus):
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "purchase",
            "arguments": {"corpus_id": paid_corpus["id"]},
        },
    }
    r = client.post("/mcp", json=body, headers={"x-agent-id": "agent-mcp"})
    assert r.status_code == 200
    text = r.json()["result"]["content"][0]["text"]
    payload = json.loads(text)
    assert "x402" in payload
    assert payload["x402"]["accepts"][0]["scheme"] == "mock"


def test_mcp_purchase_with_proof_returns_access_token(client, paid_corpus):
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "purchase",
            "arguments": {
                "corpus_id": paid_corpus["id"],
                "payment_proof": "mock:500:agent-mcp",
            },
        },
    }
    r = client.post("/mcp", json=body, headers={"x-agent-id": "agent-mcp"})
    assert r.status_code == 200
    payload = json.loads(r.json()["result"]["content"][0]["text"])
    assert payload["access_token"]
    assert payload["amount_settled_cents"] == 500
    assert payload["scheme"] == "mock"


def test_mcp_search_with_x_payment_header(client, paid_corpus):
    """MCP tool calls accept the X-PAYMENT header inline like REST."""
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "search",
            "arguments": {
                "corpus_id": paid_corpus["id"],
                "query": "anything",
            },
        },
    }
    r = client.post(
        "/mcp",
        json=body,
        headers={
            "x-agent-id": "agent-mcp",
            "x-payment": "mock:500:agent-mcp",
        },
    )
    assert r.status_code == 200
    rpc = r.json()
    # Either we got a valid result or an error, but it's NOT an access denial.
    if "error" in rpc:
        assert "payment" not in rpc["error"]["message"].lower()


def test_mcp_purchase_on_non_paid_corpus(client):
    r = client.post("/api/v1/corpora", json=_CORPUS_JSON)
    cid = r.json()["id"]
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "purchase",
            "arguments": {"corpus_id": cid},
        },
    }
    r = client.post("/mcp", json=body)
    payload = json.loads(r.json()["result"]["content"][0]["text"])
    assert "error" in payload


# ── 6. Aigis-pay seam (stub facilitator swap-in) ───────────────────


def test_aigispay_facilitator_returns_no_accepts():
    """Aigis-pay is a stub for the user's own product — emits no `accepts`
    so it doesn't accidentally appear in x402 challenges before its
    `/verify` endpoint exists."""
    fac = AigisPayFacilitator()
    accepts = fac.accepts_for(
        {"id": "c", "name": "x", "pricing_json": json.dumps(_PRICING_PER_QUERY)},
        resource="/r",
    )
    assert accepts == []


def test_aigispay_facilitator_rejects_verification():
    fac = AigisPayFacilitator()
    result = fac.verify(
        "any-proof",
        corpus={"id": "c", "name": "x"},
        expected_amount_cents=500,
        resource="/r",
    )
    assert not result.valid
    assert "stub" in result.reason.lower()


def test_facilitator_swap_via_register(monkeypatch, paid_corpus):
    """Custom facilitators can be plugged in via `register_facilitator()`
    without touching schema or HTTP layer — this is the seam aigis-pay
    will use once it grows a merchant API."""

    class StubFacilitator:
        name = "stub_test"
        schemes = ("stub_test",)

        def accepts_for(self, corpus, *, resource):
            return [
                {
                    "scheme": "stub_test",
                    "network": "stub-net",
                    "maxAmountRequired": "500",
                    "asset": "STUB",
                    "resource": resource,
                    "payTo": "stub://address",
                    "description": "stub",
                }
            ]

        def verify(self, proof, *, corpus, expected_amount_cents, resource):
            return VerificationResult(
                valid=proof == "stub-good", amount_cents=500, payer_id="p",
                scheme="stub_test", reason="" if proof == "stub-good" else "bad",
            )

    agent_payments.register_facilitator(StubFacilitator())
    monkeypatch.setattr(agent_payments, "FACILITATOR_NAMES", ["stub_test"])
    fac = get_facilitator()
    assert fac.name == "stub_test"

    challenge = build_x402_challenge(paid_corpus, resource="/r")
    assert challenge["accepts"][0]["scheme"] == "stub_test"

    # Pass facilitator_name explicitly so the scheme-routing layer doesn't
    # need to recognize "stub-good" — the override pins the verifier.
    result, sid = verify_facilitator_proof(
        paid_corpus, "stub-good", resource="/r", agent_id="a",
        facilitator_name="stub_test",
    )
    assert result.valid
    assert sid


# ── 7. Multi-facilitator support ───────────────────────────────────


def test_multi_facilitator_challenge_lists_all_active_rails(monkeypatch, paid_corpus):
    """With both Coinbase and Stripe Agent enabled, the x402 challenge
    advertises both — agents pick whichever rail their SDK speaks."""
    monkeypatch.setattr(agent_payments, "FACILITATOR_NAMES", ["coinbase_x402", "stripe_agent"])
    monkeypatch.setattr(agent_payments, "COINBASE_X402_PAYOUT_ADDRESS", "0xabc123")
    monkeypatch.setattr(agent_payments, "STRIPE_SECRET_KEY", "sk_test_xxx")
    monkeypatch.setattr(agent_payments, "STRIPE_AGENT_PAY_TO", "acct_test_456")

    challenge = build_x402_challenge(paid_corpus, resource="/api/v1/x")
    schemes = [a["scheme"] for a in challenge["accepts"]]
    assert schemes == ["exact", "stripe-pi"]
    crypto = next(a for a in challenge["accepts"] if a["scheme"] == "exact")
    fiat = next(a for a in challenge["accepts"] if a["scheme"] == "stripe-pi")
    assert crypto["payTo"] == "0xabc123"
    assert fiat["payTo"] == "acct_test_456"
    assert int(crypto["maxAmountRequired"]) == 500
    assert int(fiat["maxAmountRequired"]) == 500


def test_multi_facilitator_routes_proof_by_scheme(monkeypatch, paid_corpus):
    """A `mock:` proof goes to the mock facilitator even when other
    facilitators are also active — scheme-based routing prevents
    cross-rail collisions."""
    monkeypatch.setattr(agent_payments, "FACILITATOR_NAMES", ["mock", "coinbase_x402"])
    monkeypatch.setattr(agent_payments, "COINBASE_X402_PAYOUT_ADDRESS", "0xabc123")

    fac = agent_payments.find_facilitator_for_proof("mock:500:agent-x")
    assert fac is not None
    assert fac.name == "mock"

    # Stripe-PI proof routes to nothing because stripe_agent isn't active here.
    fac2 = agent_payments.find_facilitator_for_proof("pi_3OZxxxxx")
    assert fac2 is None


def test_facilitator_routing_picks_stripe_for_pi_prefix(monkeypatch, paid_corpus):
    monkeypatch.setattr(agent_payments, "FACILITATOR_NAMES", ["mock", "stripe_agent"])
    monkeypatch.setattr(agent_payments, "STRIPE_SECRET_KEY", "sk_test_xxx")
    monkeypatch.setattr(agent_payments, "STRIPE_AGENT_PAY_TO", "acct_test_456")

    fac = agent_payments.find_facilitator_for_proof("pi_3ABCxyz")
    assert fac is not None
    assert fac.name == "stripe_agent"


def test_singular_env_var_backwards_compat(monkeypatch):
    """The old NOOSPHERE_PAYMENT_FACILITATOR (singular) still works for
    deployments that haven't migrated to the plural form."""
    monkeypatch.delenv("NOOSPHERE_PAYMENT_FACILITATORS", raising=False)
    monkeypatch.setenv("NOOSPHERE_PAYMENT_FACILITATOR", "coinbase_x402")
    names = agent_payments._parse_facilitator_names()
    assert names == ["coinbase_x402"]


def test_plural_env_var_overrides_singular(monkeypatch):
    monkeypatch.setenv("NOOSPHERE_PAYMENT_FACILITATORS", "coinbase_x402,stripe_agent")
    monkeypatch.setenv("NOOSPHERE_PAYMENT_FACILITATOR", "mock")
    names = agent_payments._parse_facilitator_names()
    assert names == ["coinbase_x402", "stripe_agent"]


def test_unknown_facilitator_skipped_with_warning(monkeypatch, paid_corpus):
    """A typo in the env shouldn't take down the whole payment surface —
    unknown names are skipped, valid ones still work."""
    monkeypatch.setattr(agent_payments, "FACILITATOR_NAMES", ["mock", "garbage_value"])
    actives = agent_payments.get_active_facilitators()
    assert [f.name for f in actives] == ["mock"]


def test_empty_facilitator_list_falls_back_to_mock(monkeypatch):
    monkeypatch.setattr(agent_payments, "FACILITATOR_NAMES", [])
    actives = agent_payments.get_active_facilitators()
    assert [f.name for f in actives] == ["mock"]


# ── 8. Stripe Agent Toolkit facilitator ─────────────────────────────


def test_stripe_agent_facilitator_returns_no_accepts_without_config(monkeypatch, paid_corpus):
    monkeypatch.setattr(agent_payments, "STRIPE_SECRET_KEY", "")
    monkeypatch.setattr(agent_payments, "STRIPE_AGENT_PAY_TO", "")
    fac = agent_payments.StripeAgentToolkitFacilitator()
    assert fac.accepts_for(paid_corpus, resource="/r") == []


def test_stripe_agent_facilitator_advertises_when_configured(monkeypatch, paid_corpus):
    monkeypatch.setattr(agent_payments, "STRIPE_SECRET_KEY", "sk_test_xxx")
    monkeypatch.setattr(agent_payments, "STRIPE_AGENT_PAY_TO", "acct_test_456")
    fac = agent_payments.StripeAgentToolkitFacilitator()
    accepts = fac.accepts_for(paid_corpus, resource="/api/v1/x")
    assert len(accepts) == 1
    assert accepts[0]["scheme"] == "stripe-pi"
    assert accepts[0]["network"] == "stripe"
    assert accepts[0]["payTo"] == "acct_test_456"
    assert accepts[0]["asset"] == "usd-cents"


def test_stripe_agent_extract_pi_id_bare():
    fac = agent_payments.StripeAgentToolkitFacilitator()
    assert fac._extract_pi_id("pi_3ABCxyz") == "pi_3ABCxyz"


def test_stripe_agent_extract_pi_id_from_x402_envelope():
    """x402 SDKs wrap the proof in a base64 JSON. Make sure we can still
    fish the PaymentIntent ID out."""
    import base64 as b64

    fac = agent_payments.StripeAgentToolkitFacilitator()
    payload = {
        "x402Version": 1,
        "scheme": "stripe-pi",
        "network": "stripe",
        "payload": {"payment_intent_id": "pi_3SomeIntent"},
    }
    proof = b64.b64encode(json.dumps(payload).encode()).decode()
    assert fac._extract_pi_id(proof) == "pi_3SomeIntent"


def test_stripe_agent_verify_rejects_when_no_secret_key(monkeypatch, paid_corpus):
    monkeypatch.setattr(agent_payments, "STRIPE_SECRET_KEY", "")
    fac = agent_payments.StripeAgentToolkitFacilitator()
    result = fac.verify(
        "pi_3ABCxyz", corpus=paid_corpus, expected_amount_cents=500, resource="/r"
    )
    assert not result.valid
    assert "STRIPE_SECRET_KEY" in result.reason


def test_stripe_agent_verify_succeeds_with_valid_intent(monkeypatch, paid_corpus):
    """Mock the Stripe SDK to return a succeeded PaymentIntent and verify
    the facilitator validates amount, currency, and destination."""
    from unittest.mock import MagicMock, patch

    monkeypatch.setattr(agent_payments, "STRIPE_SECRET_KEY", "sk_test_xxx")
    monkeypatch.setattr(agent_payments, "STRIPE_AGENT_PAY_TO", "acct_test_456")

    fake_intent = MagicMock()
    fake_intent.id = "pi_3OK"
    fake_intent.status = "succeeded"
    fake_intent.amount = 500
    fake_intent.currency = "usd"
    fake_intent.customer = "cus_buyer"
    fake_intent.transfer_data = MagicMock()
    fake_intent.transfer_data.destination = "acct_test_456"

    with patch("stripe.PaymentIntent.retrieve", return_value=fake_intent):
        fac = agent_payments.StripeAgentToolkitFacilitator()
        result = fac.verify(
            "pi_3OK", corpus=paid_corpus, expected_amount_cents=500, resource="/r"
        )

    assert result.valid
    assert result.amount_cents == 500
    assert result.payer_id == "cus_buyer"
    assert result.scheme == "stripe-pi"
    assert result.settlement_tx == "pi_3OK"


def test_stripe_agent_verify_rejects_unsucceeded_intent(monkeypatch, paid_corpus):
    from unittest.mock import MagicMock, patch

    monkeypatch.setattr(agent_payments, "STRIPE_SECRET_KEY", "sk_test_xxx")
    fake_intent = MagicMock()
    fake_intent.status = "requires_action"
    fake_intent.amount = 500
    fake_intent.currency = "usd"
    with patch("stripe.PaymentIntent.retrieve", return_value=fake_intent):
        fac = agent_payments.StripeAgentToolkitFacilitator()
        result = fac.verify(
            "pi_3PEND", corpus=paid_corpus, expected_amount_cents=500, resource="/r"
        )
    assert not result.valid
    assert "requires_action" in result.reason


def test_stripe_agent_verify_rejects_underpayment(monkeypatch, paid_corpus):
    from unittest.mock import MagicMock, patch

    monkeypatch.setattr(agent_payments, "STRIPE_SECRET_KEY", "sk_test_xxx")
    fake_intent = MagicMock()
    fake_intent.status = "succeeded"
    fake_intent.amount = 100  # less than expected 500
    fake_intent.currency = "usd"
    fake_intent.customer = ""
    fake_intent.transfer_data = None
    with patch("stripe.PaymentIntent.retrieve", return_value=fake_intent):
        fac = agent_payments.StripeAgentToolkitFacilitator()
        result = fac.verify(
            "pi_3CHEAP", corpus=paid_corpus, expected_amount_cents=500, resource="/r"
        )
    assert not result.valid
    assert "insufficient" in result.reason


def test_stripe_agent_verify_rejects_wrong_destination(monkeypatch, paid_corpus):
    """A PaymentIntent that landed in the wrong Connect account is rejected
    even if amount and status look fine — protects against agent paying
    the wrong merchant and replaying the proof."""
    from unittest.mock import MagicMock, patch

    monkeypatch.setattr(agent_payments, "STRIPE_SECRET_KEY", "sk_test_xxx")
    monkeypatch.setattr(agent_payments, "STRIPE_AGENT_PAY_TO", "acct_test_456")
    fake_intent = MagicMock()
    fake_intent.status = "succeeded"
    fake_intent.amount = 500
    fake_intent.currency = "usd"
    fake_intent.customer = "cus_x"
    fake_intent.transfer_data = MagicMock()
    fake_intent.transfer_data.destination = "acct_OTHER_999"
    with patch("stripe.PaymentIntent.retrieve", return_value=fake_intent):
        fac = agent_payments.StripeAgentToolkitFacilitator()
        result = fac.verify(
            "pi_3WRONG", corpus=paid_corpus, expected_amount_cents=500, resource="/r"
        )
    assert not result.valid
    assert "destination" in result.reason


def test_stripe_proof_via_settle_endpoint_e2e(monkeypatch, client, paid_corpus):
    """End-to-end: agent settles via /settle using a Stripe PaymentIntent
    proof, gets back an access token, then uses it for a search."""
    from unittest.mock import MagicMock, patch

    monkeypatch.setattr(agent_payments, "FACILITATOR_NAMES", ["stripe_agent"])
    monkeypatch.setattr(agent_payments, "STRIPE_SECRET_KEY", "sk_test_xxx")
    monkeypatch.setattr(agent_payments, "STRIPE_AGENT_PAY_TO", "acct_test_456")

    fake_intent = MagicMock()
    fake_intent.id = "pi_3GOOD"
    fake_intent.status = "succeeded"
    fake_intent.amount = 500
    fake_intent.currency = "usd"
    fake_intent.customer = "cus_buyer"
    fake_intent.transfer_data = MagicMock()
    fake_intent.transfer_data.destination = "acct_test_456"

    with patch("stripe.PaymentIntent.retrieve", return_value=fake_intent):
        r = client.post(
            f"/api/v1/corpora/{paid_corpus['id']}/settle",
            json={"payment_proof": "pi_3GOOD"},
            headers={"x-agent-id": "agent-fiat"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["scheme"] == "stripe-pi"
    assert body["amount_cents"] == 500
    assert body["access_token"]


# ── 9. Cloud multi-tenant routing ──────────────────────────────────


def _seed_cloud_user(
    user_id: str,
    *,
    stripe_connect: str = "",
    crypto_address: str = "",
) -> None:
    """Initialize cloud tables and insert a creator with payout records."""
    from datetime import datetime, timezone

    from noosphere.cloud.db import init_cloud_tables
    from noosphere.core.db import get_conn

    init_cloud_tables()
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    conn.execute(
        "INSERT INTO users (id, email, tier, stripe_connect_account_id, "
        "crypto_payout_address, created_at, updated_at) "
        "VALUES (?, ?, 'pro', ?, ?, ?, ?)",
        (user_id, f"{user_id}@example.com", stripe_connect, crypto_address, now, now),
    )
    conn.commit()


def _set_corpus_owner(corpus_id: str, owner_id: str) -> dict:
    from noosphere.core.db import get_conn

    conn = get_conn()
    conn.execute(
        "UPDATE corpora SET owner_id=? WHERE id=?", (owner_id, corpus_id)
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM corpora WHERE id=?", (corpus_id,)
    ).fetchone()
    return dict(row)


def test_self_hosted_payout_uses_global_env(monkeypatch, paid_corpus):
    monkeypatch.setattr(agent_payments, "ENABLE_CLOUD", False)
    monkeypatch.setattr(agent_payments, "COINBASE_X402_PAYOUT_ADDRESS", "0xglobal")
    monkeypatch.setattr(agent_payments, "STRIPE_AGENT_PAY_TO", "acct_global")
    payout = agent_payments._resolve_payout(paid_corpus)
    assert payout.crypto_address == "0xglobal"
    assert payout.stripe_connect_id == "acct_global"
    assert payout.platform_fee_cents == 0


def test_cloud_payout_resolves_from_creator(monkeypatch, paid_corpus):
    monkeypatch.setattr(agent_payments, "ENABLE_CLOUD", True)
    _seed_cloud_user(
        "creator-routed",
        stripe_connect="acct_creator_routed",
        crypto_address="0xcreator_routed",
    )
    fresh = _set_corpus_owner(paid_corpus["id"], "creator-routed")

    payout = agent_payments._resolve_payout(fresh)
    assert payout.stripe_connect_id == "acct_creator_routed"
    assert payout.crypto_address == "0xcreator_routed"
    # 10% of the corpus's $5.00 per-query price
    assert payout.platform_fee_cents == 50


def test_cloud_unconfigured_creator_disables_fiat_rail(monkeypatch, paid_corpus):
    """A creator who hasn't run /connect/onboard has no Connect ID, so
    the fiat rail returns no accepts — no risk of routing fiat to the
    wrong account."""
    monkeypatch.setattr(agent_payments, "ENABLE_CLOUD", True)
    monkeypatch.setattr(agent_payments, "STRIPE_SECRET_KEY", "sk_test_xxx")
    _seed_cloud_user("creator-bare")
    fresh = _set_corpus_owner(paid_corpus["id"], "creator-bare")

    fac = agent_payments.StripeAgentToolkitFacilitator()
    assert fac.accepts_for(fresh, resource="/r") == []


def test_cloud_unconfigured_creator_falls_back_to_global_crypto(monkeypatch, paid_corpus):
    """When a cloud creator hasn't set a wallet, we fall back to the
    platform's global address rather than block crypto payments entirely.
    Platform operators who want strict per-creator routing leave the
    global env empty."""
    monkeypatch.setattr(agent_payments, "ENABLE_CLOUD", True)
    monkeypatch.setattr(agent_payments, "COINBASE_X402_PAYOUT_ADDRESS", "0xplatform")
    _seed_cloud_user("creator-bare-2")
    fresh = _set_corpus_owner(paid_corpus["id"], "creator-bare-2")

    payout = agent_payments._resolve_payout(fresh)
    assert payout.crypto_address == "0xplatform"


def test_cloud_stripe_accepts_includes_application_fee(monkeypatch, paid_corpus):
    """The 10% platform fee is communicated to the agent via the
    `application_fee_amount` field in `extra` so its Stripe Agent Toolkit
    can include it on the PaymentIntent."""
    monkeypatch.setattr(agent_payments, "ENABLE_CLOUD", True)
    monkeypatch.setattr(agent_payments, "STRIPE_SECRET_KEY", "sk_test_xxx")
    _seed_cloud_user("creator-fee", stripe_connect="acct_creator_fee")
    fresh = _set_corpus_owner(paid_corpus["id"], "creator-fee")

    fac = agent_payments.StripeAgentToolkitFacilitator()
    accepts = fac.accepts_for(fresh, resource="/r")
    assert len(accepts) == 1
    assert accepts[0]["payTo"] == "acct_creator_fee"
    assert accepts[0]["extra"]["application_fee_amount"] == "50"


def test_cloud_stripe_verify_rejects_underpaid_platform_fee(monkeypatch, paid_corpus):
    """A PaymentIntent that didn't carry the full platform fee is rejected
    — keeps the cloud cut enforceable even if the agent's SDK 'forgets'."""
    from unittest.mock import MagicMock, patch

    monkeypatch.setattr(agent_payments, "ENABLE_CLOUD", True)
    monkeypatch.setattr(agent_payments, "STRIPE_SECRET_KEY", "sk_test_xxx")
    _seed_cloud_user("creator-underfee", stripe_connect="acct_creator_underfee")
    fresh = _set_corpus_owner(paid_corpus["id"], "creator-underfee")

    fake_intent = MagicMock()
    fake_intent.id = "pi_3STINGY"
    fake_intent.status = "succeeded"
    fake_intent.amount = 500
    fake_intent.currency = "usd"
    fake_intent.customer = "cus_x"
    fake_intent.transfer_data = MagicMock()
    fake_intent.transfer_data.destination = "acct_creator_underfee"
    fake_intent.application_fee_amount = 10  # less than the required 50

    with patch("stripe.PaymentIntent.retrieve", return_value=fake_intent):
        fac = agent_payments.StripeAgentToolkitFacilitator()
        result = fac.verify(
            "pi_3STINGY", corpus=fresh, expected_amount_cents=500, resource="/r"
        )
    assert not result.valid
    assert "platform fee" in result.reason


def test_cloud_stripe_verify_accepts_full_platform_fee(monkeypatch, paid_corpus):
    from unittest.mock import MagicMock, patch

    monkeypatch.setattr(agent_payments, "ENABLE_CLOUD", True)
    monkeypatch.setattr(agent_payments, "STRIPE_SECRET_KEY", "sk_test_xxx")
    _seed_cloud_user("creator-honest", stripe_connect="acct_creator_honest")
    fresh = _set_corpus_owner(paid_corpus["id"], "creator-honest")

    fake_intent = MagicMock()
    fake_intent.id = "pi_3HONEST"
    fake_intent.status = "succeeded"
    fake_intent.amount = 500
    fake_intent.currency = "usd"
    fake_intent.customer = "cus_x"
    fake_intent.transfer_data = MagicMock()
    fake_intent.transfer_data.destination = "acct_creator_honest"
    fake_intent.application_fee_amount = 50

    with patch("stripe.PaymentIntent.retrieve", return_value=fake_intent):
        fac = agent_payments.StripeAgentToolkitFacilitator()
        result = fac.verify(
            "pi_3HONEST", corpus=fresh, expected_amount_cents=500, resource="/r"
        )
    assert result.valid


# ── 10. Human Stripe Checkout fallback ─────────────────────────────


def test_stripe_checkout_endpoint_still_works(client, paid_corpus):
    """The human-paid flow is independent of the agent flow. A POST to
    /checkout still creates a Stripe session as before — agents and humans
    can coexist."""
    from unittest.mock import patch, MagicMock

    mock_session = MagicMock()
    mock_session.id = "cs_human_test"
    mock_session.url = "https://checkout.stripe.com/abc"
    with patch("noosphere.core.payments.stripe") as mock_stripe, \
         patch("noosphere.core.payments.STRIPE_SECRET_KEY", "sk_test_xxx"):
        mock_stripe.checkout.Session.create.return_value = mock_session
        r = client.post(
            f"/api/v1/corpora/{paid_corpus['id']}/checkout",
            json={"payer_email": "human@example.com"},
        )
    assert r.status_code == 200
    assert r.json()["checkout_url"] == "https://checkout.stripe.com/abc"
