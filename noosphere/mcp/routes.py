"""MCP HTTP endpoints — JSON-RPC over HTTP + SSE transport."""

import asyncio
import json
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from noosphere.mcp.server import get_mcp_manifest, handle_tool_call, TOOLS
from noosphere.core.access import AccessDenied

router = APIRouter()

_sse_sessions: dict[str, asyncio.Queue] = {}


@router.get("/mcp")
async def mcp_manifest():
    """Return MCP server manifest with available tools."""
    return get_mcp_manifest()


@router.get("/mcp/sse")
async def mcp_sse(request: Request):
    """SSE endpoint for MCP protocol — long-lived connection.

    Claude Desktop and other MCP clients connect here. The client
    sends JSON-RPC messages to /mcp/message?session_id=<id> and
    receives responses as SSE events on this connection.
    """
    session_id = uuid.uuid4().hex
    queue: asyncio.Queue = asyncio.Queue()
    _sse_sessions[session_id] = queue

    async def event_stream():
        yield f"event: endpoint\ndata: /mcp/message?session_id={session_id}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"event: message\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            _sse_sessions.pop(session_id, None)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/mcp/message")
async def mcp_message(request: Request, session_id: str = ""):
    """Receive JSON-RPC messages for an SSE session."""
    queue = _sse_sessions.get(session_id)
    if not queue:
        return JSONResponse(status_code=400, content={"error": "Invalid session"})

    body = await request.json()
    response = _handle_rpc(body, request)
    await queue.put(response)
    return JSONResponse(content={"ok": True})


@router.post("/mcp")
async def mcp_call(request: Request):
    """Handle MCP JSON-RPC calls (HTTP fallback, non-SSE)."""
    body = await request.json()
    result = _handle_rpc(body, request)
    return JSONResponse(content=result)


def _handle_rpc(body: dict, request: Request) -> dict:
    """Process a single JSON-RPC message and return the response dict."""
    method = body.get("method", "")
    params = body.get("params", {})
    req_id = body.get("id")

    auth = request.headers.get("authorization", "")
    bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else None
    agent_id = request.headers.get("x-agent-id", "")

    if method == "initialize":
        return _rpc_dict(req_id, {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "noosphere", "version": "0.1.0"},
            "capabilities": {"tools": {}},
        })

    elif method == "tools/list":
        return _rpc_dict(req_id, {"tools": TOOLS})

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        token = arguments.pop("access_token", None) or bearer
        try:
            result = handle_tool_call(
                tool_name, arguments,
                bearer_token=token,
                agent_id=agent_id,
            )
        except AccessDenied as e:
            return _err_dict(req_id, -32603, e.message)
        return _rpc_dict(req_id, {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
        })

    elif method == "notifications/initialized":
        return {}

    return _err_dict(req_id, -32601, f"Method not found: {method}")


def _rpc_dict(req_id, result) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err_dict(req_id, code, message) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
