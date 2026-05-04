"""Access control — enforce corpus access levels.

Checks whether a request is authorized to access a given corpus
based on its access_level setting (public, private, token, paid).
"""

import hashlib
from datetime import datetime, timezone
from typing import Optional

from noosphere.core.db import get_conn

# Label applied to access_tokens minted by a successful x402 facilitator
# settlement. Paid-corpus access lookup matches on this label so that
# arbitrary owner-issued tokens (intended for `token`-level corpora) don't
# accidentally grant paid access.
AGENT_SETTLEMENT_LABEL = "agent-settlement"


class AccessDenied(Exception):
    """Raised when access to a corpus is denied."""

    def __init__(self, message: str = "Access denied", status_code: int = 403):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class PaymentRequired(AccessDenied):
    """Subclass of AccessDenied that carries an x402 challenge body.

    Caught by the FastAPI exception handler in api/main.py and converted
    to a JSONResponse with the full x402 spec body — agents auto-handle
    these via their payment client SDKs.
    """

    def __init__(self, corpus: dict, *, resource: str, checkout_url: str = ""):
        from noosphere.core.agent_payments import build_x402_challenge

        super().__init__(
            message="Payment required for this corpus.",
            status_code=402,
        )
        self.corpus_id = corpus["id"]
        self.body = build_x402_challenge(
            corpus, resource=resource, checkout_url=checkout_url
        )


def verify_facilitator_proof(
    corpus: dict,
    proof: str,
    *,
    resource: str,
    agent_id: str = "",
    facilitator_name: Optional[str] = None,
):
    """Verify an X-PAYMENT proof against the right facilitator.

    Returns ``(VerificationResult, settlement_id)`` on success or
    ``(VerificationResult, "")`` on failure. Caller decides whether to
    grant access based on `result.valid`.

    With multiple facilitators active, the right one is picked by parsing
    the proof's `scheme` (Coinbase x402 sends `"exact"`, Stripe Agent
    Toolkit sends `"stripe-pi"`, mock sends `"mock"`). `facilitator_name`
    overrides this routing — used by tests that want to pin the verifier.

    Records an `agent_settlements` audit row when valid — same row whether
    the call came via the inline X-PAYMENT path or the explicit /settle
    endpoint. Mints no access_token; the caller does that if it wants one.
    """
    from noosphere.core.agent_payments import (
        VerificationResult,
        _per_query_amount_cents,
        find_facilitator_for_proof,
        get_facilitator,
        record_settlement,
    )

    expected = _per_query_amount_cents(corpus)
    if expected <= 0:
        # No per-query pricing → reject. Subscription-priced corpora must use
        # Stripe Checkout, not x402 micropayments.
        return (
            VerificationResult(
                valid=False, reason="corpus has no per-query pricing"
            ),
            "",
        )
    if facilitator_name is not None:
        facilitator = get_facilitator(facilitator_name)
    else:
        facilitator = find_facilitator_for_proof(proof)
    if facilitator is None:
        return (
            VerificationResult(
                valid=False,
                reason="no active facilitator handles this proof's scheme",
            ),
            "",
        )
    result = facilitator.verify(
        proof, corpus=corpus, expected_amount_cents=expected, resource=resource
    )
    if not result.valid:
        return (result, "")
    settlement_id = record_settlement(
        corpus["id"],
        facilitator=facilitator.name,
        result=result,
        agent_id=agent_id,
        proof=proof,
    )
    return (result, settlement_id)


def check_access(corpus: dict, bearer_token: str | None = None) -> str | None:
    """Verify access to a corpus. Returns the validated token_id or None.

    Raises AccessDenied if the request is not authorized.
    """
    level = corpus.get("access_level", "public")

    if level == "public":
        return None

    if level == "private":
        raise AccessDenied("This corpus is private")

    if level == "token":
        if not bearer_token:
            raise AccessDenied("This corpus requires an access token", status_code=401)
        token_id = _validate_token(corpus["id"], bearer_token)
        if not token_id:
            raise AccessDenied("Invalid or expired access token", status_code=401)
        return token_id

    if level == "paid":
        if not bearer_token:
            raise AccessDenied(
                "This corpus requires payment. Use POST /api/v1/corpora/{id}/checkout to purchase access.",
                status_code=402,
            )
        from noosphere.core.payments import verify_paid_access
        if verify_paid_access(corpus["id"], bearer_token):
            return None
        # Fall through to access_tokens, but only the ones minted by a
        # successful facilitator settlement (label='agent-settlement'). Plain
        # tokens issued by the owner remain isolated to token-level corpora —
        # paid access still requires either a Stripe payment record or a
        # fresh facilitator-issued session token.
        token_id = _validate_token(
            corpus["id"], bearer_token, label_filter=AGENT_SETTLEMENT_LABEL
        )
        if token_id:
            return token_id
        raise AccessDenied(
            "Payment not found or expired. Use POST /api/v1/corpora/{id}/checkout to purchase access.",
            status_code=402,
        )

    return None


def _validate_token(
    corpus_id: str, raw_token: str, *, label_filter: str | None = None
) -> str | None:
    """Hash the raw token and look it up in access_tokens. Returns token id
    or None.

    Pass `label_filter` to restrict the match to tokens with a specific
    label — used for paid-corpus settlement tokens, which carry the
    `agent-settlement` label so they're not confused with owner-issued
    token-level tokens.
    """
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    conn = get_conn()
    if label_filter is not None:
        row = conn.execute(
            "SELECT id, expires_at FROM access_tokens "
            "WHERE corpus_id=? AND token_hash=? AND label=?",
            (corpus_id, token_hash, label_filter),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id, expires_at FROM access_tokens "
            "WHERE corpus_id=? AND token_hash=?",
            (corpus_id, token_hash),
        ).fetchone()
    if not row:
        return None

    if row["expires_at"]:
        try:
            exp = datetime.fromisoformat(row["expires_at"])
            if exp < datetime.now(timezone.utc):
                return None
        except (ValueError, TypeError):
            pass

    conn.execute(
        "UPDATE access_tokens SET usage_count = usage_count + 1, last_used_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), row["id"]),
    )
    conn.commit()
    return row["id"]
