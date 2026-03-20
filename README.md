# Noosphere

> Expand the scope and scale of collective enlightenment.

**arXiv for all knowledge — built for agents.**

Noosphere lets anyone publish their knowledge — papers, blogs, newsletters, podcasts, docs, notes — as structured, agent-readable corpora that AI agents can discover, query, and cite. Like arXiv, but open to all knowledge (not just academic papers) and built for agents instead of human readers. Corpora are open by default; creators who choose to can set access to private, token-gated, or paid.

```
                    Agent-native
                        ↑
                        |
         Wolfram API    |    ← Noosphere
                        |
                        |
  ──────────────────────┼──────────────────── Anyone can publish
   Closed /             |
   platform-controlled  |
                        |    HuggingFace
  Google Scholar        |    arXiv
  Semantic Scholar      |    Wikipedia
                        |
         JSTOR          |
         Elsevier       |
                        ↓
                    Human-readable
```

Every existing knowledge platform — Google Scholar, arXiv, Wikipedia, JSTOR — was built for humans to read. Noosphere is built for the world where agents are the primary consumers of knowledge, expanding both the scope (knowledge too niche to find becomes accessible through agent queries) and the scale (millions of agents querying thousands of knowledge bases simultaneously) of collective enlightenment.

## Why

Two transformations drive Noosphere:

1. **Anyone can publish.** Not just academics or institutions. Any person, community, or organization can turn their knowledge into a structured, queryable corpus — as easily as uploading files or pointing at a URL.
2. **Agents are the primary audience.** Every corpus is designed to be discovered, queried, and cited by agents first. The primary interface for consumers is MCP and API, not a web browser.

Today, making your knowledge agent-friendly requires significant technical effort — structuring content, chunking, embedding, hosting an MCP server, setting up access control, handling payments. Noosphere standardizes and democratizes the entire pipeline.

## What it does

1. **Ingest** — Point Noosphere at a directory of Markdown files, a blog, an RSS feed, or a set of documents. It converts everything into a structured corpus.
2. **Index** — Documents are chunked, embedded, and indexed for semantic search.
3. **Serve** — The corpus is exposed via MCP (for Claude, Cursor, Codex) and REST API. Every query returns cited passages, not hallucinated summaries.
4. **Control** — Set access levels: public, private, token-gated, or paid.

## Quick start

```bash
git clone https://github.com/AcademiAI/noosphere.git
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

## CLI commands

```bash
# Initialize a corpus from a directory
noosphere init ./my-docs --name "My Blog" --author "Jane Doe"

# Ingest more documents into an existing corpus
noosphere ingest ./more-docs --corpus my-blog

# Re-index a corpus (re-chunk and re-embed)
noosphere index --corpus my-blog

# List all corpora
noosphere list

# Search a corpus
noosphere search --corpus my-blog "How does pricing work?"

# Start the server
noosphere serve --port 8420
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    COMMERCIAL LAYER (BSL)                │
│  Auth · Quota · Stripe (noosphere/cloud/)               │
├─────────────────────────────────────────────────────────┤
│                     OPEN CORE LAYER (MIT)                │
│  Ingestion · Chunking · Embedding · Retrieval           │
│  Citations · MCP server · REST API · Web UI · CLI       │
└─────────────────────────────────────────────────────────┘
```

- **Open core** (this repo): ingest, index, serve, query — everything needed to run a Noosphere node locally.
- **Commercial layer** (`noosphere/cloud/`, BSL): auth, usage quotas, and Stripe billing — activated by `ENABLE_CLOUD` env var.

## Connection to Feynman

Both Noosphere and [Feynman](https://github.com/steveyeow/feynman) are independent open-core products. Noosphere publishes knowledge as agent-readable corpora. Feynman is one consumer — it can use Noosphere corpora as source-grounded minds in its knowledge network.

Integration is optional: Feynman can import `noosphere` as a Python library (same-process) or connect via API (remote). Noosphere corpora can be consumed by any MCP/API-compatible agent or tool.

## Spec

See [SPEC.md](SPEC.md) for the full product specification, corpus format, API design, business model, and roadmap.

## License

MIT (open core). The `noosphere/cloud/` directory is licensed separately under BSL 1.1.
