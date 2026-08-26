"""Generate and differentially verify a host-only USBNet control-loop candidate.

The generated C is a pure table-driven state/event transform. It has no USB handle,
device I/O primitive, register access, packet buffer, module entry point, binding
path, firmware/network mutation path, promotion path, or write authority.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import random
import shutil
import subprocess
import tempfile
from dataclasses import fields
from pathlib import Path
from typing import Any, Mapping

from Projects.AdaptiveKernel.pi3_smsc95xx_usbnet_event_emulator import (
    SCHEMA as EVENT_EMULATOR_SCHEMA,
    _packet_ready,
    _verify_sealed,
)
from Projects.AdaptiveKernel.pi3_smsc95xx_usbnet_lifecycle_model import ACTIONS, LifecycleState

LIFECYCLE_SHADOW_SCHEMA = "aurum.pi3.smsc95xx.usbnet-lifecycle-shadow.v1"
CANDIDATE_SCHEMA = "aurum.pi3.smsc95xx.usbnet-control-loop-candidate.v1"
DIFFERENTIAL_SCHEMA = "aurum.pi3.smsc95xx.usbnet-control-loop-differential.v1"
DEFAULT_SEQUENCE_SEED = 0x9514C011
DEFAULT_SEQUENCE_STEPS = 65536
EVENTS = tuple(ACTIONS) + ("tx_packet", "rx_packet")

_REQUIRED_FALSE = (
    "mutation_allowed", "device_io_allowed", "usb_transfer_allowed", "register_write_allowed",
    "interrupt_ack_write_allowed", "driver_binding_change_allowed", "kernel_module_load_allowed",
    "firmware_mutation_allowed", "network_configuration_change_allowed", "promotion_allowed", "write_authority",
)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _require_zero_authority(value: Mapping[str, Any], label: str) -> None:
    authority = value.get("authority")
    if not isinstance(authority, Mapping):
        raise ValueError(f"{label} authority is malformed")
    for key in _REQUIRED_FALSE:
        if authority.get(key) is not False:
            raise ValueError(f"{label} must keep {key}=false")
    invariants = value.get("invariants")
    if not isinstance(invariants, Mapping):
        raise ValueError(f"{label} invariants are malformed")
    for key in ("live_pi_contacted", "usb_device_opened", "usb_transfer_submitted", "driver_binding_changed"):
        if key in invariants and invariants.get(key) is not False:
            raise ValueError(f"{label} crossed no-hardware boundary: {key}")


def _validated_inputs(shadow: Mapping[str, Any], emulator: Mapping[str, Any]) -> tuple[list[str], dict[tuple[str, str], tuple[str, bool]]]:
    if shadow.get("schema") != LIFECYCLE_SHADOW_SCHEMA or not _verify_sealed(shadow):
        raise ValueError("lifecycle shadow must be a valid sealed receipt")
    if shadow.get("state") != "verified-offline-usbnet-lifecycle-fault-model":
        raise ValueError("lifecycle shadow gate has not passed")
    _require_zero_authority(shadow, "lifecycle shadow")
    if emulator.get("schema") != EVENT_EMULATOR_SCHEMA or not _verify_sealed(emulator):
        raise ValueError("event emulator must be a valid sealed receipt")
    if emulator.get("state") != "controlled-userspace-usbnet-event-emulator-passed" or emulator.get("mismatch_count") != 0:
        raise ValueError("event emulator gate has not passed")
    _require_zero_authority(emulator, "event emulator")
    if emulator.get("inputs", {}).get("lifecycle_shadow") != shadow.get("receipt_sha256"):
        raise ValueError("event emulator is not bound to the supplied lifecycle shadow")

    graph = shadow.get("graph")
    if not isinstance(graph, Mapping) or not isinstance(graph.get("states"), list) or not isinstance(graph.get("transitions"), list):
        raise ValueError("lifecycle graph is incomplete")
    states = sorted(str(row.get("id")) for row in graph["states"] if isinstance(row, Mapping))
    if len(states) != graph.get("state_count") or len(set(states)) != len(states):
        raise ValueError("lifecycle state accounting is inconsistent")
    matrix: dict[tuple[str, str], tuple[str, bool]] = {}
    for row in graph["transitions"]:
        if not isinstance(row, Mapping):
            raise ValueError("lifecycle transition row is malformed")
        key = (str(row.get("from")), str(row.get("action")))
        if key in matrix:
            raise ValueError("duplicate lifecycle transition")
        matrix[key] = (str(row.get("to")), bool(row.get("accepted")))
    if len(matrix) != len(states) * len(ACTIONS):
        raise ValueError("lifecycle transition matrix is incomplete")
    return states, matrix


def _state_from_id(state_id: str) -> LifecycleState:
    if len(state_id) != 8 or set(state_id) - {"0", "1"}:
        raise ValueError("malformed lifecycle state id")
    names = [field.name for field in fields(LifecycleState)]
    return LifecycleState(**{name: state_id[index] == "1" for index, name in enumerate(names)})


def _event_matrix(states: list[str], lifecycle: Mapping[tuple[str, str], tuple[str, bool]]) -> dict[tuple[str, str], tuple[str, bool]]:
    matrix: dict[tuple[str, str], tuple[str, bool]] = {}
    for state_id in states:
        for action in ACTIONS:
            matrix[(state_id, action)] = lifecycle[(state_id, action)]
        state = _state_from_id(state_id)
        tx_ready, _ = _packet_ready(state, "tx")
        rx_ready, _ = _packet_ready(state, "rx")
        matrix[(state_id, "tx_packet")] = (state_id, tx_ready)
        matrix[(state_id, "rx_packet")] = (state_id, rx_ready)
    return matrix


def synthesize_control_loop_candidate(shadow: Mapping[str, Any], emulator: Mapping[str, Any]) -> tuple[str, dict[str, Any], dict[tuple[str, str], tuple[str, bool]]]:
    states, lifecycle = _validated_inputs(shadow, emulator)
    matrix = _event_matrix(states, lifecycle)
    indexes = {state: index for index, state in enumerate(states)}
    next_rows = []
    accept_rows = []
    for state in states:
        next_rows.append("    {" + ", ".join(str(indexes[matrix[(state, event)][0]]) for event in EVENTS) + "}")
        accept_rows.append("    {" + ", ".join("1" if matrix[(state, event)][1] else "0" for event in EVENTS) + "}")
    source = f'''/* Aurum generated host-only USBNet control-loop candidate.\n * ZERO AUTHORITY: pure state/event table lookup.\n */\n#include <stdint.h>\n#define AURUM_STATE_COUNT {len(states)}u\n#define AURUM_EVENT_COUNT {len(EVENTS)}u\ntypedef struct {{ uint32_t next_state; uint32_t accepted; }} aurum_usbnet_step_result;\nstatic const uint8_t NEXT[{len(states)}][{len(EVENTS)}] = {{\n{',\n'.join(next_rows)}\n}};\nstatic const uint8_t ACCEPT[{len(states)}][{len(EVENTS)}] = {{\n{',\n'.join(accept_rows)}\n}};\nint aurum_usbnet_control_step(uint32_t state, uint32_t event, aurum_usbnet_step_result *out) {{\n    if (!out || state >= AURUM_STATE_COUNT || event >= AURUM_EVENT_COUNT) return -1;\n    out->next_state = NEXT[state][event];\n    out->accepted = ACCEPT[state][event];\n    return 0;\n}}\n'''
    receipt: dict[str, Any] = {
        "schema": CANDIDATE_SCHEMA,
        "state": "synthesized-zero-authority-usbnet-control-loop-candidate",
        "input_lifecycle_shadow_receipt_sha256": shadow.get("receipt_sha256"),
        "input_event_emulator_receipt_sha256": emulator.get("receipt_sha256"),
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "state_ids": states,
        "events": list(EVENTS),
        "state_count": len(states),
        "event_count": len(EVENTS),
        "authority": {key: False for key in _REQUIRED_FALSE},
        "invariants": {"live_pi_contacted": False, "usb_device_opened": False, "usb_transfer_submitted": False, "driver_binding_changed": False, "kernel_module_entrypoint_present": False, "device_io_primitive_present": False, "last_known_good_preserved": True},
        "next_gate": "compiled-complete-control-loop-differential",
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return source, receipt, matrix


class _Result(ctypes.Structure):
    _fields_ = [("next_state", ctypes.c_uint32), ("accepted", ctypes.c_uint32)]


def _compile(source: str, directory: Path) -> ctypes.CDLL:
    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not compiler:
        raise RuntimeError("host C compiler is required for control-loop differential")
    c_path = directory / "usbnet-control-loop-candidate.c"
    so_path = directory / "usbnet-control-loop-candidate.so"
    c_path.write_text(source, encoding="utf-8")
    subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC", str(c_path), "-o", str(so_path)], check=True)
    library = ctypes.CDLL(str(so_path))
    library.aurum_usbnet_control_step.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(_Result)]
    library.aurum_usbnet_control_step.restype = ctypes.c_int
    return library


def run_control_loop_differential(*, shadow: Mapping[str, Any], emulator: Mapping[str, Any], sequence_seed: int = DEFAULT_SEQUENCE_SEED, sequence_steps: int = DEFAULT_SEQUENCE_STEPS, output_dir: Path | None = None) -> dict[str, Any]:
    if sequence_steps < 1 or sequence_seed < 0:
        raise ValueError("invalid deterministic sequence parameters")
    source, candidate, matrix = synthesize_control_loop_candidate(shadow, emulator)
    states = candidate["state_ids"]
    indexes = {state: index for index, state in enumerate(states)}
    reverse = {index: state for state, index in indexes.items()}
    event_indexes = {event: index for index, event in enumerate(EVENTS)}
    mismatches = 0
    matrix_digest = hashlib.sha256()
    target_dir = output_dir or Path(tempfile.mkdtemp(prefix="aurum-usbnet-control-"))
    target_dir.mkdir(parents=True, exist_ok=True)
    library = _compile(source, target_dir)

    for state in states:
        for event in EVENTS:
            expected_state, expected_accepted = matrix[(state, event)]
            result = _Result()
            rc = library.aurum_usbnet_control_step(indexes[state], event_indexes[event], ctypes.byref(result))
            observed = (reverse.get(int(result.next_state)), bool(result.accepted))
            expected = (expected_state, expected_accepted)
            matrix_digest.update(json.dumps([state, event, expected], separators=(",", ":")).encode())
            if rc != 0 or observed != expected:
                mismatches += 1

    rng = random.Random(sequence_seed)
    current = states.index("00000000")
    sequence_digest = hashlib.sha256()
    for _ in range(sequence_steps):
        event = rng.choice(EVENTS)
        state = reverse[current]
        expected_state, expected_accepted = matrix[(state, event)]
        result = _Result()
        rc = library.aurum_usbnet_control_step(current, event_indexes[event], ctypes.byref(result))
        observed_state = reverse.get(int(result.next_state))
        sequence_digest.update(json.dumps([state, event, expected_state, expected_accepted], separators=(",", ":")).encode())
        if rc != 0 or observed_state != expected_state or bool(result.accepted) != expected_accepted:
            mismatches += 1
        current = int(result.next_state)

    receipt: dict[str, Any] = {
        "schema": DIFFERENTIAL_SCHEMA,
        "state": "controlled-host-compiled-usbnet-control-loop-differential-passed" if mismatches == 0 else "quarantined-control-loop-mismatch",
        "candidate_receipt_sha256": candidate["receipt_sha256"],
        "candidate_source_sha256": candidate["source_sha256"],
        "complete_event_scenarios": len(states) * len(EVENTS),
        "deterministic_sequence_seed": sequence_seed,
        "deterministic_sequence_steps": sequence_steps,
        "scenario_count": len(states) * len(EVENTS) + sequence_steps,
        "mismatch_count": mismatches,
        "event_matrix_sha256": matrix_digest.hexdigest(),
        "sequence_sha256": sequence_digest.hexdigest(),
        "authority": {key: False for key in _REQUIRED_FALSE},
        "invariants": {"live_pi_contacted": False, "usb_device_opened": False, "usb_transfer_submitted": False, "driver_binding_changed": False, "kernel_module_built": False, "kernel_module_loaded": False, "last_known_good_preserved": True},
        "qpu": {"used": False, "hardware_submission_performed": False, "reason": "The finite state/event matrix and deterministic sequence are exactly evaluated classically."},
        "verification": {"host_compilation": True, "shared_library_execution": True, "all_state_event_pairs": True, "deterministic_multi_step_sequences": True},
        "next_gate": "integrated-host-compiled-packet-framing-control-loop",
        "strongest_claim": "A generated portable C control-loop candidate matches every sealed USBNet lifecycle and packet-admission state/event pair plus a deterministic multi-step sequence. It remains host-only and has no USB, kernel, register, binding, mutation, or promotion capability.",
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    if output_dir is not None:
        (target_dir / "usbnet-control-loop-candidate.c").write_text(source, encoding="utf-8")
        (target_dir / "usbnet-control-loop-candidate.json").write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (target_dir / "usbnet-control-loop-differential.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def _load(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lifecycle-shadow", type=Path, required=True)
    parser.add_argument("--event-emulator", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sequence-seed", type=lambda value: int(value, 0), default=DEFAULT_SEQUENCE_SEED)
    parser.add_argument("--sequence-steps", type=int, default=DEFAULT_SEQUENCE_STEPS)
    args = parser.parse_args()
    receipt = run_control_loop_differential(shadow=_load(args.lifecycle_shadow), emulator=_load(args.event_emulator), sequence_seed=args.sequence_seed, sequence_steps=args.sequence_steps, output_dir=args.output_dir)
    if receipt["mismatch_count"]:
        raise SystemExit("control-loop differential mismatch")


if __name__ == "__main__":
    main()
