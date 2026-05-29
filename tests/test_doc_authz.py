"""Document write-authorization regression tests.

A logged-in non-owner must not be able to edit or delete another user's
document — neither through the document's own corpus URL (blocked by
`_require_owner`) nor by pointing the doc id at a corpus the attacker
controls (the cross-corpus IDOR closed by `_resolve_doc_in_corpus`).

Calls the route handlers directly with fake requests while forcing cloud
mode, because the JWT auth middleware is only wired at import time.
"""

import asyncio

import pytest
from fastapi import HTTPException

import noosphere.api.routes as routes
from noosphere.api.routes import (
    api_get_document,
    api_update_document,
    api_delete_document,
    UpdateDocumentRequest,
)
from noosphere.core.corpus import create_corpus
from noosphere.core.ingest import ingest_text, get_document


class FakeClient:
    # Non-localhost so _is_owner_request can't shortcut to True.
    host = "203.0.113.7"


class FakeRequest:
    def __init__(self, user_id=None, agent=True):
        self.client = FakeClient()
        self.state = type("S", (), {})()
        if user_id is not None:
            self.state.user_id = user_id
        # x-agent-id forces _is_owner_request -> False (simulates a real
        # remote browser that is NOT the localhost operator).
        self.headers = {"x-agent-id": "probe"} if agent else {}
        self.url = type("U", (), {"path": "/probe"})()

    # _check_corpus_access / _extract_bearer may read these
    def __getattr__(self, name):
        return None


@pytest.fixture
def cloud(monkeypatch):
    monkeypatch.setattr(routes, "_is_cloud", lambda: True)
    yield


def _mk_corpus_with_doc(owner_id, title="Victim Doc"):
    c = create_corpus(name=f"Corpus of {owner_id}", owner_id=owner_id)
    doc = ingest_text(c["id"], title=title, content="original body", source_kind="user_original")
    return c, doc


def test_nonowner_cannot_edit_doc_cloud(cloud):
    """User B PATCHes user A's doc via the doc's own corpus URL."""
    cA, docA = _mk_corpus_with_doc("userA")
    reqB = FakeRequest(user_id="userB")
    body = UpdateDocumentRequest(title="HACKED BY B")
    raised = None
    try:
        asyncio.run(api_update_document(cA["id"], docA["id"], body, reqB))
    except HTTPException as e:
        raised = e
    after = get_document(docA["id"])
    print(f"\n[edit-same-corpus] raised={raised.status_code if raised else None} title_now={after['title']!r}")
    assert raised is not None and raised.status_code == 403, (
        f"VULN: non-owner edit succeeded, title is now {after['title']!r}"
    )


def test_nonowner_cannot_delete_doc_cloud(cloud):
    cA, docA = _mk_corpus_with_doc("userA")
    reqB = FakeRequest(user_id="userB")
    raised = None
    try:
        asyncio.run(api_delete_document(cA["id"], docA["id"], reqB))
    except HTTPException as e:
        raised = e
    still = get_document(docA["id"])
    print(f"\n[delete] raised={raised.status_code if raised else None} doc_exists={still is not None}")
    assert raised is not None and raised.status_code == 403, "VULN: non-owner delete succeeded"


def test_cross_corpus_idor_edit(cloud):
    """User B owns corpus B. User B PATCHes /corpora/{B}/documents/{docA}
    where docA actually belongs to user A's corpus A. _require_owner only
    checks corpus B (which B owns); the doc-in-corpus guard must reject."""
    cA, docA = _mk_corpus_with_doc("userA", title="A's private doc")
    cB = create_corpus(name="B's corpus", owner_id="userB")
    reqB = FakeRequest(user_id="userB")
    body = UpdateDocumentRequest(title="HACKED CROSS-CORPUS")
    raised = None
    try:
        asyncio.run(api_update_document(cB["id"], docA["id"], body, reqB))
    except HTTPException as e:
        raised = e
    after = get_document(docA["id"])
    print(f"\n[cross-corpus] raised={raised.status_code if raised else None} A_doc_title_now={after['title']!r}")
    assert raised is not None and raised.status_code == 404, "VULN: cross-corpus edit not rejected"
    assert after["title"] == "A's private doc", (
        f"VULN: cross-corpus edit changed A's doc to {after['title']!r}"
    )


def test_cross_corpus_idor_read(cloud):
    """A's doc must not be readable via B's corpus URL even if B's corpus
    is public — the doc-in-corpus guard 404s instead of leaking content."""
    cA, docA = _mk_corpus_with_doc("userA", title="A's private doc")
    cB = create_corpus(name="B's corpus", owner_id="userB", access_level="public")
    reqB = FakeRequest(user_id="userB")
    raised = None
    try:
        asyncio.run(api_get_document(cB["id"], docA["id"], reqB))
    except HTTPException as e:
        raised = e
    print(f"\n[cross-corpus-read] raised={raised.status_code if raised else None}")
    assert raised is not None and raised.status_code == 404, "VULN: cross-corpus read leaked A's doc"


def test_owner_can_still_edit_own_doc(cloud):
    """Guard against over-blocking: the real owner edits through the proper URL."""
    cA, docA = _mk_corpus_with_doc("userA", title="mine")
    reqA = FakeRequest(user_id="userA")
    body = UpdateDocumentRequest(title="mine, edited")
    asyncio.run(api_update_document(cA["id"], docA["id"], body, reqA))
    assert get_document(docA["id"])["title"] == "mine, edited"
