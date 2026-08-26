"""Refine sealed Pi3 reference correlation with fresh read-only physical evidence.

This stage consumes only durable repository receipts. It cannot contact the Pi,
change a driver binding, load a module, mutate firmware/network state, or grant
promotion/mutation authority. Its purpose is to close reference gaps only when a
fresh physical fingerprint explicitly proves them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "aurum-pi3-reference-correlation-refinement-v1"
BASE_SCHEMA = "aurum-pi3-reference-correlation-v1"
FINGERPRINT_SCHEMA = "aurum.pi3.controller-link-fingerprint.v1"
EXPECTED_MODEL = "Raspberry Pi 3 Model B Rev 1.2"
EXPECTED_SERIAL = "00000000a6a7df7f"
EXPECTED_KERNEL = "6.18.34+rpt-rpi-v8"
EXPECTED_DRIVER = "smsc95xx"
_REQUIRED_FALSE = (
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


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _verify_sealed_receipt(value: Mapping[str, Any]) -> bool:
    claimed = value.get("receipt_sha256")
    if not isinstance(claimed, str):
        return False
    unsealed = dict(value)
    unsealed.pop("receipt_sha256", None)
    return claimed == _canonical_sha256(unsealed)


def verify_fingerprint_receipt(value: Mapping[str, Any]) -> bool:
    return _verify_sealed_receipt(value)


def verify_refinement_receipt(value: Mapping[str, Any]) -> bool:
    return _verify_sealed_receipt(value)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _false_authority(authority: Mapping[str, Any]) -> bool:
    return all(authority.get(key) is False for key in _REQUIRED_FALSE)


def refine_reference_correlation(
    base: Mapping[str, Any], fingerprint: Mapping[str, Any]
) -> dict[str, Any]:
    if base.get("schema") != BASE_SCHEMA or not _verify_sealed_receipt(base):
        raise ValueError("base reference correlation is not a valid sealed receipt")
    if fingerprint.get("schema") != FINGERPRINT_SCHEMA or not verify_fingerprint_receipt(fingerprint):
        raise ValueError("Pi3 fingerprint is not a valid sealed receipt")
    if fingerprint.get("state") != "completed-read-only-fingerprint":
        raise ValueError("Pi3 fingerprint must be complete and non-quarantined")

    target = _mapping(fingerprint.get("target"), "fingerprint target")
    ethernet = _mapping(fingerprint.get("ethernet"), "fingerprint ethernet")
    provenance = _mapping(fingerprint.get("provenance"), "fingerprint provenance")
    checks = _mapping(fingerprint.get("checks"), "fingerprint checks")
    authority = _mapping(fingerprint.get("authority"), "fingerprint authority")

    if not _false_authority(authority):
        raise ValueError("fingerprint must carry explicit zero authority")
    expected_target = {
        "model": EXPECTED_MODEL,
        "serial": EXPECTED_SERIAL,
        "kernel": EXPECTED_KERNEL,
    }
    for key, expected in expected_target.items():
        if target.get(key) != expected:
            raise ValueError(f"fingerprint target {key} does not match pinned reference")
    if ethernet.get("driver") != EXPECTED_DRIVER:
        raise ValueError("fingerprint reference driver does not match pinned reference")

    required_checks = (
        "pinned_identity_match",
        "protected_driver_match",
        "usb_function_identity_observed",
        "parent_hub_identity_observed",
        "lan9514_parent_hub_match",
        "link_speed_observed",
        "link_speed_within_fast_ethernet",
        "duplex_observed",
        "running_image_package_observed",
        "driver_kernel_config_observed",
        "driver_binary_provenance_observed",
    )
    missing_checks = [name for name in required_checks if checks.get(name) is not True]
    if missing_checks:
        raise ValueError(
            "fingerprint is missing required read-only proof: " + ", ".join(missing_checks)
        )

    if str(ethernet.get("parent_hub_vendor_id", "")).lower() != "0424" or str(
        ethernet.get("parent_hub_product_id", "")
    ).lower() != "9514":
        raise ValueError("fingerprint LAN9514 parent-hub identity does not match")
    if str(ethernet.get("usb_vendor_id", "")).lower() != "0424" or str(
        ethernet.get("usb_product_id", "")
    ).lower() != "ec00":
        raise ValueError("fingerprint Ethernet function identity does not match")

    speed = ethernet.get("speed_mbps")
    try:
        speed_mbps = int(speed)
    except (TypeError, ValueError) as exc:
        raise ValueError("fingerprint negotiated speed is invalid") from exc
    if speed_mbps != 100 or str(ethernet.get("duplex", "")).lower() != "full":
        raise ValueError("fingerprint negotiated link is outside the proven 100/full reference")

    base_correlation = _mapping(base.get("correlation"), "base correlation")
    raw_agreements = base_correlation.get("agreements")
    raw_gaps = base_correlation.get("gaps")
    if not isinstance(raw_agreements, list) or not isinstance(raw_gaps, list):
        raise ValueError("base correlation agreements/gaps are malformed")

    closed_gap_ids = {"controller-identity", "negotiated-link-speed"}
    remaining_gaps = [
        dict(item)
        for item in raw_gaps
        if isinstance(item, Mapping) and item.get("id") not in closed_gap_ids
    ]
    if len(remaining_gaps) != len(raw_gaps) - 2:
        raise ValueError("base correlation does not contain the expected refinable gaps")

    agreements = [dict(item) for item in raw_agreements if isinstance(item, Mapping)]
    agreements.extend(
        [
            {
                "id": "lan9514-controller-assembly",
                "state": "agrees",
                "reference": "LAN9514 reference identifies USB hub 0424:9514 with SMSC95xx Ethernet function 0424:ec00",
                "physical": "pinned Pi3 sysfs topology observed parent hub 0424:9514 and Ethernet function 0424:ec00",
            },
            {
                "id": "negotiated-fast-ethernet-link",
                "state": "agrees",
                "reference": "LAN9514 Ethernet capability is 10/100",
                "physical": "pinned Pi3 negotiated 100 Mbps full duplex on protected smsc95xx",
            },
        ]
    )

    running_package = str(provenance.get("running_image_package") or "")
    running_record = str(provenance.get("running_image_package_record") or "")
    driver_config = str(provenance.get("driver_kernel_config") or "")
    for gap in remaining_gaps:
        if gap.get("id") == "running-driver-source-provenance":
            gap["reason"] = (
                "the exact installed running-image package and built-in smsc95xx kernel-config mode are now observed, "
                "but source-commit/build-to-running-binary equivalence is not yet established"
            )
            gap["observed_package"] = running_package
            gap["observed_package_record"] = running_record
            gap["observed_driver_kernel_config"] = driver_config
            gap["next_evidence"] = "exact package source/build commit equivalence"

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "state": "completed",
        "semantic_state": "completed-with-two-actionable-reference-gaps",
        "processing": {
            "placement": "repository-receipt-refinement",
            "live_pi_contacted": False,
            "physical_mutation_authority": False,
            "qpu_hardware_contacted": False,
        },
        "inputs": {
            "base_reference_correlation_sha256": base.get("receipt_sha256"),
            "fingerprint_receipt_sha256": fingerprint.get("receipt_sha256"),
            "fingerprint_source_commit": fingerprint.get("source_commit"),
            "fingerprint_source_run_id": fingerprint.get("source_run_id"),
        },
        "physical_observation": {
            "model": target.get("model"),
            "serial": target.get("serial"),
            "kernel": target.get("kernel"),
            "reference_driver": ethernet.get("driver"),
            "usb_parent_hub": {
                "vendor_id": str(ethernet.get("parent_hub_vendor_id", "")).lower(),
                "product_id": str(ethernet.get("parent_hub_product_id", "")).lower(),
            },
            "usb_ethernet_function": {
                "vendor_id": str(ethernet.get("usb_vendor_id", "")).lower(),
                "product_id": str(ethernet.get("usb_product_id", "")).lower(),
            },
            "negotiated_link": {
                "speed_mbps": speed_mbps,
                "duplex": str(ethernet.get("duplex", "")).lower(),
                "carrier": str(ethernet.get("carrier", "")),
            },
            "running_image_package": running_package,
            "driver_kernel_config": driver_config,
        },
        "correlation": {
            "agreement_count": len(agreements),
            "agreements": agreements,
            "closed_gap_ids": sorted(closed_gap_ids),
            "gap_count": len(remaining_gaps),
            "gaps": remaining_gaps,
        },
        "invariants": {
            "last_known_good_preserved": True,
            "reference_driver_preserved": True,
            "live_pi_contacted_by_refinement": False,
            "driver_binding_changed": False,
            "kernel_changed": False,
            "firmware_changed": False,
            "network_configuration_changed": False,
            "mutation_authority_granted": False,
            "promotion_authority_granted": False,
        },
        "proposal": {
            "physical_driver_change": "no-change",
            "selected_physical_driver": EXPECTED_DRIVER,
            "state": "held-for-source-equivalence-and-functional-model",
            "next_experiment": "resolve-running-kernel-source-equivalence-and-offline-functional-driver-model",
            "next_experiment_inputs": [
                "exact package source/build commit equivalence",
                "offline functional smsc95xx/LAN9514 behavior model",
            ],
        },
        "strongest_claim": (
            "Fresh sealed read-only physical evidence closes the exact LAN9514 controller-assembly and negotiated-link gaps: "
            "the pinned Pi3 exposes parent hub 0424:9514, Ethernet function 0424:ec00, and a 100 Mbps full-duplex smsc95xx link. "
            "Two stronger proofs remain: source/build equivalence for the running kernel image and functional candidate-driver hardware behavior. "
            "No mutation or promotion authority is created."
        ),
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--fingerprint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    receipt = refine_reference_correlation(_load(args.base), _load(args.fingerprint))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "AURUM_PI3_REFERENCE_REFINEMENT "
        f"agreements={receipt['correlation']['agreement_count']} "
        f"gaps={receipt['correlation']['gap_count']} "
        "mutation_authority=false promotion_authority=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
