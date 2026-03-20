# Noosphere

> Expand the scope and scale of collective enlightenment.

**Turn any knowledge base into an agent-readable, permissioned, monetizable corpus.**

Noosphere is an open platform that lets anyone convert their personal or organizational knowledge — blogs, newsletters, podcasts, docs, notes — into a structured, agent-friendly format that AI agents can discover, query, and cite. Creators control access: free, private, or paid.

---

## Origin story

In March 2026, Lenny Rachitsky ([x.com/lennysan/status/2033958104967352587](https://x.com/lennysan/status/2033958104967352587)) converted his 300+ podcast transcripts and 350 newsletter posts into agent-friendly Markdown, published a GitHub repo, built an MCP server, and invited people to build products on top of his archive. He open-sourced a free starter pack (10 posts, 50 transcripts) and gated the full archive behind a paid subscription.

This was a manual, one-off effort by one creator. Noosphere asks: **what if anyone could do this?**

The trend is clear. More products are being built for agents. More knowledge needs to become machine-readable. But today, making your knowledge agent-friendly requires significant technical effort: structuring content, chunking, embedding, hosting an MCP server, setting up access control, handling payments. Noosphere standardizes and democratizes this entire pipeline.

## Connection to Feynman

Noosphere is inspired by and connected to [Feynman](https://github.com/steveyeow/feynman), an open-source project that lets people chat with books and learn with an evolving network of agent-simulated great minds in a navigable knowledge space (the Noosphere).

The relationship:

- **Noosphere** is the publishing layer — turn your knowledge into an agent-readable corpus
- **Feynman** is one consumer — read with these corpora as source-grounded minds in the Noosphere

Noosphere corpora can be consumed by Feynman, by other AI products, by coding agents, by research tools, or by any MCP/API-compatible client. Feynman is one important but not exclusive consumer.

---

## Mission

**Expand the scope and scale of collective enlightenment.**

We believe that:

- Human knowledge should not be locked inside formats that only humans can navigate.
- Every person, community, and organization should be able to make their knowledge accessible to agents — easily, safely, and on their own terms.
- The emerging agent ecosystem needs trusted, structured, citable knowledge sources — not just raw web scraping.
- Creators should control access to their knowledge and be able to monetize it if they choose.
- An open protocol for agent-readable knowledge will create more value than any closed platform alone.

## Design principles

1. **Knowledge is the primitive, not content.** We are not building a CMS or a file host. We are building a system that turns unstructured knowledge into structured, queryable, citable corpora that agents can reason over.

2. **Agent-native by default.** Every corpus is designed to be consumed by agents first. Human-readable interfaces are important but secondary. The primary interface is MCP/API.

3. **Creator sovereignty.** The creator owns their corpus. They decide: public, private, or paid. They decide the price, the access model, the license terms. The platform enforces their choices.

4. **Source-grounded, not generative.** When an agent queries a Noosphere corpus, the response should be grounded in retrieved passages with citations. Not hallucinated summaries. Not persona roleplay. Real source material, traceable to specific documents.

5. **Open core, commercial services.** The protocol, conversion tools, and self-hosted node are open-source. Managed hosting, payments, analytics, and discovery are commercial services.

6. **Interoperability.** Noosphere corpora should work with any MCP-compatible client, any RAG pipeline, any agent framework. No lock-in.

---

## Product architecture

### Two layers

```
┌─────────────────────────────────────────────────────────┐
│                    COMMERCIAL LAYER                      │
│                                                         │
│  Managed hosting · Creator dashboard · Payments/billing │
│  Access control · Analytics · Discovery/marketplace     │
│  Premium integrations · Enterprise features · SLA       │
├─────────────────────────────────────────────────────────┤
│                     OPEN CORE LAYER                      │
│                                                         │
│  Ingestion pipeline · Corpus format · Chunking/embedding│
│  Retrieval engine · Citation system · MCP server        │
│  REST API · Self-hosted node · CLI tools · SDKs         │
│  Protocol specification                                 │
└─────────────────────────────────────────────────────────┘
```

### Open core (open-source, MIT)

What anyone can self-host and use for free:

| Component | Description |
|-----------|-------------|
| **Ingestion pipeline** | Convert Markdown, PDF, HTML, plain text, JSON, RSS into a structured corpus |
| **Corpus format** | Standardized schema for documents, metadata, chunks, embeddings, citations |
| **Chunking engine** | Split documents into semantically meaningful chunks with metadata |
| **Embedding engine** | Generate vector embeddings for all chunks (pluggable providers) |
| **Retrieval engine** | Semantic search over corpus with cosine similarity |
| **Citation system** | Every retrieval result includes source document, chunk location, and provenance |
| **MCP server** | Model Context Protocol endpoint that agents can connect to |
| **REST API** | Standard HTTP endpoints for querying, listing, and browsing a corpus |
| **CLI tools** | Command-line tools for ingesting, indexing, and serving a corpus locally |
| **Self-hosted node** | Run a complete Noosphere node on your own infrastructure |

### Commercial layer (hosted service)

What the hosted platform adds:

| Component | Description |
|-----------|-------------|
| **Managed hosting** | Upload and serve corpora without managing infrastructure |
| **Creator dashboard** | Web UI for managing corpora, viewing analytics, configuring access |
| **Access control** | Public, private, token-gated, subscriber-only, or paid access |
| **Payments** | Stripe-based billing: per-query, per-month, per-corpus, or custom pricing |
| **Creator payouts** | Revenue sharing for creators who monetize their corpora |
| **Analytics** | Who is querying, which topics, how often, which agents |
| **Discovery** | Directory/marketplace where agents and users can find published corpora |
| **Premium integrations** | Auto-sync from Substack, Notion, Google Docs, Obsidian, Ghost, WordPress |
| **Enterprise** | Team workspaces, audit logs, SSO, compliance, private registries |

---

## Corpus format specification

A Noosphere corpus is a structured knowledge package with a well-defined schema.

### Corpus structure

```
my-corpus/
├── noosphere.json          # Corpus manifest
├── documents/
│   ├── doc-001.md          # Source documents (Markdown)
│   ├── doc-002.md
│   └── ...
├── index/
│   ├── chunks.jsonl        # Chunked documents with metadata
│   └── embeddings.bin      # Vector embeddings (binary, float32)
└── meta/
    ├── topics.json         # Extracted topics and themes
    └── stats.json          # Corpus statistics
```

### Manifest schema (`noosphere.json`)

```json
{
  "schema_version": "1.0",
  "corpus_id": "lenny-rachitsky-archive",
  "name": "Lenny's Newsletter & Podcast Archive",
  "description": "300+ podcast transcripts and newsletter posts on product, growth, and startups.",
  "author": {
    "name": "Lenny Rachitsky",
    "url": "https://www.lennysnewsletter.com",
    "avatar_url": ""
  },
  "created_at": "2026-03-19T00:00:00Z",
  "updated_at": "2026-03-19T00:00:00Z",
  "document_count": 60,
  "chunk_count": 2400,
  "word_count": 950000,
  "embedding_model": "text-embedding-3-small",
  "embedding_dim": 1536,
  "language": "en",
  "license": "personal-use",
  "tags": ["product", "growth", "startups", "AI", "PM"],
  "access": {
    "level": "public",
    "pricing": null
  },
  "source": {
    "type": "manual",
    "origin": "https://github.com/LennysNewsletter/lennys-newsletterpodcastdata"
  },
  "documents": [
    {
      "id": "doc-001",
      "title": "How Duolingo reignited user growth",
      "filename": "documents/doc-001.md",
      "type": "newsletter",
      "date": "2023-02-28",
      "word_count": 4812,
      "tags": ["growth", "strategy"],
      "metadata": {
        "subtitle": "The story behind Duolingo's 350% growth acceleration"
      }
    }
  ]
}
```

### Chunk schema (`chunks.jsonl`)

Each line is a JSON object:

```json
{
  "chunk_id": "doc-001-chunk-003",
  "document_id": "doc-001",
  "chunk_index": 3,
  "text": "The key insight was that streaks created a daily habit loop...",
  "char_start": 2401,
  "char_end": 3200,
  "word_count": 142,
  "embedding_offset": 3072,
  "metadata": {
    "section": "The streak mechanism",
    "document_title": "How Duolingo reignited user growth",
    "document_date": "2023-02-28"
  }
}
```

### Access levels

| Level | Description |
|-------|-------------|
| `public` | Anyone can query. No authentication required. |
| `private` | Only the owner can query. Not discoverable. |
| `token` | Requires a valid access token. Owner distributes tokens. |
| `subscription` | Requires an active subscription (managed by the platform). |
| `paid` | Pay-per-query or pay-per-month. Stripe-based. |

---

## Agent access interface

### MCP (Model Context Protocol)

Noosphere exposes each corpus as an MCP server. Any MCP-compatible client (Claude, Cursor, Codex, custom agents) can connect.

MCP tools exposed per corpus:

| Tool | Description |
|------|-------------|
| `search` | Semantic search across the corpus. Returns ranked chunks with citations. |
| `get_document` | Retrieve a full document by ID. |
| `list_documents` | List all documents with metadata. |
| `get_topics` | List extracted topics and themes. |
| `get_stats` | Corpus statistics (document count, word count, last updated). |
| `get_manifest` | Full corpus manifest. |

### REST API

```
GET    /api/v1/corpora                          # List available corpora
GET    /api/v1/corpora/:id                      # Get corpus manifest
GET    /api/v1/corpora/:id/documents            # List documents
GET    /api/v1/corpora/:id/documents/:doc_id    # Get a document
POST   /api/v1/corpora/:id/search               # Semantic search
GET    /api/v1/corpora/:id/topics               # List topics
GET    /api/v1/corpora/:id/stats                # Corpus statistics
```

Search request:

```json
POST /api/v1/corpora/lenny-archive/search
{
  "query": "How should startups think about pricing?",
  "top_k": 5,
  "include_context": true
}
```

Search response:

```json
{
  "results": [
    {
      "chunk_id": "doc-042-chunk-007",
      "score": 0.87,
      "text": "The biggest mistake I see in pricing is...",
      "citation": {
        "document_title": "Pricing your AI product",
        "document_id": "doc-042",
        "author": "Madhavan Ramanujam (guest)",
        "date": "2025-07-27",
        "char_range": [4200, 5100]
      }
    }
  ],
  "usage": {
    "tokens_used": 128,
    "queries_remaining": null
  }
}
```

---

## Ingestion pipeline

### Supported input formats (v1)

| Format | Source |
|--------|--------|
| Markdown files | Local directory, GitHub repo |
| Plain text | Upload |
| PDF | Upload |
| HTML | URL fetch |
| RSS/Atom | Feed URL |
| JSON index + Markdown | Lenny-style dataset structure |

### Pipeline stages

```
Input sources
    │
    ▼
┌──────────────┐
│   Ingest     │  Read files, fetch URLs, parse formats
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Clean      │  Strip HTML, normalize whitespace, extract metadata
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Chunk      │  Split into semantic chunks (500-1000 tokens)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Embed      │  Generate vector embeddings (pluggable provider)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Index      │  Build search index, extract topics, compute stats
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Publish    │  Write corpus package, start MCP/API server
└──────────────┘
```

### CLI interface

```bash
# Initialize a new corpus from a directory of Markdown files
noosphere init ./my-blog-posts --name "My Blog" --author "Jane Doe"

# Ingest additional documents
noosphere ingest ./more-posts --corpus my-blog

# Re-index (re-chunk, re-embed)
noosphere index --corpus my-blog

# Serve locally (MCP + REST API)
noosphere serve --corpus my-blog --port 8420

# Export corpus package
noosphere export --corpus my-blog --output ./my-blog-corpus.zip

# Publish to Noosphere Cloud (commercial)
noosphere publish --corpus my-blog --access public
```

---

## Technical architecture

### Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python / FastAPI |
| Database | SQLite (self-hosted) / PostgreSQL (cloud) |
| Embeddings | Pluggable: OpenAI, Gemini, local models |
| Vector storage | Embedded (NumPy cosine similarity, same as Feynman) |
| MCP server | Python MCP SDK |
| CLI | Click / Typer |
| Frontend (cloud) | React or vanilla JS (TBD) |
| Payments | Stripe |
| Auth | API keys (self-hosted) / Supabase Auth (cloud) |

### Database schema (core tables)

```sql
-- Corpora: each corpus is a knowledge base
CREATE TABLE corpora (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    description TEXT,
    author_name TEXT,
    author_url TEXT,
    document_count INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    word_count INTEGER DEFAULT 0,
    embedding_model TEXT,
    embedding_dim INTEGER,
    language TEXT DEFAULT 'en',
    license TEXT DEFAULT 'personal-use',
    tags TEXT,                          -- JSON array
    access_level TEXT DEFAULT 'public', -- public | private | token | subscription | paid
    pricing_json TEXT,                  -- JSON: pricing config if access_level is paid
    status TEXT DEFAULT 'draft',        -- draft | indexing | ready | error
    owner_id TEXT,                      -- user ID (cloud only)
    source_type TEXT,                   -- manual | github | rss | substack | notion
    source_url TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Documents within a corpus
CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    corpus_id TEXT NOT NULL REFERENCES corpora(id),
    title TEXT NOT NULL,
    content TEXT NOT NULL,              -- full document text
    doc_type TEXT,                      -- newsletter | podcast | blog | doc | note
    date TEXT,
    word_count INTEGER,
    tags TEXT,                          -- JSON array
    metadata_json TEXT,                 -- flexible metadata
    created_at TEXT NOT NULL
);
CREATE INDEX idx_documents_corpus ON documents(corpus_id);

-- Chunks: embedded segments for retrieval
CREATE TABLE chunks (
    id TEXT PRIMARY KEY,
    corpus_id TEXT NOT NULL REFERENCES corpora(id),
    document_id TEXT NOT NULL REFERENCES documents(id),
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    char_start INTEGER,
    char_end INTEGER,
    vector BLOB NOT NULL,              -- float32 embedding
    dim INTEGER NOT NULL,
    norm REAL NOT NULL,
    metadata_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_chunks_corpus ON chunks(corpus_id);
CREATE INDEX idx_chunks_document ON chunks(document_id);

-- Access tokens (for token-gated corpora)
CREATE TABLE access_tokens (
    id TEXT PRIMARY KEY,
    corpus_id TEXT NOT NULL REFERENCES corpora(id),
    token_hash TEXT NOT NULL,           -- hashed token
    label TEXT,                         -- human-readable label
    permissions TEXT DEFAULT 'read',    -- read | admin
    usage_count INTEGER DEFAULT 0,
    last_used_at TEXT,
    expires_at TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_tokens_corpus ON access_tokens(corpus_id);

-- Query logs (for analytics)
CREATE TABLE query_logs (
    id TEXT PRIMARY KEY,
    corpus_id TEXT NOT NULL REFERENCES corpora(id),
    query_text TEXT,
    result_count INTEGER,
    token_id TEXT,                      -- which token was used
    agent_id TEXT,                      -- agent identifier if provided
    latency_ms INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_queries_corpus ON query_logs(corpus_id, created_at);
```

---

## Implementation roadmap

### Phase 1: Open core MVP

Goal: a working open-source tool that can ingest a directory of Markdown files and serve them as a queryable, citable corpus via MCP and REST API.

Deliverables:
- [ ] Corpus format specification (noosphere.json schema)
- [ ] Ingestion pipeline (Markdown, plain text, JSON+Markdown like Lenny's format)
- [ ] Chunking engine with metadata preservation
- [ ] Embedding engine (OpenAI + Gemini providers)
- [ ] Retrieval engine (cosine similarity search with citations)
- [ ] MCP server (search, get_document, list_documents)
- [ ] REST API (search, documents, stats)
- [ ] CLI (init, ingest, index, serve, export)
- [ ] Lenny starter dataset as example corpus
- [ ] README with quick start guide
- [ ] MIT license

Demo: ingest Lenny's free starter dataset, serve it locally, query it from Claude/Cursor via MCP.

### Phase 2: Multi-corpus and access control

Goal: support multiple corpora, basic access control, and a simple web dashboard.

Deliverables:
- [ ] Multi-corpus support (multiple corpora on one node)
- [ ] Access levels (public, private, token-gated)
- [ ] Token management (create, revoke, track usage)
- [ ] Query logging and basic analytics
- [ ] Web dashboard for managing corpora
- [ ] PDF and HTML ingestion
- [ ] RSS/feed auto-sync
- [ ] Topic extraction

### Phase 3: Commercial hosted platform

Goal: a hosted version where creators can sign up, upload corpora, and configure access/pricing.

Deliverables:
- [ ] Hosted platform (Vercel/Railway + PostgreSQL)
- [ ] User auth (Supabase)
- [ ] Creator onboarding flow
- [ ] Stripe integration for paid corpora
- [ ] Pay-per-query and subscription billing
- [ ] Creator payouts
- [ ] Usage analytics dashboard
- [ ] Public corpus directory/discovery
- [ ] Embeddable chat widget for corpus owners

### Phase 4: Ecosystem and integrations

Goal: make Noosphere the standard way to publish knowledge for agents.

Deliverables:
- [ ] Auto-sync integrations (Substack, Notion, Ghost, WordPress, Obsidian)
- [ ] Corpus-to-corpus cross-references
- [ ] Federated discovery (multiple Noosphere nodes can discover each other)
- [ ] Feynman integration (import Noosphere corpus as a mind in Feynman)
- [ ] SDKs (Python, JavaScript, Go)
- [ ] Enterprise features (team workspaces, SSO, audit logs)

---

## How Lenny's dataset maps to Noosphere

Lenny's free starter pack is the first example corpus. Here is how it maps:

| Lenny's structure | Noosphere equivalent |
|---|---|
| `01-start-here/index.json` | `noosphere.json` manifest |
| `02-newsletters/*.md` | `documents/` with `type: "newsletter"` |
| `03-podcasts/*.md` | `documents/` with `type: "podcast"` |
| `01-start-here/LICENSE.md` | `license` field in manifest |
| Free starter pack | `access.level: "public"` |
| Paid full archive | `access.level: "subscription"` or `"paid"` |
| Starter MCP | Noosphere MCP server |

The ingestion pipeline should auto-detect Lenny's format (JSON index + Markdown directory) and convert it into a Noosphere corpus with a single command:

```bash
noosphere init ./lennys-newsletterpodcastdata-starter \
  --name "Lenny's Newsletter & Podcast (Starter)" \
  --author "Lenny Rachitsky" \
  --format lenny
```

---

## Business model

### Free tier (open-source, self-hosted)

- Unlimited corpora
- Unlimited queries
- MCP + REST API
- Self-hosted
- Community support

### Cloud free tier

- 1 corpus
- 100 documents
- 1,000 queries/month
- Public access only
- Basic analytics

### Cloud pro tier

- Unlimited corpora
- Unlimited documents
- Unlimited queries
- All access levels (public, private, token, paid)
- Stripe payments integration
- Full analytics
- Premium integrations
- Priority support

### Platform fee

For paid corpora, the platform takes a percentage of creator revenue (e.g., 10-20%), similar to app store or marketplace models.

---

## Competitive positioning

| Existing solution | What it does | What Noosphere adds |
|---|---|---|
| Lenny's Data | One creator, manual setup | Platform for anyone, automated pipeline |
| RAG-as-a-service (Pinecone, Weaviate) | Vector DB infrastructure | Full pipeline from content to agent access |
| Notion/Obsidian publish | Human-readable publishing | Agent-readable publishing |
| Substack/Ghost | Newsletter platform | Agent-native knowledge platform |
| MCP servers | Protocol specification | Full platform with ingestion, hosting, payments |

Noosphere is not competing with vector databases or content platforms. It sits at the intersection: **the platform that turns human knowledge into agent-readable infrastructure, with creator control and monetization built in.**

---

## Naming and brand

**Noosphere** — from Pierre Teilhard de Chardin's concept of a planetary layer of connected human thought.

The name signals:
- collective knowledge, not just individual content
- a living network, not a static archive
- connection between minds, not isolation
- a serious intellectual foundation

Tagline options:
- *Publish your knowledge for agents.*
- *Turn any knowledge base into agent infrastructure.*
- *The open platform for agent-readable knowledge.*
- *Make your knowledge part of the Noosphere.*

---

## Summary

Noosphere is an open platform that lets anyone turn their knowledge base into a structured, agent-readable corpus. Creators control access: free, private, or paid. The open core handles ingestion, indexing, retrieval, and serving via MCP/API. The commercial layer adds hosting, payments, analytics, and discovery.

The mission is to expand the scope and scale of collective enlightenment — by making it easy, safe, and rewarding for anyone to contribute their knowledge to the emerging agent ecosystem.
