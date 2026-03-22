"""Tests for ``noosphere.core.tokens``."""

from noosphere.core.corpus import create_corpus
from noosphere.core.tokens import (
    create_token,
    list_tokens,
    revoke_token,
    validate_token,
)


def test_create_token_returns_plaintext_once(isolated_db):
    c = create_corpus("Tok Corpus")
    row = create_token(c["id"], label="dev", permissions="read")
    assert row["id"]
    assert row["corpus_id"] == c["id"]
    assert row["label"] == "dev"
    assert row["permissions"] == "read"
    assert len(row["token"]) > 20


def test_list_tokens_excludes_secret(isolated_db):
    c = create_corpus("List Tok")
    created = create_token(c["id"], label="L1")
    listed = list_tokens(c["id"])
    assert len(listed) == 1
    assert listed[0]["id"] == created["id"]
    assert "token" not in listed[0]
    assert listed[0]["label"] == "L1"


def test_revoke_token(isolated_db):
    c = create_corpus("Rev")
    created = create_token(c["id"])
    assert revoke_token(created["id"]) is True
    assert list_tokens(c["id"]) == []
    assert revoke_token(created["id"]) is False


def test_validate_token_success_updates_usage(isolated_db):
    c = create_corpus("Val")
    created = create_token(c["id"])
    tid = validate_token(c["id"], created["token"])
    assert tid == created["id"]
    rows = list_tokens(c["id"])
    assert rows[0]["usage_count"] == 1
    assert rows[0]["last_used_at"]


def test_validate_token_wrong_corpus(isolated_db):
    a = create_corpus("A")
    b = create_corpus("B")
    created = create_token(a["id"])
    assert validate_token(b["id"], created["token"]) is None


def test_validate_token_expired(isolated_db):
    c = create_corpus("Exp")
    row = create_token(
        c["id"],
        label="old",
        expires_at="2000-01-01T00:00:00+00:00",
    )
    assert validate_token(c["id"], row["token"]) is None


def test_list_tokens_empty(isolated_db):
    c = create_corpus("No tokens yet")
    assert list_tokens(c["id"]) == []


def test_validate_token_wrong_secret(isolated_db):
    c = create_corpus("Bad secret")
    created = create_token(c["id"])
    assert validate_token(c["id"], "totally-wrong-token-string") is None
    rows = list_tokens(c["id"])
    assert rows[0]["usage_count"] == 0


def test_create_token_future_expiry_still_validates(isolated_db):
    c = create_corpus("Future")
    row = create_token(
        c["id"],
        label="future",
        expires_at="2099-01-01T00:00:00+00:00",
    )
    assert validate_token(c["id"], row["token"]) == row["id"]


def test_create_token_stores_permissions_and_expires(isolated_db):
    c = create_corpus("Meta")
    row = create_token(
        c["id"],
        label="L",
        permissions="read,query",
        expires_at="2090-06-15T12:00:00+00:00",
    )
    listed = list_tokens(c["id"])[0]
    assert listed["permissions"] == "read,query"
    assert listed["expires_at"] == "2090-06-15T12:00:00+00:00"
    assert listed["label"] == "L"


def test_create_token_without_expiry_lists_null_expires_at(isolated_db):
    c = create_corpus("No exp")
    row = create_token(c["id"], label="open")
    assert row["expires_at"] is None
    listed = list_tokens(c["id"])[0]
    assert listed.get("expires_at") in (None, "")


def test_list_tokens_includes_all_for_corpus(isolated_db):
    c = create_corpus("Many toks")
    a = create_token(c["id"], label="a")
    b = create_token(c["id"], label="b")
    rows = list_tokens(c["id"])
    assert {r["id"] for r in rows} == {a["id"], b["id"]}


def test_revoke_one_token_leaves_others(isolated_db):
    c = create_corpus("Partial revoke")
    x = create_token(c["id"], label="x")
    create_token(c["id"], label="y")
    assert revoke_token(x["id"]) is True
    labels = {r["label"] for r in list_tokens(c["id"])}
    assert labels == {"y"}
