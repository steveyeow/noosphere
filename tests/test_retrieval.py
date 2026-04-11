"""Tests for hybrid retrieval — keyword search, RRF fusion, dedup, freshness."""

from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from noosphere.core.corpus import create_corpus
from noosphere.core.ingest import ingest_text


def _mock_embedder():
    embedder = MagicMock()
    embedder.embed.side_effect = lambda texts: np.random.randn(len(texts), 8).astype(np.float32)
    embedder.dim.return_value = 8
    embedder.model_name.return_value = "mock-embed"
    return embedder


@pytest.fixture
def indexed_corpus():
    corpus = create_corpus("Retrieval Test")
    ingest_text(corpus["id"], title="Alpha Doc", content="Alpha is about machine learning and neural networks.")
    ingest_text(corpus["id"], title="Beta Doc", content="Beta discusses natural language processing.", date="2023-01-01")
    ingest_text(corpus["id"], title="Gamma Doc", content="Gamma covers reinforcement learning strategies.")

    with patch("noosphere.core.indexer.get_embedder", return_value=_mock_embedder()):
        from noosphere.core.indexer import index_corpus
        index_corpus(corpus["id"])

    return corpus


@patch("noosphere.core.retrieval.get_embedder")
def test_search_returns_results(mock_get_embedder, indexed_corpus):
    mock_get_embedder.return_value = _mock_embedder()
    from noosphere.core.retrieval import search_corpus
    result = search_corpus(indexed_corpus["id"], "machine learning", top_k=3, expand=False)
    assert "results" in result
    assert "usage" in result
    assert result["usage"]["chunks_searched"] > 0


@patch("noosphere.core.retrieval.get_embedder")
def test_search_results_have_citations(mock_get_embedder, indexed_corpus):
    mock_get_embedder.return_value = _mock_embedder()
    from noosphere.core.retrieval import search_corpus
    result = search_corpus(indexed_corpus["id"], "neural networks", top_k=3, expand=False)
    for r in result["results"]:
        assert "chunk_id" in r
        assert "score" in r
        assert "text" in r
        assert "citation" in r
        cite = r["citation"]
        assert "document_title" in cite
        assert "document_id" in cite


@patch("noosphere.core.retrieval.get_embedder")
def test_search_results_have_freshness(mock_get_embedder, indexed_corpus):
    mock_get_embedder.return_value = _mock_embedder()
    from noosphere.core.retrieval import search_corpus
    result = search_corpus(indexed_corpus["id"], "processing", top_k=5, expand=False)
    for r in result["results"]:
        assert "freshness" in r
        assert "stale" in r["freshness"]


@patch("noosphere.core.retrieval.get_embedder")
def test_search_dedup_limits_per_doc(mock_get_embedder, indexed_corpus):
    mock_get_embedder.return_value = _mock_embedder()
    from noosphere.core.retrieval import search_corpus
    result = search_corpus(indexed_corpus["id"], "learning", top_k=5, expand=False)
    doc_ids = [r["citation"]["document_id"] for r in result["results"]]
    from collections import Counter
    counts = Counter(doc_ids)
    for did, count in counts.items():
        assert count <= 1, f"Document {did} appeared {count} times (dedup should limit to 1)"


@patch("noosphere.core.retrieval.get_embedder")
def test_search_empty_corpus(mock_get_embedder):
    mock_get_embedder.return_value = _mock_embedder()
    corpus = create_corpus("Empty Corpus")
    from noosphere.core.retrieval import search_corpus
    result = search_corpus(corpus["id"], "anything", expand=False)
    assert result["results"] == []


def test_keyword_search_works(indexed_corpus):
    from noosphere.core.retrieval import _keyword_search
    results = _keyword_search(indexed_corpus["id"], "Alpha")
    assert len(results) >= 1
    assert any("Alpha" in r.get("text", "") or "alpha" in r.get("text", "").lower() for r in results)


def test_keyword_search_no_results(indexed_corpus):
    from noosphere.core.retrieval import _keyword_search
    results = _keyword_search(indexed_corpus["id"], "xyznonexistent12345")
    assert results == []


def test_rrf_fuse():
    from noosphere.core.retrieval import _rrf_fuse
    kw = [{"id": "a", "text": "a"}, {"id": "b", "text": "b"}]
    vec = [{"id": "b", "text": "b"}, {"id": "c", "text": "c"}]
    fused = _rrf_fuse(kw, vec)
    ids = [r["id"] for r in fused]
    assert "b" in ids
    assert fused[0]["id"] == "b"  # appears in both lists, highest score
    assert len(fused) == 3


def test_rrf_fuse_empty():
    from noosphere.core.retrieval import _rrf_fuse
    assert _rrf_fuse([], []) == []
    fused = _rrf_fuse([{"id": "a", "text": "a"}], [])
    assert len(fused) == 1
