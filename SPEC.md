# Noosphere

> Expand the scope and scale of collective enlightenment.

**Google Scholar and arXiv — rebuilt for agents.**

Noosphere is an open platform that lets anyone publish their knowledge — papers, blogs, newsletters, podcasts, docs, notes — as structured, agent-readable corpora that AI agents can discover, query, and cite. Like Google Scholar and arXiv, but built for agents instead of human readers, and open to all knowledge — not just academic papers. Corpora are open by default; creators who choose to can set access to private, token-gated, or paid.

---

## Origin story

Platforms for human knowledge discovery already exist. Google Scholar indexes academic papers. arXiv lets anyone upload preprints. JSTOR and Elsevier sell access to journals. Wikipedia lets anyone contribute encyclopedic knowledge. But none of them were built for the emerging world where **agents are the primary consumers of knowledge**.

```
                    Agent-native
                        ↑
                        |
         Wolfram API    |    ← Noosphere
                        |
                        |    HuggingFace
                        |
  ──────────────────────┼──────────────────── Anyone can publish
   Closed /              |
   platform-produced     |
                        |
         JSTOR          |    arXiv
         Elsevier       |    Wikipedia
                        |
         Google Scholar  |    Semantic Scholar
                        |
                        ↓
                    Human-readable
```

The upper-right quadrant — open to any knowledge creator AND built for agent consumption — is empty. That is where Noosphere sits.

The trend is clear: more products are being built for agents, and more knowledge needs to become machine-readable. But today, making your knowledge agent-friendly requires significant technical effort — structuring content, chunking, embedding, hosting an MCP server, setting up access control, handling payments. Some creators have started converting their content into agent-friendly formats manually, but each effort is a one-off technical project. Noosphere standardizes and democratizes the entire pipeline.

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

**Expand the scope and scale of collective enlightenment.**

Every existing knowledge platform was built for humans to read. Google Scholar helps researchers find papers. arXiv lets scientists share preprints. Wikipedia lets anyone contribute to a shared encyclopedia. These platforms expanded collective enlightenment within the bounds of human attention and reading speed.

Noosphere asks: what happens when agents can discover, read, and cite knowledge on behalf of humans — across every knowledge base in the world, simultaneously? The scope expands — knowledge that was previously too niche, too specialized, or too buried to find becomes accessible through agent queries. The scale expands — millions of agents can query thousands of knowledge bases simultaneously, far beyond what any individual human could consume.

Two transformations make this possible:

1. **Anyone can publish.** Not just academics, not just institutions. Any person, community, or organization can turn their knowledge into a structured, queryable corpus — as easily as uploading files or pointing at a URL.
2. **Agents are the primary audience.** Every corpus is designed to be discovered, queried, and cited by agents first. The web UI exists for creators to manage their knowledge and see how agents are using it. The primary interface for consumers is MCP and API.

We believe that:

- Human knowledge should not be locked inside formats that only humans can navigate.
- The emerging agent ecosystem needs trusted, structured, citable knowledge sources — not just raw web scraping.
- Creators should control access to their knowledge and be able to monetize it if they choose.
- An open protocol for agent-readable knowledge will create more value than any closed platform alone.

## Design principles

1. **Knowledge is the primitive, not content.** We are not building a CMS or a file host. We are building a system that turns unstructured knowledge into structured, queryable, citable corpora that agents can reason over.

2. **Agent-native by default.** Every corpus is designed to be consumed by agents first. The web UI exists for creators to manage their knowledge and see how agents are using it. The primary interface for consumers is MCP/API.

3. **Creator sovereignty.** The creator owns their corpus. They decide: public, private, token-gated, or paid. They decide the price, the access model, the license terms. The platform enforces their choices — whether self-hosted or cloud.

4. **Source-grounded, not generative.** When an agent queries a Noosphere corpus, the response should be grounded in retrieved passages with citations. Not hallucinated summaries. Real source material, traceable to specific documents.

5. **Open core, commercial convenience.** The full product is open-source and self-hostable — including paid access control. The commercial layer adds hosting convenience, not exclusive features.

6. **One network.** Self-hosted and cloud-hosted corpora are equal participants in the Noosphere. The registry connects them all. Content stays on the creator's infrastructure; only metadata is shared for discovery.

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
| **Actions** | Upload knowledge, configure access, view analytics | Search, retrieve, cite |
| **Sees** | Documents, endpoints, query activity | Chunks, scores, citations |

### User flow

```
New user arrives
  → Landing page: "Publish your knowledge for agents"
  → Click "Get Started"
  → Main view: the Noosphere (network graph + global search + your corpora)
  → Click "+ Add Knowledge"
  → Create corpus: name, description, upload files or paste URL
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
| Database | SQLite (self-hosted) / PostgreSQL (cloud) |
| Embeddings | Pluggable: OpenAI, Gemini, local models |
| Vector storage | NumPy cosine similarity |
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

### Phase 1: Open core MVP (current)

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
- [ ] Web frontend redesign: agent-native UX (global search, prominent endpoints, inline docs)
- [ ] Global search across all corpora
- [ ] README with quick start guide

### Phase 2: Access control + payments

- [ ] Token-gated access (generate/revoke access keys)
- [ ] Stripe integration for paid corpora (self-hosted: own keys)
- [ ] `noosphere/cloud/` — managed auth, quota, Stripe Connect (BSL)
- [ ] PDF ingestion

### Phase 3: Registry + hosted platform

- [ ] Registry server
- [ ] Cloud deployment (Vercel/Railway + PostgreSQL)
- [ ] User registration + Stripe billing

### Phase 4: Ecosystem

- [ ] Feynman integration
- [ ] RSS/feed auto-sync
- [ ] Audio transcription (Whisper, cloud paid feature)
- [ ] Agent-to-Agent payment support

---

## Summary

Noosphere is Google Scholar and arXiv rebuilt for agents. Anyone can publish their knowledge as structured, agent-readable corpora. Agents discover, query, and cite knowledge through MCP and API. Corpora are open by default; creators who choose to can set access to private, token-gated, or paid.

The full product is open-source and self-hostable — including paid access (bring your own Stripe, keep 100%). The commercial layer adds hosting convenience and charges a 10% commission only when payment flows through the platform.

All nodes — self-hosted and cloud-hosted — participate in a shared discovery network via the registry. Self-hosted corpora register their metadata (not content) to the public registry, making them discoverable by any agent worldwide. Content stays on the creator's infrastructure.

The mission is to expand the scope and scale of collective enlightenment — by making every person's knowledge accessible to every agent, on the creator's terms.
