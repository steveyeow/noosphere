# Noosphere — Gap Analysis & Next Iteration Plan

## Status of originally planned features

The original gap analysis compared Noosphere with Karpathy's LLM Wiki and GBrain. Most gaps have been closed:

| Feature | Status | Notes |
|---------|--------|-------|
| Chat Write-Back | ✅ Implemented | `POST /capture` endpoint + web UI. Chat responses can be saved to corpus. |
| RSS/Atom Ingestion | ✅ Implemented | `POST /ingest-feed` + CLI. Manual trigger; no auto-scheduler. |
| Batch URL Ingestion | ✅ Implemented | `POST /ingest-urls` + CLI. Up to 40 URLs per request. |
| LLM Compilation | ✅ Implemented | `POST /compile` + CLI. On-demand concept note generation from retrieved passages. |
| Knowledge Health | ✅ Implemented | `GET /knowledge-health` + CLI. Stale detection, missing chunks, empty links. |
| Maintain/Repair | ✅ Implemented | `POST /maintain`. Re-index with optional force rebuild. |
| Auto-Feed Scheduler | ❌ Not built | Background polling for RSS feeds. Users can use cron as workaround. |
| Dream Cycle | ❌ Not built | Automatic nightly enrichment. Low priority — personal KM feature, not network feature. |

---

## Network + Payments — COMPLETE

The GBrain/Karpathy gap was closed in Phase 1.5. Phase 2 closed the gaps in Noosphere's own core values — the **network** and the **marketplace**.

### Priority 1: Registry Server (Network — the moat) ✅

- **Registry server** (`noosphere/registry/`): accepts registration, stores node/corpus metadata in SQLite + FTS5
- **Registry search API**: `GET /api/v1/search?q=...` — agents discover corpora across all nodes
- **Health checks**: background thread pings nodes every 5 min, marks online/degraded/offline
- **Browsable directory**: HTML page at `/` with live search
- **CLI**: `noosphere registry-serve --port 8421`
- **20 tests** covering registration, deregistration, search, directory, stats, multi-node

### Priority 2: Stripe Integration (Get Paid) ✅

- **Stripe checkout**: `POST /corpora/{id}/checkout` creates a Stripe session
- **Payment verification**: `access.py` returns 402 for unpaid access, verifies payment_id or subscription
- **Two pricing models**: per-query (N queries per payment) and subscription (Stripe Price ID)
- **Webhook handlers**: checkout.session.completed, subscription.deleted, charge.refunded
- **Self-hosted**: creator's own `STRIPE_SECRET_KEY`, keeps 100%
- **Revenue dashboard**: `GET /corpora/{id}/revenue` — total revenue, payment count, active subs
- **16 tests** covering pricing config, access control, checkout, webhooks, revenue

### Priority 3: Web UI Completeness ✅

- **Chat "Save insight"** button: already wired to `/capture` endpoint
- **Feed management**: RSS Feed tab in Add panel (feed URL + max items)
- **Batch URL ingestion**: Batch URLs tab in Add panel (paste multiple URLs, one per line)
- **Compile trigger**: Compile tab in Add panel (topic + retrieval breadth)
- **Paid access settings**: pricing config UI in right panel (type, amount, queries/price ID) + revenue display

---

## Deprioritized (Phase 4)

These features improve individual knowledge base quality but don't strengthen the network or marketplace:

| Feature | Rationale for deprioritizing |
|---------|------------------------------|
| **Auto-feed scheduler** | RSS ingestion already works on-demand. Scheduler is convenience — users can use cron. |
| **LLM Compilation auto-mode** | On-demand compilation works. Making it automatic doesn't change the core value. |
| **Dream cycle / enrichment** | Personal KM feature modeled after GBrain. Noosphere's priority is the network, not being a better personal brain. |

These are not deleted from the roadmap — they move to Phase 4 after the network and payments are solid.

---

## What we intentionally skip

- **Structured entity schemas** (People, Companies, Meetings) — GBrain is a personal CRM. Noosphere is a knowledge publishing network.
- **Calendar/email/meeting integration** — Personal productivity features, not knowledge publishing.
- **Agent write-back from external agents** — The knowledge base owner controls what gets added. Chat capture gives the user the choice; automatic external agent write-back is a security/quality concern.
