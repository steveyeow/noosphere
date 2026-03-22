"""Access control — enforce corpus access levels.

Checks whether a request is authorized to access a given corpus
based on its access_level setting (public, private, token, paid).
"""

import hashlib
from datetime import datetime, timezone

from noosphere.core.db import get_conn


class AccessDenied(Exception):
    """Raised when access to a corpus is denied."""

    def __init__(self, message: str = "Access denied", status_code: int = 403):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


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
        raise AccessDenied("Paid access requires Stripe integration (coming in Phase 2)")

    return None


def _validate_token(corpus_id: str, raw_token: str) -> str | None:
    """Hash the raw token and look it up in access_tokens. Returns token id or None."""
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    conn = get_conn()
    row = conn.execute(
        "SELECT id, expires_at FROM access_tokens WHERE corpus_id=? AND token_hash=?",
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
