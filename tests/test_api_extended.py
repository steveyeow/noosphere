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
