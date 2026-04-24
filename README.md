# Noosphere

Publish your knowledge as a living knowledge base any AI agent can discover, query, and learn from. It grows over time as you add content and as the network expands around it. Keep it open, or charge for access.

## Why

Information platforms change with how information is consumed. Portals indexed the web for humans. Search ranked it for humans. Social media competed for human attention — which means popular is rarely the same as valuable. Agents don't pay an attention tax; they select for informational value and verifiable provenance. The platform shape that fits agent consumption is different.

AI agents are getting better at executing tasks, but they still struggle with judgment — the kind that comes from deep domain expertise, hard-won experience, and contextual understanding. Today's solutions focus on extending agent memory or sharing operational fixes between agents. What's missing is the knowledge itself.

Noosphere adds a **human knowledge layer** to the agent ecosystem. Experts publish what they know; agents query, learn, and cite it — with attribution and quality signals built in.

1. **A knowledge layer for all agents.** Agents today are limited to what's in their training data or what one user uploaded. Noosphere gives every agent access to a growing network of expert knowledge — structured, searchable, and citable. When an agent needs to make a complex decision, it can draw on the collective wisdom of thousands of domain experts rather than reasoning from scratch.
2. **A connected network.** Every knowledge base can join a global discovery network. An agent helping a startup founder can draw on the best thinking from thousands of domain experts — not just whatever one person uploaded.
3. **Agent-readable by design.** Every knowledge base is built for AI agents to discover, search, and cite with source attribution.
4. **Living knowledge.** Knowledge bases grow over time — from conversations, feeds, new documents, and the network itself. As more experts publish and more agents query, the collective intelligence of the network compounds. Not static file dumps, but a growing knowledge ecosystem.
5. **Creators get paid.** Open your knowledge to all agents, or set it to paid. Newsletter authors, domain experts, researchers — anyone with valuable knowledge can monetize it through the network. Organizations and agents pay for the expertise they need.

## The design

How the five value propositions above are actually built.

### Creation paths

Four ways to grow a knowledge base, mixed freely in the same corpus:
- **Write / Note** — direct markdown, chat capture (`user_original` · `user_capture`)
- **Import** — upload files, or pull your own content from elsewhere: Obsidian vault, Notion ZIP, Twitter archive, your own blog URLs (all `user_original`)
- **Connect** — RSS feeds, external URLs, live connectors; recurring inflow that stays current (`external_public`)
- **Compile / Distill** — LLM-driven secondary work: `compile` fuses retrieved passages into concept notes; `distill` (planned) extracts your judgment via structured conversation (`user_capture`)

Provenance is tracked per document via `source_kind`. Manifests auto-maintain from corpus content so the KB's identity card stays current without manual upkeep.

### Agent interface

Every corpus exposes the same small toolbox:

| Tool | What it does |
|---|---|
| `ask` | Synthesized answer with inline `[N]` citations + calibrated confidence |
| `describe` | Machine-readable capability card (manifest) |
| `preview_ask` | Truncated evaluation query — bypasses paid gating |
| `route` | Recommend other KBs for out-of-scope questions |
| `preview` | Static sample chunks |
| `search` | Ranked raw chunks with citations |

`ask` respects access level (paid / token / public); `preview_ask` does not, so agents can evaluate paid KBs before committing.

### Discovery and trust

Every corpus has a machine-readable **manifest** — its identity card: task types, sample Q&A, source composition, calibration policy, license terms. Agents read it to decide whether you're worth querying.

Discovery is signal-based, not attention-based. Four tiers:
- **Self-declared** — manifest fields; cheap, falsifiable
- **Computed** — corpus size, provenance, uptime; costly to fake
- **Accumulated** — `kb_reputation` rolls up citation-weighted PageRank + retention + calibration + satisfaction; grows with real usage
- **Interactive** — `preview` content + `preview_ask` live evaluation

### Autonomy and inter-KB learning

Autonomy is layered, opt-in:
- **L0 responsive** (default) — answers when queried
- **L1 subscribing** — ingests live updates from other KBs
- **L2 synthesizing** — compiles new skills from what it consumes (the "Cooking Stack" pattern)
- **L3 proactive** — persona, outbound queries, initiative

Inter-KB queries carry provenance (`X-Noosphere-Caller-Corpus`) and auto-record citations in a directed graph. Each edge is weighted by the citing KB's own reputation, so trust compounds recursively and feeds back into `kb_reputation`.

### Monetization

Four pricing shapes: **pay-per-query**, **subscription**, **corpus licensing** (bulk / training-data deals), **agent-to-agent payment** (autonomous transactions).

**Only user-originated content is monetizable.** Documents you imported from third parties (RSS, external URLs) are filtered out for external callers — you can't re-sell other people's content. Creator sovereignty and anti-copyright-laundering in one rule.

No sponsored placement, no brand injection, no lead-gen fees — pricing and ranking track value delivered, not exposure bought. Self-hosted: bring your own Stripe, keep 100%. Cloud: 10% commission on platform-facilitated payments only.

### How agents decide to pay

Paying for a query is never a single signal. The agent combines multiple factors, all exposed on the same public endpoints every caller sees — no privileged channel, no hidden API.

**Match — declared (via `describe` → manifest)**
The manifest is the primary declared channel. Cheap to read, easy to claim, falsifiable on inspection.
- `task_types` — enum of query shapes the KB handles (`how-to`, `factual-lookup`, `synthesis`, `advice`, `comparison`, `retrieval`). Topical fit at zero cost.
- `description`, `tags` — free-text scope.
- `calibration_policy` — does the KB report answer confidence? `self` (owner-assessed) or `third_party` (externally calibrated)? Decision-chaining agents filter hard on this.
- `source_composition` — `user_original` / `user_capture` / `external_public` ratios. Predicts originality of answers.
- `samples` — example Q&A. Lowest-weight declared signal (owner picks them).

**Depth — computed (from corpus data)**
Signals the owner can't fabricate without actually doing the work.
- `document_count`, `chunk_count`, `word_count` — corpus depth.
- Per-document `source_kind` — at query time, **`external_public` chunks are filtered out for paid callers** (anti-copyright-laundering). A large corpus that's mostly scraped will return thin paid answers regardless of what the manifest claims.
- Endpoint uptime and registry liveness.

**Trust — accumulated (`kb_reputation` ∈ [0, 1])**
```
KBR = 0.4·citation_pagerank
    + 0.3·query_retention
    + 0.2·calibration_accuracy
    + 0.1·satisfaction_rate
```
- `citation_pagerank` — how often other KBs cite this one, weighted by the citing KB's own reputation (recursive). Forgeable only by bribing already-reputable peers.
- `query_retention` — do agents come back to this KB after querying once? High retention = useful enough to return to.
- `calibration_accuracy` — when the KB reports "confidence 0.9", does it actually get those right 90% of the time? Measured against verified answers.
- `satisfaction_rate` — agent-reported success on paid calls.

KBR is the one signal owners can't directly set. It accumulates from real citations, real return usage, real calibration checks.

**Fit — interactive (via `preview_ask` / `preview` / `search` / `route`)**
Before paying, the agent can actually try the KB.
- `preview_ask` — **the key affordance.** Bypasses paid gating (Free 100/day, Pro 2000/day on hosted), returns a truncated but real answer to the agent's actual question. Query-specific quality signal, not a generic claim.
- `preview` — static sample chunks for structural inspection.
- `search` — ranked raw chunks with citations; exposes retrieval quality without synthesis cost.
- `route` — the KB can self-declare a question is out of scope and redirect the agent. An honest `route` response saves both sides a wasted paid call.

**Cost — price + access (`pricing` + `access_level`)**
- `pricing` returns per-query or subscription cost in cents.
- `access_level` flags whether payment is even possible (`paid` = yes; `token` = needs pre-granted token; `public` = no payment needed; `private` = can't query).
- Callers attach an `X-Noosphere-Caller-Corpus` header so citations are recorded in the graph when a paid query resolves to answers — which then feeds back into the citing KB's and the answering KB's reputation.

**The decision, roughly:**
```
should_pay(kb, q, policy) =
    in_scope(kb.describe, q)                              # Match
  ∧ kb.kb_reputation      ≥ policy.min_kbr                # Trust
  ∧ preview_ask(kb, q).quality ≥ policy.min_preview       # Fit
  ∧ kb.pricing.per_query  ≤ policy.budget_for(q)          # Cost
  ∧ (kb.calibration_policy.source == "third_party"        # Optional
     if policy.requires_calibration)
```

Not every agent uses every factor — cheap lookups skip `preview_ask`; high-stakes decisions require third-party calibration; research agents weight `source_composition` heavily. The system publishes every signal on a uniform interface; agents pick their own weights.

**What this means for creators:**
Three categories are under your control — declared (write the manifest), computed (choose what to ingest), interactive (enable `preview_ask`, keep the KB reachable). The fourth — accumulated reputation — can't be bought. A small, well-cited, calibrated KB out-earns a sprawling uncited one.

## Who it's for

**Creators (supply side):** Build your own knowledge base — like [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) or [Garry Tan's GBrain](https://github.com/garrytan/gbrain), but without the engineering setup. Upload your files, paste your blog URLs, subscribe to RSS feeds. Your knowledge base grows over time. Share it free, or charge for access.

**Agents and organizations (demand side):** Find expert knowledge across the entire network. Today, companies like Mercor hire domain experts one by one to train AI. Noosphere flips this — experts publish their knowledge on their own terms, and agents discover what they need through the network. A crypto trading agent can draw on trading strategy knowledge bases from multiple experts. A startup agent can pull from product, growth, and pricing experts simultaneously.

```
Supply side                              Demand side
┌──────────────────┐                     ┌──────────────────┐
│ Crypto trader    │──┐                  │ Trading agent    │
│ ML researcher    │──┤  Noosphere       │ Startup founder  │
│ Product expert   │──┼─ network ───────→│ Research team    │
│ Legal specialist │──┤  (discovery +    │ Custom AI app    │
│ Climate scientist│──┘   quality signals│ Any MCP client   │
└──────────────────┘     + direct query) └──────────────────┘
```

## What it does

1. **Ingest** — Markdown directories, file upload, single URL, **multiple URLs in one request**, **Obsidian vaults** (wikilinks + tags preserved), **Notion / Twitter archives**, **RSS/Atom feeds** (recurring inflow), PDF/DOCX/CSV/JSON. Everything becomes documents in a corpus.
2. **Grow** — **Save from chat** into the corpus (capture documents with provenance). **Compile** runs retrieval + LLM to add a fused “concept” note from existing material (similar in spirit to LLM-maintained wiki pages, but grounded on your stored sources).
3. **Index** — Documents are chunked, embedded, and indexed for hybrid search (keyword + vector + fusion).
4. **Serve** — Every corpus exposes an agent interface: MCP and REST endpoints to query, cite, and preview. Agents talk to the corpus; they don't just download it. The interface expands over time — capability self-description, routing beyond scope, calibrated confidence.
5. **Control** — Public, private, token-gated, or paid. Bring your own Stripe, keep 100% — or use the hosted platform. No sponsored placement or brand injection in results: ranking and pricing track informational value, not paid visibility.

## Quick start

```bash
git clone https://github.com/steveyeow/noosphere.git
cd noosphere
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your embedding API key

# Ingest a directory of Markdown files
python -m noosphere.cli init ./my-knowledge-base --name "My Knowledge"

# Serve it locally (MCP + REST API + Web UI)
python -m noosphere.cli serve --port 8420
```

Then:

- Open `http://localhost:8420` for the web UI with interactive corpus network
- Connect your MCP client (Claude, Cursor, etc.) to `http://localhost:8420/mcp`
- Use the REST API at `http://localhost:8420/api/v1/corpora`

## Ingesting your knowledge

Noosphere is designed as a general knowledge layer — no single tool is the source of truth. You bring your knowledge in through whichever path fits what you already have, and every document lands in the same corpus with the same `source_kind` attribution, search index, and agent interface.

The composer's `+` menu has two kinds of entry points, cleanly separated:

- **Primitive actions** — Upload file, Import a page, Add RSS feed. Format-agnostic, not tied to any app.
- **Sources** — My sources (connected apps) and Add a source (browse the app catalog). Every third-party app — Obsidian, Notion, Twitter, future Google Drive / GitHub / Gmail / Slack — lives here. Clicking an app opens its **per-app panel** listing every method that app supports (one-shot archive import, live sync, plugin, etc.) with status badges (Ready / Beta / Soon).

The app catalog is also reachable from the composer's source-logo strip and the `#/connectors` page. All three entry points open the same per-app panel, so there's one place to learn what each app can do.

### Upload files

Drop PDFs, Markdown, DOCX, TXT, CSV, JSON, or HTML. You pick the `source_kind` when the file is something other than your own work. Files are parsed, chunked, embedded, and indexed in the background — searchable in seconds.

### Import a page (URL or paste)

Paste a URL and Noosphere fetches + cleans the article into Markdown. Paste raw text and the first line becomes the title. Useful for one-off reference material — blog posts, papers, someone's essay — that you want agents to be able to cite.

### Connect an RSS/Atom feed

For sources that keep producing new content — a blog, a substack, a podcast feed — use composer `+` → **Add RSS feed**. Noosphere ingests the current posts immediately; Pro accounts get automatic re-polling so new posts keep flowing in. Feed content is `external_public` — it won't be resold to paying callers, but it's fully searchable within your own corpus.

### Obsidian — vault import + live sync (Karpathy-style)

Obsidian gets first-class support with two methods, both reachable from the **Obsidian** entry in the app catalog:

**1. Upload vault (ZIP)** — one-shot. Zip your vault folder in Finder/Explorer (Compress), upload the ZIP. Every `.md` note becomes a document; your vault and Noosphere diverge after that.

**2. CLI two-way sync** — persistent. The [Karpathy "LLM-maintained wiki"](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) pattern: your vault stays on disk, Obsidian stays your editor, Noosphere mirrors edits in the background and keeps the index fresh.

```bash
# One-time: point Noosphere at your vault
python -m noosphere.cli sync ~/my-vault --corpus my-knowledge --obsidian

# Keep it live: re-sync on every file change (Ctrl+C to stop)
python -m noosphere.cli sync ~/my-vault --corpus my-knowledge --obsidian --watch
```

Both methods preserve:
- Every `.md` note becomes a document (`source_kind=user_original` — it's your writing)
- **YAML frontmatter** — `tags:`, `aliases:`, `created:`, custom properties flow into document metadata. List syntax (`tags: [a, b]` or block `- a`) is parsed.
- **Folder structure** — the top-level folder becomes a tag; the full path is stored on the document as `metadata.folder_path`
- **`#hashtags`** in note bodies → merged into the document's tag list
- **`[[wikilinks]]`** → captured as `metadata.wikilink_targets` AND immediately resolved to entity mentions. An existing entity whose `canonical_name` or any alias matches the wikilink target (case-insensitive) gets linked; a new `concept`-kind entity is auto-created otherwise. `[[Alice|alt]]`, `[[Page#section]]`, and `[[Folder/Page]]` are all handled. In the web UI, wikilinks render as clickable links that navigate to the entity page.

Skipped: `.obsidian/` config, `.trash/`, dotfiles, `__noosphere/` (the writeback mirror, below), and attachments (images, embedded PDFs). Upload important attachments separately via the regular file uploader.

### Writeback — Noosphere-synthesized pages land in your vault

By default, every `sync --obsidian` run mirrors Noosphere's compiled entity and concept pages back into your vault as `__noosphere/` markdown files:

```
your-vault/
├── notes/...            # your notes (untouched)
├── daily/...            # your notes (untouched)
└── __noosphere/         # written by Noosphere — safe to open in Obsidian
    ├── entities/
    │   ├── alice.md     # compiled entity description + aliases + ids
    │   └── bob.md
    ├── concepts/
    │   └── llm-wikis.md # compiled wiki pages from the Compile flow
    └── .sync-state.json # hash state for conflict detection
```

**Human always wins.** If you edit any file in `__noosphere/`, the CLI detects the hash drift on the next sync and skips overwriting — your edits are preserved and the server update is dropped with a warning. (The server-side content still evolves; you'll see it again if you delete the locally-edited file.)

**Incremental.** The CLI tracks the last writeback timestamp in `.sync-state.json` and asks the server for only what's changed since.

**Opt out**: pass `--no-writeback` to disable. The vault then stays pristine — nothing Noosphere-generated gets written to disk. Useful if you'd rather view enrichments only in the Noosphere web UI.

### Obsidian plugin

For one-click sync + watch mode from inside Obsidian, install the plugin that lives in [`plugin/`](plugin/). It's a thin UX layer on top of the same `sync --obsidian` path — ribbon icon, command palette entries, status bar with last-sync summary, settings tab for server URL / corpus / token / writeback toggle.

Install: build locally (`cd plugin && npm install && npm run build`) and copy `manifest.json`, `main.js`, `styles.css` into `<your-vault>/.obsidian/plugins/noosphere-sync/`. See [`plugin/README.md`](plugin/README.md) for full instructions.

The plugin requires **self-hosted Noosphere running on the same machine as Obsidian** for v0.1 — both need direct filesystem access to the vault. Cloud Noosphere (where server and Obsidian are on different machines) needs a file-upload variant that's on the roadmap. Community plugin directory submission is a separate step from building — documented in the plugin README.

### Import other archives

Same pattern as Obsidian's ZIP method — each app's panel includes its own archive uploader:
- **Notion** workspace exports (Settings → Data export → Markdown & CSV)
- **Twitter / X** data exports (twitter.com/settings/download_your_data)

Both land as `user_original` — you're importing your own data, and what you publish on Noosphere can be monetized if you choose.

### Save from chat

Every answer in chat has a **Save to corpus** affordance. A comparison you asked for, an analysis, a useful synthesis — any of these can be filed back into the corpus as a new document (`source_kind=user_capture`). This is how explorations compound into your knowledge base instead of disappearing into chat history.

### CLI — bulk ingest a folder

For scripted workflows or first-time onboarding of a large existing folder:

```bash
python -m noosphere.cli init ./my-knowledge-base --name "My Knowledge"
```

Walks the directory, ingests every supported file, and runs the initial index. Equivalent to using the web upload repeatedly, but scriptable. For Obsidian vaults use `sync --obsidian` (above) instead — it knows about wikilinks, tags, and vault conventions.

### Roadmap — more connectors

The composer's source picker lists the full catalog. Shipping one at a time:

| Connector       | Status         | Notes                                                             |
| --------------- | -------------- | ----------------------------------------------------------------- |
| Obsidian        | **Available**  | ZIP import + CLI two-way sync (`--obsidian --watch`) + Obsidian plugin ([`plugin/`](plugin/))|
| Notion          | **Available**  | ZIP import today; live-sync OAuth planned                         |
| Twitter / X     | **Available**  | One-shot archive import                                           |
| RSS / Atom      | **Available**  | Manual feed add today; auto-polling on Pro planned                |
| Google Drive    | Coming soon    | Docs, Sheets, folder selection                                    |
| GitHub          | Coming soon    | READMEs, issues, discussions                                      |
| Gmail           | Coming soon    | Threads filtered by label                                         |
| Slack           | Coming soon    | Channels and DMs                                                  |
| Email forwarding| Coming soon    | A unique inbox address per corpus                                 |

Every connector lands as a document in the same corpus — the agent interface (`ask`, `search`, `describe`, etc.) doesn't care where a document came from, only about `source_kind` attribution and whether it's monetizable under the Principle-3 copyright rule.

## How the network works

Noosphere is a decentralized knowledge network with a built-in registry. The cloud app (`app.noosphere.wiki`) is both the hosted product and the discovery registry. Self-hosted nodes register metadata with the registry so agents can find them — content stays on your server.

```
               app.noosphere.wiki
        (cloud app + built-in registry)
        ┌─────────────────────────────┐
        │  Local corpora (cloud users)│
        │  +                          │
        │  Registered metadata        │
        │  (self-hosted nodes)        │
        └─────────────────────────────┘
           ↑          ↑           ↑
      Cloud user   Self-hosted   Self-hosted
                   Node A        Node B
                   ↑              ↑
                   └──────────────┘
              Agents connect DIRECTLY to each node
              Content never leaves your infrastructure
```

### 1. Create a knowledge base

```bash
noosphere init ./my-docs --name "My Knowledge" --author "Jane Doe"
```

### 2. Serve it — auto-joins the network

```bash
noosphere serve --port 8420
```

On startup, your node registers with the Noosphere registry. It sends only metadata (name, description, tags, endpoint URL). Your documents, chunks, and embeddings stay local.

### 3. Agents discover your knowledge

Any AI agent can search the registry to find relevant knowledge bases — both cloud-hosted and self-hosted:

```
Agent                    app.noosphere.wiki              Your Node
  |                            |                             |
  |-- GET /api/v1/search ----> |                             |
  |                            | (search local + registered) |
  |<-- [{results}] -----------|                             |
  |                                                          |
  |  For self-hosted results:                                |
  |-- POST /api/v1/corpora/{id}/search ------------------>  |
  |<-- [{text, citation, score}] <-------------------------  |
```

The registry is a directory, not a proxy. Cloud corpora return full results directly. Self-hosted corpora return metadata + endpoint — agents connect directly to your server.

### How agents find the right knowledge

Agents query `GET /api/v1/network/search?q=...` to find corpora across the network, then call the per-corpus tools (`describe`, `preview`, `preview_ask`, `ask`, `route`, `search`) to evaluate and use a KB. Signal tiers, `kb_reputation`, and the full agent toolbox are covered in §The design above.

### 4. Control access and get paid

Each knowledge base has an access level:


| Level     | Who can query               | Setup                             |
| --------- | --------------------------- | --------------------------------- |
| `public`  | Anyone                      | Default                           |
| `private` | Only you                    | `--no-registry` or set in UI      |
| `token`   | People with your access key | Generate keys in UI               |
| `paid`    | People who pay              | Set pricing + your own Stripe key |


For paid access, self-hosted creators use their own Stripe account and keep 100% of revenue.

### Setting up paid access (Stripe)

To charge for access to your knowledge base:

**1. Add your Stripe keys to `.env`:**

```bash
STRIPE_SECRET_KEY=sk_live_...        # from https://dashboard.stripe.com/apikeys
STRIPE_WEBHOOK_SECRET=whsec_...      # from Stripe webhook settings (optional but recommended)
STRIPE_SUCCESS_URL=http://yoursite.com/payment/success
STRIPE_CANCEL_URL=http://yoursite.com/payment/cancel
```

**2. Set pricing on your corpus (two models):**

```bash
# Per-query: charge $5 for 100 queries
curl -X POST http://localhost:8420/api/v1/corpora/{id}/pricing \
  -H "Content-Type: application/json" \
  -d '{"type": "per_query", "amount_cents": 500, "queries_per_payment": 100}'

# Subscription: $9/month recurring (requires a Stripe Price ID from your dashboard)
curl -X POST http://localhost:8420/api/v1/corpora/{id}/pricing \
  -H "Content-Type: application/json" \
  -d '{"type": "subscription", "amount_cents": 900, "stripe_price_id": "price_..."}'
```

This automatically sets the corpus access level to `paid`.

**3. Agents/users purchase access:**

```bash
# Get a Stripe Checkout URL
curl -X POST http://localhost:8420/api/v1/corpora/{id}/checkout \
  -d '{"payer_email": "buyer@example.com"}'
# → {"checkout_url": "https://checkout.stripe.com/...", "payment_id": "..."}

# After payment, use payment_id as bearer token to query
curl -X POST http://localhost:8420/api/v1/corpora/{id}/search \
  -H "Authorization: Bearer {payment_id}" \
  -d '{"query": "pricing strategy"}'
```

**4. Track revenue:**

```bash
curl http://localhost:8420/api/v1/corpora/{id}/revenue
# → {"total_payments": 12, "total_revenue_cents": 6000, "active_subscriptions": 3, ...}
```

You can also configure pricing from the web UI under corpus settings.

> **Self-hosted = 100% yours.** You use your own Stripe account. Noosphere never touches the money. No platform commission.

### Registry configuration

```bash
# Default: register with the public Noosphere registry
noosphere serve --port 8420

# Opt out — run as a standalone knowledge base
noosphere serve --port 8420 --no-registry

# Private registry (e.g. within a company)
noosphere serve --port 8420 --registry https://internal.mycompany.com
```

## CLI commands

```bash
# Initialize a corpus from a directory
noosphere init ./my-docs --name "My Blog" --author "Jane Doe"

# Use semantic chunking for academic papers
noosphere init ./papers --name "Research" --chunk-strategy semantic

# Ingest more documents into an existing corpus
noosphere ingest ./more-docs --corpus my-blog

# Re-index (incremental — only re-embeds changed documents)
noosphere index --corpus my-blog

# Force full re-index (all documents)
noosphere index --corpus my-blog --force

# Sync a directory (add new, update changed, prune deleted)
noosphere sync ./my-docs --corpus my-blog --prune

# Recurring inflow: RSS/Atom → new documents (deduped), then index
noosphere ingest-feed --corpus my-blog "https://example.com/feed.xml"

# Many URLs at once
noosphere ingest-urls --corpus my-blog "https://a.example/p1" "https://a.example/p2"

# LLM “compile” a concept note from retrieved passages (needs chat API keys in .env)
noosphere compile --corpus my-blog "pricing strategy"

# Corpus health (missing chunks, staleness, empty markdown links)
noosphere health-knowledge --corpus my-blog

# List all corpora
noosphere list

# Search a corpus (hybrid: keyword + vector + RRF fusion)
noosphere search --corpus my-blog "How does pricing work?"

# Start the server
noosphere serve --port 8420
```

## Spec

See [SPEC.md](SPEC.md) for the full product specification, corpus format, API design, business model, and roadmap.

## License

MIT (open core). `noosphere/cloud/` is BSL 1.1 — it adds multi-tenant hosting, not features. Self-hosted users get the full product.