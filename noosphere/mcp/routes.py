"""MCP HTTP endpoints — SSE transport for MCP protocol."""

import json
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from noosphere.mcp.server import get_mcp_manifest, handle_tool_call, TOOLS

router = APIRouter()


@router.get("/mcp")
async def mcp_manifest():
    """Return MCP server manifest with available tools."""
    return get_mcp_manifest()


@router.post("/mcp")
async def mcp_call(request: Request):
    """Handle MCP JSON-RPC calls."""
    body = await request.json()
    method = body.get("method", "")
    params = body.get("params", {})
    req_id = body.get("id")

    if method == "initialize":
        return _rpc_response(req_id, {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "noosphere", "version": "0.1.0"},
            "capabilities": {"tools": {}},
        })

    elif method == "tools/list":
        return _rpc_response(req_id, {"tools": TOOLS})

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        result = handle_tool_call(tool_name, arguments)
        return _rpc_response(req_id, {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
        })

    elif method == "notifications/initialized":
        return JSONResponse(content={})

    return _rpc_error(req_id, -32601, f"Method not found: {method}")


def _rpc_response(req_id, result):
    return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "result": result})


def _rpc_error(req_id, code, message):
    return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})
