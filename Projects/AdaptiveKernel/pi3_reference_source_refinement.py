"""Close the Pi3 running-driver source-provenance gap from sealed package evidence.

This is a repository-only refinement stage. It consumes the existing sealed
controller/link reference-correlation receipt plus a sealed official-package
equivalence receipt. It never contacts hardware and cannot grant mutation,
driver-binding, kernel-load, or promotion authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "aurum-pi3-reference-source-refinement-v1"
BASE_SCHEMA = "aurum-pi3-reference-correlation-refinement-v1"
EQUIVALENCE_SCHEMA = "aurum.pi3.source-equivalence.v1"
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


def _verify_sealed(value: Mapping[str, Any]) -> bool:
    claimed = value.get("receipt_sha256")
    if not isinstance(claimed, str):
        return False
    body = dict(value)
    body.pop("receipt_sha256", None)
    return claimed == _canonical_sha256(body)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def refine_source_provenance(
    base: Mapping[str, Any], equivalence: Mapping[str, Any]
) -> dict[str, Any]:
    if base.get("schema") != BASE_SCHEMA or not _verify_sealed(base):
        raise ValueError("base refined correlation is not a valid sealed receipt")
    if equivalence.get("schema") != EQUIVALENCE_SCHEMA or not _verify_sealed(equivalence):
        raise ValueError("source equivalence is not a valid sealed receipt")
    if equivalence.get("state") != "passed-official-package-binary-equivalence":
        raise ValueError("source equivalence must be passed, not quarantined")

    authority = _mapping(equivalence.get("authority"), "equivalence authority")
    if any(authority.get(key) is not False for key in _REQUIRED_FALSE):
        raise ValueError("source equivalence must carry explicit zero authority")
    invariants = _mapping(equivalence.get("invariants"), "equivalence invariants")
    if invariants.get("mutation_authority_granted") is not False:
        raise ValueError("source equivalence cannot grant mutation authority")
    if invariants.get("promotion_authority_granted") is not False:
        raise ValueError("source equivalence cannot grant promotion authority")
    if invariants.get("live_pi_contacted_by_official_comparison") is not False:
        raise ValueError("official comparison must not contact the Pi")

    correlation = _mapping(base.get("correlation"), "base correlation")
    raw_agreements = correlation.get("agreements")
    raw_gaps = correlation.get("gaps")
    if not isinstance(raw_agreements, list) or not isinstance(raw_gaps, list):
        raise ValueError("base agreements/gaps are malformed")

    source_gap = [
        item for item in raw_gaps
        if isinstance(item, Mapping) and item.get("id") == "running-driver-source-provenance"
    ]
    if len(source_gap) != 1:
        raise ValueError("base correlation does not contain exactly one source-provenance gap")

    remaining_gaps = [
        dict(item)
        for item in raw_gaps
        if isinstance(item, Mapping) and item.get("id") != "running-driver-source-provenance"
    ]
    if {item.get("id") for item in remaining_gaps} != {"candidate-driver-hardware-behavior"}:
        raise ValueError("unexpected reference gaps remain after source-provenance refinement")

    physical = _mapping(equivalence.get("physical"), "equivalence physical")
    official = _mapping(equivalence.get("official"), "equivalence official")
    checks = _mapping(equivalence.get("checks"), "equivalence checks")
    required_checks = (
        "package_name_match",
        "package_version_match",
        "package_architecture_match",
        "source_package_match",
        "source_version_match",
        "running_kernel_bytes_match_official_package",
        "official_archive_url",
    )
    missing = [name for name in required_checks if checks.get(name) is not True]
    if missing:
        raise ValueError("source equivalence is missing required proof: " + ", ".join(missing))

    agreements = [dict(item) for item in raw_agreements if isinstance(item, Mapping)]
    agreements.append(
        {
            "id": "official-running-kernel-package-equivalence",
            "state": "agrees",
            "reference": (
                f"official Raspberry Pi archive package {official.get('package')} "
                f"{official.get('version')} / source {official.get('source_package')} "
                f"{official.get('source_version')}"
            ),
            "physical": (
                f"pinned Pi3 running kernel {physical.get('kernel_binary_sha256')} "
                "matches the exact kernel bytes extracted from that official package"
            ),
        }
    )

    prior_closed = correlation.get("closed_gap_ids")
    if not isinstance(prior_closed, list):
        prior_closed = []
    closed_gap_ids = sorted(set(str(x) for x in prior_closed) | {"running-driver-source-provenance"})

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "state": "completed",
        "semantic_state": "completed-with-one-actionable-reference-gap",
        "inputs": {
            "base_refinement_receipt_sha256": base.get("receipt_sha256"),
            "source_equivalence_receipt_sha256": equivalence.get("receipt_sha256"),
            "physical_source_run_id": _mapping(
                equivalence.get("inputs"), "equivalence inputs"
            ).get("physical_source_run_id"),
        },
        "processing": {
            "placement": "repository-receipt-refinement",
            "live_pi_contacted": False,
            "physical_mutation_authority": False,
            "qpu_hardware_contacted": False,
        },
        "correlation": {
            "agreement_count": len(agreements),
            "agreements": agreements,
            "closed_gap_ids": closed_gap_ids,
            "gap_count": len(remaining_gaps),
            "gaps": remaining_gaps,
        },
        "source_provenance": {
            "physical": dict(physical),
            "official": dict(official),
            "equivalence_checks": dict(checks),
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
            "state": "held-for-functional-candidate-model",
            "next_experiment": "build-offline-functional-smsc95xx-lan9514-behavior-model",
            "next_experiment_inputs": [
                "official LAN9514 register/protocol behavior",
                "protected Linux smsc95xx reference-driver transitions",
                "sealed Pi3 physical controller/link observations",
            ],
        },
        "strongest_claim": (
            "The pinned Pi3 running-kernel bytes now have sealed equivalence to the exact official Raspberry Pi archive binary package and its source-package version, closing the running-driver source-provenance gap. One stronger reference gap remains: an offline functional candidate-driver hardware-behavior model. No mutation or promotion authority is created."
        ),
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--equivalence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    receipt = refine_source_provenance(_load(args.base), _load(args.equivalence))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "AURUM_PI3_REFERENCE_SOURCE_REFINEMENT "
        f"agreements={receipt['correlation']['agreement_count']} "
        f"gaps={receipt['correlation']['gap_count']} "
        "mutation_authority=false promotion_authority=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
