"""Tests for manifest auto-fill (LLM → capability card)."""

import json

import pytest

from noosphere.core.corpus import create_corpus, get_corpus, update_corpus
from noosphere.core.ingest import ingest_text
from noosphere.core.manifest_autofill import (
    _normalize_proposal,
    _parse_proposal,
    apply_proposal,
    autofill_if_empty,
    suggest_manifest,
)


@pytest.fixture
def stub_llm(monkeypatch):
    """Deterministic LLM that returns whatever the holder's `response` is set to."""
    holder = {
        "response": json.dumps({
            "task_types": ["advice", "synthesis"],
            "samples": [
                {"question": "How do I stir-fry a wok?", "answer_preview": "Use high heat and peanut oil."},
                {"question": "What's the ratio for soy sauce?", "answer_preview": "1:3 with water for light use."},
            ],
            "description_suggestion": "Chinese cooking techniques and ingredient ratios.",
        }),
        "calls": [],
    }

    def _fake(messages):
        holder["calls"].append(messages)
        return holder["response"]

    monkeypatch.setattr("noosphere.core.manifest_autofill.call_llm", _fake)
    return holder


# ── Parser edge cases ──────────────────────────────────────────────


def test_parse_proposal_plain_json():
    out = _parse_proposal('{"task_types": ["advice"]}')
    assert out["task_types"] == ["advice"]


def test_parse_proposal_strips_markdown_fences():
    raw = '```json\n{"task_types": ["advice"]}\n```'
    assert _parse_proposal(raw)["task_types"] == ["advice"]


def test_parse_proposal_trims_trailing_prose():
    raw = 'Here is the JSON:\n{"task_types": ["advice"]}\nLet me know.'
    assert _parse_proposal(raw)["task_types"] == ["advice"]


def test_parse_proposal_invalid_raises():
    with pytest.raises(json.JSONDecodeError):
        _parse_proposal("not json at all")


# ── Normalization ──────────────────────────────────────────────────


def test_normalize_clamps_task_types_to_valid_enum():
    corpus = create_corpus("Norm")
    proposal = {
        "task_types": ["advice", "garbage", "synthesis", "also-garbage", "retrieval", "comparison", "extra"],
        "samples": [],
        "description_suggestion": "",
    }
    out = _normalize_proposal(proposal, corpus)
    # Invalid ones dropped, capped at 4
    assert out["task_types"] == ["advice", "synthesis", "retrieval", "comparison"]


def test_normalize_clamps_samples_to_three():
    corpus = create_corpus("Norm2")
    proposal = {
        "task_types": [],
        "samples": [
            {"question": f"Q{i}?", "answer_preview": f"A{i}."} for i in range(8)
        ],
        "description_suggestion": "",
    }
    out = _normalize_proposal(proposal, corpus)
    assert len(out["samples"]) == 3


def test_normalize_drops_incomplete_samples():
    corpus = create_corpus("Norm3")
    proposal = {
        "task_types": [],
        "samples": [
            {"question": "valid?", "answer_preview": "yes"},
            {"question": "", "answer_preview": "no q"},
            {"question": "no answer", "answer_preview": ""},
            "not a dict",
        ],
        "description_suggestion": "",
    }
    out = _normalize_proposal(proposal, corpus)
    assert out["samples"] == [{"question": "valid?", "answer_preview": "yes"}]


def test_normalize_rejects_non_dict_proposal():
    corpus = create_corpus("Norm4")
    with pytest.raises(ValueError):
        _normalize_proposal(["not", "a", "dict"], corpus)


# ── End-to-end suggest ─────────────────────────────────────────────


def test_suggest_manifest_returns_none_for_empty_corpus(stub_llm):
    c = create_corpus("Empty")
    assert suggest_manifest(c["id"]) is None
    assert stub_llm["calls"] == []  # no LLM call needed


def test_suggest_manifest_returns_none_for_unknown_corpus(stub_llm):
    assert suggest_manifest("nonexistent000") is None


def test_suggest_manifest_produces_structured_proposal(stub_llm):
    c = create_corpus("Chef", description="cuisine", tags=["food"])
    ingest_text(c["id"], title="Wok basics", content="Use very high heat for stir-fry.")
    ingest_text(c["id"], title="Sauce ratios", content="Soy sauce 1:3 with water.")

    proposal = suggest_manifest(c["id"])
    assert proposal is not None
    assert proposal["task_types"] == ["advice", "synthesis"]
    assert len(proposal["samples"]) == 2
    assert proposal["description_suggestion"].startswith("Chinese")
    # LLM was actually called
    assert len(stub_llm["calls"]) == 1


def test_suggest_manifest_handles_llm_garbage(stub_llm):
    c = create_corpus("Garbage")
    ingest_text(c["id"], title="D", content="body")
    stub_llm["response"] = "totally not JSON, model malfunctioned"
    assert suggest_manifest(c["id"]) is None


# ── apply_proposal ─────────────────────────────────────────────────


def test_apply_proposal_writes_task_types_and_samples():
    c = create_corpus("Apply")
    proposal = {
        "task_types": ["advice"],
        "samples": [{"question": "q?", "answer_preview": "a."}],
        "description_suggestion": "new desc",
    }
    apply_proposal(c["id"], proposal)
    fetched = get_corpus(c["id"])
    assert fetched["task_types"] == ["advice"]
    assert fetched["samples"][0]["question"] == "q?"
    # description is NOT overwritten by default
    assert fetched["description"] != "new desc"


def test_apply_proposal_respects_refresh_description_flag():
    c = create_corpus("Apply2", description="old")
    proposal = {
        "task_types": [],
        "samples": [],
        "description_suggestion": "refreshed description",
    }
    apply_proposal(c["id"], proposal, refresh_description=True)
    fetched = get_corpus(c["id"])
    assert fetched["description"] == "refreshed description"


# ── autofill_if_empty (the post-ingest hook) ───────────────────────


def test_autofill_if_empty_skips_when_task_types_populated(stub_llm):
    c = create_corpus("Skip Me")
    update_corpus(c["id"], task_types=["advice"])
    ingest_text(c["id"], title="D", content="body")
    result = autofill_if_empty(c["id"])
    assert result is None
    assert stub_llm["calls"] == []  # never invoked LLM


def test_autofill_if_empty_fills_empty_manifest(stub_llm):
    c = create_corpus("Fill Me")
    ingest_text(c["id"], title="D", content="body content here")
    result = autofill_if_empty(c["id"])
    assert result is not None
    fetched = get_corpus(c["id"])
    assert fetched["task_types"] == ["advice", "synthesis"]
    assert len(fetched["samples"]) == 2


def test_autofill_if_empty_no_crash_when_llm_fails(stub_llm, monkeypatch):
    from noosphere.core.llm import LLMError

    def _fail(messages):
        raise LLMError("no provider available")

    monkeypatch.setattr("noosphere.core.manifest_autofill.call_llm", _fail)
    c = create_corpus("LLM Down")
    ingest_text(c["id"], title="D", content="body")
    # Must not raise; just returns None
    assert autofill_if_empty(c["id"]) is None


# ── REST endpoints ─────────────────────────────────────────────────


def test_api_manifest_suggest_returns_proposal(client, stub_llm):
    r = client.post("/api/v1/corpora", json={"name": "API Chef"})
    cid = r.json()["id"]
    ingest_text(cid, title="D", content="body")

    r = client.post(f"/api/v1/corpora/{cid}/manifest/suggest")
    assert r.status_code == 200
    body = r.json()
    assert "task_types" in body
    assert "samples" in body


def test_api_manifest_suggest_422_on_empty_corpus(client, stub_llm):
    r = client.post("/api/v1/corpora", json={"name": "API Empty"})
    cid = r.json()["id"]
    r = client.post(f"/api/v1/corpora/{cid}/manifest/suggest")
    assert r.status_code == 422


def test_api_manifest_apply_writes_fields(client, stub_llm):
    r = client.post("/api/v1/corpora", json={"name": "API Apply"})
    cid = r.json()["id"]

    r = client.post(
        f"/api/v1/corpora/{cid}/manifest/apply",
        json={
            "task_types": ["advice", "retrieval"],
            "samples": [{"question": "Q?", "answer_preview": "A."}],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["task_types"] == ["advice", "retrieval"]
    assert body["samples"][0]["question"] == "Q?"
