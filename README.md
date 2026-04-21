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

1. **Ingest** — Markdown directories, file upload, single URL, **multiple URLs in one request**, **RSS/Atom feeds** (recurring inflow), PDF/DOCX/CSV/JSON. Everything becomes documents in a corpus.
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

Discovery works through layered signals — no manual ratings needed:

```
Agent: "I need crypto derivatives pricing expertise"
                    ↓
         1. Network search (metadata)
            Match on name, description, tags, author
                    ↓
         2. Quality signals (automatic)
            document_count, source_composition, citations_in,
            kb_reputation, freshness, uptime
                    ↓
         3. Preview (sample content) + describe (capability card)
            GET /api/v1/corpora/{id}/preview
            GET /api/v1/corpora/{id}/describe
                    ↓
         4. preview_ask (evaluation query) before paying
            POST /api/v1/corpora/{id}/preview-ask
            → truncated synthesized answer, bypasses access gating
                    ↓
         5. ask or search (committed use)
            POST /api/v1/corpora/{id}/ask      → synthesized answer + citations
            POST /api/v1/corpora/{id}/search   → ranked chunks + citations
```

Agents talk to every corpus through the same small toolbox:

| Tool | What it returns | When to use |
|------|-----------------|-------------|
| `describe` | Machine-readable capability card (task types, sample Q&A, source mix, `kb_reputation`, license) | Step 2–3: decide if a KB looks right for your task |
| `preview` | A few representative chunks + quality signals | Step 3: glance at the content |
| `preview_ask` | Truncated synthesized answer to an evaluation question (bypasses paid gating) | Step 4: try before you pay |
| `ask` | Full synthesized answer with inline `[N]` citations + calibrated confidence | Step 5: committed use |
| `route` | Ranked list of other KBs that may answer better | Any step: hop to a better-fit KB |
| `search` | Ranked raw chunks with citations | Step 5: when you want passages, not synthesis |

`ask` respects access level (paid / token / public); `preview_ask` does not, so paid KBs can still be evaluated without pre-commitment. `route` and `describe` are always public.

**Quality signals are automatic and layered across four tiers** — self-declared (manifest), computed (corpus metrics, provenance), accumulated (queries, citations, calibration), and interactive (preview, live evaluation). No user ratings required — signals emerge from the data and the network.

| Signal | What it tells you | Source | Tier |
|--------|-------------------|--------|------|
| `document_count` | Knowledge base size | Registration metadata | Computed |
| `word_count` | Content depth | Registration metadata | Computed |
| `source_composition` | Mix of user-original vs curated vs external | Ingestion provenance | Computed |
| `last_updated` | Active maintenance | Last registration heartbeat | Computed |
| `query_count` | Demand / usefulness | Query log (opt-in) | Accumulated |
| `query_diversity` | Breadth of questions answered | Query log | Accumulated |
| `citations_in` | Incoming citations from other KBs (agent-era PageRank) | Citation graph | Accumulated |
| `kb_reputation` | Rolled-up Tier 3 score (0–1); citation-weighted recursive trust | Citation graph + future retention/calibration/satisfaction | Accumulated |
| `calibration` | Historical accuracy of self-reported confidence | Query outcome tracking | Accumulated |
| `uptime` | Reliability | Health check history | Computed |
| `access_level` | Free vs. paid | Corpus config | Self-declared |

Signals are **axes, not a ranking function** — each consuming agent weights them for its own task. A medical query weights calibration + provenance heavily; a creative task weights style samples + author reputation. Tier 1 (self-declared) alone is suspect; Tier 2+ carries more weight. New KBs bootstrap from Tiers 1/2/4; Tier 3 accrues with usage.

**KB reputation (`kb_reputation`).** Tier 3 signals roll up into a single 0.0–1.0 score per corpus, surfaced on the capability card. The v1 formula uses a citation-weighted PageRank term — each incoming citation is weighted by the citing KB's own `kb_reputation`, so trust compounds recursively. Future terms (query retention, calibration accuracy, satisfaction rate) plug in as those signals land. New KBs start at 0 and accumulate with use; a well-known author speeds cold-start via Tier 1 signals but earns `kb_reputation` the same way everyone else does.

**Preview before commit.** Any knowledge base (including paid ones) exposes a preview — a few representative chunks so agents can assess relevance before purchasing access.

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