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
from noosphere.api.llmstxt_router import router as llmstxt_router
from noosphere.api.og_router import router as og_router
from noosphere.mcp.routes import router as mcp_router
from noosphere.core.access import PaymentRequired
from noosphere.core.db import get_conn, close as db_close

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

_scheduler_task = None


def _is_pro_user(owner_id: str) -> bool:
    """Cloud-mode helper: is this owner on the Pro tier?

    Self-hosted mode (no cloud DB) always returns True — self-hosted users get
    every feature regardless of tier. In cloud mode, returns False for users
    with no row, 'free' tier, or lookup failures.
    """
    if not os.getenv("ENABLE_CLOUD", "").lower() in ("1", "true", "yes"):
        return True
    if not owner_id:
        return False
    try:
        from noosphere.cloud.db import get_user
        user = get_user(owner_id)
        return bool(user) and user.get("tier") == "pro"
    except Exception:
        return False


async def _enrichment_loop():
    """Background loop: keep Pro users' knowledge alive.

    For each Pro-owned corpus: re-fetch RSS feeds → auto-embed new docs →
    recompile dirty concepts. This is the "Living knowledge" Pro benefit —
    without it, Pro is just "higher quotas" and the pricing promise of
    auto-evolving Wiki/Entity/Timeline is empty.

    Skips Free-owned corpora in cloud mode. Self-hosted runs everything
    (no tier concept).
    """
    from noosphere.core.config import ENRICHMENT_INTERVAL_MINUTES
    if not ENRICHMENT_INTERVAL_MINUTES:
        return
    interval = ENRICHMENT_INTERVAL_MINUTES * 60
    await asyncio.sleep(30)  # wait for startup to settle
    while True:
        try:
            from noosphere.core.corpus import list_corpora
            from noosphere.core.knowledge_growth import (
                ingest_rss_feed, run_corpus_maintain, recompile_dirty_concepts,
            )
            conn = get_conn()
            for c in list_corpora(include_private=True):
                if not _is_pro_user(c.get("owner_id", "")):
                    continue
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
                # Pro's headline value: auto-grow Wiki/Entity/Timeline.
                # Run every cycle even if no new ingest — concepts can be marked
                # dirty by other paths (manual edits, capture, etc.) and still
                # need recompile.
                try:
                    recompile_dirty_concepts(c["id"], force=False)
                except Exception as e:
                    logger.warning("auto-recompile failed for corpus %s: %s", c["id"], e)
            logger.info("Enrichment cycle complete")
        except Exception:
            logger.warning("Enrichment cycle error", exc_info=True)
        await asyncio.sleep(interval)


async def _health_check_loop():
    """Background loop: ping registered nodes for health status."""
    from datetime import datetime, timezone
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
                    "UPDATE registered_nodes SET health_status=?, last_health_at=? WHERE endpoint=?",
                    (status, datetime.now(timezone.utc).isoformat(), ep),
                )
            conn.commit()
        except Exception:
            logger.warning("Health check error", exc_info=True)
        await asyncio.sleep(300)  # every 5 minutes


async def _register_with_registry_on_startup():
    """Best-effort one-shot registration with the discovery registry.

    Runs on every startup path — `noosphere serve`, raw `uvicorn`, Docker,
    gunicorn, PaaS — so federation isn't tied to the CLI entrypoint. The
    CLI used to be the only place this fired, which silently broke any
    deployment that didn't go through it.

    Reads `APP_URL` at runtime (config.py captured it at import; lifespan
    needs the env in case the CLI mutated it just before uvicorn.run).
    Skipped quietly when:
      - APP_URL points at localhost (dev — wouldn't be reachable anyway)
      - NOOSPHERE_REGISTRY is empty / "none" (operator opted out)
      - This node IS the registry (NOOSPHERE_IS_REGISTRY)
      - last_registration_ok() is already True (CLI got there first)

    Runs the blocking POST in a worker thread so registry latency / 15s
    timeout doesn't delay HTTP listener readiness.
    """
    try:
        from noosphere.core.config import NOOSPHERE_REGISTRY, NOOSPHERE_IS_REGISTRY
        from noosphere.core.registry import (
            is_local_endpoint, last_registration_ok,
            register_with_registry, set_node_endpoint,
        )
    except Exception as e:
        logger.debug("registry imports unavailable: %s", e)
        return
    if NOOSPHERE_IS_REGISTRY or not NOOSPHERE_REGISTRY:
        return
    if last_registration_ok():
        return
    public_url = os.getenv("APP_URL", "").strip()
    if not public_url or is_local_endpoint(public_url):
        return
    try:
        set_node_endpoint(public_url)
        await asyncio.to_thread(register_with_registry, public_url)
    except Exception as e:
        logger.warning("Lifespan registry registration failed: %s", e)


@asynccontextmanager
async def lifespan(app):
    global _scheduler_task
    get_conn()
    _scheduler_task = asyncio.gather(
        asyncio.create_task(_enrichment_loop()),
        asyncio.create_task(_health_check_loop()),
        asyncio.create_task(_register_with_registry_on_startup()),
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


@app.exception_handler(PaymentRequired)
async def payment_required_handler(_request, exc: PaymentRequired):
    """x402-compliant 402 response for paid corpora hit without valid auth.

    The body lists facilitator-issued payment requirements (`accepts`) so
    agent payment clients can satisfy the challenge and retry with
    `X-PAYMENT: <proof>`. A `checkout_url` is included for human fallback
    via Stripe Checkout. Spec: https://x402.org
    """
    return JSONResponse(status_code=402, content=exc.body)

app.include_router(api_router, prefix="/api/v1")
app.include_router(mcp_router)
# llms.txt routes mount at root (e.g. /llms.txt, /c/{slug}/llms.txt) per the
# llmstxt.org convention. Must be registered before the SPA catch-all below.
app.include_router(llmstxt_router)
# OG card preview routes (/og-preview/...). Same hard requirement as llmstxt:
# the SPA catch-all at the bottom would otherwise swallow these paths.
app.include_router(og_router)

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
