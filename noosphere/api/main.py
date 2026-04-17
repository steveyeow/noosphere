"""FastAPI application — REST API + static frontend."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from noosphere import __version__
from noosphere.api.routes import router as api_router
from noosphere.mcp.routes import router as mcp_router
from noosphere.core.db import get_conn, close as db_close

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

_scheduler_task = None


async def _enrichment_loop():
    """Background loop: run enrichment + health check on all corpora periodically."""
    from noosphere.core.config import ENRICHMENT_INTERVAL_MINUTES
    if not ENRICHMENT_INTERVAL_MINUTES:
        return
    interval = ENRICHMENT_INTERVAL_MINUTES * 60
    await asyncio.sleep(30)  # wait for startup to settle
    while True:
        try:
            from noosphere.core.corpus import list_corpora
            from noosphere.core.knowledge_growth import (
                ingest_rss_feed, run_corpus_maintain,
                enrich_extract_backfill, enrich_auto_compile,
            )
            import json as _json
            conn = get_conn()
            for c in list_corpora():
                # Phase 1: RSS Polling
                feed_rows = conn.execute(
                    "SELECT DISTINCT json_extract(metadata_json, '$.source_feed') as feed "
                    "FROM documents WHERE corpus_id=? AND json_extract(metadata_json, '$.source_feed') IS NOT NULL",
                    (c["id"],),
                ).fetchall()
                feeds = [r["feed"] for r in feed_rows if r["feed"]]
                ingested = 0
                for url in feeds:
                    try:
                        result = ingest_rss_feed(c["id"], url, max_items=25)
                        ingested += result.get("ingested", 0)
                    except Exception:
                        pass
                if ingested > 0:
                    try:
                        run_corpus_maintain(c["id"], force_reindex=False)
                    except Exception:
                        pass

                # Phase 2 & 3: LLM-based enrichment (entity extraction + auto-compile)
                # Skipped in cloud mode — users trigger manually via "Enrich Now" within their quota.
                # Self-hosted: runs only if an LLM API key is configured.
                from noosphere.core.config import ENABLE_CLOUD, GEMINI_API_KEY, OPENAI_API_KEY
                if not ENABLE_CLOUD and (GEMINI_API_KEY or OPENAI_API_KEY):
                    try:
                        result = enrich_extract_backfill(c["id"], limit=10)
                        if result.get("extracted", 0) > 0:
                            logger.info("Background enrich: extracted entities for %d docs in corpus %s", result["extracted"], c["id"])
                    except Exception:
                        pass
                    try:
                        result = enrich_auto_compile(c["id"], limit=2)
                        compiled = result.get("compiled", [])
                        if compiled:
                            logger.info("Background enrich: compiled %d concept notes in corpus %s", len(compiled), c["id"])
                    except Exception:
                        pass

            logger.info("Enrichment cycle complete")
        except Exception:
            logger.warning("Enrichment cycle error", exc_info=True)
        await asyncio.sleep(interval)


async def _health_check_loop():
    """Background loop: ping registered nodes for health status."""
    await asyncio.sleep(60)
    while True:
        try:
            import httpx
            conn = get_conn()
            nodes = conn.execute("SELECT endpoint FROM registered_nodes").fetchall()
            for node in nodes:
                ep = node["endpoint"]
                try:
                    resp = httpx.get(f"{ep}/.well-known/noosphere.json", timeout=10)
                    status = "online" if resp.status_code == 200 else "degraded"
                except Exception:
                    status = "offline"
                conn.execute(
                    "UPDATE registered_nodes SET health_status=?, last_health_check=datetime('now') WHERE endpoint=?",
                    (status, ep),
                )
            conn.commit()
        except Exception:
            logger.warning("Health check error", exc_info=True)
        await asyncio.sleep(300)  # every 5 minutes


@asynccontextmanager
async def lifespan(app):
    global _scheduler_task
    get_conn()
    # Register post-ingest hooks (entity extraction on new documents)
    try:
        from noosphere.core.knowledge_growth import register_entity_extraction_hook
        register_entity_extraction_hook()
    except Exception:
        logger.warning("Failed to register entity extraction hook", exc_info=True)
    _scheduler_task = asyncio.gather(
        asyncio.create_task(_enrichment_loop()),
        asyncio.create_task(_health_check_loop()),
        return_exceptions=True,
    )
    yield
    _scheduler_task.cancel() if _scheduler_task else None
    db_close()


app = FastAPI(title="Noosphere", version=__version__, lifespan=lifespan)

# CORS — allow agents and external clients to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
app.include_router(mcp_router)

if os.getenv("ENABLE_CLOUD", "").lower() in ("1", "true", "yes"):
    try:
        from noosphere.cloud.auth import auth_middleware
        from noosphere.cloud.quota import quota_middleware
        from noosphere.cloud.stripe_connect import router as cloud_router

        app.middleware("http")(auth_middleware)
        app.middleware("http")(quota_middleware)
        app.include_router(cloud_router)

        @app.get("/static/supabase-config.json")
        async def supabase_config():
            """Serve Supabase client config for the frontend auth UI."""
            url = os.getenv("SUPABASE_URL", "").strip()
            anon_key = os.getenv("SUPABASE_ANON_KEY", "").strip()
            return JSONResponse({"url": url, "anonKey": anon_key})
    except ImportError:
        pass


@app.get("/.well-known/noosphere.json")
async def well_known_manifest():
    """Discovery manifest — allows agents to discover this node's corpora."""
    from noosphere.core.corpus import list_corpora

    corpora = list_corpora()
    return JSONResponse(content={
        "schema_version": "1.0",
        "node_version": __version__,
        "corpus_count": len(corpora),
        "corpora": [
            {
                "id": c["id"],
                "name": c["name"],
                "slug": c.get("slug", ""),
                "description": c.get("description", ""),
                "author": c.get("author_name", ""),
                "tags": c.get("tags", []),
                "document_count": c.get("document_count", 0),
                "chunk_count": c.get("chunk_count", 0),
                "word_count": c.get("word_count", 0),
                "access_level": c.get("access_level", "public"),
                "status": c.get("status", "draft"),
            }
            for c in corpora
        ],
    })


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(str(STATIC_DIR / "index.html"))

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        if path.startswith("api/") or path.startswith(".well-known/") or path.startswith("mcp"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        file_path = STATIC_DIR / path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(STATIC_DIR / "index.html"))
