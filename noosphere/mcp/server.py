"""MCP server exposing corpus tools for AI agents.

Implements the MCP protocol over SSE (Server-Sent Events) transport,
compatible with Claude, Cursor, Codex, and other MCP clients.
"""

import json
from noosphere.core.corpus import list_corpora, get_corpus, get_corpus_by_slug
from noosphere.core.ingest import get_documents, get_document
from noosphere.core.retrieval import search_corpus
from noosphere.core.access import check_access, AccessDenied


TOOLS = [
    {
        "name": "search",
        "description": "Semantic search across a Noosphere corpus. Returns ranked text chunks with source citations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "corpus_id": {"type": "string", "description": "Corpus ID or slug"},
                "query": {"type": "string", "description": "Search query"},
                "top_k": {"type": "integer", "description": "Number of results (default 5)", "default": 5},
            },
            "required": ["corpus_id", "query"],
        },
    },
    {
        "name": "list_corpora",
        "description": "List all available Noosphere corpora with metadata.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_document",
        "description": "Retrieve a full document by ID from a corpus.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "corpus_id": {"type": "string", "description": "Corpus ID or slug"},
                "document_id": {"type": "string", "description": "Document ID"},
            },
            "required": ["corpus_id", "document_id"],
        },
    },
    {
        "name": "list_documents",
        "description": "List all documents in a corpus with metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "corpus_id": {"type": "string", "description": "Corpus ID or slug"},
            },
            "required": ["corpus_id"],
        },
    },
    {
        "name": "get_stats",
        "description": "Get statistics for a corpus (document count, chunk count, word count).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "corpus_id": {"type": "string", "description": "Corpus ID or slug"},
            },
            "required": ["corpus_id"],
        },
    },
    {
        "name": "get_topics",
        "description": "List extracted topics and themes from a corpus.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "corpus_id": {"type": "string", "description": "Corpus ID or slug"},
            },
            "required": ["corpus_id"],
        },
    },
    {
        "name": "get_manifest",
        "description": "Get the full corpus manifest including metadata, stats, and access configuration.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "corpus_id": {"type": "string", "description": "Corpus ID or slug"},
            },
            "required": ["corpus_id"],
        },
    },
]


def _resolve(corpus_id: str) -> dict | None:
    return get_corpus(corpus_id) or get_corpus_by_slug(corpus_id)


def _check_mcp_access(corpus: dict, bearer_token: str | None):
    """Enforce access control for MCP calls. Raises AccessDenied on failure."""
    check_access(corpus, bearer_token)


def handle_tool_call(
    name: str,
    arguments: dict,
    *,
    bearer_token: str | None = None,
    agent_id: str = "",
) -> dict:
    """Execute an MCP tool call and return the result.

    Raises AccessDenied if the corpus requires authentication.
    """
    if name == "search":
        c = _resolve(arguments["corpus_id"])
        if not c:
            return {"error": f"Corpus not found: {arguments['corpus_id']}"}
        token_id = None
        if bearer_token:
            from noosphere.core.tokens import validate_token
            token_id = validate_token(c["id"], bearer_token)
        _check_mcp_access(c, bearer_token)
        result = search_corpus(
            c["id"], arguments["query"],
            top_k=arguments.get("top_k", 5),
            agent_id=agent_id,
            token_id=token_id,
        )
        return result

    elif name == "list_corpora":
        corpora = list_corpora()
        return {"corpora": [{"id": c["id"], "name": c["name"], "slug": c["slug"],
                             "description": c.get("description", ""),
                             "document_count": c["document_count"],
                             "chunk_count": c["chunk_count"],
                             "status": c["status"]} for c in corpora]}

    elif name == "get_document":
        c = _resolve(arguments["corpus_id"])
        if not c:
            return {"error": f"Corpus not found: {arguments['corpus_id']}"}
        _check_mcp_access(c, bearer_token)
        doc = get_document(arguments["document_id"])
        if not doc:
            return {"error": f"Document not found: {arguments['document_id']}"}
        return doc

    elif name == "list_documents":
        c = _resolve(arguments["corpus_id"])
        if not c:
            return {"error": f"Corpus not found: {arguments['corpus_id']}"}
        _check_mcp_access(c, bearer_token)
        docs = get_documents(c["id"])
        return {"documents": [{"id": d["id"], "title": d["title"],
                               "doc_type": d.get("doc_type", ""),
                               "date": d.get("date", ""),
                               "word_count": d.get("word_count", 0)} for d in docs]}

    elif name == "get_stats":
        c = _resolve(arguments["corpus_id"])
        if not c:
            return {"error": f"Corpus not found: {arguments['corpus_id']}"}
        _check_mcp_access(c, bearer_token)
        return {
            "corpus_id": c["id"], "name": c["name"],
            "document_count": c["document_count"],
            "chunk_count": c["chunk_count"],
            "word_count": c["word_count"],
            "embedding_model": c.get("embedding_model", ""),
            "status": c["status"],
        }

    elif name == "get_topics":
        c = _resolve(arguments["corpus_id"])
        if not c:
            return {"error": f"Corpus not found: {arguments['corpus_id']}"}
        _check_mcp_access(c, bearer_token)
        docs = get_documents(c["id"])
        topics = set()
        corpus_tags = c.get("tags", [])
        if isinstance(corpus_tags, list):
            for t in corpus_tags:
                topics.add(t.strip().lower())
        for doc in docs:
            doc_tags = doc.get("tags", "[]")
            if isinstance(doc_tags, str):
                try:
                    doc_tags = json.loads(doc_tags)
                except Exception:
                    doc_tags = []
            if isinstance(doc_tags, list):
                for t in doc_tags:
                    topics.add(t.strip().lower())
        return {"topics": sorted(topics)}

    elif name == "get_manifest":
        c = _resolve(arguments["corpus_id"])
        if not c:
            return {"error": f"Corpus not found: {arguments['corpus_id']}"}
        _check_mcp_access(c, bearer_token)
        return c

    return {"error": f"Unknown tool: {name}"}


def get_mcp_manifest() -> dict:
    """Return the MCP server manifest."""
    return {
        "name": "noosphere",
        "version": "0.1.0",
        "description": "Query Noosphere knowledge corpora — semantic search with citations.",
        "tools": TOOLS,
    }
