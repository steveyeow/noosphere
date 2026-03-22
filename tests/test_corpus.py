"""Tests for corpus CRUD (``noosphere.core.corpus``)."""

import pytest

from noosphere.core.corpus import (
    create_corpus,
    delete_corpus,
    get_corpus,
    get_corpus_by_slug,
    list_corpora,
    update_corpus,
)
from noosphere.core.ingest import get_document, ingest_text
from noosphere.core.tokens import create_token, list_tokens


def test_create_corpus_returns_row_with_expected_fields(isolated_db):
    c = create_corpus(
        "My Test Corpus",
        description="A corpus for tests",
        author_name="Tester",
        tags=["a", "b"],
        access_level="public",
        language="en",
    )
    assert c["id"]
    assert c["name"] == "My Test Corpus"
    assert c["slug"] == "my-test-corpus"
    assert c["description"] == "A corpus for tests"
    assert c["author_name"] == "Tester"
    assert c["tags"] == ["a", "b"]
    assert c["access_level"] == "public"
    assert c["language"] == "en"


def test_get_corpus_returns_none_for_unknown_id(isolated_db):
    assert get_corpus("nonexistent000") is None


def test_get_corpus_round_trip(isolated_db):
    created = create_corpus("Round Trip")
    fetched = get_corpus(created["id"])
    assert fetched is not None
    assert fetched["id"] == created["id"]
    assert fetched["name"] == "Round Trip"


def test_get_corpus_by_slug(isolated_db):
    created = create_corpus("Sluggy Name")
    by_slug = get_corpus_by_slug(created["slug"])
    assert by_slug is not None
    assert by_slug["id"] == created["id"]


def test_get_corpus_by_slug_unknown(isolated_db):
    assert get_corpus_by_slug("no-such-slug") is None


def test_duplicate_name_gets_unique_slug(isolated_db):
    first = create_corpus("Same Name")
    second = create_corpus("Same Name")
    assert first["slug"] != second["slug"]
    assert second["slug"].startswith("same-name-")


def test_list_corpora_excludes_private(isolated_db):
    pub = create_corpus("Public One", access_level="public")
    create_corpus("Secret", access_level="private")
    listed = list_corpora()
    ids = {x["id"] for x in listed}
    assert pub["id"] in ids
    assert all(x["access_level"] != "private" for x in listed)


def test_list_corpora_includes_token_level(isolated_db):
    t = create_corpus("Token Corpus", access_level="token")
    listed = list_corpora()
    assert any(x["id"] == t["id"] for x in listed)


def test_update_corpus_allowed_fields(isolated_db):
    c = create_corpus("Original", description="old", tags=["x"])
    updated = update_corpus(
        c["id"],
        name="Renamed",
        description="new",
        tags=["y", "z"],
        access_level="token",
        status="published",
    )
    assert updated["name"] == "Renamed"
    assert updated["description"] == "new"
    assert updated["tags"] == ["y", "z"]
    assert updated["access_level"] == "token"
    assert updated["status"] == "published"


def test_update_corpus_ignores_unknown_fields(isolated_db):
    c = create_corpus("No Extra")
    updated = update_corpus(c["id"], bogus_field="nope", name="Still Works")
    assert updated["name"] == "Still Works"
    assert "bogus_field" not in updated


def test_update_corpus_empty_updates_returns_current(isolated_db):
    c = create_corpus("Stable")
    same = update_corpus(c["id"])
    assert same["id"] == c["id"]
    assert same["name"] == "Stable"


def test_delete_corpus_removes_row_and_related_data(isolated_db):
    c = create_corpus("To Delete")
    doc = ingest_text(c["id"], title="Doc", content="hello world")
    create_token(c["id"], label="L")
    assert delete_corpus(c["id"]) is True
    assert get_corpus(c["id"]) is None
    assert get_document(doc["id"]) is None
    assert list_tokens(c["id"]) == []


def test_delete_corpus_unknown_returns_false(isolated_db):
    assert delete_corpus("deadbeef0000") is False


def test_list_corpora_empty(isolated_db):
    assert list_corpora() == []


def test_update_corpus_nonexistent_id_returns_none(isolated_db):
    assert update_corpus("nonexistent00", name="Nope") is None


def test_create_corpus_optional_fields_defaults(isolated_db):
    c = create_corpus("Minimal")
    assert c["description"] == ""
    assert c["author_name"] == ""
    assert c["tags"] == []
    assert c["access_level"] == "public"
    assert c["status"] == "draft"


def test_get_corpus_by_slug_after_duplicate_name_slug_suffix(isolated_db):
    first = create_corpus("Dup Slug Name")
    second = create_corpus("Dup Slug Name")
    assert get_corpus_by_slug(first["slug"])["id"] == first["id"]
    assert get_corpus_by_slug(second["slug"])["id"] == second["id"]


def test_update_corpus_numeric_counts(isolated_db):
    c = create_corpus("Counts")
    updated = update_corpus(
        c["id"], document_count=3, chunk_count=10, word_count=1200
    )
    assert updated["document_count"] == 3
    assert updated["chunk_count"] == 10
    assert updated["word_count"] == 1200


def test_create_corpus_author_url_and_license(isolated_db):
    c = create_corpus(
        "Licensed",
        author_url="https://author.example",
        license_="mit",
    )
    assert c["author_url"] == "https://author.example"
    assert c["license"] == "mit"


def test_update_corpus_author_url_language_license(isolated_db):
    c = create_corpus("Up")
    u = update_corpus(
        c["id"],
        author_url="https://x.example",
        language="fr",
        license="apache-2.0",
    )
    assert u["author_url"] == "https://x.example"
    assert u["language"] == "fr"
    assert u["license"] == "apache-2.0"


def test_list_corpora_ordered_by_updated_at_desc(isolated_db):
    a = create_corpus("Older")
    b = create_corpus("Newer")
    update_corpus(a["id"], description="touch A")
    listed = list_corpora()
    assert [x["id"] for x in listed[:2]] == [a["id"], b["id"]]


def test_list_corpora_includes_paid_level(isolated_db):
    p = create_corpus("Paid Listed", access_level="paid")
    ids = {x["id"] for x in list_corpora()}
    assert p["id"] in ids


def test_delete_corpus_removes_query_logs(isolated_db):
    from datetime import datetime, timezone

    from noosphere.core.db import get_conn

    c = create_corpus("Logged")
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO query_logs (id, corpus_id, query_text, result_count, created_at) "
        "VALUES (?,?,?,?,?)",
        ("ql1", c["id"], "q", 0, now),
    )
    conn.commit()
    assert delete_corpus(c["id"]) is True
    n = conn.execute(
        "SELECT COUNT(*) FROM query_logs WHERE corpus_id=?", (c["id"],)
    ).fetchone()[0]
    assert n == 0


def test_create_corpus_embedding_fields(isolated_db):
    c = create_corpus(
        "Emb",
        embedding_model="text-embedding-3-small",
        embedding_dim=1536,
    )
    assert c["embedding_model"] == "text-embedding-3-small"
    assert c["embedding_dim"] == 1536


def test_create_corpus_source_type_and_url(isolated_db):
    c = create_corpus(
        "Src",
        source_type="git",
        source_url="https://github.com/example/repo",
    )
    assert c["source_type"] == "git"
    assert c["source_url"] == "https://github.com/example/repo"


def test_create_corpus_slug_strips_punctuation(isolated_db):
    c = create_corpus("Hello, World & Co.!")
    assert c["slug"] == "hello-world-co"
    c2 = create_corpus("  Spaces   Everywhere  ")
    assert c2["slug"] == "spaces-everywhere"


def test_get_corpus_includes_core_columns(isolated_db):
    c = create_corpus("Cols", description="d", author_name="auth")
    row = get_corpus(c["id"])
    for key in (
        "id",
        "name",
        "slug",
        "description",
        "author_name",
        "created_at",
        "updated_at",
        "access_level",
        "document_count",
        "chunk_count",
        "word_count",
    ):
        assert key in row


def test_delete_corpus_removes_chunks(isolated_db):
    import uuid
    from datetime import datetime, timezone

    from noosphere.core.db import get_conn
    from noosphere.core.ingest import ingest_text

    c = create_corpus("Chunk wipe")
    doc = ingest_text(c["id"], title="D", content="body")
    conn = get_conn()
    chunk_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO chunks
           (id, corpus_id, document_id, chunk_index, text, char_start, char_end,
            vector, dim, norm, metadata_json, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (chunk_id, c["id"], doc["id"], 0, "x", 0, 1, b"\x00", 1, 1.0, "{}", now),
    )
    conn.commit()
    assert delete_corpus(c["id"]) is True
    n = conn.execute(
        "SELECT COUNT(*) FROM chunks WHERE corpus_id=?", (c["id"],)
    ).fetchone()[0]
    assert n == 0
