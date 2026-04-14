"""Registry server tests — registration, search, health, directory."""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from noosphere.registry.server import app, set_db_path
from noosphere.registry.db import close_registry, get_registry_conn
from noosphere.registry.health import stop_health_checker


@pytest.fixture(autouse=True)
def isolated_registry_db(tmp_path: Path):
    """Fresh registry SQLite DB per test."""
    close_registry()
    stop_health_checker()

    db_path = tmp_path / "test_registry.db"
    set_db_path(str(db_path))

    # Pre-init DB so tests don't rely on lifespan
    import noosphere.registry.db as rdb
    rdb._conn = None
    get_registry_conn(str(db_path))

    yield
    close_registry()


@pytest.fixture
def client(isolated_registry_db):
    # Disable lifespan to avoid health checker in tests
    app.router.lifespan_context = _noop_lifespan
    with TestClient(app) as c:
        yield c


from contextlib import asynccontextmanager

@asynccontextmanager
async def _noop_lifespan(app):
    yield


# ── Registration ──


_NODE_PAYLOAD = {
    "node_version": "0.1.0",
    "endpoint": "http://localhost:8420",
    "corpora": [
        {
            "corpus_id": "abc-123",
            "name": "Test Knowledge Base",
            "slug": "test-kb",
            "description": "A test corpus about AI safety",
            "author": "Alice",
            "tags": ["ai", "safety", "alignment"],
            "document_count": 50,
            "chunk_count": 200,
            "word_count": 100000,
            "access_level": "public",
            "status": "ready",
        },
        {
            "corpus_id": "def-456",
            "name": "Startup Playbook",
            "slug": "startup-playbook",
            "description": "Lessons from building startups",
            "author": "Bob",
            "tags": ["startups", "growth", "product"],
            "document_count": 30,
            "chunk_count": 120,
            "word_count": 60000,
            "access_level": "public",
            "status": "ready",
        },
    ],
}


def test_register_node(client):
    r = client.post("/api/v1/register", json=_NODE_PAYLOAD)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["registered"] == 2
    assert body["endpoint"] == "http://localhost:8420"


def test_register_requires_endpoint(client):
    r = client.post("/api/v1/register", json={"endpoint": "", "corpora": [{"corpus_id": "x", "name": "x"}]})
    assert r.status_code == 400


def test_register_requires_corpora(client):
    r = client.post("/api/v1/register", json={"endpoint": "http://example.com", "corpora": []})
    assert r.status_code == 400


def test_register_updates_on_re_register(client):
    client.post("/api/v1/register", json=_NODE_PAYLOAD)

    # Update with changed metadata
    updated = {**_NODE_PAYLOAD, "corpora": [
        {**_NODE_PAYLOAD["corpora"][0], "document_count": 100},
    ]}
    r = client.post("/api/v1/register", json=updated)
    assert r.status_code == 200
    assert r.json()["registered"] == 1

    # The removed corpus should be gone
    r = client.get("/api/v1/corpora")
    assert r.status_code == 200
    corpora = r.json()["corpora"]
    assert len(corpora) == 1
    assert corpora[0]["document_count"] == 100


# ── Deregistration ──


def test_deregister_node(client):
    client.post("/api/v1/register", json=_NODE_PAYLOAD)
    r = client.post("/api/v1/deregister", json={"endpoint": "http://localhost:8420"})
    assert r.status_code == 200

    r = client.get("/api/v1/nodes")
    assert r.json()["count"] == 0

    r = client.get("/api/v1/corpora")
    assert r.json()["count"] == 0


def test_deregister_nonexistent_is_ok(client):
    r = client.post("/api/v1/deregister", json={"endpoint": "http://nowhere.example.com"})
    assert r.status_code == 200


# ── Search ──


def test_search_by_keyword(client):
    client.post("/api/v1/register", json=_NODE_PAYLOAD)

    r = client.get("/api/v1/search", params={"q": "AI safety"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert any("AI" in (c.get("name", "") + c.get("description", "")) for c in body["results"])


def test_search_returns_endpoints(client):
    client.post("/api/v1/register", json=_NODE_PAYLOAD)

    r = client.get("/api/v1/search", params={"q": "startup"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) >= 1
    assert "api_endpoint" in results[0]
    assert "mcp_endpoint" in results[0]
    assert "/api/v1/corpora/" in results[0]["api_endpoint"]


def test_search_filter_by_access_level(client):
    # Register with a token-gated corpus
    payload = {
        "endpoint": "http://localhost:9999",
        "corpora": [{
            "corpus_id": "token-1",
            "name": "Token Gated KB",
            "description": "Private knowledge",
            "access_level": "token",
            "status": "ready",
        }],
    }
    client.post("/api/v1/register", json=payload)
    client.post("/api/v1/register", json=_NODE_PAYLOAD)

    r = client.get("/api/v1/search", params={"q": "knowledge", "access_level": "token"})
    assert r.status_code == 200
    for result in r.json()["results"]:
        assert result["access_level"] == "token"


def test_search_short_query_rejected(client):
    r = client.get("/api/v1/search", params={"q": "a"})
    assert r.status_code == 400


# ── Directory ──


def test_list_nodes(client):
    client.post("/api/v1/register", json=_NODE_PAYLOAD)

    r = client.get("/api/v1/nodes")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["nodes"][0]["endpoint"] == "http://localhost:8420"
    assert body["nodes"][0]["corpus_count"] == 2


def test_list_corpora(client):
    client.post("/api/v1/register", json=_NODE_PAYLOAD)

    r = client.get("/api/v1/corpora")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    names = {c["name"] for c in body["corpora"]}
    assert "Test Knowledge Base" in names
    assert "Startup Playbook" in names


def test_list_corpora_pagination(client):
    client.post("/api/v1/register", json=_NODE_PAYLOAD)

    r = client.get("/api/v1/corpora", params={"limit": 1, "offset": 0})
    assert r.json()["count"] == 1

    r = client.get("/api/v1/corpora", params={"limit": 1, "offset": 1})
    assert r.json()["count"] == 1


def test_get_corpus_detail(client):
    client.post("/api/v1/register", json=_NODE_PAYLOAD)

    r = client.get("/api/v1/corpora/abc-123")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Test Knowledge Base"
    assert body["author"] == "Alice"
    assert "api_endpoint" in body


def test_get_corpus_not_found(client):
    r = client.get("/api/v1/corpora/nonexistent")
    assert r.status_code == 404


# ── Stats ──


def test_network_stats(client):
    client.post("/api/v1/register", json=_NODE_PAYLOAD)

    r = client.get("/api/v1/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["nodes_total"] == 1
    assert body["nodes_online"] == 1
    assert body["corpora_total"] == 2
    assert body["total_documents"] == 80  # 50 + 30
    assert body["total_words"] == 160000  # 100000 + 60000
    assert "public" in body["access_levels"]


# ── Health endpoint ──


def test_registry_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


# ── Browsable directory ──


def test_browsable_directory_html(client):
    client.post("/api/v1/register", json=_NODE_PAYLOAD)

    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Noosphere Registry" in r.text
    assert "Test Knowledge Base" in r.text


def test_browsable_directory_empty(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "No knowledge bases registered yet" in r.text


# ── Multiple nodes ──


def test_multiple_nodes(client):
    client.post("/api/v1/register", json=_NODE_PAYLOAD)

    second_node = {
        "endpoint": "http://node2.example.com:8420",
        "node_version": "0.2.0",
        "corpora": [{
            "corpus_id": "ghi-789",
            "name": "Climate Research",
            "description": "Climate science papers and analysis",
            "author": "Carol",
            "tags": ["climate", "science"],
            "document_count": 200,
            "status": "ready",
        }],
    }
    client.post("/api/v1/register", json=second_node)

    r = client.get("/api/v1/nodes")
    assert r.json()["count"] == 2

    r = client.get("/api/v1/corpora")
    assert r.json()["count"] == 3

    r = client.get("/api/v1/search", params={"q": "climate"})
    assert r.json()["count"] >= 1
    assert r.json()["results"][0]["name"] == "Climate Research"
