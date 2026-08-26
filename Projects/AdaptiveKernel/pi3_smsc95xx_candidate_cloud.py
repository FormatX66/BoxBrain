"""Seal GitHub-hosted host/differential/AArch64 evidence for the Pi3 candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "aurum.pi3.smsc95xx.candidate-cloud-verification.v1"
CANDIDATE_SCHEMA = "aurum.pi3.smsc95xx.nonbinding-candidate.v1"
DIFFERENTIAL_SCHEMA = "aurum.pi3.smsc95xx.candidate-differential.v1"
QPU_SCHEMA = "aurum-pi3-qpu-routing-reference-v1"


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def seal_cloud_candidate(
    *,
    candidate: Mapping[str, Any],
    differential: Mapping[str, Any],
    qpu: Mapping[str, Any],
    source_path: Path,
    arm64_object_path: Path,
    arm64_readelf_path: Path,
    arm64_undefined_path: Path,
) -> dict[str, Any]:
    if candidate.get("schema") != CANDIDATE_SCHEMA or not _verify_sealed(candidate):
        raise ValueError("candidate is not a valid sealed receipt")
    if candidate.get("state") != "verified-nonbinding-shadow-candidate":
        raise ValueError("candidate host verification did not pass")
    if differential.get("schema") != DIFFERENTIAL_SCHEMA or not _verify_sealed(differential):
        raise ValueError("differential result is not a valid sealed receipt")
    if differential.get("state") != "controlled-differential-passed":
        raise ValueError("candidate/model differential did not pass")
    if qpu.get("schema") != QPU_SCHEMA or not _verify_sealed(qpu):
        raise ValueError("QPU routing reference is not a valid sealed receipt")

    source_sha = _sha256_file(source_path)
    if source_sha != candidate.get("source_sha256"):
        raise ValueError("generated source does not match the sealed candidate")
    if source_sha != differential.get("candidate_source_sha256"):
        raise ValueError("differential result used a different candidate source")
    if differential.get("input_functional_model_receipt_sha256") != candidate.get(
        "input_functional_model_receipt_sha256"
    ):
        raise ValueError("candidate and differential are not bound to the same model")

    verification = differential.get("verification")
    if not isinstance(verification, Mapping) or not all(
        verification.get(key) is True
        for key in (
            "host_compilation",
            "shared_library_execution",
            "candidate_vs_model_differential",
            "exact_identity_covered",
            "wrong_identity_rejection_covered",
            "all_proven_link_modes_covered",
            "unproven_gigabit_rejection_covered",
            "rx_checksum_transitions_covered",
            "tx_framing_payload_matrix_covered",
        )
    ):
        raise ValueError("differential verification is incomplete")
    agreement_count = int(differential.get("agreement_count", 0))
    if agreement_count != 18 or int(differential.get("mismatch_count", -1)) != 0:
        raise ValueError("expected exactly 18 agreements and zero mismatches")

    readelf = arm64_readelf_path.read_text(encoding="utf-8-sig")
    if "Type:                              REL" not in readelf:
        raise ValueError("candidate object is not relocatable")
    if "Machine:                           AArch64" not in readelf:
        raise ValueError("candidate object is not AArch64")
    undefined = arm64_undefined_path.read_text(encoding="utf-8-sig").strip()
    if undefined:
        raise ValueError("candidate object has undefined external symbols")

    qpu_model = qpu.get("model")
    if not isinstance(qpu_model, Mapping):
        raise ValueError("QPU model payload is malformed")
    if qpu_model.get("hardware_digital_twin") is not False:
        raise ValueError("QPU router must not be treated as a hardware twin")
    if qpu_model.get("hardware_submission_performed") is not False:
        raise ValueError("unexpected QPU hardware submission")

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "state": "verified-cloud-arm64-nonbinding-candidate",
        "inputs": {
            "candidate_receipt_sha256": candidate.get("receipt_sha256"),
            "differential_receipt_sha256": differential.get("receipt_sha256"),
            "functional_model_receipt_sha256": candidate.get(
                "input_functional_model_receipt_sha256"
            ),
            "qpu_reference_receipt_sha256": qpu.get("receipt_sha256"),
        },
        "candidate": {
            "kind": candidate.get("candidate_kind"),
            "source_sha256": source_sha,
            "arm64_object_sha256": _sha256_file(arm64_object_path),
            "arm64_object_type": "ELF64 AArch64 relocatable",
            "undefined_external_symbols": 0,
        },
        "verification": {
            "host_compile_and_harness": True,
            "candidate_vs_model_agreements": agreement_count,
            "candidate_vs_model_mismatches": 0,
            "aarch64_cross_compile": True,
            "exact_controller_and_rejection_paths": True,
            "proven_link_envelope_and_rejection_paths": True,
            "rx_checksum_transitions": True,
            "tx_framing_matrix": True,
            "kernel_module": False,
            "device_binding_path": False,
        },
        "qpu": {
            "preserved_router_available": True,
            "used": False,
            "hardware_submission_performed": False,
            "reason": (
                "The bounded 18-case differential matrix is exhaustively and exactly "
                "evaluated classically; the preserved QPU artifact routes experiments "
                "and is not a LAN9514 hardware model."
            ),
        },
        "invariants": {
            "live_pi_contacted": False,
            "device_io_performed": False,
            "kernel_module_built": False,
            "kernel_module_loaded": False,
            "driver_binding_changed": False,
            "kernel_changed": False,
            "firmware_changed": False,
            "network_configuration_changed": False,
            "last_known_good_preserved": True,
            "mutation_authority_granted": False,
            "promotion_authority_granted": False,
        },
        "authority": {
            "mutation_allowed": False,
            "driver_binding_change_allowed": False,
            "kernel_module_load_allowed": False,
            "firmware_mutation_allowed": False,
            "network_configuration_change_allowed": False,
            "promotion_allowed": False,
            "write_authority": False,
        },
        "next_gate": "expand-register-reset-rx-status-and-interrupt-shadow-behavior",
        "strongest_claim": (
            "The Aurum-generated nonbinding C candidate passed an 18-case differential "
            "matrix against the sealed LAN9514/smsc95xx functional model and cross-compiled "
            "to an AArch64 relocatable object with no undefined external symbols. It is "
            "still a host-only shadow core, not a kernel module or bindable device driver, "
            "and grants no physical mutation or promotion authority."
        ),
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--differential", required=True, type=Path)
    parser.add_argument("--qpu", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--arm64-object", required=True, type=Path)
    parser.add_argument("--arm64-readelf", required=True, type=Path)
    parser.add_argument("--arm64-undefined", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    receipt = seal_cloud_candidate(
        candidate=_load(args.candidate),
        differential=_load(args.differential),
        qpu=_load(args.qpu),
        source_path=args.source,
        arm64_object_path=args.arm64_object,
        arm64_readelf_path=args.arm64_readelf,
        arm64_undefined_path=args.arm64_undefined,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "AURUM_PI3_SMSC95XX_CANDIDATE_CLOUD "
        f"state={receipt['state']} agreements=18 arm64=true "
        "live_pi_contacted=false mutation_authority=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
