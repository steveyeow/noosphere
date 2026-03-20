# Noosphere

> Expand the scope and scale of collective enlightenment.

**Turn any knowledge base into an agent-readable, permissioned, monetizable corpus.**

Noosphere is an open platform that lets anyone convert their personal or organizational knowledge — blogs, newsletters, podcasts, docs, notes — into a structured, agent-friendly format that AI agents can discover, query, and cite. Creators control access: free, private, or paid.

## Why

The trend is clear: more products are being built for agents. More knowledge needs to become machine-readable. But today, making your knowledge agent-friendly requires significant technical effort.

Lenny Rachitsky recently converted his 300+ podcast transcripts and newsletter posts into agent-friendly Markdown with an MCP server, and invited people to build on it. That was a manual effort by one creator. Noosphere standardizes this into a platform anyone can use.

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

# Serve it locally (MCP + REST API)
python -m noosphere.cli serve --port 8420
```

Then connect your MCP client (Claude, Cursor, etc.) to `http://localhost:8420/mcp`.

## Example: Lenny's dataset

```bash
# Clone the free starter dataset
git clone https://github.com/LennysNewsletter/lennys-newsletterpodcastdata.git

# Convert it into a Noosphere corpus
python -m noosphere.cli init ./lennys-newsletterpodcastdata \
  --name "Lenny's Newsletter & Podcast (Starter)" \
  --author "Lenny Rachitsky"

# Serve it
python -m noosphere.cli serve --port 8420
```

Now any MCP-compatible agent can query Lenny's archive with source citations.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    COMMERCIAL LAYER                      │
│  Managed hosting · Payments · Analytics · Discovery     │
├─────────────────────────────────────────────────────────┤
│                     OPEN CORE LAYER                      │
│  Ingestion · Chunking · Embedding · Retrieval           │
│  Citations · MCP server · REST API · CLI                │
└─────────────────────────────────────────────────────────┘
```

- **Open core** (this repo): ingest, index, serve, query — everything needed to run a Noosphere node locally.
- **Commercial layer** (coming soon): managed hosting, access control, payments, analytics, and a discovery marketplace.

## Connection to Feynman

Noosphere is the publishing layer. [Feynman](https://github.com/steveyeow/feynman) is one consumer: it can import Noosphere corpora as source-grounded minds in its knowledge network.

But Noosphere corpora can be consumed by any MCP/API-compatible agent or tool.

## Spec

See [SPEC.md](SPEC.md) for the full product specification, corpus format, API design, and roadmap.

## License

MIT
