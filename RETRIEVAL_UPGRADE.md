# Retrieval & Knowledge Quality Upgrade

> Make every corpus in the Noosphere smarter to build, harder to stump, and honest about what it doesn't know.

This document specifies the next wave of improvements to Noosphere's core retrieval, chunking, and sync layers. The goal: move from "it works" to "it works well at scale" — so a corpus with 5,000 documents returns precise, deduplicated, fresh results in milliseconds, and creators can keep their corpora alive without re-indexing the world.

---

## 1. Hybrid Search (keyword + vector + RRF fusion)

### Problem

Pure vector search fails in two predictable ways:

1. **Exact-match misses.** A query for "Pedro Franceschi" may not surface a document titled exactly that, because the name's embedding gets diluted by surrounding text.
2. **Recall ceiling.** A single query vector captures one semantic interpretation. Synonyms, abbreviations, and alternate phrasings are invisible.

### Design

Add **FTS5 keyword search** alongside the existing vector search, then fuse results with **Reciprocal Rank Fusion (RRF)**.

```
Query
  │
  ├──► FTS5 keyword search  ──► ranked list A
  │
  ├──► Vector cosine search ──► ranked list B
  │
  └──► RRF fusion: score = Σ 1/(k + rank)   where k = 60
       │
       ► Merged, deduplicated results
```

### Schema changes

```sql
-- New FTS5 virtual table (documents)
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title, content, doc_type, tags,
    content=documents, content_rowid=rowid
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS documents_fts_insert AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, title, content, doc_type, tags)
    VALUES (NEW.rowid, NEW.title, NEW.content, NEW.doc_type, NEW.tags);
END;

CREATE TRIGGER IF NOT EXISTS documents_fts_delete AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, content, doc_type, tags)
    VALUES ('delete', OLD.rowid, OLD.title, OLD.content, OLD.doc_type, OLD.tags);
END;

CREATE TRIGGER IF NOT EXISTS documents_fts_update AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, content, doc_type, tags)
    VALUES ('delete', OLD.rowid, OLD.title, OLD.content, OLD.doc_type, OLD.tags);
    INSERT INTO documents_fts(rowid, title, content, doc_type, tags)
    VALUES (NEW.rowid, NEW.title, NEW.content, NEW.doc_type, NEW.tags);
END;

-- Chunk-level FTS for fine-grained keyword matching
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    content=chunks, content_rowid=rowid
);

CREATE TRIGGER IF NOT EXISTS chunks_fts_insert AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text) VALUES (NEW.rowid, NEW.text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_fts_delete AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', OLD.rowid, OLD.text);
END;
```

### Retrieval logic

```python
def hybrid_search(corpus_id, query, *, top_k=5):
    keyword_results = fts5_search(corpus_id, query, limit=top_k * 3)
    vector_results  = vector_search(corpus_id, query, limit=top_k * 3)
    fused = rrf_fuse(keyword_results, vector_results, k=60)
    deduped = deduplicate(fused)
    return deduped[:top_k]
```

The existing `search_corpus` function becomes `hybrid_search` internally. The API surface (MCP, REST, CLI) does not change — callers still call `search`, and the engine decides the best strategy.

### Fallback

If no embedding provider is configured, search falls back to keyword-only (FTS5). If FTS tables don't exist yet (legacy DB), search falls back to vector-only. Both paths remain functional.

---

## 2. Search Result Deduplication

### Problem

Multiple chunks from the same document often dominate results. A 50-page paper might return 5 chunks from the same section, burying results from other documents.

### Four-layer dedup

Applied after RRF fusion, before returning results:

1. **Best chunk per document.** Keep only the highest-scoring chunk from each document. (Configurable: `per_doc_chunks=1` default, can be raised.)
2. **Cosine similarity dedup.** If two result chunks have cosine similarity > 0.90, keep the higher-scoring one.
3. **Type diversity cap.** No single `doc_type` can exceed 60% of results (e.g., if a corpus has both `paper` and `blog`, results won't be all papers).
4. **Freshness boost.** Documents with a `date` field get a small score boost based on recency (configurable, default: +0.02 per year closer to now, capped at +0.10).

---

## 3. Chunking Strategy Profiles

### Problem

A podcast transcript, an academic paper, and a collection of short notes need very different chunking. One-size-fits-all paragraph splitting loses structure for long documents and over-fragments short ones.

### Three strategies

| Strategy | Best for | How it works |
|----------|----------|--------------|
| `paragraph` (default) | Blog posts, notes, newsletters | Split on headings + double newlines, merge small, split oversized. Current behavior. |
| `recursive` | Transcripts, timelines, long-form | 5-level delimiter hierarchy: `\n\n\n` → `\n\n` → `\n` → `. ` → ` `. Larger chunks (500 words) with 80-word overlap. |
| `semantic` | Papers, essays, compiled summaries | Embed each sentence, compute adjacent cosine similarities, find topic boundaries where similarity drops. Falls back to `paragraph` on failure. |

### Interface

```python
def chunk_document(text, *, strategy="paragraph", **kwargs) -> list[dict]:
    ...
```

Corpus manifest gains an optional `chunk_strategy` field. The indexer reads this when chunking. Default remains `paragraph` for backward compatibility.

### CLI

```bash
noosphere init ./papers --name "Research" --chunk-strategy semantic
noosphere index --corpus my-blog --chunk-strategy recursive
```

---

## 4. Content-Hash Idempotent Indexing

### Problem

`index_corpus` currently deletes ALL chunks and re-embeds from scratch. For a corpus with 1,000 documents, adding one document means re-embedding all 1,000. At $0.0001/1K tokens, a 10,000-document corpus costs ~$5 per full re-index.

### Design

Add a `content_hash` column to `documents`. On ingest, compute SHA-256 of the document content. On index, skip any document whose hash hasn't changed since last indexing.

### Schema changes

```sql
ALTER TABLE documents ADD COLUMN content_hash TEXT;
ALTER TABLE documents ADD COLUMN indexed_at TEXT;
```

### Indexing logic

```python
def index_corpus(corpus_id, *, incremental=True, ...):
    docs = get_documents(corpus_id)
    for doc in docs:
        current_hash = sha256(doc.content)
        if incremental and doc.content_hash == current_hash and doc.indexed_at:
            continue  # skip, already indexed
        delete_chunks_for(doc.id)
        chunks = chunk_document(doc.content, strategy=corpus.chunk_strategy)
        embed_and_store(chunks)
        update_document_hash(doc.id, current_hash)
```

### `--force` flag

`noosphere index --corpus X --force` ignores hashes and re-indexes everything. Useful when changing embedding models or chunk strategies.

---

## 5. Incremental Sync

### Problem

Creators who maintain a living corpus (e.g., a directory of Markdown files that they edit regularly) have no way to sync changes without manually re-ingesting.

### Design

New CLI command: `noosphere sync`.

```bash
noosphere sync ./my-docs --corpus my-blog
```

Behavior:
1. Walk the directory, compute content hash for each file.
2. Compare against existing documents in the corpus (matched by relative file path stored in `metadata_json.source_path`).
3. **New files** → ingest + index.
4. **Changed files** (different hash) → update content + re-index that document only.
5. **Deleted files** → optionally remove (flag `--prune`, default: leave in place).
6. **Unchanged files** → skip entirely.

Progress output:

```
Syncing ./my-docs → corpus "my-blog"
  3 new, 2 updated, 0 pruned, 95 unchanged
  Embedding 5 documents... done (12 chunks)
```

### Metadata tracking

On ingest from directory, store the relative path:

```json
{"source_path": "papers/attention-is-all-you-need.md"}
```

This enables sync to match files to documents without relying on titles (which can change).

---

## 6. Freshness Signals

### Problem

A corpus with documents spanning years has no way to signal which content may be outdated. An agent citing a 2019 recommendation doesn't know the author updated their thinking in 2024.

### Design

Add optional freshness metadata to search results:

```json
{
  "chunk_id": "abc123",
  "score": 0.87,
  "text": "...",
  "citation": { ... },
  "freshness": {
    "document_date": "2019-03-15",
    "corpus_last_updated": "2024-11-20",
    "age_days": 2036,
    "stale": true
  }
}
```

A document is considered **stale** if its `date` is more than 365 days older than the corpus's `updated_at`. The threshold is configurable per corpus.

This doesn't hide stale results — it gives agents the signal to qualify their citations ("according to a 2019 document...").

---

## 7. Multi-Query Expansion

### Problem

A single query vector captures one interpretation. "When should you ignore conventional wisdom?" won't find a document titled "The Bus Ticket Theory of Genius" even though it's semantically relevant.

### Design

Before searching, expand the user query into 2–3 alternative phrasings using a lightweight LLM call.

```
Original: "when should you ignore conventional wisdom?"
Expanded:
  - "contrarian thinking in startups"
  - "going against the crowd benefits"
  - "when conventional advice is wrong"
```

Each expansion is searched independently (vector + keyword). Results from all queries are pooled, then RRF-fused and deduped as usual.

### Cost control

- Uses the cheapest available model (Gemini Flash or GPT-4o-mini).
- Only triggers when `top_k >= 3` and corpus has > 50 chunks (small corpora don't need it).
- Can be disabled per-query: `search --no-expand` or `"expand": false` in API.
- Total overhead: ~0.5s latency, ~$0.00002 per query.

---

## 8. Implementation Order

| Phase | What | Files touched |
|-------|------|--------------|
| **A** | FTS5 schema + keyword search | `db.py`, `retrieval.py` |
| **B** | RRF fusion + hybrid search | `retrieval.py` |
| **C** | Result dedup (4 layers) | `retrieval.py` |
| **D** | Content-hash + incremental index | `db.py`, `ingest.py`, `indexer.py` |
| **E** | Chunking profiles (recursive, semantic) | `chunker.py`, `indexer.py`, `config.py` |
| **F** | Sync command | `ingest.py`, `cli/main.py` |
| **G** | Freshness signals | `retrieval.py` |
| **H** | Multi-query expansion | `retrieval.py`, `config.py` |

Phases A–D are the highest impact and should land first. E–H build on the foundation.

---

## 9. Backward Compatibility

- All changes are additive. Existing databases get new tables/columns via migrations that run on first connect.
- The default chunking strategy remains `paragraph`. Existing corpora are unaffected.
- `search_corpus()` signature gains optional keyword arguments but no required parameters change.
- MCP tools and REST API remain identical from the caller's perspective.
- FTS5 is built into SQLite (no external dependency).

---

## 10. Success Criteria

1. **Precision.** A query for an exact person/company name returns that entity's document as the #1 result (keyword search catches what vector misses).
2. **Recall.** A conceptual query ("when should founders ignore advice") surfaces semantically related documents even if they don't share keywords (multi-query expansion).
3. **Efficiency.** Adding 1 document to a 1,000-document corpus re-embeds only that document, not all 1,000.
4. **Diversity.** Top-5 results come from at least 3 different documents (dedup prevents single-doc domination).
5. **Freshness.** Agents can distinguish a 2024 insight from a 2019 one without reading the full document.
