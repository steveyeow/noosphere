"""Tests for incremental sync — ingest.sync_directory."""

import os

import pytest

from noosphere.core.corpus import create_corpus
from noosphere.core.ingest import sync_directory, get_documents


@pytest.fixture
def corpus():
    return create_corpus("Sync Test")


@pytest.fixture
def doc_dir(tmp_path):
    d = tmp_path / "docs"
    d.mkdir()
    (d / "one.md").write_text("# Doc One\n\nFirst document content.")
    (d / "two.md").write_text("# Doc Two\n\nSecond document content.")
    return d


def test_sync_adds_new_files(corpus, doc_dir):
    result = sync_directory(corpus["id"], str(doc_dir))
    assert result["new"] == 2
    assert result["updated"] == 0
    assert result["pruned"] == 0

    docs = get_documents(corpus["id"])
    assert len(docs) == 2


def test_sync_detects_changes(corpus, doc_dir):
    sync_directory(corpus["id"], str(doc_dir))

    (doc_dir / "one.md").write_text("# Doc One\n\nUpdated content for doc one.")
    result = sync_directory(corpus["id"], str(doc_dir))
    assert result["updated"] >= 1
    assert result["new"] == 0


def test_sync_prune_removes_deleted(corpus, doc_dir):
    sync_directory(corpus["id"], str(doc_dir))

    os.remove(doc_dir / "two.md")
    result = sync_directory(corpus["id"], str(doc_dir), prune=True)
    assert result["pruned"] == 1

    docs = get_documents(corpus["id"])
    assert len(docs) == 1


def test_sync_no_prune_keeps_deleted(corpus, doc_dir):
    sync_directory(corpus["id"], str(doc_dir))

    os.remove(doc_dir / "two.md")
    result = sync_directory(corpus["id"], str(doc_dir), prune=False)
    assert result["pruned"] == 0

    docs = get_documents(corpus["id"])
    assert len(docs) == 2


def test_sync_respects_file_extensions(corpus, doc_dir):
    (doc_dir / "skip.xyz").write_text("Should be skipped")
    result = sync_directory(corpus["id"], str(doc_dir), file_extensions=(".md",))
    assert result["new"] == 2  # only .md files


def test_sync_empty_dir(corpus, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = sync_directory(corpus["id"], str(empty))
    assert result["new"] == 0
