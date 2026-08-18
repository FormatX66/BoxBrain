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
from Projects.Codelation.field.native_gap_catalog import native_semantic_gap_names


DEFAULT_MACHINE_STATE = Path(__file__).resolve().parent / "autobuild" / "native_gate_state.bin"
DEFAULT_PROJECTION = Path(__file__).resolve().parent / "autobuild" / "native_gate_projection.json"
DEFAULT_BOOTSTRAP = Path(__file__).resolve().parent / "autobuild" / "native_chain_state.json"
STATE_VERSION = 2
_ZERO = bytes(32)
_HEADER_V1 = struct.Struct(">B32sI")
_HEADER_V2 = struct.Struct(">BIIII")

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


def block_id(reason: str, state: bytes | None = None) -> bytes:
    parts = [_DOMAIN_BLOCK]
    if state is not None:
        parts.append(require_atom(state))
    parts.append(hashlib.sha256(reason.encode("utf-8")).digest())
    return atom(*parts)


def _atoms(values: tuple[bytes, ...] | list[bytes] | set[bytes]) -> tuple[bytes, ...]:
    return tuple(sorted({require_atom(value) for value in values}))


@dataclass(frozen=True)
class MachineFrontier:
    """Binary scheduler state with no lifecycle ordering.

    `pending` contains machine states whose transition work can execute now.
    `parked` contains states waiting on evidence/capability/authority.
    `resolved` prevents completed work from being reintroduced by cyclic projections.
    All three collections are opaque state identities; names live only in Codelation.
    """

    pending: tuple[bytes, ...]
    parked: tuple[bytes, ...]
    resolved: tuple[bytes, ...]
    field: GateField

    def __post_init__(self) -> None:
        pending = _atoms(self.pending)
        parked = _atoms(self.parked)
        resolved = _atoms(self.resolved)
        if set(pending) & set(parked):
            raise ValueError("state cannot be pending and parked")
        if set(pending) & set(resolved):
            raise ValueError("state cannot be pending and resolved")
        if set(parked) & set(resolved):
            raise ValueError("state cannot be parked and resolved")
        for state in (*pending, *parked, *resolved):
            if not self.field.is_active(state):
                raise ValueError("scheduler state is not active in gate field")
        object.__setattr__(self, "pending", pending)
        object.__setattr__(self, "parked", parked)
        object.__setattr__(self, "resolved", resolved)

    @property
    def focus(self) -> bytes:
        # Codelation compatibility only. Machine authority is the whole pending/parked set.
        if self.pending:
            return self.pending[0]
        if self.parked:
            return self.parked[0]
        return _ZERO

    def to_bytes(self) -> bytes:
        field_bytes = self.field.to_bytes()
        out = bytearray(
            _HEADER_V2.pack(
                STATE_VERSION,
                len(self.pending),
                len(self.parked),
                len(self.resolved),
                len(field_bytes),
            )
        )
        for group in (self.pending, self.parked, self.resolved):
            for state in group:
                out.extend(state)
        out.extend(field_bytes)
        return bytes(out)

    @classmethod
    def from_bytes(cls, payload: bytes) -> "MachineFrontier":
        if not payload:
            raise ValueError("truncated machine frontier")
        version = payload[0]
        if version == 1:
            if len(payload) < _HEADER_V1.size:
                raise ValueError("truncated v1 machine frontier")
            _, focus, field_size = _HEADER_V1.unpack(payload[: _HEADER_V1.size])
            end = _HEADER_V1.size + field_size
            if end != len(payload):
                raise ValueError("v1 machine frontier length mismatch")
            field = GateField.from_bytes(payload[_HEADER_V1.size:end])
            pending = () if focus == _ZERO else (focus,)
            return cls(pending=pending, parked=(), resolved=(), field=field)
        if version != STATE_VERSION or len(payload) < _HEADER_V2.size:
            raise ValueError("unsupported machine frontier version")

        _, pending_count, parked_count, resolved_count, field_size = _HEADER_V2.unpack(
            payload[: _HEADER_V2.size]
        )
        offset = _HEADER_V2.size

        def read_group(count: int) -> tuple[bytes, ...]:
            nonlocal offset
            values: list[bytes] = []
            for _ in range(count):
                end = offset + 32
                if end > len(payload):
                    raise ValueError("truncated machine scheduler state")
                values.append(bytes(payload[offset:end]))
                offset = end
            return tuple(values)

        pending = read_group(pending_count)
        parked = read_group(parked_count)
        resolved = read_group(resolved_count)
        end = offset + field_size
        if end != len(payload):
            raise ValueError("machine frontier length mismatch")
        field = GateField.from_bytes(payload[offset:end])
        return cls(pending=pending, parked=parked, resolved=resolved, field=field)

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


def _catalog_labels(bootstrap_state: Mapping[str, Any] | None) -> tuple[str, ...]:
    preferred = str(
        (bootstrap_state or {}).get("next_gap")
        or (bootstrap_state or {}).get("start_gap")
        or "learning_delta_score"
    )
    names = {str(name) for name in native_semantic_gap_names() if str(name)}
    names.add(preferred)
    return (preferred, *sorted(names - {preferred}))


def bootstrap(
    bootstrap_state: Mapping[str, Any] | None,
) -> tuple[MachineFrontier, dict[str, Any]]:
    labels_in = _catalog_labels(bootstrap_state)
    identities = tuple(capability_id(label) for label in labels_in)
    field = GateField(active=identities)
    machine = MachineFrontier(pending=identities, parked=(), resolved=(), field=field)
    labels = {state.hex(): label for state, label in zip(identities, labels_in)}
    projection = {
        "schema": "aurum-gate-projection-v2",
        "role": "codelation-only-not-authoritative",
        "machine_state_sha256": machine.identity(),
        "focus": machine.focus.hex() if machine.focus != _ZERO else None,
        "pending": [state.hex() for state in machine.pending],
        "parked": [],
        "resolved": [],
        "labels": labels,
        "blocked": {},
        "executor_checkpoint": _checkpoint_from_bootstrap(bootstrap_state),
        "external_evidence": {},
        "reasoning_requests": {},
        "yield_reason": "bootstrap",
        "work_done_this_burst": 0,
        "attempts_this_burst": 0,
    }
    return machine, projection


def _resolve_label(projection: Mapping[str, Any], state_id: bytes) -> str:
    labels = projection.get("labels")
    if not isinstance(labels, Mapping):
        raise ValueError("Codelation projection lacks label map")
    label = labels.get(state_id.hex())
    if not isinstance(label, str) or not label:
        raise ValueError("Codelation projection cannot resolve machine state")
    return label


def _ensure_catalog_work(
    *,
    pending: list[bytes],
    parked: set[bytes],
    resolved: set[bytes],
    field: GateField,
    labels: dict[str, Any],
) -> tuple[GateField, list[bytes]]:
    known = set(pending) | parked | resolved
    additions: list[bytes] = []
    for label in native_semantic_gap_names():
        state = capability_id(str(label))
        labels.setdefault(state.hex(), str(label))
        if state in known:
            continue
        additions.append(state)
        known.add(state)
    if additions:
        field.activate(*additions)
        pending.extend(additions)
    pending[:] = sorted(set(pending))
    return field, additions


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
    labels: dict[str, Any] = dict(sidecar.get("labels") or {})
    blocked: dict[str, Any] = dict(sidecar.get("blocked") or {})
    external_by_state: dict[str, Any] = dict(sidecar.get("external_evidence") or {})
    reasoning_by_state: dict[str, Any] = dict(sidecar.get("reasoning_requests") or {})
    checkpoint = dict(sidecar.get("executor_checkpoint") or {})

    field = machine.field
    pending = list(machine.pending)
    parked = set(machine.parked)
    resolved = set(machine.resolved)
    field, _ = _ensure_catalog_work(
        pending=pending,
        parked=parked,
        resolved=resolved,
        field=field,
        labels=labels,
    )

    # A new event should be able to retry parked work. When runnable work already exists,
    # preserve capacity for it; when only parked work remains, probe each parked state once.
    retrying_parked = not pending and bool(parked)
    if retrying_parked:
        pending = sorted(parked)

    work_done = 0
    attempts = 0
    last_blocked_reason: str | None = None

    while pending and attempts < work_budget:
        state = pending.pop(0)
        was_parked = state in parked
        if state in resolved:
            continue
        if was_parked:
            parked.discard(state)

        label = _resolve_label({**sidecar, "labels": labels}, state)
        result = legacy_executor.run_chain(
            start_gap=label,
            max_generations=1,  # compatibility slice only; no lifecycle semantics
            evidence_now=evidence_now,
            seed_state=_executor_seed(checkpoint),
        )
        attempts += 1

        raw_checkpoint = result.get("_checkpoint")
        if isinstance(raw_checkpoint, Mapping):
            checkpoint = dict(raw_checkpoint)

        records = result.get("generations") or []
        block_reason = result.get("blocked_reason")
        if records and block_reason == "generation-bound-reached":
            block_reason = None

        state_hex = state.hex()
        external_by_state[state_hex] = result.get("external_evidence")
        if result.get("reasoning_required"):
            reasoning_by_state[state_hex] = result.get("reasoning_request")
        else:
            reasoning_by_state.pop(state_hex, None)

        if not records or block_reason:
            reason = str(block_reason or "no-verified-work")
            marker = block_id(reason, state)
            field.activate(marker)
            parked.add(state)
            blocked[state_hex] = reason
            last_blocked_reason = reason
            # One blocked capability never stalls unrelated pending work.
            continue

        blocked.pop(state_hex, None)
        reasoning_by_state.pop(state_hex, None)
        resolved.add(state)
        work_done += 1

        record = records[-1]
        proof = proof_id(record)
        field.activate(proof)

        next_label_raw = result.get("next_gap")
        if not next_label_raw:
            continue

        next_label = str(next_label_raw)
        next_state = capability_id(next_label)
        labels[next_state.hex()] = next_label
        if not field.is_active(next_state):
            field.activate(next_state)

        inputs = [state, proof]
        evidence = record.get("external_evidence") if isinstance(record, Mapping) else None
        if isinstance(evidence, Mapping):
            authorization_reference = evidence.get("authorization_reference")
            authority_granted = bool(evidence.get("authority_granted"))
            if authorization_reference and authority_granted:
                authority = authority_id(str(authorization_reference))
                field.activate(authority)
                inputs.append(authority)

        field = field.with_gate(Gate(tuple(inputs), next_state))
        if next_state not in resolved and next_state not in parked and next_state not in pending:
            pending.append(next_state)
            pending.sort()

    # If this was merely a parked-state retry, remove unprocessed parked states that were
    # temporarily placed in the local pending queue; authoritative parking remains intact.
    if retrying_parked:
        for state in pending:
            parked.add(state)
        pending = []

    global_blocked: str | None = None
    if pending:
        yield_reason = "compute-burst-yield"
    elif parked:
        yield_reason = "waiting-on-external-state"
        global_blocked = last_blocked_reason or "parked-state-pending"
    else:
        yield_reason = "field-converged"

    # Keep every scheduler state represented inside the field before serialization.
    scheduler_states = tuple(set(pending) | parked | resolved)
    if scheduler_states:
        field.activate(*scheduler_states)

    advanced = MachineFrontier(
        pending=tuple(pending),
        parked=tuple(parked),
        resolved=tuple(resolved),
        field=field,
    )
    sidecar.update(
        {
            "schema": "aurum-gate-projection-v2",
            "role": "codelation-only-not-authoritative",
            "machine_state_sha256": advanced.identity(),
            "focus": advanced.focus.hex() if advanced.focus != _ZERO else None,
            "pending": [state.hex() for state in advanced.pending],
            "parked": [state.hex() for state in advanced.parked],
            "resolved": [state.hex() for state in advanced.resolved],
            "labels": labels,
            "blocked": blocked,
            "blocked_reason": global_blocked,
            "executor_checkpoint": checkpoint,
            "external_evidence": external_by_state,
            "reasoning_requests": reasoning_by_state,
            "reasoning_required": bool(reasoning_by_state),
            "yield_reason": yield_reason,
            "work_done_this_burst": work_done,
            "attempts_this_burst": attempts,
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
    print(
        json.dumps(
            {
                "machine_state_sha256": advanced.identity(),
                "focus": sidecar.get("focus"),
                "pending": len(advanced.pending),
                "parked": len(advanced.parked),
                "resolved": len(advanced.resolved),
                "blocked_reason": sidecar.get("blocked_reason"),
                "yield_reason": sidecar.get("yield_reason"),
                "work_done_this_burst": sidecar.get("work_done_this_burst"),
                "attempts_this_burst": sidecar.get("attempts_this_burst"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
