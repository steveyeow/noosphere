"""Tests for the indexer — incremental indexing with content hashes."""

from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from noosphere.core.corpus import create_corpus
from noosphere.core.ingest import ingest_text
from noosphere.core.db import get_conn


def _mock_embedder():
    embedder = MagicMock()
    embedder.embed.side_effect = lambda texts: np.random.randn(len(texts), 8).astype(np.float32)
    embedder.dim.return_value = 8
    embedder.model_name.return_value = "mock-embed"
    return embedder


@pytest.fixture
def corpus_with_docs():
    corpus = create_corpus("Test Corpus")
    ingest_text(corpus["id"], title="Doc A", content="Alpha content about testing.")
    ingest_text(corpus["id"], title="Doc B", content="Beta content about indexing.")
    return corpus


@patch("noosphere.core.indexer.get_embedder")
def test_index_creates_chunks(mock_get_embedder, corpus_with_docs):
    mock_get_embedder.return_value = _mock_embedder()
    from noosphere.core.indexer import index_corpus
    result = index_corpus(corpus_with_docs["id"])
    assert result["chunk_count"] > 0
    assert result["embedding_model"] == "mock-embed"


@patch("noosphere.core.indexer.get_embedder")
def test_incremental_skips_unchanged(mock_get_embedder, corpus_with_docs):
    mock_get_embedder.return_value = _mock_embedder()
    from noosphere.core.indexer import index_corpus

    r1 = index_corpus(corpus_with_docs["id"])
    assert r1["embedded"] > 0
    assert r1["skipped"] == 0

    r2 = index_corpus(corpus_with_docs["id"])
    assert r2["skipped"] == 2
    assert r2.get("embedded", 0) == 0


@patch("noosphere.core.indexer.get_embedder")
def test_force_reindexes_everything(mock_get_embedder, corpus_with_docs):
    mock_get_embedder.return_value = _mock_embedder()
    from noosphere.core.indexer import index_corpus

    index_corpus(corpus_with_docs["id"])
    r2 = index_corpus(corpus_with_docs["id"], force=True)
    assert r2["skipped"] == 0
    assert r2["embedded"] > 0


@patch("noosphere.core.indexer.get_embedder")
def test_content_hash_stored(mock_get_embedder, corpus_with_docs):
    mock_get_embedder.return_value = _mock_embedder()
    from noosphere.core.indexer import index_corpus

    index_corpus(corpus_with_docs["id"])
    conn = get_conn()
    docs = conn.execute(
        "SELECT content_hash, indexed_at FROM documents WHERE corpus_id=?",
        (corpus_with_docs["id"],),
    ).fetchall()
    for doc in docs:
        assert doc["content_hash"] is not None
        assert doc["indexed_at"] is not None


@patch("noosphere.core.indexer.get_embedder")
def test_fts_populated_after_index(mock_get_embedder, corpus_with_docs):
    mock_get_embedder.return_value = _mock_embedder()
    from noosphere.core.indexer import index_corpus

    index_corpus(corpus_with_docs["id"])
    conn = get_conn()
    fts_count = conn.execute("SELECT COUNT(*) as n FROM chunks_fts").fetchone()["n"]
    chunk_count = conn.execute(
        "SELECT COUNT(*) as n FROM chunks WHERE corpus_id=?",
        (corpus_with_docs["id"],),
    ).fetchone()["n"]
    assert fts_count == chunk_count
