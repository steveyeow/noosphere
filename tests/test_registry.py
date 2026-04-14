"""Network discovery tests — registration, search, health check, stats.

Tests the built-in registry endpoints on the main API (no separate server).
"""

import pytest
from fastapi.testclient import TestClient

from noosphere.api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Fresh SQLite DB per test via the main app."""
    monkeypatch.setenv("NOOSPHERE_DATA_DIR", str(tmp_path))

    import noosphere.core.db as db_mod
    db_mod._conn = None

    import noosphere.core.config as cfg
    cfg.DATA_DIR = tmp_path
    cfg.DB_PATH = tmp_path / "noosphere.db"
    db_mod.DATA_DIR = tmp_path
    db_mod.DB_PATH = tmp_path / "noosphere.db"

    with TestClient(app) as c:
        yield c

    db_mod.close()


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


# ── Registration ──


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

    updated = {**_NODE_PAYLOAD, "corpora": [
        {**_NODE_PAYLOAD["corpora"][0], "document_count": 100},
    ]}
    r = client.post("/api/v1/register", json=updated)
    assert r.status_code == 200
    assert r.json()["registered"] == 1

    r = client.get("/api/v1/network/nodes")
    nodes = r.json()["nodes"]
    assert len(nodes) == 1


# ── Deregistration ──


def test_deregister_node(client):
    client.post("/api/v1/register", json=_NODE_PAYLOAD)
    r = client.post("/api/v1/deregister", json={"endpoint": "http://localhost:8420"})
    assert r.status_code == 200

    r = client.get("/api/v1/network/nodes")
    assert r.json()["count"] == 0


def test_deregister_nonexistent_is_ok(client):
    r = client.post("/api/v1/deregister", json={"endpoint": "http://nowhere.example.com"})
    assert r.status_code == 200


# ── Network search ──


def test_network_search_by_keyword(client):
    client.post("/api/v1/register", json=_NODE_PAYLOAD)

    r = client.get("/api/v1/network/search", params={"q": "AI safety"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1


def test_network_search_returns_endpoints(client):
    client.post("/api/v1/register", json=_NODE_PAYLOAD)

    r = client.get("/api/v1/network/search", params={"q": "startup"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) >= 1
    remote = [x for x in results if x.get("source") == "remote"]
    if remote:
        assert "api_endpoint" in remote[0]
        assert "mcp_endpoint" in remote[0]


def test_network_search_short_query_rejected(client):
    r = client.get("/api/v1/network/search", params={"q": "a"})
    assert r.status_code == 400


# ── Nodes ──


def test_list_nodes(client):
    client.post("/api/v1/register", json=_NODE_PAYLOAD)

    r = client.get("/api/v1/network/nodes")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["nodes"][0]["endpoint"] == "http://localhost:8420"


# ── Stats ──


def test_network_stats(client):
    client.post("/api/v1/register", json=_NODE_PAYLOAD)

    r = client.get("/api/v1/network/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["remote_corpora"] == 2
    assert body["nodes_total"] >= 1
    assert "version" in body


# ── Health endpoint includes network info ──


def test_health_includes_network_info(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "network_nodes" in body
    assert "network_corpora" in body


# ── Cron health check ──


def test_cron_health_check_empty(client):
    r = client.get("/api/v1/cron/health-check")
    assert r.status_code == 200
    assert r.json()["checked"] == 0


def test_cron_health_check_with_nodes(client):
    client.post("/api/v1/register", json=_NODE_PAYLOAD)
    r = client.get("/api/v1/cron/health-check")
    assert r.status_code == 200
    assert r.json()["checked"] == 1


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

    r = client.get("/api/v1/network/nodes")
    assert r.json()["count"] == 2

    r = client.get("/api/v1/network/stats")
    assert r.json()["remote_corpora"] == 3
