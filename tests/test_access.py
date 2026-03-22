"""Tests for ``noosphere.core.access``."""

import pytest

from noosphere.core.access import AccessDenied, check_access
from noosphere.core.corpus import create_corpus, get_corpus
from noosphere.core.tokens import create_token, list_tokens


def test_check_access_public_allows_without_token(isolated_db):
    c = create_corpus("Pub", access_level="public")
    full = get_corpus(c["id"])
    assert check_access(full, None) is None
    assert check_access(full, "") is None


def test_check_access_private_denies(isolated_db):
    c = create_corpus("Priv", access_level="private")
    full = get_corpus(c["id"])
    with pytest.raises(AccessDenied) as exc:
        check_access(full, None)
    assert "private" in exc.value.message.lower()
    assert exc.value.status_code == 403


def test_check_access_token_requires_bearer(isolated_db):
    c = create_corpus("Tok", access_level="token")
    full = get_corpus(c["id"])
    with pytest.raises(AccessDenied) as exc:
        check_access(full, None)
    assert exc.value.status_code == 401
    with pytest.raises(AccessDenied) as exc2:
        check_access(full, "")
    assert exc2.value.status_code == 401


def test_check_access_token_invalid_denies(isolated_db):
    c = create_corpus("Tok2", access_level="token")
    full = get_corpus(c["id"])
    with pytest.raises(AccessDenied) as exc:
        check_access(full, "not-a-valid-token")
    assert exc.value.status_code == 401
    assert "invalid" in exc.value.message.lower() or "expired" in exc.value.message.lower()


def test_check_access_token_valid_returns_token_id(isolated_db):
    c = create_corpus("Tok3", access_level="token")
    full = get_corpus(c["id"])
    created = create_token(c["id"], label="cli")
    token_id = check_access(full, created["token"])
    assert token_id == created["id"]


def test_check_access_paid_denies(isolated_db):
    c = create_corpus("Paid", access_level="paid")
    full = get_corpus(c["id"])
    with pytest.raises(AccessDenied) as exc:
        check_access(full, None)
    assert "stripe" in exc.value.message.lower() or "paid" in exc.value.message.lower()


def test_access_denied_attributes():
    e = AccessDenied("msg", status_code=418)
    assert e.message == "msg"
    assert e.status_code == 418
    assert str(e) == "msg"


def test_check_access_valid_token_increments_usage(isolated_db):
    c = create_corpus("Usage", access_level="token")
    full = get_corpus(c["id"])
    created = create_token(c["id"], label="u")
    check_access(full, created["token"])
    check_access(full, created["token"])
    rows = list_tokens(c["id"])
    assert rows[0]["usage_count"] == 2


def test_check_access_expired_token_denies(isolated_db):
    c = create_corpus("Exp acc", access_level="token")
    full = get_corpus(c["id"])
    row = create_token(
        c["id"],
        label="gone",
        expires_at="1999-12-31T23:59:59+00:00",
    )
    with pytest.raises(AccessDenied) as exc:
        check_access(full, row["token"])
    assert exc.value.status_code == 401


def test_check_access_unknown_level_allows(isolated_db):
    """Levels other than public/private/token/paid fall through to allow."""
    c = create_corpus("Weird", access_level="custom_future")
    full = get_corpus(c["id"])
    assert check_access(full, None) is None


def test_access_denied_default_message_and_status():
    e = AccessDenied()
    assert e.status_code == 403
    assert "denied" in e.message.lower()


def test_check_access_token_whitespace_only_is_invalid_not_missing(isolated_db):
    """Non-empty whitespace is truthy; validation fails as invalid token."""
    c = create_corpus("WS tok", access_level="token")
    full = get_corpus(c["id"])
    with pytest.raises(AccessDenied) as exc:
        check_access(full, "   ")
    assert exc.value.status_code == 401
    assert "invalid" in exc.value.message.lower() or "expired" in exc.value.message.lower()


def test_check_access_paid_still_denies_with_valid_token(isolated_db):
    c = create_corpus("Paid plus tok", access_level="paid")
    full = get_corpus(c["id"])
    tok = create_token(c["id"])
    with pytest.raises(AccessDenied):
        check_access(full, tok["token"])
