# Capability Card UI Spec

Frontend work deferred until the current `static/` in-flight changes are settled.
This doc specifies the UI the backend is ready for — `noosphere/api/static/` can
layer it in without further backend changes.

## Placement

On the corpus detail page, directly below the header (corpus name + author).
This is the "identity" section of the page — analogous to a GitHub repo's
`About` panel in the top-right, or the README preamble.

Mental model: **this is what agents see about the KB. Show it to the owner
first so they understand their KB's public face.**

## Data source

Single endpoint:

```
GET /api/v1/corpora/{id}/describe
```

Response shape:

```json
{
  "corpus_id": "abc123",
  "name": "Chinese Chef",
  "description": "Chinese cooking techniques and ratios.",
  "author": { "name": "Steve", "url": "https://..." },
  "tags": ["food", "cooking"],
  "task_types": ["advice", "synthesis"],
  "samples": [
    { "question": "How do I stir-fry?", "answer_preview": "Use high heat and peanut oil." }
  ],
  "autonomy_level": 0,
  "source_composition": { "user_original": 0.7, "external_public": 0.3 },
  "calibration_policy": { "reports_confidence": true, "confidence_source": "self" },
  "license_terms": { "query": "pay-per-query" },
  "access_level": "public",
  "kb_reputation": 0.34,
  "quality": { "document_count": 42, "word_count": 125000, "last_updated": "...", "status": "ready" }
}
```

## Layout

```
┌──────────────────────────────────────────────────────────────┐
│  Capability card          [kb_reputation: 0.34]  [L0 Responsive] │
├──────────────────────────────────────────────────────────────┤
│  Answers     [advice] [synthesis]                            │
│                                                               │
│  Content     42 docs · 125k words · updated 2h ago           │
│              70% your work · 30% external                    │
│                                                               │
│  Samples     ▸ How do I stir-fry?                            │
│              ▸ What's the soy sauce ratio?                    │
│                                                               │
│  Licensing   pay-per-query · $0.50 / query                   │
│  Confidence  self-reported                                   │
│                                                               │
│  [Auto-regenerate]    [Edit manually]                        │
└──────────────────────────────────────────────────────────────┘
```

## Field mapping

| Card label | Source field | Display |
|---|---|---|
| kb_reputation | `kb_reputation` | badge, 2-decimal, color scale green > 0.5, yellow 0.2–0.5, grey < 0.2 |
| Autonomy | `autonomy_level` | pill: L0 Responsive / L1 Subscribing / L2 Synthesizing / L3 Proactive |
| Answers | `task_types[]` | tags |
| Content stats | `quality.*` + `source_composition` | "N docs · Mk words · updated X" + "N% your work · N% external" |
| Samples | `samples[]` | collapsible list, click reveals answer_preview |
| Licensing | `license_terms` | summarized (e.g. "pay-per-query" → pricing row from `/pricing`) |
| Confidence | `calibration_policy` | "self-reported" / "agent-rated" / "not reported" |

## Owner-only actions

Two buttons:

1. **Auto-regenerate** → `POST /api/v1/corpora/{id}/manifest/suggest` returns a
   proposal. Show a diff (old vs proposed task_types / samples / description),
   let owner accept or dismiss. On accept, call
   `POST /api/v1/corpora/{id}/manifest/apply` with the accepted fields.

2. **Edit manually** → inline editor for `task_types` (multi-select from the 6
   valid enum values), `samples` (add/remove Q/A pairs), and optionally
   `description`. Saves via `PATCH /api/v1/corpora/{id}`.

## Auto-fill on creation

After the first `index-corpus` completes, the backend already runs
`autofill_if_empty` which populates `task_types` + `samples` silently (no-op
if LLM isn't available or if task_types is already set). By the time the owner
arrives at the corpus detail page, the card is pre-filled — they don't see an
empty card.

## Public view vs owner view

Same card, different affordances:

- **Owner sees**: both action buttons (Auto-regenerate, Edit manually)
- **Public viewer / agent sees**: card in read-only form (no buttons),
  plus a `Query this KB` primary action that reveals the endpoints
  (`/ask`, `/preview-ask`, `/search`) for copy-to-clipboard.

## Accessibility / behavior notes

- `kb_reputation` tooltip on hover: "Composite trust score from citations,
  retention, and paid-satisfaction history. Grows with real usage."
- `Autonomy` tooltip: short description of the current level + link to docs.
- Long sample questions should truncate with `...` and expand on click.
- If `task_types` is empty (LLM unavailable or manually cleared), show a
  subtle hint: "Add topics so agents know what you answer well." with a
  one-click button to trigger `/manifest/suggest`.
