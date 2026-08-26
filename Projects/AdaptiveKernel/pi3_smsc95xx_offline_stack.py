"""Build the sealed Pi3 smsc95xx register/interrupt/packet offline stack.

The stack is deliberately host-only. It consumes the already verified functional
model and ARM64 nonbinding-candidate receipt, then derives reference-pinned
register, interrupt, USB-control, TX, and RX semantics without opening a device or
granting any mutation, binding, module-load, or promotion authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from Projects.AdaptiveKernel.pi3_smsc95xx_candidate_cloud import (
    SCHEMA as CLOUD_CANDIDATE_SCHEMA,
    _verify_sealed as verify_cloud_candidate,
)
from Projects.AdaptiveKernel.pi3_smsc95xx_packet_transfer_model import (
    build_packet_transfer_model,
    decode_rx_status,
    model_register_transfer,
    model_tx_frame,
)
from Projects.AdaptiveKernel.pi3_smsc95xx_register_interrupt_candidate import (
    run_differential,
    synthesize_candidate,
)
from Projects.AdaptiveKernel.pi3_smsc95xx_register_interrupt_model import (
    build_register_interrupt_model,
)

SCHEMA = "aurum.pi3.smsc95xx.offline-stack.v2"

_REQUIRED_FALSE = (
    "mutation_allowed",
    "device_io_allowed",
    "usb_transfer_allowed",
    "register_write_allowed",
    "interrupt_ack_write_allowed",
    "driver_binding_change_allowed",
    "kernel_module_load_allowed",
    "firmware_mutation_allowed",
    "network_configuration_change_allowed",
    "promotion_allowed",
    "write_authority",
)

_CLOUD_REQUIRED_FALSE = (
    "mutation_allowed",
    "driver_binding_change_allowed",
    "kernel_module_load_allowed",
    "firmware_mutation_allowed",
    "network_configuration_change_allowed",
    "promotion_allowed",
    "write_authority",
)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _verify_sealed(value: Mapping[str, Any]) -> bool:
    claimed = value.get("receipt_sha256")
    if not isinstance(claimed, str):
        return False
    body = dict(value)
    body.pop("receipt_sha256", None)
    return claimed == _canonical_sha256(body)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _require_false(mapping: Mapping[str, Any], keys: tuple[str, ...], label: str) -> None:
    for key in keys:
        if mapping.get(key) is not False:
            raise ValueError(f"{label} must keep {key}=false")


def build_offline_stack(
    *,
    functional_model: Mapping[str, Any],
    cloud_candidate: Mapping[str, Any],
    reference_manifest: Mapping[str, Any],
    rpi_smsc95xx_h: str,
    upstream_smsc95xx_h: str,
    cc: str | None = None,
) -> dict[str, Any]:
    if cloud_candidate.get("schema") != CLOUD_CANDIDATE_SCHEMA or not verify_cloud_candidate(cloud_candidate):
        raise ValueError("cloud candidate must be a valid sealed receipt")
    if cloud_candidate.get("state") != "verified-cloud-arm64-nonbinding-candidate":
        raise ValueError("cloud ARM64 candidate gate has not passed")
    cloud_inputs = cloud_candidate.get("inputs")
    if not isinstance(cloud_inputs, Mapping):
        raise ValueError("cloud candidate inputs are malformed")
    if cloud_inputs.get("functional_model_receipt_sha256") != functional_model.get("receipt_sha256"):
        raise ValueError("cloud candidate and functional model receipts do not match")
    cloud_authority = cloud_candidate.get("authority")
    if not isinstance(cloud_authority, Mapping):
        raise ValueError("cloud candidate authority is malformed")
    _require_false(cloud_authority, _CLOUD_REQUIRED_FALSE, "cloud candidate")
    cloud_invariants = cloud_candidate.get("invariants")
    if not isinstance(cloud_invariants, Mapping):
        raise ValueError("cloud candidate invariants are malformed")
    _require_false(
        cloud_invariants,
        (
            "live_pi_contacted",
            "kernel_module_built",
            "kernel_module_loaded",
            "driver_binding_changed",
            "kernel_changed",
            "firmware_changed",
            "network_configuration_changed",
            "mutation_authority_granted",
            "promotion_authority_granted",
        ),
        "cloud candidate invariants",
    )
    cloud_qpu = cloud_candidate.get("qpu")
    if not isinstance(cloud_qpu, Mapping):
        raise ValueError("cloud candidate QPU evidence is malformed")
    _require_false(cloud_qpu, ("used", "hardware_submission_performed"), "cloud candidate QPU evidence")

    register_model = build_register_interrupt_model(
        functional_model,
        reference_manifest,
        rpi_smsc95xx_h,
        upstream_smsc95xx_h,
    )
    candidate_source, candidate_receipt = synthesize_candidate(register_model)
    differential = run_differential(register_model, cc=cc)
    packet_model = build_packet_transfer_model(register_model)

    if differential.get("candidate_receipt_sha256") != candidate_receipt.get("receipt_sha256"):
        raise ValueError("register candidate and differential receipts do not match")
    if differential.get("input_register_model_receipt_sha256") != register_model.get("receipt_sha256"):
        raise ValueError("register differential is not bound to the register model")
    if packet_model.get("input_register_model_receipt_sha256") != register_model.get("receipt_sha256"):
        raise ValueError("packet shadow is not bound to the register model")

    register_intent = [
        model_register_transfer(direction="read", register_index=0x08),
        model_register_transfer(direction="read", register_index=0x68),
        model_register_transfer(direction="write", register_index=0x10, value=0x00000004),
    ]
    tx_scenarios = []
    for frame_length in (64, 512, 1500):
        tx_scenarios.append(model_tx_frame(frame_length=frame_length))
        tx_scenarios.append(
            model_tx_frame(
                frame_length=frame_length,
                checksum_start_offset=34,
                checksum_field_offset=16,
            )
        )
    rx_scenarios = [
        decode_rx_status(status_word=64 << 16, available_payload_bytes=64),
        decode_rx_status(status_word=1500 << 16, available_payload_bytes=1500),
        decode_rx_status(status_word=(512 << 16) | 0x00008000, available_payload_bytes=500),
    ]
    if any(item.get("device_io_performed") is not False for item in register_intent + tx_scenarios + rx_scenarios):
        raise ValueError("packet shadow unexpectedly performed device I/O")
    if any(item.get("usb_transfer_performed") is not False for item in register_intent + tx_scenarios):
        raise ValueError("packet shadow unexpectedly submitted a USB transfer")

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "state": "verified-offline-register-interrupt-packet-stack",
        "inputs": {
            "functional_model_receipt_sha256": functional_model.get("receipt_sha256"),
            "cloud_arm64_candidate_receipt_sha256": cloud_candidate.get("receipt_sha256"),
            "register_model_receipt_sha256": register_model.get("receipt_sha256"),
            "register_candidate_receipt_sha256": candidate_receipt.get("receipt_sha256"),
            "register_differential_receipt_sha256": differential.get("receipt_sha256"),
            "packet_model_receipt_sha256": packet_model.get("receipt_sha256"),
        },
        "verification": {
            "rpi_upstream_register_define_mismatches": register_model["verification"][
                "rpi_upstream_define_mismatches"
            ],
            "register_interrupt_differential_scenarios": differential["scenario_count"],
            "register_interrupt_differential_mismatches": differential["mismatch_count"],
            "register_control_intent_scenarios": len(register_intent),
            "tx_packet_scenarios": len(tx_scenarios),
            "rx_packet_scenarios": len(rx_scenarios),
            "host_compiled_register_decoder": differential["verification"]["host_compilation"],
            "usb_transfer_submitted": False,
        },
        "qpu": {
            "preserved_router_available": bool(cloud_qpu.get("preserved_router_available")),
            "used": False,
            "hardware_submission_performed": False,
            "reason": "The bounded deterministic register and packet matrices are exhaustively evaluated classically.",
        },
        "authority": {key: False for key in _REQUIRED_FALSE},
        "invariants": {
            "live_pi_contacted": False,
            "usb_device_opened": False,
            "usb_transfer_submitted": False,
            "register_read_performed": False,
            "register_write_performed": False,
            "interrupt_ack_write_performed": False,
            "kernel_module_built": False,
            "kernel_module_loaded": False,
            "driver_binding_changed": False,
            "kernel_changed": False,
            "firmware_changed": False,
            "network_configuration_changed": False,
            "last_known_good_preserved": True,
        },
        "next_gate": "source-referenced-packet-transfer-differential-and-bounded-fuzz-expansion",
        "strongest_claim": (
            "The sealed Pi3 smsc95xx offline stack now extends the verified ARM64 nonbinding candidate through "
            "hash-pinned register and interrupt semantics, a compiled C decoder differential, and deterministic USB "
            "control/TX/RX packet shadows. It remains host-only and is not a kernel module, device driver, hardware "
            "digital twin, binding proof, or promotion authorization."
        ),
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return {
        "register_model": register_model,
        "register_candidate_source": candidate_source,
        "register_candidate_receipt": candidate_receipt,
        "register_differential": differential,
        "packet_model": packet_model,
        "stack_receipt": receipt,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--functional-model", required=True, type=Path)
    parser.add_argument("--cloud-candidate", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--rpi-header", required=True, type=Path)
    parser.add_argument("--upstream-header", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--cc")
    args = parser.parse_args()

    result = build_offline_stack(
        functional_model=_load(args.functional_model),
        cloud_candidate=_load(args.cloud_candidate),
        reference_manifest=_load(args.manifest),
        rpi_smsc95xx_h=args.rpi_header.read_text(encoding="utf-8"),
        upstream_smsc95xx_h=args.upstream_header.read_text(encoding="utf-8"),
        cc=args.cc,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "register-interrupt-shadow.json": result["register_model"],
        "register-interrupt-candidate.json": result["register_candidate_receipt"],
        "register-interrupt-differential.json": result["register_differential"],
        "packet-transfer-shadow.json": result["packet_model"],
        "offline-stack-v2.json": result["stack_receipt"],
    }
    for filename, value in outputs.items():
        (args.output_dir / filename).write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    (args.output_dir / "register-interrupt-candidate.c").write_text(
        result["register_candidate_source"],
        encoding="utf-8",
    )
    receipt = result["stack_receipt"]
    print(
        "AURUM_PI3_SMSC95XX_OFFLINE_STACK "
        f"state={receipt['state']} "
        f"register_scenarios={receipt['verification']['register_interrupt_differential_scenarios']} "
        "live_pi_contacted=false mutation_authority=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
