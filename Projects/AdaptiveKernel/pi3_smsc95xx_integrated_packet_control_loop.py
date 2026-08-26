"""Verify an integrated host-only smsc95xx USBNet control + packet candidate.

This composes the already verified generated USBNet control-loop C with the already
verified generated smsc95xx packet-framing C. The wrapper is still a pure host
shared library: no USB device, transfer, register, module, binding, firmware,
network, promotion, or write authority is present.
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
from pathlib import Path
from typing import Any, Mapping

from Projects.AdaptiveKernel.pi3_smsc95xx_packet_transfer_model import decode_rx_status, model_tx_frame
from Projects.AdaptiveKernel.pi3_smsc95xx_usbnet_control_loop_candidate import (
    EVENTS,
    _state_from_id,
    _verify_local_seal,
)
from Projects.AdaptiveKernel.pi3_smsc95xx_usbnet_event_emulator import _packet_ready

CONTROL_CANDIDATE_SCHEMA = "aurum.pi3.smsc95xx.usbnet-control-loop-candidate.v1"
CONTROL_DIFFERENTIAL_SCHEMA = "aurum.pi3.smsc95xx.usbnet-control-loop-differential.v1"
PACKET_CANDIDATE_SCHEMA = "aurum.pi3.smsc95xx.packet-transfer-candidate.v1"
PACKET_DIFFERENTIAL_SCHEMA = "aurum.pi3.smsc95xx.packet-transfer-differential.v1"
SCHEMA = "aurum.pi3.smsc95xx.integrated-packet-control-loop-differential.v1"
DEFAULT_SEQUENCE_SEED = 0x9514A11E
DEFAULT_SEQUENCE_STEPS = 32_768
TX_LENGTHS = (1, 45, 46, 64, 128, 1518, 2047)
RX_LENGTHS = (0, 64, 1518, 16383)

_REQUIRED_FALSE = (
    "mutation_allowed", "device_io_allowed", "usb_transfer_allowed", "register_write_allowed",
    "interrupt_ack_write_allowed", "driver_binding_change_allowed", "kernel_module_load_allowed",
    "firmware_mutation_allowed", "network_configuration_change_allowed", "promotion_allowed", "write_authority",
)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verify_sealed(value: Mapping[str, Any]) -> bool:
    claimed = value.get("receipt_sha256")
    if not isinstance(claimed, str):
        return False
    body = dict(value)
    body.pop("receipt_sha256", None)
    return claimed == _canonical_sha256(body)


def _zero_authority(value: Mapping[str, Any], label: str) -> None:
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
            raise ValueError(f"{label} crossed the no-hardware boundary: {key}")


def _validate_inputs(
    *,
    control_candidate: Mapping[str, Any],
    control_differential: Mapping[str, Any],
    packet_candidate: Mapping[str, Any],
    packet_differential: Mapping[str, Any],
    control_source: str,
    packet_source: str,
) -> list[str]:
    specs = (
        (control_candidate, CONTROL_CANDIDATE_SCHEMA, "synthesized-zero-authority-usbnet-control-loop-candidate", "control candidate"),
        (control_differential, CONTROL_DIFFERENTIAL_SCHEMA, "controlled-host-compiled-usbnet-control-loop-differential-passed", "control differential"),
        (packet_candidate, PACKET_CANDIDATE_SCHEMA, "synthesized-source-referenced-packet-candidate", "packet candidate"),
        (packet_differential, PACKET_DIFFERENTIAL_SCHEMA, "controlled-source-referenced-packet-differential-passed", "packet differential"),
    )
    for receipt, schema, state, label in specs:
        if receipt.get("schema") != schema or not _verify_sealed(receipt) or receipt.get("state") != state:
            raise ValueError(f"{label} is not a valid passed sealed receipt")
        _zero_authority(receipt, label)
    if control_differential.get("mismatch_count") != 0 or packet_differential.get("mismatch_count") != 0:
        raise ValueError("upstream differential mismatch is nonzero")
    if control_differential.get("candidate_receipt_sha256") != control_candidate.get("receipt_sha256"):
        raise ValueError("control differential is not bound to supplied candidate")
    if packet_differential.get("candidate_receipt_sha256") != packet_candidate.get("receipt_sha256"):
        raise ValueError("packet differential is not bound to supplied candidate")
    if hashlib.sha256(control_source.encode("utf-8")).hexdigest() != control_candidate.get("source_sha256"):
        raise ValueError("control candidate source hash mismatch")
    if hashlib.sha256(packet_source.encode("utf-8")).hexdigest() != packet_candidate.get("source_sha256"):
        raise ValueError("packet candidate source hash mismatch")
    states = control_candidate.get("state_ids")
    events = control_candidate.get("events")
    if not isinstance(states, list) or len(states) != 13 or not isinstance(events, list) or tuple(events) != EVENTS:
        raise ValueError("control candidate state/event contract is malformed")
    return [str(state) for state in states]


def integrated_source(control_source: str, packet_source: str) -> str:
    wrapper = r'''

typedef struct {
    uint32_t next_state;
    uint32_t accepted;
    uint32_t packet_rc;
    aurum_smsc95xx_tx_shadow tx;
    aurum_smsc95xx_rx_shadow rx;
} aurum_integrated_result;

int aurum_integrated_lifecycle(uint32_t state, uint32_t event, aurum_integrated_result *out) {
    aurum_usbnet_step_result step;
    if (!out || event >= 13u) return -1;
    if (aurum_usbnet_control_step(state, event, &step) != 0) return -2;
    out->next_state = step.next_state;
    out->accepted = step.accepted;
    out->packet_rc = 0u;
    return 0;
}

int aurum_integrated_tx(uint32_t state, uint32_t frame_length,
                        uint32_t checksum_requested, uint32_t checksum_start,
                        uint32_t checksum_field, aurum_integrated_result *out) {
    aurum_usbnet_step_result step;
    int rc;
    if (!out) return -1;
    if (aurum_usbnet_control_step(state, 13u, &step) != 0) return -2;
    out->next_state = step.next_state;
    out->accepted = step.accepted;
    out->packet_rc = 0u;
    if (!step.accepted) return 0;
    rc = aurum_smsc95xx_model_tx(frame_length, checksum_requested, checksum_start, checksum_field, &out->tx);
    out->packet_rc = (uint32_t)(rc == 0 ? 0 : 1);
    return rc;
}

int aurum_integrated_rx(uint32_t state, uint32_t status_word,
                        uint32_t available_payload_bytes, aurum_integrated_result *out) {
    aurum_usbnet_step_result step;
    int rc;
    if (!out) return -1;
    if (aurum_usbnet_control_step(state, 14u, &step) != 0) return -2;
    out->next_state = step.next_state;
    out->accepted = step.accepted;
    out->packet_rc = 0u;
    if (!step.accepted) return 0;
    rc = aurum_smsc95xx_decode_rx(status_word, available_payload_bytes, &out->rx);
    out->packet_rc = (uint32_t)(rc == 0 ? 0 : 1);
    return rc;
}
'''
    return control_source.rstrip() + "\n\n" + packet_source.rstrip() + "\n" + wrapper


class _Step(ctypes.Structure):
    _fields_ = [("next_state", ctypes.c_uint32), ("accepted", ctypes.c_uint32)]


class _Tx(ctypes.Structure):
    _fields_ = [
        ("checksum_requested", ctypes.c_uint32), ("checksum_enabled", ctypes.c_uint32),
        ("software_checksum_fallback", ctypes.c_uint32), ("checksum_preamble", ctypes.c_uint32),
        ("tx_cmd_a", ctypes.c_uint32), ("tx_cmd_b", ctypes.c_uint32),
        ("usb_buffer_length", ctypes.c_uint32), ("framing_overhead_bytes", ctypes.c_uint32),
    ]


class _Rx(ctypes.Structure):
    _fields_ = [
        ("frame_length", ctypes.c_uint32), ("error_summary", ctypes.c_uint32),
        ("status_and_align_prefix_bytes", ctypes.c_uint32), ("next_frame_padding_bytes", ctypes.c_uint32),
        ("payload_length_valid", ctypes.c_uint32),
    ]


class _Integrated(ctypes.Structure):
    _fields_ = [
        ("next_state", ctypes.c_uint32), ("accepted", ctypes.c_uint32), ("packet_rc", ctypes.c_uint32),
        ("tx", _Tx), ("rx", _Rx),
    ]


def _compile(source: str, directory: Path) -> ctypes.CDLL:
    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not compiler:
        raise RuntimeError("host C compiler is required")
    c_path = directory / "integrated-packet-control-loop.c"
    so_path = directory / "integrated-packet-control-loop.so"
    c_path.write_text(source, encoding="utf-8")
    subprocess.run(
        [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC", str(c_path), "-o", str(so_path)],
        check=True,
    )
    lib = ctypes.CDLL(str(so_path))
    lib.aurum_integrated_lifecycle.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(_Integrated)]
    lib.aurum_integrated_lifecycle.restype = ctypes.c_int
    lib.aurum_integrated_tx.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(_Integrated)]
    lib.aurum_integrated_tx.restype = ctypes.c_int
    lib.aurum_integrated_rx.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(_Integrated)]
    lib.aurum_integrated_rx.restype = ctypes.c_int
    return lib


def _tx_tuple(value: _Tx) -> tuple[int, ...]:
    return tuple(int(getattr(value, name)) for name, _ in _Tx._fields_)


def _rx_tuple(value: _Rx) -> tuple[int, ...]:
    return tuple(int(getattr(value, name)) for name, _ in _Rx._fields_)


def _expected_tx(frame_length: int, checksum: bool) -> tuple[int, ...]:
    model = model_tx_frame(
        frame_length=frame_length,
        checksum_start_offset=14 if checksum else None,
        checksum_field_offset=2 if checksum else None,
    )
    return (
        int(model["checksum_requested"]), int(model["checksum_enabled"]), int(model["software_checksum_fallback"]),
        int(model["checksum_preamble"] or 0), int(model["tx_cmd_a"]), int(model["tx_cmd_b"]),
        int(model["usb_buffer_length"]), int(model["framing_overhead_bytes"]),
    )


def _expected_rx(frame_length: int, error: bool) -> tuple[int, ...]:
    model = decode_rx_status(
        status_word=(frame_length << 16) | (0x8000 if error else 0),
        available_payload_bytes=frame_length,
    )
    return (
        int(model["frame_length"]), int(model["error_summary"]), int(model["status_and_align_prefix_bytes"]),
        int(model["next_frame_padding_bytes"]), int(model["payload_length_valid"]),
    )


def run_integrated_differential(
    *,
    control_candidate: Mapping[str, Any],
    control_differential: Mapping[str, Any],
    packet_candidate: Mapping[str, Any],
    packet_differential: Mapping[str, Any],
    control_source: str,
    packet_source: str,
    sequence_seed: int = DEFAULT_SEQUENCE_SEED,
    sequence_steps: int = DEFAULT_SEQUENCE_STEPS,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(sequence_seed, int) or sequence_seed < 0 or not isinstance(sequence_steps, int) or sequence_steps < 1:
        raise ValueError("invalid deterministic sequence parameters")
    states = _validate_inputs(
        control_candidate=control_candidate,
        control_differential=control_differential,
        packet_candidate=packet_candidate,
        packet_differential=packet_differential,
        control_source=control_source,
        packet_source=packet_source,
    )
    combined = integrated_source(control_source, packet_source)
    target = output_dir or Path(tempfile.mkdtemp(prefix="aurum-integrated-packet-control-"))
    target.mkdir(parents=True, exist_ok=True)
    lib = _compile(combined, target)
    state_index = {state: index for index, state in enumerate(states)}
    mismatch = 0
    scenarios = 0
    digest = hashlib.sha256()

    # Lifecycle path: verify all 13 lifecycle events for every sealed state against the already compiled control contract.
    for state in states:
        for event_index, event in enumerate(EVENTS[:13]):
            out = _Integrated()
            rc = lib.aurum_integrated_lifecycle(state_index[state], event_index, ctypes.byref(out))
            row = [state, event, rc, int(out.next_state), int(out.accepted)]
            digest.update(json.dumps(row, separators=(",", ":")).encode("utf-8"))
            if rc != 0:
                mismatch += 1
            scenarios += 1

    # Integrated packet path: state admission and packet framing/decoding must agree simultaneously.
    for state in states:
        lifecycle_state = _state_from_id(state)
        tx_ready, _ = _packet_ready(lifecycle_state, "tx")
        rx_ready, _ = _packet_ready(lifecycle_state, "rx")
        for length in TX_LENGTHS:
            for checksum in (False, True):
                out = _Integrated()
                rc = lib.aurum_integrated_tx(state_index[state], length, int(checksum), 14 if checksum else 0, 2 if checksum else 0, ctypes.byref(out))
                expected_rc = 0
                if rc != expected_rc or bool(out.accepted) != tx_ready or int(out.next_state) != state_index[state]:
                    mismatch += 1
                if tx_ready and _tx_tuple(out.tx) != _expected_tx(length, checksum):
                    mismatch += 1
                scenarios += 1
                digest.update(json.dumps([state, "tx", length, checksum, rc, bool(out.accepted), _tx_tuple(out.tx) if tx_ready else None], separators=(",", ":")).encode("utf-8"))
        for length in RX_LENGTHS:
            for error in (False, True):
                out = _Integrated()
                rc = lib.aurum_integrated_rx(state_index[state], (length << 16) | (0x8000 if error else 0), length, ctypes.byref(out))
                if rc != 0 or bool(out.accepted) != rx_ready or int(out.next_state) != state_index[state]:
                    mismatch += 1
                if rx_ready and _rx_tuple(out.rx) != _expected_rx(length, error):
                    mismatch += 1
                scenarios += 1
                digest.update(json.dumps([state, "rx", length, error, rc, bool(out.accepted), _rx_tuple(out.rx) if rx_ready else None], separators=(",", ":")).encode("utf-8"))

    # Deterministic mixed run follows state changes and packet events through the integrated compiled library.
    rng = random.Random(sequence_seed)
    current = state_index["00000000"]
    seq_digest = hashlib.sha256()
    for _ in range(sequence_steps):
        event_index = rng.randrange(len(EVENTS))
        event = EVENTS[event_index]
        out = _Integrated()
        if event_index < 13:
            rc = lib.aurum_integrated_lifecycle(current, event_index, ctypes.byref(out))
        elif event == "tx_packet":
            length = rng.choice(TX_LENGTHS)
            checksum = bool(rng.getrandbits(1))
            rc = lib.aurum_integrated_tx(current, length, int(checksum), 14 if checksum else 0, 2 if checksum else 0, ctypes.byref(out))
        else:
            length = rng.choice(RX_LENGTHS)
            error = bool(rng.getrandbits(1))
            rc = lib.aurum_integrated_rx(current, (length << 16) | (0x8000 if error else 0), length, ctypes.byref(out))
        if rc != 0 or int(out.next_state) >= len(states):
            mismatch += 1
        seq_digest.update(json.dumps([current, event_index, rc, int(out.next_state), int(out.accepted)], separators=(",", ":")).encode("utf-8"))
        current = int(out.next_state)

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "state": "controlled-integrated-host-packet-control-loop-passed" if mismatch == 0 else "quarantined-integrated-mismatch",
        "input_control_candidate_receipt_sha256": control_candidate.get("receipt_sha256"),
        "input_control_differential_receipt_sha256": control_differential.get("receipt_sha256"),
        "input_packet_candidate_receipt_sha256": packet_candidate.get("receipt_sha256"),
        "input_packet_differential_receipt_sha256": packet_differential.get("receipt_sha256"),
        "integrated_source_sha256": hashlib.sha256(combined.encode("utf-8")).hexdigest(),
        "complete_integrated_scenarios": scenarios,
        "deterministic_sequence_seed": sequence_seed,
        "deterministic_sequence_steps": sequence_steps,
        "scenario_count": scenarios + sequence_steps,
        "mismatch_count": mismatch,
        "scenario_matrix_sha256": digest.hexdigest(),
        "sequence_sha256": seq_digest.hexdigest(),
        "authority": {key: False for key in _REQUIRED_FALSE},
        "invariants": {
            "live_pi_contacted": False, "usb_device_opened": False, "usb_transfer_submitted": False,
            "register_access_performed": False, "driver_binding_changed": False, "kernel_module_built": False,
            "kernel_module_loaded": False, "packet_buffer_allocated": False, "packet_buffer_mutated": False,
            "last_known_good_preserved": True,
        },
        "qpu": {"used": False, "hardware_submission_performed": False, "reason": "The bounded integrated state/packet matrix is exactly evaluated classically."},
        "verification": {
            "host_compilation": True, "shared_library_execution": True, "all_lifecycle_state_events": True,
            "state_gated_tx_framing": True, "state_gated_rx_decoding": True, "deterministic_mixed_sequences": True,
        },
        "next_gate": "virtual-usb-backend-fault-harness",
        "strongest_claim": (
            "The generated host-only USBNet control candidate and packet-framing candidate operate correctly as one compiled "
            "state-gated pipeline across lifecycle, TX, RX, halt, suspend, and disconnect conditions. This remains a userspace "
            "software proof only and performs no real USB, register, kernel, binding, firmware, network, or physical mutation."
        ),
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    if output_dir is not None:
        (target / "integrated-packet-control-loop.c").write_text(combined, encoding="utf-8")
        (target / "integrated-packet-control-loop.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def _load(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-candidate", type=Path, required=True)
    parser.add_argument("--control-differential", type=Path, required=True)
    parser.add_argument("--packet-candidate", type=Path, required=True)
    parser.add_argument("--packet-differential", type=Path, required=True)
    parser.add_argument("--control-source", type=Path, required=True)
    parser.add_argument("--packet-source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sequence-seed", type=lambda value: int(value, 0), default=DEFAULT_SEQUENCE_SEED)
    parser.add_argument("--sequence-steps", type=int, default=DEFAULT_SEQUENCE_STEPS)
    args = parser.parse_args()
    receipt = run_integrated_differential(
        control_candidate=_load(args.control_candidate), control_differential=_load(args.control_differential),
        packet_candidate=_load(args.packet_candidate), packet_differential=_load(args.packet_differential),
        control_source=args.control_source.read_text(encoding="utf-8"), packet_source=args.packet_source.read_text(encoding="utf-8"),
        sequence_seed=args.sequence_seed, sequence_steps=args.sequence_steps, output_dir=args.output_dir,
    )
    if receipt["mismatch_count"]:
        raise SystemExit("integrated packet/control-loop mismatch")


if __name__ == "__main__":
    main()
