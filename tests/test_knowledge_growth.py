"""Tests for knowledge growth (RSS, capture, health, compile)."""

import pytest

from noosphere.core.corpus import create_corpus
from noosphere.core.ingest import ingest_text
from noosphere.core.knowledge_growth import (
    _parse_rss_atom,
    corpus_knowledge_health,
    save_capture,
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
