#!/usr/bin/env python3
"""Reconstruct Aurum's operational truth from durable repository state only.

This intentionally does not consult chat history, external AI memory, live hardware,
or time-sensitive authorization. It proves the continuity requirement in
Projects/Aurum/STATE_AUTHORITY.md: after a restart, Aurum can recover what it is
building, what is complete/runnable/blocked, the evidence supporting that state,
the next gate, and the preserved recovery path from committed state alone.

The reconstruction is conservative. Authority-like values stored in repository
snapshots are evidence only; destructive authority always requires a live recheck.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

PATHS = {
    "completion_plan": Path("Projects/Aurum/completion-plan.json"),
    "release_handoff": Path("Projects/Aurum/Release/latest-tinyseed-handoff.json"),
    "physical_preflight": Path("Projects/Aurum/Recovery/latest-tinyseed-physical-preflight.json"),
    "future_branch": Path("Projects/Aurum/future-branches.json"),
}


class ReconstructionError(ValueError):
    """Durable state is incomplete or internally contradictory."""


def read_json(path: Path) -> dict[str, Any]:
    """Read durable JSON while tolerating a UTF-8 BOM from Windows producers.

    Aurum's canonical state can be emitted by both Linux and Windows runners.
    Windows PowerShell 5 may write ``-Encoding UTF8`` with a BOM.  That marker is
    encoding metadata, not authority-bearing content, so accepting it here keeps
    restart reconstruction portable without weakening any provenance/state gate.
    Malformed JSON still fails closed.
    """
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ReconstructionError(f"required durable state missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReconstructionError(f"invalid durable JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReconstructionError(f"durable state must be an object: {path}")
    return value


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _state_text(gate: dict[str, Any]) -> str:
    value = gate.get("state")
    return value if isinstance(value, str) else "unknown"


def gate_complete(gate: dict[str, Any]) -> bool:
    state = _state_text(gate)
    return state.startswith(("passed", "ci-passed"))


def reconstruct(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    sources = {name: root / rel for name, rel in PATHS.items()}
    plan = read_json(sources["completion_plan"])
    handoff = read_json(sources["release_handoff"])
    preflight = read_json(sources["physical_preflight"])
    future = read_json(sources["future_branch"])

    plan_release = plan.get("latest_release_source_commit")
    handoff_release = handoff.get("source_commit")
    preflight_release = preflight.get("release_source_commit")
    releases = {
        value for value in (plan_release, handoff_release, preflight_release)
        if isinstance(value, str) and value
    }
    if len(releases) != 1:
        raise ReconstructionError(
            "canonical release provenance mismatch: "
            f"plan={plan_release!r} handoff={handoff_release!r} preflight={preflight_release!r}"
        )
    release_source = next(iter(releases))

    plan_state = plan.get("release_state")
    handoff_state = handoff.get("state")
    preflight_state = preflight.get("release_state")
    release_states = {
        value for value in (plan_state, handoff_state, preflight_state)
        if isinstance(value, str) and value
    }
    if len(release_states) != 1:
        raise ReconstructionError(
            "canonical release state mismatch: "
            f"plan={plan_state!r} handoff={handoff_state!r} preflight={preflight_state!r}"
        )
    release_state = next(iter(release_states))

    gates_raw = plan.get("gates")
    if not isinstance(gates_raw, list):
        raise ReconstructionError("completion-plan gates must be an array")
    gates = [gate for gate in gates_raw if isinstance(gate, dict) and isinstance(gate.get("id"), str)]
    by_id = {gate["id"]: gate for gate in gates}
    if len(by_id) != len(gates):
        raise ReconstructionError("completion-plan gate ids must be unique")

    completed: list[dict[str, Any]] = []
    runnable: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for gate in gates:
        gate_id = gate["id"]
        state = _state_text(gate)
        deps = gate.get("depends_on") if isinstance(gate.get("depends_on"), list) else []
        missing_deps = [dep for dep in deps if dep not in by_id]
        if missing_deps:
            raise ReconstructionError(f"gate {gate_id} references unknown dependencies: {missing_deps}")
        unmet = [dep for dep in deps if not gate_complete(by_id[dep])]
        record = {
            "id": gate_id,
            "lane": gate.get("lane"),
            "state": state,
            "proof": gate.get("proof"),
            "depends_on": deps,
        }
        if gate_complete(gate):
            completed.append(record)
        elif bool(gate.get("ready_now")) and not unmet:
            runnable.append(record)
        else:
            record["unmet_dependencies"] = unmet
            blocked.append(record)

    next_gate = preflight.get("next_gate")
    if not isinstance(next_gate, str) or not next_gate:
        raise ReconstructionError("physical preflight next_gate missing")

    canonical = future.get("canonical_evidence")
    canonical = canonical if isinstance(canonical, dict) else {}
    fallback = canonical.get("fallback_carrier")
    fallback = fallback if isinstance(fallback, dict) else {}
    usb = preflight.get("usb_candidate")
    usb = usb if isinstance(usb, dict) else {}
    recovery = preflight.get("preexecution_recovery")
    recovery = recovery if isinstance(recovery, dict) else {}
    authorization = preflight.get("authorization")
    authorization = authorization if isinstance(authorization, dict) else {}

    top_inputs = future.get("likely_user_inputs")
    top_inputs = top_inputs if isinstance(top_inputs, list) else []
    top_machines = future.get("likely_machine_outcomes")
    top_machines = top_machines if isinstance(top_machines, list) else []

    next_branch = next((item for item in top_machines if isinstance(item, dict)), None)
    next_input = next((item for item in top_inputs if isinstance(item, dict)), None)

    source_digests = {
        name: {
            "path": str(path.relative_to(root)).replace("\\", "/"),
            "sha256": file_digest(path),
        }
        for name, path in sources.items()
    }

    physical_boot = bool(preflight.get("physical_boot_proven"))
    guardian_rollback = bool(preflight.get("guardian_forced_rollback_proven"))

    result = {
        "schema": "aurum-restart-reconstruction-v1",
        "mode": "durable-repository-state-only",
        "release": {
            "state": release_state,
            "source_commit": release_source,
            "x86_artifact": handoff.get("artifacts", {}).get("x86", {}).get("name")
            if isinstance(handoff.get("artifacts"), dict) else None,
            "x86_sha256": preflight.get("x86_sha256"),
        },
        "answers": {
            "what_am_i_building": plan.get("goal"),
            "what_is_already_complete": completed,
            "what_is_running_or_runnable": {
                "running": [],
                "running_truth": "No live process is inferred from repository state; only dependency-satisfied runnable work is reported.",
                "runnable": runnable,
            },
            "what_is_blocked": blocked,
            "what_evidence_supports_this_state": {
                "source_files": source_digests,
                "release_handoff_state": handoff_state,
                "release_gates": handoff.get("gates"),
                "physical_preflight_state": preflight.get("preflight_state"),
                "usb_candidate": {
                    "present": bool(usb),
                    "model": usb.get("model"),
                    "size_bytes": usb.get("size_bytes"),
                    "serial_sha256": usb.get("serial_sha256"),
                    "protected": usb.get("protected"),
                    "is_boot": usb.get("is_boot"),
                    "is_system": usb.get("is_system"),
                },
                "physical_boot_proven": physical_boot,
                "guardian_forced_rollback_proven": guardian_rollback,
            },
            "what_should_execute_next": {
                "canonical_next_gate": next_gate,
                "top_machine_branch": next_branch,
                "top_likely_human_input": next_input,
                "human_or_destructive_boundary": next_gate.startswith("explicit-") or "physical" in next_gate,
            },
            "what_recovery_or_fallback_exists": {
                "last_known_good_invariant": "no-new-state-may-destroy-last-proven-state",
                "preexecution_recovery": {
                    "terminal_receipt_present": recovery.get("terminal_receipt_present"),
                    "remote_repair": recovery.get("remote_repair"),
                    "terminal_reason": recovery.get("terminal_reason"),
                    "manual_handoff_released": recovery.get("manual_handoff_released"),
                },
                "guardian_forced_rollback_proven": guardian_rollback,
                "fallback_carrier": {
                    "warm_current": fallback.get("warm_current"),
                    "canonical_payload_match": fallback.get("canonical_payload_match"),
                    "physical_proof_inferred": False,
                    "authority_granted": False,
                },
            },
        },
        "authority": {
            "repository_authorization_snapshot": authorization.get("authorization_state"),
            "snapshot_write_authority": bool(preflight.get("write_authority")),
            "snapshot_destructive_action_allowed": bool(preflight.get("destructive_action_allowed")),
            "authority_snapshot_authoritative": False,
            "live_recheck_required": True,
            "authority_granted": False,
        },
        "physical_proof_inferred": False,
        "lkg_mutation_allowed": False,
    }
    return result


def main() -> None:
    print(json.dumps(reconstruct(), indent=2, sort_keys=False))


if __name__ == "__main__":
    main()
