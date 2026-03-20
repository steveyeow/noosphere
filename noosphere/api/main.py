"""FastAPI application — REST API + static frontend."""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from noosphere import __version__
from noosphere.api.routes import router as api_router
from noosphere.mcp.routes import router as mcp_router
from noosphere.core.db import get_conn

app = FastAPI(title="Noosphere", version=__version__)

app.include_router(api_router, prefix="/api/v1")
app.include_router(mcp_router)

if os.getenv("ENABLE_CLOUD", "").lower() in ("1", "true", "yes"):
    try:
        from noosphere.cloud.auth import auth_middleware
        from noosphere.cloud.quota import quota_middleware

        app.middleware("http")(auth_middleware)
        app.middleware("http")(quota_middleware)
    except ImportError:
        pass

STATIC_DIR = Path(__file__).parent / "static"


@app.on_event("startup")
def startup():
    get_conn()


@app.get("/.well-known/noosphere.json")
async def well_known_manifest():
    """Federated discovery manifest — allows other nodes and agents
    to discover this node's corpora without a central registry."""
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
        if path.startswith("api/") or path.startswith(".well-known/"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        file_path = STATIC_DIR / path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(STATIC_DIR / "index.html"))
