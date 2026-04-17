"""Extended API tests — covering endpoints not tested in test_api.py."""

import pytest
from unittest.mock import patch, MagicMock

import numpy as np


@pytest.fixture
def corpus(client):
    r = client.post("/api/v1/corpora", json={
        "name": "Extended Test",
        "description": "for extended tests",
        "tags": ["alpha", "beta"],
        "access_level": "public",
    })
    assert r.status_code == 200
    return r.json()


@pytest.fixture
def corpus_with_doc(client, corpus):
    from io import BytesIO
    md = b"---\ntitle: Test Doc\n---\n\nThis is test content about machine learning and neural networks."
    r = client.post(
        f"/api/v1/corpora/{corpus['id']}/upload",
        files=[("files", ("test.md", BytesIO(md), "text/markdown"))],
    )
    assert r.status_code == 200
    return corpus


# ── Terminal ──

def test_terminal_question(client, corpus_with_doc):
    r = client.post("/api/v1/terminal", json={"input": "hello", "context": {}})
    assert r.status_code == 200
    data = r.json()
    assert "lines" in data
    assert "context" in data


def test_terminal_help(client):
    r = client.post("/api/v1/terminal", json={"input": "/help", "context": {}})
    assert r.status_code == 200
    assert "lines" in r.json()


def test_terminal_blocked_for_agents(client):
    r = client.post(
        "/api/v1/terminal",
        json={"input": "test", "context": {}},
        headers={"x-agent-id": "external-agent"},
    )
    assert r.status_code == 403


# ── Global Search ──

def test_global_search_empty(client):
    r = client.post("/api/v1/search", json={"query": "anything"})
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert "corpora_searched" in data


def test_global_search_excludes_private(client):
    r = client.post("/api/v1/corpora", json={"name": "Private Search", "access_level": "public"})
    cid = r.json()["id"]
    client.patch(f"/api/v1/corpora/{cid}", json={"access_level": "private"})

    r = client.post("/api/v1/search", json={"query": "anything"})
    data = r.json()
    for result in data.get("results", []):
        assert result.get("corpus_id") != cid


# ── Index ──

def _mock_embedder():
    embedder = MagicMock()
    embedder.embed.side_effect = lambda texts: np.random.randn(len(texts), 8).astype(np.float32)
    embedder.dim.return_value = 8
    embedder.model_name.return_value = "mock-embed"
    return embedder


@patch("noosphere.core.indexer.get_embedder")
def test_index_corpus_api(mock_get_embedder, client, corpus_with_doc):
    mock_get_embedder.return_value = _mock_embedder()
    r = client.post(f"/api/v1/corpora/{corpus_with_doc['id']}/index")
    assert r.status_code == 200
    data = r.json()
    assert "chunk_count" in data
    assert data["chunk_count"] > 0


@patch("noosphere.core.indexer.get_embedder")
def test_index_corpus_with_force(mock_get_embedder, client, corpus_with_doc):
    mock_get_embedder.return_value = _mock_embedder()
    r = client.post(
        f"/api/v1/corpora/{corpus_with_doc['id']}/index",
        json={"force": True},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["skipped"] == 0


def test_index_blocked_for_agents(client, corpus):
    r = client.post(
        f"/api/v1/corpora/{corpus['id']}/index",
        headers={"x-agent-id": "external-agent"},
    )
    assert r.status_code == 403


# ── Ingest URL ──

@patch("httpx.get")
def test_ingest_url_api(mock_get, client, corpus):
    mock_resp = MagicMock()
    mock_resp.text = "<html><head><title>Test Page</title></head><body><p>Some content about testing and knowledge.</p></body></html>"
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp
    r = client.post(
        f"/api/v1/corpora/{corpus['id']}/ingest-url",
        json={"url": "https://example.com/test"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "id" in data


# ── Stats ──

def test_stats_api(client, corpus):
    r = client.get(f"/api/v1/corpora/{corpus['id']}/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["corpus_id"] == corpus["id"]
    assert "document_count" in data
    assert "chunk_count" in data
    assert "word_count" in data


# ── Topics ──

def test_topics_api(client, corpus):
    r = client.get(f"/api/v1/corpora/{corpus['id']}/topics")
    assert r.status_code == 200
    data = r.json()
    assert "topics" in data
    assert isinstance(data["topics"], list)


def test_topics_include_corpus_tags(client, corpus):
    r = client.get(f"/api/v1/corpora/{corpus['id']}/topics")
    data = r.json()
    assert "alpha" in data["topics"]
    assert "beta" in data["topics"]


# ── Analytics ──

def test_analytics_api(client, corpus):
    r = client.get(f"/api/v1/corpora/{corpus['id']}/analytics")
    assert r.status_code == 200
    data = r.json()
    assert "total_queries" in data
    assert "recent_queries" in data
    assert isinstance(data["recent_queries"], list)


# ── Network ──

def test_network_api(client, corpus):
    r = client.get("/api/v1/corpora/network")
    assert r.status_code == 200
    data = r.json()
    assert "nodes" in data
    assert "links" in data
    assert len(data["nodes"]) >= 1
    assert data["nodes"][0]["id"] == corpus["id"]


def test_network_links_computed(client):
    client.post("/api/v1/corpora", json={"name": "Net A", "tags": ["shared"]})
    client.post("/api/v1/corpora", json={"name": "Net B", "tags": ["shared"]})
    r = client.get("/api/v1/corpora/network")
    data = r.json()
    assert len(data["links"]) >= 1


# ── Chat Sessions ──

def test_chat_sessions_list(client):
    r = client.get("/api/v1/chat-sessions")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_chat_session_not_found(client):
    r = client.get("/api/v1/chat-sessions/nonexistent")
    assert r.status_code == 404


def test_delete_chat_session(client, corpus):
    from noosphere.core.db import get_conn
    import uuid
    from datetime import datetime, timezone

    conn = get_conn()
    sid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO chat_sessions (id, corpus_id, title, created_at, updated_at) VALUES (?,?,?,?,?)",
        (sid, corpus["id"], "Test Session", now, now),
    )
    conn.commit()

    r = client.delete(f"/api/v1/chat-sessions/{sid}")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r = client.get(f"/api/v1/chat-sessions/{sid}")
    assert r.status_code == 404


def test_delete_chat_session_blocked_for_agents(client, corpus):
    r = client.delete(
        "/api/v1/chat-sessions/some-id",
        headers={"x-agent-id": "external-agent"},
    )
    assert r.status_code == 403


# ── Auth: Create corpus ──

def test_create_corpus_blocked_for_agents(client):
    r = client.post(
        "/api/v1/corpora",
        json={"name": "Hacked"},
        headers={"x-agent-id": "external-agent"},
    )
    assert r.status_code == 403


# ── Upload blocked for agents ──

def test_upload_blocked_for_agents(client, corpus):
    from io import BytesIO
    r = client.post(
        f"/api/v1/corpora/{corpus['id']}/upload",
        files=[("files", ("test.md", BytesIO(b"hello"), "text/markdown"))],
        headers={"x-agent-id": "external-agent"},
    )
    assert r.status_code == 403


# ── Knowledge growth API ──

def test_capture_to_corpus(client, corpus, monkeypatch):
    monkeypatch.setattr(
        "noosphere.core.knowledge_growth.index_corpus",
        lambda *a, **k: {"chunk_count": 0, "skipped": 0},
    )
    r = client.post(
        f"/api/v1/corpora/{corpus['id']}/capture",
        json={"content": "# Cap\n\nhello world", "title": "From UI", "question": "Why?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("doc_type") == "capture"
    assert body.get("title") == "From UI"


def test_knowledge_health_endpoint(client, corpus_with_doc):
    r = client.get(f"/api/v1/corpora/{corpus_with_doc['id']}/knowledge-health")
    assert r.status_code == 200
    data = r.json()
    assert data["document_count"] >= 1
    assert "documents_without_chunks_count" in data


def test_ingest_feed_api_mock(client, corpus, monkeypatch):
    xml = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>T</title><link>https://example.invalid/only-xml</link><guid>g99</guid>
<description>Body only</description></item></channel></rss>"""

    class FakeResp:
        def raise_for_status(self):
            return None

        @property
        def content(self):
            return xml

    def fake_get(*a, **k):
        return FakeResp()

    monkeypatch.setattr("noosphere.core.knowledge_growth.httpx.get", fake_get)
    monkeypatch.setattr(
        "noosphere.core.knowledge_growth.index_corpus",
        lambda *a, **k: {"chunk_count": 0},
    )
    r = client.post(
        f"/api/v1/corpora/{corpus['id']}/ingest-feed",
        json={"feed_url": "https://example.com/feed.xml", "max_items": 5},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("ingested", 0) >= 1


def test_ingest_urls_bulk_mock(client, corpus, monkeypatch):
    monkeypatch.setattr(
        "noosphere.core.knowledge_growth.ingest_url",
        lambda cid, url, doc_type="blog", source_kind=None: {"id": "x1", "title": url, "corpus_id": cid},
    )
    monkeypatch.setattr(
        "noosphere.core.knowledge_growth.index_corpus",
        lambda *a, **k: {"chunk_count": 0},
    )
    r = client.post(
        f"/api/v1/corpora/{corpus['id']}/ingest-urls",
        json={"urls": ["https://a.example/x", "https://b.example/y"]},
    )
    assert r.status_code == 200
    assert r.json()["ingested"] == 2


def test_maintain_endpoint(client, corpus, monkeypatch):
    monkeypatch.setattr(
        "noosphere.core.knowledge_growth.index_corpus",
        lambda *a, **k: {"chunk_count": 0, "skipped": 0},
    )
    r = client.post(
        f"/api/v1/corpora/{corpus['id']}/maintain",
        json={"force": False},
    )
    assert r.status_code == 200


# ── Phase 1a: source_kind filter + publish guard ──


def test_access_summary_counts_by_source_kind(client, corpus):
    from noosphere.core.ingest import ingest_text
    ingest_text(corpus["id"], title="Mine", content="my note body", source_kind="user_original")
    ingest_text(corpus["id"], title="Feed", content="external blog body", source_kind="external_public")
    ingest_text(corpus["id"], title="Book", content="ebook content body", source_kind="external_subscription")

    r = client.get(f"/api/v1/corpora/{corpus['id']}/access-summary")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    assert data["originals"] == 1
    assert data["by_source_kind"]["user_original"] == 1
    assert data["by_source_kind"]["external_public"] == 1
    assert data["by_source_kind"]["external_subscription"] == 1
    assert data["can_enable_external_access"] is True
    assert data["visibility"]["owner"] == 3
    assert data["visibility"]["external"] == 1


def test_access_summary_empty_corpus(client, corpus):
    r = client.get(f"/api/v1/corpora/{corpus['id']}/access-summary")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["originals"] == 0
    assert data["can_enable_external_access"] is False


def test_pricing_blocked_when_only_external_content(client, corpus):
    from noosphere.core.ingest import ingest_text
    ingest_text(corpus["id"], title="Ext", content="external body", source_kind="external_public")

    r = client.post(
        f"/api/v1/corpora/{corpus['id']}/pricing",
        json={"type": "per_query", "amount_cents": 500, "currency": "usd", "queries_per_payment": 10},
    )
    assert r.status_code == 400
    assert "external" in r.json()["detail"].lower()


def test_pricing_allowed_with_user_original(client, corpus):
    from noosphere.core.ingest import ingest_text
    ingest_text(corpus["id"], title="Ext", content="external body", source_kind="external_public")
    ingest_text(corpus["id"], title="Mine", content="my body", source_kind="user_original")

    r = client.post(
        f"/api/v1/corpora/{corpus['id']}/pricing",
        json={"type": "per_query", "amount_cents": 500, "currency": "usd", "queries_per_payment": 10},
    )
    assert r.status_code == 200


def test_access_level_change_to_public_blocked_when_external_only(client, corpus):
    # Corpus was created as access_level=public already; need to re-set by first
    # moving to private, then trying to move back to public with only external content.
    from noosphere.core.ingest import ingest_text
    ingest_text(corpus["id"], title="Ext", content="external body", source_kind="external_public")
    r = client.patch(f"/api/v1/corpora/{corpus['id']}", json={"access_level": "private"})
    assert r.status_code == 200
    r = client.patch(f"/api/v1/corpora/{corpus['id']}", json={"access_level": "public"})
    assert r.status_code == 400


def test_search_filters_external_for_external_caller(client, corpus):
    """Caller-aware filter hides external_* from non-owners. Uses a mocked embedder
    so the test doesn't require a real API key in CI.
    """
    from noosphere.core.ingest import ingest_text
    ingest_text(corpus["id"], title="My note", content="alpha beta gamma original thinking here", source_kind="user_original")
    ingest_text(corpus["id"], title="External", content="alpha beta gamma external material here", source_kind="external_public")

    def _mock_embedder():
        m = MagicMock()
        m.embed.side_effect = lambda texts: np.random.randn(len(texts), 8).astype(np.float32)
        m.dim.return_value = 8
        m.model_name.return_value = "mock-embed"
        return m

    with patch("noosphere.core.indexer.get_embedder", return_value=_mock_embedder()):
        from noosphere.core.indexer import index_corpus
        index_corpus(corpus["id"])

    with patch("noosphere.core.retrieval.get_embedder", return_value=_mock_embedder()):
        # Owner caller (owner is detected via TestClient being localhost + no x-agent-id header)
        r = client.post(f"/api/v1/corpora/{corpus['id']}/search", json={"query": "alpha beta"})
        assert r.status_code == 200
        owner_titles = {r_["citation"]["document_title"] for r_ in r.json().get("results", [])}
        assert "My note" in owner_titles
        assert "External" in owner_titles

        # External caller (x-agent-id header forces non-owner detection)
        r = client.post(
            f"/api/v1/corpora/{corpus['id']}/search",
            json={"query": "alpha beta"},
            headers={"x-agent-id": "agent-1"},
        )
        assert r.status_code == 200
        external_titles = {r_["citation"]["document_title"] for r_ in r.json().get("results", [])}
        assert "My note" in external_titles
        assert "External" not in external_titles


# ── Phase 0.5: entity extraction ──


def test_html_author_detection_from_meta_tags():
    from noosphere.core.entities import detect_html_author
    assert detect_html_author('<html><head><meta name="author" content="Paul Graham" /></head>') == "Paul Graham"
    assert detect_html_author('<meta property="article:author" content="Lenny Rachitsky">') == "Lenny Rachitsky"
    assert detect_html_author('<meta name="twitter:creator" content="@steverz">') == "steverz"
    assert detect_html_author('<html><body>no author</body></html>') is None
    assert detect_html_author("") is None


def test_upsert_entity_dedup_case_insensitive(client, corpus):
    from noosphere.core.entities import upsert_entity, get_entity
    e1 = upsert_entity(corpus["id"], "person", "Paul Graham")
    e2 = upsert_entity(corpus["id"], "person", "paul graham")
    assert e1 == e2  # deduped case-insensitively
    assert get_entity(e1)["canonical_name"] == "Paul Graham"  # first write wins


def test_upsert_entity_merges_aliases(client, corpus):
    from noosphere.core.entities import upsert_entity, get_entity
    eid = upsert_entity(corpus["id"], "person", "Andrej Karpathy", aliases=["karpathy"])
    upsert_entity(corpus["id"], "person", "Andrej Karpathy", aliases=["Karpathy", "andrej"])
    ent = get_entity(eid)
    assert set(ent["aliases"]) == {"karpathy", "Karpathy", "andrej"}


def test_upsert_entity_rejects_invalid_kind(client, corpus):
    from noosphere.core.entities import upsert_entity
    assert upsert_entity(corpus["id"], "invalid_kind", "Something") is None


def test_list_entities_counts_mentions_across_fields(client, corpus):
    """mention_count aggregates author_entity_id + participants + metadata mentions."""
    from noosphere.core.entities import upsert_entity, list_entities
    from noosphere.core.ingest import ingest_text

    p1 = upsert_entity(corpus["id"], "person", "Alice")
    p2 = upsert_entity(corpus["id"], "person", "Bob")

    # Doc 1: authored by Alice
    ingest_text(corpus["id"], title="A", content="one", author_entity_id=p1)
    # Doc 2: authored by Alice, Bob is a participant
    ingest_text(corpus["id"], title="B", content="two", author_entity_id=p1, participant_entity_ids=[p2])
    # Doc 3: mentions Bob only (via metadata)
    ingest_text(corpus["id"], title="C", content="three", metadata={"mentioned_entity_ids": [p2]})

    ents = {e["canonical_name"]: e for e in list_entities(corpus["id"])}
    assert ents["Alice"]["mention_count"] == 2
    assert ents["Bob"]["mention_count"] == 2


def test_list_entities_api(client, corpus):
    from noosphere.core.entities import upsert_entity
    upsert_entity(corpus["id"], "person", "Ada Lovelace")
    upsert_entity(corpus["id"], "company", "Anthropic")
    r = client.get(f"/api/v1/corpora/{corpus['id']}/entities")
    assert r.status_code == 200
    names = {e["canonical_name"] for e in r.json()["entities"]}
    assert {"Ada Lovelace", "Anthropic"} <= names

    r_p = client.get(f"/api/v1/corpora/{corpus['id']}/entities?kind=person")
    p_names = {e["canonical_name"] for e in r_p.json()["entities"]}
    assert p_names == {"Ada Lovelace"}


def test_extract_entities_endpoint_mock(client, corpus, monkeypatch):
    from noosphere.core.ingest import ingest_text
    doc = ingest_text(
        corpus["id"],
        title="Post",
        content="A long enough piece of prose about several topics that the extractor can chew on. "
                "It mentions Paul Graham and his work at Y Combinator. It also discusses AI.",
    )
    monkeypatch.setattr(
        "noosphere.core.entities.extract_entities_from_text",
        lambda text: [
            {"kind": "person", "canonical_name": "Paul Graham"},
            {"kind": "company", "canonical_name": "Y Combinator"},
        ],
    )
    r = client.post(f"/api/v1/corpora/{corpus['id']}/documents/{doc['id']}/extract-entities")
    assert r.status_code == 200
    body = r.json()
    assert body["entities_extracted"] == 2
    # Mentions persisted in doc metadata
    r2 = client.get(f"/api/v1/corpora/{corpus['id']}/entities")
    names = {e["canonical_name"] for e in r2.json()["entities"]}
    assert {"Paul Graham", "Y Combinator"} <= names


def test_batch_extract_skips_already_enriched(client, corpus, monkeypatch):
    from noosphere.core.ingest import ingest_text
    ingest_text(corpus["id"], title="A", content="long prose about Alice and her work " * 5)
    ingest_text(corpus["id"], title="B", content="long prose about Bob and his work " * 5)
    calls = {"n": 0}

    def _fake(text):
        calls["n"] += 1
        return [{"kind": "person", "canonical_name": "Alice"}]

    monkeypatch.setattr("noosphere.core.entities.extract_entities_from_text", _fake)

    r = client.post(f"/api/v1/corpora/{corpus['id']}/extract-entities", json={"limit": 50})
    assert r.status_code == 200
    assert r.json()["enriched"] == 2
    assert calls["n"] == 2

    # Second call: everything already enriched, should skip
    r2 = client.post(f"/api/v1/corpora/{corpus['id']}/extract-entities", json={"limit": 50})
    assert r2.status_code == 200
    assert r2.json()["enriched"] == 0
    assert calls["n"] == 2


def test_ingest_url_sets_author_from_meta(client, corpus, monkeypatch):
    from noosphere.core.ingest import ingest_url
    import httpx

    class _Resp:
        status_code = 200
        text = (
            '<html><head><title>How to Read</title>'
            '<meta name="author" content="Paul Graham" /></head>'
            '<body><h1>How to Read</h1><p>One should read widely.</p></body></html>'
        )
        def raise_for_status(self):
            pass

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp())
    doc = ingest_url(corpus["id"], "http://paulgraham.com/read.html")
    assert doc["source_kind"] == "external_public"

    from noosphere.core.entities import list_entities
    ents = list_entities(corpus["id"])
    assert any(e["canonical_name"] == "Paul Graham" and e["kind"] == "person" for e in ents)


def test_compile_endpoint_mock(client, corpus_with_doc, monkeypatch):
    monkeypatch.setattr(
        "noosphere.core.knowledge_growth.search_corpus",
        lambda cid, q, top_k=5: {
            "results": [
                {
                    "text": "Fact one about topic.",
                    "score": 0.9,
                    "citation": {"document_title": "Src", "document_id": "d1"},
                }
            ]
        },
    )
    monkeypatch.setattr(
        "noosphere.core.llm.call_llm",
        lambda messages: "# Summary\n\nSynth.\n\n## Sources\n- Src",
    )
    monkeypatch.setattr(
        "noosphere.core.knowledge_growth.index_corpus",
        lambda *a, **k: {"chunk_count": 1},
    )
    r = client.post(
        f"/api/v1/corpora/{corpus_with_doc['id']}/compile",
        json={"topic": "topic", "top_k": 3},
    )
    assert r.status_code == 200
    assert r.json().get("doc_type") == "concept"
