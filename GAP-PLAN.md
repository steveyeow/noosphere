# Noosphere — Knowledge Growth Engine Plan

Bridging the capability gap with Karpathy's LLM Wiki and GBrain.

---

## Context

Karpathy's LLM Wiki and Garry Tan's GBrain have popularized a new category: personal AI knowledge bases maintained by LLMs. Noosphere's differentiators are democratization (zero-technical-barrier creation) and network effects (cross-knowledge-base discovery). But several capabilities they pioneered are genuinely valuable and missing from Noosphere today.

This document specifies the four features that close the most important gaps — ordered by impact and implementation complexity.

---

## 1. Chat Write-Back

**What:** Insights generated during RAG chat sessions can be saved back to the knowledge base as new documents.

**Why this matters:** Both Karpathy and GBrain treat conversations as a source of new knowledge. In Karpathy's system, "every exploration adds up" — query outputs get filed back into the wiki. In GBrain, agents write updated information back after every interaction. Noosphere's chat is currently read-only; insights vanish when the session ends.

**Design:**

```
User chats with knowledge base
  → AI returns answer with citations
  → User clicks "Save to knowledge base" on a response
  → System creates a new document from the response
  → Document is chunked, embedded, and indexed
  → Knowledge base grows from use
```

**Implementation:**

1. Add a `POST /api/v1/corpora/:id/save-from-chat` endpoint that accepts:
   - `content` (the chat response text)
   - `title` (auto-generated or user-provided)
   - `session_id` (links back to the chat session for provenance)
   - `source_chunks` (the chunk IDs that were cited, for attribution)

2. In the chat UI, add a "Save insight" button on each assistant response. Clicking it:
   - Opens a small modal: auto-generated title (editable), preview of content
   - On confirm: calls the API, creates a document, triggers incremental indexing
   - Shows confirmation: "Added to your knowledge base"

3. The saved document includes metadata:
   ```json
   {
     "source_type": "chat_insight",
     "derived_from": ["chunk-id-1", "chunk-id-2"],
     "chat_session": "session-abc",
     "created_via": "chat_writeback"
   }
   ```

**Scope:** ~1-2 days. Mostly UI work + one new API endpoint. The ingestion pipeline already handles single-document addition.

---

## 2. URL/RSS Auto-Sync

**What:** Subscribe to URLs or RSS feeds. Noosphere periodically checks for new content and ingests it automatically.

**Why this matters:** GBrain's "dream cycle" automatically ingests from meetings, emails, and conversations. Karpathy manually drops files but the LLM does all the processing. Neither requires the user to remember to upload. Many knowledge creators publish via blogs, newsletters, or RSS — auto-sync means their Noosphere knowledge base stays current without manual effort.

**Design:**

```
Creator adds a feed source (URL or RSS)
  → Noosphere stores the source config
  → Background job checks periodically (configurable: hourly/daily/weekly)
  → New content is fetched, converted to markdown, ingested
  → Existing content is skipped (content-hash dedup, already implemented)
  → Creator sees "Last synced: 2h ago" in the UI
```

**Implementation:**

1. New database table `feed_sources`:
   ```sql
   CREATE TABLE feed_sources (
     id TEXT PRIMARY KEY,
     corpus_id TEXT NOT NULL REFERENCES corpora(id),
     source_type TEXT NOT NULL,  -- 'rss', 'url', 'sitemap'
     url TEXT NOT NULL,
     check_interval INTEGER DEFAULT 86400,  -- seconds
     last_checked_at TEXT,
     last_new_content_at TEXT,
     etag TEXT,  -- HTTP ETag for conditional fetch
     status TEXT DEFAULT 'active'  -- active, paused, error
   );
   ```

2. Background sync worker (can be a simple threading.Timer or APScheduler):
   - On each tick: query all `active` sources past their `check_interval`
   - For RSS: parse feed, compare entry URLs against existing documents
   - For URL: fetch page, compare content hash against stored hash
   - For new content: run through existing ingestion pipeline
   - Update `last_checked_at`

3. CLI: `noosphere feed add <corpus> <url> --interval daily`

4. Web UI: "Add feed source" in corpus detail, shows list of subscribed feeds with sync status

5. REST API:
   ```
   POST   /api/v1/corpora/:id/feeds          -- add a feed source
   GET    /api/v1/corpora/:id/feeds          -- list feed sources
   DELETE /api/v1/corpora/:id/feeds/:feed_id -- remove a feed source
   POST   /api/v1/corpora/:id/feeds/:feed_id/sync  -- trigger manual sync
   ```

**Scope:** ~3-4 days. RSS parsing (feedparser), background scheduler, UI for feed management.

---

## 3. LLM Compilation Layer (Knowledge Compiler)

**What:** An optional LLM pass that generates derived knowledge artifacts — summary pages, concept extractions, cross-document links — from the raw documents in a knowledge base.

**Why this matters:** This is Karpathy's core innovation. His LLM Wiki has three layers: raw sources (immutable), compiled wiki (LLM-maintained), and a schema that guides compilation. The LLM doesn't just store documents — it actively structures, cross-links, and derives insights. This is what turns a pile of documents into a living knowledge system.

Noosphere currently only does: ingest → chunk → embed → search. There is no "understanding" layer. Adding one would dramatically improve search quality and make knowledge bases more useful.

**Design:**

```
Knowledge base has N documents
  → User triggers "Compile" (or it runs automatically after ingest)
  → LLM reads all documents (or new ones since last compile)
  → LLM generates:
      1. Concept index — key concepts with definitions and which docs mention them
      2. Summary pages — one-paragraph summaries of each document
      3. Cross-links — "Document A relates to Document B because..."
      4. Knowledge graph — entities and relationships extracted from content
  → Derived artifacts are stored as special document types (source_type: "compiled")
  → Search can now leverage both raw chunks AND compiled summaries
```

**Implementation:**

1. New document metadata field `source_type`: `"original"` | `"compiled_summary"` | `"compiled_concept"` | `"compiled_crosslink"`

2. Compilation pipeline:
   - Read all documents (or delta since last compile)
   - For each document: generate a structured summary via LLM (title, key points, entities, related concepts)
   - Across all documents: generate a concept index (concept → list of documents that discuss it)
   - Store compiled artifacts as documents in the same corpus (tagged as compiled)
   - Update `topics.json` with extracted concepts

3. CLI: `noosphere compile --corpus my-blog`

4. Web UI: "Compile knowledge base" button in corpus detail. Shows compilation status and last compiled time.

5. The existing search pipeline automatically benefits — compiled summaries and concept pages become searchable chunks alongside the original content.

**Scope:** ~4-5 days. LLM integration (reuse existing chat LLM config), prompt engineering for compilation, storage of derived artifacts.

**Note:** This is the highest-impact feature for knowledge base quality but also the most complex. Start with simple document summaries and concept extraction; cross-links and knowledge graph can be iterative.

---

## 4. Incremental Enrichment (Dream Cycle)

**What:** A scheduled background process that autonomously improves the knowledge base — finding gaps, detecting stale content, suggesting new connections, and running health checks.

**Why this matters:** GBrain's "dream cycle" runs overnight: it scans recent conversations, enriches entity pages, fixes broken citations, consolidates memory, and creates cross-references. Karpathy's "lint" operation does similar periodic health checks. This is what makes a knowledge base feel alive rather than static.

**Design:**

```
Scheduled job (nightly or configurable)
  → For each knowledge base:
      1. Stale detection: flag documents not updated in >N days
      2. Gap analysis: LLM reviews concept index, identifies topics mentioned
         but not well-covered
      3. Cross-link refresh: re-run cross-linking on recently added documents
      4. Quality check: find duplicate content, contradictions, orphan documents
      5. Report: generate a "health report" visible in the UI
```

**Implementation:**

1. Depends on Feature 3 (LLM Compilation Layer) — the enrichment cycle is essentially a re-run of compilation + additional quality checks.

2. New table `enrichment_runs`:
   ```sql
   CREATE TABLE enrichment_runs (
     id TEXT PRIMARY KEY,
     corpus_id TEXT NOT NULL,
     started_at TEXT,
     completed_at TEXT,
     status TEXT,  -- running, completed, failed
     report JSON   -- structured health report
   );
   ```

3. Enrichment tasks:
   - **Stale detection**: already partially implemented (freshness signals in search). Extend to generate a report.
   - **Gap analysis**: LLM prompt: "Given these concepts and documents, what important topics are missing or under-covered?"
   - **Dedup**: cosine similarity between document embeddings to find near-duplicates
   - **Health report**: JSON summary with actionable items, visible in corpus detail UI

4. CLI: `noosphere enrich --corpus my-blog`
5. Scheduler: reuse the same background scheduler from Feature 2

**Scope:** ~3-4 days (after Feature 3 is built). Heavily reuses compilation infrastructure.

---

## Implementation order

```
Feature 1: Chat Write-Back          [~2 days]  ← Start here (quick win, high visibility)
Feature 2: URL/RSS Auto-Sync        [~3 days]  ← Next (enables auto-growth)
Feature 3: LLM Compilation          [~5 days]  ← Core differentiator
Feature 4: Incremental Enrichment   [~3 days]  ← Builds on Feature 3
                                     --------
                              Total: ~13 days
```

**Rationale for order:**
- Feature 1 is the smallest change with the most visible impact — it immediately makes chat feel like a knowledge-building tool, not just a search interface.
- Feature 2 enables passive growth, which is the single biggest behavioral difference between Noosphere and GBrain/Karpathy.
- Feature 3 is the deepest capability — it's what makes Noosphere more than a "chunk and search" tool. But it's also the most complex, so it should come after the quick wins are shipped.
- Feature 4 depends on Feature 3 and is the "dream cycle" — the thing that makes knowledge bases feel alive.

---

## What we intentionally skip

Some GBrain/Karpathy features are NOT appropriate for Noosphere:

- **Structured entity schemas** (People, Companies, Meetings) — GBrain is a personal CRM/memory system. Noosphere is a knowledge publishing platform. Structured entities are valuable for GBrain's use case but would be over-engineering for general knowledge publishing.
- **Calendar/email/meeting integration** — Same reasoning. These are personal productivity features, not knowledge publishing features.
- **Agent write-back from external agents** — GBrain lets agents write back after every interaction. For Noosphere, the knowledge base owner should control what gets added. Chat write-back (Feature 1) gives the user the choice; automatic agent write-back would be a security/quality concern for a multi-user publishing platform.
