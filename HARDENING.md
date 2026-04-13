# Noosphere Hardening Spec

Ship-readiness checklist — everything needed to go from working MVP to production-quality release.

## Status: Complete

---

## 1. Remaining Auth Gaps

### 1a. `DELETE /chat-sessions/{id}` — unauthenticated

The endpoint allows anyone who can reach the server to delete any chat session by ID.

**Fix:** Add `request: Request` parameter and `_require_owner(request)` check.

### 1b. `POST /corpora` — open to all

On a network-exposed instance, unauthenticated users can create corpora. Add owner check.

**Fix:** Add `request: Request` parameter and `_require_owner(request)` check.

### 1c. `POST /terminal` — unauthenticated

The terminal endpoint has no auth. Already fixed to only search public corpora, but write operations (upload, create corpus) triggered via terminal commands should require owner.

**Fix:** Add `request: Request` parameter and `_require_owner(request)` check.

---

## 2. Silent Error Swallowing

Multiple `except Exception: pass` blocks across the codebase silently swallow errors, making debugging impossible and allowing data divergence between chunks and FTS.

### Affected locations:


| File           | Function                  | Risk                                           |
| -------------- | ------------------------- | ---------------------------------------------- |
| `indexer.py`   | `_sync_fts_insert`        | FTS index diverges from chunks table           |
| `indexer.py`   | `_sync_fts_delete_doc`    | Stale FTS entries remain after doc deletion    |
| `indexer.py`   | `_sync_fts_delete_corpus` | Stale FTS entries remain after corpus deletion |
| `retrieval.py` | `_log_query`              | Query analytics lost silently                  |
| `retrieval.py` | `_deduplicate` (cosine)   | Failed dedup may return duplicates             |
| `routes.py`    | `api_global_search`       | Per-corpus errors swallowed                    |


**Fix:** Replace `pass` with `logging.warning(...)` in all cases. Do not change control flow — failures should still be non-fatal, but must be visible.

---

## 3. API Index Endpoint — Missing Parameters

`POST /corpora/{corpus_id}/index` always calls `index_corpus(corpus_id)` with defaults. The CLI supports `--force` and `--chunk-strategy` but the API has no way to pass these.

**Fix:** Add optional `IndexRequest` body with `force: bool = False` and `chunk_strategy: str | None = None`.

---

## 4. Frontend: Global Search UI

The backend `POST /api/v1/search` supports cross-corpus search, but the main view (`#/main`) has no UI to invoke it. The SPEC calls for a global search bar.

**Fix:** Add a search bar to the home view that queries `POST /search` and renders results with corpus attribution.

---

## 5. Frontend: Live Network Graph

The landing page D3 graph uses hardcoded demo data (`DM` array). The network view already uses live corpora, but the landing page should too.

**Fix:** Replace `DM` with a fetch to `GET /api/v1/corpora/network` for the landing graph. Fall back to demo data if no corpora exist.

---

## 6. URL Consistency

All URLs now unified to `github.com/steveyeow/noosphere`.

**Status:** Fixed.

---

## 7. Dead Import

`BackgroundTasks` is imported in `routes.py` but never used.

**Fix:** Remove from import line.

---

## 8. API Test Coverage

Untested endpoints:

- `POST /terminal`
- `POST /search` (global)
- `POST .../index`
- `POST .../ingest-url`
- `GET .../stats`
- `GET .../topics`
- `GET .../analytics`
- `DELETE /chat-sessions/{id}`
- `GET /corpora/network`

**Fix:** Add test functions for each.

---

## 9. CI Improvements

Current CI only runs `pytest`. No linting, no coverage.

**Fix:**

- Add `ruff` to `requirements-dev.txt` and CI
- Add `pytest-cov` with coverage reporting
- Fail CI if coverage drops below threshold

---

## Implementation Order

1. Auth gaps (1a-1c) + dead import cleanup (7)
2. Silent error → logging (2)
3. API index params (3)
4. Frontend: global search (4) + live graph (5) + URL fix (6)
5. API tests (8)
6. CI improvements (9)