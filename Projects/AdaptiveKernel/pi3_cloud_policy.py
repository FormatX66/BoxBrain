"""Analyze sealed Pi3 evidence on GitHub-hosted compute without Pi authority.

The cloud lane verifies a checked-in semantic result and the exact files from
its GitHub artifact, performs deterministic window and bootstrap policy replay,
and emits a sealed proposal.  It has no live collector, SSH client, executor,
QPU client, or hardware mutation path.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re
from typing import Any, Mapping, Sequence

from Projects.AdaptiveKernel.adaptive_runtime import (
    DEFAULT_POLICIES,
    evaluate_shadow_window,
    verify_receipt,
)
from Projects.AdaptiveKernel.pi3_artifact_adapter import (
    ArtifactEvidenceError,
    load_overnight_samples,
)


RECEIPT_SCHEMA = "aurum-pi3-cloud-policy-proposal-v1"
EXPECTED_MODEL = "Raspberry Pi 3 Model B Rev 1.2"
EXPECTED_SERIAL = "00000000a6a7df7f"
EXPECTED_KERNEL = "6.18.34+rpt-rpi-v8"
EXPECTED_BOOT_ID = "3488238f-e35d-4249-9d53-6133eeed4b8a"
EXPECTED_ROOT = "/dev/mmcblk0p2"
EXPECTED_DRIVER = "smsc95xx"
EXPECTED_ROLLBACK_RAW_SHA256 = (
    "61a4c6bfc03e7ea3444ce67de20c506dbc57a7fc7e34da250b3bfab8d2845c62"
)
EXPECTED_ROLLBACK_ARCHIVE_SHA256 = (
    "c45bb76d88867b1c3552791f9b992068bccd2c9f2f9b83c2fcab3d0cc79ee984"
)
PRESSURE_THERMAL_CEILING_C = 72.0
QPU_MIN_CANDIDATES = 64
MIN_SCENARIOS = 100
MAX_SCENARIOS = 250_000
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_EVENTS_BYTES = 8 * 1024 * 1024
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CloudPolicyEvidenceError(ValueError):
    """The cloud proposal input is malformed, inconsistent, or untrusted."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return _sha256_bytes(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    )


def _seal(receipt: Mapping[str, Any]) -> dict[str, Any]:
    sealed = dict(receipt)
    sealed.pop("receipt_sha256", None)
    sealed["receipt_sha256"] = _canonical_sha256(sealed)
    return sealed


def verify_cloud_policy_receipt(receipt: Mapping[str, Any]) -> bool:
    claimed = receipt.get("receipt_sha256")
    if not isinstance(claimed, str):
        return False
    unsealed = dict(receipt)
    unsealed.pop("receipt_sha256", None)
    return claimed == _canonical_sha256(unsealed)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CloudPolicyEvidenceError(f"{name} must be a mapping")
    return value


def _positive_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CloudPolicyEvidenceError(f"{name} must be a positive integer")
    return value


def _read_json(path: Path, name: str) -> tuple[Mapping[str, Any], str]:
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise CloudPolicyEvidenceError(f"{name} must be a file")
        body = resolved.read_bytes()
    except OSError as exc:
        raise CloudPolicyEvidenceError(f"{name} is unavailable") from exc
    if not body or len(body) > MAX_JSON_BYTES:
        raise CloudPolicyEvidenceError(f"{name} size is empty or outside bounds")
    try:
        parsed = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CloudPolicyEvidenceError(f"{name} is invalid JSON") from exc
    return _mapping(parsed, name), _sha256_bytes(body)


def _read_bounded_hash(path: Path, name: str, maximum: int) -> str:
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise CloudPolicyEvidenceError(f"{name} must be a file")
        body = resolved.read_bytes()
    except OSError as exc:
        raise CloudPolicyEvidenceError(f"{name} is unavailable") from exc
    if not body or len(body) > maximum:
        raise CloudPolicyEvidenceError(f"{name} size is empty or outside bounds")
    return _sha256_bytes(body)


def _expect_equal(actual: Any, expected: Any, name: str) -> None:
    if actual != expected:
        raise CloudPolicyEvidenceError(f"{name} does not match pinned evidence")


def _verify_source_result(source: Mapping[str, Any]) -> None:
    claimed = source.get("receipt_sha256")
    if not isinstance(claimed, str) or not _SHA256.fullmatch(claimed):
        raise CloudPolicyEvidenceError("source result has no valid receipt seal")
    unsealed = dict(source)
    unsealed.pop("receipt_sha256", None)
    if claimed != _canonical_sha256(unsealed):
        raise CloudPolicyEvidenceError("source result receipt seal failed")
    _expect_equal(
        source.get("schema"),
        "aurum-pi3-adaptive-runtime-pressure-result-v1",
        "source result schema",
    )


def _verify_identity(identity: Mapping[str, Any], name: str) -> None:
    _expect_equal(identity.get("model"), EXPECTED_MODEL, f"{name}.model")
    _expect_equal(identity.get("serial"), EXPECTED_SERIAL, f"{name}.serial")
    kernel = identity.get("kernel", identity.get("kernel_release"))
    _expect_equal(kernel, EXPECTED_KERNEL, f"{name}.kernel")
    _expect_equal(identity.get("boot_id"), EXPECTED_BOOT_ID, f"{name}.boot_id")
    _expect_equal(identity.get("root_source"), EXPECTED_ROOT, f"{name}.root_source")
    _expect_equal(
        identity.get("reference_driver"), EXPECTED_DRIVER, f"{name}.reference_driver"
    )


def _verify_true_fields(value: Mapping[str, Any], names: Sequence[str], prefix: str) -> None:
    for name in names:
        if value.get(name) is not True:
            raise CloudPolicyEvidenceError(f"{prefix}.{name} is not proven true")


def _summarize_receipts(receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    states: Counter[str] = Counter()
    recommendations: Counter[str] = Counter()
    policies: Counter[str] = Counter()
    quarantined_samples = 0
    for receipt in receipts:
        if not verify_receipt(receipt):
            raise CloudPolicyEvidenceError("adaptive-runtime replay receipt seal failed")
        decision = _mapping(receipt.get("decision"), "shadow decision")
        evidence = _mapping(receipt.get("evidence"), "shadow evidence")
        states[str(decision.get("state"))] += 1
        recommendations[str(decision.get("recommendation"))] += 1
        policies[str(decision.get("selected_policy_id"))] += 1
        quarantined_samples += int(evidence.get("quarantined_count", 0))
    return {
        "receipt_count": len(receipts),
        "state_counts": dict(sorted(states.items())),
        "recommendation_counts": dict(sorted(recommendations.items())),
        "selected_policy_counts": dict(sorted(policies.items())),
        "quarantined_sample_receipt_count": quarantined_samples,
    }


def _sliding_window_analysis(samples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    analyses: dict[str, Any] = {}
    for size in (3, 8, 16, 32):
        if size > len(samples):
            continue
        receipts = [
            evaluate_shadow_window(
                samples[start : start + size], expected_reference_driver=EXPECTED_DRIVER
            )
            for start in range(0, len(samples) - size + 1)
        ]
        analyses[str(size)] = _summarize_receipts(receipts)
    return analyses


def _bootstrap_analysis(
    samples: Sequence[Mapping[str, Any]],
    *,
    scenario_count: int,
    seed_digest: str,
) -> dict[str, Any]:
    if not MIN_SCENARIOS <= scenario_count <= MAX_SCENARIOS:
        raise CloudPolicyEvidenceError(
            f"scenario_count must be between {MIN_SCENARIOS} and {MAX_SCENARIOS}"
        )
    window_size = min(8, len(samples))
    if window_size < 3:
        raise CloudPolicyEvidenceError("at least three samples are required")
    seed = int(seed_digest.removeprefix("sha256:")[:16], 16)
    generator = random.Random(seed)
    states: Counter[str] = Counter()
    recommendations: Counter[str] = Counter()
    policies: Counter[str] = Counter()
    quarantine_count = 0
    for scenario_index in range(scenario_count):
        scenario: list[dict[str, Any]] = []
        for sample_index in range(window_size):
            sample = dict(samples[generator.randrange(len(samples))])
            sample["sample_id"] = f"bootstrap-{scenario_index}-{sample_index}"
            scenario.append(sample)
        receipt = evaluate_shadow_window(
            scenario, expected_reference_driver=EXPECTED_DRIVER
        )
        if not verify_receipt(receipt):
            raise CloudPolicyEvidenceError("bootstrap receipt seal failed")
        decision = _mapping(receipt.get("decision"), "bootstrap decision")
        evidence = _mapping(receipt.get("evidence"), "bootstrap evidence")
        states[str(decision.get("state"))] += 1
        recommendations[str(decision.get("recommendation"))] += 1
        policies[str(decision.get("selected_policy_id"))] += 1
        quarantine_count += int(evidence.get("quarantined_count", 0))
    return {
        "method": "deterministic-bootstrap-with-replacement",
        "scenario_count": scenario_count,
        "window_size": window_size,
        "seed_source": "first-64-bits-of-github-artifact-digest",
        "state_counts": dict(sorted(states.items())),
        "recommendation_counts": dict(sorted(recommendations.items())),
        "selected_policy_counts": dict(sorted(policies.items())),
        "quarantined_sample_receipt_count": quarantine_count,
    }


def evaluate_cloud_policy(
    evidence_dir: Path,
    source_result_path: Path,
    *,
    source_run_id: int,
    artifact_id: int,
    artifact_digest: str,
    scenario_count: int = 50_000,
) -> dict[str, Any]:
    """Verify physical evidence and produce a deterministic zero-authority proposal."""

    source_run_id = _positive_integer(source_run_id, "source_run_id")
    artifact_id = _positive_integer(artifact_id, "artifact_id")
    if not isinstance(artifact_digest, str) or not _DIGEST.fullmatch(artifact_digest):
        raise CloudPolicyEvidenceError("artifact_digest must be a lowercase SHA-256 digest")

    source, source_result_sha256 = _read_json(source_result_path, "source result")
    _verify_source_result(source)
    artifact = _mapping(source.get("artifact"), "source artifact")
    run = _mapping(source.get("run"), "source run")
    _expect_equal(run.get("id"), source_run_id, "source run id")
    _expect_equal(artifact.get("id"), artifact_id, "source artifact id")
    _expect_equal(artifact.get("digest"), artifact_digest, "source artifact digest")

    evidence_root = evidence_dir.resolve(strict=True)
    control, control_sha256 = _read_json(
        evidence_root / "control-receipt.json", "control receipt"
    )
    summary, summary_sha256 = _read_json(
        evidence_root / "remote" / "summary.json", "remote summary"
    )
    events_path = evidence_root / "remote" / "events.jsonl"
    samples_path = evidence_root / "remote" / "samples.jsonl"
    events_sha256 = _read_bounded_hash(events_path, "remote events", MAX_EVENTS_BYTES)
    samples, samples_sha256 = load_overnight_samples(samples_path)

    _expect_equal(
        control_sha256, artifact.get("control_receipt_sha256"), "control receipt hash"
    )
    _expect_equal(summary_sha256, artifact.get("summary_sha256"), "summary hash")
    _expect_equal(events_sha256, artifact.get("events_sha256"), "events hash")
    _expect_equal(samples_sha256, artifact.get("samples_sha256"), "samples hash")

    source_identity = _mapping(source.get("identity"), "source identity")
    _verify_identity(source_identity, "source identity")
    _verify_identity(_mapping(summary.get("identity_before"), "identity before"), "identity before")
    _verify_identity(_mapping(summary.get("identity_after"), "identity after"), "identity after")
    target = _mapping(control.get("target"), "control target")
    _expect_equal(target.get("model"), EXPECTED_MODEL, "control target.model")
    _expect_equal(target.get("serial"), EXPECTED_SERIAL, "control target.serial")
    _expect_equal(control.get("run_id"), str(source_run_id), "control run id")
    _expect_equal(control.get("remote_boot_id"), EXPECTED_BOOT_ID, "control boot id")
    _expect_equal(control.get("lan_scan_performed"), False, "control lan scan")

    summary_invariants = _mapping(summary.get("invariant_checks"), "summary invariants")
    _verify_true_fields(
        summary_invariants,
        (
            "boot_id_unchanged",
            "ethernet_carrier_present",
            "identity_match",
            "kernel_unchanged",
            "model_unchanged",
            "reference_driver_file_hash_unchanged",
            "reference_driver_unchanged",
            "root_source_unchanged",
            "serial_unchanged",
        ),
        "summary invariants",
    )
    _expect_equal(summary.get("persistent_kernel_or_driver_change"), False, "persistent change")
    _expect_equal(summary.get("replacement_kernel_installed"), False, "replacement kernel")
    _expect_equal(summary.get("boot_configuration_changed"), False, "boot configuration")
    _expect_equal(summary.get("firmware_changed"), False, "firmware")

    rollback = _mapping(source.get("rollback"), "source rollback")
    _expect_equal(
        rollback.get("raw_image_sha256"),
        EXPECTED_ROLLBACK_RAW_SHA256,
        "rollback raw image hash",
    )
    _expect_equal(
        rollback.get("archive_sha256"),
        EXPECTED_ROLLBACK_ARCHIVE_SHA256,
        "rollback archive hash",
    )
    _expect_equal(rollback.get("archive_integrity_test"), "passed", "rollback archive test")
    _expect_equal(rollback.get("verified_fresh_before_physical_contact"), True, "rollback freshness")

    stages = _mapping(summary.get("stages"), "summary stages")
    pressure = _mapping(
        stages.get("adaptive-runtime-pressure-canary"), "pressure stage"
    )
    _expect_equal(pressure.get("state"), "held", "pressure stage state")
    _expect_equal(
        pressure.get("reason"),
        "pressure-thermal-stop-before-live-policy",
        "pressure stage reason",
    )
    pressure_samples = pressure.get("pressure_evidence")
    if not isinstance(pressure_samples, list) or not pressure_samples:
        raise CloudPolicyEvidenceError("pressure evidence is missing")
    pressure_temperatures = [
        float(_mapping(sample, "pressure sample").get("temperature_c"))
        for sample in pressure_samples
    ]
    maximum_pressure_temperature_c = max(pressure_temperatures)
    if maximum_pressure_temperature_c <= PRESSURE_THERMAL_CEILING_C:
        raise CloudPolicyEvidenceError("source thermal hold is inconsistent with evidence")

    sliding = _sliding_window_analysis(samples)
    bootstrap = _bootstrap_analysis(
        samples, scenario_count=scenario_count, seed_digest=artifact_digest
    )
    candidate_count = len(DEFAULT_POLICIES)
    qpu_eligible = candidate_count >= QPU_MIN_CANDIDATES

    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "state": "completed",
        "semantic_state": "held-zero-authority-thermal-source",
        "processing": {
            "placement": "github-hosted-actions",
            "mode": "sealed-evidence-policy-replay",
            "live_pi_contacted": False,
            "pi_compute_consumed": False,
        },
        "source": {
            "github_run_id": source_run_id,
            "github_artifact_id": artifact_id,
            "github_artifact_digest": artifact_digest,
            "source_result_sha256": source_result_sha256,
            "source_result_receipt_sha256": source["receipt_sha256"],
            "control_receipt_sha256": control_sha256,
            "summary_sha256": summary_sha256,
            "events_sha256": events_sha256,
            "samples_sha256": samples_sha256,
            "observation_sample_count": len(samples),
            "pressure_sample_count": len(pressure_samples),
        },
        "physical_gate": {
            "source_pressure_state": pressure["state"],
            "source_pressure_reason": pressure["reason"],
            "thermal_ceiling_c": PRESSURE_THERMAL_CEILING_C,
            "maximum_pressure_temperature_c": maximum_pressure_temperature_c,
            "physical_promotion_eligible": False,
        },
        "analysis": {
            "sliding_windows": sliding,
            "bootstrap": bootstrap,
        },
        "qpu_routing": {
            "considered": True,
            "candidate_count": candidate_count,
            "minimum_candidate_count": QPU_MIN_CANDIDATES,
            "eligible": qpu_eligible,
            "used": False,
            "hardware_submission_performed": False,
            "classical_exhaustive_search_authoritative": True,
            "reason": (
                "candidate-space-large-enough-but-no-authorized-qpu-lane"
                if qpu_eligible
                else "candidate-space-too-small-for-measurable-qpu-value"
            ),
        },
        "proposal": {
            "state": "held",
            "recommendation": "no-change",
            "selected_policy_id": "runtime-baseline-v1",
            "reason": "source-thermal-gate-prevents-physical-promotion",
            "next_evidence_gate": "cooler-or-calibrated-low-duty-cycle-physical-run",
            "change_applied": False,
        },
        "invariants": {
            "evidence_only": True,
            "live_pi_contacted": False,
            "ssh_used": False,
            "password_used": False,
            "lan_scan_performed": False,
            "qpu_hardware_contacted": False,
            "mutation_authority_granted": False,
            "executor_connected": False,
            "kernel_changed": False,
            "driver_binding_changed": False,
            "boot_or_firmware_changed": False,
            "network_changed": False,
            "reference_driver_preserved": True,
            "last_known_good_preserved": True,
        },
        "strongest_claim": (
            "GitHub-hosted compute independently verified the sealed Pi3 pressure "
            "artifact and replayed bounded adaptive-runtime policy scenarios without "
            "contacting the Pi. The result remains a zero-authority no-change proposal "
            "because the physical source run crossed its thermal gate."
        ),
    }
    return _seal(receipt)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--source-result", required=True, type=Path)
    parser.add_argument("--source-run-id", required=True, type=int)
    parser.add_argument("--artifact-id", required=True, type=int)
    parser.add_argument("--artifact-digest", required=True)
    parser.add_argument("--scenario-count", type=int, default=50_000)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        receipt = evaluate_cloud_policy(
            args.evidence_dir,
            args.source_result,
            source_run_id=args.source_run_id,
            artifact_id=args.artifact_id,
            artifact_digest=args.artifact_digest,
            scenario_count=args.scenario_count,
        )
    except (ArtifactEvidenceError, CloudPolicyEvidenceError, OSError, ValueError) as exc:
        receipt = _seal(
            {
                "schema": RECEIPT_SCHEMA,
                "state": "refused",
                "reason": str(exc),
                "invariants": {
                    "live_pi_contacted": False,
                    "qpu_hardware_contacted": False,
                    "mutation_authority_granted": False,
                    "change_applied": False,
                },
            }
        )
        _write_json(args.output, receipt)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 1
    _write_json(args.output, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
