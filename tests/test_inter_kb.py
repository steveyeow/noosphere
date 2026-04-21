"""Tests for M5 — inter-KB direct query attribution.

Verifies that when an agent sets `X-Noosphere-Caller-Corpus` on a successful
`ask` call, a `query`-kind citation is auto-recorded (with 24h dedupe) and the
cited KB's `kb_reputation` refreshes.
"""

from datetime import datetime, timedelta, timezone

import pytest

from noosphere.core.citations import (
    KIND_QUERY,
    citation_count_in,
    citations_in,
    record_inter_kb_query,
)
from noosphere.core.corpus import create_corpus, get_corpus
from noosphere.core.db import get_conn


@pytest.fixture
def stub_llm(monkeypatch):
    holder = {"text": "Synthesized answer [1]."}
    monkeypatch.setattr("noosphere.core.kb_agent._call_llm", lambda m: holder["text"])
    return holder


@pytest.fixture
def stub_search(monkeypatch):
    holder = {"chunks": []}
    monkeypatch.setattr(
        "noosphere.core.kb_agent.search_corpus",
        lambda cid, q, **kw: {"results": holder["chunks"], "usage": {}},
    )
    return holder


def _chunk(title: str, text: str, *, score: float = 0.7, doc_id: str = "d1") -> dict:
    return {
        "chunk_id": "c1", "score": score, "text": text,
        "citation": {"document_title": title, "document_id": doc_id, "date": ""},
    }


# ── record_inter_kb_query core ─────────────────────────────────────


def test_record_inter_kb_query_creates_edge_and_refreshes_kbr():
    a = create_corpus("A")
    b = create_corpus("B")
    # Give A some reputation so the edge contributes weight
    get_conn().execute("UPDATE corpora SET kb_reputation=? WHERE id=?", (0.5, a["id"]))
    get_conn().commit()

    assert record_inter_kb_query(a["id"], b["id"], context="test") is True
    assert citation_count_in(b["id"], kind=KIND_QUERY) == 1
    # B's kb_reputation should refresh from 0 to something > 0
    assert get_corpus(b["id"])["kb_reputation"] > 0


def test_record_inter_kb_query_dedupes_within_24h():
    a = create_corpus("A")
    b = create_corpus("B")
    assert record_inter_kb_query(a["id"], b["id"]) is True
    # Second immediate call should dedupe
    assert record_inter_kb_query(a["id"], b["id"]) is False
    assert citation_count_in(b["id"], kind=KIND_QUERY) == 1


def test_record_inter_kb_query_rejects_self_attribution():
    a = create_corpus("A")
    assert record_inter_kb_query(a["id"], a["id"]) is False


def test_record_inter_kb_query_outside_24h_window_records_again():
    a = create_corpus("A")
    b = create_corpus("B")
    record_inter_kb_query(a["id"], b["id"])
    # Shift the first edge back by 25 hours
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    get_conn().execute(
        "UPDATE corpus_citations SET created_at=? WHERE citing_corpus_id=? AND cited_corpus_id=?",
        (old, a["id"], b["id"]),
    )
    get_conn().commit()
    assert record_inter_kb_query(a["id"], b["id"]) is True
    assert citation_count_in(b["id"], kind=KIND_QUERY) == 2


# ── REST ask with caller-corpus header ─────────────────────────────


def test_ask_with_caller_corpus_records_citation(client, stub_llm, stub_search):
    r_a = client.post("/api/v1/corpora", json={"name": "Caller KB"})
    r_b = client.post("/api/v1/corpora", json={"name": "Target KB"})
    a_id = r_a.json()["id"]
    b_id = r_b.json()["id"]

    stub_search["chunks"] = [_chunk("doc", "body", score=0.8)]
    stub_llm["text"] = "Answer [1]."

    r = client.post(
        f"/api/v1/corpora/{b_id}/ask",
        json={"question": "hello?"},
        headers={"X-Noosphere-Caller-Corpus": a_id},
    )
    assert r.status_code == 200
    assert citation_count_in(b_id, kind=KIND_QUERY) == 1
    edge = citations_in(b_id, kind=KIND_QUERY)[0]
    assert edge["citing_corpus_id"] == a_id


def test_ask_without_caller_corpus_does_not_record(client, stub_llm, stub_search):
    r_b = client.post("/api/v1/corpora", json={"name": "No Attr Target"})
    b_id = r_b.json()["id"]
    stub_search["chunks"] = [_chunk("doc", "body", score=0.8)]
    stub_llm["text"] = "x"
    client.post(f"/api/v1/corpora/{b_id}/ask", json={"question": "q"})
    assert citation_count_in(b_id, kind=KIND_QUERY) == 0


def test_ask_with_unknown_caller_corpus_is_ignored(client, stub_llm, stub_search):
    r_b = client.post("/api/v1/corpora", json={"name": "Target Unk"})
    b_id = r_b.json()["id"]
    stub_search["chunks"] = [_chunk("doc", "body", score=0.8)]
    stub_llm["text"] = "x"
    r = client.post(
        f"/api/v1/corpora/{b_id}/ask",
        json={"question": "q"},
        headers={"X-Noosphere-Caller-Corpus": "nonexistent000"},
    )
    assert r.status_code == 200
    assert citation_count_in(b_id, kind=KIND_QUERY) == 0


def test_ask_out_of_scope_does_not_record_citation(client, stub_llm, stub_search):
    r_a = client.post("/api/v1/corpora", json={"name": "OOS Caller"})
    r_b = client.post("/api/v1/corpora", json={"name": "OOS Target"})
    a_id = r_a.json()["id"]
    b_id = r_b.json()["id"]
    stub_search["chunks"] = []  # no results → out_of_scope
    r = client.post(
        f"/api/v1/corpora/{b_id}/ask",
        json={"question": "q"},
        headers={"X-Noosphere-Caller-Corpus": a_id},
    )
    assert r.status_code == 200
    assert r.json()["out_of_scope"] is True
    assert citation_count_in(b_id, kind=KIND_QUERY) == 0


def test_ask_with_self_caller_does_not_record(client, stub_llm, stub_search):
    r = client.post("/api/v1/corpora", json={"name": "Self Ref"})
    cid = r.json()["id"]
    stub_search["chunks"] = [_chunk("doc", "body", score=0.8)]
    stub_llm["text"] = "x"
    client.post(
        f"/api/v1/corpora/{cid}/ask",
        json={"question": "q"},
        headers={"X-Noosphere-Caller-Corpus": cid},
    )
    assert citation_count_in(cid, kind=KIND_QUERY) == 0


def test_repeated_inter_kb_queries_dedupe_within_24h(client, stub_llm, stub_search):
    r_a = client.post("/api/v1/corpora", json={"name": "Repeat A"})
    r_b = client.post("/api/v1/corpora", json={"name": "Repeat B"})
    a_id = r_a.json()["id"]
    b_id = r_b.json()["id"]
    stub_search["chunks"] = [_chunk("doc", "body", score=0.8)]
    stub_llm["text"] = "x"
    headers = {"X-Noosphere-Caller-Corpus": a_id}
    for _ in range(5):
        client.post(f"/api/v1/corpora/{b_id}/ask", json={"question": "q"}, headers=headers)
    assert citation_count_in(b_id, kind=KIND_QUERY) == 1


# ── MCP ask honors caller-corpus attribution ───────────────────────


def test_mcp_ask_with_caller_corpus_records_citation(stub_llm, stub_search):
    from noosphere.mcp.server import handle_tool_call
    a = create_corpus("MCP Caller")
    b = create_corpus("MCP Target")
    stub_search["chunks"] = [_chunk("doc", "body", score=0.8)]
    stub_llm["text"] = "Answer [1]."
    result = handle_tool_call(
        "ask", {"corpus_id": b["id"], "question": "q"},
        caller_corpus_id=a["id"],
    )
    assert result.get("chunks_used") == 1
    assert citation_count_in(b["id"], kind=KIND_QUERY) == 1


def test_mcp_ask_without_caller_corpus_does_not_record(stub_llm, stub_search):
    from noosphere.mcp.server import handle_tool_call
    b = create_corpus("MCP NoAttr")
    stub_search["chunks"] = [_chunk("doc", "body", score=0.8)]
    stub_llm["text"] = "x"
    handle_tool_call("ask", {"corpus_id": b["id"], "question": "q"})
    assert citation_count_in(b["id"], kind=KIND_QUERY) == 0
