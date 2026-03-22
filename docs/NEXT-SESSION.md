# Completed: Open-Source Launch Readiness

All features from the launch plan have been implemented. Here's what was done:

## Phase A: Access Control (Security Baseline)
- [x] `noosphere/core/access.py` — `check_access()` middleware enforcing public/private/token/paid levels
- [x] `noosphere/core/tokens.py` — Token CRUD: create, list, revoke, validate (SHA-256 hashed)
- [x] API endpoints: POST/GET/DELETE `/corpora/:id/tokens`
- [x] Access checks on all read endpoints (REST + MCP)
- [x] Token management UI in right panel (generate, copy, revoke)
- [x] `paid` access level disabled with "Phase 2" tooltip

## Phase B: Global Search UI
- [x] Terminal handler renders search results with score/title/source cards
- [x] Corpus detail: Search | Chat tab toggle
- [x] Search tab calls `POST /corpora/:id/search` and displays cited passages

## Phase C: Fix Fake Features
- [x] Corpus card "..." menu with Rename, Export, Delete (with confirmation)
- [x] Removed "Register to the Noosphere" checkbox from Upload page
- [x] Token-gated selectable, Paid disabled in access dropdown
- [x] Registry status: "Registered in the Noosphere" / "Local only" in right panel
- [x] "Back to Noosphere" link at top of corpus detail

## Phase D: Complete Missing Features
- [x] Query logging with `agent_id` (X-Agent-ID header) and `token_id` tracking
- [x] Agent activity pulses on network graph (nodes with queries glow)
- [x] Export API endpoint: `GET /corpora/:id/export` returns ZIP
- [x] Export button in corpus right panel
- [x] SPEC-compliant export format: `noosphere.json`, `documents/`, `index/chunks.jsonl`, `meta/`
- [x] CLI export refactored to use shared `noosphere/core/export.py`

## Phase E: Tests
- [x] 115 tests across 8 files
- [x] `tests/conftest.py` — temp DB fixtures
- [x] `tests/test_corpus.py` — corpus CRUD
- [x] `tests/test_ingest.py` — ingestion pipeline
- [x] `tests/test_access.py` — access control
- [x] `tests/test_tokens.py` — token management
- [x] `tests/test_export.py` — export format
- [x] `tests/test_api.py` — FastAPI integration
- [x] `tests/test_mcp.py` — MCP protocol
- [x] `.github/workflows/test.yml` — CI config (Python 3.11-3.13)

## Phase F: Launch Polish
- [x] Fixed FastAPI deprecation warning (on_event -> lifespan)
- [x] MCP SSE transport: `GET /mcp/sse` + `POST /mcp/message` (Claude Desktop compatible)
- [x] Toast notification system for frontend errors
- [x] Graceful DB shutdown on app exit

## Next: Commercial Layer (Phase 2+)
- [ ] `noosphere/cloud/` directory (BSL): auth, quota, Stripe Connect
- [ ] Stripe integration for paid corpora
- [ ] Cloud deployment (PostgreSQL, Vercel/Railway)
- [ ] User registration + billing tiers
