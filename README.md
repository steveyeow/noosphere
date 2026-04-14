# Noosphere

Noosphere lets you publish your knowledge — papers, blogs, newsletters, notes — as a living knowledge base any AI agent can discover, query, and cite. It grows over time as you add content. Keep it open, or charge for access.

## Why

Personal AI knowledge bases are clearly the future. But today they are all isolated, and there's no way to connect them or monetize the knowledge inside.

Noosphere is built on four ideas:

1. **A connected network.** Every knowledge base can join a global discovery network. An agent helping a startup founder can draw on the best thinking from thousands of domain experts — not just whatever one person uploaded.
2. **Agent-readable by design.** Every knowledge base is built for AI agents to discover, search, and cite with source attribution.
3. **Living knowledge.** Knowledge bases grow over time — from conversations, feeds, and new documents. Not static file dumps, but compounding knowledge systems.
4. **Creators get paid.** Open your knowledge to everyone, or set it to paid. Newsletter authors, domain experts, researchers — anyone with valuable knowledge can monetize it through the network. Organizations and agents pay for the expertise they need.

## What it does

1. **Ingest** — Markdown directories, file upload, single URL, **multiple URLs in one request**, **RSS/Atom feeds** (recurring inflow), PDF/DOCX/CSV/JSON. Everything becomes documents in a corpus.
2. **Grow** — **Save from chat** into the corpus (capture documents with provenance). **Compile** runs retrieval + LLM to add a fused “concept” note from existing material (similar in spirit to LLM-maintained wiki pages, but grounded on your stored sources).
3. **Index** — Documents are chunked, embedded, and indexed for hybrid search (keyword + vector + fusion).
4. **Serve** — Every corpus gets discovery and query endpoints. Agents connect directly; creators manage via the web UI.
5. **Control** — Public, private, token-gated, or paid. Bring your own Stripe, keep 100% — or use the hosted platform.

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

Noosphere is a decentralized knowledge network. Every self-hosted node is an equal participant — content stays on your server, only metadata is shared for discovery.

```
                    Noosphere Registry
                 (registry.noosphere.ai)
                  stores ONLY metadata:
              name, description, tags, endpoint
                   /        |        \
                  /         |         \
   Self-hosted       Self-hosted       Cloud-hosted
   Node A            Node B            Node C
   (your laptop)     (company server)  (platform)
        ↑                 ↑                ↑
        └─────────────────┴────────────────┘
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

On startup, your node registers with the Noosphere Registry. It sends only metadata (name, description, tags, endpoint URL). Your documents, chunks, and embeddings stay local.

### 3. Agents discover your knowledge

Any AI agent can search the registry to find relevant knowledge bases across the entire network:

```
Agent                          Registry                        Your Node
  |                               |                               |
  |-- GET /search?q=AI+safety --> |                               |
  |                               |                               |
  |<-- [{name, endpoint, ...}] ---|                               |
  |                                                               |
  |-- POST /api/v1/corpora/{id}/search  -----------------------> |
  |<-- [{text, citation, score}]  <------------------------------ |
```

The registry is a directory, not a proxy — agents connect directly to your server for queries.

### 4. Control access and get paid

Each knowledge base has an access level:

| Level | Who can query | Setup |
|-------|---------------|-------|
| `public` | Anyone | Default |
| `private` | Only you | `--no-registry` or set in UI |
| `token` | People with your access key | Generate keys in UI |
| `paid` | People who pay | Set pricing + your own Stripe key |

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

### Network configuration

```bash
# Default: register with the public Noosphere registry
noosphere serve --port 8420

# Opt out — run as a standalone knowledge base
noosphere serve --port 8420 --no-registry

# Private registry (e.g. within a company)
noosphere serve --port 8420 --registry https://internal.mycompany.com/registry

# Run your own registry server
noosphere registry-serve --port 8421
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