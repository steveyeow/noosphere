"""REST API routes for corpus operations."""

import json as _json
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel

from noosphere import __version__
from noosphere.core.corpus import list_corpora, get_corpus, get_corpus_by_slug, create_corpus, update_corpus, delete_corpus
from noosphere.core.ingest import get_documents, get_document, ingest_text, ingest_url, delete_document
from noosphere.core.retrieval import search_corpus
from noosphere.core.db import get_conn

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    include_context: bool = True


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    top_k: int = 5


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


class IngestURLRequest(BaseModel):
    url: str
    doc_type: str = "blog"


@router.post("/terminal")
async def api_terminal(req: TerminalRequest):
    """Interactive terminal command handler."""
    from noosphere.core.terminal import handle_terminal_input
    return handle_terminal_input(req.input, req.context)


def _resolve_corpus(corpus_id: str) -> dict:
    corpus = get_corpus(corpus_id) or get_corpus_by_slug(corpus_id)
    if not corpus:
        raise HTTPException(status_code=404, detail="Corpus not found")
    return corpus


@router.get("/health")
async def api_health():
    corpora = list_corpora()
    return {"status": "ok", "version": __version__, "corpus_count": len(corpora)}


# ── Corpus CRUD ──

@router.get("/corpora")
async def api_list_corpora():
    return list_corpora()


@router.post("/corpora")
async def api_create_corpus(req: CreateCorpusRequest):
    corpus = create_corpus(
        req.name, description=req.description, author_name=req.author_name,
        tags=req.tags, access_level=req.access_level, language=req.language,
    )
    return corpus


@router.get("/corpora/network")
async def api_corpus_network():
    corpora = list_corpora()
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
async def api_get_corpus(corpus_id: str):
    return _resolve_corpus(corpus_id)


@router.patch("/corpora/{corpus_id}")
async def api_update_corpus(corpus_id: str, req: UpdateCorpusRequest):
    _resolve_corpus(corpus_id)
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = update_corpus(corpus_id, **updates)
    return result


@router.delete("/corpora/{corpus_id}")
async def api_delete_corpus(corpus_id: str):
    _resolve_corpus(corpus_id)
    delete_corpus(corpus_id)
    return {"status": "deleted"}


# ── Documents ──

@router.get("/corpora/{corpus_id}/documents")
async def api_list_documents(corpus_id: str):
    corpus = _resolve_corpus(corpus_id)
    return get_documents(corpus["id"])


@router.get("/corpora/{corpus_id}/documents/{doc_id}")
async def api_get_document(corpus_id: str, doc_id: str):
    _resolve_corpus(corpus_id)
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/corpora/{corpus_id}/documents/{doc_id}")
async def api_delete_document(corpus_id: str, doc_id: str):
    _resolve_corpus(corpus_id)
    if not delete_document(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "deleted"}


# ── File upload ──

@router.post("/corpora/{corpus_id}/upload")
async def api_upload_files(
    corpus_id: str,
    files: list[UploadFile] = File(...),
    background_tasks: BackgroundTasks = None,
):
    corpus = _resolve_corpus(corpus_id)
    results = []
    for f in files:
        content = (await f.read()).decode("utf-8", errors="replace")
        if not content.strip():
            continue
        from noosphere.core.ingest import _extract_markdown_metadata, _extract_markdown_title
        metadata, body = _extract_markdown_metadata(content)
        title = metadata.get("title") or _extract_markdown_title(body) or (f.filename or "Untitled").rsplit(".", 1)[0]

        ext = (f.filename or "").rsplit(".", 1)[-1].lower()
        doc_type = "doc"
        if ext in ("md", "markdown"):
            doc_type = "doc"
        elif ext in ("txt", "text"):
            doc_type = "note"

        tags_str = metadata.get("tags", "")
        tags = [t.strip() for t in tags_str.split(",")] if tags_str else []

        doc = ingest_text(
            corpus["id"], title=title, content=body, doc_type=doc_type,
            date=metadata.get("date", ""), tags=tags, metadata=metadata,
        )
        results.append(doc)

    return {"uploaded": len(results), "documents": results}


# ── URL ingestion ──

@router.post("/corpora/{corpus_id}/ingest-url")
async def api_ingest_url(corpus_id: str, req: IngestURLRequest):
    corpus = _resolve_corpus(corpus_id)
    try:
        doc = ingest_url(corpus["id"], req.url, doc_type=req.doc_type)
        return doc
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Indexing ──

@router.post("/corpora/{corpus_id}/index")
async def api_index_corpus(corpus_id: str, background_tasks: BackgroundTasks = None):
    corpus = _resolve_corpus(corpus_id)
    from noosphere.core.indexer import index_corpus
    result = index_corpus(corpus["id"])
    return result


# ── Search ──

@router.post("/corpora/{corpus_id}/search")
async def api_search(corpus_id: str, req: SearchRequest):
    corpus = _resolve_corpus(corpus_id)
    return search_corpus(corpus["id"], req.query, top_k=req.top_k, include_context=req.include_context)


# ── Stats & Topics ──

@router.get("/corpora/{corpus_id}/stats")
async def api_stats(corpus_id: str):
    corpus = _resolve_corpus(corpus_id)
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
async def api_topics(corpus_id: str):
    corpus = _resolve_corpus(corpus_id)
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


# ── Query Logs / Analytics ──

@router.post("/search")
async def api_global_search(req: SearchRequest):
    """Search across ALL public corpora."""
    corpora = list_corpora()
    ready = [c for c in corpora if c.get("status") == "ready"]
    if not ready:
        return {"results": [], "corpora_searched": 0}

    all_results = []
    for c in ready:
        try:
            result = search_corpus(c["id"], req.query, top_k=req.top_k, include_context=req.include_context)
            for r in result.get("results", []):
                r["corpus_id"] = c["id"]
                r["corpus_name"] = c["name"]
                all_results.append(r)
        except Exception:
            continue

    all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {
        "results": all_results[: req.top_k],
        "corpora_searched": len(ready),
    }


# ── Chat ──

@router.post("/chat")
async def api_global_chat(req: ChatRequest):
    """Chat across all public corpora in the Noosphere."""
    from noosphere.core.chat import chat_with_noosphere
    return chat_with_noosphere(req.message, history=req.history, top_k=req.top_k)


@router.post("/corpora/{corpus_id}/chat")
async def api_corpus_chat(corpus_id: str, req: ChatRequest):
    """Chat with a specific corpus."""
    corpus = _resolve_corpus(corpus_id)
    from noosphere.core.chat import chat_with_corpus
    return chat_with_corpus(corpus["id"], req.message, history=req.history, top_k=req.top_k)


@router.get("/corpora/{corpus_id}/analytics")
async def api_analytics(corpus_id: str, limit: int = 50):
    corpus = _resolve_corpus(corpus_id)
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
