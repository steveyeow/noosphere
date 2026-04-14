# Noosphere

> The knowledge network for the agent era.

Noosphere lets you publish your knowledge — papers, blogs, newsletters, notes — as a living knowledge base any AI agent can discover, query, and cite. It grows over time as you add content. Share it free, keep it private, or charge for access.

---

## Origin story

A new kind of knowledge tool is emerging. People like [Andrej Karpathy](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) (LLM Wiki), [Garry Tan](https://github.com/garrytan/gbrain) (GBrain), and countless others are building personal knowledge bases that their AI agents can read — structured wikis and brains maintained by LLMs, growing from conversations and documents over time.

This is clearly where knowledge is going. But there are two problems:

**1. Every knowledge base is an island.** Karpathy's wiki can't talk to Garry's brain. There is no discovery layer — no way for an agent to search across multiple people's knowledge bases to find the right expert knowledge.

**2. Building one requires serious technical skill.** Structuring content, chunking, embedding, hosting an MCP server, managing vector search, setting up access control — each personal knowledge base is a one-off engineering project. Most creators, researchers, and domain experts simply can't do this.

Noosphere solves both problems. It is the infrastructure layer that:
- **Democratizes** what Karpathy and Garry Tan built — anyone can create an agent-readable knowledge base by uploading files or pasting a URL, with zero technical setup.
- **Connects** isolated knowledge bases into a shared discovery network — agents can search across all public knowledge bases at once, finding the right expert knowledge wherever it lives.

```
                    Agent-native
                        ↑
                        |
   Karpathy LLM Wiki   |    ← Noosphere
   GBrain              |    (networked + democratized)
                        |
  ──────────────────────┼──────────────────── Anyone can publish
   Closed /             |
   platform-controlled  |
                        |    HuggingFace
  Google Scholar        |    arXiv
  Semantic Scholar      |    Wikipedia
                        |
         JSTOR          |
         Elsevier       |
                        ↓
                    Human-readable
```

Karpathy's LLM Wiki and Garry Tan's GBrain sit in the upper-left: agent-native, but single-user and technically demanding. Noosphere occupies the upper-right: agent-native AND open to anyone, with a network that connects them all.

## Connection to Feynman

Noosphere is inspired by and connected to [Feynman](https://github.com/steveyeow/feynman), an open-source project that lets people chat with books and learn with an evolving network of agent-simulated great minds in a navigable knowledge space (the Noosphere).

Both are independent open-core products with the same architecture:

| | Noosphere | Feynman |
|---|---|---|
| **What** | Knowledge publishing infrastructure | Chat-with-books product |
| **MIT core** | Ingest, chunk, embed, search, MCP, API, CLI, Web UI | Chat, RAG, minds, library, Web UI |
| **BSL commercial** | `noosphere/cloud/` (auth, quota, stripe) | `app/pro/` (auth, quota, stripe) |
| **Self-hosted** | Full functionality, free forever | Full functionality, free forever |
| **Repo** | Separate repo | Separate repo |

The relationship is **producer-consumer**, not parent-child:

- **Noosphere** publishes knowledge as agent-readable corpora
- **Feynman** is one consumer — it can use Noosphere corpora as source-grounded minds

Integration is optional. Feynman can import `noosphere` as a Python library (same-process, zero latency) or connect to a remote Noosphere instance via API (cross-network). Noosphere corpora can be consumed by any MCP/API-compatible agent or tool.

---

## Mission

**The knowledge network for the agent era.**

Personal AI knowledge bases are the future — but isolated knowledge bases are a transitional state. The real value comes when they're connected into a network, and when creators can control and monetize access.

Four things define Noosphere:

1. **A connected network.** Every knowledge base can join a global discovery network. An agent helping a startup founder can draw on the best thinking from thousands of domain experts. The network makes every individual knowledge base more valuable — and creates a marketplace where knowledge finds the people (and agents) who need it.
2. **Agent-readable by design.** Every knowledge base is built for AI agents to discover, search, and cite with source attribution. Agents are the primary consumers. The web UI exists for creators to manage their knowledge.
3. **Living knowledge.** Knowledge bases grow over time — from chat conversations, RSS feeds, URL imports, and LLM-powered compilation. They are compounding knowledge systems, not static file dumps.
4. **Creators get paid.** Open your knowledge to everyone, or set it to paid. Lenny Rachitsky opened part of his newsletter to agents for free but kept the full archive behind a subscription. Domain experts, researchers, consultants — anyone with valuable knowledge can monetize it through the network. Organizations and agents pay for the expertise they need, without hiring consultants to train proprietary models.

We believe that:

- Personal knowledge bases will become as common as personal websites — and they need a network, not just tools.
- The emerging agent ecosystem needs trusted, structured, citable knowledge sources — not just raw web scraping.
- Isolated knowledge bases are a transitional state. The network is the product.
- Creators should own and control access to their knowledge — including the right to get paid for it.

## Design principles

1. **Knowledge is the primitive, not content.** We are not building a CMS or a file host. We are building a system that turns unstructured knowledge into structured, queryable, citable corpora that agents can reason over.

2. **Agent-native by default.** Every corpus is designed to be consumed by agents first. The web UI exists for creators to manage their knowledge and see how agents are using it. The primary interface for consumers is MCP/API.

3. **Creator sovereignty.** The creator owns their corpus. They decide: public, private, token-gated, or paid. They decide the price, the access model, the license terms. The platform enforces their choices — whether self-hosted or cloud.

4. **Source-grounded, not generative.** When an agent queries a Noosphere corpus, the response should be grounded in retrieved passages with citations. Not hallucinated summaries. Real source material, traceable to specific documents.

5. **Open core, commercial convenience.** The full product is open-source and self-hostable — including paid access control. The commercial layer adds hosting convenience, not exclusive features.

6. **One network.** Self-hosted and cloud-hosted corpora are equal participants in the Noosphere. The registry connects them all. Content stays on the creator's infrastructure; only metadata is shared for discovery.

---

## Knowledge lifecycle (growth, fusion, maintenance)

Personal LLM wikis and agent brains emphasize **continuous compilation**: raw inputs → structured pages, chat that writes back, and periodic “lint” or overnight enrichment. Noosphere’s first job remains **publishable, citable corpora for agents**; the lifecycle features below **narrow the gap** with those workflows without changing the core product (network + APIs + access control).

| Pattern (LLM wiki / agent brain) | Noosphere capability |
|----------------------------------|------------------------|
| Raw + compiled layers | **Compile:** `POST /corpora/{id}/compile` — retrieves top passages, calls the chat LLM to write a single Markdown **concept** document with sections (summary, key points, sources). Grounded in stored docs; does not replace human judgment for contradictions. |
| Chat → knowledge | **Capture:** `POST /corpora/{id}/capture` — saves arbitrary Markdown (e.g. assistant reply) as `doc_type=capture` with optional `question` + `session_id` metadata. Web UI: **Save to corpus** on each assistant message. |
| Feeds / recurring inflow | **RSS/Atom:** `POST /corpora/{id}/ingest-feed` — fetches feed, dedupes by `rss_guid` / link metadata, ingests new entries (fetch URL when possible; else summary body). CLI: `noosphere ingest-feed`. |
| Batch URLs | **`POST /corpora/{id}/ingest-urls`** — up to 40 URLs per request. CLI: `noosphere ingest-urls`. |
| Lint / health / repair | **`GET /corpora/{id}/knowledge-health`** — documents with no chunks, suspected empty `]()` links, counts of capture/concept docs, documents older than `stale_threshold_days`. **`POST /corpora/{id}/maintain`** — re-runs `index_corpus` (optional `force` for full rebuild). |
| Nightly “dream” enrichment | **Not implemented** — possible future job using the same LLM stack; today, run `maintain` + `compile` on a schedule (e.g. cron) if desired. |
| Automatic meeting/email/calendar ingest | **Out of scope for open core** — requires deep integrations; cloud roadmap may add connectors. |

**Honest boundary:** Noosphere still does not auto-ingest your private digital life the way a personal OpenClaw + brain stack can. It **does** support **networked publishing**, **lower-friction inflow** (feeds, batch URLs, captures, compile), and **observable corpus health**.

---

## Product architecture

### Single repo, open core with commercial shim

Following the same architecture as Feynman, Noosphere is a single repository with clear license boundaries:

```
noosphere/
├── LICENSE                    ← MIT (root)
├── noosphere/
│   ├── core/                  ← MIT — ingestion, chunking, embedding, retrieval
│   ├── api/                   ← MIT — REST API + web frontend
│   ├── cli/                   ← MIT — CLI commands
│   ├── mcp/                   ← MIT — MCP server
│   └── cloud/                 ← BSL — managed auth, quota, stripe connect (Phase 2+)
│       ├── LICENSE            ← BSL 1.1
│       ├── auth.py
│       ├── quota.py
│       └── stripe.py
├── tests/
├── requirements.txt
└── README.md
```

### Self-hosted vs Cloud

| | Self-hosted (open source) | Cloud (commercial) |
|---|---|---|
| Code | Same repo | Same repo |
| Database | SQLite | PostgreSQL |
| Embedding API keys | User's own | Platform's |
| Usage limits | None | Free/Pro tier quotas |
| Set corpus to paid | **Yes** (user's own Stripe) | Yes (Stripe Connect) |
| Platform commission | **0%** | 10% on paid corpus revenue |
| Registry participation | Yes (opt-in per corpus) | Automatic |
| Who pays infra costs | User | Us (covered by subscription) |

The open-source version is the **full product**, not a crippled trial. Self-hosted users can do everything cloud users can — including monetizing their corpora. The cloud version sells **convenience** (we run the infra) and charges a commission only when money flows through our payment rails.

### Interface layers

```
Layer 4:  MCP Server          ← Agent-native protocol (Claude, Cursor, Codex)
Layer 3:  REST API            ← Universal HTTP interface (any client)
Layer 2:  CLI                 ← Developer/creator tool (ingest, index, serve)
Layer 1:  Corpus Format       ← Structured data (Markdown + chunks + embeddings)
```

All layers are needed:
- **Markdown** is the content storage format, not an access interface
- **CLI** is the creator-side tool for building and managing corpora
- **REST API** is the universal access interface — any agent, app, or script can call HTTP
- **MCP** is the agent-native discovery and tool-use protocol that sits on top

MCP and REST API share the same core logic. The CLI calls the same core functions directly.

---

## Access levels

| Level | Description | Available in |
|-------|-------------|--------------|
| `public` | Anyone can query. No authentication. Discoverable in the Noosphere registry. | Self-hosted + Cloud |
| `private` | Only the owner can query. Not registered in the registry. | Self-hosted + Cloud |
| `token` | Requires an access key. Creator generates keys and shares them with specific people or agents. Useful for granting access to collaborators, beta testers, or specific agent deployments without making the corpus fully public. | Self-hosted + Cloud |
| `paid` | Pay-per-query or subscription. Requires Stripe integration. Self-hosted users configure their own Stripe keys; cloud users use Stripe Connect (platform takes 10%). | Self-hosted + Cloud |

---

## Web frontend

The web UI serves **creators** — people who add knowledge to the Noosphere and want to see how agents are using it. Agents access knowledge via MCP/API, not the web UI.

### Two audiences, two interfaces

| | Creator (human) | Consumer (agent) |
|---|---|---|
| **Interface** | Web UI | MCP / REST API |
| **Actions** | Upload knowledge, ingest feeds/URLs, save from chat, compile concept notes, run health/maintain, configure access, view analytics | Search, retrieve, cite |
| **Sees** | Documents, endpoints, query activity | Chunks, scores, citations |

### User flow

```
New user arrives
  → Landing page: "Publish your knowledge to a network any AI agent can query."
  → Click "Get Started"
  → Main view: the Noosphere (network graph + global search + your corpora)
  → Click "+ Add Knowledge"
  → Create corpus: name, description, upload files, paste URL, paste RSS, or batch URLs (API/CLI)
  → Optional: chat with the corpus and **Save to corpus** to grow captures; run **Compile** (API/CLI) for fused concept notes
  → Choose access: public / private / token-gated
  → Choose whether to register in the Noosphere (recommended for public)
  → Done → See your corpus with MCP/API endpoints prominently displayed
  → Copy endpoint → paste into Claude/Cursor/agent config
  → Come back later → see query activity (agents are using your knowledge)
```

### Page structure (two levels)

**Level 1 — Main view (the Noosphere)**

The home screen after landing. Shows:
- **Global search bar** at the top — search across ALL public corpora in the Noosphere
- **Network graph** — D3 force-directed graph where each node is a corpus. Nodes connected by shared tags/topics. Agent activity shown as pulses on nodes.
- **Your Corpora** — list of the user's own corpora, each showing:
  - Name, access level, doc count, query activity
  - MCP and API endpoint URLs with copy buttons (this is the primary call-to-action)
  - "Manage →" to go to corpus detail
- **"+ Add Knowledge" button**

**Level 2 — Corpus detail (click into one corpus)**

Shows everything about one corpus on a single page:
- **Back to Noosphere** link
- **Header**: name, author, description
- **Connection info**: MCP endpoint + API endpoint with copy buttons (prominent)
- **Access settings**: dropdown to change access level + save
- **Stats**: documents, chunks, words, queries received, model
- **Documents**: listed with expand/collapse to read content inline (no third page level)
- **Search**: search box to try queries against this corpus
- **Actions**: add documents, re-index
- **Registry status**: "Registered in the Noosphere ✓" or "Local only"

### Key UI principles

1. **MCP/API endpoints are the hero** — the most prominent element on each corpus card. The user's main action is "copy this URL and give it to an agent."
2. **Documents expand inline** — click to expand/collapse, no page navigation for reading content.
3. **Global search searches the whole Noosphere** — not just one corpus. Results show which corpus each answer came from.
4. **Agent activity is visible** — query count on each corpus, pulses on network nodes when agents query.
5. **Registry awareness** — the UI makes it clear that public corpora join a global network of knowledge.

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
  "corpus_id": "example-archive",
  "name": "Example Knowledge Base",
  "description": "A collection of articles on product, growth, and startups.",
  "author": {
    "name": "Jane Doe",
    "url": "https://www.example.com"
  },
  "created_at": "2026-03-19T00:00:00Z",
  "updated_at": "2026-03-19T00:00:00Z",
  "document_count": 60,
  "chunk_count": 2400,
  "word_count": 950000,
  "embedding_model": "gemini-embedding-001",
  "embedding_dim": 3072,
  "language": "en",
  "tags": ["product", "growth", "startups"],
  "access": {
    "level": "public",
    "pricing": null
  }
}
```

---

## Agent access interface

### MCP (Model Context Protocol)

Noosphere exposes corpora via MCP. Any MCP-compatible client (Claude, Cursor, Codex, custom agents) can connect.

MCP tools:

| Tool | Description |
|------|-------------|
| `search` | Semantic search across corpora. Returns ranked chunks with citations. |
| `get_document` | Retrieve a full document by ID. |
| `list_documents` | List all documents with metadata. |
| `list_corpora` | List available corpora. |
| `get_topics` | List extracted topics and themes. |
| `get_stats` | Corpus statistics. |
| `get_manifest` | Full corpus manifest. |

Growth actions (**capture**, **compile**, **ingest-feed**, **ingest-urls**, **maintain**) are **REST/CLI-first** so agent consumers stay read/query-oriented; the corpus owner (or integrations with owner credentials) uses HTTP or CLI to grow the corpus.

### REST API

```
GET    /api/v1/health                           # Health check (for registry)
GET    /api/v1/corpora                          # List available corpora
POST   /api/v1/corpora                          # Create a new corpus
GET    /api/v1/corpora/:id                      # Get corpus manifest
PATCH  /api/v1/corpora/:id                      # Update corpus settings
DELETE /api/v1/corpora/:id                      # Delete corpus
GET    /api/v1/corpora/:id/documents            # List documents
GET    /api/v1/corpora/:id/documents/:doc_id    # Get a document
POST   /api/v1/corpora/:id/upload               # Upload files
POST   /api/v1/corpora/:id/ingest-url           # Ingest from URL
POST   /api/v1/corpora/:id/ingest-urls          # Batch URL ingest (max 40)
POST   /api/v1/corpora/:id/ingest-feed          # RSS or Atom feed → documents
POST   /api/v1/corpora/:id/capture              # Save Markdown into corpus (chat → KB)
POST   /api/v1/corpora/:id/compile              # LLM concept note from retrieved passages
GET    /api/v1/corpora/:id/knowledge-health     # Health / lint-style report
POST   /api/v1/corpora/:id/maintain             # Re-index (repair FTS/chunk drift)
POST   /api/v1/corpora/:id/index                # Trigger indexing
POST   /api/v1/corpora/:id/search               # Semantic search
GET    /api/v1/corpora/:id/analytics            # Query logs
GET    /api/v1/corpora/:id/topics               # Topics
GET    /api/v1/corpora/:id/stats                # Statistics
POST   /api/v1/search                           # Global search across all public corpora
GET    /.well-known/noosphere.json              # Federated discovery manifest
```

---

## Ingestion pipeline

### Supported input formats (v1)

| Format | Source |
|--------|--------|
| Markdown files | Local directory, upload, GitHub repo |
| Plain text | Upload |
| HTML / Blog | URL fetch → auto-convert to markdown |
| RSS / Atom | Feed URL → new documents per item (deduped); prefers fetching item link |
| Batch URLs | `ingest-urls` API / CLI — multiple pages in one operation |
| Audio transcription | Cloud only (Whisper API) — paid feature |

### Pipeline stages

```
Input sources → Ingest → Clean → Chunk → Embed → Index → Publish
```

---

## Technical architecture

### Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python / FastAPI |
| Database | SQLite + FTS5 (self-hosted) / PostgreSQL (cloud) |
| Embeddings | Pluggable: OpenAI, Gemini, local models |
| Retrieval | Hybrid: FTS5 keyword + vector cosine + RRF fusion |
| Chunking | Pluggable: paragraph, recursive, semantic |
| MCP server | JSON-RPC over HTTP |
| CLI | Click |
| Frontend | Vanilla JS SPA + D3.js (served by FastAPI) |
| Payments | Stripe (self-hosted: user's own keys, cloud: Stripe Connect) |
| Auth (cloud) | Supabase |

---

## Discovery and registry

### Design: centralized registry, decentralized hosting

```
┌──────────────────────────────────────────────────────────┐
│                  Noosphere Registry                       │
│           (registry.noosphere.ai)                         │
│                                                           │
│  Stores ONLY metadata:                                    │
│    corpus name, description, tags, endpoint URL,          │
│    document count, access level, last health check        │
│                                                           │
│  Does NOT store:                                          │
│    document content, chunks, embeddings, auth tokens      │
├───────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│  │ Self-    │  │ Self-    │  │ Cloud-   │               │
│  │ hosted   │  │ hosted   │  │ hosted   │               │
│  │ node A   │  │ node B   │  │ node C   │               │
│  └──────────┘  └──────────┘  └──────────┘               │
│       ▲              ▲             ▲                      │
│       └──────────────┴─────────────┘                      │
│         Agents connect DIRECTLY to each node              │
└───────────────────────────────────────────────────────────┘
```

Self-hosted and cloud-hosted corpora are equal citizens. The registry indexes all of them. Agents query the registry to discover corpora, then connect directly to the hosting node.

### Registration in the UI

When a user creates a public corpus, the UI asks:

```
🌐 Join the Noosphere?

Register this corpus so agents worldwide can discover
and query your knowledge.

☑ Register to the Noosphere (recommended)

Your content stays on your server.
Only the name, description, and tags are shared.
```

This makes registration explicit and the user understands what's shared (metadata only).

### Configuration

```bash
# Default: register with the public registry on serve
noosphere serve --port 8420

# Opt out
noosphere serve --port 8420 --no-registry

# Custom registry
noosphere serve --port 8420 --registry https://internal.mycompany.com/registry
```

---

## Business model

### Principle: charge for our costs, not their content

Creator's content = Creator's property. Our infrastructure = Our cost. Payment facilitation = Our service.

### Self-hosted (open source)

- Full product, free forever
- Bring your own API keys, infra, and Stripe keys
- All access levels including paid corpora
- 0% platform commission
- No usage limits
- Register to the Noosphere for free

### Cloud tiers

| Resource | Free Tier | Pro Tier ($9/month) |
|----------|-----------|---------------------|
| Corpora | 1 | Unlimited |
| Documents per corpus | 100 | Unlimited |
| Embedding tokens/month | 10K | Unlimited |
| Storage | 100MB | 10GB+ |
| Queries received/month | 1,000 | 100K |
| Access levels | All | All |
| Paid corpus support | Stripe Connect | Stripe Connect |
| Audio transcription | Not available | Whisper API included |

### Transaction commission (cloud only)

When a cloud-hosted paid corpus is queried and payment flows through our Stripe Connect:
- Creator gets 90%
- Platform gets 10%
- Stripe fees are separate (~2.9% + $0.30)

Self-hosted users who set up their own Stripe keep 100%.

---

## Implementation roadmap

### Phase 1: Open core MVP

Goal: working open-source tool — ingest, index, search, serve via MCP/API/CLI/Web.

Deliverables:
- [x] Corpus format specification
- [x] Database schema and corpus management
- [x] Ingestion pipeline (Markdown, plain text, URL fetch)
- [x] Chunking engine
- [x] Embedding engine (OpenAI + Gemini)
- [x] Retrieval engine (cosine similarity + citations)
- [x] MCP server (7 tools)
- [x] REST API (full CRUD + search + upload + analytics)
- [x] CLI (init, ingest, index, serve, list, search, export)
- [x] Web frontend: landing page with D3 network graph
- [x] Web frontend: corpus network view
- [x] Web frontend: corpus detail with search, documents, access control
- [x] Health endpoint + /.well-known/noosphere.json
- [x] Registry client (auto-registration)
- [x] RetrievalEngine abstraction (local + remote)
- [x] Web frontend redesign: agent-native UX (terminal, prominent endpoints, inline docs)
- [x] Global search across all corpora
- [x] README with quick start guide
- [x] Token-gated access (generate/revoke access keys)
- [x] PDF / DOCX / CSV / JSON ingestion
- [x] Export (SPEC-compliant ZIP format)
- [x] RAG chat with corpus and cross-corpus chat
- [x] Access control (public / private / token / paid)
- [x] Query logging with agent_id tracking
- [x] Test suite (214 tests, CI for Python 3.11–3.13)

### Phase 1.5: Retrieval & knowledge quality (complete)

Goal: production-grade retrieval that works at scale — hybrid search, smart chunking, incremental sync — plus **knowledge lifecycle** primitives that align with LLM-wiki / agent-brain patterns (without changing the mission).

Deliverables:
- [x] Hybrid search: FTS5 keyword + vector cosine + RRF fusion
- [x] Multi-query expansion (Gemini Flash / GPT-4o-mini)
- [x] 4-layer result dedup (best-per-doc, cosine similarity, type diversity, freshness boost)
- [x] Freshness signals in search results (stale detection, age metadata)
- [x] Chunking strategy profiles: paragraph (default), recursive (transcripts), semantic (papers)
- [x] Content-hash idempotent indexing (skip unchanged documents)
- [x] Incremental sync: `noosphere sync` command (add new, update changed, optionally prune deleted)
- [x] FTS5 virtual tables with auto-population for existing databases
- [x] Schema migrations (additive, backward-compatible)
- [x] Chat → corpus: `POST …/capture` + “Save to corpus” in web UI
- [x] RSS/Atom feed ingest + batch URL ingest
- [x] LLM **compile** (concept note from retrieval + chat LLM)
- [x] Knowledge health report + **maintain** (re-index / optional force)

See [RETRIEVAL_UPGRADE.md](RETRIEVAL_UPGRADE.md) for the full design document.

### Phase 2: Network + Payments (complete)

Goal: the two things that make Noosphere a product, not a tool — the network and the ability for creators to get paid. Without these, Noosphere is just another local knowledge base tool.

#### 2a. Registry Server — the network becomes real

- [x] Registry server: accepts registration, stores metadata, serves discovery queries
- [x] Registry search API: agents query the registry to find relevant corpora across all nodes
- [x] Registry health checks: periodic ping of registered nodes, mark stale/offline
- [x] Registry UI: browsable directory of all public knowledge bases in the Noosphere

#### 2b. Stripe Integration — creators get paid

- [x] Stripe checkout flow: `POST /corpora/{id}/checkout` creates a Stripe session
- [x] Payment verification middleware: validate payment before serving paid corpus queries (402 status)
- [x] Pricing config: creator sets price (per-query or subscription) in corpus settings
- [x] Webhook handlers: handle payment success, refund, subscription cancellation
- [x] Self-hosted: creator uses their own Stripe keys, keeps 100%
- [x] Revenue dashboard: creator sees earnings per corpus

#### 2c. Web UI completeness

- [x] Chat “Save insight” button on each assistant response
- [x] Feed management UI: add RSS feeds from web UI
- [x] Batch URL ingestion UI: paste multiple URLs at once
- [x] Compile UI: trigger concept note compilation from the web
- [x] Paid access settings UI: set pricing type, amount, and Stripe config

### Phase 3: Cloud + Scale

Goal: hosted version for creators who don't want to self-host.

- [ ] `noosphere/cloud/` — managed auth (Supabase), quota enforcement, Stripe Connect (BSL)
- [ ] Cloud deployment (Vercel/Railway + PostgreSQL)
- [ ] Free/Pro tier billing
- [ ] Platform commission (10%) on paid corpus revenue via Stripe Connect

### Phase 4: Automation + Ecosystem

Goal: convenience features that make knowledge bases feel alive. These are valuable but not core — they improve the experience without changing the product's fundamental value.

- [ ] Background feed scheduler: auto-poll RSS sources on interval (today: manual `ingest-feed` or cron)
- [ ] Scheduled enrichment: periodic compile + maintain runs (dream-cycle style)
- [ ] Feynman integration: Noosphere corpora as source-grounded minds
- [ ] Audio transcription (Whisper, cloud paid feature)
- [ ] Agent-to-Agent payment support

---

## Summary

Noosphere is the knowledge network for the agent era. Publish your knowledge as a living knowledge base any AI agent can discover, query, and cite. It grows over time as you add content. Share it free, keep it private, or charge for access.

The network connects all knowledge bases — self-hosted and cloud-hosted alike. Agents query the registry to discover knowledge, then connect directly to each node. Content stays on the creator's infrastructure; only metadata is shared for discovery.

The full product is open-source and self-hostable — including paid access (bring your own Stripe, keep 100%). The commercial layer adds hosting convenience and charges a 10% commission only when payment flows through the platform.

Creators own their knowledge, control access, and keep the revenue. The network makes every knowledge base more valuable by connecting it to the agents and organizations that need it.
