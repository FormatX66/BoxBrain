"""Convert preserved Pi 3 laboratory samples into sealed shadow decisions.

This adapter reads an already-downloaded ``samples.jsonl`` artifact.  It has no
live collector, SSH client, hardware adapter, or active policy executor.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from Projects.AdaptiveKernel.adaptive_runtime import evaluate_shadow_window


RECEIPT_SCHEMA = "aurum-adaptive-runtime-artifact-shadow-v1"
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
MAX_ARTIFACT_SAMPLES = 4096
MAX_JSONL_LINE_BYTES = 128 * 1024
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class ArtifactEvidenceError(ValueError):
    """The preserved artifact is malformed, ambiguous, or outside bounds."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    body = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return _sha256_bytes(body)


def verify_artifact_receipt(receipt: Mapping[str, Any]) -> bool:
    claimed = receipt.get("receipt_sha256")
    if not isinstance(claimed, str):
        return False
    unsealed = dict(receipt)
    unsealed.pop("receipt_sha256", None)
    return claimed == _canonical_sha256(unsealed)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ArtifactEvidenceError(f"{name} must be a mapping")
    return value


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ArtifactEvidenceError(f"{name} must be a nonnegative integer")
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ArtifactEvidenceError(f"{name} must be numeric")
    result = float(value)
    if result != result or result in {float("inf"), float("-inf")}:
        raise ArtifactEvidenceError(f"{name} must be finite")
    return result


def convert_overnight_sample(
    raw: Any,
    *,
    index: int,
    cpu_count: int = 4,
) -> dict[str, Any]:
    """Convert one overnight-lab sample to the governor's strict schema."""

    source = _mapping(raw, "sample")
    memory = _mapping(source.get("memory_kib"), "memory_kib")
    network = _mapping(source.get("network"), "network")
    throttled = _mapping(source.get("throttled"), "throttled")
    if isinstance(cpu_count, bool) or not isinstance(cpu_count, int) or cpu_count < 1:
        raise ArtifactEvidenceError("cpu_count must be a positive integer")

    loadavg = source.get("loadavg")
    if not isinstance(loadavg, str) or not loadavg.split():
        raise ArtifactEvidenceError("loadavg must contain a one-minute value")
    try:
        load_1m = float(loadavg.split()[0])
    except ValueError as exc:
        raise ArtifactEvidenceError("loadavg one-minute value is invalid") from exc

    current_fault = throttled.get("current_fault")
    if not isinstance(current_fault, bool):
        raise ArtifactEvidenceError("throttled.current_fault must be boolean")
    reference_driver = source.get("reference_driver")
    if not isinstance(reference_driver, str) or not reference_driver:
        raise ArtifactEvidenceError("reference_driver is required")

    elapsed = _number(source.get("elapsed_seconds"), "elapsed_seconds")
    if elapsed < 0:
        raise ArtifactEvidenceError("elapsed_seconds must be nonnegative")
    available_kib = _integer(memory.get("MemAvailable"), "memory_kib.MemAvailable")
    total_kib = _integer(memory.get("MemTotal"), "memory_kib.MemTotal")
    if total_kib < 1:
        raise ArtifactEvidenceError("memory_kib.MemTotal must be positive")

    return {
        "sample_id": f"overnight-{index:04d}",
        "temperature_c": _number(source.get("temperature_c"), "temperature_c"),
        "current_throttled": current_fault,
        "memory_available_bytes": available_kib * 1024,
        "memory_total_bytes": total_kib * 1024,
        "load_1m": load_1m,
        "cpu_count": cpu_count,
        "ethernet": {
            "carrier": network.get("carrier"),
            "operstate": network.get("operstate"),
            "reference_driver": reference_driver,
            "rx_errors": _integer(network.get("rx_errors"), "network.rx_errors"),
            "tx_errors": _integer(network.get("tx_errors"), "network.tx_errors"),
            "rx_dropped": _integer(network.get("rx_dropped"), "network.rx_dropped"),
            "tx_dropped": _integer(network.get("tx_dropped"), "network.tx_dropped"),
        },
        "source": {
            "elapsed_seconds": round(elapsed, 3),
            "timestamp": source.get("timestamp"),
        },
    }


def load_overnight_samples(path: Path) -> tuple[list[dict[str, Any]], str]:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ArtifactEvidenceError("samples artifact must be a file")
    body = resolved.read_bytes()
    if len(body) > MAX_ARTIFACT_BYTES:
        raise ArtifactEvidenceError("samples artifact exceeds the bounded size")
    lines = body.splitlines()
    if not lines or len(lines) > MAX_ARTIFACT_SAMPLES:
        raise ArtifactEvidenceError("samples artifact count is empty or outside bounds")

    samples: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        if not line or len(line) > MAX_JSONL_LINE_BYTES:
            raise ArtifactEvidenceError(f"sample line {index} is empty or outside bounds")
        try:
            parsed = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArtifactEvidenceError(f"sample line {index} is invalid JSON") from exc
        samples.append(convert_overnight_sample(parsed, index=index))
    return samples, _sha256_bytes(body)


def evaluate_overnight_artifact(
    samples_path: Path,
    *,
    artifact_id: int,
    artifact_digest: str,
    window_size: int = 16,
) -> dict[str, Any]:
    """Evaluate the last bounded evidence window without applying a change."""

    if isinstance(artifact_id, bool) or not isinstance(artifact_id, int) or artifact_id < 1:
        raise ArtifactEvidenceError("artifact_id must be a positive integer")
    if not isinstance(artifact_digest, str) or not _DIGEST.fullmatch(artifact_digest):
        raise ArtifactEvidenceError("artifact_digest must be a lowercase SHA-256 digest")
    if isinstance(window_size, bool) or not isinstance(window_size, int) or not 3 <= window_size <= 64:
        raise ArtifactEvidenceError("window_size must be between 3 and 64")

    samples, samples_sha256 = load_overnight_samples(samples_path)
    selected = samples[-window_size:]
    shadow = evaluate_shadow_window(selected, expected_reference_driver="smsc95xx")
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "mode": "preserved-artifact-shadow",
        "source": {
            "github_artifact_id": artifact_id,
            "github_artifact_digest": artifact_digest,
            "samples_jsonl_sha256": samples_sha256,
            "total_sample_count": len(samples),
            "window_sample_count": len(selected),
            "window_first_sample_id": selected[0]["sample_id"],
            "window_last_sample_id": selected[-1]["sample_id"],
            "window_first_elapsed_seconds": selected[0]["source"]["elapsed_seconds"],
            "window_last_elapsed_seconds": selected[-1]["source"]["elapsed_seconds"],
        },
        "shadow_receipt": shadow,
        "decision": {
            "state": shadow["decision"]["state"],
            "recommendation": shadow["decision"]["recommendation"],
            "selected_policy_id": shadow["decision"]["selected_policy_id"],
            "change_applied": False,
        },
        "invariants": {
            "preserved_artifact_only": True,
            "live_pi_contacted": False,
            "active_executor_connected": False,
            "kernel_changed": False,
            "driver_binding_changed": False,
            "boot_or_firmware_changed": False,
            "network_changed": False,
            "mutation_authority_granted": False,
        },
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return receipt


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", required=True, type=Path)
    parser.add_argument("--artifact-id", required=True, type=int)
    parser.add_argument("--artifact-digest", required=True)
    parser.add_argument("--window-size", type=int, default=16)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        receipt = evaluate_overnight_artifact(
            args.samples,
            artifact_id=args.artifact_id,
            artifact_digest=args.artifact_digest,
            window_size=args.window_size,
        )
    except (ArtifactEvidenceError, OSError, ValueError) as exc:
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "mode": "preserved-artifact-shadow",
            "state": "refused",
            "reason": str(exc),
            "mutation_authority_granted": False,
        }
        _write_json(args.output, receipt)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 1
    _write_json(args.output, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
