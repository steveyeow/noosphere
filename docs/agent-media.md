# Noosphere Thesis: Agent Media

Working document. Captures the thesis, the architectural commitments that follow from it, and the open design questions we still need to resolve. Supersedes the earlier `team-tier.md` — pricing is downstream of the thesis, not the thesis itself.

Origin session: `32dd6e97-034a-418e-b32c-b02285825e7f` (2026-04-20), expanded in follow-up discussion 2026-04-21.

---

## 1. Thesis: Noosphere is the next information platform

Information platforms evolve in eras, and each era is shaped by how information is consumed:

- **Portals** — curated directories for humans (Yahoo, MSN)
- **Search** — ranked retrieval for humans (Google)
- **Social media** — attention marketplaces for humans (Facebook, Twitter, TikTok)
- **Agent media** — information platforms for agent consumption

Social media optimized for human attention, so popular content is often not the most valuable. Agents don't pay an attention tax — they select for **informational value** and **verifiable provenance**. The next information platform is shaped by that constraint.

Noosphere's ambition is to be that next-era platform.

- **Near-term**: humans ingest, compile, and publish knowledge; agents consume and pay for it.
- **Medium-term**: humans also consume back from the network (agent-synthesized answers over raw search).
- **Long-term**: agents learn from each other through the network, building on knowledge other agents have compiled and published back.

## 2. Two core capabilities

From the thesis, the product has exactly two things it must be uniquely good at:

1. **Fast, flexible knowledge creation** — Write, Distill, and Connect. Turn what a human knows into an agent-readable corpus with minimal friction.
2. **Publish and sell to agents** — machine-readable discovery, trust signals, provenance, pricing, and payment, all engineered for agent consumers.

Everything else is downstream of these two. Features that don't strengthen one or both are likely noise.

## 3. Symmetry: individual → team → company

Noosphere's loop — `create → compile → share/monetize` — is already defined for individuals. The same loop applies at team and company scale. A team tier is **not a different product**; it's the same loop with multiple contributors.

Grounding references that came out of discussion:

- **SimpleClosure / Asset Hub**. The transcription company cielo24 sold 13 years of Slack, Jira, and email through SimpleClosure for hundreds of thousands of dollars. This is proof that organizational knowledge has real monetary value. The product opportunity is to let companies *continuously* grow and monetize this asset during their life — not liquidate it at end-of-life.
- **GStack / Superpower / YC CEO skill packs / chef example**. Individual expertise distilled into sellable, queryable artifacts. The "Cooking Stack" framing names the endgame: tacit know-how becomes a product that agents query and pay for.

Both references point at the same loop applied at different scales. This is why Team pricing collapsed to a single tier (see §8) — splitting "collaboration" from "external access" imported an old SaaS pattern that doesn't fit here.

## 4. Knowledge bases are agents

For discovery, trust, and inter-KB learning to work, a knowledge base cannot be just a document collection retrieved via search. It must be a stateful, callable entity with self-description and an interface — an **agent**.

```
KB-as-agent = {
  corpus,     // underlying knowledge (human-authored + agent-absorbed)
  manifest,   // self-description: domain, depth, samples, recency, source mix, pricing
  interface,  // answer / cite / route / subscribe / preview_ask
  state,      // query history, citation graph position, calibration track record
  policy      // who can access, at what price, and how it learns
}
```

### Autonomy levels

Every KB has the agent interface; autonomy is what varies.

| Level | Behavior |
|---|---|
| **L0 — Responsive** (default) | self-describe, answer with citation, route fallback, report calibrated uncertainty |
| **L1 — Subscribing** | + subscribe to other KBs, auto-ingest incremental updates |
| **L2 — Synthesizing** | + compile reusable skills / capsules from consumed content |
| **L3 — Proactive** | + initiate outbound queries, persona, outreach |

Each level is a superset of the previous. New corpora default to L0. Owners opt in to higher levels. Higher autonomy unlocks higher monetization potential — an L3 Cooking Stack plausibly commands higher per-query pricing than a passive reference archive.

This mirrors Evolver's Gene → Capsule distinction: L0 behaves like a static fetched Gene; L2+ behaves like a mutating Capsule. We should look at Evolver's protocol (GEP) to decide whether to interoperate or build our own primitives.

## 5. Discovery and trust: four-tier signal stack

Agent media needs a PageRank equivalent, but it cannot be based on attention. It must be based on **informational value** and **verifiable provenance**. Signals form four tiers, from cheapest-and-most-gameable to most-expensive-and-most-trustworthy.

### Tier 1 — Self-declared (cheap, manipulable)
- **Manifest**: domain tags, task types, description, sample Q&A, pricing, access terms, author claim
- **Recency claim**: last-updated timestamp

### Tier 2 — Computed / verifiable
- **Corpus metrics**: `document_count`, `word_count`
- **Source composition**: breakdown by `source_kind` (user_original / user_curated / external_public / etc.) — already tracked in ingestion
- **Source verification**: do claimed sources resolve? any dead links?
- **Indexing status**: ready / draft / indexing
- **Uptime / availability**: health-check history

### Tier 3 — Accumulated via usage (adversarial-resistant, slow to bootstrap)
- **Query count** — demand signal
- **Query diversity** — breadth of questions successfully answered, not just one popular query repeated
- **Citation graph** — incoming citations from other KBs, weighted by the citing KB's own reputation (agent-era PageRank)
- **Refund / satisfaction rate** — from paying agents
- **Calibration history** — predicted vs actual correctness; does this KB report honest confidence?
- **Entity reputation** — track record attached to the KB itself, independent of author (enables collective or re-authored KBs)

### Tier 4 — Interactive (consumer-invoked)
- **Static preview** — representative chunks, no auth (already built)
- **`preview_ask` (live query)** — one free or low-cost query against the live interface for evaluation
- **Benchmark responses** — responses to standardized probes per declared domain

### Design principles

1. **Signals are axes, not a ranking function.** The platform exposes values; each consuming agent weights them for its own task. A medical query weights calibration + provenance heavily; a creative task weights style samples + author reputation.
2. **Weight Tier 2+ heavily.** Tier 1 alone is suspect — self-declaration is free to fake.
3. **Bootstrap path**. New KBs have no Tier 3 data, so Tier 1 + 2 + 4 carry more weight early. Tier 3 accrues with usage.
4. **Author reputation ≠ entity reputation.** A KB inherits some authority from its author at launch, but the KB itself accumulates independent track record.
5. **Adversarial resistance matters.** As the network grows, some actors will try to game signals. The stack must keep Tier 2+3 signals costly-to-fake.

### What this replaces / drops from earlier thinking

- "Human reputation" as a single signal is too coarse — split into author identity (Tier 1 claim) and entity reputation (Tier 3 computed).
- "Economic signals" (market price) as a trust signal is weak — market price is an input to the buy/no-buy decision, not a trust signal. Refund rate is the real trust signal and is kept.
- Added: source composition, source verification, `preview_ask` (live evaluation query), benchmark responses, query diversity, entity reputation, adversarial framing.

## 6. Inter-KB learning mechanisms

How do KBs actually learn from each other? Four mechanisms, from lightest to heaviest:

1. **Direct query** — KB A pays to query KB B for one answer. (Closest to current pay-per-query. Ship first.)
2. **Corpus subscription** — KB A subscribes to KB B's incremental updates. Substack-shaped.
3. **Skill / capsule import** — KB A imports a compiled capability from KB B. Evolver-shaped.
4. **Derivative corpus** — KB A builds a new corpus on top of KB B's content, with attribution. Creative-Commons-shaped citation chain.

Provenance and billing complexity increase from 1 → 4. Ship 1 first; 2–4 are later. Provenance tracking must be in place from 1 so later mechanisms can compose cleanly.

## 7. Monetization

### Allowed paths (price information value)
- **Pay-per-query / subscription access** — agent or user pays per usage
- **Corpus licensing** — full corpus licensed for training or bulk access (the live-company version of the SimpleClosure case)

### Anti-patterns (permanent design commitment)
- **Sponsored corpus / placement** — paying to be surfaced first in agent answers
- **Brand injection** — embedding brand references in returned answers
- **Lead-gen fees** — taking a cut when the KB's answer drives a downstream conversion

These reintroduce social media's failure mode: attention bought rather than earned. Agent media's whole premise is that trust tracks information value. Attention-based monetization would break that contract. This is not a future option we might open up — it's an anti-commitment.

## 8. Pricing tiers (downstream of thesis)

| Tier | Monthly | Seats | Corpora | Notes |
|---|---|---|---|---|
| Personal Free | $0 | 1 | 1 | Existing |
| Personal Pro | $20 | 1 | ∞ | Existing |
| **Team** | $49/seat | 3–50 | ∞ | Multi-contributor; all access levels; 10% platform fee on paid access |

**Explicitly dropped**:
- **Business tier** — `access_level` is per-corpus, not tier-gated. A Team user can already set any access level including `paid`. No hard reason to split.
- **Enterprise tier** — deferred until real customer demand. No hypothetical compliance features.

**Three separate query buckets**:
- **Internal queries** (org members + their agents) — counted against tier limit
- **External paid queries** (`access_level=paid`) — not counted against tier; 10% platform fee via Stripe Connect
- **External public queries** (anonymous, `access_level=public`) — separate quota to prevent infrastructure abuse, sized generously to not penalize openness

## 9. UX references

- **Notion** — connector paywall pattern; composer bottom-left / bottom-right `my sources` / `add sources` affordances; mapping: our corpus ↔ Notion project/file, our sources ↔ Notion connector.
- **Claude Code connectors page** — fallback reference when Notion is paywalled.
- **Feynman subscription page** (github.com/steveyeow/feynman) — card styling reference.

## 10. Open decisions

1. ~~**L0 interface shape at Day 1.**~~ **Resolved (M2).** Shipped `ask` (synthesized answer with inline [N] citations + score-based confidence), `describe` (capability card), and `preview_ask` (truncated free-evaluation query that bypasses paid gating) as REST endpoints and MCP tools. `route` deferred to M3 (needs citation graph).
2. ~~**Manifest as a first-class data-model object.**~~ **Resolved (M1).** Manifest expanded with `task_types`, `source_composition` (computed rollup), `samples`, `autonomy_level`, `calibration_policy`, `license_terms`. Exposed in corpus detail, preview (`capability` block), registry payload, and exported `noosphere.json` (bumped to schema_version 1.1).
3. ~~**Citation graph as Day 1 schema.**~~ **Resolved (M3).** Shipped `corpus_citations` table with four edge kinds (manifest / route / query / derivative). Owner-declared manifest citations land via `POST /corpora/{id}/citations`. The citation-weighted PageRank feeds into `kb_reputation` (the Tier 3 rollup score on each KB).
4. ~~**`preview_ask` pricing.**~~ **Resolved (M2).** Free with daily rate limit; quota bucket `preview_ask` (100/day Free, 2000/day Pro).
5. **Benchmark responses.** Standardized probes per domain. Probably later, once we see what domains cluster.
6. **Entity-reputation model.** Computation, storage, decay. Needs a dedicated design pass.
7. **Evolver alignment.** Is it worth speaking Evolver's GEP / Gene / Capsule vocabulary for interop, or do we build our own primitives? Closer look at their spec needed.
8. ~~**KB-as-agent runtime.**~~ **Resolved (M2).** Landed as a shared runtime: one module (`noosphere/core/kb_agent.py`) reuses the existing retrieval + LLM layer with a per-corpus prompt and capability context. L0 doesn't need per-KB inference isolation; future higher autonomy levels (L1/L2/L3) can layer on.
9. **Author / creator profile as a separate signal.** Keep distinct from `kb_reputation` — "Karpathy famous" ≠ "Karpathy's KB is good." Low default weight, decays as KBR accumulates. Needs external profile connectors (GitHub, Scholar, verified identity). Design pass + connector design pending.
10. **KBR v1 → v2 formula.** Current formula only activates `citation_pagerank` (weight 0.4). M4 should light up `query_retention` (0.3), `calibration_accuracy` (0.2), `satisfaction_rate` (0.1). Retention and satisfaction have natural data sources once inter-KB queries accrue (M5 just shipped). Calibration needs a ground-truth signal — probably starts from agent/user feedback on `ask` answers.
11. **Manifest auto-fill (LLM-proposed, owner-approved).** Reduce the onboarding drop-off: today a new KB starts with empty `task_types`/`samples`/`license_terms`. System should propose; owner accepts. Pro-tier feature (LLM cost); self-hosted users get it free when they bring their own LLM. Free tier: manual fill only.
