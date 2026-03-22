"""Tests for ``noosphere.core.ingest`` (text, file, directory, helpers)."""

import json

import pytest

from noosphere.core.corpus import create_corpus, get_corpus
from noosphere.core.ingest import (
    _extract_markdown_metadata,
    _html_to_markdown,
    delete_document,
    get_document,
    get_documents,
    ingest_directory,
    ingest_file,
    ingest_text,
)


def test_ingest_text_stores_document_and_updates_counts(isolated_db):
    c = create_corpus("Ingest Corpus")
    doc = ingest_text(
        c["id"],
        title="Hello",
        content="one two three four",
        doc_type="note",
        date="2024-01-01",
        tags=["t1"],
        metadata={"k": "v"},
    )
    assert doc["corpus_id"] == c["id"]
    assert doc["title"] == "Hello"
    assert doc["word_count"] == 4
    row = get_corpus(c["id"])
    assert row["document_count"] == 1
    assert row["word_count"] >= 4


def test_get_documents_and_get_document(isolated_db):
    c = create_corpus("Docs")
    d1 = ingest_text(c["id"], title="B", content="x", date="2024-02-01")
    d2 = ingest_text(c["id"], title="A", content="y", date="2024-03-01")
    docs = get_documents(c["id"])
    assert len(docs) == 2
    titles_in_order = [d["title"] for d in docs]
    assert titles_in_order == ["A", "B"]
    one = get_document(d1["id"])
    assert one is not None
    assert one["title"] == "B"


def test_get_document_missing(isolated_db):
    assert get_document("nope00000000") is None


def test_delete_document_removes_and_updates_counts(isolated_db):
    c = create_corpus("Del")
    doc = ingest_text(c["id"], title="T", content="body")
    assert delete_document(doc["id"]) is True
    assert get_document(doc["id"]) is None
    assert get_corpus(c["id"])["document_count"] == 0


def test_delete_document_unknown(isolated_db):
    assert delete_document("missing00000") is False


def test_ingest_file_with_front_matter(tmp_path, isolated_db):
    c = create_corpus("Files")
    p = tmp_path / "post.md"
    p.write_text(
        '---\ntitle: From FM\ndate: 2025-06-01\ntags: "a, b"\n---\n\n# Ignored H1\nBody here.',
        encoding="utf-8",
    )
    doc = ingest_file(c["id"], p, doc_type="md")
    assert doc is not None
    assert doc["title"] == "From FM"
    assert doc["date"] == "2025-06-01"
    stored = get_document(doc["id"])
    assert "Body here" in stored["content"]
    assert stored["title"] == "From FM"


def test_ingest_file_uses_heading_or_stem_when_no_title(tmp_path, isolated_db):
    c = create_corpus("Head")
    p = tmp_path / "chapter.md"
    p.write_text("# Chapter One\n\nPara.", encoding="utf-8")
    doc = ingest_file(c["id"], p)
    assert doc["title"] == "Chapter One"


def test_ingest_file_missing_returns_none(tmp_path, isolated_db):
    c = create_corpus("Missing")
    assert ingest_file(c["id"], tmp_path / "nope.md") is None


def test_ingest_file_empty_returns_none(tmp_path, isolated_db):
    c = create_corpus("Empty")
    p = tmp_path / "empty.md"
    p.write_text("   \n", encoding="utf-8")
    assert ingest_file(c["id"], p) is None


def test_ingest_directory(tmp_path, isolated_db):
    c = create_corpus("Dir")
    (tmp_path / "a.md").write_text("# A\nx", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("plain", encoding="utf-8")
    docs = ingest_directory(c["id"], tmp_path)
    assert len(docs) == 2
    titles = {d["title"] for d in docs}
    assert "A" in titles
    assert "b" in titles


def test_ingest_directory_not_found(tmp_path, isolated_db):
    c = create_corpus("NF")
    with pytest.raises(FileNotFoundError):
        ingest_directory(c["id"], tmp_path / "missing_dir")


def test_ingest_directory_no_matching_files(tmp_path, isolated_db):
    c = create_corpus("Noext")
    (tmp_path / "x.py").write_text("print(1)", encoding="utf-8")
    with pytest.raises(ValueError, match="No files"):
        ingest_directory(c["id"], tmp_path)


def test_extract_markdown_metadata_no_front_matter():
    body = "Just text\n---\nnot yaml"
    meta, rest = _extract_markdown_metadata(body)
    assert meta == {}
    assert rest == body


def test_extract_markdown_metadata_parses_yaml_block():
    text = '---\ntitle: T\ndate: D\n---\n\nBody line'
    meta, rest = _extract_markdown_metadata(text)
    assert meta["title"] == "T"
    assert meta["date"] == "D"
    assert rest.strip().startswith("Body")


def test_extract_markdown_metadata_incomplete_delimiters():
    text = "---\nonly open"
    meta, rest = _extract_markdown_metadata(text)
    assert meta == {}
    assert rest == text


def test_html_to_markdown_strips_scripts_and_headings():
    html = (
        '<script>alert(1)</script><h1>Title</h1>'
        '<p>Hello <strong>bold</strong></p>'
        '<a href="https://x.com">link</a>'
    )
    md = _html_to_markdown(html)
    assert "alert" not in md
    assert "# Title" in md
    assert "**bold**" in md
    assert "[link](https://x.com)" in md


def test_get_documents_empty_corpus(isolated_db):
    c = create_corpus("No Docs")
    assert get_documents(c["id"]) == []


def test_ingest_text_defaults_for_tags_and_metadata(isolated_db):
    c = create_corpus("Defaults")
    doc = ingest_text(c["id"], title="T", content="body text here")
    row = get_document(doc["id"])
    assert json.loads(row["tags"]) == []
    assert json.loads(row["metadata_json"]) == {}


def test_ingest_directory_includes_text_extension(tmp_path, isolated_db):
    c = create_corpus("Text ext")
    (tmp_path / "note.text").write_text("# From Text\n\nok", encoding="utf-8")
    docs = ingest_directory(c["id"], tmp_path)
    assert len(docs) == 1
    assert docs[0]["title"] == "From Text"


def test_get_documents_same_date_sorts_by_title(isolated_db):
    c = create_corpus("Sort")
    ingest_text(c["id"], title="Zed", content="a", date="2024-01-01")
    ingest_text(c["id"], title="Alpha", content="b", date="2024-01-01")
    titles = [d["title"] for d in get_documents(c["id"])]
    assert titles == ["Alpha", "Zed"]


def test_html_to_markdown_strips_nav_style_and_entities():
    html = (
        '<nav>skip me</nav><style>.x{}</style>'
        '<p>Hi&nbsp;there<br/>line</p>'
    )
    md = _html_to_markdown(html)
    assert "skip me" not in md
    assert ".x" not in md
    assert "Hi there" in md
    assert "line" in md


def test_html_to_markdown_h2_and_em():
    html = "<h2>Sub</h2><p><em>italic</em></p>"
    md = _html_to_markdown(html)
    assert "## Sub" in md
    assert "*italic*" in md


def test_extract_markdown_metadata_strips_quotes_on_values():
    text = "---\ntitle: \"Quoted\"\n---\n\nBody"
    meta, rest = _extract_markdown_metadata(text)
    assert meta["title"] == "Quoted"
    assert "Body" in rest


def test_ingest_file_uses_stem_when_no_heading_or_front_matter(tmp_path, isolated_db):
    c = create_corpus("Stem only")
    p = tmp_path / "my-chapter.md"
    p.write_text("Plain paragraph only.\n", encoding="utf-8")
    doc = ingest_file(c["id"], p)
    assert doc["title"] == "my-chapter"


def test_delete_document_removes_chunks(isolated_db):
    from datetime import datetime, timezone
    import uuid

    from noosphere.core.db import get_conn

    c = create_corpus("Chunk del")
    doc = ingest_text(c["id"], title="D", content="content")
    conn = get_conn()
    chunk_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO chunks
           (id, corpus_id, document_id, chunk_index, text, char_start, char_end,
            vector, dim, norm, metadata_json, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (chunk_id, c["id"], doc["id"], 0, "c", 0, 1, b"\x00", 1, 1.0, "{}", now),
    )
    conn.commit()
    assert delete_document(doc["id"]) is True
    n = conn.execute(
        "SELECT COUNT(*) FROM chunks WHERE document_id=?", (doc["id"],)
    ).fetchone()[0]
    assert n == 0


def test_ingest_directory_respects_file_extensions(tmp_path, isolated_db):
    c = create_corpus("Ext filter")
    (tmp_path / "keep.md").write_text("# K\n", encoding="utf-8")
    (tmp_path / "skip.txt").write_text("plain", encoding="utf-8")
    docs = ingest_directory(c["id"], tmp_path, file_extensions=(".md",))
    assert len(docs) == 1
    assert docs[0]["title"] == "K"


def test_ingest_text_default_doc_type(isolated_db):
    c = create_corpus("Doc type default")
    doc = ingest_text(c["id"], title="T", content="one")
    row = get_document(doc["id"])
    assert row["doc_type"] == "doc"


def test_html_to_markdown_h3_and_footer_stripped():
    html = "<footer>foot</footer><h3>H3</h3><p>x</p>"
    md = _html_to_markdown(html)
    assert "foot" not in md
    assert "### H3" in md


def test_extract_markdown_metadata_single_quoted_values():
    text = "---\ntitle: 'Single'\n---\n\nB"
    meta, rest = _extract_markdown_metadata(text)
    assert meta["title"] == "Single"
    assert "B" in rest
