# Noosphere — Agent Integration Guide

> How AI agents discover, evaluate, and query knowledge bases on the Noosphere network.

## Quick start

Noosphere exposes two interfaces: a **REST API** and an **MCP server** (Model Context Protocol). Both provide the same capabilities — use whichever fits your agent framework.

### MCP (recommended for AI agents)

Add to your MCP client config:

```json
{
  "mcpServers": {
    "noosphere": {
      "url": "http://localhost:8420/mcp"
    }
  }
}
```

Available tools: `search`, `preview`, `list_corpora`, `get_document`, `list_documents`, `get_stats`, `get_topics`, `get_manifest`.

### REST API

Base URL: `http://localhost:8420/api/v1`

## Agent workflow

### 1. Discover knowledge bases

```
MCP:  list_corpora
REST: GET /api/v1/corpora
```

Returns all available corpora with name, description, tags, document count, and status.

For network-wide discovery (across self-hosted nodes):

```
REST: GET /api/v1/network/search?q=crypto+trading
```

### 2. Evaluate relevance (preview)

Before committing to a full search or purchase, preview any knowledge base — including paid ones:

```
MCP:  preview(corpus_id="crypto-trading")
REST: GET /api/v1/corpora/{corpus_id}/preview
```

Returns:
- **Sample chunks** (up to 5, one per document, truncated)
- **Quality signals**: document_count, chunk_count, word_count, query_count, last_updated, status
- **Content types**: breakdown by document type (blog, note, concept, etc.)
- **Tags and description**

No authentication required for preview.

### 3. Search

```
MCP:  search(corpus_id="crypto-trading", query="derivatives pricing models", detail="medium")
REST: POST /api/v1/corpora/{corpus_id}/search
      {"query": "derivatives pricing models", "top_k": 5, "detail": "medium"}
```

**Detail levels** control search depth and cost:

| Level | Behavior | Use when |
|-------|----------|----------|
| `low` | Keyword-only, no expansion, fast | Quick lookups, known-item search |
| `medium` | Hybrid keyword+vector, expansion for large corpora | General queries (default) |
| `high` | Forced expansion + more results + full context | Deep research, comprehensive answers |

Results include text chunks with citations (document title, ID, type, date, char range) and freshness metadata. Compiled concept notes (distilled knowledge) receive a score boost.

### 4. Access control

- **Public corpora**: no auth needed
- **Private corpora**: require a bearer token from the corpus owner
- **Paid corpora**: require purchase or subscription via Stripe

Pass tokens via:
- MCP: Bearer token in transport auth
- REST: `Authorization: Bearer <token>` header

Agent identification (optional but recommended):
- REST: `X-Agent-Id: your-agent-name` header

## Quality signals

Every knowledge base carries objective metrics — no user ratings needed:

| Signal | What it tells you |
|--------|-------------------|
| `document_count` | Knowledge base size |
| `word_count` | Content depth |
| `last_updated` | Active maintenance |
| `query_count` | Popularity / usefulness |
| `status` | draft, published, archived |
| `access_level` | public, private, paid |

Use these to rank and filter when multiple knowledge bases match a query.

## Enrichment

Knowledge bases grow over time. The enrichment cycle polls RSS feeds, re-indexes new content, and runs health checks:

```
REST: POST /api/v1/corpora/{corpus_id}/enrich
```

Agents with write access can trigger enrichment to ensure they're searching the latest content.

## Common patterns

**Research agent**: `list_corpora` → filter by tags → `preview` top candidates → `search` with `detail="high"` on the best match.

**Monitoring agent**: periodically call `enrich` on subscribed corpora, then `search` for new developments.

**Multi-source agent**: `search` across multiple corpora, merge results by score, cite sources from different knowledge bases.
