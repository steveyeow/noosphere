"""MCP server exposing corpus tools for AI agents.

Implements the MCP protocol over SSE (Server-Sent Events) transport,
compatible with Claude, Cursor, Codex, and other MCP clients.
"""

import json
from noosphere.core.corpus import list_corpora, get_corpus, get_corpus_by_slug
from noosphere.core.ingest import get_documents, get_document
from noosphere.core.retrieval import search_corpus
from noosphere.core.kb_agent import ask as kb_ask, describe as kb_describe, preview_ask as kb_preview_ask, route as kb_route
from noosphere.core.access import check_access, AccessDenied, verify_facilitator_proof


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
                "detail": {"type": "string", "description": "Search depth: low (keyword-only, fast), medium (hybrid, default), high (expanded + more results)", "enum": ["low", "medium", "high"], "default": "medium"},
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
    {
        "name": "preview",
        "description": "Preview a knowledge base before querying — returns sample content, quality signals, and content types. Works on any corpus including paid ones, no authentication needed. Use this to evaluate relevance before committing to a full search.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "corpus_id": {"type": "string", "description": "Corpus ID or slug"},
            },
            "required": ["corpus_id"],
        },
    },
    {
        "name": "ask",
        "description": "Ask a question against a corpus and receive a synthesized answer with inline [N] citations grounded in the source material. The corpus acts as an L0 agent — it answers, cites, and reports calibrated confidence. Respects access level (paid/token/public) like search.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "corpus_id": {"type": "string", "description": "Corpus ID or slug"},
                "question": {"type": "string", "description": "The question to ask"},
                "top_k": {"type": "integer", "description": "Number of source chunks to ground on (default 5)", "default": 5},
            },
            "required": ["corpus_id", "question"],
        },
    },
    {
        "name": "describe",
        "description": "Get a corpus's machine-readable capability card — task types, sample Q&A, source composition, autonomy level, calibration policy, and license terms. Use this to evaluate whether a KB matches your task before querying. No authentication required.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "corpus_id": {"type": "string", "description": "Corpus ID or slug"},
            },
            "required": ["corpus_id"],
        },
    },
    {
        "name": "preview_ask",
        "description": "Evaluation version of `ask` — bypasses access gating (even on paid corpora) and returns a truncated synthesized answer plus citations so agents can assess KB answer quality before paying for full access. Use `preview_ask` to decide; use `ask` when you've committed to using this KB.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "corpus_id": {"type": "string", "description": "Corpus ID or slug"},
                "question": {"type": "string", "description": "Evaluation question"},
            },
            "required": ["corpus_id", "question"],
        },
    },
    {
        "name": "route",
        "description": "Given a question this KB may not be the best fit for, recommend other KBs in the network that could answer it better. Returns a ranked list of candidate corpora (local + remote) with relevance, kb_reputation, and any explicit manifest endorsements from this KB.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "corpus_id": {"type": "string", "description": "Corpus ID or slug (the source KB)"},
                "question": {"type": "string", "description": "The question to route"},
                "limit": {"type": "integer", "description": "Max candidates to return (default 5)", "default": 5},
            },
            "required": ["corpus_id", "question"],
        },
    },
    {
        "name": "purchase",
        "description": (
            "Pay for paid-corpus access using an x402 payment proof. Without "
            "`payment_proof`, returns the x402 challenge body — pass it to your "
            "x402 payment client (Coinbase x402 SDK, etc.) to mint a proof, then "
            "call `purchase` again with `payment_proof` set. Returns an "
            "`access_token` usable with other MCP tools (pass via the "
            "`access_token` argument) for the duration of the TTL."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "corpus_id": {"type": "string", "description": "Corpus ID or slug"},
                "payment_proof": {
                    "type": "string",
                    "description": "Base64-encoded x402 payment payload (X-PAYMENT). Omit on first call to fetch the challenge.",
                },
            },
            "required": ["corpus_id"],
        },
    },
]


def _resolve(corpus_id: str) -> dict | None:
    return get_corpus(corpus_id) or get_corpus_by_slug(corpus_id)


def _check_mcp_access(
    corpus: dict,
    bearer_token: str | None,
    *,
    payment_proof: str | None = None,
    agent_id: str = "",
    tool_name: str = "",
) -> str | None:
    """Enforce access control for MCP calls. Returns token_id, settlement_id,
    or None. Raises AccessDenied on failure.

    For paid corpora, if the bearer doesn't validate but an x402
    `payment_proof` is supplied (either via X-PAYMENT header on the HTTP
    request or via the tool's `payment_proof` argument), the configured
    facilitator gets a chance to verify. Successful verification grants
    this single tool call and records an `agent_settlements` audit row.
    """
    try:
        return check_access(corpus, bearer_token)
    except AccessDenied as e:
        if e.status_code == 402 and payment_proof:
            resource = f"/mcp/tools/{tool_name or 'unknown'}/corpora/{corpus['id']}"
            result, settlement_id = verify_facilitator_proof(
                corpus, payment_proof, resource=resource, agent_id=agent_id,
            )
            if result.valid:
                return settlement_id
        raise


def handle_tool_call(
    name: str,
    arguments: dict,
    *,
    bearer_token: str | None = None,
    agent_id: str = "",
    caller_corpus_id: str = "",
    payment_proof: str | None = None,
) -> dict:
    """Execute an MCP tool call and return the result.

    Raises AccessDenied if the corpus requires authentication.

    `caller_corpus_id` (from `X-Noosphere-Caller-Corpus` header) enables
    inter-KB attribution: when set to a locally-known corpus, successful
    `ask` calls record a `query`-kind citation so the network learns which
    KBs get consulted by which.
    """
    if name == "search":
        c = _resolve(arguments["corpus_id"])
        if not c:
            return {"error": f"Corpus not found: {arguments['corpus_id']}"}
        token_id = _check_mcp_access(c, bearer_token, payment_proof=payment_proof, agent_id=agent_id, tool_name=name)
        # MCP consumers are external agents — always apply source_kind filter.
        result = search_corpus(
            c["id"], arguments["query"],
            top_k=arguments.get("top_k", 5),
            detail=arguments.get("detail", "medium"),
            agent_id=agent_id,
            token_id=token_id,
            caller="external",
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
        _check_mcp_access(c, bearer_token, payment_proof=payment_proof, agent_id=agent_id, tool_name=name)
        doc = get_document(arguments["document_id"])
        if not doc:
            return {"error": f"Document not found: {arguments['document_id']}"}
        return doc

    elif name == "list_documents":
        c = _resolve(arguments["corpus_id"])
        if not c:
            return {"error": f"Corpus not found: {arguments['corpus_id']}"}
        _check_mcp_access(c, bearer_token, payment_proof=payment_proof, agent_id=agent_id, tool_name=name)
        docs = get_documents(c["id"])
        return {"documents": [{"id": d["id"], "title": d["title"],
                               "doc_type": d.get("doc_type", ""),
                               "date": d.get("date", ""),
                               "word_count": d.get("word_count", 0)} for d in docs]}

    elif name == "get_stats":
        c = _resolve(arguments["corpus_id"])
        if not c:
            return {"error": f"Corpus not found: {arguments['corpus_id']}"}
        _check_mcp_access(c, bearer_token, payment_proof=payment_proof, agent_id=agent_id, tool_name=name)
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
        _check_mcp_access(c, bearer_token, payment_proof=payment_proof, agent_id=agent_id, tool_name=name)
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
        _check_mcp_access(c, bearer_token, payment_proof=payment_proof, agent_id=agent_id, tool_name=name)
        return c

    elif name == "preview":
        c = _resolve(arguments["corpus_id"])
        if not c:
            return {"error": f"Corpus not found: {arguments['corpus_id']}"}
        # Preview is always available — no access check
        from noosphere.core.db import get_conn
        conn = get_conn()
        sample_chunks = conn.execute(
            """SELECT c.text, c.document_id, d.title as document_title, d.doc_type
               FROM chunks c JOIN documents d ON d.id = c.document_id
               WHERE c.corpus_id=? ORDER BY c.created_at DESC LIMIT 20""",
            (c["id"],),
        ).fetchall()
        seen_docs = set()
        samples = []
        for row in sample_chunks:
            did = row["document_id"]
            if did in seen_docs:
                continue
            seen_docs.add(did)
            text = row["text"]
            if len(text) > 250:
                text = text[:247] + "..."
            samples.append({"text": text, "document_title": row["document_title"],
                            "document_type": row["doc_type"] or ""})
            if len(samples) >= 5:
                break
        query_count = conn.execute(
            "SELECT COUNT(*) as n FROM query_logs WHERE corpus_id=?", (c["id"],)
        ).fetchone()["n"]
        tags = c.get("tags", [])
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = []
        return {
            "corpus_id": c["id"], "name": c["name"],
            "description": c.get("description", ""),
            "author": c.get("author_name", ""),
            "tags": tags,
            "access_level": c.get("access_level", "public"),
            "quality": {
                "document_count": c.get("document_count", 0),
                "word_count": c.get("word_count", 0),
                "query_count": query_count,
                "last_updated": c.get("updated_at", ""),
                "status": c.get("status", "draft"),
            },
            "samples": samples,
        }

    elif name == "ask":
        c = _resolve(arguments["corpus_id"])
        if not c:
            return {"error": f"Corpus not found: {arguments['corpus_id']}"}
        token_id = _check_mcp_access(c, bearer_token, payment_proof=payment_proof, agent_id=agent_id, tool_name=name)
        result = kb_ask(
            c["id"], arguments["question"],
            top_k=arguments.get("top_k", 5),
            caller="external",
            agent_id=agent_id,
            token_id=token_id,
        )
        if result is None:
            return {"error": f"Corpus not found: {arguments['corpus_id']}"}
        if caller_corpus_id:
            resolved_caller = _resolve(caller_corpus_id)
            if resolved_caller and resolved_caller["id"] != c["id"] and result.get("chunks_used", 0) > 0:
                from noosphere.core.citations import record_inter_kb_query
                try:
                    record_inter_kb_query(
                        resolved_caller["id"], c["id"],
                        context=arguments["question"][:200],
                    )
                except Exception:
                    pass
        return result

    elif name == "describe":
        c = _resolve(arguments["corpus_id"])
        if not c:
            return {"error": f"Corpus not found: {arguments['corpus_id']}"}
        # Describe is always available — capability cards are discoverable.
        result = kb_describe(c["id"])
        return result or {"error": f"Corpus not found: {arguments['corpus_id']}"}

    elif name == "preview_ask":
        c = _resolve(arguments["corpus_id"])
        if not c:
            return {"error": f"Corpus not found: {arguments['corpus_id']}"}
        if c.get("access_level") == "private":
            return {"error": "Private corpus — preview_ask not available"}
        result = kb_preview_ask(c["id"], arguments["question"])
        return result or {"error": f"Corpus not found: {arguments['corpus_id']}"}

    elif name == "route":
        c = _resolve(arguments["corpus_id"])
        if not c:
            return {"error": f"Corpus not found: {arguments['corpus_id']}"}
        if c.get("access_level") == "private":
            return {"error": "Private corpus — route not available"}
        result = kb_route(
            c["id"], arguments["question"],
            limit=arguments.get("limit", 5),
        )
        return result or {"error": f"Corpus not found: {arguments['corpus_id']}"}

    elif name == "purchase":
        c = _resolve(arguments["corpus_id"])
        if not c:
            return {"error": f"Corpus not found: {arguments['corpus_id']}"}
        if c.get("access_level") != "paid":
            return {"error": "Corpus is not paid — no payment required"}
        proof = (arguments.get("payment_proof") or payment_proof or "").strip()
        if not proof:
            from noosphere.core.agent_payments import build_x402_challenge

            return {
                "x402": build_x402_challenge(
                    c, resource=f"/mcp/tools/purchase/corpora/{c['id']}",
                ),
                "instructions": (
                    "Use your x402 payment client to satisfy the challenge, then "
                    "call `purchase` again with `payment_proof` set to the resulting "
                    "X-PAYMENT payload."
                ),
            }
        from noosphere.core.agent_payments import (
            ACCESS_TOKEN_TTL_SECONDS,
            mint_access_token,
        )

        result, settlement_id = verify_facilitator_proof(
            c, proof,
            resource=f"/mcp/tools/purchase/corpora/{c['id']}",
            agent_id=agent_id,
        )
        if not result.valid:
            return {"error": f"Payment invalid: {result.reason}"}
        _, raw = mint_access_token(c["id"])
        return {
            "settlement_id": settlement_id,
            "amount_settled_cents": result.amount_cents,
            "scheme": result.scheme,
            "network": result.network,
            "settlement_tx": result.settlement_tx,
            "access_token": raw,
            "access_token_ttl_seconds": ACCESS_TOKEN_TTL_SECONDS,
        }

    return {"error": f"Unknown tool: {name}"}


def get_mcp_manifest() -> dict:
    """Return the MCP server manifest."""
    return {
        "name": "noosphere",
        "version": "0.1.0",
        "description": "Query Noosphere knowledge corpora — semantic search with citations.",
        "tools": TOOLS,
    }
