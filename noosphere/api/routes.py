"""REST API routes for corpus operations."""

import json as _json
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel

from noosphere import __version__
from noosphere.core.corpus import list_corpora, get_corpus, get_corpus_by_slug, create_corpus, update_corpus, delete_corpus
from noosphere.core.ingest import get_documents, get_document, ingest_text, ingest_url, delete_document, update_document
from noosphere.core.retrieval import search_corpus
from noosphere.core.access import check_access, AccessDenied
from noosphere.core.db import get_conn

router = APIRouter()

_registry_connected: bool = False


def set_registry_connected(value: bool):
    global _registry_connected
    _registry_connected = value


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
        if host in ("127.0.0.1", "::1", "localhost", "0.0.0.0"):
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


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    include_context: bool = True


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


class UpdateDocumentRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


class IngestURLRequest(BaseModel):
    url: str
    doc_type: str = "blog"


class CreateTokenRequest(BaseModel):
    label: str = ""
    permissions: str = "read"
    expires_at: str | None = None


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
    corpora = list_corpora(include_private=True)
    return {
        "status": "ok",
        "version": __version__,
        "corpus_count": len(corpora),
        "registry_connected": _registry_connected,
    }


# ── Profile ──

@router.get("/me")
async def api_me():
    from noosphere.core.config import OWNER_NAME
    return {"name": OWNER_NAME}


# ── Corpus CRUD ──

@router.get("/corpora")
async def api_list_corpora(request: Request):
    return list_corpora(include_private=_is_owner_request(request))


@router.post("/corpora")
async def api_create_corpus(req: CreateCorpusRequest):
    corpus = create_corpus(
        req.name, description=req.description, author_name=req.author_name,
        tags=req.tags, access_level=req.access_level, language=req.language,
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
async def api_update_document(corpus_id: str, doc_id: str, req: UpdateDocumentRequest):
    _resolve_corpus(corpus_id)
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = update_document(doc_id, **updates)
    if not result:
        raise HTTPException(status_code=404, detail="Document not found")
    return result


@router.delete("/corpora/{corpus_id}/documents/{doc_id}")
async def api_delete_document(corpus_id: str, doc_id: str):
    _resolve_corpus(corpus_id)
    if not delete_document(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "deleted"}


# ── File upload ──

def _extract_pdf_text(raw: bytes) -> str:
    import fitz
    doc = fitz.open(stream=raw, filetype="pdf")
    pages = [page.get_text() for page in doc]
    doc.close()
    return "\n\n".join(pages)


def _extract_docx_text(raw: bytes) -> str:
    import io
    from docx import Document
    doc = Document(io.BytesIO(raw))
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _extract_csv_text(content: str) -> str:
    import csv, io
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        return ""
    header = rows[0]
    lines = []
    for row in rows[1:]:
        entry = "; ".join(f"{header[i]}: {row[i]}" for i in range(min(len(header), len(row))) if row[i].strip())
        if entry:
            lines.append(entry)
    return "\n".join(lines)


def _extract_json_text(content: str) -> str:
    import json
    data = json.loads(content)
    if isinstance(data, list):
        parts = []
        for item in data:
            if isinstance(item, dict):
                parts.append("\n".join(f"{k}: {v}" for k, v in item.items() if isinstance(v, (str, int, float))))
            else:
                parts.append(str(item))
        return "\n\n".join(parts)
    elif isinstance(data, dict):
        return "\n".join(f"{k}: {v}" for k, v in data.items() if isinstance(v, (str, int, float)))
    return str(data)


SUPPORTED_EXTENSIONS = {"md", "markdown", "txt", "text", "html", "htm", "pdf", "docx", "csv", "json", "jsonl"}


@router.post("/corpora/{corpus_id}/upload")
async def api_upload_files(
    corpus_id: str,
    files: list[UploadFile] = File(...),
    background_tasks: BackgroundTasks = None,
):
    corpus = _resolve_corpus(corpus_id)
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
            date=metadata.get("date", "") if isinstance(metadata, dict) else "",
            tags=tags, metadata=metadata if isinstance(metadata, dict) else {},
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
    try:
        result = index_corpus(corpus["id"])
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
    agent_id = request.headers.get("x-agent-id", "")
    return search_corpus(
        corpus["id"], req.query, top_k=req.top_k,
        include_context=req.include_context,
        agent_id=agent_id, token_id=token_id,
    )


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
async def api_export_corpus(corpus_id: str):
    """Export a corpus as a ZIP file."""
    corpus = _resolve_corpus(corpus_id)
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
async def api_create_token(corpus_id: str, req: CreateTokenRequest):
    """Create an access token for a corpus. Returns plaintext token (one-time)."""
    corpus = _resolve_corpus(corpus_id)
    from noosphere.core.tokens import create_token
    return create_token(corpus["id"], label=req.label, permissions=req.permissions, expires_at=req.expires_at)


@router.get("/corpora/{corpus_id}/tokens")
async def api_list_tokens(corpus_id: str):
    """List all access tokens for a corpus (without hashes)."""
    corpus = _resolve_corpus(corpus_id)
    from noosphere.core.tokens import list_tokens
    return list_tokens(corpus["id"])


@router.delete("/corpora/{corpus_id}/tokens/{token_id}")
async def api_revoke_token(corpus_id: str, token_id: str):
    """Revoke an access token."""
    _resolve_corpus(corpus_id)
    from noosphere.core.tokens import revoke_token
    if not revoke_token(token_id):
        raise HTTPException(status_code=404, detail="Token not found")
    return {"status": "revoked"}


# ── Query Logs / Analytics ──

@router.post("/search")
async def api_global_search(req: SearchRequest):
    """Search across ALL public corpora."""
    corpora = list_corpora()
    ready = [c for c in corpora if c.get("status") == "ready" and c.get("access_level") == "public"]
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
async def api_corpus_chat(corpus_id: str, req: ChatRequest, request: Request):
    """Chat with a specific corpus."""
    import uuid
    from datetime import datetime, timezone

    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    from noosphere.core.chat import chat_with_corpus
    result = chat_with_corpus(corpus["id"], req.message, history=req.history, top_k=req.top_k)

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
async def api_delete_chat_session(session_id: str):
    """Delete a chat session and all its messages."""
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
