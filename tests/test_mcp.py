"""MCP HTTP endpoint integration tests (JSON-RPC over POST /mcp)."""

import json


def _rpc(body: dict) -> dict:
    return {"jsonrpc": "2.0", "id": 42, **body}


def test_get_mcp_returns_manifest(client):
    r = client.get("/mcp")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "noosphere"
    assert "tools" in data
    names = {t["name"] for t in data["tools"]}
    assert "list_corpora" in names
    assert "get_manifest" in names


def test_post_mcp_initialize(client):
    r = client.post("/mcp", json=_rpc({"method": "initialize", "params": {}}))
    assert r.status_code == 200
    data = r.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 42
    assert "result" in data
    assert data["result"]["protocolVersion"] == "2024-11-05"
    assert data["result"]["serverInfo"]["name"] == "noosphere"


def test_post_mcp_tools_list(client):
    r = client.post("/mcp", json=_rpc({"method": "tools/list", "params": {}}))
    assert r.status_code == 200
    data = r.json()
    assert "result" in data
    tools = data["result"]["tools"]
    assert isinstance(tools, list)
    assert any(t["name"] == "list_corpora" for t in tools)


def test_post_mcp_tools_call_list_corpora(client):
    r = client.post(
        "/mcp",
        json=_rpc(
            {
                "method": "tools/call",
                "params": {"name": "list_corpora", "arguments": {}},
            }
        ),
    )
    assert r.status_code == 200
    data = r.json()
    assert "result" in data
    text = data["result"]["content"][0]["text"]
    payload = json.loads(text)
    assert "corpora" in payload
    assert payload["corpora"] == []

    client.post("/api/v1/corpora", json={"name": "MCP Listed"})
    r = client.post(
        "/mcp",
        json=_rpc(
            {
                "method": "tools/call",
                "params": {"name": "list_corpora", "arguments": {}},
            }
        ),
    )
    payload = json.loads(r.json()["result"]["content"][0]["text"])
    assert len(payload["corpora"]) == 1
    assert payload["corpora"][0]["name"] == "MCP Listed"


def test_post_mcp_tools_call_get_manifest(client):
    cr = client.post("/api/v1/corpora", json={"name": "Manifest Me"})
    cid = cr.json()["id"]

    r = client.post(
        "/mcp",
        json=_rpc(
            {
                "method": "tools/call",
                "params": {
                    "name": "get_manifest",
                    "arguments": {"corpus_id": cid},
                },
            }
        ),
    )
    assert r.status_code == 200
    data = r.json()
    text = data["result"]["content"][0]["text"]
    manifest = json.loads(text)
    assert manifest["id"] == cid
    assert manifest["name"] == "Manifest Me"


def test_mcp_tools_call_get_manifest_with_authorization_bearer(client):
    """Token-gated corpus: ``Authorization: Bearer`` is accepted (same as REST)."""
    cr = client.post(
        "/api/v1/corpora",
        json={"name": "MCP Bearer Header", "access_level": "public"},
    )
    cid = cr.json()["id"]
    tr = client.post(f"/api/v1/corpora/{cid}/tokens", json={"label": "mcp-bearer"})
    raw = tr.json()["token"]
    client.patch(f"/api/v1/corpora/{cid}", json={"access_level": "token"})

    r = client.post(
        "/mcp",
        json=_rpc(
            {
                "method": "tools/call",
                "params": {"name": "get_manifest", "arguments": {"corpus_id": cid}},
            }
        ),
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert r.status_code == 200
    assert "result" in r.json()
    manifest = json.loads(r.json()["result"]["content"][0]["text"])
    assert manifest["id"] == cid


def test_mcp_get_manifest_with_access_token_in_arguments(client):
    """Token-gated corpus: tools/call can pass the secret via ``access_token``."""

    cr = client.post("/api/v1/corpora", json={"name": "MCP Token Arg", "access_level": "public"})
    cid = cr.json()["id"]
    tr = client.post(f"/api/v1/corpora/{cid}/tokens", json={"label": "mcp-arg"})
    raw = tr.json()["token"]
    client.patch(f"/api/v1/corpora/{cid}", json={"access_level": "token"})

    r = client.post(
        "/mcp",
        json=_rpc(
            {
                "method": "tools/call",
                "params": {
                    "name": "get_manifest",
                    "arguments": {"corpus_id": cid, "access_token": raw},
                },
            }
        ),
    )
    assert r.status_code == 200
    data = r.json()
    assert "result" in data
    manifest = json.loads(data["result"]["content"][0]["text"])
    assert manifest["id"] == cid


def test_mcp_access_denied_for_private_corpus(client):
    cr = client.post(
        "/api/v1/corpora",
        json={"name": "Private MCP", "access_level": "public"},
    )
    cid = cr.json()["id"]
    client.patch(f"/api/v1/corpora/{cid}", json={"access_level": "private"})

    r = client.post(
        "/mcp",
        json=_rpc(
            {
                "method": "tools/call",
                "params": {
                    "name": "get_manifest",
                    "arguments": {"corpus_id": cid},
                },
            }
        ),
    )
    assert r.status_code == 200
    data = r.json()
    assert "error" in data
    assert data["error"]["code"] == -32603
    assert "private" in data["error"]["message"].lower()
