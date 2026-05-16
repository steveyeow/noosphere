# Noosphere

> Expand the scope and scale of collective enlightenment.

Noosphere lets you publish your knowledge as living knowledge bases any AI agent can read, query, and learn from. It grows over time as you add content or chat, and also as the network expands. You can keep it private, open, or charge for access.

Write what you know, distill it through chat, or connect what's already scattered across your apps. Noosphere indexes everything for agent retrieval, synthesizes it into living concept notes that compound over time, and keeps it yours. Solo creators publish their expertise; teams turn scattered fragments — Slack, meetings, decisions, customer calls — into a shared and living brain that compounds as the team works.

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
                    Agent-readable
                        ↑
                        |
   Karpathy LLM Wiki   |    ← Noosphere
   GBrain              |    (networked + democratized)
   Scale / Mercor      |
   Luel                |
   (manual, platform-  |
    controlled data)   |
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

Karpathy's LLM Wiki and Garry Tan's GBrain sit in the upper-left: agent-readable, but single-user and technically demanding. Scale, Mercor, and Luel also sit on the left: agent-facing, but platform-controlled and manually dispatched around buyer specs. Noosphere occupies the upper-right: agent-readable AND open to anyone, with a network that connects them all.

### Information platforms evolve

Information platforms change with how information is consumed:

- **Portals** — curated directories for humans (Yahoo, MSN)
- **Search** — ranked retrieval for humans (Google)
- **Social media** — attention marketplaces for humans (Facebook, Twitter, TikTok)
- **Agent media** — information platforms shaped for agent consumption

Social media optimized for human attention, so popular content is often not the most valuable. Agents don't pay an attention tax — they select for informational value and verifiable provenance. A platform shaped for agent consumption looks different: machine-readable discovery, provenance as a first-class signal, pricing for information value rather than exposure. Noosphere is built for that shape.

## The loop

Noosphere is built around a virtuous cycle between human knowledge and agent capability — not a one-shot pipeline:

```
   Humans create knowledge
            ↓
   Encoded as agent-readable substrate
            ↓
   AI compiles · maintains · grows
            ↓
   Network: corpora discover · subscribe · learn · transact
            ↓
   Any agent (peer Noosphere corpus or external AI)
   queries · trains on · reasons with corpora
            ↓
   Value flows back to humans
   (decisions, learning, new creation)
            ↺ loop continues
```

Karpathy's LLM Wiki and Garry Tan's GBrain are early single-user instances of this loop: personal knowledge as agent-readable substrate, AI as the multiplier, the human as both creator and beneficiary. Noosphere extends the loop across people. Every corpus is itself an agentic node — at higher autonomy levels it discovers, subscribes to, pays for, and learns from other corpora on its own. Any agent — a peer Noosphere corpus, or an external AI in a company / app / developer environment — can consume from the network.

Each step compounds the next. Better substrate makes AI compile better. Network learning deepens individual corpora. Agents using the network surface gaps that humans then fill. The longer the loop runs, the more useful the whole system gets. Every feature in this spec maps to one or more steps of this loop; if a proposed feature doesn't, it's likely off-thesis.

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

## Core value

**Expand the scope and scale of collective enlightenment.**

Personal AI knowledge bases are the future — but isolated knowledge bases are a transitional state. The real value comes when they're connected into a network, and when creators can control and monetize access.

Six things define Noosphere:

1. **A connected network.** Every knowledge base can join a global discovery network. An agent helping a startup founder can draw on the best thinking from thousands of domain experts. The network makes every individual knowledge base more valuable — and creates a marketplace where knowledge finds the people (and agents) who need it.
2. **Agent-readable by design.** Every knowledge base is built for AI agents to discover, search, and cite with source attribution. Agents are the primary consumers. The web UI exists for creators to manage their knowledge.
3. **Living knowledge.** Knowledge bases grow over time — from chat conversations, RSS feeds, URL imports, and LLM-powered compilation. They are compounding knowledge systems, not static file dumps.
4. **Creators get paid.** Open your knowledge to everyone, or set it to paid. Lenny Rachitsky opened part of his newsletter to agents for free but kept the full archive behind a subscription. Domain experts, researchers, consultants — anyone with valuable knowledge can monetize it through the network. Organizations and agents pay for the expertise they need, without hiring consultants to train proprietary models.
5. **Knowledge bases are agents.** A corpus is not just a document collection — it is an agentic node. It answers with citations, describes itself, routes out-of-scope questions, reports calibrated confidence, and at higher autonomy levels actively discovers, subscribes to, and pays for other corpora on its own. It both consumes and produces in the network. Networking is the substrate (every corpus is reachable by default); autonomy is the dial — three tiers: **Static** (manual, on-demand), **Living** (auto-ingest from connected feeds, keep compiled Wiki in sync), **Fully Autonomous** (actively discovers, subscribes, pays, compiles, grows within owner-set policy).
6. **A network of learning agents.** Knowledge bases consume from other knowledge bases — direct query, subscription to increments, skill/capsule import, or derivative corpora with attribution. Humans author first; agents compound on top. Provenance is tracked through the chain.

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

7. **Information value, not exposure.** Ranking and pricing track informational value and verifiable provenance. No sponsored placement in results, no brand injection in answers, no lead-gen fees. Attention-based monetization reintroduces social media's failure mode; this is an anti-commitment, not a future option.

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
| Nightly “dream” enrichment | **Enrichment cycle:** `POST /corpora/{id}/enrich` — discovers all RSS feeds from document metadata, polls for new entries, re-indexes, and returns a health summary. Call on a schedule (cron, agent, or scheduler) for automatic knowledge growth. |
| Automatic meeting/email/calendar ingest | **Out of scope for open core** — requires deep integrations; cloud roadmap may add connectors. |

**Honest boundary:** Noosphere still does not auto-ingest your private digital life the way a personal OpenClaw + brain stack can. It **does** support **networked publishing**, **lower-friction inflow** (feeds, batch URLs, captures, compile), **enrichment cycles**, and **observable corpus health**.

### Knowledge enrichment

Knowledge bases are living systems, not static file dumps. The enrichment cycle is how they grow:

```
                    ┌─────────────────────────────────┐
                    │        Enrichment Cycle          │
                    │   POST /corpora/{id}/enrich      │
                    └──────────┬──────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                 ▼
        Poll RSS feeds   Re-index new      Health check
        (discover +      content            (stale docs,
         ingest new      (chunks +          missing chunks,
         entries)         embeddings)        broken links)
              │                │                 │
              └────────────────┼────────────────┘
                               ▼
                    Updated corpus with
                    fresh content + signals
```

**How it works:**

1. **Feed discovery.** The enrichment endpoint scans document metadata for `source_feed` URLs — every RSS/Atom feed that has ever been ingested is automatically tracked.
2. **Incremental polling.** Each feed is fetched and deduped against existing documents (by `rss_guid` or link). Only new entries are ingested.
3. **Re-indexing.** If new content was ingested, the corpus is re-indexed to update chunks and embeddings.
4. **Health check.** Returns the same signals as `GET /knowledge-health`: documents without chunks, stale content, empty links, capture/concept counts.

**Compiled truth.** Concept notes created via `POST /compile` represent distilled knowledge — synthesized from multiple sources by the LLM. The search engine gives these a score boost (`+0.08`) because they represent higher-signal, cross-referenced content. Over time, as more concept notes are compiled, the knowledge base develops a layer of “compiled truth” that improves search quality.

**Search detail levels.** Agents can choose how deep to search:

| Level | Behavior | Latency |
|-------|----------|---------|
| `low` | Keyword-only, no query expansion | Fastest |
| `medium` | Hybrid keyword+vector, expansion for large corpora | Default |
| `high` | Forced expansion, more results, full context | Thorough |

This lets agents trade off speed vs. thoroughness depending on their task.

---

## Product architecture

### Single repo, open core with commercial shim

Following the same architecture as Feynman, Noosphere is a single repository with clear license boundaries:

```
noosphere/
├── LICENSE                    ← MIT (root)
├── noosphere/
│   ├── core/                  ← MIT — ingestion, chunking, embedding, retrieval, registry
│   ├── api/                   ← MIT — REST API + web frontend + network discovery
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
Layer 4:  Three transports    ← MCP · REST · CLI — same operations, three protocols
Layer 1:  Corpus Format       ← Structured data (Markdown + chunks + embeddings)
```

The three transports are first-class peers, not stacked. Each surfaces the same read/query/growth operations against a shared core; consumers pick whichever fits.

- **MCP** suits GUI-first agent clients (Claude Desktop, Cursor) where tools register into a shared context
- **REST** is the lingua franca for scripts, CI, the web app, and any system without an LLM in the loop
- **CLI** is what LLMs encounter most in their training data; composes via shell pipelines; auth runs through OS-standard mechanisms (keychain, env vars). First-class for Claude Code, Cursor agent mode, terminal users, and humans
- **Markdown** is the underlying content format, not an access interface

All three transports share the same core logic; the CLI calls the same core functions directly.

---

## Team workspaces

Noosphere works in two contexts: a personal workspace (one user, their corpora) and team workspaces (an organization, its members, its corpora). **Both are the same product** — same DB, same MCP/REST, same compile/distill engine. A solo Pro user who later forms a team keeps everything; the corpus just gains an `org_id`.

### Mental model

A user account is personal-first. Everyone has a Personal workspace (Free or Pro). A user can additionally belong to N **org workspaces** (Team tier), switchable from a top-left workspace switcher (Notion-style). A corpus belongs to exactly one scope — either `owner_id` (personal) XOR `org_id` (team). Personal corpora are never auto-shared with any org.

### Why teams need this

A team's organizational memory today is scattered across Slack, Notion, meeting tools, ticket systems, customer-feedback inboxes, sales transcripts. None of it is queryable by agents — and most of it isn't queryable by the team either, except by remembering who said what in which channel. A team Noosphere captures from the edge (where work happens), synthesizes through compile + distill, and exposes one shared brain to every member and every agent.

This is the same shape Karpathy's LLM Wiki and Garry Tan's GBrain take individually — extended to a multi-contributor context. Where individual Noosphere is creator-first, team Noosphere is **edge-first**: knowledge enters at the point of work, not as a separate authoring task.

### Three team archetypes

Same product, different access-level mixes per corpus:

| Archetype | Example | Primary value | Monetization |
|---|---|---|---|
| Internal org brain | Eng team, ops team, startup | Memory that survives turnover; queryable ops | None — the brain is the product |
| Mixed | Newsletter team, research lab | Internal corpora alongside public/paid expertise corpora | Per-corpus, optional |
| Knowledge supplier | Domain practice (e.g. specialty consulting) | Team explicitly builds corpora to sell | Yes; per-contributor weights |

We don't fork tiers for these — they're the same Team plan with different `access_level` choices.

### Data model

```sql
organizations(
  id UUID PK, slug TEXT UNIQUE, name TEXT,
  tier TEXT DEFAULT 'team',
  billing_customer_id TEXT,
  stripe_connect_account_id TEXT,    -- cloud only; null in self-hosted
  settings_json TEXT,
  created_at, updated_at
);

organization_members(
  org_id FK, user_id FK,
  role TEXT,                          -- owner | admin | editor | viewer
  invited_by TEXT, joined_at TEXT,
  PRIMARY KEY (org_id, user_id)
);

audit_logs(
  id UUID PK, org_id TEXT, actor_user_id TEXT,
  action TEXT,                        -- corpus.create | doc.ingest | member.invite | access.change | ...
  resource_type TEXT, resource_id TEXT,
  metadata_json TEXT, ip_addr TEXT, created_at TEXT
);

ALTER TABLE corpora    ADD COLUMN org_id TEXT NULL;
-- constraint: (owner_id IS NOT NULL) XOR (org_id IS NOT NULL)

ALTER TABLE documents  ADD COLUMN contributor_user_id TEXT NULL;
-- for org-owned corpora, tracks who ingested each doc
```

### Roles

Four roles apply across every org corpus. v1 has no per-corpus ACL overrides:

| Role | Members | Corpora | Settings | Audit log |
|---|---|---|---|---|
| owner | manage | full | all | view |
| admin | manage | full | all except billing | view |
| editor | view | create / ingest / compile | corpus-level access | — |
| viewer | view | read-only (and queries via personal agent) | — | — |

The existing per-route check (`owner_id == current_user_id`) extends to: user is corpus owner OR user is a member of `corpus.org_id` with role ≥ editor for writes, ≥ viewer for reads.

### Team-only capture surfaces

These don't make sense for a single user; they're only available in org workspaces.

| Surface | What it does | Source kind |
|---|---|---|
| Slack `/noosphere` slash command | Save a thread or message into a chosen corpus | `user_capture` |
| Per-corpus email forwarding | Each corpus gets a unique inbox; forward customer email, sales notes, alerts | `user_capture` |
| Meeting transcripts | Paste or forward Granola/Otter/Fireflies output | `user_capture` |
| Linear/Jira close hook | Closed tickets feed a "what we've fixed" KB | `user_capture` |

All capture writes record `contributor_user_id`. Authoring (Write) remains available, but the team-tier emphasis is on **capture from the edge, synthesis by the system** — not coordinated authoring.

### Team-only synthesis

Compile recipes templated for orgs (each is a saved query against the existing compile primitive):

- **Weekly digest** — what shipped, what shifted, what's blocked
- **Decision log** — extract decisions and rationale from threads + meetings
- **Customer-pain synthesis** — patterns across feedback corpora
- **Onboarding pack** — auto-generated "what a new hire needs to know"
- **Ops dashboards** — saved queries rendered as cards (hiring, sales, eng)

Distill in team context interviews team members with org-aware prompt templates. Output is `source_kind=user_original` with `contributor_user_id` set — a way to capture tacit founder/expert knowledge before they leave.

### Self-improving: "What we don't know yet"

A per-org dashboard that surfaces low-confidence or zero-result queries from members and their agents. Output is a prioritized backlog: ingest these sources, interview these people via Distill, compile these topics. The team brain becomes self-driving: gaps surface, get filled, compound.

### Self-hosted vs Cloud

Same MIT/BSL line as personal:

| Capability | Self-hosted (MIT) | Cloud (BSL) |
|---|---|---|
| Org primitives, members, roles, audit log | ✓ | ✓ |
| Multi-contributor ingest, contributor attribution | ✓ | ✓ |
| Org-level OAuth connectors | ✓ | ✓ |
| Slack capture, email-to-corpus, transcripts | ✓ | ✓ |
| Compile recipes, "what we don't know yet" dashboard | ✓ | ✓ |
| Bring-your-own-Stripe at org level (direct, keep 100%) | ✓ | — |
| Multi-tenant isolation (one server, many orgs) | — | ✓ |
| Stripe Connect with 10% platform fee | — | ✓ |
| Hosted billing, seat enforcement, email invites | — | ✓ |
| Auth: minimal (single OIDC or basic password) | ✓ | — |
| Auth: hosted SSO, magic-link email | — | ✓ |

Self-hosted runs as a single org per instance — no multi-tenant complexity. Cloud is where one user belongs to a Personal workspace plus N orgs.

### Roadmap

Sequenced; deliverables gated on product clarity, not engineering hours.

| Tag | Deliverable |
|---|---|
| **T-1** | Org primitives: orgs, members, invites, roles, workspace switcher, `corpora.org_id`, `documents.contributor_user_id`, role checks on all write/read paths, audit-log writes |
| **T-2** | Source adapter framework — **wiring**, not framework code (framework + first manifest already scaffolded as of 2026-04-28). Build the deferred items in `## Ingestion pipeline` → "Deferred work needed before any manifest adapter ships to users": `connector_configs` REST lifecycle, run-trigger endpoint, scheduler integration, source-logo panel instance UI, last-sync surfacing. Pick a BYO-manifest sandbox tier before exposing any upload UI. First adapters to graduate from scaffolding to user-facing once wiring lands: GitHub (CLI/PAT), Notion (MCP), Google Workspace (OAuth+REST), Slack (REST or email fallback) |
| **T-3** | Team-native capture: Slack `/noosphere`, per-corpus email forwarding, meeting transcript ingest |
| **T-4** | Team compile recipes (weekly digest, decision log, customer-pain, onboarding pack), "What we don't know yet" dashboard |
| **T-5** | Team Distill: org-aware interview templates, contributor attribution |
| **T-6** | Per-contributor revenue weights (manual distribution by org owner; no auto-payout in v1) |

#### T-1 sub-task breakdown (the foundation everything else depends on)

| # | Task | Notes |
|---|---|---|
| **T-1.1** | Schema migration | New tables `organizations`, `organization_members`, `audit_logs`. New columns `corpora.org_id NULL`, `documents.contributor_user_id NULL`. Constraint `(corpora.owner_id IS NOT NULL) XOR (corpora.org_id IS NOT NULL)`. SQLite (self-hosted) and PostgreSQL (cloud) variants. |
| **T-1.2** | Org models + CRUD | New module `noosphere/core/orgs.py`. Endpoints: `POST /orgs`, `GET /orgs/:id`, `PATCH /orgs/:id`, `DELETE /orgs/:id`. Slug uniqueness, owner = creator. |
| **T-1.3** | Member ops + invites | Endpoints: `POST/GET/PATCH/DELETE /orgs/:id/members`, `POST /orgs/:id/invites`, `POST /orgs/invites/:token/accept`. Cloud uses email; self-hosted uses shared link tokens. |
| **T-1.4** | Permission middleware | New helper `current_user_can(action, resource)` extending the existing `owner_id == user_id` check in `noosphere/api/routes.py`. Corpus writes: owner OR org member with role ≥ editor. Reads: ≥ viewer. Org settings: ≥ admin. Billing: owner only. Apply to **every** corpus mutation endpoint — no exceptions. |
| **T-1.5** | Audit-log writes | Hook `audit_logs.insert()` async on: `corpus.create/delete`, `doc.ingest`, `member.invite/remove/role_change`, `access.change`, `corpus.transfer`. Endpoint `GET /orgs/:id/audit-logs` paginated, owner/admin only. No advanced filtering UI in v1. |
| **T-1.6** | Workspace switcher (frontend) | Top-left of `#/main` shell: Personal · Org A · Org B · `+ Create org`. Switching changes active workspace context (corpus list, network search scope, settings). Active workspace stored in `localStorage`. |
| **T-1.7** | Org creation + member-management UI | Modal: name + slug. Post-create redirects to org workspace and prompts to invite. Org settings page lists members + role dropdown + invite-by-email. |
| **T-1.8** | Workspace-context threading | Every API call attaches `X-Noosphere-Workspace: personal\|org:<id>` header. Server returns 403 if requested resource doesn't match active workspace. Corpus list, network search, all settings endpoints — scope by header. **High scope-leak risk; needs explicit tests.** |
| **T-1.9** | Contributor attribution UI | Document list shows contributor name when in org workspace. Per-corpus `Contributors` view (count of docs per member). Personal workspace: hidden. |
| **T-1.10** | Tests | Permission boundary: personal user cannot read/write org corpus and vice versa. Scope leak: API request with mismatched workspace header rejected. Migration round-trip on existing data with NULL `org_id`. XOR constraint enforced. Role transitions (editor → viewer revokes write). |

T-1 is done when: a self-hosted user can create an org, invite a teammate via shared link, both ingest into the same corpus, both see contributor names on documents, and a third non-member is correctly rejected — all with audit log entries recorded.

### Pricing

Team tier: **$49/seat/month**, 3–50 seats, unlimited corpora. All access levels available — including paid (10% platform fee on cloud, 0% self-hosted). Monetization is not the team headline; it's a quiet option in corpus settings, identical to the personal flow.

---

## Access levels

| Level | Description | Available in |
|-------|-------------|--------------|
| `public` | Anyone can query. No authentication. Discoverable in the Noosphere registry. | Self-hosted + Cloud |
| `private` | Only the owner can query. Not registered in the registry. | Self-hosted + Cloud |
| `token` | Requires an access key. Creator generates keys and shares them with specific people or agents. Useful for granting access to collaborators, beta testers, or specific agent deployments without making the corpus fully public. | Self-hosted + Cloud |
| `paid` | Pay-per-query, subscription, or corpus licensing (bulk/one-time access for training or enterprise use). Requires Stripe integration. Self-hosted users configure their own Stripe keys; cloud users use Stripe Connect (platform takes 10%). | Self-hosted + Cloud |

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

The manifest is the KB's **agent-media capability card** — it's how external agents decide whether this corpus is worth querying or paying for. It carries self-declared and computed signals together (Tier 1 + Tier 2 of the signal stack, see Discovery section).

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
  "task_types": ["retrieval", "synthesis", "advice"],
  "source_composition": {
    "user_original": 0.6,
    "user_curated": 0.3,
    "external_public": 0.1
  },
  "samples": [
    {
      "question": "How should a seed-stage startup price its first enterprise deal?",
      "answer_preview": "Anchor on the buyer's budget, not your cost..."
    }
  ],
  "autonomy_level": 0,
  "calibration_policy": {
    "reports_confidence": true,
    "confidence_source": "self"
  },
  "license_terms": {
    "query": "pay-per-query",
    "bulk": "negotiable"
  },
  "access": {
    "level": "public",
    "pricing": null
  }
}
```

**New fields (Phase 4):**
- `task_types` — what kinds of questions the KB answers well (retrieval, synthesis, advice, how-to, factual-lookup, etc.)
- `source_composition` — rollup of `source_kind` over documents; a KB that is 90% user_original has a different trust profile than one that is 90% external_public
- `samples` — representative Q&A pairs for agents to evaluate relevance quickly
- `autonomy_level` — Static (default), Living, Fully Autonomous (see Core value #5 for definitions)
- `calibration_policy` — whether and how the KB reports confidence
- `license_terms` — accepted monetization shapes (query / subscription / bulk / licensing)

---

## Agent access interface

Noosphere exposes corpora across three transports — **MCP**, **REST**, and **CLI**. Same capability set; pick the transport that fits the consumer.

### Two consumer classes

Both are first-order:

- **In-network agents** — other corpora across Noosphere instances, accessing each other through the registry, citation graph, and peer subscription. Corpus-to-corpus traffic underwrites network learning.
- **Out-of-network agents** — external AI in companies, developer apps, research orgs, end-user agent clients (Claude Desktop, Cursor, custom bots). They consume Noosphere through public APIs / MCP / `llms.txt`.

Both classes use the same toolbox; discovery and trust mechanisms (manifest, `kb_reputation`, `preview_ask`, citation graph) serve both equally. As the network scales, this discovery + evaluation infrastructure becomes the network's central asset — without it, a network of corpora is noise; with it, an agent of either class can find and trust the right corpus efficiently.

### Use modes

The same toolbox supports several use modes that recur in practice:

- **Grounded Q&A** — an agent answers a user's question grounded in retrieved passages, with citations. The most common case.
- **Reasoning context** — an agent solving a complex task (a decision, a multi-step analysis, problem diagnosis) uses one or more corpora as substrate for its reasoning. Each step's claims trace back to specific documents.
- **Capability source** — a corpus is licensed (per `corpus licensing`) as fine-tuning or persistent RAG substrate for a derivative agent. The corpus stays the source of truth; new agents inherit the underlying knowledge.

Pricing, access, and provenance signals (`access_level`, `pricing`, `source_composition`) apply uniformly across modes. An agent picks the mode by how it stitches the toolbox together — Noosphere does not gate by mode.

### Why three transports (not just MCP)

MCP is well-suited to GUI-first agent clients where tools register into a shared context. But MCP has known limitations for other consumers: process overhead per server, context bloat from tool definitions in the agent's context window, less reliable tool selection vs. deterministic command invocation. CLI is what LLMs encounter most in their training data; it composes via shell pipelines; auth runs through OS-standard mechanisms. REST is the universal protocol for scripts, CI, integrations, and any system without an LLM in the loop.

The right choice depends on the consumer. Claude Desktop wants MCP. Claude Code shells out and prefers CLI. A CI job calling `curl` wants REST. The web app wants REST. Rather than betting on one, all three are first-class. If the protocol landscape shifts, the choice shifts with it; the underlying capabilities do not change.

### MCP (for Claude Desktop, Cursor, MCP-native clients)

Any MCP-compatible client (Claude, Cursor, Codex, custom agents) can connect.

MCP tools:

| Tool | Description | Status |
|------|-------------|--------|
| `search` | Semantic search across corpora. Returns ranked chunks with citations. | Shipped |
| `get_document` | Retrieve a full document by ID. | Shipped |
| `list_documents` | List all documents with metadata. | Shipped |
| `list_corpora` | List available corpora. | Shipped |
| `get_topics` | List extracted topics and themes. | Shipped |
| `get_stats` | Corpus statistics. | Shipped |
| `get_manifest` | Full corpus manifest (including agent-media capability card). | Shipped |
| `ask` | Synthesized answer with citations, grounded in retrieved passages. | Phase 4 |
| `describe` | Structured self-description: task types, scope, confidence posture. | Phase 4 |
| `route` | Given a query outside this KB's scope, suggest other KBs that may answer it. | Phase 4 |
| `preview_ask` | Evaluation version of `ask` — truncated synthesized answer bypassing access gating, so agents can judge answer quality before paying. | Phase 4 |

The Phase 4 tools move corpora from pure retrieval endpoints to **KB-as-agent interfaces**: `ask` gives agents a synthesized answer instead of raw chunks; `describe` + `preview_ask` support discovery/trust at query time; `route` enables inter-KB handoff.

**Inter-KB attribution.** When an agent acts on behalf of a corpus, it should set `X-Noosphere-Caller-Corpus: {corpus_id}` on `ask` / `search` calls. Successful `ask` calls (where the source returned chunks) auto-record a `query`-kind citation from caller to target, deduped per pair within a 24-hour window. The target's `kb_reputation` refreshes on insert. Unknown / unresolvable caller IDs are silently ignored (can't poison the graph with fake attributions).

Growth actions (**capture**, **compile**, **ingest-feed**, **ingest-urls**, **maintain**) are **REST/CLI-first** so agent consumers stay read/query-oriented; the corpus owner (or integrations with owner credentials) uses HTTP or CLI to grow the corpus.

### CLI (for Claude Code, terminal users, Bash-driven agents)

A `noosphere` CLI (npm + Homebrew distribution) mirrors the read, query, and growth operations. JSON output by default (`--format=text` for human-readable). Auth via `noosphere login` (stores token in OS keychain) or `NOOSPHERE_TOKEN` environment variable.

Representative commands:

```
noosphere list-corpora
noosphere search "..." --corpus engineering
noosphere ask "..." --corpus engineering
noosphere describe engineering
noosphere route "..."
noosphere capture --corpus engineering --content - <<< "..."
noosphere compile engineering --topic "..."
```

The same CLI is what Claude Code, Cursor agent mode, and Cline shell out to when they want to use Noosphere — no MCP plumbing required, no extra context bloat, deterministic invocation. Humans use it for scripted ingest, CI checks, and one-off queries.

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

### Static discovery surfaces (shipped)

Mounted at the site root rather than under `/api/v1` because the standards expect them at conventional paths. AI-era and traditional crawlers find them by convention without prior knowledge of the API.

| Endpoint | Purpose |
|---|---|
| `GET /llms.txt` | llmstxt.org site index — lists every public corpus with a markdown link to its own `llms.txt` |
| `GET /c/{slug}/llms.txt` | Per-corpus markdown index (header + document list, externally-visible content only) |
| `GET /c/{slug}/llms-full.txt` | Per-corpus full-text dump for one-shot LLM ingestion |
| `GET /sitemap.xml` | Standard sitemap listing the site-root `llms.txt` and every public corpus's two markdown URLs |
| `GET /robots.txt` | Allow-all + `Sitemap:` link |
| `<script type="application/ld+json">` in HTML | Site-level WebSite schema (static); per-corpus Dataset schema injected client-side when a corpus page loads |

These complement, not replace, MCP/REST/CLI: they give zero-friction read access to LLMs and crawlers that don't speak any agent protocol, plus the discovery surface that lets external AI search engines (ChatGPT search, Perplexity, Anthropic web fetch) index Noosphere content automatically.

### Embeddable widgets (planned)

A `<script>`-loadable AI Chat / AI Search widget that any user can drop into their personal site, blog, Substack, or Notion. The widget calls Noosphere's existing `/ask` and `/search`; visitors ask questions of the corpus and get cited answers without leaving the host page.

**Why it matters.** MCP / REST / CLI / `llms.txt` reach developers, agents, and power users — the technical end of the consumer spectrum. Embeddable widgets close the loop for **non-technical readers on a creator's audience surface**: Substack subscribers querying the writer's published research, blog visitors asking the author about their archive. This turns Noosphere from "agent-readable knowledge layer" into "publishing layer with AI native".

**Distribution shape (illustrative):**
```html
<script src="https://{noosphere}/embed/{slug}.js" data-mode="chat" data-theme="auto"></script>
```

**v1 capabilities:**
- Ask widget — chat-style with citations back to source documents, "powered by Noosphere" attribution
- Search widget — ranked passages with deep links into the corpus
- Theme via CSS variables; auto light/dark detection from the host page
- Access gating — public corpora work no-auth; token corpora require an embed token in the script's data attributes; private corpora cannot be embedded

**Open design questions (deferred to a dedicated planning round before build):**
- Shadow DOM vs iframe isolation (Shadow DOM preferred for theming; iframe only if the security model demands it)
- Per-widget rate limiting at the corpus level (one popular embed could fan out to many visitors)
- Anonymous-visitor analytics — count widget conversations per corpus without storing visitor PII
- Embed-token rotation, revocation, and per-domain pinning

**Roadmap fit.** Horizontal — benefits both Personal Pro and Team tiers. Sequenced after the static discovery surfaces (`/llms.txt`, sitemap, robots, per-corpus JSON-LD shipped 2026-04-28); not blocked by and does not block T-1 to T-6 team-workspace work.

**Out of scope for v1:**
- White-label custom domain hosting of the widget bundle
- Visitor authentication (anonymous read only in v1)
- Server-side rendering of the widget HTML

---

## Ingestion pipeline

### MVP ingest paths (currently exposed)

These are the entry points users actually see and use today. The composer's `+` menu lists them in this order:

| # | Path | Surface | Underlying mechanism |
|---|---|---|---|
| 1 | **Write a note** | Composer `+` → `Write` (Markdown editor) | Direct insert via `POST /api/v1/corpora/:id/capture` (or the unified ingest pipeline) |
| 2 | **Upload file** | Composer `+` → `Upload` (PDF / MD / DOCX / TXT / CSV / JSON / HTML) | `POST /api/v1/corpora/:id/upload` |
| 3 | **Import a page** | Composer `+` → `Import a page` (URL or paste) | `POST /api/v1/corpora/:id/ingest-url` (single) / `ingest-urls` (batch) |
| 4 | **Add RSS feed** | Composer `+` → `Add RSS feed` | `POST /api/v1/corpora/:id/ingest-feed`, polled on cron |

Plus the secondary surfaces that map to the same primitives:

- **Chat capture** — every assistant reply has a Save-to-corpus affordance; calls `/capture`
- **Source logo panel** (Composer `+` → `Add a source` → click app logo) — currently surfaces ZIP-archive imports for Notion / Twitter / Obsidian and the Obsidian live-sync (CLI + plugin); other apps are listed but their methods are flagged `Soon`

**These four are the supported MVP** for the foreseeable near term. Everything else in this section is scaffolding for a roadmap path, not a current capability — see "current state" callouts below.

### Source adapter framework (scaffolded — not yet user-exposed)

**Current state (2026-04-28)**: the framework code is implemented (`noosphere/core/connectors/manifest.py`, `transports/cli.py`, `manifests/github.toml`); a `ManifestConnector` registers into the same `REGISTRY` as the built-in Python connectors. **But there is no user-facing UI for creating, configuring, scheduling, or running manifest-driven adapters.** The `connector_configs` table exists in the schema with no API or lifecycle code reading from it. `ManifestConnector.run()` works when invoked directly from Python; nothing in the HTTP layer or scheduler invokes it yet.

This section describes the design intent that the existing scaffolding implements. Wiring it into the product UI is deferred until the four MVP paths are validated and we have a concrete user need for a fifth source.

#### Design intent

Each ingestion source is configured by a manifest specifying its **transport**, auth model, and operations. Noosphere does not write per-source connector code beyond what each transport requires. New sources are added by writing a manifest, not by writing a bespoke connector.

Supported transports:

| Transport | When to use | Example sources |
|---|---|---|
| **MCP** | Source ships an official or stable MCP server | Notion (official), Postgres |
| **CLI** | Source has a stable, JSON-output CLI | GitHub (`gh`), Linear (`linear-cli`), gcloud |
| **REST** | Source has neither MCP nor CLI but offers API + OAuth | Slack, Stripe, most SaaS |
| **Email forwarding** | Source has no programmatic surface, or notification-tier data is sufficient | Granola, Otter, long-tail SaaS, customer mail |
| **File / snapshot** | One-time backfill or filesystem-resident data | Notion ZIP, Slack export, Twitter archive, Obsidian vault, GitHub repo clone |

The right transport per source depends on what is most stable today, not on a global preference. Notion's official MCP is solid; we use MCP. GitHub's `gh` CLI is more battle-tested than its MCP today; we use CLI. Slack has no maintained official MCP; we use REST or email. Choices revisit as the ecosystem matures — the manifest framework absorbs the change without rewriting ingest code.

### Source manifest examples

```yaml
# adapters/github.yaml
transport: cli
binary: gh
auth: gh_user_credential   # uses user's gh CLI auth
poll: every 10min
ingest:
  - cmd: "gh issue list --state open --json number,title,body,labels,createdAt,author"
    source_kind: user_capture
  - cmd: "gh pr list --json number,title,body,reviewDecision,author"
    source_kind: user_capture
```

```yaml
# adapters/notion.yaml
transport: mcp
mcp_server: "@notionhq/mcp-server"
auth: oauth_notion
poll: every 15min
tools: [list_databases, query_database, get_page_blocks]
source_kind: external_subscription
```

```yaml
# adapters/granola.yaml
transport: email
forwarding_address: "*@granola.ai"
parser: granola_transcript
auth: none
source_kind: user_capture
```

### Per-source selection rule

For any source, choose in this order:

1. Stable MCP if one exists and is well-maintained
2. Stable CLI if one exists with reliable JSON output
3. Direct REST API if neither
4. Email forwarding if the source has no programmatic surface
5. ZIP/snapshot import for backfill or cold-start

A source can use multiple adapters at once — e.g., one-time ZIP backfill plus ongoing CLI poll.

#### Deferred work needed before any manifest adapter ships to users

These items must be designed and built before the source adapter framework graduates from scaffolding to a user-facing capability. They are intentionally out of MVP scope.

| Item | Why it is deferred |
|---|---|
| `connector_configs` lifecycle (REST CRUD: create, list, update, delete instance) | Schema exists, no API. Required so each user can configure their own GitHub / Notion / etc. instance per corpus, store auth, schedule, last-sync metadata |
| Run-trigger endpoint (`POST /connector_configs/:id/run`) | Required so the UI can invoke `ManifestConnector.run()` on demand |
| Scheduler integration | Required so manifests with `default_cron` actually poll on schedule (today they only run when invoked manually from Python) |
| Source-logo panel UI: instance configuration form | Required so the existing `_SOURCE_CONNECTORS` panel can offer a real `Connect` action when an adapter ships, instead of `Soon` |
| Last-sync result display + error surfacing | Required so users can tell whether the polling is healthy |

#### Cloud vs self-hosted constraint for CLI adapters

The CLI transport runs `subprocess.run(...)` on the **Noosphere server**, not on the user's device. This has different implications by deployment:

| Deployment | CLI auth source | Works without per-user config? |
|---|---|---|
| Self-hosted on user's own laptop | The user's local CLI auth (e.g. `gh auth login` already done) | ✅ Yes |
| Self-hosted on a team server | The server operator's CLI auth, single shared identity | ⚠️ Yes for org-wide read; not per-user |
| **Cloud (multi-tenant)** | No user credentials present | ❌ Requires user-supplied secret (e.g. GitHub PAT in `GH_TOKEN` env) — same UX friction as Notion's API token, not the "no-OAuth" promise |

The "use your existing CLI auth, no separate OAuth" pitch only holds cleanly for the self-hosted single-user case. Cloud must ship a per-user-token form alongside any CLI adapter, or restrict that adapter to self-hosted. This must be honest in any user-facing copy.

#### BYO-manifest security constraint

Manifests carry executable directives — for the CLI transport, an arbitrary `cmd` argv that gets handed to `subprocess.run`. **Letting end users upload manifests through a web UI is remote code execution as a feature.** Threat surface includes RCE, secret exfiltration, cross-tenant DB reads in cloud, resource exhaustion, internal-network egress, and path traversal in file/REST transports.

Until a sandbox design is built, the framework operates at **Tier 0**: manifests live only in the repository under `noosphere/core/connectors/manifests/`, ship with releases, and are reviewed by maintainers. No user-facing manifest upload anywhere. Self-hosted operators may still drop their own TOML into that directory at their own risk because they own the host.

When user-uploadable manifests become a product requirement, choose the strictest tier compatible with the use case:

| Tier | Mechanism | Where it fits |
|---|---|---|
| **Tier 0** (current) | Repo-only, maintainer review | Today, both self-hosted and cloud |
| **Tier 1** | Org-owner-only upload + binary allowlist + audit log | Self-hosted org workspaces |
| **Tier 2** | Allow only `transport=rest` or `transport=mcp-hosted` (no shell-out anywhere) | Cloud, when REST/MCP-only sources are enough |
| **Tier 3** | Containerised execution (Docker / Bubblewrap / Firejail) with no network egress, ephemeral FS, resource quotas | Cloud, when CLI BYO is genuinely required |

Tier 0 is in force today. Promoting the framework to a user-facing capability requires picking and implementing one of Tiers 1–3 explicitly; no implicit promotion.

### Built-in input formats (still supported)

These are the file/URL/feed inputs that don't require a source manifest — they're the substrate every adapter ultimately produces.

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
Source adapter → Ingest → Clean → Chunk → Embed → Index → Publish
```

Adapter-level concerns (rate limits, polling schedules, retries, auth refresh) are handled in the adapter framework. Everything downstream of "Ingest" is transport-agnostic — a Notion page from MCP, a GitHub issue from CLI, and a Granola transcript from email all become the same chunked + embedded document.

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

Discovery is the core value proposition of Noosphere: experts publish knowledge on their own terms, and agents/companies find what they need through the network. Without effective discovery, every knowledge base is an island — with it, the network becomes more valuable than the sum of its parts.

### The demand-side problem

Today, companies like Mercor hire domain experts one by one to train AI models.
The process is manual, slow, and expensive because production starts from the
buyer's order: post a spec, recruit or dispatch people, review the output, and
deliver a static dataset. Noosphere flips the mechanism. People and teams keep
building living knowledge bases for their own work; owners choose what agents
can discover, preview, license, and use. A crypto trading agent can draw on
multiple trading strategy corpora. A startup agent can pull from product,
growth, and pricing experts simultaneously. The supply side keeps growing; the
demand side discovers dynamically.

**The core differentiator (state it precisely).** Every data vendor — Scale,
Surge, Mercor, Luel — runs made-to-order production: a buyer posts a spec, the
platform dispatches and recruits humans to fulfill it (post-job → dispatch →
take-order → upload). Noosphere is the opposite: first it is a free,
user-owned knowledge production network where people and teams build and keep
growing corpora for their own reasons; then owners elect what agents can access,
under what terms. **Not assignment fulfillment.** Two properties follow:
**non-rivalry** (one supply licensed to unlimited consumers — no re-collection,
no exclusivity, no single sale) and an **automated, agent-initiated
transaction** (no human posting/dispatching work in between). "agents" spans
both runtime agents (the native mode — open-book lookup, never trained on) and
AI-lab training needs (a batch licensing adjacency on the same supply). Future
Noosphere can also support creators intentionally producing new corpora for
agent/model demand, but that is an extension of the channel, not the founding
production model.

**Two access designs.** (a) **Two-sided standard interface** — on `public`, the
manifest (or a well-known file) auto-advertises access-friendly supply and
exposes the minimal requirements a consumer must meet (a standardized
supply↔demand handshake). (b) **Minimal base + need-driven middle** — the
consumer's need drives discovery/acquisition/payment through `compile` /
`distill` / `search` plus manifest / `kb_reputation` / `preview_ask`. (b) is
the critical, load-bearing mechanism; see Phase 4g for the missing demand-side
half.

### Design: the cloud app IS the registry

The cloud deployment (`noosphere.wiki`) serves as both the hosted product for cloud users **and** the discovery registry for the entire network. There is no separate registry service — this keeps deployment simple (single service, single database) while still enabling a federated network.

```
┌───────────────────────────────────────────────────────┐
│           noosphere.wiki                          │
│     (cloud app + built-in registry)                   │
│                                                       │
│  ┌───────────────┐  ┌──────────────────────────────┐  │
│  │ corpora table │  │ registered_nodes +            │  │
│  │ (cloud users) │  │ registered_corpora tables     │  │
│  │               │  │ (remote self-hosted metadata) │  │
│  └───────────────┘  └──────────────────────────────┘  │
│                                                       │
│  GET /api/v1/network/search                           │
│    → query local corpora (same DB, fast)              │
│    → query registered_corpora (remote metadata)       │
│    → merge results, ranked by quality signals         │
│                                                       │
└───────────────────────────────────────────────────────┘
         ↑                          ↑
    Cloud users                Self-hosted nodes
    (corpora in same DB)       (register metadata via POST)
```

Self-hosted and cloud-hosted corpora are equal citizens in the network. Cloud corpora are discovered directly from the database. Self-hosted corpora register their metadata (name, description, tags, endpoint URL) so agents can discover and connect to them directly.

**What the registry stores for remote nodes:**
- corpus name, description, tags, endpoint URL, document count, word count, access level, status, last health check

**What it does NOT store:**
- document content, chunks, embeddings, auth tokens

### Self-hosted node registration

Self-hosted nodes register with the cloud app on startup:

```bash
# Register with the public Noosphere (default)
noosphere serve --port 8420

# Opt out — run as a standalone knowledge base
noosphere serve --port 8420 --no-registry

# Private/corporate registry
noosphere serve --port 8420 --registry https://internal.mycompany.com
```

Registration payload:

```json
{
  "endpoint": "https://mynode.example.com:8420",
  "node_version": "0.1.0",
  "corpora": [
    {
      "corpus_id": "abc-123",
      "name": "Crypto Trading Strategies",
      "slug": "crypto-trading",
      "description": "Quantitative trading strategies for crypto derivatives",
      "author": "Alice",
      "tags": ["crypto", "trading", "derivatives", "quant"],
      "document_count": 50,
      "chunk_count": 200,
      "word_count": 100000,
      "access_level": "paid",
      "status": "ready"
    }
  ]
}
```

Nodes re-register periodically (heartbeat). The registry updates metadata and records `last_seen`. Stale nodes (no heartbeat for >24 hours) are flagged but not removed — agents see reduced quality signals.

### Agent discovery protocol

Discovery is a 4-step funnel. Each step narrows the set of knowledge bases and increases confidence before committing to a query (especially a paid one).

```
Agent: "I need crypto derivatives pricing expertise"
                    ↓
         Step 1. Network search (metadata match)
            GET /api/v1/network/search?q=crypto+derivatives
            → Match on name, description, tags, author
            → Returns ranked list with quality signals
                    ↓
         Step 2. Evaluate quality signals (automatic)
            Each result carries objective metrics:
            document_count, word_count, freshness,
            query_count (popularity), uptime, status
            → Agent filters/ranks by these signals
                    ↓
         Step 3. Preview (sample content, no auth)
            GET /api/v1/corpora/{id}/preview
            → 3-5 representative chunks (truncated)
            → No authentication needed, even for paid corpora
            → Agent assesses topical relevance
                    ↓
         Step 4. Query or purchase
            POST /api/v1/corpora/{id}/search
            → Full ranked results with citations
            → For paid: checkout → bearer token → search
```

#### Step 1: Network search

**Endpoint:** `GET /api/v1/network/search?q={query}`

Searches across both local corpora and registered remote corpora using full-text search on name, description, tags, and author. Results are merged and ranked.

Response includes for each result:
- `corpus_id`, `name`, `slug`, `description`, `author`, `tags`
- `source`: `"local"` or `"remote"`
- `api_endpoint` and `mcp_endpoint` (for remote corpora)
- `quality`: objective quality signals (see below)
- `preview_url`: direct link to the preview endpoint

#### Step 2: Quality signals — the four-tier stack

Agent media needs a PageRank equivalent that is based on **informational value and verifiable provenance**, not attention. Signals are organized in four tiers, from cheapest-and-most-gameable to most-expensive-and-most-trustworthy.

**Tier 1 — Self-declared (cheap, manipulable)**

| Signal | What it tells agents | Source |
|--------|---------------------|--------|
| `manifest.description` | What the KB is about | Owner declares |
| `manifest.tags` / `task_types` | Declared domain and question shapes | Owner declares |
| `manifest.samples` | Representative Q&A for quick relevance check | Owner declares |
| `manifest.license_terms` | Allowed monetization shapes | Owner declares |
| `author.identity` | Who stands behind this KB | Owner declares (optionally verified) |

**Tier 2 — Computed / verifiable**

| Signal | What it tells agents | Source |
|--------|---------------------|--------|
| `document_count` | KB size / breadth | Ingestion |
| `word_count` | Content depth | Ingestion |
| `source_composition` | Mix of user_original / user_curated / external_public | Provenance rollup over documents |
| `last_updated` | Active maintenance, freshness | Last registration heartbeat |
| `status` | Indexing state (`draft`, `indexing`, `ready`) | Pipeline |
| `uptime` | Reliability for production use | Health check history |
| `source_verification` | % of claimed sources resolving | Link check |

**Tier 3 — Accumulated via usage (adversarial-resistant, slow to bootstrap)**

| Signal | What it tells agents | Source |
|--------|---------------------|--------|
| `query_count` | Demand / proven usefulness | Query log |
| `query_diversity` | Breadth of questions answered (not just one popular query repeated) | Query log clustering |
| `citations_in` | Incoming citations from other KBs, weighted by citing KB's reputation — agent-era PageRank | Citation graph |
| `refund_rate` / `satisfaction` | Paying agents' reported value | Payment system |
| `calibration` | Historical accuracy of self-reported confidence | Outcome tracking |
| `entity_reputation` | Track record attached to the KB itself, independent of author | Computed from above |

**Tier 4 — Interactive (consumer-invoked)**

| Signal | What it tells agents | Source |
|--------|---------------------|--------|
| Static preview | Representative chunks, no auth | `GET /preview` (shipped) |
| `preview_ask` (live query) | One free or low-cost query for evaluation | `POST /preview-ask` (Phase 4) |
| Benchmark responses | Answers to standardized probes per declared domain | Standardized test set (later) |

**Design principles:**

1. **Signals are axes, not a ranking function.** The platform exposes values; each consuming agent weights them for its task. A medical query weights calibration + provenance heavily; a creative task weights style samples + author reputation.
2. **Weight Tier 2+ heavily.** Tier 1 alone is suspect — self-declaration is free to fake.
3. **Bootstrap path.** New KBs have no Tier 3 data, so Tier 1+2+4 carry more weight early. Tier 3 accrues with usage.
4. **Author reputation ≠ entity reputation.** A KB inherits some authority from its author at launch, but the KB itself accumulates independent track record.
5. **Adversarial resistance.** As the network grows, some actors will try to game signals. Keeping Tier 2 and Tier 3 costly-to-fake is core to the stack.

Agents implement their own ranking on top of these signals. A simple heuristic for early-stage discovery:

```
relevance_score   = text_match(query, manifest)
tier2_score       = log(document_count + 1) * 0.25
                  + log(word_count + 1) * 0.15
                  + freshness_decay(last_updated) * 0.10
                  + source_composition_user_original_weight * 0.10
tier3_score       = log(query_count + 1) * 0.15
                  + log(citations_in + 1) * 0.15
                  + calibration_score * 0.10

final_score = relevance_score * 0.5 + tier2_score * 0.3 + tier3_score * 0.2
```

Consumers should treat this as a starting point, not a fixed ranking. Task context shifts the weights.

#### Step 3: Preview

**Endpoint:** `GET /api/v1/corpora/{id}/preview`

Preview is the "try before you buy" mechanism. It returns enough content for an agent to assess whether a knowledge base is topically relevant, without giving away the full content.

**No authentication required** — even for paid and token-gated corpora. This is by design: agents need to evaluate relevance before committing to payment or token exchange.

Response schema:

```json
{
  "corpus_id": "abc-123",
  "name": "Crypto Trading Strategies",
  "description": "Quantitative trading strategies for crypto derivatives",
  "author": "Alice",
  "tags": ["crypto", "trading", "derivatives"],
  "access_level": "paid",
  "quality": {
    "document_count": 50,
    "word_count": 100000,
    "query_count": 342,
    "last_updated": "2026-04-10T14:30:00Z",
    "status": "ready"
  },
  "samples": [
    {
      "text": "Delta-neutral strategies in crypto involve balancing long and short positions across correlated assets to minimize directional exposure while capturing...",
      "document_title": "Delta-Neutral Crypto Strategies",
      "document_type": "markdown"
    }
  ],
  "content_types": [
    {"type": "markdown", "count": 35},
    {"type": "pdf", "count": 15}
  ]
}
```

**Sample selection rules:**
- Maximum 5 samples, one per document (deduplicated by document_id)
- Text truncated to 250 characters
- Ordered by most recent chunks first
- Enough to assess topic coverage, not enough to replace a full query

#### Step 4: Query or purchase

Once an agent has confirmed relevance through preview, it queries the knowledge base directly:

- **Public corpora:** `POST /api/v1/corpora/{id}/search` — no auth needed
- **Token-gated corpora:** Same endpoint with `Authorization: Bearer {token}` header
- **Paid corpora:** `POST /api/v1/corpora/{id}/checkout` → Stripe Checkout → receive `payment_id` → use as bearer token for queries

For remote (self-hosted) corpora, the agent connects directly to the node's endpoint. Content never passes through the registry.

```
Agent                       noosphere.wiki              Self-hosted node
  |                               |                               |
  |-- network/search ----------> |                               |
  |<-- [{results + endpoints}] --|                               |
  |                                                               |
  |-- preview (remote) ----------------------------------------> |
  |<-- {samples, quality} <------------------------------------- |
  |                                                               |
  |-- search (remote, with auth) -----------------------------> |
  |<-- [{text, citation, score}] <------------------------------ |
```

### MCP discovery

The same discovery flow is available through MCP tools, enabling agents that connect via MCP (Claude, Cursor, Codex, etc.) to discover and evaluate knowledge bases programmatically:

| MCP Tool | Equivalent REST Endpoint | Purpose |
|----------|--------------------------|---------|
| `list_corpora` | `GET /api/v1/corpora` | Browse available knowledge bases |
| `preview` | `GET /api/v1/corpora/{id}/preview` | Evaluate relevance before querying |
| `get_stats` | `GET /api/v1/corpora/{id}` | Check quality signals |
| `get_topics` | — | Understand knowledge base coverage |
| `search` | `POST /api/v1/corpora/{id}/search` | Full semantic search with citations |
| `get_manifest` | `GET /api/v1/corpora/{id}` | Full corpus metadata |

The `preview` tool is particularly important: it lets an MCP-connected agent assess a knowledge base (including paid ones) before committing to a search query.

### Health check

Node health is checked via a cron-compatible endpoint (`GET /api/v1/cron/health-check`) that pings all registered self-hosted nodes. Cloud corpora don't need health checks — they're in the same database.

Health check results feed into quality signals:
- Nodes that respond get `uptime` incremented
- Nodes that fail are flagged with `last_health_status: "down"`
- After 24h of failures, the node's corpora are deprioritized in search results (but not removed)

### Network effects

As the network grows, Tier 3 signals get richer and ranking becomes more discriminating:

1. **Query count + diversity as demand proof.** Most-queried KBs rise, but weighted by whether they answer *diverse* questions well, not just one viral query.
2. **Citation graph PageRank.** When a compiled note in corpus A cites corpus B, B accumulates incoming authority from A. Weighting is recursive — citations from high-reputation KBs count more. This is the agent-era PageRank and requires **Day-1 schema support** for citation edges.
3. **Calibration track record.** KBs that report honest confidence (e.g. flagging "low confidence" on out-of-scope questions) accumulate higher trust than KBs that always answer with false certainty.
4. **Entity reputation separate from author.** The KB as an object builds its own track record. A KB re-authored by a new contributor retains the track record; a new KB by a well-known author gets a boost but still has to earn its own Tier 3 signals.
5. **Category emergence.** Natural clusters form (crypto, ML, legal, etc.) from tag + citation patterns, enabling category-based browsing alongside search.
6. **Adversarial pressure.** As money flows, some actors will try to fake signals. The stack must keep Tier 2 and Tier 3 costly-to-fake — e.g. citations from gamed KBs get deweighted recursively; calibration requires held-out probe-based verification.

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

| Resource | Free | Pro ($20/mo) | Team ($49/seat/mo) |
|----------|------|---------------|---------------------|
| Corpora | 1 | Unlimited | Unlimited |
| Seats | 1 | 1 | 3–50 |
| Documents per corpus | 100 | Unlimited | Unlimited |
| Embedding tokens/month | 10K | Unlimited | Unlimited |
| Storage | 100MB | 10GB+ | Pooled |
| Internal queries/month (members + their agents) | 1,000 | 100K | Pooled |
| External paid queries | N/A | Supported | Supported |
| Access levels | All | All | All |
| Paid corpus support | Stripe Connect | Stripe Connect | Stripe Connect |
| Audio transcription | Not available | Whisper API included | Whisper API included |

**Team tier rationale.** The individual create → compile → share/monetize loop applies equally at org scale (see "Six things" in Core value, and the SimpleClosure asset-value case). Team is not a different product — it is the same loop with multiple contributors and pooled resources. We deliberately did not split out a "Business" tier: `access_level` is per-corpus, not tier-gated, so a Team user can already publish any corpus as public / paid / token. Enterprise-style features (SSO, audit retention, IP allowlist) are deferred until a real customer asks.

**Query counting has three separate buckets:**
- **Internal queries** (org members + their agents) — counted against tier limit
- **External paid queries** (`access_level=paid`) — **not** counted against tier; platform takes 10% via Stripe Connect
- **External public queries** (anonymous, `access_level=public`) — separate quota sized to prevent infra abuse without penalizing openness

### Transaction commission (cloud only)

Three monetization shapes, all via Stripe Connect:
- **Pay-per-query** — agent pays per request
- **Subscription** — recurring access
- **Corpus licensing** — bulk / one-time access for training or enterprise use

Split:
- Creator gets 90%
- Platform gets 10%
- Stripe fees are separate (~2.9% + $0.30)

Self-hosted users who set up their own Stripe keep 100%.

### Anti-patterns (explicitly out)

We do not monetize visibility or placement. The following are **permanent design commitments**, not future options:

- **No sponsored corpus / paid placement in results** — ranking tracks information value and provenance, not who paid.
- **No brand injection in returned answers** — answers cite real sources; they do not embed sponsor references.
- **No lead-gen commissions** — we do not take a cut when an answer drives a downstream conversion off-platform.

Attention-based monetization reintroduces social media's failure mode (popular ≠ valuable). Agent media depends on trust tracking information value; breaking that contract would break the platform.

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
- [x] Web frontend redesign: agent-readable UX (terminal, prominent endpoints, inline docs)
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

#### 2a. Registry — the network becomes real

- [x] Built-in registry: the cloud app serves as both product and discovery registry (no separate service)
- [x] Registry search API: agents query the registry to find corpora across all nodes (local + remote)
- [x] Registry health checks: cron-compatible endpoint pings registered self-hosted nodes
- [x] Registry directory: browsable view of all public knowledge bases in the Noosphere

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

- [x] `noosphere/cloud/` — managed auth (Supabase), quota enforcement, Stripe Connect (BSL)
- [x] Free/Pro tier billing (Pro subscription checkout + webhook handlers)
- [x] Platform commission (10%) on paid corpus revenue via Stripe Connect
- [x] PostgreSQL database adapter (SQLite for self-hosted, PostgreSQL for cloud)
- [ ] Cloud deployment (Vercel + Neon PostgreSQL — single service, cloud app IS the registry)

### Phase 4: Agent Media upgrades

Goal: move corpora from retrieval endpoints to **KB-as-agent interfaces**, and build out the discovery/trust infrastructure that makes agent media work. This is the phase where Noosphere earns its positioning in §Core value #5 and #6.

**4a. Capability surface — KB-as-agent interface (Static foundation)**

Applies to every corpus regardless of autonomy tier — the substrate that makes a KB an agentic node.

- [x] Expand manifest schema: `task_types`, `source_composition`, `samples`, `autonomy_level`, `calibration_policy`, `license_terms`
- [x] MCP + REST `ask` — synthesized answer with inline citations, grounded in retrieved passages
- [x] MCP + REST `describe` — structured self-description
- [x] MCP + REST `route` — recommend other KBs for out-of-scope questions (uses citation graph + manifest match)
- [x] MCP + REST `preview_ask` — truncated evaluation query that bypasses access gating so agents can judge answer quality before paying
- [x] Shared response runtime (per-corpus prompt + retrieval on top of shared inference layer)
- [x] Manifest auto-fill via LLM — `noosphere/core/manifest_autofill.py` proposes `task_types` + `samples` + `description_suggestion` from corpus content. REST `POST /corpora/{id}/manifest/suggest` returns a proposal; `POST /manifest/apply` writes selected fields. Post-ingest hook `autofill_if_empty` runs silently on first indexing. Pro-gated quota (`manifest_suggest`); self-hosted with LLM = free. Web UI Capability card spec in `docs/capability-card-ui.md` — frontend work deferred until static/ changes settle.

**4b. Discovery and trust — four-tier signal stack**
- [x] Source composition rollup (Tier 2)
- [ ] Source verification (link-resolve check) (Tier 2)
- [x] Citation edge schema + ingestion (Tier 3) — `corpus_citations` table, owner-declared manifest citations via REST, feeds `kb_reputation`
- [ ] Query diversity metric (Tier 3)
- [x] Query retention (Tier 3) — `query_retention_score` from repeat `agent_id` over 30d
- [x] Satisfaction rate (Tier 3) — `satisfaction_score` = 1 - refund_rate over 90d
- [ ] Calibration tracking (Tier 3) — v2a stubbed at 0.5; needs feedback endpoint for real measurement
- [ ] Entity reputation computation (Tier 3)
- [x] KBR v2a — four-term weighted composite; nightly refresh via `POST /cron/refresh-kb-reputation`
- [ ] Adversarial-resistance pass: recursive citation deweighting, probe-based calibration verification
- [ ] Author / creator profile as a **separate** Tier 1 signal (identity + optional external-platform reputation like GitHub, Scholar). Kept distinct from `kb_reputation` so agents can distinguish "famous author" from "proven KB" — a new Karpathy KB has high author signal but low KBR until it earns its own. Low default weight; decays as KBR accumulates.

**4c. Inter-KB learning mechanisms**
- [x] Direct query with provenance — `X-Noosphere-Caller-Corpus` header attribution on `ask`; successful inter-KB calls auto-record `query`-kind citations (24h dedupe per pair) and refresh `kb_reputation` on the cited corpus
- [ ] Corpus subscription (KB A subscribes to KB B increments) — shipping order 2
- [ ] Skill / capsule import (Evolver-style portable capability units) — shipping order 3
- [ ] Derivative corpus with attribution chain — shipping order 4

**4d. Higher autonomy tiers (opt-in)**

Networking is the substrate (every corpus is reachable in the network by default). Autonomy is the dial — what the corpus does in the network without prompting. See Core value #5 for tier definitions.

*Living tier (mostly shipped via the connector framework):*
- [x] Auto-ingest from connected feeds (RSS, URL, directory sync)
- [ ] Periodic auto-compile from consumed material — keeps Wiki / entities / timelines in sync as sources change
- [ ] Stale-concept detection + scheduled recompile (uses `stale_threshold_days`)

*Fully Autonomous tier (new):*
- [ ] Owner-approved auto-subscribe to peer KBs (consumes their increments)
- [ ] Active peer discovery — corpus periodically scans the registry for relevant new corpora and proposes subscriptions
- [ ] Autonomous payment for paid corpora within owner-set budget / policy
- [ ] Outbound queries — corpus proactively queries peers when its own answer would be low-confidence; results fold into its compiled knowledge with provenance

**4e. Monetization extensions**
- [ ] Corpus licensing path (bulk / one-time, for training or enterprise use)
- [ ] Agent-to-agent payment support (agent on KB A pays agent on KB B)

**4f. Convenience features (previously Phase 4)**
- [ ] Background feed scheduler: auto-poll RSS sources on interval
- [ ] Scheduled enrichment: periodic compile + maintain runs (dream-cycle style)
- [ ] Feynman integration: Noosphere corpora as source-grounded minds
- [ ] Audio transcription (Whisper, cloud paid feature)

**4g. Two-sided matching — the demand side (settled direction, 2026-05-16; the load-bearing next work)**

Today only the supply side is machine-decidable (the manifest). Automated, non-broker matching needs the demand side in the same vocabulary, and a contract a buyer's principal can audit without a human reading prose. This is the conversion that turns described supply into an actual market.

- [ ] **Demand object** — a schema an agent carries to state its need (task type, topic, required provenance / calibration / freshness / license), mirroring the supply-side manifest so matching is two-sided in one vocabulary.
- [ ] **Conformance preview** — extend `preview_ask` to report conformance *against the caller's stated demand object*, including an honest "cannot satisfy."
- [ ] **`compile`/`distill` output contract** — claim-level output; each claim carries provenance, scope, asserted-at / superseded-by, confidence.
- [ ] **Machine-verifiable license/consent/provenance object** — promote `license_terms` + `source_composition` into a structured, buyer-auditable contract (permitted-use enum: single-use / cache / train / redistribute; per-claim binding; only originated content monetizable).
- [ ] **Per-need-type reputation** — `kb_reputation` accumulates conditioned on need-type, so the accumulated mapping replaces the broker's matching judgment.
- [ ] **Standard interface (design a)** — on `public`, auto-emit an access-friendly advertisement + minimal consumer requirements in the manifest / a well-known file.
- [ ] **Need-driven export path (design b)** — define how search + compile + distill produce either a per-query answer or a batch dataset shaped to a declared demand object, including rejection when the corpus cannot satisfy the need.
- [ ] **Directed-production extension** — design how a creator could later choose to build new corpora for known agent/model demand without turning Noosphere into a job-posting and dispatch marketplace.

Strategy note: native mode is runtime (per-query, no weights); post/pre-training are batch licensing adjacency off the same supply. Which mode to prioritize as the first commercial wedge is an open decision (current lean: post-training). Strategy/why lives in `docs/agent-data-market-thesis.md`; buildable roadmap lives here.

---

## Summary

Noosphere is the knowledge network for the agent era. Publish your knowledge as a living knowledge base any AI agent can discover, query, and cite. It grows over time as you add content. Share it free, keep it private, or charge for access.

The network connects all knowledge bases — self-hosted and cloud-hosted alike. Agents query the registry to discover knowledge, then connect directly to each node. Content stays on the creator's infrastructure; only metadata is shared for discovery.

The full product is open-source and self-hostable — including paid access (bring your own Stripe, keep 100%). The commercial layer adds hosting convenience and charges a 10% commission only when payment flows through the platform.

Creators own their knowledge, control access, and keep the revenue. The network makes every knowledge base more valuable by connecting it to the agents and organizations that need it.
