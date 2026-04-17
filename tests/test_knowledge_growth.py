"""Tests for knowledge growth (RSS, capture, health, compile, living concepts)."""

import json

import numpy as np
import pytest

from noosphere.core.corpus import create_corpus
from noosphere.core.indexer import index_corpus
from noosphere.core.ingest import get_document, ingest_text
from noosphere.core.knowledge_growth import (
    _append_to_matching_concept_timelines,
    _assemble_concept_content,
    _parse_concept_content,
    _parse_rss_atom,
    corpus_knowledge_health,
    get_concept_versions,
    recompile_concept_if_dirty,
    recompile_dirty_concepts,
    save_capture,
)


# ── Stubs for deterministic tests ──────────────────────────────────────

class _StubEmbedder:
    """Map known keywords to orthogonal 8-dim vectors so cosine is predictable."""

    TOPIC_KEYS = {
        "pmf": 0,
        "product-market": 0,
        "product market": 0,
        "auth": 1,
        "authentication": 1,
        "cooking": 2,
        "recipe": 2,
        "generic": 3,
    }

    def embed(self, texts):
        out = []
        for t in texts:
            v = np.zeros(8, dtype=np.float32)
            tl = (t or "").lower()
            for kw, idx in self.TOPIC_KEYS.items():
                if kw in tl:
                    v[idx] += 1.0
            if float(np.linalg.norm(v)) == 0:
                v[7] = 0.5  # weak default signal (~0 cosine against topic vectors)
            out.append(v)
        return np.array(out, dtype=np.float32)

    def dim(self):
        return 8

    def model_name(self):
        return "stub-embedder"


@pytest.fixture
def stub_embedder(monkeypatch):
    """Patch every module that holds a reference to get_embedder."""
    inst = _StubEmbedder()
    monkeypatch.setattr("noosphere.core.embeddings.get_embedder", lambda provider="": inst)
    monkeypatch.setattr("noosphere.core.indexer.get_embedder", lambda provider="": inst)
    monkeypatch.setattr("noosphere.core.retrieval.get_embedder", lambda provider="": inst)
    return inst


@pytest.fixture
def stub_llm(monkeypatch):
    """Replace _call_llm with a deterministic stub. Returns list of captured calls."""
    calls: list[list[dict]] = []

    def _fake(messages):
        calls.append(messages)
        return "# Refreshed synthesis\n\nTest recompiled body."

    monkeypatch.setattr("noosphere.core.llm.call_llm", _fake)
    return calls


def _make_concept_doc(corpus_id: str, title: str, topic_keyword: str) -> dict:
    """Ingest a living-concept doc with proper metadata for hook tests."""
    content = (
        f"Summary about {topic_keyword}.\n\n"
        f"Key ideas around {topic_keyword} and related concepts.\n\n"
        "## Timeline\n\n"
        "(no timeline entries yet)\n"
    )
    return ingest_text(
        corpus_id,
        title=title,
        content=content,
        doc_type="concept",
        metadata={
            "version": 1,
            "timeline_dirty": False,
            "pending_changes": 0,
            "compile_kind": "concept_note",
            "source_document_ids": [],
        },
    )


def test_parse_rss_basic():
    xml = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>Hello</title><link>https://example.com/a</link><guid>g1</guid></item>
<item><title>Two</title><link>https://example.com/b</link></item>
</channel></rss>"""
    items = _parse_rss_atom(xml)
    assert len(items) == 2
    assert items[0]["title"] == "Hello"
    assert items[0]["link"] == "https://example.com/a"
    assert items[0]["guid"] == "g1"


def test_parse_atom_basic():
    xml = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Atom Post</title>
    <id>urn:uuid:1</id>
    <link href="https://example.com/x"/>
    <summary>Short body</summary>
  </entry>
</feed>"""
    items = _parse_rss_atom(xml)
    assert len(items) == 1
    assert items[0]["title"] == "Atom Post"
    assert "example.com/x" in items[0]["link"]


def test_save_capture(monkeypatch):
    monkeypatch.setattr(
        "noosphere.core.knowledge_growth.index_corpus",
        lambda *a, **k: {"chunk_count": 1, "skipped": 0},
    )
    c = create_corpus("Cap")
    doc = save_capture(
        c["id"],
        content="# Note\n\nBody text.",
        title="From chat",
        question="What is X?",
        session_id="sess-1",
    )
    assert doc["title"] == "From chat"
    assert doc["doc_type"] == "capture"


def test_corpus_knowledge_health_no_chunks():
    c = create_corpus("H")
    ingest_text(c["id"], title="Lonely", content="Some text here.", doc_type="doc")
    report = corpus_knowledge_health(c["id"])
    assert report["document_count"] == 1
    assert report["documents_without_chunks_count"] == 1
    assert report["documents_without_chunks"][0]["title"] == "Lonely"


def test_compile_requires_sources(monkeypatch):
    from noosphere.core.knowledge_growth import compile_concept_note

    c = create_corpus("Compile")
    monkeypatch.setattr(
        "noosphere.core.knowledge_growth.search_corpus",
        lambda *a, **k: {"results": []},
    )
    with pytest.raises(ValueError, match="No sources found"):
        compile_concept_note(c["id"], "anything")


# ── Living concept notes: parse/assemble helpers ──────────────────────

def test_concept_content_roundtrip():
    compiled = "Summary line.\n\nKey points."
    timeline = [
        "- 2026-01-01 — ingested: doc one [id=aaaaaaaaaaaa]",
        "- 2026-01-02 — captured: chat q [id=bbbbbbbbbbbb]",
    ]
    serialized = _assemble_concept_content(compiled, timeline)
    assert "## Timeline" in serialized
    parsed_compiled, parsed_timeline = _parse_concept_content(serialized)
    assert parsed_compiled == compiled.rstrip()
    assert parsed_timeline == timeline


def test_timeline_parse_handles_legacy_concept():
    """Concept content without '## Timeline' heading is treated as compiled-truth only."""
    legacy = "# Old concept note\n\nSome body text without a timeline section."
    compiled, timeline = _parse_concept_content(legacy)
    assert compiled == legacy.rstrip()
    assert timeline == []


# ── Living concept notes: timeline-append hook ────────────────────────

def test_concept_timeline_appends_on_matching_ingest(stub_embedder):
    c = create_corpus("T1")
    concept = _make_concept_doc(c["id"], "Concept: Product-Market Fit", "pmf")
    # Index so concept chunks exist for similarity scoring.
    index_corpus(c["id"])

    source = ingest_text(
        c["id"],
        title="PMF early signals",
        content="Detailed discussion of pmf heuristics and product-market fit evidence.",
        doc_type="blog",
    )
    index_corpus(c["id"])

    linked = _append_to_matching_concept_timelines(c["id"], source["id"])
    assert len(linked) == 1
    assert linked[0]["concept_id"] == concept["id"]

    concept_after = get_document(concept["id"])
    _, timeline = _parse_concept_content(concept_after["content"])
    # Entry references new doc's id
    assert any(source["id"] in line for line in timeline)

    meta = json.loads(concept_after["metadata_json"])
    assert meta["timeline_dirty"] is True
    assert meta["pending_changes"] == 1


def test_concept_timeline_skips_unrelated_ingest(stub_embedder):
    c = create_corpus("T2")
    concept = _make_concept_doc(c["id"], "Concept: Auth", "authentication")
    index_corpus(c["id"])

    unrelated = ingest_text(
        c["id"],
        title="Recipe for pasta",
        content="Cooking instructions for a simple pasta recipe dish.",
        doc_type="blog",
    )
    index_corpus(c["id"])

    linked = _append_to_matching_concept_timelines(c["id"], unrelated["id"])
    assert linked == []

    concept_after = get_document(concept["id"])
    _, timeline = _parse_concept_content(concept_after["content"])
    # Timeline stayed empty (legacy "(no timeline entries yet)" line is not a `- ` bullet).
    assert timeline == []

    meta = json.loads(concept_after["metadata_json"])
    assert meta.get("timeline_dirty", False) is False


def test_concept_timeline_caps_at_max_matches(stub_embedder, monkeypatch):
    # Lower cap to 2 so we can verify the limit with a small fixture.
    monkeypatch.setattr("noosphere.core.knowledge_growth.CONCEPT_TIMELINE_MAX_MATCHES", 2)
    c = create_corpus("T3")
    for i in range(5):
        _make_concept_doc(c["id"], f"Concept: PMF #{i}", "product-market pmf")
    index_corpus(c["id"])

    source = ingest_text(
        c["id"],
        title="Another PMF article",
        content="Discussion of pmf and product-market fit.",
        doc_type="blog",
    )
    index_corpus(c["id"])

    linked = _append_to_matching_concept_timelines(c["id"], source["id"])
    assert len(linked) == 2, f"expected cap at 2, got {len(linked)}"


def test_hook_is_idempotent_for_same_entry(stub_embedder):
    c = create_corpus("T4")
    concept = _make_concept_doc(c["id"], "Concept: PMF", "pmf product-market")
    index_corpus(c["id"])

    source = ingest_text(
        c["id"],
        title="PMF post",
        content="Discussion of pmf heuristics and product-market fit.",
        doc_type="blog",
    )
    index_corpus(c["id"])

    _append_to_matching_concept_timelines(c["id"], source["id"])
    # Second call with identical doc should not add a duplicate entry.
    _append_to_matching_concept_timelines(c["id"], source["id"])

    concept_after = get_document(concept["id"])
    _, timeline = _parse_concept_content(concept_after["content"])
    # Only one entry for this source id.
    matching = [ln for ln in timeline if source["id"] in ln]
    assert len(matching) == 1


# ── Living concept notes: recompile ───────────────────────────────────

def test_recompile_noop_when_below_threshold(stub_embedder, stub_llm):
    c = create_corpus("T5")
    concept = _make_concept_doc(c["id"], "Concept: PMF", "pmf product-market")
    # Mark mildly dirty but below threshold.
    conn = __import__("noosphere.core.db", fromlist=["get_conn"]).get_conn()
    meta = {
        "version": 1,
        "timeline_dirty": True,
        "pending_changes": 1,  # below default 3
        "compile_kind": "concept_note",
        "source_document_ids": [],
    }
    conn.execute(
        "UPDATE documents SET metadata_json=? WHERE id=?",
        (json.dumps(meta), concept["id"]),
    )
    conn.commit()

    result = recompile_concept_if_dirty(concept["id"])
    assert result["status"] == "skipped"
    assert stub_llm == []  # no LLM call made


def test_recompile_force_overrides_threshold(stub_embedder, stub_llm):
    c = create_corpus("T6")
    concept = _make_concept_doc(c["id"], "Concept: PMF", "pmf product-market")
    # Ingest a source doc so timeline has a real id to pull from.
    source = ingest_text(
        c["id"],
        title="PMF article",
        content="Text about pmf and product-market fit signals.",
        doc_type="blog",
    )
    index_corpus(c["id"])
    _append_to_matching_concept_timelines(c["id"], source["id"])

    result = recompile_concept_if_dirty(concept["id"], force=True)
    assert result["status"] == "recompiled"
    assert result["version"] == 2
    assert result["previous_version"] == 1
    assert source["id"] in result["source_doc_ids"]

    # LLM was called; concept content has new synthesis but timeline preserved.
    assert len(stub_llm) == 1
    concept_after = get_document(concept["id"])
    _, timeline = _parse_concept_content(concept_after["content"])
    assert any(source["id"] in ln for ln in timeline)

    meta = json.loads(concept_after["metadata_json"])
    assert meta["version"] == 2
    assert meta["timeline_dirty"] is False
    assert meta["pending_changes"] == 0


def test_recompile_produces_snapshot_and_preserves_timeline(stub_embedder, stub_llm):
    c = create_corpus("T7")
    concept = _make_concept_doc(c["id"], "Concept: PMF", "pmf product-market")
    source = ingest_text(
        c["id"],
        title="PMF article",
        content="Text about pmf and product-market fit.",
        doc_type="blog",
    )
    index_corpus(c["id"])
    _append_to_matching_concept_timelines(c["id"], source["id"])

    before = get_document(concept["id"])
    _, timeline_before = _parse_concept_content(before["content"])

    recompile_concept_if_dirty(concept["id"], force=True)

    versions = get_concept_versions(concept["id"])
    assert len(versions) == 1
    assert versions[0]["version"] == 1
    assert versions[0]["content"] == before["content"]  # byte-identical snapshot
    assert source["id"] in versions[0]["source_doc_ids"]

    after = get_document(concept["id"])
    _, timeline_after = _parse_concept_content(after["content"])
    # Timeline unchanged — only compiled truth rewritten.
    assert timeline_after == timeline_before


def test_concept_versions_endpoint_returns_history(stub_embedder, stub_llm, client):
    c = create_corpus("T8")
    concept = _make_concept_doc(c["id"], "Concept: PMF", "pmf product-market")
    source = ingest_text(
        c["id"],
        title="PMF article",
        content="pmf product-market fit insights.",
        doc_type="blog",
    )
    index_corpus(c["id"])
    _append_to_matching_concept_timelines(c["id"], source["id"])

    recompile_concept_if_dirty(concept["id"], force=True)
    recompile_concept_if_dirty(concept["id"], force=True)

    resp = client.get(f"/api/v1/corpora/{c['id']}/documents/{concept['id']}/versions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == concept["id"]
    assert len(body["versions"]) == 2
    assert [v["version"] for v in body["versions"]] == [1, 2]


def test_recompile_dirty_concepts_skips_clean(stub_embedder, stub_llm):
    c = create_corpus("T9")
    _make_concept_doc(c["id"], "Concept: PMF", "pmf")  # clean, pending=0
    result = recompile_dirty_concepts(c["id"])
    assert result["total"] == 1
    assert result["recompiled"] == []
    assert len(result["skipped"]) == 1
