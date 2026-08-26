"""ChatGPT/MCP adapter for the canonical Aurum Chat Tree.

This is intentionally a small tool-only MCP surface. The durable tree, topic
router, and evidence-backed state remain owned by BoxBrain; this server exposes
those same primitives through Streamable HTTP at ``/mcp``.
"""

from __future__ import annotations

import os
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Literal, Mapping
from urllib import error as urlerror
from urllib import request as urlrequest

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
FARMER_REPOSITORY = "FormatX66/Chat-to-Git-Pipeline"
FARMER_EVENT_TYPE = "aurum_farmer_event"
FARMER_OBJECTIVE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")

TOOL_NAMES = frozenset(
    {
        "get_tree",
        "get_state",
        "plan_consolidation",
        "consolidate_branch",
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
DESTRUCTIVE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=False,
    open_world_hint=False,
)
EXECUTING = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=True,
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


def _farmer_token() -> str:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    token_file = os.getenv("AURUM_FARMER_GITHUB_TOKEN_FILE", "").strip()
    if not token and token_file:
        try:
            token = Path(token_file).read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return token


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
    title="Dispatch Aurum Farmer Objective",
    description=(
        "Dispatch one bounded Aurum Farmer objective into the verified GitHub event-driven "
        "completion controller. Repository, event type, credential, and safety constraints "
        "are server-owned; arbitrary commands and payloads are not accepted."
    ),
    annotations=EXECUTING,
    structured_output=True,
)
def dispatch_farmer_objective(objective_id: str, objective: str) -> dict[str, Any]:
    if not FARMER_OBJECTIVE_ID.fullmatch(objective_id):
        raise ValueError("objective_id is invalid")
    objective = objective.strip()
    if not objective or len(objective) > 4000:
        raise ValueError("objective must contain 1 to 4000 characters")
    token = _farmer_token()
    if not token:
        return {
            "status": "machine_blocked",
            "human_required": False,
            "blocker": {"kind": "github_execution_credential_unavailable"},
        }
    body = json.dumps(
        {
            "event_type": FARMER_EVENT_TYPE,
            "client_payload": {
                "schema": "aurum.farmer.dispatch.v1",
                "objective_id": objective_id,
                "source": "chatgpt",
                "completion_definition": {
                    "no_further_human_input": True,
                    "no_known_bugs_or_glitches": True,
                    "fully_functional": True,
                    "no_required_changes_remaining": True,
                    "verification_passed": True,
                },
                "constraints": {
                    "continuation": "event_driven_no_polling",
                    "no_user_relay": True,
                    "no_arbitrary_shell": True,
                    "independent_verification_required": True,
                    "last_known_good_required": True,
                },
                "event": {"type": "farmer_request", "objective": objective, "work": []},
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")
    request = urlrequest.Request(
        f"https://api.github.com/repos/{FARMER_REPOSITORY}/dispatches",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "aurum-farmer-actuator/1",
        },
    )
    try:
        with urlrequest.urlopen(request, timeout=30) as response:
            status = response.status
            github_request_id = response.headers.get("x-github-request-id")
            detail = response.read(1000).decode("utf-8", "replace")
    except urlerror.HTTPError as exc:
        return {
            "status": "machine_blocked",
            "human_required": False,
            "blocker": {
                "kind": "github_repository_dispatch_failed",
                "http_status": exc.code,
                "detail": exc.read(1000).decode("utf-8", "replace"),
            },
        }
    except OSError as exc:
        return {
            "status": "machine_blocked",
            "human_required": False,
            "blocker": {"kind": "github_repository_dispatch_failed", "http_status": 0, "detail": str(exc)[:1000]},
        }
    if not 200 <= status < 300:
        return {
            "status": "machine_blocked",
            "human_required": False,
            "blocker": {"kind": "github_repository_dispatch_failed", "http_status": status, "detail": detail},
        }
    receipt = hashlib.sha256(
        FARMER_REPOSITORY.encode() + b"\0" + objective_id.encode() + b"\0" + (github_request_id or "").encode() + b"\0" + body
    ).hexdigest()[:32]
    return {
        "status": "dispatch_accepted",
        "human_required": False,
        "objective_id": objective_id,
        "repository": FARMER_REPOSITORY,
        "event_type": FARMER_EVENT_TYPE,
        "github_request_id": github_request_id,
        "dispatch_receipt": receipt,
        "continuation": "event_driven_no_polling",
        "terminal_states": ["verified_completion", "proven_human_only_blocker"],
    }


@mcp.tool(
    title="Plan Chat Branch Consolidation",
    description=(
        "Find completed or failed Chat Tree nodes that share the exact same parent group "
        "and branch lane. This is read-only and does not archive ChatGPT conversation history."
    ),
    annotations=READ_ONLY,
    structured_output=True,
)
def plan_consolidation(
    parent_id: str | None = None,
    lane_id: str | None = None,
) -> dict[str, Any]:
    args: dict[str, object] = {}
    if parent_id is not None:
        args["parent_id"] = parent_id
    if lane_id is not None:
        args["lane_id"] = lane_id
    return dispatch("plan_consolidation", args)


@mcp.tool(
    title="Consolidate and Archive Chat Tree Branch",
    description=(
        "Create one provenance-preserving checkpoint from an exact reviewed consolidation "
        "plan and archive its source Chat Tree nodes. This does not archive the underlying "
        "conversations in ChatGPT history."
    ),
    annotations=DESTRUCTIVE,
    structured_output=True,
)
def consolidate_branch(
    source_node_ids: list[str],
    plan_token: str,
    new_node_id: str,
    title: str,
    summary: str = "",
) -> dict[str, Any]:
    return dispatch(
        "consolidate_branch",
        {
            "source_node_ids": source_node_ids,
            "plan_token": plan_token,
            "new_node_id": new_node_id,
            "title": title,
            "summary": summary,
        },
    )


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
            "farmer_dispatch_ready": bool(_farmer_token()),
            "farmer_repository": FARMER_REPOSITORY,
            "farmer_event_type": FARMER_EVENT_TYPE,
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
