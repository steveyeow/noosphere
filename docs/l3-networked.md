# L3 Networked Autonomy — Design Spec

**Status**: Design — not yet implemented.
**Parent**: SPEC.md §4c "Inter-KB learning mechanisms" + §4d "Higher autonomy levels".
**Corresponds to**: `autonomy_level >= 3` in `corpora.autonomy_level` (currently just a stored integer with no triggered behavior).

## 1. What L3 actually means

Current right-rail copy:

> **Networked** — Subscribes to peer KBs, absorbs their updates, and exposes its own compiled pages for them to subscribe back.

Decomposed into three concrete capabilities the KB must actually *do*:

| Capability | What it means operationally | Who initiates |
|---|---|---|
| **Discover** | KB keeps an index of peer KBs it cares about (owner-chosen or LLM-proposed from `route`/citation graph) | Owner (with LLM assist) |
| **Subscribe** | KB has an owner-approved subscription list; each subscription = a declared intent to periodically pull content from peer X | Owner |
| **Absorb** | On schedule, KB performs outbound `ask` / `search` / `describe` calls to each subscribed peer, brings results back, ingests them as documents (new `source_kind`) | Scheduler (autonomous) |
| **Expose** | KB's own compiled Wiki pages are already exposed via `/ask` / `/describe` — no new work. Peers subscribe by adding us to their own subscription list | Other KBs' owners |

"Mutual learning" = two KBs each independently subscribing to the other. There is **no special peer-to-peer negotiation protocol**; it's just two one-way subscriptions that happen to point at each other.

## 2. Access model — explicitly normal

Subscriptions do **not** bypass access gating. A subscription is just a persistent intent to call `/ask` on a peer; the call itself is subject to the peer's `access_level`:

- **Public peer** → subscription runs free (normal public query)
- **Token peer** → subscription requires the subscriber's owner to have pre-acquired an access token, which is stored alongside the subscription row
- **Paid peer** → subscription consumes the subscriber owner's budget (see §6) per call; uses an existing payment_id as bearer like any paid caller

This is the explicit design decision from the 2026-04 discussion: **no peer-privileged access path**. "Networked" is automation + budgeting on top of the existing agent-access interface, not a new access tier.

## 3. Data model

Three new tables.

### `peer_subscriptions`

```sql
CREATE TABLE peer_subscriptions (
    id TEXT PRIMARY KEY,                    -- uuid4
    subscriber_corpus_id TEXT NOT NULL,     -- the KB doing the subscribing
    target_corpus_id TEXT,                  -- local target (nullable if remote-only)
    target_endpoint TEXT,                   -- e.g. "https://other-node.com/api/v1/corpora/{slug}"
    target_slug TEXT,                       -- slug at target node (for display)

    -- What to pull
    mode TEXT NOT NULL,                     -- 'ask' | 'describe' | 'new_documents'
    query TEXT,                             -- for mode='ask': the question to run each cycle
    topic_filter TEXT,                      -- for mode='new_documents': tag / keyword filter
    cadence_minutes INTEGER NOT NULL,       -- poll interval (min 60, max 10080=1wk)
    max_docs_per_cycle INTEGER NOT NULL DEFAULT 5,

    -- Auth / payment
    bearer_token TEXT,                      -- token_id or payment_id for gated peers
    auth_mode TEXT NOT NULL,                -- 'public' | 'token' | 'paid'
    budget_cents_per_month INTEGER,         -- hard cap for 'paid' (NULL = no cap)

    -- State
    status TEXT NOT NULL,                   -- 'active' | 'paused' | 'failed' | 'revoked'
    last_run_at TEXT,
    next_run_at TEXT NOT NULL,
    last_error TEXT,
    consecutive_failures INTEGER DEFAULT 0,

    created_at TEXT NOT NULL,
    approved_by TEXT NOT NULL,              -- user_id of the corpus owner who approved
    FOREIGN KEY (subscriber_corpus_id) REFERENCES corpora(id) ON DELETE CASCADE
);

CREATE INDEX idx_peer_sub_next_run
    ON peer_subscriptions(status, next_run_at)
    WHERE status='active';
```

### `peer_subscription_runs`

Log of every poll execution — debugging + citation attribution + budget accounting.

```sql
CREATE TABLE peer_subscription_runs (
    id TEXT PRIMARY KEY,
    subscription_id TEXT NOT NULL,
    ran_at TEXT NOT NULL,
    outcome TEXT NOT NULL,                  -- 'ok' | 'no_new_content' | 'rate_limited' | 'auth_failed' | 'peer_down' | 'budget_exceeded' | 'error'
    docs_ingested INTEGER DEFAULT 0,
    chunks_ingested INTEGER DEFAULT 0,
    cents_spent INTEGER DEFAULT 0,
    latency_ms INTEGER,
    error_detail TEXT,
    FOREIGN KEY (subscription_id) REFERENCES peer_subscriptions(id) ON DELETE CASCADE
);

CREATE INDEX idx_peer_run_sub_date ON peer_subscription_runs(subscription_id, ran_at DESC);
```

### `source_kind` — new value

Add `peer_subscription` to the existing enum (currently: `user_original`, `user_capture`, `external_public`, `external_subscription`).

- Documents pulled via peer_subscription are marked `source_kind='peer_subscription'`
- `metadata_json` carries `{ subscription_id, peer_corpus_id, peer_endpoint, peer_name }` so the UI can show provenance
- Filtered OUT for paid external callers (same rule as `external_public`) — you can't resell learned-from-peers content as your own paid answers

## 4. Components

### 4.1 Subscription manager (backend module)

`noosphere/core/peer_subscriptions.py`

Functions:
- `create_subscription(subscriber_id, target, mode, ...) -> sub_id` — owner-only; validates target exists and is reachable; stores row with `next_run_at = now + cadence_minutes`
- `list_subscriptions(corpus_id) -> list[dict]`
- `pause_subscription(sub_id)` / `resume_subscription(sub_id)` / `revoke_subscription(sub_id)`
- `due_subscriptions(limit=50) -> list[dict]` — scheduler picker: `SELECT ... WHERE status='active' AND next_run_at <= now() ORDER BY next_run_at LIMIT ?`

### 4.2 Outbound runner

`noosphere/core/peer_runner.py` — executes a single subscription run.

```
run_subscription(sub_id):
    sub = load
    if sub.auth_mode == 'paid':
        remaining = budget - spent_this_month(sub_id)
        if remaining < sub.peer.pricing.amount_cents:
            log run(outcome='budget_exceeded'); mark paused; return

    headers = { 'X-Noosphere-Caller-Corpus': sub.subscriber_corpus_id }
    if sub.bearer_token: headers['Authorization'] = f'Bearer {sub.bearer_token}'

    match sub.mode:
        case 'ask':       resp = httpx.post(f'{sub.target_endpoint}/ask',       json={'question': sub.query}, headers=headers)
        case 'describe':  resp = httpx.get (f'{sub.target_endpoint}/describe',                                  headers=headers)
        case 'new_documents': resp = httpx.get(f'{sub.target_endpoint}/documents?since={sub.last_run_at}&filter={sub.topic_filter}', headers=headers)

    if 402 (payment required) → log 'auth_failed'; notify owner; pause
    if 429 (rate limited)    → log; exponential back-off on next_run_at
    if 5xx                   → log 'peer_down'; bump consecutive_failures; after 3 → pause

    on 200:
        docs = extract_new_documents(resp, since=sub.last_run_at, max=sub.max_docs_per_cycle)
        for d in docs:
            ingest_text(subscriber_id, ..., source_kind='peer_subscription',
                        metadata={subscription_id, peer_corpus_id, peer_endpoint, peer_name})
        record inter-KB citation (piggyback on existing citation graph; kind='subscription')
        log run(outcome='ok', docs_ingested=len(docs), cents_spent=price_if_paid)
        update next_run_at = now + cadence_minutes
```

### 4.3 Scheduler

Reuse the existing enrichment cron pattern (`ENRICHMENT_INTERVAL_MINUTES` in `config.py`). New tick: `POST /cron/run-peer-subscriptions` — picks up to N due subscriptions, runs each with a short timeout, commits. Safe to run every 5-10 min even if some subs are cadence=60min (it's a pull model, not a push).

### 4.4 REST endpoints

```
POST   /api/v1/corpora/{id}/subscriptions                 # Create subscription (owner-only)
GET    /api/v1/corpora/{id}/subscriptions                 # List
PATCH  /api/v1/corpora/{id}/subscriptions/{sub_id}        # Pause / resume / update cadence
DELETE /api/v1/corpora/{id}/subscriptions/{sub_id}        # Revoke (hard delete)
GET    /api/v1/corpora/{id}/subscriptions/{sub_id}/runs   # Run history for debugging
POST   /api/v1/cron/run-peer-subscriptions                # Scheduler entry
```

All of the above require owner authentication on the *subscriber* corpus. No target-side authorization needed — the target KB just sees normal inbound `ask` / `describe` calls with `X-Noosphere-Caller-Corpus` header set.

## 5. Integration with existing systems

### 5.1 autonomy_level

- Setting `autonomy_level >= 3` alone no longer means anything hidden — the actual trigger is **having at least one active subscription**.
- Re-derive `autonomy_level` on subscription create / revoke:
  - 0 if no feeds + no auto-compile + no subscriptions
  - 1 if connectors/RSS active
  - 2 if auto-compile enabled
  - 3 if at least one active peer_subscription
- This makes the right-rail badge self-truthful: it reflects what the KB *is* configured to do, derived from state, not a number the owner toggled.

### 5.2 kb_reputation

- Each successful peer_subscription run records a `citation` edge (kind='subscription') from subscriber → target.
- Subscription edges weight heavier than ad-hoc `query` edges in the PageRank computation (subscribing is a stronger signal of trust than a one-off query). Concretely: `subscription` edges contribute 3× the weight of `query` edges in the adjacency input to `compute_kb_reputation`.

### 5.3 Registry

- Peer discovery uses the existing `registered_corpora` table — no new registry endpoints needed.
- Subscription target can be selected from either local corpora or remote registered corpora.

### 5.4 source_kind filtering

- `caller='external'` already filters out `external_public` + `external_subscription`. Add `peer_subscription` to that filter set.
- Effect: paid queries to a Networked KB can't be answered with material pulled from other KBs. The subscriber consumed the peer's answers; they can't resell them.

## 6. Budget & rate limits

### 6.1 Budget (for paid peers)

- `budget_cents_per_month` per subscription. Enforced per subscription, not per corpus.
- Monthly window is calendar month. Reset at UTC midnight on the 1st.
- When hit: log `outcome='budget_exceeded'`, pause subscription, email/notify owner.
- Aggregate budget view in account dashboard (Backlog): "This month you've spent $X across N subscriptions."

### 6.2 Rate limits (subscriber side)

- Minimum cadence = 60 minutes. Hard-coded. UI doesn't let users pick less.
- Max cadence = 1 week (10080 min). Longer than this, just disable.
- The runner runs at most 20 subscriptions per tick to keep tick duration bounded.

### 6.3 Rate limits (target side)

- Target KB sees subscriptions as normal `ask` / `search` calls. Target's existing quota / rate-limit logic applies unchanged. If the target is the Cloud platform and subscriber is Free, their own daily `ask` quota limits how many subs can fire per day.

## 7. UI surface

Minimum needed:

1. **New right-panel sub-block** inside Access when `access_level` allows the corpus to be subscribed to, showing inbound subscriber count ("3 peer KBs follow this").
2. **New right-panel sub-block** in Autonomy section: "Subscriptions (N)". Lists subscribed peers as tiny rows. Each row: peer name + cadence + status dot. Click → detail modal with runs history, pause/resume, revoke.
3. **Add subscription** action — button in Autonomy section or Insights tab. Opens modal:
   - Step 1: Pick peer (local corpus dropdown + "search network" autocomplete hitting `/api/v1/network/search`)
   - Step 2: Pick mode (Ask a recurring question / Pull new documents / Refresh capability card)
   - Step 3: If peer is paid → show price, confirm budget cap
   - Step 4: Cadence + confirm
4. **Insights tab** (already a placeholder) shows per-subscription run history.

Defer a dedicated "Discover peers" browse UI. Start with owner-picks-explicitly.

## 8. Phased build plan

**Phase 1 — Core** (~2–3 focused sessions)
- [ ] Migrations: `peer_subscriptions`, `peer_subscription_runs`, extend `source_kind` enum checks in code
- [ ] `core/peer_subscriptions.py` — CRUD
- [ ] `core/peer_runner.py` — single run execution
- [ ] REST endpoints (create / list / revoke)
- [ ] Cron endpoint `/cron/run-peer-subscriptions`
- [ ] UI: minimal list + Add-subscription modal in right-rail Autonomy section
- [ ] Derive `autonomy_level` from state on subscription change

**Phase 2 — Trust wiring** (1 session)
- [ ] Record subscription-kind citations into `corpus_citations`
- [ ] Update `compute_kb_reputation` weight table
- [ ] Add `source_kind='peer_subscription'` to external-caller filter in `retrieval.py`

**Phase 3 — Budget & safety** (1 session)
- [ ] Monthly budget enforcement in runner
- [ ] Consecutive-failure pause
- [ ] Owner notification on auth_failed / budget_exceeded (email if cloud, toast if web UI open)

**Phase 4 — Discovery / polish** (1 session)
- [ ] Peer autocomplete from `/api/v1/network/search`
- [ ] Insights tab subscription runs panel
- [ ] Inbound-subscriber count on target's Access sub-block

## 9. Open questions

1. **Subscription of mode='new_documents'**: target needs to expose `GET /corpora/{id}/documents?since=...` already does. But for paid / external callers, will that endpoint filter by `source_kind`? It currently does not filter — we need to add the same caller-based filter that `search_corpus` applies. (Follow-up: unify the filter in a `_access_filter()` helper.)

2. **Ingesting synthesized answers**: for mode='ask', we bring back a synthesized answer string. How is it stored?
   - Option A: one document per cycle, doc_type='peer_answer', content = LLM answer text
   - Option B: feed it into the subscriber's compile pipeline as a passage among other sources
   - **Recommendation**: A. Simpler, clearer provenance. Compile can still pick it up as a source.

3. **Duplicate detection for mode='new_documents'**: target will return overlapping doc lists across cycles. Use `content_hash` already computed by `ingest_text` — it naturally dedupes.

4. **Revocation propagation**: when subscriber deletes subscription, should target know? Probably not — target just sees fewer inbound queries. The citation graph decays naturally because no new `subscription`-kind citations are recorded.

5. **Loop detection**: KB-A subscribes to KB-B, KB-B subscribes to KB-A. Both pull each other's content indefinitely. Content-hash dedupe prevents duplicate ingestion, but budgets still get consumed. Add a check: if target's recent docs are >50% peer_subscription content, log a warning and skip. (Defer; rare in practice at small N.)

## 10. Acceptance criteria

L3 Networked is done when:

- Owner can add a subscription from the web UI (pick peer, mode, cadence, budget if paid).
- Scheduler runs subscriptions on cadence; outcomes logged.
- Subscribed documents appear in the subscriber's Sources section with `source_kind='peer_subscription'` and visible peer attribution.
- `autonomy_level` of a corpus with >=1 active subscription auto-displays as Networked.
- External callers to subscribed KBs do not see peer-subscription content in answers.
- Paid subscriptions enforce monthly budget cap and pause on overrun.
- Subscription-kind citations feed into `kb_reputation` at 3× the weight of query-kind citations.

## 11. References

- Parent spec: `SPEC.md` §4c, §4d, §6.4 (source_kind access policy)
- Related: `docs/agent-media.md` (agent-as-KB framing)
- Existing infrastructure reused: `corpus_citations`, `registered_corpora`, `X-Noosphere-Caller-Corpus` header, `core/access.py` gating, `retrieval.py` caller-based filtering.
