"""Export a corpus as a portable ZIP package aligned with SPEC format."""

import io
import json
import zipfile

from noosphere.core.corpus import get_corpus
from noosphere.core.ingest import get_documents
from noosphere.core.db import get_conn


def export_corpus(corpus_id: str) -> io.BytesIO:
    """Export a corpus as a ZIP file in SPEC-compliant structure.

    Structure:
        corpus-slug/
          noosphere.json       # manifest
          documents/
            doc-{id}.md        # source documents with front-matter
          index/
            chunks.jsonl       # chunk metadata (no vectors)
          meta/
            topics.json
            stats.json
    """
    corpus = get_corpus(corpus_id)
    if not corpus:
        raise ValueError(f"Corpus not found: {corpus_id}")

    docs = get_documents(corpus_id)
    slug = corpus.get("slug", corpus_id)

    conn = get_conn()
    chunks = conn.execute(
        "SELECT id, document_id, chunk_index, text, char_start, char_end, metadata_json "
        "FROM chunks WHERE corpus_id=? ORDER BY document_id, chunk_index",
        (corpus_id,),
    ).fetchall()

    tags = corpus.get("tags", [])
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except Exception:
            tags = []

    manifest = {
        "schema_version": "1.0",
        "corpus_id": corpus["id"],
        "name": corpus["name"],
        "description": corpus.get("description", ""),
        "author": {
            "name": corpus.get("author_name", ""),
            "url": corpus.get("author_url", ""),
        },
        "created_at": corpus.get("created_at", ""),
        "updated_at": corpus.get("updated_at", ""),
        "document_count": corpus.get("document_count", 0),
        "chunk_count": corpus.get("chunk_count", 0),
        "word_count": corpus.get("word_count", 0),
        "embedding_model": corpus.get("embedding_model", ""),
        "embedding_dim": corpus.get("embedding_dim", 0),
        "language": corpus.get("language", "en"),
        "tags": tags,
        "access": {
            "level": corpus.get("access_level", "public"),
            "pricing": None,
        },
    }

    all_topics = set()
    for t in tags:
        all_topics.add(t.strip().lower())
    for doc in docs:
        dt = doc.get("tags", "[]")
        if isinstance(dt, str):
            try:
                dt = json.loads(dt)
            except Exception:
                dt = []
        for t in (dt if isinstance(dt, list) else []):
            all_topics.add(t.strip().lower())

    stats = {
        "document_count": corpus.get("document_count", 0),
        "chunk_count": corpus.get("chunk_count", 0),
        "word_count": corpus.get("word_count", 0),
        "embedding_model": corpus.get("embedding_model", ""),
        "status": corpus.get("status", "draft"),
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{slug}/noosphere.json", json.dumps(manifest, indent=2, ensure_ascii=False))

        for doc in docs:
            content = doc.get("content", "")
            title = doc.get("title", "")
            date = doc.get("date", "")
            header = f"---\ntitle: {title}\n"
            if date:
                header += f"date: {date}\n"
            header += "---\n\n"
            zf.writestr(f"{slug}/documents/{doc['id']}.md", header + content)

        chunk_lines = []
        for c in chunks:
            meta = {}
            if c["metadata_json"]:
                try:
                    meta = json.loads(c["metadata_json"])
                except Exception:
                    pass
            chunk_lines.append(json.dumps({
                "id": c["id"],
                "document_id": c["document_id"],
                "chunk_index": c["chunk_index"],
                "text": c["text"],
                "char_start": c["char_start"],
                "char_end": c["char_end"],
                "metadata": meta,
            }, ensure_ascii=False))
        zf.writestr(f"{slug}/index/chunks.jsonl", "\n".join(chunk_lines))

        zf.writestr(f"{slug}/meta/topics.json", json.dumps({"topics": sorted(all_topics)}, indent=2))
        zf.writestr(f"{slug}/meta/stats.json", json.dumps(stats, indent=2))

    buf.seek(0)
    return buf
