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
    {"command":"publish_live_state","subject_id":"chat-123","status":"blocked",
     "current_action":"Verify the runner","blocker":"runner offline",
     "evidence":["log:runner-probe-123"],"next_action":"Retry after recovery",
     "actor":"chat-123","source":"chatgpt-conversation:chat-123"}
    {"command":"read_live_state","subject_id":"chat-123","include_history":true}
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
from shared_state_bus import SharedStateBus, StateEvent, SubjectState, VERIFIED_STATUSES


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
    return SharedStateBus.load_consistent(path)


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


def _string_list(
    request: Mapping[str, object],
    key: str,
    *,
    required: bool = False,
) -> list[str]:
    raw = _require(request, key) if required else request.get(key, ())
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise BridgeError(f"{key} must be a list")
    if any(not isinstance(item, str) for item in raw):
        raise BridgeError(f"{key} entries must be strings")
    values = [item.strip() for item in raw]
    if any(not item for item in values):
        raise BridgeError(f"{key} entries must be non-empty")
    return list(dict.fromkeys(values))


def _required_text(request: Mapping[str, object], key: str) -> str:
    raw = _require(request, key)
    if not isinstance(raw, str):
        raise BridgeError(f"{key} must be a string")
    value = raw.strip()
    if not value:
        raise BridgeError(f"{key} must be non-empty")
    return value


def _optional_text(request: Mapping[str, object], key: str) -> str | None:
    value = request.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise BridgeError(f"{key} must be a string or null")
    text = value.strip()
    return text or None


def _request_bool(request: Mapping[str, object], key: str, default: bool = False) -> bool:
    value = request.get(key, default)
    if not isinstance(value, bool):
        raise BridgeError(f"{key} must be boolean")
    return value


def _payload(request: Mapping[str, object]) -> dict[str, object]:
    raw = request.get("payload", {}) or {}
    if not isinstance(raw, Mapping):
        raise BridgeError("payload must be an object")
    return dict(raw)


def _live_state_view(state: SubjectState) -> dict[str, object]:
    payload = dict(state.payload)
    return {
        "subject_id": state.subject_id,
        "subject_kind": state.subject_kind,
        "status": state.status,
        "current_action": payload.get("current_action"),
        "blocker": payload.get("blocker"),
        "evidence": list(state.evidence_refs),
        "next_action": payload.get("next_action"),
        "actor": state.actor,
        "source": state.source,
        "event_id": state.event_id,
        "timestamp": state.timestamp,
        "node_id": state.node_id,
        "summary": state.summary,
        "dependency_ids": list(state.dependency_ids),
        "confidence": state.confidence,
        "authority_ref": state.authority_ref,
        "verified_runtime": state.status in VERIFIED_STATUSES,
        "grants_execution_authority": False,
        "payload": payload,
    }


def _append_event(
    bus: SharedStateBus,
    event: StateEvent,
    *,
    events_path: Path,
    projection_path: Path,
) -> SubjectState:
    bus.append_file(events_path, event, projection_path=projection_path)
    latest = bus.latest(event.subject_id)
    if latest is None:  # Defensive: an accepted append must project its subject.
        raise BridgeError("accepted event was not projected")
    return latest


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
        return {
            "ok": True,
            "command": command,
            "state": bus.to_projection_dict(),
            "authority_granted": False,
            "chat_memory_used_as_source": False,
        }

    if command == "read_live_state":
        bus = _load_bus(events_path)
        subject_id = _optional_text(request, "subject_id")
        node_id = _optional_text(request, "node_id")
        verified_only = _request_bool(request, "verified_only")
        include_history = _request_bool(request, "include_history")
        limit = int(request.get("limit", 50))
        if not 1 <= limit <= 500:
            raise BridgeError("limit must be between 1 and 500")

        states = []
        for state in bus.projection().values():
            if subject_id is not None and state.subject_id != subject_id:
                continue
            if node_id is not None and state.node_id != node_id:
                continue
            if verified_only and state.status not in VERIFIED_STATUSES:
                continue
            states.append(state)
        states.sort(key=lambda item: (item.timestamp, item.event_id), reverse=True)
        states = states[:limit]

        history: list[dict[str, object]] = []
        if include_history:
            for event in reversed(bus.events):
                if subject_id is not None and event.subject_id != subject_id:
                    continue
                if node_id is not None and event.node_id != node_id:
                    continue
                if verified_only and event.status not in VERIFIED_STATUSES:
                    continue
                history.append(event.to_dict())
                if len(history) >= limit:
                    break

        return {
            "ok": True,
            "command": command,
            "live_state": {
                "subjects": {
                    state.subject_id: _live_state_view(state) for state in states
                },
                "events": history,
                "event_count": len(bus.events),
                "matched_subject_count": len(states),
                "history_newest_first": True,
                "source_of_truth": "append-only-shared-state-bus",
            },
            "invariants": bus.to_projection_dict()["invariants"],
            "authority_granted": False,
            "chat_memory_used_as_source": False,
        }

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
        event_kwargs: dict[str, object] = {}
        if request.get("event_id") is not None:
            event_kwargs["event_id"] = str(request["event_id"])
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
            payload=_payload(request),
            **event_kwargs,
        )
        latest = _append_event(
            bus,
            event,
            events_path=events_path,
            projection_path=projection_path,
        )
        return {
            "ok": True,
            "command": command,
            "event": event.to_dict(),
            "state": latest.to_dict(),
            "authority_granted": False,
            "chat_memory_used_as_source": False,
        }

    if command == "publish_live_state":
        bus = _load_bus(events_path)
        evidence = _string_list(request, "evidence", required=True)
        payload = _payload(request)
        payload.update(
            {
                "current_action": _required_text(request, "current_action"),
                "blocker": _optional_text(request, "blocker"),
                "next_action": _required_text(request, "next_action"),
            }
        )
        event_kwargs: dict[str, object] = {}
        if request.get("event_id") is not None:
            event_kwargs["event_id"] = str(request["event_id"])
        event = StateEvent(
            subject_id=_required_text(request, "subject_id"),
            subject_kind=_optional_text(request, "subject_kind") or "chat",
            status=_required_text(request, "status"),
            actor=_required_text(request, "actor"),
            source=_required_text(request, "source"),
            node_id=_optional_text(request, "node_id"),
            summary=str(request.get("summary", "")),
            evidence_refs=tuple(evidence),
            dependency_ids=tuple(_string_list(request, "dependency_ids")),
            confidence=None if request.get("confidence") is None else float(request["confidence"]),
            authority_ref=_optional_text(request, "authority_ref"),
            payload=payload,
            **event_kwargs,
        )
        latest = _append_event(
            bus,
            event,
            events_path=events_path,
            projection_path=projection_path,
        )
        return {
            "ok": True,
            "command": command,
            "event": event.to_dict(),
            "live_state": _live_state_view(latest),
            "event_count": len(bus.events),
            "authority_granted": False,
            "chat_memory_used_as_source": False,
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
