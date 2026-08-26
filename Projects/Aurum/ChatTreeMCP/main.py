"""ChatGPT/MCP adapter for the canonical Aurum Chat Tree.

This is intentionally a small tool-only MCP surface. The durable tree, topic
router, and evidence-backed state remain owned by BoxBrain; this server exposes
those same primitives through Streamable HTTP at ``/mcp``.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any, Literal, Mapping

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


HERE = Path(__file__).resolve().parent
AURUM_ROOT = HERE.parent
EXPERIMENTS = AURUM_ROOT / "Experiments"
if str(EXPERIMENTS) not in sys.path:
    sys.path.insert(0, str(EXPERIMENTS))

from chat_tree_bridge import handle_request  # noqa: E402


DEFAULT_TREE = AURUM_ROOT / "chat-process-tree.json"
DEFAULT_EVENTS = AURUM_ROOT / "shared-state" / "events.jsonl"
DEFAULT_PROJECTION = AURUM_ROOT / "shared-state" / "CURRENT_STATE.json"

TOOL_NAMES = frozenset(
    {
        "get_tree",
        "get_state",
        "route_topic",
        "post_receipt",
        "publish_live_state",
        "read_live_state",
    }
)
STATUS = Literal[
    "planned",
    "queued",
    "running_unverified",
    "running_verified",
    "waiting",
    "blocked",
    "succeeded",
    "failed",
    "no_change",
    "refused",
]
RELATION_HINT = Literal["same", "subproblem", "new", "unknown"]

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
MUTATING = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)


def _path_from_env(name: str, default: Path) -> Path:
    value = os.getenv(name)
    return Path(value).expanduser().resolve() if value else default


def storage_paths() -> tuple[Path, Path, Path]:
    return (
        _path_from_env("CHAT_TREE_TREE_PATH", DEFAULT_TREE),
        _path_from_env("CHAT_TREE_EVENTS_PATH", DEFAULT_EVENTS),
        _path_from_env("CHAT_TREE_PROJECTION_PATH", DEFAULT_PROJECTION),
    )


def _split_env_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _expanded_hosts(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        result.append(value)
        if ":" not in value and "*" not in value:
            result.append(f"{value}:*")
    return list(dict.fromkeys(result))


def _transport_security_settings() -> TransportSecuritySettings | None:
    allowed_hosts = _expanded_hosts(_split_env_list(os.getenv("MCP_ALLOWED_HOSTS")))
    allowed_origins = _split_env_list(os.getenv("MCP_ALLOWED_ORIGINS"))
    if not allowed_hosts and not allowed_origins:
        return None
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


def dispatch(tool_name: str, arguments: Mapping[str, object] | None = None) -> dict[str, Any]:
    """Delegate one MCP operation to the canonical transport-neutral bridge."""

    if tool_name not in TOOL_NAMES:
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


mcp = MCPServer(
    "aurum-chat-tree",
    title="Aurum Chat Tree",
    description=(
        "Durable topic routing and evidence-backed shared state for BoxBrain/Future Branch. "
        "Chat memory is context; runtime claims require receipts."
    ),
)


@mcp.tool(
    title="Read Aurum Chat Tree",
    description=(
        "Use this when you need the current durable Aurum conversation/process tree, "
        "focus path, sibling lanes, concepts, or boundaries."
    ),
    annotations=READ_ONLY,
    structured_output=True,
)
def get_tree(focus_id: str | None = None) -> dict[str, Any]:
    args: dict[str, object] = {}
    if focus_id:
        args["focus_id"] = focus_id
    return dispatch("get_tree", args)


@mcp.tool(
    title="Read Aurum Shared State",
    description=(
        "Use this when you need evidence-backed live state for Aurum devices, projects, "
        "runners, or processes. Do not infer runtime truth from chat memory."
    ),
    annotations=READ_ONLY,
    structured_output=True,
)
def get_state() -> dict[str, Any]:
    return dispatch("get_state")


@mcp.tool(
    title="Read Aurum Cross-Chat Live State",
    description=(
        "Use this consumer action to read the newest shared status/current action, "
        "blocker, evidence, and next action for one chat/process or the live frontier. "
        "The append-only bus, not chat memory, is the source of truth."
    ),
    annotations=READ_ONLY,
    structured_output=True,
)
def read_live_state(
    subject_id: str | None = None,
    node_id: str | None = None,
    verified_only: bool = False,
    include_history: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    args: dict[str, object] = {
        "verified_only": verified_only,
        "include_history": include_history,
        "limit": limit,
    }
    if subject_id is not None:
        args["subject_id"] = subject_id
    if node_id is not None:
        args["node_id"] = node_id
    return dispatch("read_live_state", args)


@mcp.tool(
    title="Route Aurum Topic",
    description=(
        "Use this when the conversation objective may have changed and Chat Tree must "
        "decide whether to continue, create a child subproblem, or create a sibling topic."
    ),
    annotations=MUTATING,
    structured_output=True,
)
def route_topic(
    current_id: str,
    new_node_id: str,
    title: str,
    objective: str,
    concepts: list[str] | None = None,
    relation_hint: RELATION_HINT = "unknown",
    summary: str = "",
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    return dispatch(
        "route_topic",
        {
            "current_id": current_id,
            "new_node_id": new_node_id,
            "title": title,
            "objective": objective,
            "concepts": concepts or [],
            "relation_hint": relation_hint,
            "summary": summary,
            "evidence_refs": evidence_refs or [],
        },
    )


@mcp.tool(
    title="Post Aurum Evidence Receipt",
    description=(
        "Use this when a runner, device, chat, or process has new state to record. "
        "running_verified and succeeded require evidence references."
    ),
    annotations=MUTATING,
    structured_output=True,
)
def post_receipt(
    subject_id: str,
    subject_kind: str,
    status: STATUS,
    actor: str,
    source: str,
    node_id: str | None = None,
    summary: str = "",
    evidence_refs: list[str] | None = None,
    dependency_ids: list[str] | None = None,
    confidence: float | None = None,
    authority_ref: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if confidence is not None and not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")

    args: dict[str, object] = {
        "subject_id": subject_id,
        "subject_kind": subject_kind,
        "status": status,
        "actor": actor,
        "source": source,
        "summary": summary,
        "evidence_refs": evidence_refs or [],
        "dependency_ids": dependency_ids or [],
        "payload": payload or {},
    }
    if node_id is not None:
        args["node_id"] = node_id
    if confidence is not None:
        args["confidence"] = confidence
    if authority_ref is not None:
        args["authority_ref"] = authority_ref
    return dispatch("post_receipt", args)


@mcp.tool(
    title="Publish Aurum Cross-Chat Live State",
    description=(
        "Use this publisher action when a chat or process has a real live-state update. "
        "Append status, current action, blocker, evidence, and next action to the shared "
        "journal. Verified runtime/success states are refused without evidence, and this "
        "action never grants execution authority."
    ),
    annotations=MUTATING,
    structured_output=True,
)
def publish_live_state(
    subject_id: str,
    status: STATUS,
    current_action: str,
    next_action: str,
    actor: str,
    source: str,
    evidence: list[str],
    blocker: str | None = None,
    subject_kind: str = "chat",
    node_id: str | None = None,
    summary: str = "",
    dependency_ids: list[str] | None = None,
    confidence: float | None = None,
    authority_ref: str | None = None,
    event_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if confidence is not None and not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    args: dict[str, object] = {
        "subject_id": subject_id,
        "subject_kind": subject_kind,
        "status": status,
        "current_action": current_action,
        "blocker": blocker,
        "evidence": evidence,
        "next_action": next_action,
        "actor": actor,
        "source": source,
        "summary": summary,
        "dependency_ids": dependency_ids or [],
        "payload": payload or {},
    }
    if node_id is not None:
        args["node_id"] = node_id
    if confidence is not None:
        args["confidence"] = confidence
    if authority_ref is not None:
        args["authority_ref"] = authority_ref
    if event_id is not None:
        args["event_id"] = event_id
    return dispatch("publish_live_state", args)


@mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
async def health(_: Request) -> Response:
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


MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
app = mcp.streamable_http_app(
    stateless_http=True,
    transport_security=_transport_security_settings(),
    host=MCP_HOST,
)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    bind_host = os.getenv("BIND_HOST", "0.0.0.0")
    uvicorn.run(app, host=bind_host, port=port)
