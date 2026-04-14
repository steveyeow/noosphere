"""Registry server — FastAPI app for the Noosphere discovery network.

Endpoints:
  POST /api/v1/register     — node registers its corpora
  POST /api/v1/deregister   — node removes itself
  GET  /api/v1/search       — agents discover corpora by keyword
  GET  /api/v1/nodes        — list all registered nodes
  GET  /api/v1/corpora      — list all registered corpora
  GET  /api/v1/corpora/{id} — single corpus metadata
  GET  /api/v1/health       — registry health
  GET  /api/v1/stats        — network-wide statistics
  GET  /                    — browsable HTML directory
"""

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from noosphere import __version__
from noosphere.registry.db import get_registry_conn, close_registry

log = logging.getLogger(__name__)

# Will be set by CLI or caller before starting the server
_db_path: str = "registry.db"
_health_task = None


def set_db_path(path: str):
    global _db_path
    _db_path = path


# ── Models ──


class CorpusRegistration(BaseModel):
    corpus_id: str
    name: str
    slug: str = ""
    description: str = ""
    author: str = ""
    tags: list[str] = []
    document_count: int = 0
    chunk_count: int = 0
    word_count: int = 0
    access_level: str = "public"
    status: str = "draft"


class RegisterRequest(BaseModel):
    node_version: str = ""
    endpoint: str
    corpora: list[CorpusRegistration]


class DeregisterRequest(BaseModel):
    endpoint: str


# ── Lifespan ──


@asynccontextmanager
async def lifespan(app):
    get_registry_conn(_db_path)

    # Start background health checker
    from noosphere.registry.health import start_health_checker, stop_health_checker
    global _health_task
    _health_task = start_health_checker(_db_path)

    yield

    stop_health_checker()
    close_registry()


app = FastAPI(title="Noosphere Registry", version=__version__, lifespan=lifespan)


# ── Helpers ──


def _conn():
    return get_registry_conn(_db_path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rebuild_fts_for_node(conn, node_endpoint: str):
    """Rebuild FTS entries for all corpora belonging to a node."""
    # Delete old FTS entries for this node
    conn.execute("DELETE FROM registry_corpora_fts WHERE registry_id IN (SELECT id FROM registry_corpora WHERE node_endpoint=?)", (node_endpoint,))
    # Re-insert
    rows = conn.execute(
        "SELECT id, name, description, author, tags FROM registry_corpora WHERE node_endpoint=?",
        (node_endpoint,),
    ).fetchall()
    for row in rows:
        conn.execute(
            "INSERT INTO registry_corpora_fts(name, description, author, tags, registry_id) VALUES (?, ?, ?, ?, ?)",
            (row["name"], row["description"] or "", row["author"] or "", row["tags"] or "", row["id"]),
        )


# ── Registration ──


@app.post("/api/v1/register")
async def register_node(req: RegisterRequest):
    """Register or update a node and its corpora."""
    conn = _conn()
    now = _now()
    endpoint = req.endpoint.rstrip("/")

    if not endpoint:
        raise HTTPException(status_code=400, detail="endpoint is required")
    if not req.corpora:
        raise HTTPException(status_code=400, detail="at least one corpus is required")

    # Upsert node
    existing = conn.execute("SELECT endpoint FROM nodes WHERE endpoint=?", (endpoint,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE nodes SET node_version=?, last_seen_at=?, health_status='online', consecutive_failures=0 WHERE endpoint=?",
            (req.node_version, now, endpoint),
        )
    else:
        conn.execute(
            "INSERT INTO nodes (endpoint, node_version, first_seen_at, last_seen_at, health_status) VALUES (?, ?, ?, ?, 'online')",
            (endpoint, req.node_version, now, now),
        )

    # Upsert corpora
    registered = 0
    for c in req.corpora:
        # Use compound key: node_endpoint + corpus_id
        row_id = f"{endpoint}:{c.corpus_id}"
        tags_json = json.dumps(c.tags) if isinstance(c.tags, list) else c.tags

        existing_corpus = conn.execute(
            "SELECT id FROM registry_corpora WHERE node_endpoint=? AND corpus_id=?",
            (endpoint, c.corpus_id),
        ).fetchone()

        if existing_corpus:
            conn.execute(
                """UPDATE registry_corpora SET name=?, slug=?, description=?, author=?,
                   tags=?, document_count=?, chunk_count=?, word_count=?,
                   access_level=?, status=?, updated_at=?
                   WHERE node_endpoint=? AND corpus_id=?""",
                (c.name, c.slug, c.description, c.author, tags_json,
                 c.document_count, c.chunk_count, c.word_count,
                 c.access_level, c.status, now, endpoint, c.corpus_id),
            )
        else:
            conn.execute(
                """INSERT INTO registry_corpora
                   (id, node_endpoint, corpus_id, name, slug, description, author,
                    tags, document_count, chunk_count, word_count, access_level, status,
                    registered_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (row_id, endpoint, c.corpus_id, c.name, c.slug, c.description, c.author,
                 tags_json, c.document_count, c.chunk_count, c.word_count,
                 c.access_level, c.status, now, now),
            )
        registered += 1

    # Remove corpora from this node that are no longer in the registration
    registered_ids = {c.corpus_id for c in req.corpora}
    old_rows = conn.execute(
        "SELECT corpus_id FROM registry_corpora WHERE node_endpoint=?", (endpoint,)
    ).fetchall()
    for row in old_rows:
        if row["corpus_id"] not in registered_ids:
            conn.execute(
                "DELETE FROM registry_corpora WHERE node_endpoint=? AND corpus_id=?",
                (endpoint, row["corpus_id"]),
            )

    _rebuild_fts_for_node(conn, endpoint)
    conn.commit()

    log.info(f"Registered {registered} corpora from {endpoint}")
    return {"status": "ok", "registered": registered, "endpoint": endpoint}


@app.post("/api/v1/deregister")
async def deregister_node(req: DeregisterRequest):
    """Remove a node and all its corpora from the registry."""
    conn = _conn()
    endpoint = req.endpoint.rstrip("/")

    # Delete FTS entries first
    conn.execute(
        "DELETE FROM registry_corpora_fts WHERE registry_id IN (SELECT id FROM registry_corpora WHERE node_endpoint=?)",
        (endpoint,),
    )
    conn.execute("DELETE FROM registry_corpora WHERE node_endpoint=?", (endpoint,))
    conn.execute("DELETE FROM nodes WHERE endpoint=?", (endpoint,))
    conn.commit()

    log.info(f"Deregistered node {endpoint}")
    return {"status": "ok"}


# ── Search (agent discovery) ──


@app.get("/api/v1/search")
async def search_corpora(
    q: str = Query(..., description="Search query"),
    access_level: str = Query("", description="Filter by access level"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Search registered corpora by keyword. This is the primary agent discovery endpoint.

    Agents query this to find relevant knowledge bases across the entire Noosphere.
    """
    conn = _conn()

    # FTS5 search with fallback to LIKE for short/special queries
    if len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")

    # Try FTS first
    try:
        fts_query = " OR ".join(f'"{word}"' for word in q.strip().split() if word)
        sql = """
            SELECT rc.*, n.health_status,
                   fts.rank as relevance
            FROM registry_corpora_fts fts
            JOIN registry_corpora rc ON rc.id = fts.registry_id
            JOIN nodes n ON n.endpoint = rc.node_endpoint
            WHERE registry_corpora_fts MATCH ?
        """
        params: list = [fts_query]

        if access_level:
            sql += " AND rc.access_level = ?"
            params.append(access_level)

        # Only show corpora from healthy nodes
        sql += " AND n.health_status != 'offline'"
        sql += " ORDER BY fts.rank LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(sql, params).fetchall()
    except Exception:
        # Fallback: LIKE search across name + description
        pattern = f"%{q.strip()}%"
        sql = """
            SELECT rc.*, n.health_status
            FROM registry_corpora rc
            JOIN nodes n ON n.endpoint = rc.node_endpoint
            WHERE (rc.name LIKE ? OR rc.description LIKE ? OR rc.author LIKE ? OR rc.tags LIKE ?)
              AND n.health_status != 'offline'
        """
        params = [pattern, pattern, pattern, pattern]
        if access_level:
            sql += " AND rc.access_level = ?"
            params.append(access_level)
        sql += " ORDER BY rc.document_count DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()

    results = []
    for row in rows:
        r = dict(row)
        # Parse tags back to list
        if isinstance(r.get("tags"), str):
            try:
                r["tags"] = json.loads(r["tags"])
            except Exception:
                r["tags"] = []
        # Add the API endpoint so agents know where to connect
        r["api_endpoint"] = f"{r['node_endpoint']}/api/v1/corpora/{r['corpus_id']}"
        r["mcp_endpoint"] = f"{r['node_endpoint']}/mcp"
        r.pop("relevance", None)
        results.append(r)

    # Get total count
    count_sql = """
        SELECT COUNT(*) as total FROM registry_corpora rc
        JOIN nodes n ON n.endpoint = rc.node_endpoint
        WHERE n.health_status != 'offline'
    """
    total = conn.execute(count_sql).fetchone()["total"]

    return {
        "query": q,
        "results": results,
        "count": len(results),
        "total_corpora": total,
        "limit": limit,
        "offset": offset,
    }


# ── Directory (browsable) ──


@app.get("/api/v1/nodes")
async def list_nodes():
    """List all registered nodes."""
    conn = _conn()
    rows = conn.execute(
        """SELECT n.*, COUNT(rc.id) as corpus_count,
                  SUM(rc.document_count) as total_documents,
                  SUM(rc.word_count) as total_words
           FROM nodes n
           LEFT JOIN registry_corpora rc ON rc.node_endpoint = n.endpoint
           GROUP BY n.endpoint
           ORDER BY n.last_seen_at DESC"""
    ).fetchall()
    return {"nodes": [dict(r) for r in rows], "count": len(rows)}


@app.get("/api/v1/corpora")
async def list_all_corpora(
    access_level: str = Query("", description="Filter by access level"),
    status: str = Query("", description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List all registered corpora across the network."""
    conn = _conn()
    sql = """
        SELECT rc.*, n.health_status
        FROM registry_corpora rc
        JOIN nodes n ON n.endpoint = rc.node_endpoint
        WHERE 1=1
    """
    params: list = []

    if access_level:
        sql += " AND rc.access_level = ?"
        params.append(access_level)
    if status:
        sql += " AND rc.status = ?"
        params.append(status)

    sql += " ORDER BY rc.updated_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(sql, params).fetchall()
    results = []
    for row in rows:
        r = dict(row)
        if isinstance(r.get("tags"), str):
            try:
                r["tags"] = json.loads(r["tags"])
            except Exception:
                r["tags"] = []
        r["api_endpoint"] = f"{r['node_endpoint']}/api/v1/corpora/{r['corpus_id']}"
        r["mcp_endpoint"] = f"{r['node_endpoint']}/mcp"
        results.append(r)

    total = conn.execute("SELECT COUNT(*) as n FROM registry_corpora").fetchone()["n"]
    return {"corpora": results, "count": len(results), "total": total}


@app.get("/api/v1/corpora/{corpus_id}")
async def get_corpus_detail(corpus_id: str):
    """Get details for a specific registered corpus."""
    conn = _conn()
    row = conn.execute(
        """SELECT rc.*, n.health_status
           FROM registry_corpora rc
           JOIN nodes n ON n.endpoint = rc.node_endpoint
           WHERE rc.id = ? OR rc.corpus_id = ?""",
        (corpus_id, corpus_id),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Corpus not found in registry")
    r = dict(row)
    if isinstance(r.get("tags"), str):
        try:
            r["tags"] = json.loads(r["tags"])
        except Exception:
            r["tags"] = []
    r["api_endpoint"] = f"{r['node_endpoint']}/api/v1/corpora/{r['corpus_id']}"
    r["mcp_endpoint"] = f"{r['node_endpoint']}/mcp"
    return r


# ── Stats ──


@app.get("/api/v1/stats")
async def network_stats():
    """Network-wide statistics."""
    conn = _conn()
    nodes_total = conn.execute("SELECT COUNT(*) as n FROM nodes").fetchone()["n"]
    nodes_online = conn.execute("SELECT COUNT(*) as n FROM nodes WHERE health_status='online'").fetchone()["n"]
    corpora_total = conn.execute("SELECT COUNT(*) as n FROM registry_corpora").fetchone()["n"]
    total_docs = conn.execute("SELECT COALESCE(SUM(document_count), 0) as n FROM registry_corpora").fetchone()["n"]
    total_words = conn.execute("SELECT COALESCE(SUM(word_count), 0) as n FROM registry_corpora").fetchone()["n"]
    total_chunks = conn.execute("SELECT COALESCE(SUM(chunk_count), 0) as n FROM registry_corpora").fetchone()["n"]

    access_counts = conn.execute(
        "SELECT access_level, COUNT(*) as n FROM registry_corpora GROUP BY access_level"
    ).fetchall()

    return {
        "nodes_total": nodes_total,
        "nodes_online": nodes_online,
        "corpora_total": corpora_total,
        "total_documents": total_docs,
        "total_words": total_words,
        "total_chunks": total_chunks,
        "access_levels": {row["access_level"]: row["n"] for row in access_counts},
        "version": __version__,
    }


# ── Health ──


@app.get("/api/v1/health")
async def registry_health():
    """Registry server health check."""
    conn = _conn()
    nodes = conn.execute("SELECT COUNT(*) as n FROM nodes").fetchone()["n"]
    corpora = conn.execute("SELECT COUNT(*) as n FROM registry_corpora").fetchone()["n"]
    return {
        "status": "ok",
        "version": __version__,
        "nodes": nodes,
        "corpora": corpora,
    }


# ── Browsable HTML directory ──


@app.get("/", response_class=HTMLResponse)
async def browsable_directory():
    """Serve a browsable HTML directory of all registered knowledge bases."""
    conn = _conn()

    nodes_count = conn.execute("SELECT COUNT(*) as n FROM nodes").fetchone()["n"]
    corpora_rows = conn.execute(
        """SELECT rc.*, n.health_status
           FROM registry_corpora rc
           JOIN nodes n ON n.endpoint = rc.node_endpoint
           ORDER BY rc.updated_at DESC
           LIMIT 200"""
    ).fetchall()

    stats = conn.execute(
        "SELECT COALESCE(SUM(document_count),0) as docs, COALESCE(SUM(word_count),0) as words FROM registry_corpora"
    ).fetchone()

    corpus_cards = ""
    for row in corpora_rows:
        r = dict(row)
        tags_str = r.get("tags", "[]")
        if isinstance(tags_str, str):
            try:
                tags = json.loads(tags_str)
            except Exception:
                tags = []
        else:
            tags = tags_str

        tags_html = "".join(f'<span class="tag">{t}</span>' for t in tags[:5])
        health_dot = "green" if r.get("health_status") == "online" else "gray"
        access_badge = r.get("access_level", "public")

        corpus_cards += f"""
        <div class="corpus-card">
            <div class="card-header">
                <span class="health-dot" style="background:{health_dot}"></span>
                <h3>{_esc(r['name'])}</h3>
                <span class="badge badge-{access_badge}">{access_badge}</span>
            </div>
            <p class="description">{_esc(r.get('description') or 'No description')}</p>
            <div class="meta">
                <span>by {_esc(r.get('author') or 'Anonymous')}</span>
                <span>{r.get('document_count', 0)} docs</span>
                <span>{r.get('word_count', 0):,} words</span>
            </div>
            <div class="tags">{tags_html}</div>
            <div class="endpoints">
                <code>API: {_esc(r['node_endpoint'])}/api/v1/corpora/{_esc(r['corpus_id'])}</code>
                <code>MCP: {_esc(r['node_endpoint'])}/mcp</code>
            </div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Noosphere Registry</title>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
               background:#0a0a0a; color:#e0e0e0; }}
        .header {{ padding:2rem; text-align:center; border-bottom:1px solid #222; }}
        .header h1 {{ font-size:1.8rem; color:#fff; margin-bottom:0.5rem; }}
        .header p {{ color:#888; font-size:0.95rem; }}
        .stats {{ display:flex; gap:2rem; justify-content:center; margin-top:1rem; }}
        .stat {{ text-align:center; }}
        .stat .num {{ font-size:1.5rem; color:#4ade80; font-weight:700; }}
        .stat .label {{ font-size:0.75rem; color:#666; text-transform:uppercase; }}
        .search-bar {{ max-width:600px; margin:1.5rem auto; padding:0 1rem; }}
        .search-bar input {{ width:100%; padding:0.75rem 1rem; background:#111; border:1px solid #333;
                             border-radius:8px; color:#fff; font-size:1rem; outline:none; }}
        .search-bar input:focus {{ border-color:#4ade80; }}
        .grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(400px, 1fr));
                 gap:1rem; padding:1.5rem; max-width:1200px; margin:0 auto; }}
        .corpus-card {{ background:#111; border:1px solid #222; border-radius:10px; padding:1.25rem;
                        transition:border-color 0.2s; }}
        .corpus-card:hover {{ border-color:#4ade80; }}
        .card-header {{ display:flex; align-items:center; gap:0.5rem; margin-bottom:0.5rem; }}
        .card-header h3 {{ font-size:1rem; color:#fff; flex:1; }}
        .health-dot {{ width:8px; height:8px; border-radius:50%; flex-shrink:0; }}
        .badge {{ font-size:0.65rem; padding:2px 6px; border-radius:4px; text-transform:uppercase;
                  font-weight:600; }}
        .badge-public {{ background:#1a3a1a; color:#4ade80; }}
        .badge-token {{ background:#3a2a1a; color:#fbbf24; }}
        .badge-paid {{ background:#1a2a3a; color:#60a5fa; }}
        .badge-private {{ background:#2a1a1a; color:#f87171; }}
        .description {{ color:#999; font-size:0.85rem; margin-bottom:0.5rem;
                        overflow:hidden; text-overflow:ellipsis;
                        display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }}
        .meta {{ display:flex; gap:1rem; font-size:0.75rem; color:#666; margin-bottom:0.5rem; }}
        .tags {{ display:flex; gap:0.3rem; flex-wrap:wrap; margin-bottom:0.75rem; }}
        .tag {{ font-size:0.65rem; background:#1a1a2e; color:#818cf8; padding:2px 6px; border-radius:3px; }}
        .endpoints {{ font-size:0.7rem; }}
        .endpoints code {{ display:block; color:#666; margin:2px 0; word-break:break-all; }}
        .empty {{ text-align:center; padding:4rem 2rem; color:#555; }}
        .api-link {{ text-align:center; padding:1rem; color:#555; font-size:0.8rem; }}
        .api-link a {{ color:#4ade80; text-decoration:none; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Noosphere Registry</h1>
        <p>The knowledge network for the agent era</p>
        <div class="stats">
            <div class="stat"><div class="num">{nodes_count}</div><div class="label">Nodes</div></div>
            <div class="stat"><div class="num">{len(corpora_rows)}</div><div class="label">Knowledge Bases</div></div>
            <div class="stat"><div class="num">{stats['docs']:,}</div><div class="label">Documents</div></div>
            <div class="stat"><div class="num">{stats['words']:,}</div><div class="label">Words</div></div>
        </div>
    </div>
    <div class="search-bar">
        <input type="text" id="search" placeholder="Search the Noosphere..." onkeydown="if(event.key==='Enter')doSearch()">
    </div>
    <div class="grid" id="results">
        {corpus_cards if corpus_cards else '<div class="empty">No knowledge bases registered yet. Start a Noosphere node and it will appear here.</div>'}
    </div>
    <div class="api-link">
        Agent API: <a href="/api/v1/search?q=example">/api/v1/search?q=...</a> |
        <a href="/api/v1/corpora">/api/v1/corpora</a> |
        <a href="/api/v1/nodes">/api/v1/nodes</a> |
        <a href="/api/v1/stats">/api/v1/stats</a>
    </div>
    <script>
    async function doSearch() {{
        const q = document.getElementById('search').value.trim();
        if (!q) return;
        try {{
            const resp = await fetch('/api/v1/search?q=' + encodeURIComponent(q));
            const data = await resp.json();
            const grid = document.getElementById('results');
            if (!data.results || data.results.length === 0) {{
                grid.innerHTML = '<div class="empty">No results for "' + q + '"</div>';
                return;
            }}
            grid.innerHTML = data.results.map(r => {{
                const tags = (r.tags || []).slice(0, 5).map(t => '<span class="tag">' + t + '</span>').join('');
                const health = r.health_status === 'online' ? 'green' : 'gray';
                const al = r.access_level || 'public';
                return '<div class="corpus-card">' +
                    '<div class="card-header"><span class="health-dot" style="background:' + health + '"></span>' +
                    '<h3>' + (r.name||'') + '</h3><span class="badge badge-' + al + '">' + al + '</span></div>' +
                    '<p class="description">' + (r.description||'') + '</p>' +
                    '<div class="meta"><span>by ' + (r.author||'Anonymous') + '</span>' +
                    '<span>' + (r.document_count||0) + ' docs</span>' +
                    '<span>' + (r.word_count||0).toLocaleString() + ' words</span></div>' +
                    '<div class="tags">' + tags + '</div>' +
                    '<div class="endpoints"><code>API: ' + (r.api_endpoint||'') + '</code>' +
                    '<code>MCP: ' + (r.mcp_endpoint||'') + '</code></div></div>';
            }}).join('');
        }} catch(e) {{ console.error(e); }}
    }}
    </script>
</body>
</html>"""

    return HTMLResponse(content=html)


def _esc(s: str) -> str:
    """Basic HTML escaping."""
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
