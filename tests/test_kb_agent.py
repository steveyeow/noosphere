"""Tests for the KB-as-agent L0 interface: ask, describe, probe."""

import pytest

from noosphere.core.corpus import create_corpus, update_corpus
from noosphere.core.kb_agent import (
    PREVIEW_ASK_TRUNCATE_CHARS,
    ask,
    describe,
    preview_ask,
)


@pytest.fixture
def stub_llm(monkeypatch):
    """Return whatever text the caller sets via the returned holder."""
    holder = {"text": "Default answer referencing [1] and [2]."}

    def _fake(messages):
        return holder["text"]

    monkeypatch.setattr("noosphere.core.kb_agent._call_llm", _fake)
    return holder


@pytest.fixture
def stub_search(monkeypatch):
    """Stub search_corpus so kb_agent tests don't need real indexing.

    The holder's `chunks` field controls what the retrieval returns.
    """
    holder = {"chunks": []}

    def _fake(corpus_id, query, **kw):
        return {"results": holder["chunks"], "usage": {}}

    monkeypatch.setattr("noosphere.core.kb_agent.search_corpus", _fake)
    return holder


def _chunk(title: str, text: str, *, score: float = 0.5, doc_id: str = "doc-1", date: str = "") -> dict:
    return {
        "chunk_id": "c1",
        "score": score,
        "text": text,
        "citation": {
            "document_title": title,
            "document_id": doc_id,
            "date": date,
        },
    }


# ── describe ───────────────────────────────────────────────────────


def test_describe_unknown_corpus_returns_none():
    assert describe("nonexistent000") is None


def test_describe_returns_capability_card():
    c = create_corpus("Chef", description="Chinese cuisine", author_name="Steve", tags=["food"])
    update_corpus(
        c["id"],
        task_types=["advice", "synthesis"],
        samples=[{"question": "Stir-fry?", "answer_preview": "Wok high heat"}],
        autonomy_level=1,
        calibration_policy={"reports_confidence": True, "confidence_source": "self"},
        license_terms={"query": "pay-per-query"},
    )
    card = describe(c["id"])
    assert card is not None
    assert card["corpus_id"] == c["id"]
    assert card["name"] == "Chef"
    assert card["description"] == "Chinese cuisine"
    assert card["author"]["name"] == "Steve"
    assert card["task_types"] == ["advice", "synthesis"]
    assert card["samples"][0]["question"] == "Stir-fry?"
    assert card["autonomy_level"] == 1
    assert card["calibration_policy"]["reports_confidence"] is True
    assert card["license_terms"]["query"] == "pay-per-query"
    # source_composition is computed — empty corpus has no docs
    assert card["source_composition"] == {}
    assert "quality" in card
    assert card["quality"]["document_count"] == 0


# ── ask ────────────────────────────────────────────────────────────


def test_ask_unknown_corpus_returns_none(stub_llm, stub_search):
    assert ask("nonexistent000", "hi") is None


def test_ask_no_chunks_marks_out_of_scope(stub_llm, stub_search):
    c = create_corpus("Empty")
    stub_search["chunks"] = []
    result = ask(c["id"], "anything")
    assert result["out_of_scope"] is True
    assert result["chunks_used"] == 0
    assert result["citations"] == []
    assert result["confidence"] == "low"


def test_ask_returns_numbered_citations(stub_llm, stub_search):
    c = create_corpus("Cooking")
    stub_search["chunks"] = [
        _chunk("Wok Basics", "Use high heat.", score=0.8, doc_id="d1"),
        _chunk("Oil Choices", "Peanut oil for smoke point.", score=0.6, doc_id="d2", date="2024-01-02"),
    ]
    stub_llm["text"] = "Start with high heat [1] and pick oil carefully [2]."
    result = ask(c["id"], "How to stir-fry?")
    assert result["out_of_scope"] is False
    assert result["chunks_used"] == 2
    assert result["answer"] == "Start with high heat [1] and pick oil carefully [2]."
    assert [cite["index"] for cite in result["citations"]] == [1, 2]
    assert result["citations"][0]["title"] == "Wok Basics"
    assert result["citations"][0]["document_id"] == "d1"
    assert result["citations"][1]["date"] == "2024-01-02"


def test_ask_confidence_from_top_score(stub_llm, stub_search):
    c = create_corpus("Confidence")
    stub_search["chunks"] = [_chunk("t", "body", score=0.9)]
    assert ask(c["id"], "q")["confidence"] == "high"
    stub_search["chunks"] = [_chunk("t", "body", score=0.5)]
    assert ask(c["id"], "q")["confidence"] == "medium"
    stub_search["chunks"] = [_chunk("t", "body", score=0.2)]
    assert ask(c["id"], "q")["confidence"] == "low"


def test_ask_capability_context_includes_source_composition(stub_llm, stub_search):
    c = create_corpus("Ctx")
    stub_search["chunks"] = [_chunk("t", "body", score=0.9)]
    result = ask(c["id"], "q")
    ctx = result["capability_context"]
    assert ctx["corpus_id"] == c["id"]
    assert ctx["corpus_name"] == "Ctx"
    assert "source_composition" in ctx
    assert "autonomy_level" in ctx
    assert ctx["calibration_reported"] is False


# ── preview_ask ────────────────────────────────────────────────────


def test_preview_ask_unknown_corpus_returns_none(stub_llm, stub_search):
    assert preview_ask("nonexistent000", "hi") is None


def test_preview_ask_truncates_long_answers(stub_llm, stub_search):
    c = create_corpus("Long")
    stub_search["chunks"] = [_chunk("t", "body", score=0.9)]
    stub_llm["text"] = "x" * (PREVIEW_ASK_TRUNCATE_CHARS + 100)
    result = preview_ask(c["id"], "q")
    assert result["truncated"] is True
    assert len(result["answer"]) == PREVIEW_ASK_TRUNCATE_CHARS
    assert result["answer"].endswith("...")
    assert "note" in result


def test_preview_ask_short_answer_not_truncated(stub_llm, stub_search):
    c = create_corpus("Short")
    stub_search["chunks"] = [_chunk("t", "body", score=0.9)]
    stub_llm["text"] = "Short answer."
    result = preview_ask(c["id"], "q")
    assert result["truncated"] is False
    assert result["answer"] == "Short answer."


# ── REST endpoints ─────────────────────────────────────────────────


def test_api_describe_returns_capability_card(client):
    r = client.post("/api/v1/corpora", json={"name": "ApiDesc", "description": "x"})
    corpus_id = r.json()["id"]
    update_corpus(corpus_id, task_types=["advice"], autonomy_level=2)
    r = client.get(f"/api/v1/corpora/{corpus_id}/describe")
    assert r.status_code == 200
    body = r.json()
    assert body["corpus_id"] == corpus_id
    assert body["task_types"] == ["advice"]
    assert body["autonomy_level"] == 2
    assert "source_composition" in body


def test_api_describe_404_for_unknown(client):
    r = client.get("/api/v1/corpora/nonexistent000/describe")
    assert r.status_code == 404


def test_api_preview_ask_public_works_without_auth(client, stub_llm, stub_search):
    r = client.post("/api/v1/corpora", json={"name": "PA Pub", "description": "x"})
    corpus_id = r.json()["id"]
    stub_search["chunks"] = [_chunk("t", "body", score=0.7)]
    stub_llm["text"] = "Evaluation answer."
    r = client.post(f"/api/v1/corpora/{corpus_id}/preview-ask", json={"question": "hello?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Evaluation answer."
    assert "note" in body


def test_api_preview_ask_403_on_private(client, stub_llm, stub_search):
    r = client.post("/api/v1/corpora", json={"name": "PA Priv", "access_level": "private"})
    corpus_id = r.json()["id"]
    r = client.post(f"/api/v1/corpora/{corpus_id}/preview-ask", json={"question": "hi"})
    assert r.status_code == 403


def test_api_ask_on_public_returns_answer(client, stub_llm, stub_search):
    r = client.post("/api/v1/corpora", json={"name": "Ask Pub"})
    corpus_id = r.json()["id"]
    stub_search["chunks"] = [_chunk("t", "body", score=0.9)]
    stub_llm["text"] = "Answer referring to [1]."
    r = client.post(f"/api/v1/corpora/{corpus_id}/ask", json={"question": "?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Answer referring to [1]."
    assert body["citations"][0]["index"] == 1


# ── MCP handlers ───────────────────────────────────────────────────


def test_mcp_describe_returns_capability_card():
    from noosphere.mcp.server import handle_tool_call
    c = create_corpus("MCP Desc")
    update_corpus(c["id"], task_types=["advice"])
    result = handle_tool_call("describe", {"corpus_id": c["id"]})
    assert result["corpus_id"] == c["id"]
    assert result["task_types"] == ["advice"]


def test_mcp_preview_ask_on_public(stub_llm, stub_search):
    from noosphere.mcp.server import handle_tool_call
    c = create_corpus("MCP PA")
    stub_search["chunks"] = [_chunk("t", "body", score=0.8)]
    stub_llm["text"] = "x"
    result = handle_tool_call("preview_ask", {"corpus_id": c["id"], "question": "q"})
    assert "answer" in result
    assert "note" in result


def test_mcp_preview_ask_blocked_on_private():
    from noosphere.mcp.server import handle_tool_call
    c = create_corpus("MCP Priv", access_level="private")
    result = handle_tool_call("preview_ask", {"corpus_id": c["id"], "question": "q"})
    assert "error" in result
    assert "Private" in result["error"]


def test_mcp_tools_list_includes_new():
    from noosphere.mcp.server import TOOLS
    names = {t["name"] for t in TOOLS}
    assert {"ask", "describe", "preview_ask"}.issubset(names)
