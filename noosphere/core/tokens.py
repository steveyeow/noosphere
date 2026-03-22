"""Access token management — create, list, revoke, validate tokens."""

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from noosphere.core.db import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_token(
    corpus_id: str,
    label: str = "",
    permissions: str = "read",
    expires_at: str | None = None,
) -> dict:
    """Create a new access token. Returns the plaintext token (shown only once)."""
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    token_id = uuid.uuid4().hex[:12]
    now = _now()

    conn = get_conn()
    conn.execute(
        """INSERT INTO access_tokens
           (id, corpus_id, token_hash, label, permissions, usage_count, expires_at, created_at)
           VALUES (?,?,?,?,?,0,?,?)""",
        (token_id, corpus_id, token_hash, label, permissions, expires_at, now),
    )
    conn.commit()

    return {
        "id": token_id,
        "corpus_id": corpus_id,
        "token": raw_token,
        "label": label,
        "permissions": permissions,
        "expires_at": expires_at,
        "created_at": now,
    }


def list_tokens(corpus_id: str) -> list[dict]:
    """List all tokens for a corpus (without the hash)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, corpus_id, label, permissions, usage_count, last_used_at, expires_at, created_at "
        "FROM access_tokens WHERE corpus_id=? ORDER BY created_at DESC",
        (corpus_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def revoke_token(token_id: str) -> bool:
    """Delete a token by ID. Returns True if a token was deleted."""
    conn = get_conn()
    cursor = conn.execute("DELETE FROM access_tokens WHERE id=?", (token_id,))
    conn.commit()
    return cursor.rowcount > 0


def validate_token(corpus_id: str, raw_token: str) -> str | None:
    """Validate a raw token against stored hashes. Returns token_id or None."""
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
        (_now(), row["id"]),
    )
    conn.commit()
    return row["id"]
