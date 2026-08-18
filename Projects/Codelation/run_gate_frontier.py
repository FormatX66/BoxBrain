#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Projects.Codelation import run_native_autonomous_chain as legacy_executor
from Projects.Codelation.gate_native import Gate, GateField, atom, require_atom


DEFAULT_MACHINE_STATE = Path(__file__).resolve().parent / "autobuild" / "native_gate_state.bin"
DEFAULT_PROJECTION = Path(__file__).resolve().parent / "autobuild" / "native_gate_projection.json"
DEFAULT_BOOTSTRAP = Path(__file__).resolve().parent / "autobuild" / "native_chain_state.json"
STATE_VERSION = 1
_ZERO = bytes(32)
_HEADER = struct.Struct(">B32sI")

# Numeric domains exist only to keep unrelated binary identities disjoint.
_DOMAIN_CAPABILITY = b"\x01"
_DOMAIN_PROOF = b"\x02"
_DOMAIN_AUTHORITY = b"\x03"
_DOMAIN_BLOCK = b"\x04"


def _canonical(value: Any) -> bytes:
    # This encoding is part of the Codelation adapter only. The machine state stores
    # only the resulting 256-bit identity; it never stores these labels or JSON bytes.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def capability_id(label: str) -> bytes:
    return atom(_DOMAIN_CAPABILITY, label.encode("utf-8"))


def proof_id(value: Any) -> bytes:
    return atom(_DOMAIN_PROOF, hashlib.sha256(_canonical(value)).digest())


def authority_id(reference: str) -> bytes:
    return atom(_DOMAIN_AUTHORITY, reference.encode("utf-8"))


def block_id(reason: str) -> bytes:
    return atom(_DOMAIN_BLOCK, reason.encode("utf-8"))


@dataclass(frozen=True)
class MachineFrontier:
    """Authoritative control state.

    The serialized representation contains only numeric/binary state: one opaque
    focus identity plus the gate field. Human names and executor-language details
    live exclusively in the projection sidecar used by Codelation adapters.
    """

    focus: bytes
    field: GateField

    def __post_init__(self) -> None:
        if self.focus != _ZERO:
            require_atom(self.focus)

    def to_bytes(self) -> bytes:
        field_bytes = self.field.to_bytes()
        return _HEADER.pack(STATE_VERSION, self.focus, len(field_bytes)) + field_bytes

    @classmethod
    def from_bytes(cls, payload: bytes) -> "MachineFrontier":
        if len(payload) < _HEADER.size:
            raise ValueError("truncated machine frontier")
        version, focus, field_size = _HEADER.unpack(payload[: _HEADER.size])
        if version != STATE_VERSION:
            raise ValueError("unsupported machine frontier version")
        end = _HEADER.size + field_size
        if end != len(payload):
            raise ValueError("machine frontier length mismatch")
        field = GateField.from_bytes(payload[_HEADER.size:end])
        if focus != _ZERO and not field.is_active(focus):
            raise ValueError("focus state is not active")
        return cls(focus=focus, field=field)

    def identity(self) -> str:
        return hashlib.sha256(self.to_bytes()).hexdigest()


def _atomic_binary_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _atomic_json_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return dict(value) if isinstance(value, Mapping) else None


def _checkpoint_from_bootstrap(bootstrap: Mapping[str, Any] | None) -> dict[str, Any]:
    checkpoint = bootstrap.get("_checkpoint") if bootstrap else None
    if isinstance(checkpoint, Mapping):
        return dict(checkpoint)
    return {
        "schema": "aurum-native-chain-resume-v1",
        "learned_expressions": {},
        "verified_local_capabilities": [],
    }


def _executor_seed(checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": legacy_executor.STATE_SCHEMA,
        "catalog_revision": legacy_executor.CATALOG_REVISION,
        "synthesis_revision": legacy_executor.SYNTHESIS_REVISION,
        "self_debug_revision": legacy_executor.SELF_DEBUG_REVISION,
        "local_verification_revision": legacy_executor.LOCAL_VERIFICATION_REVISION,
        "_checkpoint": dict(checkpoint),
    }


def bootstrap(
    bootstrap_state: Mapping[str, Any] | None,
) -> tuple[MachineFrontier, dict[str, Any]]:
    label = str(
        (bootstrap_state or {}).get("next_gap")
        or (bootstrap_state or {}).get("start_gap")
        or "learning_delta_score"
    )
    current = capability_id(label)
    machine = MachineFrontier(focus=current, field=GateField(active=(current,)))
    projection = {
        "schema": "aurum-gate-projection-v1",
        "role": "codelation-only-not-authoritative",
        "machine_state_sha256": machine.identity(),
        "focus": current.hex(),
        "labels": {current.hex(): label},
        "executor_checkpoint": _checkpoint_from_bootstrap(bootstrap_state),
        "external_evidence": None,
        "blocked_reason": None,
        "reasoning_required": False,
        "reasoning_request": None,
        "yield_reason": "bootstrap",
        "work_done_this_burst": 0,
    }
    return machine, projection


def _resolve_label(projection: Mapping[str, Any], state_id: bytes) -> str:
    labels = projection.get("labels")
    if not isinstance(labels, Mapping):
        raise ValueError("Codelation projection lacks label map")
    label = labels.get(state_id.hex())
    if not isinstance(label, str) or not label:
        raise ValueError("Codelation projection cannot resolve machine focus")
    return label


def advance(
    machine: MachineFrontier,
    projection: Mapping[str, Any],
    *,
    work_budget: int,
    evidence_now: int | None = None,
) -> tuple[MachineFrontier, dict[str, Any]]:
    if work_budget < 1:
        raise ValueError("work budget must be positive")

    sidecar = dict(projection)
    labels = dict(sidecar.get("labels") or {})
    checkpoint = dict(sidecar.get("executor_checkpoint") or {})
    field = machine.field
    focus = machine.focus
    work_done = 0
    blocked_reason: str | None = None
    reasoning_required = False
    reasoning_request: Any = None
    external_evidence: Any = None

    while focus != _ZERO and work_done < work_budget:
        label = _resolve_label({**sidecar, "labels": labels}, focus)
        result = legacy_executor.run_chain(
            start_gap=label,
            max_generations=1,  # compatibility executor slice; not machine lifecycle state
            evidence_now=evidence_now,
            seed_state=_executor_seed(checkpoint),
        )
        records = result.get("generations") or []
        raw_checkpoint = result.get("_checkpoint")
        if isinstance(raw_checkpoint, Mapping):
            checkpoint = dict(raw_checkpoint)

        external_evidence = result.get("external_evidence")
        reasoning_required = bool(result.get("reasoning_required"))
        reasoning_request = result.get("reasoning_request")
        blocked_reason = result.get("blocked_reason")
        if records and blocked_reason == "generation-bound-reached":
            blocked_reason = None

        if not records:
            reason = str(blocked_reason or "no-verified-work")
            field.activate(block_id(reason))
            blocked_reason = reason
            break

        record = records[-1]
        proof = proof_id(record)
        field.activate(proof)
        next_label = result.get("next_gap")
        if blocked_reason:
            field.activate(block_id(str(blocked_reason)))
            break
        if not next_label:
            focus = _ZERO
            work_done += 1
            break

        next_label = str(next_label)
        next_state = capability_id(next_label)
        labels[next_state.hex()] = next_label

        inputs = [focus, proof]
        evidence = record.get("external_evidence") if isinstance(record, Mapping) else None
        if isinstance(evidence, Mapping):
            authorization_reference = evidence.get("authorization_reference")
            authority_granted = bool(evidence.get("authority_granted"))
            if authorization_reference and authority_granted:
                authority = authority_id(str(authorization_reference))
                field.activate(authority)
                inputs.append(authority)

        gate = Gate(tuple(inputs), next_state)
        field = field.with_gate(gate)
        # with_gate fires immediately if all prerequisite states already exist.
        if not field.is_active(next_state):
            blocked_reason = "gate-prerequisite-unsatisfied"
            break
        focus = next_state
        work_done += 1

    yield_reason: str
    if blocked_reason:
        yield_reason = "blocked-on-state"
    elif focus == _ZERO:
        yield_reason = "frontier-converged"
    elif work_done >= work_budget:
        yield_reason = "compute-burst-yield"
    else:
        yield_reason = "state-changed"

    advanced = MachineFrontier(focus=focus, field=field)
    sidecar.update(
        {
            "schema": "aurum-gate-projection-v1",
            "role": "codelation-only-not-authoritative",
            "machine_state_sha256": advanced.identity(),
            "focus": None if focus == _ZERO else focus.hex(),
            "labels": labels,
            "executor_checkpoint": checkpoint,
            "external_evidence": external_evidence,
            "blocked_reason": blocked_reason,
            "reasoning_required": reasoning_required,
            "reasoning_request": reasoning_request,
            "yield_reason": yield_reason,
            "work_done_this_burst": work_done,
        }
    )
    return advanced, sidecar


def main() -> int:
    parser = argparse.ArgumentParser(description="Advance Aurum using binary gate-native authority")
    parser.add_argument("--machine-state", type=Path, default=DEFAULT_MACHINE_STATE)
    parser.add_argument("--projection", type=Path, default=DEFAULT_PROJECTION)
    parser.add_argument("--bootstrap-state", type=Path, default=DEFAULT_BOOTSTRAP)
    parser.add_argument("--work-budget", type=int, default=32)
    parser.add_argument("--evidence-now", type=int)
    args = parser.parse_args()

    machine_path = args.machine_state.resolve()
    projection_path = args.projection.resolve()
    projection = _read_json(projection_path)
    try:
        machine = MachineFrontier.from_bytes(machine_path.read_bytes())
    except (OSError, ValueError):
        machine, projection = bootstrap(_read_json(args.bootstrap_state.resolve()))
    if projection is None:
        raise SystemExit("machine state exists but Codelation projection is missing")
    if projection.get("machine_state_sha256") != machine.identity():
        raise SystemExit("Codelation projection does not match authoritative machine state")

    advanced, sidecar = advance(
        machine,
        projection,
        work_budget=args.work_budget,
        evidence_now=args.evidence_now,
    )
    _atomic_binary_write(machine_path, advanced.to_bytes())
    _atomic_json_write(projection_path, sidecar)
    print(json.dumps({
        "machine_state_sha256": advanced.identity(),
        "focus": sidecar.get("focus"),
        "blocked_reason": sidecar.get("blocked_reason"),
        "yield_reason": sidecar.get("yield_reason"),
        "work_done_this_burst": sidecar.get("work_done_this_burst"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
