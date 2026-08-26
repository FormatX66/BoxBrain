"""Small JSON bridge for GPT/Future Branch/runners to share one Chat Tree state.

Usage examples (one JSON request on stdin):

    {"command":"get_tree"}
    {"command":"get_state"}
    {"command":"route_topic","current_id":"chat-tree","new_node_id":"pi3-tests",
     "title":"Pi3 adaptive driver tests","objective":"Boot and test the Pi3",
     "concepts":["adaptive-kernel"],"relation_hint":"new"}
    {"command":"post_receipt","subject_id":"pi3","subject_kind":"device",
     "status":"running_verified","actor":"pi3-runner","source":"usb-probe",
     "evidence_refs":["artifact:pi3-probe-123"]}

The bridge is intentionally transport-neutral. A ChatGPT App/MCP tool, local
agent, GitHub runner, or BoxBrain process can wrap the same commands later.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Mapping

from chat_process_tree import ChatProcessTree
from chat_topic_router import TopicSignal, route_into_tree
from shared_state_bus import SharedStateBus, StateEvent


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TREE = ROOT / "Projects" / "Aurum" / "chat-process-tree.json"
DEFAULT_EVENTS = ROOT / "Projects" / "Aurum" / "shared-state" / "events.jsonl"
DEFAULT_PROJECTION = ROOT / "Projects" / "Aurum" / "shared-state" / "CURRENT_STATE.json"


class BridgeError(ValueError):
    pass


def _load_tree(path: Path) -> ChatProcessTree:
    return ChatProcessTree.from_json(path.read_text(encoding="utf-8"))


def _write_tree(path: Path, tree: ChatProcessTree, focus_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tree.to_json(focus_id=focus_id), encoding="utf-8")


def _load_bus(path: Path) -> SharedStateBus:
    return SharedStateBus.load(path)


def _write_projection(path: Path, bus: SharedStateBus) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(bus.to_projection_json(), encoding="utf-8")


def _require(request: Mapping[str, object], key: str) -> object:
    if key not in request:
        raise BridgeError(f"missing required field: {key}")
    return request[key]


def handle_request(
    request: Mapping[str, object],
    *,
    tree_path: Path = DEFAULT_TREE,
    events_path: Path = DEFAULT_EVENTS,
    projection_path: Path = DEFAULT_PROJECTION,
) -> dict[str, object]:
    command = str(_require(request, "command"))

    if command == "get_tree":
        tree = _load_tree(tree_path)
        focus_id = str(request.get("focus_id") or tree.root_id)
        return {"ok": True, "command": command, "tree": tree.to_dict(focus_id=focus_id)}

    if command == "get_state":
        bus = _load_bus(events_path)
        return {"ok": True, "command": command, "state": bus.to_projection_dict()}

    if command == "route_topic":
        tree = _load_tree(tree_path)
        concepts = tuple(str(item) for item in request.get("concepts", ()) or ())
        signal = TopicSignal(
            title=str(_require(request, "title")),
            objective=str(_require(request, "objective")),
            concepts=concepts,
            relation_hint=str(request.get("relation_hint", "unknown")),
        )
        changed, decision, focus_id = route_into_tree(
            tree,
            current_id=str(_require(request, "current_id")),
            new_node_id=str(_require(request, "new_node_id")),
            incoming=signal,
            summary=str(request.get("summary", "")),
            evidence_refs=tuple(str(item) for item in request.get("evidence_refs", ()) or ()),
        )
        if changed is not tree:
            _write_tree(tree_path, changed, focus_id)
        return {
            "ok": True,
            "command": command,
            "route": decision.route,
            "confidence": decision.confidence,
            "reason_codes": list(decision.reason_codes),
            "overlap": decision.overlap,
            "focus_id": focus_id,
            "tree_changed": changed is not tree,
        }

    if command == "post_receipt":
        bus = _load_bus(events_path)
        event = StateEvent(
            subject_id=str(_require(request, "subject_id")),
            subject_kind=str(_require(request, "subject_kind")),
            status=str(_require(request, "status")),
            actor=str(_require(request, "actor")),
            source=str(_require(request, "source")),
            node_id=None if request.get("node_id") is None else str(request["node_id"]),
            summary=str(request.get("summary", "")),
            evidence_refs=tuple(str(item) for item in request.get("evidence_refs", ()) or ()),
            dependency_ids=tuple(str(item) for item in request.get("dependency_ids", ()) or ()),
            confidence=None if request.get("confidence") is None else float(request["confidence"]),
            authority_ref=None if request.get("authority_ref") is None else str(request["authority_ref"]),
            payload=dict(request.get("payload", {}) or {}),
        )
        bus.append_file(events_path, event)
        _write_projection(projection_path, bus)
        return {
            "ok": True,
            "command": command,
            "event": event.to_dict(),
            "state": bus.latest(event.subject_id).to_dict(),
        }

    raise BridgeError(f"unknown command: {command}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--projection", type=Path, default=DEFAULT_PROJECTION)
    args = parser.parse_args(argv)

    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise BridgeError("request must be a JSON object")
        response = handle_request(
            request,
            tree_path=args.tree,
            events_path=args.events,
            projection_path=args.projection,
        )
        json.dump(response, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    except Exception as exc:  # CLI boundary: return structured failure to callers.
        json.dump(
            {"ok": False, "error": type(exc).__name__, "message": str(exc)},
            sys.stdout,
            indent=2,
            sort_keys=True,
        )
        sys.stdout.write("\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
