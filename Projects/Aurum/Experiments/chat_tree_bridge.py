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
    {"command":"project_human_futures","verified_state":"READY_TO_BOOT",
     "likely_next":[{"state":"physical-hopper-boot","probability":0.75}]}
    {"command":"plan_operational_futures","verified_state":"ci-green",
     "candidates":[{"name":"inspect-logs","domain":"ci-build","probability":0.8,
     "impact":0.8,"human_time_saved":2,"preparation_leverage":1,"cost":0.2,
     "read_only":true}]}

The bridge is intentionally transport-neutral. A ChatGPT App/MCP tool, local
agent, GitHub runner, or BoxBrain process can wrap the same commands later.
Future Branch projections are advisory and side-effect free: likely intent or a
ranked operational path never becomes authority or physical proof.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Mapping

from chat_process_tree import ChatProcessTree
from chat_topic_router import TopicSignal, route_into_tree
from human_branch import status_projection
from operational_branch import WorkflowCandidate, WorkflowDomain, operational_plan
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


def _mapping_list(request: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    raw = _require(request, key)
    if not isinstance(raw, list):
        raise BridgeError(f"{key} must be a list")
    values: list[Mapping[str, object]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise BridgeError(f"{key}[{index}] must be an object")
        values.append(item)
    return values


def _bool_field(item: Mapping[str, object], key: str, default: bool) -> bool:
    value = item.get(key, default)
    if not isinstance(value, bool):
        raise BridgeError(f"{key} must be boolean")
    return value


def _workflow_candidate(item: Mapping[str, object]) -> WorkflowCandidate:
    allowed = {
        "name",
        "domain",
        "probability",
        "impact",
        "human_time_saved",
        "preparation_leverage",
        "cost",
        "evidence_freshness",
        "read_only",
        "reversible",
        "external_side_effect",
        "authorization_required",
        "rollback_prepared",
        "preserves_verified_state",
        "unchanged_retry",
        "retry_after_seconds",
        "trust_broadening",
        "alternate_authorized_route",
    }
    unknown = sorted(set(item) - allowed)
    if unknown:
        raise BridgeError(f"unknown operational candidate fields: {', '.join(unknown)}")
    return WorkflowCandidate(
        name=str(_require(item, "name")),
        domain=WorkflowDomain(str(_require(item, "domain"))),
        probability=float(_require(item, "probability")),
        impact=float(_require(item, "impact")),
        human_time_saved=float(_require(item, "human_time_saved")),
        preparation_leverage=float(_require(item, "preparation_leverage")),
        cost=float(_require(item, "cost")),
        evidence_freshness=float(item.get("evidence_freshness", 1.0)),
        read_only=_bool_field(item, "read_only", False),
        reversible=_bool_field(item, "reversible", False),
        external_side_effect=_bool_field(item, "external_side_effect", False),
        authorization_required=_bool_field(item, "authorization_required", False),
        rollback_prepared=_bool_field(item, "rollback_prepared", False),
        preserves_verified_state=_bool_field(item, "preserves_verified_state", True),
        unchanged_retry=_bool_field(item, "unchanged_retry", False),
        retry_after_seconds=int(item.get("retry_after_seconds", 0)),
        trust_broadening=_bool_field(item, "trust_broadening", False),
        alternate_authorized_route=_bool_field(item, "alternate_authorized_route", False),
    )


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

    if command == "project_human_futures":
        futures = []
        for item in _mapping_list(request, "likely_next"):
            state = str(item.get("state") or item.get("name") or "")
            if not state:
                raise BridgeError("human future state required")
            futures.append((state, float(_require(item, "probability"))))
        blockers_raw = request.get("blockers", ()) or ()
        if not isinstance(blockers_raw, (list, tuple)):
            raise BridgeError("blockers must be a list")
        lkg_raw = request.get("lkg")
        projection = status_projection(
            verified_state=str(_require(request, "verified_state")),
            likely_next=futures,
            lkg=None if lkg_raw is None else str(lkg_raw),
            blockers=(str(item) for item in blockers_raw),
        )
        return {
            "ok": True,
            "command": command,
            "projection": projection,
            "authority_granted": False,
            "physical_proof_inferred": False,
            "side_effects_performed": False,
        }

    if command == "plan_operational_futures":
        candidates = [_workflow_candidate(item) for item in _mapping_list(request, "candidates")]
        plan = operational_plan(
            candidates,
            verified_state=str(_require(request, "verified_state")),
            limit=int(request.get("limit", 8)),
        )
        return {
            "ok": True,
            "command": command,
            "plan": plan,
            "authority_granted": False,
            "side_effects_performed": False,
        }

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
