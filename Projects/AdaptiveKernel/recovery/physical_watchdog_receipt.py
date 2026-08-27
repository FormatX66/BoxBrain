"""Validate canonical physical Pi3 out-of-band recovery evidence.

This module is an evidence gate, not a hardware actuator.  It converts a
complete, provenance-bound physical recovery receipt into the existing
``WatchdogEvidence`` contract.  Missing or contradictory evidence fails closed,
and successful validation still never grants kernel-mutation authority.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping

from Projects.AdaptiveKernel.pi3_watchdog_contract import WatchdogEvidence, evaluate_watchdog


RECEIPT_SCHEMA = "aurum.pi3.oob-recovery.physical.v1"
EVALUATION_SCHEMA = "aurum.pi3.oob-recovery.evaluation.v1"
EXPECTED_MODEL_MARKER = "Raspberry Pi 3 Model B Rev 1.2"
EXPECTED_SERIAL = "00000000a6a7df7f"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class PhysicalWatchdogReceiptError(ValueError):
    """The receipt cannot support the physical watchdog prerequisite."""


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PhysicalWatchdogReceiptError(f"{label} must be an object")
    return value


def _true(value: object, label: str) -> None:
    if value is not True:
        raise PhysicalWatchdogReceiptError(f"{label} must be true")


def _false(value: object, label: str) -> None:
    if value is not False:
        raise PhysicalWatchdogReceiptError(f"{label} must be false")


def _identity(value: object, *, role: str) -> tuple[str, str]:
    component = _mapping(value, f"topology.{role}")
    if component.get("role") != role:
        raise PhysicalWatchdogReceiptError(f"topology.{role}.role is invalid")
    component_id = str(component.get("component_id") or "").strip()
    fingerprint = str(component.get("identity_fingerprint") or "").strip()
    if not component_id or not fingerprint:
        raise PhysicalWatchdogReceiptError(f"topology.{role} identity is incomplete")
    _true(component.get("independently_identified"), f"topology.{role}.independently_identified")
    _true(
        component.get("independent_of_target_kernel"),
        f"topology.{role}.independent_of_target_kernel",
    )
    _false(component.get("simulation_only"), f"topology.{role}.simulation_only")
    return component_id, fingerprint


def _target(value: object, label: str) -> Mapping[str, Any]:
    target = _mapping(value, label)
    if target.get("model_marker") != EXPECTED_MODEL_MARKER or target.get("serial") != EXPECTED_SERIAL:
        raise PhysicalWatchdogReceiptError(f"{label} is not the pinned experimental Pi3")
    return target


def _lkg(value: object, label: str) -> tuple[str, str]:
    lkg = _mapping(value, label)
    artifact_id = str(lkg.get("artifact_id") or "").strip()
    digest = str(lkg.get("sha256") or "").strip().lower()
    if not artifact_id or SHA256_RE.fullmatch(digest) is None:
        raise PhysicalWatchdogReceiptError(f"{label} identity is invalid")
    return artifact_id, digest


def _evidence(value: object, label: str) -> tuple[tuple[str, str, str], ...]:
    if not isinstance(value, list) or not value:
        raise PhysicalWatchdogReceiptError(f"{label} must contain evidence references")
    parsed: list[tuple[str, str, str]] = []
    for index, item in enumerate(value):
        ref = _mapping(item, f"{label}[{index}]")
        kind = str(ref.get("kind") or "").strip()
        locator = str(ref.get("locator") or "").strip()
        digest = str(ref.get("sha256") or "").strip().lower()
        if not kind or not locator or SHA256_RE.fullmatch(digest) is None:
            raise PhysicalWatchdogReceiptError(f"{label}[{index}] is incomplete")
        parsed.append((kind, locator, digest))
    if len(set(parsed)) != len(parsed):
        raise PhysicalWatchdogReceiptError(f"{label} contains duplicate references")
    return tuple(parsed)


def evaluate_physical_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a physical receipt and derive a zero-authority watchdog decision."""

    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise PhysicalWatchdogReceiptError("unexpected physical watchdog receipt schema")
    if receipt.get("mode") != "physical" or receipt.get("state") != "verified-physical-recovery":
        raise PhysicalWatchdogReceiptError("receipt does not claim a completed physical recovery cycle")

    expected_target = _target(receipt.get("target_expected"), "target_expected")
    expected_lkg = _lkg(receipt.get("lkg_expected"), "lkg_expected")

    topology = _mapping(receipt.get("topology"), "topology")
    identities = [_identity(topology.get(role), role=role) for role in ("controller", "observer", "actuator", "verifier")]
    if len({identity[0] for identity in identities}) != 4:
        raise PhysicalWatchdogReceiptError("topology component IDs must be distinct")
    if len({identity[1] for identity in identities}) != 4:
        raise PhysicalWatchdogReceiptError("topology identity fingerprints must be distinct")

    observer = _mapping(topology.get("observer"), "topology.observer")
    signal_path = str(observer.get("signal_path") or "").strip()
    if signal_path not in {"hdmi-capture", "serial-console", "external-health-probe"}:
        raise PhysicalWatchdogReceiptError("observer signal path is not target-kernel-independent")
    actuator = _mapping(topology.get("actuator"), "topology.actuator")
    _true(actuator.get("can_control_power"), "topology.actuator.can_control_power")
    _true(actuator.get("can_select_or_restore_lkg"), "topology.actuator.can_select_or_restore_lkg")

    observation = _mapping(receipt.get("observation"), "observation")
    _true(observation.get("failure_detected"), "observation.failure_detected")
    _true(observation.get("automatic_detection"), "observation.automatic_detection")
    _false(observation.get("target_kernel_responsive"), "observation.target_kernel_responsive")
    _false(observation.get("local_target_timer_only"), "observation.local_target_timer_only")
    observation_refs = _evidence(observation.get("evidence_refs"), "observation.evidence_refs")

    actuation = _mapping(receipt.get("actuation"), "actuation")
    for field in ("requested", "completed", "automatic", "power_control_exercised", "lkg_recovery_exercised"):
        _true(actuation.get(field), f"actuation.{field}")
    _false(actuation.get("network_only"), "actuation.network_only")
    actuation_refs = _evidence(actuation.get("evidence_refs"), "actuation.evidence_refs")

    recovered = _mapping(receipt.get("post_recovery"), "post_recovery")
    observed_target = _target(recovered.get("target"), "post_recovery.target")
    observed_lkg = _lkg(recovered.get("lkg"), "post_recovery.lkg")
    _true(recovered.get("healthy"), "post_recovery.healthy")
    recovery_refs = _evidence(recovered.get("evidence_refs"), "post_recovery.evidence_refs")
    if dict(expected_target) != dict(observed_target) or expected_lkg != observed_lkg:
        raise PhysicalWatchdogReceiptError("post-recovery target or LKG does not match the expected identity")

    all_refs = observation_refs + actuation_refs + recovery_refs
    if len({item[2] for item in all_refs}) != len(all_refs):
        raise PhysicalWatchdogReceiptError("evidence artifacts must have distinct content hashes")

    provenance = _mapping(receipt.get("provenance"), "provenance")
    source_commit = str(provenance.get("source_commit") or "").strip().lower()
    collector_id = str(provenance.get("collector_id") or "").strip()
    collector_digest = str(provenance.get("collector_sha256") or "").strip().lower()
    run_id = str(provenance.get("run_id") or "").strip()
    if (
        COMMIT_RE.fullmatch(source_commit) is None
        or not collector_id
        or SHA256_RE.fullmatch(collector_digest) is None
        or not run_id.isdigit()
        or int(run_id) <= 0
    ):
        raise PhysicalWatchdogReceiptError("receipt provenance is incomplete")

    authority = _mapping(receipt.get("authority"), "authority")
    for field in (
        "mutation_authority_granted",
        "kernel_module_load_allowed",
        "driver_binding_change_allowed",
        "firmware_mutation_allowed",
    ):
        _false(authority.get(field), f"authority.{field}")
    safety = _mapping(receipt.get("safety"), "safety")
    _false(safety.get("production_nodes_allowed"), "safety.production_nodes_allowed")

    evidence = WatchdogEvidence(
        pinned_target_identity=True,
        independent_controller_identity=True,
        observer_independent_of_target_kernel=True,
        recovery_actuator_independent_of_target_kernel=True,
        automatic_failure_detection_proven=True,
        automatic_recovery_actuation_proven=True,
        post_recovery_target_identity_proven=True,
        lkg_restored_and_healthy_proven=True,
        local_target_timer_only=False,
        network_only_actuation=False,
        mutation_authority_granted=False,
    )
    decision = evaluate_watchdog(evidence)
    fingerprint = hashlib.sha256(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schema": EVALUATION_SCHEMA,
        "receipt_schema": RECEIPT_SCHEMA,
        "receipt_sha256": fingerprint,
        "state": decision.state.value,
        "watchdog_proven": decision.watchdog_proven,
        "mutation_authority_granted": decision.mutation_authority_granted,
        "next_gate": decision.next_gate,
        "target": dict(expected_target),
        "lkg": {"artifact_id": expected_lkg[0], "sha256": expected_lkg[1]},
        "watchdog_evidence": asdict(evidence),
        "physical_proof_validated": True,
        "physical_proof_inferred": False,
    }


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PhysicalWatchdogReceiptError(f"cannot read valid receipt JSON: {path}") from exc
    if not isinstance(value, dict):
        raise PhysicalWatchdogReceiptError("receipt root must be an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args()
    try:
        result = evaluate_physical_receipt(_read(Path(args.receipt)))
    except PhysicalWatchdogReceiptError as exc:
        print(f"AURUM_PI3_OOB_WATCHDOG_REFUSED reason={exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
