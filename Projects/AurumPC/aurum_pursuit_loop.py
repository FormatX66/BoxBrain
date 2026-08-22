#!/usr/bin/env python3
"""Persistent adaptive pursuit loop for Aurum.

A failed path is evidence, not a stop condition.

This module repeatedly:
  1. refreshes a capability field,
  2. ranks paths through the autonomy envelope,
  3. chooses an already-authorized bounded actuator,
  4. records the measured result,
  5. updates path history,
  6. replans until the desired state is reached or a real boundary is hit.

The loop never provides arbitrary command execution. Physical effects must be
implemented by a separately registered bounded actuator. The pursuit engine
only selects among those registered capabilities.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from aurum_autonomy_runtime import (
    AUTO,
    DENY,
    ESCALATE,
    default_envelope,
    empty_history,
    plan_with_envelope,
    record_receipt,
)

PURSUIT_SCHEMA = "aurum.adaptive-pursuit.v1"
CHECKPOINT_SCHEMA = "aurum.adaptive-pursuit-checkpoint.v1"

ACTIVE = "ACTIVE"
SUCCEEDED = "SUCCEEDED"
BOUNDARY = "BOUNDARY"
EXHAUSTED = "EXHAUSTED"
PAUSED = "PAUSED"

DEFAULT_CHECKPOINT = Path(
    os.environ.get("AURUM_PURSUIT_CHECKPOINT", "/var/lib/aurum/state/pursuit-checkpoint.json")
)

GraphProvider = Callable[[], dict[str, Any]]
Actuator = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
GoalCheck = Callable[[dict[str, Any]], bool]


def default_policy() -> dict[str, Any]:
    return {
        "max_total_attempts": 64,
        "max_attempts_per_path": 4,
        "refresh_mesh_every_attempts": 1,
        "failure_backoff_base_ms": 250,
        "failure_backoff_cap_ms": 8000,
        "stop_on_boundary": True,
        "rotate_after_failure": True,
        "success_requires_goal_check_when_provided": True,
        "principle": "failure improves the map; it does not end the pursuit",
    }


def new_checkpoint(intent: dict[str, Any], *, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema": CHECKPOINT_SCHEMA,
        "created_at": _now(),
        "updated_at": _now(),
        "status": ACTIVE,
        "intent": intent,
        "policy": policy or default_policy(),
        "attempts": 0,
        "path_attempts": {},
        "path_failures": {},
        "last_node_id": None,
        "last_decision": None,
        "last_receipt": None,
        "boundary": None,
        "goal_observed": False,
        "next_backoff_ms": 0,
    }


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _path_key(candidate: dict[str, Any], intent: dict[str, Any]) -> str:
    return f"{intent.get('action_class') or 'observe'}|{candidate.get('node_id')}"


def _bounded_candidates(
    decision: dict[str, Any], checkpoint: dict[str, Any]
) -> list[dict[str, Any]]:
    policy = checkpoint.get("policy") or default_policy()
    per_path_limit = int(policy.get("max_attempts_per_path") or 1)
    attempts = checkpoint.get("path_attempts") or {}
    intent = checkpoint.get("intent") or {}

    eligible: list[dict[str, Any]] = []
    for candidate in decision.get("candidates") or []:
        if (candidate.get("policy") or {}).get("decision") != AUTO:
            continue
        key = _path_key(candidate, intent)
        if int(attempts.get(key) or 0) >= per_path_limit:
            continue
        eligible.append(candidate)

    if not eligible:
        return []

    if policy.get("rotate_after_failure", True):
        last_node = checkpoint.get("last_node_id")
        last_receipt = checkpoint.get("last_receipt") or {}
        if last_node and not last_receipt.get("success") and len(eligible) > 1:
            different = [item for item in eligible if item.get("node_id") != last_node]
            same = [item for item in eligible if item.get("node_id") == last_node]
            eligible = different + same
    return eligible


def _backoff_ms(checkpoint: dict[str, Any], key: str) -> int:
    policy = checkpoint.get("policy") or default_policy()
    failures = int((checkpoint.get("path_failures") or {}).get(key) or 0)
    if failures <= 0:
        return 0
    base = int(policy.get("failure_backoff_base_ms") or 0)
    cap = int(policy.get("failure_backoff_cap_ms") or base)
    return min(cap, base * (2 ** max(0, failures - 1)))


def _normalize_receipt(
    raw: dict[str, Any],
    candidate: dict[str, Any],
    intent: dict[str, Any],
    *,
    started_ns: int,
    finished_ns: int,
) -> dict[str, Any]:
    receipt = dict(raw or {})
    node_id = str(candidate.get("node_id") or "")
    receipt.setdefault("node_id", node_id)
    if receipt.get("node_id") != node_id:
        raise ValueError("actuator receipt node_id does not match selected candidate")
    receipt.setdefault("action_class", str(intent.get("action_class") or "observe"))
    receipt.setdefault("observed_at", _now())
    receipt.setdefault("success", False)
    receipt.setdefault("execution_ms", round((finished_ns - started_ns) / 1_000_000, 3))
    receipt.setdefault("queue_delay_ms", 0.0)
    receipt.setdefault("latency_ms", receipt.get("execution_ms"))
    receipt.setdefault("bounded_actuator", True)
    return receipt


def pursuit_step(
    mesh: dict[str, Any],
    checkpoint: dict[str, Any],
    actuator: Actuator,
    *,
    envelope: dict[str, Any] | None = None,
    history: dict[str, Any] | None = None,
    goal_check: GoalCheck | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    """Perform one bounded pursuit step.

    Returns (checkpoint, history, receipt). A receipt is None when no actuator
    ran because the goal was already satisfied or a boundary/exhaustion state
    was reached.
    """
    envelope = envelope or default_envelope()
    history = history or empty_history()
    intent = checkpoint.get("intent") or {}
    policy = checkpoint.get("policy") or default_policy()

    if checkpoint.get("status") != ACTIVE:
        return checkpoint, history, None

    if goal_check is not None and goal_check(intent):
        checkpoint["status"] = SUCCEEDED
        checkpoint["goal_observed"] = True
        checkpoint["updated_at"] = _now()
        return checkpoint, history, None

    if int(checkpoint.get("attempts") or 0) >= int(policy.get("max_total_attempts") or 1):
        checkpoint["status"] = EXHAUSTED
        checkpoint["updated_at"] = _now()
        checkpoint["last_decision"] = "attempt-budget-exhausted"
        return checkpoint, history, None

    decision = plan_with_envelope(mesh, intent, envelope=envelope, history=history)
    checkpoint["last_decision"] = decision.get("decision")

    eligible = _bounded_candidates(decision, checkpoint)
    if not eligible:
        escalation = decision.get("escalation_candidate")
        if escalation:
            checkpoint["status"] = BOUNDARY
            checkpoint["boundary"] = {
                "candidate": escalation,
                "reason": (escalation.get("policy") or {}).get("reasons") or ["boundary-change"],
            }
        else:
            denied = [
                item for item in decision.get("candidates") or []
                if (item.get("policy") or {}).get("decision") == DENY
            ]
            checkpoint["status"] = EXHAUSTED
            checkpoint["boundary"] = {
                "reason": ["no-auto-path-remains"],
                "denied_candidates": len(denied),
            }
        checkpoint["updated_at"] = _now()
        return checkpoint, history, None

    candidate = eligible[0]
    key = _path_key(candidate, intent)
    path_attempts = checkpoint.setdefault("path_attempts", {})
    path_attempts[key] = int(path_attempts.get(key) or 0) + 1
    checkpoint["attempts"] = int(checkpoint.get("attempts") or 0) + 1
    checkpoint["last_node_id"] = candidate.get("node_id")

    started_ns = time.monotonic_ns()
    try:
        raw_receipt = actuator(candidate, intent)
    except Exception as exc:  # bounded actuator failure becomes evidence, not fatal loop termination
        raw_receipt = {
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    finished_ns = time.monotonic_ns()

    receipt = _normalize_receipt(raw_receipt, candidate, intent, started_ns=started_ns, finished_ns=finished_ns)
    checkpoint["last_receipt"] = receipt
    history = record_receipt(history, receipt)

    if receipt.get("success"):
        if goal_check is None:
            checkpoint["status"] = SUCCEEDED
            checkpoint["goal_observed"] = True
        elif goal_check(intent):
            checkpoint["status"] = SUCCEEDED
            checkpoint["goal_observed"] = True
        elif not policy.get("success_requires_goal_check_when_provided", True):
            checkpoint["status"] = SUCCEEDED
    else:
        path_failures = checkpoint.setdefault("path_failures", {})
        path_failures[key] = int(path_failures.get(key) or 0) + 1

    checkpoint["next_backoff_ms"] = 0 if receipt.get("success") else _backoff_ms(checkpoint, key)
    checkpoint["updated_at"] = _now()
    return checkpoint, history, receipt


def pursue(
    graph_provider: GraphProvider,
    intent: dict[str, Any],
    actuator: Actuator,
    *,
    envelope: dict[str, Any] | None = None,
    history: dict[str, Any] | None = None,
    checkpoint: dict[str, Any] | None = None,
    goal_check: GoalCheck | None = None,
    max_cycles: int | None = None,
    sleep_between_failures: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Keep adapting until success, a real boundary, or bounded exhaustion."""
    checkpoint = checkpoint or new_checkpoint(intent)
    history = history or empty_history()
    cycles = 0
    mesh: dict[str, Any] | None = None

    while checkpoint.get("status") == ACTIVE:
        if max_cycles is not None and cycles >= max_cycles:
            checkpoint["status"] = PAUSED
            checkpoint["updated_at"] = _now()
            break

        refresh_every = max(1, int((checkpoint.get("policy") or {}).get("refresh_mesh_every_attempts") or 1))
        if mesh is None or cycles % refresh_every == 0:
            mesh = graph_provider()

        checkpoint, history, receipt = pursuit_step(
            mesh,
            checkpoint,
            actuator,
            envelope=envelope,
            history=history,
            goal_check=goal_check,
        )
        cycles += 1

        if (
            sleep_between_failures
            and checkpoint.get("status") == ACTIVE
            and receipt is not None
            and not receipt.get("success")
        ):
            time.sleep(max(0, int(checkpoint.get("next_backoff_ms") or 0)) / 1000.0)

    return checkpoint, history


def _load_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback
    return payload if isinstance(payload, dict) else fallback


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Aurum persistent adaptive pursuit loop")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--intent", type=Path, required=True)
    init.add_argument("--out", type=Path, default=DEFAULT_CHECKPOINT)

    inspect = sub.add_parser("inspect")
    inspect.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)

    args = parser.parse_args()
    if args.command == "init":
        intent = _load_json(args.intent, {})
        if not intent:
            raise SystemExit("intent is empty or unreadable")
        checkpoint = new_checkpoint(intent)
        _atomic_json(args.out, checkpoint)
        print(json.dumps(checkpoint, indent=2, sort_keys=True))
        return 0

    checkpoint = _load_json(args.checkpoint, {})
    if not checkpoint:
        raise SystemExit("checkpoint is empty or unreadable")
    print(json.dumps(checkpoint, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
