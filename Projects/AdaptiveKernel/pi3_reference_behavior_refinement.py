"""Close the Pi3 functional candidate-behavior reference gap from a sealed model.

This repository-only stage consumes the seven-agreement source-provenance receipt
and a verified non-actuating functional model. It closes the *reference-model*
gap only. It does not claim that an Aurum native driver is implemented or safe to
bind, and it cannot create physical mutation or promotion authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "aurum-pi3-reference-behavior-refinement-v1"
BASE_SCHEMA = "aurum-pi3-reference-source-refinement-v1"
MODEL_SCHEMA = "aurum.pi3.smsc95xx.functional-model.v1"
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


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def refine_behavior_gap(base: Mapping[str, Any], model: Mapping[str, Any]) -> dict[str, Any]:
    if base.get("schema") != BASE_SCHEMA or not _verify_sealed(base):
        raise ValueError("base source-provenance refinement is not a valid sealed receipt")
    if model.get("schema") != MODEL_SCHEMA or not _verify_sealed(model):
        raise ValueError("functional model is not a valid sealed receipt")
    if model.get("state") != "verified-offline-functional-model":
        raise ValueError("functional model must be verified before reference refinement")

    authority = _mapping(model.get("authority"), "functional model authority")
    if any(authority.get(key) is not False for key in _REQUIRED_FALSE):
        raise ValueError("functional model must carry explicit zero authority")
    invariants = _mapping(model.get("invariants"), "functional model invariants")
    for key in (
        "live_pi_contacted",
        "device_io_performed",
        "driver_binding_changed",
        "kernel_changed",
        "firmware_changed",
        "network_configuration_changed",
        "mutation_authority_granted",
        "promotion_authority_granted",
    ):
        if invariants.get(key) is not False:
            raise ValueError(f"functional model invariant must remain false: {key}")
    if invariants.get("last_known_good_preserved") is not True:
        raise ValueError("functional model must preserve Last Known Good")

    verification = _mapping(model.get("verification"), "functional model verification")
    required_true = (
        "physical_state_reproduced",
        "reference_tx_framing_reproduced",
        "reversible_rx_checksum_sequence_reproduced",
    )
    missing = [key for key in required_true if verification.get(key) is not True]
    if missing:
        raise ValueError("functional model is missing verification: " + ", ".join(missing))
    if int(verification.get("functional_scenarios_passed") or 0) < 7:
        raise ValueError("functional model did not pass the minimum scenario set")

    correlation = _mapping(base.get("correlation"), "base correlation")
    agreements = correlation.get("agreements")
    gaps = correlation.get("gaps")
    if not isinstance(agreements, list) or not isinstance(gaps, list):
        raise ValueError("base agreements/gaps are malformed")
    gap_ids = [item.get("id") for item in gaps if isinstance(item, Mapping)]
    if gap_ids != ["candidate-driver-hardware-behavior"]:
        raise ValueError("candidate-driver-hardware-behavior must be the sole remaining reference gap")

    final_agreements = [dict(item) for item in agreements if isinstance(item, Mapping)]
    final_agreements.append(
        {
            "id": "offline-functional-smsc95xx-lan9514-model",
            "state": "agrees",
            "reference": "hash-pinned Raspberry Pi smsc95xx source plus sealed LAN9514/reference evidence",
            "physical": "sealed Pi3 identity/link/checksum observations reproduced by the non-actuating model",
            "model_receipt_sha256": model.get("receipt_sha256"),
        }
    )
    prior_closed = correlation.get("closed_gap_ids")
    if not isinstance(prior_closed, list):
        prior_closed = []
    closed_gap_ids = sorted(set(str(x) for x in prior_closed) | {"candidate-driver-hardware-behavior"})

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "state": "completed",
        "semantic_state": "reference-model-gaps-closed",
        "inputs": {
            "source_refinement_receipt_sha256": base.get("receipt_sha256"),
            "functional_model_receipt_sha256": model.get("receipt_sha256"),
        },
        "correlation": {
            "agreement_count": len(final_agreements),
            "agreements": final_agreements,
            "closed_gap_ids": closed_gap_ids,
            "gap_count": 0,
            "gaps": [],
        },
        "invariants": {
            "last_known_good_preserved": True,
            "reference_driver_preserved": True,
            "live_pi_contacted_by_refinement": False,
            "device_io_performed_by_refinement": False,
            "driver_binding_changed": False,
            "kernel_changed": False,
            "firmware_changed": False,
            "network_configuration_changed": False,
            "mutation_authority_granted": False,
            "promotion_authority_granted": False,
        },
        "authority": {key: False for key in _REQUIRED_FALSE},
        "proposal": {
            "physical_driver_change": "no-change",
            "reference_model_state": "complete-for-current-bounded-first-milestone",
            "native_driver_implementation_state": "not-yet-functional-native-driver",
            "next_experiment": "synthesize-minimal-nonbinding-smsc95xx-candidate-from-functional-model",
            "physical_binding_allowed": False,
        },
        "strongest_claim": (
            "All currently tracked Pi3 reference-model gaps are closed at the non-actuating model layer: exact controller identity/link, official package-to-running-kernel provenance, and a functional LAN9514/smsc95xx shadow model now agree with sealed physical/reference evidence. This does not prove an Aurum native driver implementation, physical binding safety, or promotion eligibility."
        ),
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    receipt = refine_behavior_gap(_load(args.base), _load(args.model))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "AURUM_PI3_REFERENCE_BEHAVIOR_REFINEMENT "
        f"agreements={receipt['correlation']['agreement_count']} gaps=0 "
        "mutation_authority=false promotion_authority=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
