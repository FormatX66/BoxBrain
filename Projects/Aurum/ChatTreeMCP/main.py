"""ChatGPT/MCP adapter for Aurum Chat Tree.

This is intentionally a tool-only MCP surface. The durable tree, routing logic,
and evidence-backed state remain owned by the existing BoxBrain modules; this
server only exposes those capabilities through Streamable HTTP at /mcp.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
import sys
from typing import Any, Dict, List, Mapping

import mcp.types as types
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse


HERE = Path(__file__).resolve().parent
AURUM_ROOT = HERE.parent
EXPERIMENTS = AURUM_ROOT / "Experiments"
if str(EXPERIMENTS) not in sys.path:
    sys.path.insert(0, str(EXPERIMENTS))

from chat_tree_bridge import handle_request  # noqa: E402


DEFAULT_TREE = AURUM_ROOT / "chat-process-tree.json"
DEFAULT_EVENTS = AURUM_ROOT / "shared-state" / "events.jsonl"
DEFAULT_PROJECTION = AURUM_ROOT / "shared-state" / "CURRENT_STATE.json"


def _path_from_env(name: str, default: Path) -> Path:
    value = os.getenv(name)
    return Path(value).expanduser().resolve() if value else default


def storage_paths() -> tuple[Path, Path, Path]:
    return (
        _path_from_env("CHAT_TREE_TREE_PATH", DEFAULT_TREE),
        _path_from_env("CHAT_TREE_EVENTS_PATH", DEFAULT_EVENTS),
        _path_from_env("CHAT_TREE_PROJECTION_PATH", DEFAULT_PROJECTION),
    )


def _split_env_list(value: str | None) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _transport_security_settings() -> TransportSecuritySettings:
    allowed_hosts = _split_env_list(os.getenv("MCP_ALLOWED_HOSTS"))
    allowed_origins = _split_env_list(os.getenv("MCP_ALLOWED_ORIGINS"))
    if not allowed_hosts and not allowed_origins:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


mcp = FastMCP(
    name="aurum-chat-tree",
    stateless_http=True,
    transport_security=_transport_security_settings(),
)


TOOL_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "get_tree": {
        "title": "Read Aurum Chat Tree",
        "description": (
            "Use this when you need the current durable Aurum conversation/process "
            "tree, focus path, sibling lanes, concepts, or boundaries."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "focus_id": {
                    "type": "string",
                    "description": "Optional node to render as the requested focus.",
                }
            },
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
            "idempotentHint": True,
        },
    },
    "get_state": {
        "title": "Read Aurum Shared State",
        "description": (
            "Use this when you need evidence-backed live state for Aurum devices, "
            "projects, runners, or processes. Chat memory is not treated as runtime proof."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
            "idempotentHint": True,
        },
    },
    "route_topic": {
        "title": "Route Aurum Topic",
        "description": (
            "Use this when the conversation objective may have changed and Chat Tree "
            "must decide whether to continue, create a child subproblem, or create a sibling topic."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "current_id": {"type": "string"},
                "new_node_id": {"type": "string"},
                "title": {"type": "string"},
                "objective": {"type": "string"},
                "concepts": {"type": "array", "items": {"type": "string"}},
                "relation_hint": {
                    "type": "string",
                    "enum": ["same", "subproblem", "new", "unknown"],
                    "default": "unknown",
                },
                "summary": {"type": "string"},
                "evidence_refs": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["current_id", "new_node_id", "title", "objective"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": False,
            "idempotentHint": False,
        },
    },
    "post_receipt": {
        "title": "Post Aurum Evidence Receipt",
        "description": (
            "Use this when a runner, device, chat, or process has new state to record. "
            "Verified-running and succeeded states require evidence references."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "subject_id": {"type": "string"},
                "subject_kind": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": [
                        "planned", "queued", "running_unverified", "running_verified",
                        "waiting", "blocked", "succeeded", "failed", "no_change", "refused"
                    ],
                },
                "actor": {"type": "string"},
                "source": {"type": "string"},
                "node_id": {"type": "string"},
                "summary": {"type": "string"},
                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                "dependency_ids": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "authority_ref": {"type": "string"},
                "payload": {"type": "object"},
            },
            "required": ["subject_id", "subject_kind", "status", "actor", "source"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": False,
            "idempotentHint": False,
        },
    },
}


@mcp._mcp_server.list_tools()
async def _list_tools() -> List[types.Tool]:
    return [
        types.Tool(
            name=name,
            title=spec["title"],
            description=spec["description"],
            inputSchema=deepcopy(spec["inputSchema"]),
            annotations=deepcopy(spec["annotations"]),
        )
        for name, spec in TOOL_DEFINITIONS.items()
    ]


def dispatch(tool_name: str, arguments: Mapping[str, object] | None = None) -> dict[str, object]:
    if tool_name not in TOOL_DEFINITIONS:
        raise ValueError(f"unknown tool: {tool_name}")
    request: dict[str, object] = {"command": tool_name}
    request.update(dict(arguments or {}))
    tree_path, events_path, projection_path = storage_paths()
    return handle_request(
        request,
        tree_path=tree_path,
        events_path=events_path,
        projection_path=projection_path,
    )


@mcp._mcp_server.call_tool()
async def _call_tool(req: types.CallToolRequest) -> types.ServerResult:
    try:
        result = dispatch(req.params.name, req.params.arguments or {})
        return types.ServerResult(
            types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=_result_summary(req.params.name, result),
                    )
                ],
                structuredContent=result,
                isError=False,
            )
        )
    except Exception as exc:
        return types.ServerResult(
            types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=f"{type(exc).__name__}: {exc}",
                    )
                ],
                structuredContent={
                    "ok": False,
                    "error": type(exc).__name__,
                    "message": str(exc),
                },
                isError=True,
            )
        )


def _result_summary(tool_name: str, result: Mapping[str, object]) -> str:
    if tool_name == "route_topic":
        return (
            f"Topic route: {result.get('route')} -> focus {result.get('focus_id')} "
            f"(tree_changed={result.get('tree_changed')})."
        )
    if tool_name == "post_receipt":
        state = result.get("state")
        if isinstance(state, Mapping):
            return f"Recorded {state.get('subject_id')} as {state.get('status')}."
        return "Recorded Aurum state receipt."
    if tool_name == "get_tree":
        return "Read the durable Aurum Chat Tree."
    return "Read the evidence-backed Aurum shared-state projection."


app = mcp.streamable_http_app()


async def _health(_: object) -> JSONResponse:
    tree_path, events_path, projection_path = storage_paths()
    return JSONResponse(
        {
            "ok": True,
            "service": "aurum-chat-tree-mcp",
            "mcp": "/mcp",
            "tree_exists": tree_path.exists(),
            "events_exists": events_path.exists(),
            "projection_exists": projection_path.exists(),
        }
    )


app.add_route("/healthz", _health, methods=["GET"])


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
