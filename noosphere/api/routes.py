"""REST API routes for corpus operations and network discovery."""

import json as _json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File, Form
from pydantic import BaseModel

from noosphere import __version__
from noosphere.core.corpus import list_corpora, list_user_corpora, get_corpus, get_corpus_by_slug, create_corpus, update_corpus, delete_corpus
from noosphere.core.ingest import get_documents, get_document, ingest_text, ingest_url, delete_document, update_document
from noosphere.core.retrieval import search_corpus
from noosphere.core.access import check_access, AccessDenied
from noosphere.core.db import get_conn, is_pg

# Cloud quota helpers — no-ops when ENABLE_CLOUD is off or user is not authenticated
def _check_quota(request: Request, action: str):
    if not _is_cloud():
        return
    try:
        from noosphere.cloud.quota import check_quota
        check_quota(request, action)
    except ImportError:
        pass

def _check_corpus_limit(request: Request):
    if not _is_cloud():
        return
    try:
        from noosphere.cloud.quota import check_corpus_limit
        check_corpus_limit(request)
    except ImportError:
        pass

def _check_document_limit(request: Request, corpus_id: str):
    if not _is_cloud():
        return
    try:
        from noosphere.cloud.quota import check_document_limit
        check_document_limit(request, corpus_id)
    except ImportError:
        pass

def _track_usage(request: Request, action: str, tokens_used: int = 0):
    if not _is_cloud():
        return
    try:
        from noosphere.cloud.quota import track_usage
        track_usage(request, action, tokens_used)
    except ImportError:
        pass

router = APIRouter()

_CLOUD_MODE = os.getenv("ENABLE_CLOUD", "").lower() in ("1", "true", "yes") if "os" in dir() else False

def _is_cloud() -> bool:
    from noosphere.core.config import ENABLE_CLOUD
    return ENABLE_CLOUD


def _get_user_id(request: Request) -> str | None:
    """Get the authenticated user_id from request state (cloud mode)."""
    return getattr(request.state, "user_id", None)


def _extract_bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def _is_owner_request(request: Request) -> bool:
    """Check if the request comes from the owner (local web UI or localhost).

    In self-hosted mode, the person running the server is the owner.
    Access control only restricts external agent/API consumers.
    Owner is identified by: connecting from localhost, or having a
    same-origin Referer, or not having an X-Agent-ID header while
    connecting from the local network.
    """
    if request.headers.get("x-agent-id"):
        return False

    client = request.client
    if client:
        host = client.host or ""
        if host in ("127.0.0.1", "::1", "localhost", "0.0.0.0", "testclient"):
            return True

    referer = request.headers.get("referer", "")
    if referer:
        base = str(request.base_url).rstrip("/")
        if referer.startswith(base):
            return True
        if "://localhost:" in referer or "://127.0.0.1:" in referer:
            return True

    origin = request.headers.get("origin", "")
    if origin and ("://localhost:" in origin or "://127.0.0.1:" in origin):
        return True

    return False


def _check_corpus_access(corpus: dict, request: Request) -> str | None:
    """Enforce access control. Returns token_id if token auth was used.

    Owner requests from the web UI bypass access control (self-hosted
    mode: the person running the server owns all corpora).
    """
    if _is_owner_request(request):
        return None
    try:
        return check_access(corpus, _extract_bearer(request))
    except AccessDenied as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


def _require_owner(request: Request, corpus: dict | None = None):
    """Require the request to come from the owner. Used for write/mutation endpoints.

    In cloud mode: checks that the authenticated user owns the corpus.
    In self-hosted mode: checks localhost/same-origin (original behavior).
    """
    if _is_cloud():
        user_id = _get_user_id(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        if corpus and corpus.get("owner_id") and corpus["owner_id"] != user_id:
            raise HTTPException(status_code=403, detail="You do not own this corpus")
        return
    if not _is_owner_request(request):
        raise HTTPException(status_code=403, detail="Write access restricted to corpus owner")


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    include_context: bool = True
    detail: str = "medium"  # low | medium | high


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    top_k: int = 5
    session_id: Optional[str] = None


class TerminalRequest(BaseModel):
    input: str
    context: dict = {}


class CreateCorpusRequest(BaseModel):
    name: str
    description: str = ""
    author_name: str = ""
    tags: list[str] = []
    access_level: str = "public"
    language: str = "en"


class UpdateCorpusRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    access_level: Optional[str] = None
    tags: Optional[list[str]] = None
    owned_handles: Optional[list[str]] = None


class UpdateDocumentRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


class IngestURLRequest(BaseModel):
    url: str
    doc_type: str = "blog"
    source_kind: Optional[str] = None


class IndexRequest(BaseModel):
    force: bool = False
    chunk_strategy: Optional[str] = None


class CaptureRequest(BaseModel):
    """Save chat output or notes back into the corpus (chat → knowledge base)."""

    content: str
    title: str = ""
    question: str = ""
    session_id: Optional[str] = None


class IngestFeedRequest(BaseModel):
    feed_url: str
    max_items: int = 25


class IngestUrlsRequest(BaseModel):
    urls: list[str]
    doc_type: str = "blog"
    source_kind: Optional[str] = None


class CompileRequest(BaseModel):
    topic: str
    top_k: int = 10


class RecompileRequest(BaseModel):
    """Force-recompile a living concept's compiled truth from its timeline sources."""
    force: bool = False


class RecompileDirtyRequest(BaseModel):
    """Batch recompile every concept in a corpus that is dirty (or all, with force)."""
    force: bool = False


class MaintainRequest(BaseModel):
    force: bool = False


class CreateTokenRequest(BaseModel):
    label: str = ""
    permissions: str = "read"
    expires_at: str | None = None


@router.post("/terminal")
async def api_terminal(req: TerminalRequest, request: Request):
    """Interactive terminal command handler."""
    _require_owner(request)
    from noosphere.core.terminal import handle_terminal_input
    return handle_terminal_input(req.input, req.context)


def _resolve_corpus(corpus_id: str) -> dict:
    corpus = get_corpus(corpus_id) or get_corpus_by_slug(corpus_id)
    if not corpus:
        raise HTTPException(status_code=404, detail="Corpus not found")
    return corpus


@router.get("/health")
async def api_health():
    corpora = list_corpora(include_private=True)
    conn = get_conn()
    try:
        remote_nodes = conn.execute("SELECT COUNT(*) as n FROM registered_nodes").fetchone()["n"]
        remote_corpora = conn.execute("SELECT COUNT(*) as n FROM registered_corpora").fetchone()["n"]
    except Exception:
        remote_nodes, remote_corpora = 0, 0
    return {
        "status": "ok",
        "version": __version__,
        "corpus_count": len(corpora),
        "network_nodes": remote_nodes,
        "network_corpora": remote_corpora,
    }


# ── Profile ──

@router.get("/me")
async def api_me(request: Request):
    if _is_cloud():
        user_id = _get_user_id(request)
        email = getattr(request.state, "email", "")
        tier = getattr(request.state, "tier", "free")
        name = email.split("@")[0].replace(".", " ").title() if email else "User"
        return {"name": name, "user_id": user_id, "email": email, "tier": tier, "cloud": True}
    from noosphere.core.config import OWNER_NAME
    return {"name": OWNER_NAME}


# ── Corpus CRUD ──

@router.get("/corpora")
async def api_list_corpora(request: Request):
    if _is_cloud():
        user_id = _get_user_id(request)
        if user_id:
            # Return user's own corpora + public corpora from others
            own = list_user_corpora(user_id)
            own_ids = {c["id"] for c in own}
            public = [c for c in list_corpora() if c["id"] not in own_ids]
            return own + public
        return list_corpora()
    return list_corpora(include_private=_is_owner_request(request))


@router.post("/corpora")
async def api_create_corpus(req: CreateCorpusRequest, request: Request):
    _require_owner(request)
    _check_corpus_limit(request)
    owner_id = _get_user_id(request) if _is_cloud() else ""
    corpus = create_corpus(
        req.name, description=req.description, author_name=req.author_name,
        tags=req.tags, access_level=req.access_level, language=req.language,
        owner_id=owner_id,
    )
    return corpus


@router.get("/corpora/network")
async def api_corpus_network(request: Request):
    corpora = list_corpora(include_private=_is_owner_request(request))
    nodes = []
    for c in corpora:
        tags = c.get("tags", [])
        if isinstance(tags, str):
            try:
                tags = _json.loads(tags)
            except Exception:
                tags = []
        tokens = []
        for t in tags:
            tokens.extend([x.strip().lower() for x in t.replace(",", " ").split() if x.strip()])
        name = c["name"]
        initials = "".join(w[0].upper() for w in name.split()[:2]) if name else "?"
        nodes.append({
            "id": c["id"], "name": name, "slug": c.get("slug", ""),
            "description": c.get("description", ""), "author": c.get("author_name", ""),
            "tags": tags, "tokens": tokens, "initials": initials,
            "document_count": c.get("document_count", 0),
            "chunk_count": c.get("chunk_count", 0),
            "word_count": c.get("word_count", 0),
            "status": c.get("status", "draft"),
            "access_level": c.get("access_level", "public"),
        })

    links = []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            shared = set(nodes[i]["tokens"]) & set(nodes[j]["tokens"])
            if shared:
                links.append({
                    "source": nodes[i]["id"], "target": nodes[j]["id"],
                    "strength": len(shared), "shared_tags": list(shared),
                })
    return {"nodes": nodes, "links": links}


@router.get("/corpora/{corpus_id}")
async def api_get_corpus(corpus_id: str, request: Request):
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    return corpus


def _corpus_source_kind_breakdown(corpus_id: str) -> dict[str, int]:
    """Count documents per source_kind for a corpus."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT source_kind, COUNT(*) as n FROM documents WHERE corpus_id=? GROUP BY source_kind",
        (corpus_id,),
    ).fetchall()
    return {r["source_kind"] or "user_original": r["n"] for r in rows}


def _require_originals_for_public_access(corpus_id: str, new_access_level: str) -> None:
    """Block publish / paid-access when the corpus has documents but zero originals.

    Empty corpora are allowed through (user may be configuring before ingest).
    Corpora with only external content are blocked — external callers would
    receive nothing since imported external material is filtered out.
    """
    if new_access_level not in ("public", "paid", "token"):
        return
    counts = _corpus_source_kind_breakdown(corpus_id)
    total = sum(counts.values())
    if total == 0:
        return
    originals = counts.get("user_original", 0) + counts.get("user_capture", 0)
    if originals == 0:
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot enable external access: this corpus contains only "
                "external material. External callers would receive an empty "
                "response since imported external content is filtered out. "
                "Add at least one user-originated document first."
            ),
        )


@router.get("/corpora/{corpus_id}/access-summary")
async def api_access_summary(corpus_id: str, request: Request):
    """Breakdown of documents by source_kind — used by publish/paid confirm flows.

    Returns counts per source_kind plus what each class will look like to
    different caller types (owner vs external).
    """
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    counts = _corpus_source_kind_breakdown(corpus["id"])
    total = sum(counts.values())
    originals = counts.get("user_original", 0) + counts.get("user_capture", 0)
    return {
        "total": total,
        "originals": originals,
        "by_source_kind": counts,
        "can_enable_external_access": originals > 0,
        "visibility": {
            "owner": total,
            "external": originals,
        },
    }


@router.patch("/corpora/{corpus_id}")
async def api_update_corpus(corpus_id: str, req: UpdateCorpusRequest, request: Request):
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    new_access_level = updates.get("access_level")
    if new_access_level and new_access_level != corpus.get("access_level"):
        _require_originals_for_public_access(corpus_id, new_access_level)
    result = update_corpus(corpus_id, **updates)
    return result


@router.delete("/corpora/{corpus_id}")
async def api_delete_corpus(corpus_id: str, request: Request):
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    delete_corpus(corpus_id)
    return {"status": "deleted"}


# ── Documents ──

@router.get("/corpora/{corpus_id}/documents")
async def api_list_documents(corpus_id: str, request: Request):
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    return get_documents(corpus["id"])


@router.get("/corpora/{corpus_id}/documents/{doc_id}")
async def api_get_document(corpus_id: str, doc_id: str, request: Request):
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.patch("/corpora/{corpus_id}/documents/{doc_id}")
async def api_update_document(corpus_id: str, doc_id: str, req: UpdateDocumentRequest, request: Request):
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = update_document(doc_id, **updates)
    if not result:
        raise HTTPException(status_code=404, detail="Document not found")
    return result


@router.delete("/corpora/{corpus_id}/documents/{doc_id}")
async def api_delete_document(corpus_id: str, doc_id: str, request: Request):
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    if not delete_document(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "deleted"}


# ── File upload ──

from noosphere.core.ingest import (
    _extract_pdf_text, _extract_docx_text, _extract_csv_text, _extract_json_text,
)


@router.post("/corpora/{corpus_id}/upload")
async def api_upload_files(
    corpus_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
    source_kind: str = Form("user_original"),
):
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_document_limit(request, corpus["id"])
    results = []
    for f in files:
        ext = (f.filename or "").rsplit(".", 1)[-1].lower()
        raw = await f.read()

        if ext == "pdf":
            body = _extract_pdf_text(raw)
            title = (f.filename or "Untitled").rsplit(".", 1)[0]
            metadata, doc_type = {}, "paper"
        elif ext == "docx":
            body = _extract_docx_text(raw)
            title = (f.filename or "Untitled").rsplit(".", 1)[0]
            metadata, doc_type = {}, "doc"
        elif ext == "csv":
            content = raw.decode("utf-8", errors="replace")
            body = _extract_csv_text(content)
            title = (f.filename or "Untitled").rsplit(".", 1)[0]
            metadata, doc_type = {}, "data"
        elif ext in ("json", "jsonl"):
            content = raw.decode("utf-8", errors="replace")
            if ext == "jsonl":
                import json as _j
                lines = [_j.loads(line) for line in content.strip().splitlines() if line.strip()]
                body = _extract_json_text(_json.dumps(lines))
            else:
                body = _extract_json_text(content)
            title = (f.filename or "Untitled").rsplit(".", 1)[0]
            metadata, doc_type = {}, "data"
        else:
            content = raw.decode("utf-8", errors="replace")
            if not content.strip():
                continue
            from noosphere.core.ingest import _extract_markdown_metadata, _extract_markdown_title
            metadata, body = _extract_markdown_metadata(content)
            title = metadata.get("title") or _extract_markdown_title(body) or (f.filename or "Untitled").rsplit(".", 1)[0]
            doc_type = "doc" if ext in ("md", "markdown", "html", "htm") else "note"

        if not body or not body.strip():
            continue

        tags_str = metadata.get("tags", "") if isinstance(metadata, dict) else ""
        tags = [t.strip() for t in tags_str.split(",")] if tags_str else []

        doc = ingest_text(
            corpus["id"], title=title, content=body, doc_type=doc_type,
            source_kind=source_kind,
            date=metadata.get("date", "") if isinstance(metadata, dict) else "",
            tags=tags, metadata=metadata if isinstance(metadata, dict) else {},
        )
        results.append(doc)

    return {"uploaded": len(results), "documents": results}


# ── URL ingestion ──

@router.post("/corpora/{corpus_id}/ingest-url")
async def api_ingest_url(corpus_id: str, req: IngestURLRequest, request: Request):
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_quota(request, "ingest_url")
    _check_document_limit(request, corpus["id"])
    try:
        doc = ingest_url(corpus["id"], req.url, doc_type=req.doc_type, source_kind=req.source_kind)
        return doc
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/corpora/{corpus_id}/ingest-urls")
async def api_ingest_urls_bulk(corpus_id: str, req: IngestUrlsRequest, request: Request):
    """Batch URL ingestion (lower friction than one request per page)."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    if len(req.urls) > 40:
        raise HTTPException(status_code=400, detail="Maximum 40 URLs per request")
    from noosphere.core.knowledge_growth import ingest_urls_bulk

    try:
        return ingest_urls_bulk(corpus["id"], req.urls, doc_type=req.doc_type, source_kind=req.source_kind)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/corpora/{corpus_id}/ingest-feed")
async def api_ingest_feed(corpus_id: str, req: IngestFeedRequest, request: Request):
    """Ingest new entries from an RSS or Atom feed."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_quota(request, "ingest_feed")
    from noosphere.core.knowledge_growth import ingest_rss_feed

    try:
        return ingest_rss_feed(corpus["id"], req.feed_url.strip(), max_items=req.max_items)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/corpora/{corpus_id}/capture")
async def api_capture(corpus_id: str, req: CaptureRequest, request: Request):
    """Persist text into the corpus (e.g. assistant reply from chat)."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.knowledge_growth import save_capture

    try:
        return save_capture(
            corpus["id"],
            content=req.content,
            title=req.title,
            question=req.question,
            session_id=req.session_id or "",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Entity extraction (Phase 0.5) ──


class ExtractEntitiesRequest(BaseModel):
    limit: int = 50


@router.get("/corpora/{corpus_id}/entities")
async def api_list_entities(corpus_id: str, request: Request, kind: Optional[str] = None):
    """List entities in the corpus, annotated with mention counts."""
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    from noosphere.core.entities import list_entities
    return {"entities": list_entities(corpus["id"], kind=kind)}


@router.post("/corpora/{corpus_id}/entities/{entity_id}/compile")
async def api_compile_entity(corpus_id: str, entity_id: str, request: Request):
    """LLM-compile a 'compiled truth' summary for an entity (one page per person/company)."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_quota(request, "compile")
    from noosphere.core.entities import compile_entity_note, get_entity
    ent = get_entity(entity_id)
    if not ent or ent.get("corpus_id") != corpus["id"]:
        raise HTTPException(status_code=404, detail="Entity not found")
    result = compile_entity_note(entity_id)
    if not result:
        raise HTTPException(
            status_code=400,
            detail="Compile failed — no related documents, or LLM unavailable.",
        )
    _track_usage(request, "compile")
    return result


@router.get("/corpora/{corpus_id}/entities/{entity_id}")
async def api_get_entity(corpus_id: str, entity_id: str, request: Request):
    """Entity detail page: the entity + three buckets of related documents.

    See entities.get_entity_with_related_docs for the bucket semantics.
    """
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    from noosphere.core.entities import get_entity_with_related_docs
    ent = get_entity_with_related_docs(entity_id)
    if not ent or ent.get("corpus_id") != corpus["id"]:
        raise HTTPException(status_code=404, detail="Entity not found")
    return ent


@router.post("/corpora/{corpus_id}/documents/{doc_id}/extract-entities")
async def api_extract_document_entities(corpus_id: str, doc_id: str, request: Request):
    """Run entity extraction on a single document."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_quota(request, "extract_entities")
    from noosphere.core.entities import enrich_document
    result = enrich_document(doc_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found")
    _track_usage(request, "extract_entities")
    return result


@router.post("/corpora/{corpus_id}/extract-entities")
async def api_extract_corpus_entities(
    corpus_id: str, req: ExtractEntitiesRequest, request: Request,
):
    """Batch entity extraction across unenriched documents.

    Separate from /enrich (which polls RSS feeds). This runs an LLM pass
    per doc to populate the entities table; call repeatedly until
    remaining == 0 on large corpora.
    """
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_quota(request, "extract_entities")
    from noosphere.core.entities import enrich_corpus
    result = enrich_corpus(corpus["id"], limit=max(1, min(req.limit, 200)))
    _track_usage(request, "extract_entities", tokens_used=result.get("enriched", 0))
    return result


@router.post("/corpora/{corpus_id}/compile")
async def api_compile_concept(corpus_id: str, req: CompileRequest, request: Request):
    """LLM-compile a concept note from retrieved passages (knowledge fusion)."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_quota(request, "compile")
    from noosphere.core.knowledge_growth import compile_concept_note

    try:
        result = compile_concept_note(corpus["id"], req.topic.strip(), top_k=req.top_k)
        _track_usage(request, "compile")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/corpora/{corpus_id}/documents/{doc_id}/recompile")
async def api_recompile_concept(
    corpus_id: str, doc_id: str, req: RecompileRequest, request: Request,
):
    """Regenerate a concept doc's compiled truth from its timeline sources.

    Snapshots the prior version to ``concept_versions`` so history is diff-able.
    Body ``{"force": true}`` bypasses the pending-changes threshold.
    """
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_quota(request, "compile")
    from noosphere.core.knowledge_growth import recompile_concept_if_dirty

    try:
        result = recompile_concept_if_dirty(doc_id, force=req.force)
        if result.get("status") == "recompiled":
            _track_usage(request, "compile")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/corpora/{corpus_id}/documents/{doc_id}/versions")
async def api_concept_versions(corpus_id: str, doc_id: str, request: Request):
    """List all snapshot versions of a concept doc (oldest first)."""
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    from noosphere.core.knowledge_growth import get_concept_versions

    return {"document_id": doc_id, "versions": get_concept_versions(doc_id)}


@router.post("/corpora/{corpus_id}/recompile-dirty")
async def api_recompile_dirty(
    corpus_id: str, req: RecompileDirtyRequest, request: Request,
):
    """Batch-recompile all dirty concept docs in this corpus."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_quota(request, "compile")
    from noosphere.core.knowledge_growth import recompile_dirty_concepts

    return recompile_dirty_concepts(corpus["id"], force=req.force)


@router.get("/corpora/{corpus_id}/knowledge-health")
async def api_knowledge_health(corpus_id: str, request: Request):
    """Corpus health / lint-style report (coverage, staleness, link hygiene)."""
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    from noosphere.core.knowledge_growth import corpus_knowledge_health

    try:
        return corpus_knowledge_health(corpus["id"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/corpora/{corpus_id}/maintain")
async def api_maintain_corpus(corpus_id: str, req: MaintainRequest, request: Request):
    """Re-index corpus to repair search index drift (lightweight maintain pass)."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.knowledge_growth import run_corpus_maintain

    try:
        return run_corpus_maintain(corpus["id"], force_reindex=req.force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/corpora/{corpus_id}/enrich")
async def api_enrich_corpus(corpus_id: str, request: Request):
    """Enrichment cycle: poll RSS feeds, re-index, and health check.

    Designed to be called periodically (cron, agent, or scheduler).
    Polls all known RSS feeds for new entries, re-indexes to pick up
    new content, and returns a health summary.
    """
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.knowledge_growth import (
        ingest_rss_feed, run_corpus_maintain, corpus_knowledge_health,
    )

    # 1. Discover feeds: find unique source_feed URLs from document metadata
    conn = get_conn()
    feed_rows = conn.execute(
        "SELECT DISTINCT json_extract(metadata_json, '$.source_feed') as feed "
        "FROM documents WHERE corpus_id=? AND json_extract(metadata_json, '$.source_feed') IS NOT NULL",
        (corpus["id"],),
    ).fetchall()
    feed_urls = [r["feed"] for r in feed_rows if r["feed"]]

    # 2. Poll each feed for new entries
    feed_results = []
    total_ingested = 0
    for url in feed_urls:
        try:
            result = ingest_rss_feed(corpus["id"], url, max_items=25)
            feed_results.append(result)
            total_ingested += result.get("ingested", 0)
        except Exception as e:
            feed_results.append({"feed_url": url, "error": str(e)})

    # 3. Re-index if new content was ingested
    index_result = {}
    if total_ingested > 0:
        try:
            index_result = run_corpus_maintain(corpus["id"], force_reindex=False)
        except Exception as e:
            index_result = {"error": str(e)}

    # 4. Health check
    try:
        health = corpus_knowledge_health(corpus["id"])
    except Exception as e:
        health = {"error": str(e)}

    return {
        "corpus_id": corpus["id"],
        "feeds_polled": len(feed_urls),
        "total_new_documents": total_ingested,
        "feed_results": feed_results,
        "index": index_result,
        "health": health,
    }


# ── Indexing ──

@router.post("/corpora/{corpus_id}/index")
async def api_index_corpus(corpus_id: str, request: Request, req: IndexRequest = None):
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.indexer import index_corpus
    kwargs = {}
    if req:
        if req.force:
            kwargs["force"] = True
        if req.chunk_strategy:
            kwargs["chunk_strategy"] = req.chunk_strategy
    try:
        result = index_corpus(corpus["id"], **kwargs)
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Search ──

@router.post("/corpora/{corpus_id}/search")
async def api_search(corpus_id: str, req: SearchRequest, request: Request):
    corpus = _resolve_corpus(corpus_id)
    token_id = _check_corpus_access(corpus, request)
    _check_quota(request, "search")
    agent_id = request.headers.get("x-agent-id", "")
    caller = "owner" if _is_owner_request(request) else "external"
    result = search_corpus(
        corpus["id"], req.query, top_k=req.top_k,
        include_context=req.include_context,
        detail=req.detail,
        agent_id=agent_id, token_id=token_id,
        caller=caller,
    )
    _track_usage(request, "search")
    return result


# ── Preview (discovery) ──

@router.get("/corpora/{corpus_id}/preview")
async def api_preview(corpus_id: str):
    """Preview a knowledge base — returns sample chunks and quality signals.

    Available without authentication, even for paid corpora. Designed for
    agents evaluating whether a knowledge base is relevant before committing
    to a full query or purchase.
    """
    corpus = _resolve_corpus(corpus_id)
    conn = get_conn()

    # Sample chunks: pick a few representative ones (newest, spread across documents)
    sample_chunks = conn.execute(
        """SELECT c.text, c.document_id, c.created_at,
                  d.title as document_title, d.doc_type
           FROM chunks c
           JOIN documents d ON d.id = c.document_id
           WHERE c.corpus_id=?
           ORDER BY c.created_at DESC
           LIMIT 20""",
        (corpus["id"],),
    ).fetchall()

    # Deduplicate by document — one chunk per document, max 5
    seen_docs = set()
    samples = []
    for row in sample_chunks:
        did = row["document_id"]
        if did in seen_docs:
            continue
        seen_docs.add(did)
        text = row["text"]
        # Truncate to ~200 chars for preview
        if len(text) > 250:
            text = text[:247] + "..."
        samples.append({
            "text": text,
            "document_title": row["document_title"],
            "document_type": row["doc_type"] or "",
        })
        if len(samples) >= 5:
            break

    # Quality signals
    query_count = conn.execute(
        "SELECT COUNT(*) as n FROM query_logs WHERE corpus_id=?",
        (corpus["id"],),
    ).fetchone()["n"]

    # Topic summary from tags + document types
    doc_types = conn.execute(
        "SELECT doc_type, COUNT(*) as cnt FROM documents WHERE corpus_id=? GROUP BY doc_type ORDER BY cnt DESC",
        (corpus["id"],),
    ).fetchall()

    tags = corpus.get("tags", [])
    if isinstance(tags, str):
        try:
            tags = _json.loads(tags)
        except Exception:
            tags = []

    return {
        "corpus_id": corpus["id"],
        "name": corpus["name"],
        "description": corpus.get("description", ""),
        "author": corpus.get("author_name", ""),
        "tags": tags,
        "access_level": corpus.get("access_level", "public"),
        "quality": {
            "document_count": corpus.get("document_count", 0),
            "chunk_count": corpus.get("chunk_count", 0),
            "word_count": corpus.get("word_count", 0),
            "query_count": query_count,
            "last_updated": corpus.get("updated_at", ""),
            "status": corpus.get("status", "draft"),
            "embedding_model": corpus.get("embedding_model", ""),
        },
        "content_types": [{"type": r["doc_type"] or "doc", "count": r["cnt"]} for r in doc_types],
        "samples": samples,
    }


# ── Stats & Topics ──

@router.get("/corpora/{corpus_id}/stats")
async def api_stats(corpus_id: str, request: Request):
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    return {
        "corpus_id": corpus["id"], "name": corpus["name"],
        "document_count": corpus["document_count"],
        "chunk_count": corpus["chunk_count"],
        "word_count": corpus["word_count"],
        "embedding_model": corpus.get("embedding_model", ""),
        "status": corpus["status"],
        "access_level": corpus["access_level"],
        "updated_at": corpus["updated_at"],
    }


@router.get("/corpora/{corpus_id}/topics")
async def api_topics(corpus_id: str, request: Request):
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    docs = get_documents(corpus["id"])
    topics = set()
    for src in [corpus.get("tags", [])]:
        if isinstance(src, str):
            try: src = _json.loads(src)
            except Exception: src = []
        for t in (src if isinstance(src, list) else []):
            topics.add(t.strip().lower())
    for doc in docs:
        dt = doc.get("tags", "[]")
        if isinstance(dt, str):
            try: dt = _json.loads(dt)
            except Exception: dt = []
        for t in (dt if isinstance(dt, list) else []):
            topics.add(t.strip().lower())
    return {"topics": sorted(topics)}


# ── Export ──

@router.get("/corpora/{corpus_id}/export")
async def api_export_corpus(corpus_id: str, request: Request):
    """Export a corpus as a ZIP file."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.export import export_corpus
    from fastapi.responses import StreamingResponse
    buf = export_corpus(corpus["id"])
    slug = corpus.get("slug", corpus_id)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{slug}.zip"'},
    )


# ── Access Tokens ──

@router.post("/corpora/{corpus_id}/tokens")
async def api_create_token(corpus_id: str, req: CreateTokenRequest, request: Request):
    """Create an access token for a corpus. Returns plaintext token (one-time)."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.tokens import create_token
    return create_token(corpus["id"], label=req.label, permissions=req.permissions, expires_at=req.expires_at)


@router.get("/corpora/{corpus_id}/tokens")
async def api_list_tokens(corpus_id: str, request: Request):
    """List all access tokens for a corpus (without hashes)."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.tokens import list_tokens
    return list_tokens(corpus["id"])


@router.delete("/corpora/{corpus_id}/tokens/{token_id}")
async def api_revoke_token(corpus_id: str, token_id: str, request: Request):
    """Revoke an access token."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.tokens import revoke_token
    if not revoke_token(token_id):
        raise HTTPException(status_code=404, detail="Token not found")
    return {"status": "revoked"}


# ── Query Logs / Analytics ──

@router.post("/search")
async def api_global_search(req: SearchRequest):
    """Search across ALL public corpora (local + registered remote nodes)."""
    corpora = list_corpora()
    ready = [c for c in corpora if c.get("status") == "ready" and c.get("access_level") == "public"]

    all_results = []
    for c in ready:
        try:
            # Cross-corpus search is always external w.r.t. each corpus.
            result = search_corpus(c["id"], req.query, top_k=req.top_k, include_context=req.include_context, caller="external")
            for r in result.get("results", []):
                r["corpus_id"] = c["id"]
                r["corpus_name"] = c["name"]
                r["source"] = "local"
                all_results.append(r)
        except Exception:
            logger.warning("Global search failed for corpus %s", c["id"], exc_info=True)
            continue

    remote_results = _search_registered_corpora(req.query, limit=req.top_k)
    all_results.extend(remote_results)

    all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {
        "results": all_results[: req.top_k],
        "corpora_searched": len(ready) + len(remote_results),
    }


def _compute_quality_score(corpus: dict) -> float:
    """Compute a quality ranking score from objective signals (0.0–1.0)."""
    import math
    score = 0.0
    # Document count: log scale, max ~0.3 at 500+ docs
    doc_count = corpus.get("document_count", 0)
    if isinstance(doc_count, dict):
        doc_count = doc_count.get("document_count", 0)
    q = corpus.get("quality", {})
    if isinstance(q, dict):
        doc_count = doc_count or q.get("document_count", 0)
    score += min(0.3, math.log1p(doc_count) / 20)
    # Word count: log scale, max ~0.2 at 100k+ words
    word_count = q.get("word_count", 0) if isinstance(q, dict) else corpus.get("word_count", 0)
    score += min(0.2, math.log1p(word_count) / 60)
    # Health: online nodes get a bonus
    health = q.get("health_status", "") if isinstance(q, dict) else corpus.get("health_status", "")
    if health == "online":
        score += 0.15
    elif health == "degraded":
        score += 0.05
    # Access level: public gets slight preference (more useful for discovery)
    if corpus.get("access_level") == "public":
        score += 0.1
    elif corpus.get("access_level") == "paid":
        score += 0.05
    # Base score so nothing is zero
    score += 0.1
    return round(min(1.0, score), 4)


def _search_registered_corpora(query: str, limit: int = 20) -> list[dict]:
    """Search registered remote corpora by metadata (FTS or LIKE fallback)."""
    conn = get_conn()
    try:
        if is_pg():
            rows = conn.execute(
                """SELECT rc.*, rn.health_status
                   FROM registered_corpora rc
                   JOIN registered_nodes rn ON rn.endpoint = rc.node_endpoint
                   WHERE rn.health_status != 'offline'
                     AND rc.tsv @@ plainto_tsquery('english', ?)
                   ORDER BY ts_rank(rc.tsv, plainto_tsquery('english', ?)) DESC
                   LIMIT ?""",
                (query, query, limit),
            ).fetchall()
        else:
            fts_query = " OR ".join(f'"{w}"' for w in query.strip().split() if w)
            try:
                rows = conn.execute(
                    """SELECT rc.*, rn.health_status
                       FROM registered_corpora_fts fts
                       JOIN registered_corpora rc ON rc.id = fts.registry_id
                       JOIN registered_nodes rn ON rn.endpoint = rc.node_endpoint
                       WHERE registered_corpora_fts MATCH ?
                         AND rn.health_status != 'offline'
                       ORDER BY fts.rank LIMIT ?""",
                    (fts_query, limit),
                ).fetchall()
            except Exception:
                pattern = f"%{query.strip()}%"
                rows = conn.execute(
                    """SELECT rc.*, rn.health_status
                       FROM registered_corpora rc
                       JOIN registered_nodes rn ON rn.endpoint = rc.node_endpoint
                       WHERE (rc.name LIKE ? OR rc.description LIKE ? OR rc.author LIKE ?)
                         AND rn.health_status != 'offline'
                       ORDER BY rc.document_count DESC LIMIT ?""",
                    (pattern, pattern, pattern, limit),
                ).fetchall()
    except Exception:
        return []

    results = []
    for row in rows:
        r = dict(row)
        tags = r.get("tags", "[]")
        if isinstance(tags, str):
            try:
                tags = _json.loads(tags)
            except Exception:
                tags = []
        results.append({
            "corpus_id": r["corpus_id"],
            "corpus_name": r["name"],
            "description": r.get("description", ""),
            "author": r.get("author", ""),
            "tags": tags,
            "quality": {
                "document_count": r.get("document_count", 0),
                "chunk_count": r.get("chunk_count", 0),
                "word_count": r.get("word_count", 0),
                "last_updated": r.get("updated_at", ""),
                "health_status": r.get("health_status", "unknown"),
            },
            "access_level": r.get("access_level", "public"),
            "api_endpoint": f"{r['node_endpoint']}/api/v1/corpora/{r['corpus_id']}",
            "mcp_endpoint": f"{r['node_endpoint']}/mcp",
            "preview_url": f"{r['node_endpoint']}/api/v1/corpora/{r['corpus_id']}/preview",
            "source": "remote",
            "score": _compute_quality_score(r),
        })
    return results


# ── Chat ──

@router.post("/chat")
async def api_global_chat(req: ChatRequest):
    """Chat across all public corpora in the Noosphere."""
    from noosphere.core.chat import chat_with_noosphere
    return chat_with_noosphere(req.message, history=req.history, top_k=req.top_k)


@router.post("/corpora/{corpus_id}/chat")
async def api_corpus_chat(corpus_id: str, req: ChatRequest, request: Request):
    """Chat with a specific corpus."""
    import uuid
    from datetime import datetime, timezone

    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    _check_quota(request, "chat")
    caller = "owner" if _is_owner_request(request) else "external"
    from noosphere.core.chat import chat_with_corpus
    result = chat_with_corpus(corpus["id"], req.message, history=req.history, top_k=req.top_k, caller=caller)

    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    session_id = req.session_id

    if not session_id:
        session_id = str(uuid.uuid4())
        title = req.message[:80]
        conn.execute(
            "INSERT INTO chat_sessions (id, corpus_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, corpus["id"], title, now, now),
        )
    else:
        conn.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (now, session_id))

    user_msg_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO chat_messages (id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_msg_id, session_id, "user", req.message, now),
    )

    asst_msg_id = str(uuid.uuid4())
    citations_json = _json.dumps(result.get("citations")) if result.get("citations") else None
    conn.execute(
        "INSERT INTO chat_messages (id, session_id, role, content, citations_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (asst_msg_id, session_id, "assistant", result.get("response", ""), citations_json, now),
    )
    conn.commit()

    _track_usage(request, "chat")
    result["session_id"] = session_id
    return result


@router.get("/chat-sessions")
async def api_list_chat_sessions(limit: int = 20):
    """List recent chat sessions across all corpora."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT s.id, s.corpus_id, s.title, s.created_at, s.updated_at,
                  c.name as corpus_name,
                  (SELECT COUNT(*) FROM chat_messages WHERE session_id=s.id) as message_count
           FROM chat_sessions s
           LEFT JOIN corpora c ON c.id = s.corpus_id
           ORDER BY s.updated_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/chat-sessions/{session_id}")
async def api_get_chat_session(session_id: str):
    """Get a chat session with all its messages."""
    conn = get_conn()
    session = conn.execute("SELECT * FROM chat_sessions WHERE id=?", (session_id,)).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    messages = conn.execute(
        "SELECT id, role, content, citations_json, created_at FROM chat_messages WHERE session_id=? ORDER BY created_at ASC",
        (session_id,),
    ).fetchall()
    result = dict(session)
    result["messages"] = []
    for m in messages:
        msg = dict(m)
        if msg.get("citations_json"):
            msg["citations"] = _json.loads(msg["citations_json"])
        msg.pop("citations_json", None)
        result["messages"].append(msg)
    return result


@router.delete("/chat-sessions/{session_id}")
async def api_delete_chat_session(session_id: str, request: Request):
    """Delete a chat session and all its messages."""
    _require_owner(request)
    conn = get_conn()
    conn.execute("DELETE FROM chat_messages WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))
    conn.commit()
    return {"ok": True}


@router.get("/corpora/{corpus_id}/analytics")
async def api_analytics(corpus_id: str, request: Request, limit: int = 50):
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM query_logs WHERE corpus_id=? ORDER BY created_at DESC LIMIT ?",
        (corpus["id"], limit),
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) as cnt FROM query_logs WHERE corpus_id=?",
        (corpus["id"],),
    ).fetchone()
    return {
        "total_queries": total["cnt"],
        "recent_queries": [dict(r) for r in rows],
    }


# ── Network Discovery (built-in registry) ──


class RegisterNodeRequest(BaseModel):
    node_version: str = ""
    endpoint: str
    corpora: list[dict]


class DeregisterNodeRequest(BaseModel):
    endpoint: str


def _rebuild_rc_fts(conn, node_endpoint: str):
    """Rebuild FTS entries for all registered corpora belonging to a node."""
    if is_pg():
        conn.execute(
            """UPDATE registered_corpora
               SET tsv = to_tsvector('english', coalesce(name,'') || ' ' || coalesce(description,'') || ' ' || coalesce(author,''))
               WHERE node_endpoint=?""",
            (node_endpoint,),
        )
    else:
        conn.execute(
            "DELETE FROM registered_corpora_fts WHERE registry_id IN "
            "(SELECT id FROM registered_corpora WHERE node_endpoint=?)",
            (node_endpoint,),
        )
        rows = conn.execute(
            "SELECT id, name, description, author, tags FROM registered_corpora WHERE node_endpoint=?",
            (node_endpoint,),
        ).fetchall()
        for row in rows:
            conn.execute(
                "INSERT INTO registered_corpora_fts(name, description, author, tags, registry_id) VALUES (?, ?, ?, ?, ?)",
                (row["name"], row["description"] or "", row["author"] or "", row["tags"] or "", row["id"]),
            )


@router.post("/register")
async def api_register_node(req: RegisterNodeRequest):
    """Register a self-hosted node and its corpora for network discovery."""
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    endpoint = req.endpoint.rstrip("/")

    if not endpoint:
        raise HTTPException(status_code=400, detail="endpoint is required")
    if not req.corpora:
        raise HTTPException(status_code=400, detail="at least one corpus is required")

    existing = conn.execute("SELECT endpoint FROM registered_nodes WHERE endpoint=?", (endpoint,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE registered_nodes SET node_version=?, last_seen_at=?, health_status='online', consecutive_failures=0 WHERE endpoint=?",
            (req.node_version, now, endpoint),
        )
    else:
        conn.execute(
            "INSERT INTO registered_nodes (endpoint, node_version, first_seen_at, last_seen_at, health_status) VALUES (?, ?, ?, ?, 'online')",
            (endpoint, req.node_version, now, now),
        )

    registered = 0
    for c in req.corpora:
        row_id = f"{endpoint}:{c.get('corpus_id', '')}"
        tags_json = _json.dumps(c.get("tags", [])) if isinstance(c.get("tags"), list) else c.get("tags", "[]")
        corpus_id = c.get("corpus_id", "")

        existing_corpus = conn.execute(
            "SELECT id FROM registered_corpora WHERE node_endpoint=? AND corpus_id=?",
            (endpoint, corpus_id),
        ).fetchone()

        if existing_corpus:
            conn.execute(
                """UPDATE registered_corpora SET name=?, slug=?, description=?, author=?,
                   tags=?, document_count=?, chunk_count=?, word_count=?,
                   access_level=?, status=?, updated_at=?
                   WHERE node_endpoint=? AND corpus_id=?""",
                (c.get("name", ""), c.get("slug", ""), c.get("description", ""), c.get("author", ""),
                 tags_json, c.get("document_count", 0), c.get("chunk_count", 0), c.get("word_count", 0),
                 c.get("access_level", "public"), c.get("status", "draft"), now, endpoint, corpus_id),
            )
        else:
            conn.execute(
                """INSERT INTO registered_corpora
                   (id, node_endpoint, corpus_id, name, slug, description, author,
                    tags, document_count, chunk_count, word_count, access_level, status,
                    registered_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (row_id, endpoint, corpus_id, c.get("name", ""), c.get("slug", ""),
                 c.get("description", ""), c.get("author", ""), tags_json,
                 c.get("document_count", 0), c.get("chunk_count", 0), c.get("word_count", 0),
                 c.get("access_level", "public"), c.get("status", "draft"), now, now),
            )
        registered += 1

    registered_ids = {c.get("corpus_id", "") for c in req.corpora}
    old_rows = conn.execute(
        "SELECT corpus_id FROM registered_corpora WHERE node_endpoint=?", (endpoint,)
    ).fetchall()
    for row in old_rows:
        if row["corpus_id"] not in registered_ids:
            if not is_pg():
                conn.execute(
                    "DELETE FROM registered_corpora_fts WHERE registry_id IN "
                    "(SELECT id FROM registered_corpora WHERE node_endpoint=? AND corpus_id=?)",
                    (endpoint, row["corpus_id"]),
                )
            conn.execute(
                "DELETE FROM registered_corpora WHERE node_endpoint=? AND corpus_id=?",
                (endpoint, row["corpus_id"]),
            )

    _rebuild_rc_fts(conn, endpoint)
    conn.commit()
    return {"status": "ok", "registered": registered, "endpoint": endpoint}


@router.post("/deregister")
async def api_deregister_node(req: DeregisterNodeRequest):
    """Remove a self-hosted node and all its corpora from the network."""
    conn = get_conn()
    endpoint = req.endpoint.rstrip("/")

    if not is_pg():
        conn.execute(
            "DELETE FROM registered_corpora_fts WHERE registry_id IN "
            "(SELECT id FROM registered_corpora WHERE node_endpoint=?)",
            (endpoint,),
        )
    conn.execute("DELETE FROM registered_corpora WHERE node_endpoint=?", (endpoint,))
    conn.execute("DELETE FROM registered_nodes WHERE endpoint=?", (endpoint,))
    conn.commit()
    return {"status": "ok"}


@router.get("/network/search")
async def api_network_search(
    q: str = Query(..., description="Search query"),
    access_level: str = Query("", description="Filter by access level"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Search the entire Noosphere network — local corpora + registered remote nodes."""
    if len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")

    results = _search_registered_corpora(q, limit=limit)

    local_corpora = list_corpora()
    for c in local_corpora:
        if c.get("access_level") == "private":
            continue
        name = c.get("name", "")
        desc = c.get("description", "")
        q_lower = q.lower()
        if q_lower in name.lower() or q_lower in desc.lower() or any(q_lower in t.lower() for t in (c.get("tags") or [])):
            tags = c.get("tags", [])
            if isinstance(tags, str):
                try:
                    tags = _json.loads(tags)
                except Exception:
                    tags = []
            results.append({
                "corpus_id": c["id"],
                "corpus_name": name,
                "description": desc,
                "author": c.get("author_name", ""),
                "tags": tags,
                "document_count": c.get("document_count", 0),
                "access_level": c.get("access_level", "public"),
                "source": "local",
                "score": 1.0,
            })

    # Compute quality scores for local results too
    for r in results:
        if r.get("source") == "local":
            r["score"] = _compute_quality_score(r)

    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {
        "query": q,
        "results": results[offset : offset + limit],
        "count": len(results[offset : offset + limit]),
        "total": len(results),
    }


@router.get("/network/nodes")
async def api_network_nodes():
    """List all registered self-hosted nodes."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT rn.*, COUNT(rc.id) as corpus_count,
                      COALESCE(SUM(rc.document_count), 0) as total_documents,
                      COALESCE(SUM(rc.word_count), 0) as total_words
               FROM registered_nodes rn
               LEFT JOIN registered_corpora rc ON rc.node_endpoint = rn.endpoint
               GROUP BY rn.endpoint
               ORDER BY rn.last_seen_at DESC"""
        ).fetchall()
    except Exception:
        rows = []
    return {"nodes": [dict(r) for r in rows], "count": len(rows)}


@router.get("/cron/health-check")
async def api_cron_health_check(request: Request):
    """Cron-compatible endpoint: ping all registered nodes and update health status.

    Replaces the old daemon thread. Call via Vercel Cron, external cron,
    or manually. Safe to call frequently — each check is a quick HTTP GET.
    """
    import httpx

    conn = get_conn()
    try:
        nodes = conn.execute("SELECT endpoint FROM registered_nodes").fetchall()
    except Exception:
        return {"status": "ok", "checked": 0}

    now = datetime.now(timezone.utc).isoformat()
    checked = 0
    for node in nodes:
        endpoint = node["endpoint"]
        try:
            resp = httpx.get(f"{endpoint}/api/v1/health", timeout=10, follow_redirects=True)
            if resp.status_code == 200:
                conn.execute(
                    "UPDATE registered_nodes SET health_status='online', last_health_at=?, consecutive_failures=0 WHERE endpoint=?",
                    (now, endpoint),
                )
                conn.commit()
                checked += 1
                continue
        except Exception:
            pass
        row = conn.execute("SELECT consecutive_failures FROM registered_nodes WHERE endpoint=?", (endpoint,)).fetchone()
        if not row:
            continue
        failures = (row["consecutive_failures"] or 0) + 1
        status = "offline" if failures >= 3 else "degraded"
        conn.execute(
            "UPDATE registered_nodes SET health_status=?, last_health_at=?, consecutive_failures=? WHERE endpoint=?",
            (status, now, failures, endpoint),
        )
        conn.commit()
        checked += 1

    return {"status": "ok", "checked": checked}


@router.get("/network/stats")
async def api_network_stats():
    """Network-wide statistics (local + remote)."""
    conn = get_conn()
    local_corpora = list_corpora()
    local_public = [c for c in local_corpora if c.get("access_level") != "private"]

    try:
        nodes_total = conn.execute("SELECT COUNT(*) as n FROM registered_nodes").fetchone()["n"]
        nodes_online = conn.execute("SELECT COUNT(*) as n FROM registered_nodes WHERE health_status='online'").fetchone()["n"]
        remote_corpora = conn.execute("SELECT COUNT(*) as n FROM registered_corpora").fetchone()["n"]
        remote_docs = conn.execute("SELECT COALESCE(SUM(document_count), 0) as n FROM registered_corpora").fetchone()["n"]
        remote_words = conn.execute("SELECT COALESCE(SUM(word_count), 0) as n FROM registered_corpora").fetchone()["n"]
    except Exception:
        nodes_total = nodes_online = remote_corpora = remote_docs = remote_words = 0

    local_docs = sum(c.get("document_count", 0) for c in local_public)
    local_words = sum(c.get("word_count", 0) for c in local_public)

    return {
        "nodes_total": nodes_total + 1,
        "nodes_online": nodes_online + 1,
        "corpora_total": len(local_public) + remote_corpora,
        "total_documents": local_docs + remote_docs,
        "total_words": local_words + remote_words,
        "local_corpora": len(local_public),
        "remote_corpora": remote_corpora,
        "version": __version__,
    }


# ── Payments (Stripe) ──


class CheckoutRequest(BaseModel):
    success_url: str = ""
    cancel_url: str = ""
    payer_email: str = ""
    agent_id: str = ""


class PricingRequest(BaseModel):
    """Set pricing for a paid corpus."""
    type: str = "per_query"  # "per_query" or "subscription"
    amount_cents: int = 500
    currency: str = "usd"
    queries_per_payment: int = 100  # per_query only
    stripe_price_id: str = ""       # subscription only


@router.post("/corpora/{corpus_id}/checkout")
async def api_checkout(corpus_id: str, req: CheckoutRequest, request: Request):
    """Create a Stripe Checkout session for a paid corpus."""
    corpus = _resolve_corpus(corpus_id)
    if corpus.get("access_level") != "paid":
        raise HTTPException(status_code=400, detail="This corpus is not set to paid access")

    from noosphere.core.payments import create_checkout_session, PaymentError
    try:
        return create_checkout_session(
            corpus,
            success_url=req.success_url,
            cancel_url=req.cancel_url,
            payer_email=req.payer_email,
            agent_id=req.agent_id,
        )
    except PaymentError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/corpora/{corpus_id}/pricing")
async def api_set_pricing(corpus_id: str, req: PricingRequest, request: Request):
    """Set pricing config for a corpus. Also sets access_level to 'paid'."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _require_originals_for_public_access(corpus["id"], "paid")

    import json as _j
    pricing = {
        "type": req.type,
        "amount_cents": req.amount_cents,
        "currency": req.currency,
    }
    if req.type == "per_query":
        pricing["queries_per_payment"] = req.queries_per_payment
    elif req.type == "subscription":
        if not req.stripe_price_id:
            raise HTTPException(status_code=400, detail="subscription type requires stripe_price_id")
        pricing["stripe_price_id"] = req.stripe_price_id

    from noosphere.core.corpus import update_corpus
    result = update_corpus(corpus["id"], pricing_json=_j.dumps(pricing), access_level="paid")
    return {"pricing": pricing, "corpus": result}


@router.get("/corpora/{corpus_id}/pricing")
async def api_get_pricing(corpus_id: str, request: Request):
    """Get pricing config for a corpus."""
    corpus = _resolve_corpus(corpus_id)
    from noosphere.core.payments import get_pricing
    pricing = get_pricing(corpus)
    return {"pricing": pricing, "access_level": corpus.get("access_level", "public")}


@router.get("/corpora/{corpus_id}/revenue")
async def api_revenue(corpus_id: str, request: Request):
    """Revenue dashboard for a paid corpus (owner only)."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.payments import get_revenue_stats
    return get_revenue_stats(corpus_id)


@router.post("/stripe/webhook")
async def api_stripe_webhook(request: Request):
    """Handle Stripe webhook events (payment completion, refunds, subscription cancellation)."""
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    from noosphere.core.payments import handle_webhook_event, PaymentError
    try:
        result = handle_webhook_event(payload, sig)
        return result
    except PaymentError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
