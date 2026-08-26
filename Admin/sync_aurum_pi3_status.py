"""Project verified experimental Pi3 evidence into the Aurum completion graph.

This projector is intentionally zero-authority. It can remove stale claims that the
experimental Pi3 hardware is unavailable and can record already-proven userspace
milestones, but it can never grant kernel/firmware mutation authority or infer a
kernel-module canary from userspace evidence.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN_RELATIVE = Path("Projects/Aurum/completion-plan.json")
GEN2_RELATIVE = Path("Projects/AdaptiveDrivers/evidence/pi3-generation2-physical.json")
KERNEL_PREFLIGHT_RELATIVE = Path("Projects/AdaptiveDrivers/evidence/pi3-kernel-canary-preflight.json")

GEN2_SCHEMA = "aurum.pi3.adaptive-driver.generation2.physical.v1"
KERNEL_PREFLIGHT_SCHEMA = "aurum.pi3.kernel-canary.preflight.v1"
PINNED_SERIAL = "00000000a6a7df7f"


class Pi3StatusError(ValueError):
    """Raised when Pi3 evidence cannot safely support a completion-plan projection."""


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Pi3StatusError(f"cannot read valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise Pi3StatusError(f"expected JSON object: {path}")
    return value


def _gates(plan: dict) -> list[dict]:
    gates = plan.get("gates")
    if not isinstance(gates, list):
        raise Pi3StatusError("completion-plan gates must be an array")
    if not all(isinstance(item, dict) for item in gates):
        raise Pi3StatusError("completion-plan gates must contain objects")
    return gates


def _gate(plan: dict, gate_id: str) -> dict | None:
    for item in _gates(plan):
        if item.get("id") == gate_id:
            return item
    return None


def _upsert_before(plan: dict, gate: dict, *, before_id: str) -> dict:
    gates = _gates(plan)
    existing = _gate(plan, str(gate["id"]))
    if existing is not None:
        existing.clear()
        existing.update(gate)
        return existing
    index = next((i for i, item in enumerate(gates) if item.get("id") == before_id), len(gates))
    gates.insert(index, gate)
    return gate


def _validate_generation2(evidence: dict) -> None:
    if evidence.get("schema") != GEN2_SCHEMA:
        raise Pi3StatusError("unexpected Pi3 generation-2 evidence schema")
    if evidence.get("state") != "passed-physical-userspace-generation2":
        raise Pi3StatusError("Pi3 generation-2 evidence is not physically passed")

    target = evidence.get("target")
    generation2 = evidence.get("generation2")
    fault = evidence.get("fault_injection")
    rollback = evidence.get("isolated_metadata_rollback")
    safety = evidence.get("safety")
    if not all(isinstance(item, dict) for item in (target, generation2, fault, rollback, safety)):
        raise Pi3StatusError("Pi3 generation-2 evidence is structurally incomplete")

    if target.get("serial") != PINNED_SERIAL or target.get("strict_key_only_ssh") is not True:
        raise Pi3StatusError("Pi3 generation-2 target identity is not the pinned experiment")
    if (
        generation2.get("candidate_id") != "pi3-net-sysfs-tolerant-v2"
        or generation2.get("generation") != 2
        or generation2.get("decision") != "promoted"
        or generation2.get("read_evidence_complete") is not True
        or generation2.get("lkg_preserved_during_test") is not True
    ):
        raise Pi3StatusError("Pi3 generation-2 promotion evidence is incomplete")
    score = generation2.get("score")
    if not isinstance(score, (int, float)) or score < 100.0:
        raise Pi3StatusError("Pi3 generation-2 score is below the proven reference match")

    if (
        fault.get("candidate_id") != "pi3-net-sysfs-tolerant-v2-missing-field-fixture"
        or fault.get("decision") != "quarantined"
        or fault.get("reason") != "required-read-only-field-unavailable"
        or fault.get("lkg_preserved_during_test") is not True
        or fault.get("missing_fields") != ["carrier"]
        or fault.get("lkg_sha256_before") != fault.get("lkg_sha256_after")
    ):
        raise Pi3StatusError("Pi3 generation-2 fault quarantine/LKG proof is incomplete")
    if rollback.get("passed") is not True or rollback.get("restored_profile_id") != "pi3-linux-reference-driver":
        raise Pi3StatusError("Pi3 generation-2 isolated rollback proof is incomplete")

    forbidden_true = (
        "system_driver_changed",
        "kernel_module_loaded",
        "kernel_driver_binding_changed",
        "firmware_mutation_allowed",
        "kernel_driver_mutation_allowed",
        "production_nodes_allowed",
        "persistent_trust_changed",
    )
    if any(safety.get(key) is not False for key in forbidden_true):
        raise Pi3StatusError("Pi3 generation-2 evidence crosses the userspace safety boundary")


def _project_generation2(plan: dict, evidence: dict) -> None:
    _validate_generation2(evidence)
    _upsert_before(
        plan,
        {
            "id": "pi3-physical-baseline",
            "lane": "physical-experiment",
            "depends_on": [],
            "state": "passed-physical-experiment",
            "ready_now": True,
            "proof": "pinned experimental Pi3 identity, exact current-card rollback image/archive, and post-backup physical reboot canary are proven",
        },
        before_id="pi3-kernel-canary",
    )
    _upsert_before(
        plan,
        {
            "id": "pi3-adaptive-driver-userspace-generation2",
            "lane": "physical-experiment",
            "depends_on": ["pi3-physical-baseline"],
            "state": "passed-physical-experiment",
            "ready_now": True,
            "proof": "generation-2 read-only userspace driver observer matched reference behavior, missing-field fault quarantined with byte-identical LKG metadata, and isolated metadata rollback restored the Linux reference profile",
        },
        before_id="pi3-kernel-canary",
    )

    kernel_gate = _gate(plan, "pi3-kernel-canary")
    if kernel_gate is not None:
        kernel_gate["depends_on"] = [
            "pi3-physical-baseline",
            "pi3-adaptive-driver-userspace-generation2",
            "adaptive-kernel-independent",
        ]
        kernel_gate["state"] = "held-on-kernel-mutation-prerequisites"
        kernel_gate["ready_now"] = False
        kernel_gate["proof"] = (
            "experimental Pi3 hardware and userspace generation-2 recovery are proven; "
            "a kernel-module canary still requires exact matching headers, an automatic "
            "out-of-band watchdog/recovery path, and fresh explicit kernel-mutation authority"
        )


def _project_kernel_preflight(plan: dict, evidence: dict) -> None:
    if evidence.get("schema") != KERNEL_PREFLIGHT_SCHEMA:
        raise Pi3StatusError("unexpected Pi3 kernel-canary preflight schema")
    target = evidence.get("target")
    authority = evidence.get("authority")
    safety = evidence.get("safety")
    if not all(isinstance(item, dict) for item in (target, authority, safety)):
        raise Pi3StatusError("Pi3 kernel-canary preflight evidence is incomplete")
    if target.get("serial") != PINNED_SERIAL or target.get("strict_key_only_ssh") is not True:
        raise Pi3StatusError("Pi3 kernel-canary preflight target is not pinned")
    if (
        authority.get("kernel_module_load_allowed") is not False
        or authority.get("driver_binding_change_allowed") is not False
        or authority.get("firmware_mutation_allowed") is not False
        or safety.get("module_loaded") is not False
        or safety.get("system_driver_changed") is not False
        or safety.get("production_nodes_allowed") is not False
    ):
        raise Pi3StatusError("Pi3 kernel-canary preflight claims mutation or unsafe scope")

    gate = _gate(plan, "pi3-kernel-canary")
    if gate is None:
        return
    state = evidence.get("state")
    allowed_states = {
        "held-missing-matching-headers",
        "held-compile-only-canary-failed",
        "held-out-of-band-watchdog-unproven",
        "held-explicit-kernel-mutation-authority",
        "ready-for-explicit-kernel-canary",
    }
    if state not in allowed_states:
        raise Pi3StatusError("unexpected Pi3 kernel-canary preflight state")
    # Even a preflight that has resolved every technical prerequisite does not itself
    # contain the operator's fresh kernel-mutation authorization.
    gate["state"] = str(state)
    gate["ready_now"] = False
    gate["proof"] = (
        "kernel-canary prerequisite probe is persisted; no module was loaded and no "
        "system driver changed. Current technical boundary: " + str(evidence.get("next_gate", "unknown"))
    )


def sync_pi3_status(root: Path = ROOT) -> dict:
    plan_path = root / PLAN_RELATIVE
    gen2_path = root / GEN2_RELATIVE
    preflight_path = root / KERNEL_PREFLIGHT_RELATIVE
    plan = _read_json(plan_path)
    before = json.loads(json.dumps(plan))

    if gen2_path.is_file():
        _project_generation2(plan, _read_json(gen2_path))
    if preflight_path.is_file():
        _project_kernel_preflight(plan, _read_json(preflight_path))

    changed = before != plan
    if changed:
        plan_path.write_text(json.dumps(plan, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    kernel_gate = _gate(plan, "pi3-kernel-canary")
    return {
        "changed": changed,
        "generation2_present": gen2_path.is_file(),
        "kernel_preflight_present": preflight_path.is_file(),
        "kernel_state": None if kernel_gate is None else kernel_gate.get("state"),
    }


def main() -> int:
    try:
        result = sync_pi3_status()
    except Pi3StatusError as exc:
        print(f"AURUM_PI3_STATUS_SYNC_REFUSED reason={exc}", file=sys.stderr)
        return 1
    print(
        "AURUM_PI3_STATUS_SYNC "
        f"changed={str(result['changed']).lower()} "
        f"generation2_present={str(result['generation2_present']).lower()} "
        f"kernel_preflight_present={str(result['kernel_preflight_present']).lower()} "
        f"kernel_state={result['kernel_state']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
