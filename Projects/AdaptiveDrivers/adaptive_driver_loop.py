"""Safe userspace adaptive-driver self-build loop for Raspberry Pi 3.

The first candidate is deliberately a read-only userspace compatibility shim.
It observes the same sysfs network facts as the Linux Last Known Good driver,
but it never binds/unbinds a kernel module, writes firmware, changes networking,
or mutates boot state. A generation-2 observer adds Pi-specific incomplete-read
evidence without crossing that safety boundary. That makes the complete
build/load/score/promotion/quarantine loop testable before a later kernel-module
canary earns stronger recovery evidence.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import py_compile
import re
import shlex
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping, Sequence


LOOP_SCHEMA = "aurum-adaptive-driver-loop-v1"
FINGERPRINT_SCHEMA = "aurum-hardware-fingerprint-v1"
LKG_SCHEMA = "aurum-adaptive-driver-lkg-v1"
PI3_MODEL_MARKER = "Raspberry Pi 3"
ARM_ARCHITECTURES = {"armv7l", "armv8l", "aarch64", "arm64"}
OBSERVATION_FIELDS = (
    "address",
    "carrier",
    "mtu",
    "operstate",
    "type",
    "rx_packets",
    "tx_packets",
)
SAFE_INTERFACE = re.compile(r"^[A-Za-z0-9_.:-]+$")


@dataclass(frozen=True)
class DriverCandidate:
    candidate_id: str
    generation: int
    fields: tuple[str, ...]
    strict: bool
    predicted_coverage: float
    risk: str = "low"
    fault_mode: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _sha256_value(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip("\x00\n \t")
    except (FileNotFoundError, PermissionError, IsADirectoryError, OSError):
        return ""


def _rooted(root: Path, relative: str) -> Path:
    return root / relative.strip("/\\")


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    data = json.dumps(value, indent=2, sort_keys=True) + "\n"
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _network_field_path(root: Path, interface: str, field: str) -> Path:
    base = _rooted(root, f"sys/class/net/{interface}")
    if field == "rx_packets":
        return base / "statistics/rx_packets"
    if field == "tx_packets":
        return base / "statistics/tx_packets"
    return base / field


def _network_observation(
    root: Path, interface: str, fields: Iterable[str] = OBSERVATION_FIELDS
) -> dict[str, str]:
    if not SAFE_INTERFACE.fullmatch(interface):
        raise ValueError(f"unsafe interface identifier: {interface!r}")
    return {
        field: _read_text(_network_field_path(root, interface, field))
        for field in fields
    }


def collect_hardware_fingerprint(
    root: Path = Path("/"), *, platform_overrides: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Collect a bounded, read-only hardware identity and network inventory."""

    overrides = dict(platform_overrides or {})
    model = _read_text(_rooted(root, "proc/device-tree/model"))
    if not model:
        model = _read_text(_rooted(root, "sys/firmware/devicetree/base/model"))
    compatible_raw = _read_text(_rooted(root, "proc/device-tree/compatible"))
    if not compatible_raw:
        compatible_raw = _read_text(
            _rooted(root, "sys/firmware/devicetree/base/compatible")
        )
    compatible = [item for item in compatible_raw.split("\x00") if item]

    net_root = _rooted(root, "sys/class/net")
    try:
        interface_names = sorted(entry.name for entry in net_root.iterdir())
    except (FileNotFoundError, PermissionError, OSError):
        interface_names = []

    interfaces: list[dict[str, Any]] = []
    for name in interface_names:
        if not SAFE_INTERFACE.fullmatch(name):
            continue
        base = net_root / name
        driver = ""
        try:
            driver = (base / "device/driver").resolve(strict=True).name
        except (FileNotFoundError, PermissionError, OSError):
            driver = ""
        interfaces.append(
            {
                "name": name,
                "driver": driver,
                "modalias": _read_text(base / "device/modalias"),
                "available_fields": [
                    field
                    for field in OBSERVATION_FIELDS
                    if _network_field_path(root, name, field).is_file()
                ],
            }
        )

    facts = {
        "schema": FINGERPRINT_SCHEMA,
        "model": overrides.get("model", model),
        "compatible": overrides.get("compatible", compatible),
        "arch": str(overrides.get("arch", platform.machine())).lower(),
        "kernel": str(overrides.get("kernel", platform.release())),
        "hostname": str(overrides.get("hostname", platform.node())),
        "boot_id": str(
            overrides.get(
                "boot_id", _read_text(_rooted(root, "proc/sys/kernel/random/boot_id"))
            )
        ),
        "interfaces": interfaces,
    }
    # Boot ID and hostname prove a live execution but are not hardware identity.
    # Excluding them keeps the same Pi eligible after a clean reboot while still
    # invalidating the fingerprint for kernel, topology, or device changes.
    identity_material = {
        key: facts[key]
        for key in ("schema", "model", "compatible", "arch", "kernel", "interfaces")
    }
    facts["fingerprint_sha256"] = _sha256_value(identity_material)
    return facts


def gate_pi3_fingerprint(fingerprint: Mapping[str, Any]) -> dict[str, Any]:
    problems: list[str] = []
    if fingerprint.get("schema") != FINGERPRINT_SCHEMA:
        problems.append("unknown-fingerprint-schema")
    if PI3_MODEL_MARKER not in str(fingerprint.get("model", "")):
        problems.append("model-not-raspberry-pi-3")
    if str(fingerprint.get("arch", "")).lower() not in ARM_ARCHITECTURES:
        problems.append("unexpected-arm-architecture")
    if not str(fingerprint.get("boot_id", "")).strip():
        problems.append("missing-boot-id")
    interfaces = fingerprint.get("interfaces")
    if not isinstance(interfaces, list) or not interfaces:
        problems.append("missing-interface-inventory")
    return {
        "accepted": not problems,
        "state": "physical-pi3-verified" if not problems else "hold",
        "problems": problems,
        "kernel_driver_mutation_allowed": False,
        "firmware_mutation_allowed": False,
    }


def build_capability_model(fingerprint: Mapping[str, Any]) -> dict[str, Any]:
    interfaces = [
        item
        for item in fingerprint.get("interfaces", [])
        if isinstance(item, dict) and item.get("name") != "lo"
    ]
    target = interfaces[0] if interfaces else None
    available = set(target.get("available_fields", [])) if target else set()
    return {
        "schema": "aurum-driver-capability-model-v1",
        "target_class": "network-interface" if target else "unresolved",
        "target_interface": target.get("name") if target else None,
        "reference_driver": target.get("driver") if target else "",
        "modalias": target.get("modalias") if target else "",
        "capabilities": {
            "read-link-identity": {"supported": "address" in available},
            "read-link-state": {
                "supported": {"carrier", "operstate"}.issubset(available)
            },
            "read-link-shape": {"supported": {"mtu", "type"}.issubset(available)},
            "read-packet-counters": {
                "supported": {"rx_packets", "tx_packets"}.issubset(available)
            },
        },
        "required_fields": list(OBSERVATION_FIELDS),
        "available_fields": sorted(available),
        "write_capabilities": [],
        "risk": "read-only",
    }


def candidate_catalog(*, include_faults: bool = False) -> tuple[DriverCandidate, ...]:
    candidates = [
        DriverCandidate(
            "pi3-net-sysfs-strict-v1", 1, OBSERVATION_FIELDS, True, 1.0
        ),
        DriverCandidate(
            "pi3-net-sysfs-tolerant-v1", 1, OBSERVATION_FIELDS, False, 1.0
        ),
        DriverCandidate(
            "pi3-net-sysfs-tolerant-v2", 2, OBSERVATION_FIELDS, False, 1.0
        ),
        DriverCandidate(
            "pi3-net-sysfs-minimal-v1",
            1,
            ("address", "mtu", "operstate"),
            True,
            3 / len(OBSERVATION_FIELDS),
        ),
    ]
    if include_faults:
        candidates.extend(
            [
                DriverCandidate(
                    "pi3-net-sysfs-mismatch-fixture",
                    1,
                    OBSERVATION_FIELDS,
                    True,
                    1.0,
                    fault_mode="mismatch",
                ),
                DriverCandidate(
                    "pi3-net-sysfs-build-failure-fixture",
                    1,
                    OBSERVATION_FIELDS,
                    True,
                    1.0,
                    fault_mode="syntax-error",
                ),
                DriverCandidate(
                    "pi3-net-sysfs-tolerant-v2-missing-field-fixture",
                    2,
                    OBSERVATION_FIELDS,
                    False,
                    1.0,
                    risk="fixture-only",
                    fault_mode="missing-sysfs-field",
                ),
            ]
        )
    return tuple(candidates)


def rank_candidates(
    candidates: Sequence[DriverCandidate],
    *,
    qpu_command: str | None = None,
    qpu_min_candidates: int = 8,
    estimated_candidate_test_ms: float = 250.0,
) -> tuple[list[DriverCandidate], dict[str, Any]]:
    """Rank classically, optionally accepting a measured QPU shortlist."""

    started = time.perf_counter()
    classical = sorted(
        candidates,
        key=lambda item: (
            item.risk != "low",
            -item.predicted_coverage,
            item.strict is False,
            item.candidate_id,
        ),
    )
    classical_ms = (time.perf_counter() - started) * 1000
    evidence: dict[str, Any] = {
        "classical_fallback": True,
        "classical_ms": round(classical_ms, 4),
        "qpu_requested": bool(qpu_command),
        "qpu_used": False,
    }
    if not qpu_command:
        evidence["qpu_reason"] = "unavailable-or-not-configured"
        return classical, evidence
    if len(candidates) < qpu_min_candidates:
        evidence["qpu_reason"] = "candidate-space-too-small"
        return classical, evidence

    payload = {
        "objective": "maximize predicted coverage; minimize risk and physical tests",
        "candidates": [asdict(candidate) for candidate in candidates],
        "output_schema": {"ordered_ids": ["candidate-id"]},
    }
    qpu_started = time.perf_counter()
    try:
        completed = subprocess.run(
            shlex.split(qpu_command),
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        qpu_ms = (time.perf_counter() - qpu_started) * 1000
        evidence["qpu_ms"] = round(qpu_ms, 4)
        if completed.returncode != 0:
            evidence["qpu_reason"] = "provider-nonzero-exit"
            return classical, evidence
        response = json.loads(completed.stdout)
        ordered_ids = response.get("ordered_ids", [])
        by_id = {candidate.candidate_id: candidate for candidate in candidates}
        if (
            not isinstance(ordered_ids, list)
            or not ordered_ids
            or any(item not in by_id for item in ordered_ids)
            or len(set(ordered_ids)) != len(ordered_ids)
        ):
            evidence["qpu_reason"] = "invalid-provider-result"
            return classical, evidence
        proposed_first = by_id[ordered_ids[0]]
        classical_first = classical[0]
        if (
            proposed_first.risk != "low"
            or proposed_first.predicted_coverage < classical_first.predicted_coverage
        ):
            evidence["qpu_reason"] = "provider-result-inferior-to-classical-proof"
            return classical, evidence
        avoided = max(0, len(candidates) - len(ordered_ids))
        estimated_savings_ms = avoided * estimated_candidate_test_ms
        evidence["estimated_candidate_tests_avoided"] = avoided
        evidence["estimated_savings_ms"] = estimated_savings_ms
        if qpu_ms >= estimated_savings_ms:
            evidence["qpu_reason"] = "no-measurable-value"
            return classical, evidence
        selected = [by_id[item] for item in ordered_ids]
        selected.extend(item for item in classical if item.candidate_id not in ordered_ids)
        evidence["qpu_used"] = True
        evidence["qpu_reason"] = "measured-test-reduction"
        return selected, evidence
    except (OSError, subprocess.TimeoutExpired, ValueError, json.JSONDecodeError) as exc:
        evidence["qpu_reason"] = f"provider-error:{type(exc).__name__}"
        return classical, evidence


def _candidate_source(candidate: DriverCandidate) -> str:
    if candidate.fault_mode == "syntax-error":
        return "def broken(:\n"
    fields = repr(candidate.fields)
    mismatch = candidate.fault_mode == "mismatch"
    missing_field = (
        "carrier" if candidate.fault_mode == "missing-sysfs-field" else None
    )
    return f'''#!/usr/bin/env python3
"""Synthesized Aurum read-only network interface candidate."""
import argparse
import json
from pathlib import Path
import re

CANDIDATE_ID = {candidate.candidate_id!r}
GENERATION = {candidate.generation!r}
FIELDS = {fields}
STRICT = {candidate.strict!r}
MISMATCH_FIXTURE = {mismatch!r}
MISSING_FIELD_FIXTURE = {missing_field!r}
SAFE_INTERFACE = re.compile(r"^[A-Za-z0-9_.:-]+$")

def field_path(root, interface, field):
    base = root / "sys" / "class" / "net" / interface
    if field == "rx_packets":
        return base / "statistics" / "rx_packets"
    if field == "tx_packets":
        return base / "statistics" / "tx_packets"
    return base / field

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--interface", required=True)
    args = parser.parse_args()
    if not SAFE_INTERFACE.fullmatch(args.interface):
        raise SystemExit("unsafe interface identifier")
    root = Path(args.root)
    observation = {{}}
    missing_fields = []
    for field in FIELDS:
        path = field_path(root, args.interface, field)
        try:
            if field == MISSING_FIELD_FIXTURE:
                raise FileNotFoundError("deterministic missing-sysfs-field fixture")
            observation[field] = path.read_text(encoding="utf-8", errors="replace").strip("\\x00\\n \\t")
        except (FileNotFoundError, PermissionError, IsADirectoryError, OSError):
            if STRICT:
                raise SystemExit("required read-only field unavailable: " + field)
            observation[field] = ""
            missing_fields.append(field)
    if MISMATCH_FIXTURE and "mtu" in observation:
        observation["mtu"] = "-1"
    print(json.dumps({{
        "candidate_id": CANDIDATE_ID,
        "generation": GENERATION,
        "observation": observation,
        "missing_fields": missing_fields,
        "evidence_complete": not missing_fields,
    }}, sort_keys=True))

if __name__ == "__main__":
    main()
'''


def synthesize_and_build(candidate: DriverCandidate, build_dir: Path) -> dict[str, Any]:
    build_dir.mkdir(parents=True, exist_ok=True)
    source_path = build_dir / "driver_candidate.py"
    source_path.write_text(_candidate_source(candidate), encoding="utf-8", newline="\n")
    try:
        py_compile.compile(
            str(source_path),
            cfile=str(build_dir / "driver_candidate.pyc"),
            doraise=True,
        )
    except py_compile.PyCompileError as exc:
        return {
            "state": "quarantined",
            "reason": "isolated-build-failed",
            "error_class": type(exc).__name__,
            "source_sha256": _sha256_file(source_path),
        }
    return {
        "state": "built",
        "source": str(source_path),
        "source_sha256": _sha256_file(source_path),
        "bytecode_sha256": _sha256_file(build_dir / "driver_candidate.pyc"),
        "build_mode": "isolated-python-bytecode",
    }


def load_and_test_candidate(
    candidate: DriverCandidate,
    build: Mapping[str, Any],
    *,
    root: Path,
    interface: str,
    repetitions: int = 3,
) -> dict[str, Any]:
    if build.get("state") != "built":
        raise ValueError("candidate must build before load/test")
    runs: list[dict[str, Any]] = []
    for _ in range(repetitions):
        started = time.perf_counter()
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                str(build["source"]),
                "--root",
                str(root),
                "--interface",
                interface,
            ],
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        parsed: dict[str, Any] | None = None
        if completed.returncode == 0:
            try:
                parsed = json.loads(completed.stdout)
            except json.JSONDecodeError:
                parsed = None
        runs.append(
            {
                "exit_code": completed.returncode,
                "elapsed_ms": round(elapsed_ms, 3),
                "output": parsed,
                "stderr": completed.stderr.strip()[:500],
            }
        )
    outputs = [run["output"] for run in runs if run["output"] is not None]
    observations = [item.get("observation", {}) for item in outputs]
    missing_fields = sorted(
        {
            field
            for item in outputs
            for field in item.get("missing_fields", [])
            if isinstance(field, str)
        }
    )
    static_fields = [
        field
        for field in candidate.fields
        if field not in {"rx_packets", "tx_packets"}
    ]
    static_repeatable = bool(observations) and all(
        all(item.get(field) == observations[0].get(field) for field in static_fields)
        for item in observations
    )
    counters_repeatable = True
    for field in ("rx_packets", "tx_packets"):
        if field not in candidate.fields:
            continue
        try:
            values = [int(item[field]) for item in observations]
        except (KeyError, TypeError, ValueError):
            counters_repeatable = False
            break
        if values != sorted(values):
            counters_repeatable = False
            break
    return {
        "state": "tested",
        "load_mode": "isolated-unprivileged-userspace-shim",
        "kernel_module_loaded": False,
        "kernel_driver_binding_changed": False,
        "missing_fields": missing_fields,
        "read_evidence_complete": (
            len(outputs) == repetitions
            and all(item.get("evidence_complete") is True for item in outputs)
        ),
        "runs": runs,
        "repeatable": (
            len(outputs) == repetitions and static_repeatable and counters_repeatable
        ),
    }


def score_candidate(
    candidate: DriverCandidate,
    test: Mapping[str, Any],
    baseline: Mapping[str, str],
    *,
    hardware_evidence_unchanged: bool,
) -> dict[str, Any]:
    outputs = [
        run.get("output")
        for run in test.get("runs", [])
        if run.get("exit_code") == 0 and isinstance(run.get("output"), dict)
    ]
    observation = outputs[0].get("observation", {}) if outputs else {}
    comparisons: dict[str, dict[str, Any]] = {}
    for field in candidate.fields:
        baseline_value = baseline.get(field, "")
        candidate_value = observation.get(field, "")
        if field in {"rx_packets", "tx_packets"}:
            try:
                matched = int(candidate_value) >= int(baseline_value)
            except (TypeError, ValueError):
                matched = False
            comparator = "monotonic-greater-than-or-equal"
        else:
            matched = candidate_value == baseline_value
            comparator = "exact"
        comparisons[field] = {
            "baseline": baseline_value,
            "candidate": candidate_value,
            "comparator": comparator,
            "match": matched,
        }
    functional_match = bool(comparisons) and all(
        item["match"] for item in comparisons.values()
    )
    coverage = len(candidate.fields) / len(OBSERVATION_FIELDS)
    score = 0.0
    if functional_match:
        score += 50.0
    score += 20.0 * coverage
    if test.get("repeatable"):
        score += 15.0
    if hardware_evidence_unchanged:
        score += 15.0
    return {
        "score": round(score, 3),
        "baseline_score": 100.0,
        "functional_match": functional_match,
        "coverage": round(coverage, 4),
        "repeatable": bool(test.get("repeatable")),
        "hardware_evidence_unchanged": hardware_evidence_unchanged,
        "comparisons": comparisons,
    }


def _initial_lkg(
    fingerprint: Mapping[str, Any], capability: Mapping[str, Any], baseline: Mapping[str, str]
) -> dict[str, Any]:
    return {
        "schema": LKG_SCHEMA,
        "active": {
            "profile_id": "pi3-linux-reference-driver",
            "kind": "kernel-reference",
            "score": 100.0,
            "fingerprint_sha256": fingerprint["fingerprint_sha256"],
            "interface": capability["target_interface"],
            "driver": capability["reference_driver"],
            "observation_sha256": _sha256_value(baseline),
        },
        "rollback": None,
        "protected_snapshots": [],
        "system_driver_changed": False,
    }


def ensure_lkg(
    state_dir: Path,
    fingerprint: Mapping[str, Any],
    capability: Mapping[str, Any],
    baseline: Mapping[str, str],
) -> tuple[dict[str, Any], Path]:
    path = state_dir / "lkg.json"
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))
        if current.get("schema") != LKG_SCHEMA:
            raise ValueError("refusing unknown LKG schema")
        return current, path
    current = _initial_lkg(fingerprint, capability, baseline)
    _atomic_write_json(path, current)
    return current, path


def promote_candidate(
    state_dir: Path,
    current_lkg: Mapping[str, Any],
    candidate: DriverCandidate,
    build: Mapping[str, Any],
    score: Mapping[str, Any],
    fingerprint: Mapping[str, Any],
) -> dict[str, Any]:
    snapshots = state_dir / "lkg-snapshots"
    current_hash = _sha256_value(current_lkg)
    snapshot_path = snapshots / f"{current_hash}.json"
    if not snapshot_path.exists():
        _atomic_write_json(snapshot_path, current_lkg)
    if _sha256_value(json.loads(snapshot_path.read_text(encoding="utf-8"))) != current_hash:
        raise ValueError("LKG rollback snapshot verification failed")
    protected = list(current_lkg.get("protected_snapshots", []))
    relative_snapshot = str(snapshot_path.relative_to(state_dir)).replace("\\", "/")
    if relative_snapshot not in protected:
        protected.append(relative_snapshot)
    promoted = {
        "schema": LKG_SCHEMA,
        "active": {
            "profile_id": candidate.candidate_id,
            "kind": (
                "generation-1-userspace-compatibility-shim"
                if candidate.generation == 1
                else "generation-2-userspace-hardware-specific-observer"
            ),
            "generation": candidate.generation,
            "score": score["score"],
            "fingerprint_sha256": fingerprint["fingerprint_sha256"],
            "artifact_sha256": build["source_sha256"],
        },
        "rollback": {
            "snapshot": relative_snapshot,
            "sha256": current_hash,
            "profile_id": current_lkg["active"]["profile_id"],
        },
        "protected_snapshots": protected,
        "system_driver_changed": False,
    }
    _atomic_write_json(state_dir / "lkg.json", promoted)
    return promoted


def rollback_to_previous(state_dir: Path) -> dict[str, Any]:
    lkg_path = state_dir / "lkg.json"
    current = json.loads(lkg_path.read_text(encoding="utf-8"))
    rollback = current.get("rollback")
    if not isinstance(rollback, dict):
        raise ValueError("no rollback target is recorded")
    snapshot_path = state_dir / rollback["snapshot"]
    restored = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if _sha256_value(restored) != rollback["sha256"]:
        raise ValueError("rollback snapshot hash mismatch")
    _atomic_write_json(lkg_path, restored)
    return restored


def provision_pi3_fixture(root: Path) -> dict[str, Any]:
    """Provision a deterministic fake sysfs/proc tree for non-hardware CI."""

    files = {
        "proc/device-tree/model": "Raspberry Pi 3 Model B Plus Rev 1.3\x00",
        "proc/device-tree/compatible": "raspberrypi,3-model-b-plus\x00brcm,bcm2837\x00",
        "proc/sys/kernel/random/boot_id": "11111111-2222-3333-4444-555555555555\n",
        "sys/class/net/eth0/address": "b8:27:eb:12:34:56\n",
        "sys/class/net/eth0/carrier": "1\n",
        "sys/class/net/eth0/mtu": "1500\n",
        "sys/class/net/eth0/operstate": "up\n",
        "sys/class/net/eth0/type": "1\n",
        "sys/class/net/eth0/statistics/rx_packets": "12000\n",
        "sys/class/net/eth0/statistics/tx_packets": "9000\n",
        "sys/class/net/eth0/device/modalias": "usb:v0424p7800d0300\n",
        "sys/class/net/lo/address": "00:00:00:00:00:00\n",
        "sys/class/net/lo/carrier": "1\n",
        "sys/class/net/lo/mtu": "65536\n",
        "sys/class/net/lo/operstate": "unknown\n",
        "sys/class/net/lo/type": "772\n",
        "sys/class/net/lo/statistics/rx_packets": "10\n",
        "sys/class/net/lo/statistics/tx_packets": "10\n",
    }
    for relative, content in files.items():
        path = _rooted(root, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")
    return {
        "model": "Raspberry Pi 3 Model B Plus Rev 1.3",
        "compatible": ["raspberrypi,3-model-b-plus", "brcm,bcm2837"],
        "arch": "armv7l",
        "kernel": "6.6.74-v7+",
        "hostname": "aurum-pi3-fixture",
        "boot_id": "11111111-2222-3333-4444-555555555555",
    }


def _future_branches(
    *,
    gate_accepted: bool,
    decision: str | None,
    next_candidate: str | None,
    qpu: Mapping[str, Any],
    missing_sysfs_fault_quarantined: bool = False,
) -> list[dict[str, Any]]:
    if not gate_accepted:
        return [
            {
                "branch_id": "pi3-strict-identity-reconnect",
                "status": "waiting",
                "confidence": 0.95,
                "safe_preparation": "runner and read-only probe are ready",
            },
            {
                "branch_id": "fixture-regression-loop",
                "status": "prepared",
                "confidence": 1.0,
                "safe_preparation": "full deterministic loop remains runnable without hardware",
            },
        ]
    branches = [
        {
            "branch_id": "next-generation-1-candidate",
            "status": "warm" if next_candidate else "cold",
            "confidence": 0.9,
            "candidate_id": next_candidate,
        },
        {
            "branch_id": "missing-sysfs-field-fault-injection",
            "status": (
                "quarantined" if missing_sysfs_fault_quarantined else "prepared"
            ),
            "confidence": 0.85,
            "purpose": "prove reject/quarantine and LKG preservation",
            **(
                {
                    "verification": (
                        "incomplete read evidence blocked promotion and preserved LKG"
                    )
                }
                if missing_sysfs_fault_quarantined
                else {}
            ),
        },
        {
            "branch_id": "pi3-kernel-module-canary",
            "status": "held",
            "confidence": 0.55,
            "requires": [
                "matching-kernel-headers",
                "out-of-band-watchdog",
                "reboot-recovery-proof",
                "explicit-kernel-mutation-gate",
            ],
        },
        {
            "branch_id": "qpu-candidate-ordering",
            "status": "used" if qpu.get("qpu_used") else "cold",
            "confidence": 0.25,
            "reason": qpu.get("qpu_reason"),
        },
    ]
    if decision in {"rejected", "quarantined"}:
        branches[0]["confidence"] = 0.97
    return branches


def run_adaptive_driver_loop(
    state_dir: Path,
    *,
    root: Path = Path("/"),
    platform_overrides: Mapping[str, Any] | None = None,
    allow_promotion: bool = False,
    requested_candidate: str | None = None,
    include_faults: bool = False,
    qpu_command: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Execute one complete, reversible adaptive-driver candidate cycle."""

    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = state_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = collect_hardware_fingerprint(root, platform_overrides=platform_overrides)
    gate = gate_pi3_fingerprint(fingerprint)
    result: dict[str, Any] = {
        "schema": LOOP_SCHEMA,
        "run_id": run_id,
        "started_at": _utc_now(),
        "target": "raspberry-pi-3-experimental",
        "fingerprint": fingerprint,
        "physical_gate": gate,
        "allow_promotion": allow_promotion,
        "system_driver_mutation_allowed": False,
        "system_driver_changed": False,
        "qpu": {
            "classical_fallback": True,
            "qpu_requested": bool(qpu_command),
            "qpu_used": False,
            "qpu_reason": "physical-gate-held",
        },
    }
    if not gate["accepted"]:
        result.update(
            {
                "state": "waiting",
                "decision": "quarantined",
                "reason": "physical-pi3-identity-not-proven",
                "future_branches": _future_branches(
                    gate_accepted=False,
                    decision="quarantined",
                    next_candidate=None,
                    qpu=result["qpu"],
                ),
            }
        )
        result["completed_at"] = _utc_now()
        _atomic_write_json(run_dir / "result.json", result)
        _append_jsonl(state_dir / "history.jsonl", result)
        return result

    capability = build_capability_model(fingerprint)
    interface = capability["target_interface"]
    if not interface:
        raise ValueError("Pi3 fingerprint has no non-loopback network interface")
    baseline = _network_observation(root, interface)
    initial_evidence_hash = _sha256_value(
        {
            "fingerprint_sha256": fingerprint["fingerprint_sha256"],
            "boot_id": fingerprint["boot_id"],
            "static_baseline": {
                field: baseline[field] for field in ("address", "mtu", "type")
            },
        }
    )
    current_lkg, lkg_path = ensure_lkg(state_dir, fingerprint, capability, baseline)
    lkg_before_hash = _sha256_file(lkg_path)
    active_fingerprint = str(current_lkg.get("active", {}).get("fingerprint_sha256", ""))
    if active_fingerprint != fingerprint["fingerprint_sha256"]:
        result.update(
            {
                "state": "completed",
                "decision": "quarantined",
                "reason": "hardware-or-kernel-fingerprint-changed",
                "capability_model": capability,
                "baseline": {
                    "profile_id": current_lkg["active"]["profile_id"],
                    "score": current_lkg["active"]["score"],
                    "observation": baseline,
                },
                "lkg": {
                    "before_sha256": lkg_before_hash,
                    "active_before": current_lkg["active"]["profile_id"],
                    "active_after": current_lkg["active"]["profile_id"],
                    "rollback": current_lkg.get("rollback"),
                    "system_driver_changed": current_lkg["system_driver_changed"],
                },
                "lkg_preserved": _sha256_file(lkg_path) == lkg_before_hash,
                "qpu": {
                    "classical_fallback": True,
                    "qpu_requested": False,
                    "qpu_used": False,
                    "qpu_reason": "candidate-selection-held-for-recharacterization",
                },
                "future_branches": [
                    {
                        "branch_id": "targeted-hardware-recharacterization",
                        "status": "warm",
                        "confidence": 1.0,
                        "safe_preparation": "retain prior LKG and collect a new read-only baseline",
                    },
                    {
                        "branch_id": "prior-lkg-rollback",
                        "status": "protected",
                        "confidence": 1.0,
                    },
                ],
            }
        )
        result["completed_at"] = _utc_now()
        _atomic_write_json(run_dir / "result.json", result)
        _append_jsonl(state_dir / "history.jsonl", result)
        return result

    candidates = candidate_catalog(include_faults=include_faults)
    if requested_candidate:
        matching = [item for item in candidates if item.candidate_id == requested_candidate]
        if not matching:
            raise ValueError(f"unknown requested candidate: {requested_candidate}")
        ordered = matching + [item for item in candidates if item not in matching]
        qpu_evidence = {
            "classical_fallback": True,
            "qpu_requested": False,
            "qpu_used": False,
            "qpu_reason": "explicit-candidate-request",
        }
    else:
        ordered, qpu_evidence = rank_candidates(candidates, qpu_command=qpu_command)
    candidate = ordered[0]
    next_candidate = ordered[1].candidate_id if len(ordered) > 1 else None
    build = synthesize_and_build(candidate, run_dir / "candidate")
    result.update(
        {
            "capability_model": capability,
            "baseline": {
                "profile_id": current_lkg["active"]["profile_id"],
                "score": current_lkg["active"]["score"],
                "observation": baseline,
            },
            "candidate": asdict(candidate),
            "candidate_selection": {
                "ordered_ids": [item.candidate_id for item in ordered],
                "next_candidate": next_candidate,
            },
            "build": build,
            "qpu": qpu_evidence,
            "lkg": {
                "before_sha256": lkg_before_hash,
                "active_before": current_lkg["active"]["profile_id"],
            },
        }
    )

    if build["state"] != "built":
        result.update(
            {
                "state": "completed",
                "decision": "quarantined",
                "reason": build["reason"],
                "lkg_preserved": _sha256_file(lkg_path) == lkg_before_hash,
                "lkg": {
                    **result["lkg"],
                    "active_after": current_lkg["active"]["profile_id"],
                    "rollback": current_lkg.get("rollback"),
                    "system_driver_changed": current_lkg["system_driver_changed"],
                },
            }
        )
    else:
        test = load_and_test_candidate(
            candidate, build, root=root, interface=interface
        )
        final_fingerprint = collect_hardware_fingerprint(
            root, platform_overrides=platform_overrides
        )
        final_baseline = _network_observation(root, interface)
        final_evidence_hash = _sha256_value(
            {
                "fingerprint_sha256": final_fingerprint["fingerprint_sha256"],
                "boot_id": final_fingerprint["boot_id"],
                "static_baseline": {
                    field: final_baseline[field] for field in ("address", "mtu", "type")
                },
            }
        )
        score = score_candidate(
            candidate,
            test,
            baseline,
            hardware_evidence_unchanged=initial_evidence_hash == final_evidence_hash,
        )
        lkg_untouched_during_test = _sha256_file(lkg_path) == lkg_before_hash
        if not lkg_untouched_during_test:
            decision = "quarantined"
            reason = "lkg-changed-during-candidate-test"
        elif test.get("missing_fields"):
            decision = "quarantined"
            reason = "required-read-only-field-unavailable"
        elif not score["functional_match"] or not score["repeatable"]:
            decision = "rejected"
            reason = "candidate-behavior-did-not-match-reference"
        elif score["score"] < score["baseline_score"]:
            decision = "rejected"
            reason = "candidate-did-not-meet-lkg-score"
        elif not allow_promotion:
            decision = "eligible-held"
            reason = "promotion-not-authorized"
        else:
            promote_candidate(
                state_dir, current_lkg, candidate, build, score, fingerprint
            )
            decision = "promoted"
            reason = "candidate-matched-lkg-and-rollback-snapshot-verified"
        lkg_after = json.loads(lkg_path.read_text(encoding="utf-8"))
        result.update(
            {
                "state": "completed",
                "test": test,
                "score": score,
                "decision": decision,
                "reason": reason,
                "lkg_preserved_during_test": lkg_untouched_during_test,
                "lkg": {
                    **result["lkg"],
                    "active_after": lkg_after["active"]["profile_id"],
                    "rollback": lkg_after.get("rollback"),
                    "system_driver_changed": lkg_after["system_driver_changed"],
                },
            }
        )

    result["future_branches"] = _future_branches(
        gate_accepted=True,
        decision=result["decision"],
        next_candidate=next_candidate,
        qpu=qpu_evidence,
        missing_sysfs_fault_quarantined=(
            candidate.fault_mode == "missing-sysfs-field"
            and result["decision"] == "quarantined"
        ),
    )
    result["completed_at"] = _utc_now()
    _atomic_write_json(run_dir / "result.json", result)
    _append_jsonl(state_dir / "history.jsonl", result)
    return result


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("/"))
    parser.add_argument("--fixture", choices=("pi3b",))
    parser.add_argument("--allow-promotion", action="store_true")
    parser.add_argument("--candidate")
    parser.add_argument("--include-faults", action="store_true")
    parser.add_argument("--qpu-command")
    parser.add_argument("--run-id")
    parser.add_argument("--result-file", type=Path)
    parser.add_argument("--rollback", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.rollback:
        result = rollback_to_previous(args.state_dir)
        print(json.dumps({"state": "rolled-back", "lkg": result}, indent=2, sort_keys=True))
        return 0
    root = args.root
    overrides = None
    if args.fixture == "pi3b":
        root = args.state_dir / "fixture-root"
        overrides = provision_pi3_fixture(root)
    result = run_adaptive_driver_loop(
        args.state_dir,
        root=root,
        platform_overrides=overrides,
        allow_promotion=args.allow_promotion,
        requested_candidate=args.candidate,
        include_faults=args.include_faults,
        qpu_command=args.qpu_command,
        run_id=args.run_id,
    )
    if args.result_file:
        _atomic_write_json(args.result_file, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
