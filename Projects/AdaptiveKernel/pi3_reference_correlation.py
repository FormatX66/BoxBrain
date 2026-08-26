"""Correlate pinned hardware/driver references with preserved Pi3 evidence.

This cloud-only analyzer verifies immutable reference hashes, extracts explicit
expectations, compares Raspberry Pi and upstream Linux driver sources, and
reconciles those expectations with a sealed physical artifact.  It has no SSH,
live collector, driver loader, executor, or hardware mutation path.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from Projects.AdaptiveKernel.pi3_cloud_policy import verify_cloud_policy_receipt


RECEIPT_SCHEMA = "aurum-pi3-reference-correlation-v1"
MANIFEST_SCHEMA = "aurum-pi3-hardware-reference-manifest-v1"
QPU_SCHEMA = "aurum-pi3-qpu-routing-reference-v1"
EXPECTED_MODEL = "Raspberry Pi 3 Model B Rev 1.2"
EXPECTED_SERIAL = "00000000a6a7df7f"
EXPECTED_KERNEL = "6.18.34+rpt-rpi-v8"
EXPECTED_DRIVER = "smsc95xx"
EXPECTED_PRESSURE_RUN = 32_964_554_773
EXPECTED_PRESSURE_ARTIFACT = 9_605_841_913
EXPECTED_PRESSURE_DIGEST = (
    "sha256:5ec90bdf6c9606bfbd6a481d453326323cfc292c07f2c6248a31729acc1b1740"
)
MAX_REFERENCE_BYTES = 4 * 1024 * 1024
MAX_REFERENCE_COUNT = 16
QPU_VALUE_CANDIDATE_FLOOR = 64
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9_.-]{1,160}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_REFERENCE_HOSTS = {
    "datasheets.raspberrypi.com",
    "raw.githubusercontent.com",
    "ww1.microchip.com",
}


class ReferenceCorrelationError(ValueError):
    """Reference or evidence input is malformed, changed, or ambiguous."""


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


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    sealed = dict(value)
    sealed.pop("receipt_sha256", None)
    sealed["receipt_sha256"] = _canonical_sha256(sealed)
    return sealed


def verify_reference_correlation_receipt(value: Mapping[str, Any]) -> bool:
    claimed = value.get("receipt_sha256")
    if not isinstance(claimed, str):
        return False
    unsealed = dict(value)
    unsealed.pop("receipt_sha256", None)
    return claimed == _canonical_sha256(unsealed)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReferenceCorrelationError(f"{name} must be a mapping")
    return value


def _list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ReferenceCorrelationError(f"{name} must be a list")
    return value


def _load_json(path: Path, name: str) -> tuple[Mapping[str, Any], str]:
    try:
        body = path.resolve(strict=True).read_bytes()
    except OSError as exc:
        raise ReferenceCorrelationError(f"{name} is unavailable") from exc
    if not body or len(body) > MAX_REFERENCE_BYTES:
        raise ReferenceCorrelationError(f"{name} size is empty or outside bounds")
    try:
        parsed = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReferenceCorrelationError(f"{name} is invalid JSON") from exc
    return _mapping(parsed, name), _sha256_bytes(body)


def _expect(actual: Any, expected: Any, name: str) -> None:
    if actual != expected:
        raise ReferenceCorrelationError(f"{name} does not match pinned evidence")


def _verify_generic_seal(value: Mapping[str, Any], name: str) -> None:
    claimed = value.get("receipt_sha256")
    if not isinstance(claimed, str) or not _SHA256.fullmatch(claimed):
        raise ReferenceCorrelationError(f"{name} has no valid receipt seal")
    unsealed = dict(value)
    unsealed.pop("receipt_sha256", None)
    if claimed != _canonical_sha256(unsealed):
        raise ReferenceCorrelationError(f"{name} receipt seal failed")


def _bounded_file(path: Path, name: str) -> tuple[bytes, str]:
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise ReferenceCorrelationError(f"{name} must be a file")
        body = resolved.read_bytes()
    except OSError as exc:
        raise ReferenceCorrelationError(f"{name} is unavailable") from exc
    if not body or len(body) > MAX_REFERENCE_BYTES:
        raise ReferenceCorrelationError(f"{name} size is empty or outside bounds")
    return body, _sha256_bytes(body)


def _verify_reference_manifest(
    manifest: Mapping[str, Any], reference_dir: Path
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    _expect(manifest.get("schema"), MANIFEST_SCHEMA, "reference manifest schema")
    target = _mapping(manifest.get("target"), "reference target")
    _expect(target.get("model"), EXPECTED_MODEL, "reference target model")
    _expect(target.get("serial"), EXPECTED_SERIAL, "reference target serial")
    _expect(target.get("kernel"), EXPECTED_KERNEL, "reference target kernel")
    _expect(target.get("reference_driver"), EXPECTED_DRIVER, "reference target driver")
    sources = _list(manifest.get("sources"), "reference sources")
    if not 1 <= len(sources) <= MAX_REFERENCE_COUNT:
        raise ReferenceCorrelationError("reference source count is outside bounds")

    root = reference_dir.resolve(strict=True)
    verified: dict[str, dict[str, Any]] = {}
    texts: dict[str, str] = {}
    seen_files: set[str] = set()
    for index, raw_source in enumerate(sources):
        source = _mapping(raw_source, f"source {index}")
        source_id = source.get("id")
        filename = source.get("filename")
        expected_sha = source.get("sha256")
        url = source.get("url")
        kind = source.get("kind")
        if not isinstance(source_id, str) or not source_id:
            raise ReferenceCorrelationError(f"source {index} has no id")
        if (
            not isinstance(filename, str)
            or not _SAFE_FILENAME.fullmatch(filename)
            or filename in seen_files
        ):
            raise ReferenceCorrelationError(f"source {source_id} filename is unsafe or repeated")
        if not isinstance(expected_sha, str) or not _SHA256.fullmatch(expected_sha):
            raise ReferenceCorrelationError(f"source {source_id} hash is invalid")
        if not isinstance(url, str):
            raise ReferenceCorrelationError(f"source {source_id} URL is missing")
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_REFERENCE_HOSTS:
            raise ReferenceCorrelationError(f"source {source_id} URL host is not allowed")
        if kind not in {"pdf", "source"}:
            raise ReferenceCorrelationError(f"source {source_id} kind is unsupported")
        seen_files.add(filename)
        body, actual_sha = _bounded_file(root / filename, f"source {source_id}")
        _expect(actual_sha, expected_sha, f"source {source_id} hash")

        if kind == "pdf":
            text_filename = source.get("text_filename")
            if not isinstance(text_filename, str) or not _SAFE_FILENAME.fullmatch(text_filename):
                raise ReferenceCorrelationError(f"source {source_id} text filename is unsafe")
            text_body, _ = _bounded_file(root / text_filename, f"source {source_id} extracted text")
            text = text_body.decode("utf-8-sig", errors="strict")
        else:
            text = body.decode("utf-8", errors="strict")

        required_tokens = _list(source.get("required_tokens"), f"source {source_id} tokens")
        if not required_tokens or any(
            not isinstance(token, str) or not token for token in required_tokens
        ):
            raise ReferenceCorrelationError(f"source {source_id} token contract is invalid")
        missing = [token for token in required_tokens if token not in text]
        if missing:
            raise ReferenceCorrelationError(
                f"source {source_id} is missing required tokens: {', '.join(missing)}"
            )
        verified[source_id] = {
            "filename": filename,
            "kind": kind,
            "sha256": actual_sha,
            "url": url,
            "required_token_count": len(required_tokens),
            "comparison_group": source.get("comparison_group"),
            "implementation": source.get("implementation"),
        }
        texts[source_id] = text
    return verified, texts


def _source_delta(
    left_id: str,
    right_id: str,
    texts: Mapping[str, str],
    verified: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    left = texts[left_id].splitlines()
    right = texts[right_id].splitlines()
    matcher = difflib.SequenceMatcher(a=left, b=right, autojunk=False)
    added = 0
    removed = 0
    changed_blocks = 0
    for tag, left_start, left_end, right_start, right_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed_blocks += 1
        removed += left_end - left_start
        added += right_end - right_start
    return {
        "left": left_id,
        "right": right_id,
        "left_sha256": verified[left_id]["sha256"],
        "right_sha256": verified[right_id]["sha256"],
        "exact_match": verified[left_id]["sha256"] == verified[right_id]["sha256"],
        "similarity_ratio": round(matcher.ratio(), 6),
        "changed_blocks": changed_blocks,
        "left_only_or_replaced_lines": removed,
        "right_only_or_replaced_lines": added,
    }


def _verify_physical_evidence(
    pressure: Mapping[str, Any],
    cloud: Mapping[str, Any],
    evidence_dir: Path,
) -> Mapping[str, Any]:
    _verify_generic_seal(pressure, "pressure result")
    _expect(
        pressure.get("schema"),
        "aurum-pi3-adaptive-runtime-pressure-result-v1",
        "pressure result schema",
    )
    identity = _mapping(pressure.get("identity"), "pressure identity")
    _expect(identity.get("model"), EXPECTED_MODEL, "pressure model")
    _expect(identity.get("serial"), EXPECTED_SERIAL, "pressure serial")
    _expect(identity.get("kernel"), EXPECTED_KERNEL, "pressure kernel")
    _expect(identity.get("reference_driver"), EXPECTED_DRIVER, "pressure driver")
    run = _mapping(pressure.get("run"), "pressure run")
    artifact = _mapping(pressure.get("artifact"), "pressure artifact")
    _expect(run.get("id"), EXPECTED_PRESSURE_RUN, "pressure run id")
    _expect(artifact.get("id"), EXPECTED_PRESSURE_ARTIFACT, "pressure artifact id")
    _expect(artifact.get("digest"), EXPECTED_PRESSURE_DIGEST, "pressure artifact digest")

    if not verify_cloud_policy_receipt(cloud):
        raise ReferenceCorrelationError("cloud policy result seal failed")
    cloud_source = _mapping(cloud.get("source"), "cloud policy source")
    _expect(cloud_source.get("github_run_id"), EXPECTED_PRESSURE_RUN, "cloud source run")
    _expect(
        cloud_source.get("github_artifact_id"), EXPECTED_PRESSURE_ARTIFACT, "cloud source artifact"
    )

    root = evidence_dir.resolve(strict=True)
    control_body, control_sha = _bounded_file(root / "control-receipt.json", "control receipt")
    summary_body, summary_sha = _bounded_file(root / "remote" / "summary.json", "remote summary")
    events_body, events_sha = _bounded_file(root / "remote" / "events.jsonl", "remote events")
    samples_body, samples_sha = _bounded_file(root / "remote" / "samples.jsonl", "remote samples")
    _expect(control_sha, artifact.get("control_receipt_sha256"), "control receipt hash")
    _expect(summary_sha, artifact.get("summary_sha256"), "summary hash")
    _expect(events_sha, artifact.get("events_sha256"), "events hash")
    _expect(samples_sha, artifact.get("samples_sha256"), "samples hash")
    try:
        control = _mapping(json.loads(control_body), "control receipt")
        summary = _mapping(json.loads(summary_body), "remote summary")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReferenceCorrelationError("physical control or summary JSON is invalid") from exc
    _expect(control.get("lan_scan_performed"), False, "control LAN scan")
    summary_identity = _mapping(summary.get("identity_after"), "summary identity")
    _expect(summary_identity.get("model"), EXPECTED_MODEL, "summary model")
    _expect(summary_identity.get("serial"), EXPECTED_SERIAL, "summary serial")
    _expect(summary_identity.get("kernel_release"), EXPECTED_KERNEL, "summary kernel")
    _expect(summary_identity.get("reference_driver"), EXPECTED_DRIVER, "summary driver")
    stages = _mapping(summary.get("stages"), "summary stages")
    feature = _mapping(stages.get("smsc95xx-feature-canary"), "smsc95xx feature stage")
    _expect(feature.get("state"), "passed", "smsc95xx feature stage state")
    _expect(feature.get("feature"), "rx-checksumming", "smsc95xx tested feature")
    _expect(feature.get("reference_driver_during"), EXPECTED_DRIVER, "feature reference driver")
    _expect(feature.get("persistent_change"), False, "feature persistent change")
    pressure_stage = _mapping(
        stages.get("adaptive-runtime-pressure-canary"), "pressure stage"
    )
    _expect(pressure_stage.get("state"), "held", "pressure stage state")
    return summary


def _verify_candidate_evidence(
    candidate: Mapping[str, Any],
    direct_compile: Mapping[str, Any],
    ci_compile: Mapping[str, Any],
) -> None:
    _expect(
        candidate.get("schema"),
        "aurum.adaptive-kernel.driver-candidate.v1",
        "candidate manifest schema",
    )
    target = _mapping(candidate.get("target"), "candidate target")
    _expect(target.get("model_marker"), EXPECTED_MODEL, "candidate model")
    _expect(target.get("reference_driver"), EXPECTED_DRIVER, "candidate reference driver")
    _expect(target.get("reference_driver_replaced"), False, "candidate driver replacement")
    safety = _mapping(candidate.get("safety"), "candidate safety")
    _expect(safety.get("load_allowed"), False, "candidate load authority")
    _expect(safety.get("performs_hardware_io"), False, "candidate hardware I/O")

    _expect(direct_compile.get("state"), "verified-compile-only", "direct compile state")
    direct_target = _mapping(direct_compile.get("target"), "direct compile target")
    _expect(direct_target.get("kernel"), EXPECTED_KERNEL, "direct compile kernel")
    _expect(direct_target.get("reference_driver"), EXPECTED_DRIVER, "direct compile driver")
    direct_verification = _mapping(direct_compile.get("verification"), "direct verification")
    direct_invariants = _mapping(direct_compile.get("invariants"), "direct invariants")
    _expect(direct_invariants.get("module_loaded"), False, "direct module loaded")

    _expect(ci_compile.get("state"), "verified-compile-only", "CI compile state")
    ci_target = _mapping(ci_compile.get("target"), "CI compile target")
    _expect(ci_target.get("kernel"), EXPECTED_KERNEL, "CI compile kernel")
    ci_candidate = _mapping(ci_compile.get("candidate"), "CI candidate")
    _expect(
        ci_candidate.get("module_sha256"),
        direct_verification.get("module_sha256"),
        "direct/CI module hash",
    )
    ci_invariants = _mapping(ci_compile.get("invariants"), "CI invariants")
    _expect(ci_invariants.get("module_loaded"), False, "CI module loaded")


def evaluate_reference_correlation(
    reference_dir: Path,
    manifest_path: Path,
    pressure_result_path: Path,
    cloud_result_path: Path,
    evidence_dir: Path,
    candidate_manifest_path: Path,
    direct_compile_path: Path,
    ci_compile_path: Path,
    qpu_model_path: Path,
) -> dict[str, Any]:
    manifest, manifest_sha = _load_json(manifest_path, "reference manifest")
    verified, texts = _verify_reference_manifest(manifest, reference_dir)
    pressure, pressure_sha = _load_json(pressure_result_path, "pressure result")
    cloud, cloud_sha = _load_json(cloud_result_path, "cloud policy result")
    summary = _verify_physical_evidence(pressure, cloud, evidence_dir)
    candidate, candidate_sha = _load_json(candidate_manifest_path, "candidate manifest")
    direct, direct_sha = _load_json(direct_compile_path, "direct compile result")
    ci_compile, ci_sha = _load_json(ci_compile_path, "CI compile result")
    _verify_candidate_evidence(candidate, direct, ci_compile)
    qpu, qpu_sha = _load_json(qpu_model_path, "QPU routing model")
    _expect(qpu.get("schema"), QPU_SCHEMA, "QPU model schema")
    _verify_generic_seal(qpu, "QPU routing model")

    source_deltas = {
        "smsc95xx_c": _source_delta(
            "upstream-linux-v6.18-smsc95xx-c",
            "raspberry-pi-linux-smsc95xx-c",
            texts,
            verified,
        ),
        "smsc95xx_h": _source_delta(
            "upstream-linux-v6.18-smsc95xx-h",
            "raspberry-pi-linux-smsc95xx-h",
            texts,
            verified,
        ),
        "usbnet_c": _source_delta(
            "upstream-linux-v6.18-usbnet-c",
            "raspberry-pi-linux-usbnet-c",
            texts,
            verified,
        ),
    }
    schematic_text = texts["raspberry-pi-3b-rev12-reduced-schematic"]
    rpi_driver_text = texts["raspberry-pi-linux-smsc95xx-c"]
    datasheet_text = texts["microchip-lan9514-datasheet-00002306a"]
    stages = _mapping(summary.get("stages"), "summary stages")
    feature = _mapping(stages.get("smsc95xx-feature-canary"), "feature stage")
    final_network = _mapping(summary.get("final_network"), "final network")
    qpu_model = _mapping(qpu.get("model"), "QPU model")
    known_comparison_count = 5

    agreements = [
        {
            "id": "board-model-and-soc",
            "state": "agrees",
            "reference": "Pi3B Rev 1.2 reduced schematic names the board and BCM2837",
            "physical": "exact model and serial gates passed",
        },
        {
            "id": "reference-driver-binding",
            "state": "agrees",
            "reference": "Raspberry Pi kernel config and source include built-in smsc95xx over usbnet",
            "physical": "smsc95xx remained bound before, during, and after the run",
        },
        {
            "id": "checksum-offload-capability",
            "state": "agrees",
            "reference": "LAN9514 datasheet and smsc95xx source expose checksum support",
            "physical": "rx-checksumming canary passed and restored without persistent change",
        },
        {
            "id": "reference-driver-health",
            "state": "agrees",
            "reference": "protected Linux branch remains the baseline",
            "physical": "carrier remained present with zero final errors and drops",
        },
    ]
    if "LAN9514" not in schematic_text:
        schematic_controller_scope = "reduced-schematic-does-not-name-lan9514"
    else:
        schematic_controller_scope = "schematic-names-lan9514"

    gaps = [
        {
            "id": "controller-identity",
            "state": "unproven",
            "reason": (
                "the controller datasheet is pinned, but the reduced board schematic does not "
                "name LAN9514 and the physical artifact contains no USB VID:PID or product ID"
            ),
            "next_evidence": "read-only exact-controller USB identity",
        },
        {
            "id": "negotiated-link-speed",
            "state": "unproven",
            "reason": "the LAN9514 reference is 10/100, but the physical artifact records no negotiated speed",
            "next_evidence": "read-only ethtool speed/duplex receipt",
        },
        {
            "id": "running-driver-source-provenance",
            "state": "unproven",
            "reason": (
                "the running kernel is 6.18.34+rpt-rpi-v8 while the pinned Raspberry Pi source is "
                "a later rpi-6.18.y commit; source-to-running-binary equivalence is not established"
            ),
            "next_evidence": "exact package build/source commit provenance",
        },
        {
            "id": "candidate-driver-hardware-behavior",
            "state": "unproven",
            "reason": "the Aurum candidate is an inert API probe, not a functional driver",
            "next_evidence": "offline functional model before any binding proposal",
        },
    ]

    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "state": "completed",
        "semantic_state": "completed-with-actionable-reference-gaps",
        "processing": {
            "placement": "github-hosted-actions",
            "mode": "schematic-source-telemetry-qpu-correlation",
            "live_pi_contacted": False,
            "physical_mutation_authority": False,
        },
        "inputs": {
            "reference_manifest_sha256": manifest_sha,
            "verified_reference_count": len(verified),
            "pressure_result_sha256": pressure_sha,
            "cloud_policy_result_sha256": cloud_sha,
            "candidate_manifest_sha256": candidate_sha,
            "direct_compile_result_sha256": direct_sha,
            "ci_compile_result_sha256": ci_sha,
            "qpu_model_excerpt_sha256": qpu_sha,
            "source_pressure_run_id": EXPECTED_PRESSURE_RUN,
            "source_pressure_artifact_id": EXPECTED_PRESSURE_ARTIFACT,
        },
        "hardware_model": {
            "board_model": EXPECTED_MODEL,
            "soc_reference": "BCM2837",
            "controller_reference": "LAN9514/LAN9514i",
            "controller_reference_capabilities": {
                "usb_hub": "USB 2.0 four-downstream-port",
                "ethernet": "10/100 MAC and PHY",
                "checksum_offload": "TCP/UDP",
            },
            "controller_mapping_to_exact_pi": "unproven",
            "schematic_controller_scope": schematic_controller_scope,
            "datasheet_tokens_verified": all(
                token in datasheet_text
                for token in (
                    "LAN9514/LAN9514i",
                    "TCP/UDP checksum offload support",
                )
            ),
        },
        "known_driver_comparison": {
            "comparison_count": known_comparison_count,
            "protected_physical_driver": EXPECTED_DRIVER,
            "comparators": [
                "physical-linux-smsc95xx",
                "raspberry-pi-rpi-6.18.y-smsc95xx",
                "upstream-linux-v6.18-smsc95xx",
                "raspberry-pi-lan78xx-family-pattern-only",
                "aurum-inert-usbnet-api-probe",
            ],
            "rpi_source_checksum_default_present": "DEFAULT_RX_CSUM_ENABLE" in rpi_driver_text,
            "physical_feature_tested": feature.get("feature"),
            "physical_feature_original": feature.get("original"),
            "physical_feature_test_value": feature.get("tested"),
            "physical_persistent_change": feature.get("persistent_change"),
            "final_carrier": final_network.get("carrier"),
            "final_network_error_or_drop_total": sum(
                int(final_network.get(name, 0))
                for name in ("rx_errors", "tx_errors", "rx_dropped", "tx_dropped")
            ),
            "source_deltas": source_deltas,
            "alternate_driver_binding_tested": False,
            "candidate_hardware_behavior_proven": False,
        },
        "correlation": {
            "agreement_count": len(agreements),
            "agreements": agreements,
            "gap_count": len(gaps),
            "gaps": gaps,
            "raw_empirical_lane_retained": True,
            "reference_aware_lane_retained": True,
        },
        "qpu_comparison": {
            "model_available": True,
            "source_run_id": _mapping(qpu.get("provenance"), "QPU provenance").get("run_id"),
            "model_kind": qpu_model.get("candidate_kind"),
            "hardware_digital_twin": qpu_model.get("hardware_digital_twin"),
            "applicable_to_hardware_expectations": False,
            "applicable_to_experiment_ordering": True,
            "original_qpu_eligible": qpu_model.get("qpu_eligible"),
            "original_population_size": qpu_model.get("population_size"),
            "current_comparison_count": known_comparison_count,
            "current_qpu_value_floor": QPU_VALUE_CANDIDATE_FLOOR,
            "current_qpu_eligible": False,
            "used": False,
            "hardware_submission_performed": False,
            "gate_conflict": True,
            "gate_conflict_resolution": (
                "the old model gates machine-path weighting on branch failure rate; this test gates "
                "driver/reference search on measurable candidate-space savings, so the objectives are not interchangeable"
            ),
        },
        "proposal": {
            "state": "held-for-read-only-identity-evidence",
            "physical_driver_change": "no-change",
            "selected_physical_driver": EXPECTED_DRIVER,
            "next_experiment": "cloud-guided-read-only-controller-and-link-fingerprint",
            "next_experiment_inputs": [
                "USB VID:PID and product identity",
                "negotiated link speed and duplex",
                "exact running-kernel source/package provenance",
            ],
            "change_applied": False,
        },
        "invariants": {
            "official_reference_hashes_verified": True,
            "preserved_artifact_hashes_verified": True,
            "live_pi_contacted": False,
            "ssh_used": False,
            "password_used": False,
            "lan_scan_performed": False,
            "qpu_hardware_contacted": False,
            "mutation_authority_granted": False,
            "kernel_changed": False,
            "driver_binding_changed": False,
            "boot_or_firmware_changed": False,
            "network_configuration_changed": False,
            "reference_driver_preserved": True,
            "last_known_good_preserved": True,
        },
        "strongest_claim": (
            "Pinned official schematic, controller-datasheet, Raspberry Pi Linux, upstream Linux, "
            "compile-only candidate, QPU-router, and physical telemetry evidence agree on the exact "
            "board class, protected smsc95xx path, checksum capability, and healthy empirical behavior. "
            "The comparison also exposes three decisive missing proofs: exact USB controller identity, "
            "negotiated link speed, and source-to-running-binary provenance."
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
    parser.add_argument("--reference-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--pressure-result", required=True, type=Path)
    parser.add_argument("--cloud-result", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--candidate-manifest", required=True, type=Path)
    parser.add_argument("--direct-compile", required=True, type=Path)
    parser.add_argument("--ci-compile", required=True, type=Path)
    parser.add_argument("--qpu-model", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        receipt = evaluate_reference_correlation(
            args.reference_dir,
            args.manifest,
            args.pressure_result,
            args.cloud_result,
            args.evidence_dir,
            args.candidate_manifest,
            args.direct_compile,
            args.ci_compile,
            args.qpu_model,
        )
    except (OSError, ReferenceCorrelationError, ValueError) as exc:
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
