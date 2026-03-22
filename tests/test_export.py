"""Tests for ``noosphere.core.export``."""

import json
import uuid
import zipfile
from datetime import datetime, timezone

import pytest

from noosphere.core.corpus import create_corpus, get_corpus, update_corpus
from noosphere.core.db import get_conn
from noosphere.core.export import export_corpus
from noosphere.core.ingest import ingest_text


def test_export_corpus_zip_structure_and_manifest(isolated_db):
    c = create_corpus(
        "Export Me",
        description="desc",
        author_name="Author",
        tags=["alpha", "beta"],
        access_level="public",
    )
    ingest_text(c["id"], title="Doc One", content="Hello export", date="2024-01-02")

    buf = export_corpus(c["id"])
    data = buf.getvalue()
    assert len(data) > 0

    full = get_corpus(c["id"])
    slug = full["slug"]
    prefix = f"{slug}/"

    with zipfile.ZipFile(buf, "r") as zf:
        names = zf.namelist()
        assert f"{prefix}noosphere.json" in names
        assert any(n.startswith(f"{prefix}documents/") and n.endswith(".md") for n in names)
        assert f"{prefix}index/chunks.jsonl" in names
        assert f"{prefix}meta/topics.json" in names
        assert f"{prefix}meta/stats.json" in names

        manifest = json.loads(zf.read(f"{prefix}noosphere.json"))
        assert manifest["schema_version"] == "1.0"
        assert manifest["corpus_id"] == c["id"]
        assert manifest["name"] == "Export Me"
        assert manifest["description"] == "desc"
        assert manifest["author"]["name"] == "Author"
        assert set(manifest["tags"]) >= {"alpha", "beta"}
        assert manifest["access"]["level"] == "public"
        assert manifest["document_count"] == 1

        stats = json.loads(zf.read(f"{prefix}meta/stats.json"))
        assert stats["document_count"] == 1

        topics = json.loads(zf.read(f"{prefix}meta/topics.json"))
        assert "topics" in topics


def test_export_corpus_unknown_raises(isolated_db):
    with pytest.raises(ValueError, match="not found"):
        export_corpus("deadbeef0000")


def test_export_empty_corpus_zip_structure(isolated_db):
    c = create_corpus("Empty Export")
    buf = export_corpus(c["id"])
    slug = get_corpus(c["id"])["slug"]
    prefix = f"{slug}/"
    with zipfile.ZipFile(buf, "r") as zf:
        names = zf.namelist()
        assert f"{prefix}noosphere.json" in names
        assert f"{prefix}index/chunks.jsonl" in names
        assert f"{prefix}meta/topics.json" in names
        assert f"{prefix}meta/stats.json" in names
        doc_entries = [n for n in names if n.startswith(f"{prefix}documents/")]
        assert doc_entries == []
        manifest = json.loads(zf.read(f"{prefix}noosphere.json"))
        assert manifest["document_count"] == 0


def test_export_document_markdown_has_front_matter(isolated_db):
    c = create_corpus("FM Export")
    d = ingest_text(
        c["id"],
        title="Titled Doc",
        content="Main **body**.",
        date="2023-11-11",
    )
    buf = export_corpus(c["id"])
    slug = get_corpus(c["id"])["slug"]
    path = f"{slug}/documents/{d['id']}.md"
    with zipfile.ZipFile(buf, "r") as zf:
        raw = zf.read(path).decode("utf-8")
    assert raw.startswith("---\n")
    assert "title: Titled Doc" in raw
    assert "date: 2023-11-11" in raw
    assert "Main **body**." in raw


def test_export_includes_chunk_index_lines(isolated_db):
    """Insert a chunk row so index/chunks.jsonl is non-empty JSONL."""
    c = create_corpus("Chunks")
    doc = ingest_text(c["id"], title="D", content="chunked body here")
    chunk_id = uuid.uuid4().hex[:12]
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO chunks
           (id, corpus_id, document_id, chunk_index, text, char_start, char_end,
            vector, dim, norm, metadata_json, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            chunk_id,
            c["id"],
            doc["id"],
            0,
            "chunk text",
            0,
            10,
            b"\x00\x00",
            1,
            1.0,
            '{"section": 1}',
            now,
        ),
    )
    conn.commit()

    buf = export_corpus(c["id"])
    slug = get_corpus(c["id"])["slug"]
    prefix = f"{slug}/"
    with zipfile.ZipFile(buf, "r") as zf:
        raw = zf.read(f"{prefix}index/chunks.jsonl").decode("utf-8")
        line = raw.strip().split("\n")[0]
        obj = json.loads(line)
        assert obj["id"] == chunk_id
        assert obj["document_id"] == doc["id"]
        assert obj["text"] == "chunk text"
        assert obj["metadata"] == {"section": 1}


def test_export_zip_entries_live_under_corpus_slug_prefix(isolated_db):
    c = create_corpus("Zip root")
    buf = export_corpus(c["id"])
    slug = get_corpus(c["id"])["slug"]
    root = f"{slug}/"
    with zipfile.ZipFile(buf, "r") as zf:
        for name in zf.namelist():
            assert name.startswith(root), name


def test_export_topics_merge_corpus_and_document_tags(isolated_db):
    c = create_corpus("Topic merge", tags=["CorpusTag"])
    ingest_text(
        c["id"],
        title="Tagged",
        content="x",
        tags=["DocOnly"],
    )
    buf = export_corpus(c["id"])
    slug = get_corpus(c["id"])["slug"]
    with zipfile.ZipFile(buf, "r") as zf:
        topics = json.loads(zf.read(f"{slug}/meta/topics.json"))["topics"]
    assert "corpustag" in topics
    assert "doconly" in topics


def test_export_manifest_reflects_chunk_count_from_corpus(isolated_db):
    c = create_corpus("Chunk count meta")
    update_corpus(c["id"], chunk_count=42)
    buf = export_corpus(c["id"])
    slug = get_corpus(c["id"])["slug"]
    with zipfile.ZipFile(buf, "r") as zf:
        manifest = json.loads(zf.read(f"{slug}/noosphere.json"))
        stats = json.loads(zf.read(f"{slug}/meta/stats.json"))
    assert manifest["chunk_count"] == 42
    assert stats["chunk_count"] == 42
