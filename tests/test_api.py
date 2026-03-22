"""REST API integration tests (FastAPI TestClient)."""

import io
import zipfile

import pytest

_CORPUS_JSON = {
    "name": "API Test Corpus",
    "description": "integration",
    "author_name": "Tester",
    "tags": ["api", "test"],
    "access_level": "public",
    "language": "en",
}


@pytest.fixture
def corpus(client):
    r = client.post("/api/v1/corpora", json=_CORPUS_JSON)
    assert r.status_code == 200
    return r.json()


def test_get_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert body["corpus_count"] == 0
    assert "registry_connected" in body


def test_post_corpora_create(client):
    r = client.post(
        "/api/v1/corpora",
        json={**_CORPUS_JSON, "name": "Created Corpus", "description": "new"},
    )
    assert r.status_code == 200
    created = r.json()
    assert created["name"] == "Created Corpus"
    assert created["description"] == "new"
    assert created["access_level"] == "public"
    assert "id" in created
    assert created["slug"]


def test_get_corpora_list(client, corpus):
    r = client.get("/api/v1/corpora")
    assert r.status_code == 200
    listed = r.json()
    assert any(c["id"] == corpus["id"] for c in listed)


def test_get_corpus_by_id(client, corpus):
    cid = corpus["id"]
    r = client.get(f"/api/v1/corpora/{cid}")
    assert r.status_code == 200
    assert r.json()["id"] == cid
    assert r.json()["name"] == corpus["name"]


def test_get_corpus_by_slug(client, corpus):
    slug = corpus["slug"]
    r = client.get(f"/api/v1/corpora/{slug}")
    assert r.status_code == 200
    assert r.json()["id"] == corpus["id"]
    assert r.json()["slug"] == slug


def test_get_corpus_not_found(client):
    r = client.get("/api/v1/corpora/nonexistent-id-xyz")
    assert r.status_code == 404
    assert r.json()["detail"] == "Corpus not found"


def test_patch_corpora(client, corpus):
    cid = corpus["id"]
    r = client.patch(
        f"/api/v1/corpora/{cid}",
        json={"name": "Renamed", "description": "patched"},
    )
    assert r.status_code == 200
    updated = r.json()
    assert updated["name"] == "Renamed"
    assert updated["description"] == "patched"


def test_patch_corpora_no_fields_returns_400(client, corpus):
    cid = corpus["id"]
    r = client.patch(f"/api/v1/corpora/{cid}", json={})
    assert r.status_code == 400
    assert r.json()["detail"] == "No fields to update"


def test_delete_corpora(client):
    r = client.post("/api/v1/corpora", json={**_CORPUS_JSON, "name": "To Delete"})
    assert r.status_code == 200
    cid = r.json()["id"]

    r = client.delete(f"/api/v1/corpora/{cid}")
    assert r.status_code == 200
    assert r.json() == {"status": "deleted"}

    r = client.get(f"/api/v1/corpora/{cid}")
    assert r.status_code == 404


def test_post_corpora_upload_md(client, corpus):
    cid = corpus["id"]
    md_bytes = b"# Title\n\nHello from **markdown**.\n"
    r = client.post(
        f"/api/v1/corpora/{cid}/upload",
        files=[("files", ("note.md", io.BytesIO(md_bytes), "text/markdown"))],
    )
    assert r.status_code == 200
    up = r.json()
    assert up["uploaded"] == 1
    assert len(up["documents"]) == 1
    assert up["documents"][0]["title"]


def test_post_corpora_tokens_create(client, corpus):
    cid = corpus["id"]
    r = client.post(
        f"/api/v1/corpora/{cid}/tokens",
        json={"label": "ci", "permissions": "read"},
    )
    assert r.status_code == 200
    tok = r.json()
    assert "token" in tok
    assert tok["id"]
    assert tok["corpus_id"] == cid

    lr = client.get(f"/api/v1/corpora/{cid}/tokens")
    rows = lr.json()
    assert len(rows) == 1
    assert rows[0]["id"] == tok["id"]
    assert "token" not in rows[0]


def test_get_corpora_tokens_list(client, corpus):
    cid = corpus["id"]
    tr = client.post(f"/api/v1/corpora/{cid}/tokens", json={"label": "list-me"})
    assert tr.status_code == 200
    token_id = tr.json()["id"]

    r = client.get(f"/api/v1/corpora/{cid}/tokens")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["id"] == token_id
    assert "token" not in rows[0]


def test_delete_corpora_tokens_revoke(client, corpus):
    cid = corpus["id"]
    tr = client.post(f"/api/v1/corpora/{cid}/tokens", json={"label": "revoke-me"})
    token_id = tr.json()["id"]

    r = client.delete(f"/api/v1/corpora/{cid}/tokens/{token_id}")
    assert r.status_code == 200
    assert r.json() == {"status": "revoked"}

    assert client.get(f"/api/v1/corpora/{cid}/tokens").json() == []


def test_get_corpora_export_returns_zip(client, corpus):
    cid = corpus["id"]
    md_bytes = b"# Export doc\n\nbody\n"
    client.post(
        f"/api/v1/corpora/{cid}/upload",
        files=[("files", ("page.md", io.BytesIO(md_bytes), "text/markdown"))],
    )

    r = client.get(f"/api/v1/corpora/{cid}/export")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/zip")
    assert "attachment" in r.headers.get("content-disposition", "").lower()
    buf = io.BytesIO(r.content)
    assert zipfile.is_zipfile(buf)
    with zipfile.ZipFile(buf, "r") as zf:
        assert any(n.endswith("noosphere.json") for n in zf.namelist())


def test_access_private_blocks_get_and_list(client):
    r = client.post("/api/v1/corpora", json={"name": "Secret", "access_level": "public"})
    cid = r.json()["id"]

    client.patch(f"/api/v1/corpora/{cid}", json={"access_level": "private"})

    r = client.get(f"/api/v1/corpora/{cid}")
    assert r.status_code == 403
    assert "private" in r.json()["detail"].lower()

    r = client.get("/api/v1/corpora")
    assert cid not in {c["id"] for c in r.json()}


def test_access_token_requires_bearer_header(client):
    r = client.post("/api/v1/corpora", json={"name": "Gated", "access_level": "public"})
    cid = r.json()["id"]

    tr = client.post(f"/api/v1/corpora/{cid}/tokens", json={"label": "key"})
    assert tr.status_code == 200
    raw_token = tr.json()["token"]

    client.patch(f"/api/v1/corpora/{cid}", json={"access_level": "token"})

    r = client.get(f"/api/v1/corpora/{cid}")
    assert r.status_code == 401
    assert "token" in r.json()["detail"].lower()

    r = client.get(
        f"/api/v1/corpora/{cid}",
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert r.status_code == 200
    assert r.json()["id"] == cid

    r = client.get(
        f"/api/v1/corpora/{cid}",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert r.status_code == 401
