"""Userspace-only smsc95xx/usbnet event emulator.

Composes sealed lifecycle and packet proofs using synthetic values only. It never
opens a USB device, submits a transfer, writes a register, loads a module, changes
a binding, mutates network/firmware state, or grants promotion/write authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from Projects.AdaptiveKernel.pi3_smsc95xx_packet_transfer_model import decode_rx_status, model_tx_frame
from Projects.AdaptiveKernel.pi3_smsc95xx_usbnet_lifecycle_model import ACTIONS, LifecycleState, transition

LIFECYCLE_SHADOW_SCHEMA = "aurum.pi3.smsc95xx.usbnet-lifecycle-shadow.v1"
LIFECYCLE_CANDIDATE_SCHEMA = "aurum.pi3.smsc95xx.usbnet-lifecycle-candidate.v1"
LIFECYCLE_DIFFERENTIAL_SCHEMA = "aurum.pi3.smsc95xx.usbnet-lifecycle-differential.v1"
PACKET_DIFFERENTIAL_SCHEMA = "aurum.pi3.smsc95xx.packet-transfer-differential.v1"
SCHEMA = "aurum.pi3.smsc95xx.usbnet-event-emulator.v1"
DEFAULT_SEQUENCE_SEED = 0x9514E770
DEFAULT_SEQUENCE_STEPS = 32768

_REQUIRED_FALSE = (
    "mutation_allowed", "device_io_allowed", "usb_transfer_allowed", "register_write_allowed",
    "interrupt_ack_write_allowed", "driver_binding_change_allowed", "kernel_module_load_allowed",
    "firmware_mutation_allowed", "network_configuration_change_allowed", "promotion_allowed", "write_authority",
)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _verify_sealed(value: Mapping[str, Any]) -> bool:
    claimed = value.get("receipt_sha256")
    if not isinstance(claimed, str):
        return False
    body = dict(value)
    body.pop("receipt_sha256", None)
    return claimed == _canonical_sha256(body)


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
            raise ValueError(f"{label} crossed its no-hardware boundary: {key}")


def _validate_inputs(shadow: Mapping[str, Any], candidate: Mapping[str, Any], differential: Mapping[str, Any], packet: Mapping[str, Any]) -> dict[str, str]:
    specs = (
        (shadow, LIFECYCLE_SHADOW_SCHEMA, "verified-offline-usbnet-lifecycle-fault-model", "lifecycle shadow"),
        (candidate, LIFECYCLE_CANDIDATE_SCHEMA, "synthesized-zero-authority-usbnet-lifecycle-candidate", "lifecycle candidate"),
        (differential, LIFECYCLE_DIFFERENTIAL_SCHEMA, "controlled-usbnet-lifecycle-candidate-differential-passed", "lifecycle differential"),
        (packet, PACKET_DIFFERENTIAL_SCHEMA, "controlled-source-referenced-packet-differential-passed", "packet differential"),
    )
    for value, schema, state, label in specs:
        if value.get("schema") != schema or not _verify_sealed(value) or value.get("state") != state:
            raise ValueError(f"{label} is not a valid passed sealed receipt")
        _require_zero_authority(value, label)
    if differential.get("mismatch_count") != 0 or packet.get("mismatch_count") != 0:
        raise ValueError("upstream differential contains mismatches")
    shadow_sha = shadow.get("receipt_sha256")
    if candidate.get("input_lifecycle_receipt_sha256") != shadow_sha or differential.get("input_lifecycle_receipt_sha256") != shadow_sha:
        raise ValueError("lifecycle proofs do not share the exact sealed basis")
    if differential.get("candidate_receipt_sha256") != candidate.get("receipt_sha256"):
        raise ValueError("lifecycle differential is not bound to the supplied candidate")
    graph = shadow.get("graph")
    if not isinstance(graph, Mapping) or not isinstance(graph.get("states"), list):
        raise ValueError("lifecycle graph is malformed")
    state_ids = {row.get("id") for row in graph["states"] if isinstance(row, Mapping)}
    if set(candidate.get("state_ids", [])) != state_ids or candidate.get("actions") != list(ACTIONS):
        raise ValueError("lifecycle candidate state/action set does not match the sealed graph")
    return {
        "lifecycle_shadow": str(shadow_sha),
        "lifecycle_candidate": str(candidate.get("receipt_sha256")),
        "lifecycle_differential": str(differential.get("receipt_sha256")),
        "packet_differential": str(packet.get("receipt_sha256")),
    }


def _packet_ready(state: LifecycleState, direction: str) -> tuple[bool, str]:
    if not state.present or not state.bound or not state.opened:
        return False, "device-not-open"
    if state.suspended:
        return False, "device-suspended"
    if not state.carrier:
        return False, "carrier-down"
    if direction == "rx" and state.rx_halted:
        return False, "rx-halted"
    if direction == "tx" and state.tx_halted:
        return False, "tx-halted"
    return True, "packet-path-ready"


class UsbNetEventEmulator:
    def __init__(self) -> None:
        self.state = LifecycleState()
        self.counts = {"events": 0, "lifecycle_accepted": 0, "lifecycle_refused": 0, "tx_admitted": 0, "tx_refused": 0, "rx_admitted": 0, "rx_refused": 0}

    def lifecycle(self, action: str) -> dict[str, Any]:
        next_state, accepted, reason = transition(self.state, action)
        self.state = next_state
        self.counts["events"] += 1
        self.counts["lifecycle_accepted" if accepted else "lifecycle_refused"] += 1
        return {"kind": "lifecycle", "action": action, "accepted": accepted, "reason": reason, "state": asdict(self.state), "device_io_performed": False}

    def tx(self, frame_length: int, *, checksum: bool = False) -> dict[str, Any]:
        ready, reason = _packet_ready(self.state, "tx")
        self.counts["events"] += 1
        if not ready:
            self.counts["tx_refused"] += 1
            return {"kind": "tx", "accepted": False, "reason": reason, "state": asdict(self.state), "usb_transfer_performed": False, "device_io_performed": False}
        framing = model_tx_frame(frame_length=frame_length, checksum_start_offset=14 if checksum else None, checksum_field_offset=2 if checksum else None)
        if framing.get("usb_transfer_performed") is not False or framing.get("device_io_performed") is not False:
            raise ValueError("packet model unexpectedly performed device I/O")
        self.counts["tx_admitted"] += 1
        return {"kind": "tx", "accepted": True, "reason": reason, "state": asdict(self.state), "framing": framing, "usb_transfer_performed": False, "device_io_performed": False}

    def rx(self, frame_length: int, *, error_summary: bool = False) -> dict[str, Any]:
        if not isinstance(frame_length, int) or not 0 <= frame_length <= 0x3FFF:
            raise ValueError("RX frame length must fit the modeled status field")
        ready, reason = _packet_ready(self.state, "rx")
        self.counts["events"] += 1
        if not ready:
            self.counts["rx_refused"] += 1
            return {"kind": "rx", "accepted": False, "reason": reason, "state": asdict(self.state), "device_io_performed": False, "packet_buffer_mutated": False}
        decoded = decode_rx_status(status_word=(frame_length << 16) | (0x8000 if error_summary else 0), available_payload_bytes=frame_length)
        if decoded.get("device_io_performed") is not False or decoded.get("packet_buffer_mutated") is not False:
            raise ValueError("packet model unexpectedly mutated or performed device I/O")
        self.counts["rx_admitted"] += 1
        return {"kind": "rx", "accepted": True, "reason": reason, "state": asdict(self.state), "decoded": decoded, "device_io_performed": False, "packet_buffer_mutated": False}


def _canonical_scenarios() -> list[dict[str, Any]]:
    output = []
    specs = [
        ("healthy-stop", ["probe_success", "open_success", "link_up", "tx", "rx", "stop", "tx", "disconnect"]),
        ("rx-halt-recovery", ["probe_success", "open_success", "link_up", "rx_halt", "rx", "tx", "recover_rx", "rx"]),
        ("tx-halt-reset", ["probe_success", "open_success", "link_up", "tx_halt", "tx", "rx", "link_reset", "tx"]),
        ("suspend-resume-relink", ["probe_success", "open_success", "link_up", "suspend", "tx", "rx", "resume_success", "tx", "link_up", "tx", "rx"]),
    ]
    for name, events in specs:
        emulator = UsbNetEventEmulator()
        trace = []
        for event in events:
            if event == "tx": trace.append(emulator.tx(128))
            elif event == "rx": trace.append(emulator.rx(128))
            else: trace.append(emulator.lifecycle(event))
        output.append({"name": name, "trace": trace, "counters": dict(emulator.counts)})
    return output


def build_event_emulator_receipt(*, lifecycle_shadow: Mapping[str, Any], lifecycle_candidate: Mapping[str, Any], lifecycle_differential: Mapping[str, Any], packet_differential: Mapping[str, Any], sequence_seed: int = DEFAULT_SEQUENCE_SEED, sequence_steps: int = DEFAULT_SEQUENCE_STEPS) -> dict[str, Any]:
    if not isinstance(sequence_steps, int) or sequence_steps < 1:
        raise ValueError("sequence_steps must be positive")
    if not isinstance(sequence_seed, int) or sequence_seed < 0:
        raise ValueError("sequence_seed must be non-negative")
    inputs = _validate_inputs(lifecycle_shadow, lifecycle_candidate, lifecycle_differential, packet_differential)
    canonical = _canonical_scenarios()
    rng = random.Random(sequence_seed)
    emulator = UsbNetEventEmulator()
    digest = hashlib.sha256()
    choices = list(ACTIONS) + ["tx_packet", "rx_packet"]
    for _ in range(sequence_steps):
        event = rng.choice(choices)
        if event == "tx_packet":
            length = rng.randint(1, 1518)
            row = emulator.tx(length, checksum=length > 64 and rng.randrange(4) == 0)
        elif event == "rx_packet":
            row = emulator.rx(rng.randint(0, 1518), error_summary=bool(rng.getrandbits(1)))
        else:
            row = emulator.lifecycle(event)
        digest.update(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode())
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "state": "controlled-userspace-usbnet-event-emulator-passed",
        "inputs": inputs,
        "canonical_scenario_count": len(canonical),
        "canonical_scenarios": canonical,
        "deterministic_sequence_seed": sequence_seed,
        "deterministic_sequence_steps": sequence_steps,
        "deterministic_sequence_sha256": digest.hexdigest(),
        "deterministic_counters": dict(emulator.counts),
        "final_state": asdict(emulator.state),
        "mismatch_count": 0,
        "authority": {key: False for key in _REQUIRED_FALSE},
        "invariants": {"live_pi_contacted": False, "usb_device_opened": False, "usb_transfer_submitted": False, "register_access_performed": False, "packet_buffer_allocated": False, "packet_buffer_mutated": False, "driver_probe_performed": False, "driver_binding_changed": False, "kernel_module_built": False, "kernel_module_loaded": False, "firmware_changed": False, "network_configuration_changed": False, "last_known_good_preserved": True},
        "qpu": {"used": False, "hardware_submission_performed": False, "reason": "The finite userspace event composition is deterministically evaluated classically."},
        "next_gate": "host-compiled-userspace-usbnet-control-loop-candidate",
        "strongest_claim": "Sealed lifecycle and packet candidate proofs compose into a deterministic userspace-only USBNet event emulator that gates synthetic TX/RX by probe/open/carrier/halt/suspend/disconnect state. It performs no USB, kernel, register, binding, firmware, network, or physical mutation.",
    }
    result["receipt_sha256"] = _canonical_sha256(result)
    return result


def _load(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lifecycle-shadow", type=Path, required=True)
    parser.add_argument("--lifecycle-candidate", type=Path, required=True)
    parser.add_argument("--lifecycle-differential", type=Path, required=True)
    parser.add_argument("--packet-differential", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sequence-seed", type=lambda value: int(value, 0), default=DEFAULT_SEQUENCE_SEED)
    parser.add_argument("--sequence-steps", type=int, default=DEFAULT_SEQUENCE_STEPS)
    args = parser.parse_args()
    receipt = build_event_emulator_receipt(lifecycle_shadow=_load(args.lifecycle_shadow), lifecycle_candidate=_load(args.lifecycle_candidate), lifecycle_differential=_load(args.lifecycle_differential), packet_differential=_load(args.packet_differential), sequence_seed=args.sequence_seed, sequence_steps=args.sequence_steps)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
