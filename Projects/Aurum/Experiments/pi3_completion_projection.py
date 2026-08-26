"""Project proven Pi3 kernel-canary prerequisites into Aurum completion truth.

The shared-state bus is evidence, never authority.  This projector may narrow a
completion blocker when exact compile prerequisites are proven, but it cannot mark
a kernel canary passed, grant mutation authority, or infer watchdog/recovery proof.
"""
from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any


SHARED_SCHEMA = "aurum-shared-state-v1"
PLAN_SCHEMA = "aurum-completion-plan-v1"
PREFLIGHT_SOURCE = "github-pi3-kernel-canary-preflight"
GATE_ID = "pi3-kernel-canary"


def _time(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed


def _latest_preflight(shared: dict[str, Any]) -> dict[str, Any] | None:
    if shared.get("schema") != SHARED_SCHEMA:
        raise ValueError("unsupported shared-state schema")
    subjects = shared.get("subjects")
    if not isinstance(subjects, dict):
        raise ValueError("shared-state subjects required")
    candidates = []
    for item in subjects.values():
        if not isinstance(item, dict) or item.get("source") != PREFLIGHT_SOURCE:
            continue
        try:
            timestamp = _time(item.get("timestamp"))
        except ValueError:
            continue
        candidates.append((timestamp, item))
    if not candidates:
        return None
    return max(candidates, key=lambda pair: pair[0])[1]


def _proven_compile_prerequisites(event: dict[str, Any]) -> tuple[bool, str | None, bool]:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return False, None, False
    required_true = (
        payload.get("matching_headers_present") is True,
        payload.get("module_symvers_present") is True,
        payload.get("compile_only_canary_passed") is True,
    )
    required_false = (
        payload.get("module_loaded") is False,
        payload.get("system_driver_changed") is False,
    )
    if not all(required_true) or not all(required_false):
        return False, None, False
    if payload.get("workflow_conclusion") != "success":
        return False, None, False
    kernel = payload.get("kernel")
    if not isinstance(kernel, str) or not kernel:
        return False, None, False
    watchdog = payload.get("out_of_band_watchdog_proven") is True
    return True, kernel, watchdog


def project_pi3_completion(plan: dict[str, Any], shared: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    if plan.get("schema") != PLAN_SCHEMA:
        raise ValueError("unsupported completion-plan schema")
    gates = plan.get("gates")
    if not isinstance(gates, list):
        raise ValueError("completion-plan gates required")
    event = _latest_preflight(shared)
    if event is None:
        return copy.deepcopy(plan), False
    proven, kernel, watchdog = _proven_compile_prerequisites(event)
    if not proven:
        return copy.deepcopy(plan), False

    output = copy.deepcopy(plan)
    gate = next((item for item in output["gates"] if isinstance(item, dict) and item.get("id") == GATE_ID), None)
    if gate is None:
        raise ValueError(f"missing completion gate {GATE_ID}")

    if watchdog:
        desired_state = "held-on-explicit-kernel-mutation-authority"
        proof = (
            f"physical Pi3 baseline and userspace Generation-2 recovery are proven; exact running kernel {kernel} "
            "matching headers, Module.symvers, and inert compile-only canary are proven with no module load or driver change; "
            "automatic out-of-band watchdog/recovery is proven, but fresh explicit kernel-mutation authority is still required"
        )
    else:
        desired_state = "held-on-watchdog-and-kernel-authority"
        proof = (
            f"physical Pi3 baseline and userspace Generation-2 recovery are proven; exact running kernel {kernel} "
            "matching headers, Module.symvers, and inert compile-only canary are proven with no module load or driver change; "
            "kernel mutation remains held until an automatic out-of-band watchdog/recovery path and fresh explicit kernel-mutation authority are separately proven"
        )

    changed = gate.get("state") != desired_state or gate.get("proof") != proof or gate.get("ready_now") is not False
    gate["state"] = desired_state
    gate["ready_now"] = False
    gate["proof"] = proof
    return output, changed


def write_projection(repo_root: Path) -> bool:
    plan_path = repo_root / "Projects" / "Aurum" / "completion-plan.json"
    shared_path = repo_root / "Projects" / "Aurum" / "shared-state" / "CURRENT_STATE.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    shared = json.loads(shared_path.read_text(encoding="utf-8-sig"))
    projected, changed = project_pi3_completion(plan, shared)
    if changed:
        plan_path.write_text(json.dumps(projected, indent=2) + "\n", encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    if args.write:
        changed = write_projection(root)
        print(f"AURUM_PI3_COMPLETION_PROJECTION changed={str(changed).lower()}")
        return 0
    plan = json.loads((root / "Projects" / "Aurum" / "completion-plan.json").read_text(encoding="utf-8-sig"))
    shared = json.loads((root / "Projects" / "Aurum" / "shared-state" / "CURRENT_STATE.json").read_text(encoding="utf-8-sig"))
    projected, changed = project_pi3_completion(plan, shared)
    gate = next(item for item in projected["gates"] if item.get("id") == GATE_ID)
    print(json.dumps({"changed": changed, "gate": gate}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
