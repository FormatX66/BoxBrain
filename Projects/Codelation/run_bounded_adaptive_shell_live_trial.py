#!/usr/bin/env python3
"""Run one carrier-backed adaptive-shell trial in an ephemeral state workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Mapping


FIELD_DIR = Path(__file__).resolve().parent / "field"
sys.path.insert(0, str(FIELD_DIR))

from external_prerequisite_evidence import (  # noqa: E402
    EVIDENCE_PATH,
    READINESS_EVIDENCE_PATH,
    TRIAL_EVIDENCE_KIND,
    TRIAL_EVIDENCE_PATH,
    TRIAL_EVIDENCE_SCHEMA,
    TRIAL_EVIDENCE_SOURCE,
    apply_external_prerequisite_evidence_from_file,
)
from native_gap_catalog import get_native_semantic_gap  # noqa: E402


PROPOSED_DELTA = "add=terminal;remove=none;evidence=coding-confidence-high"
MAX_RESULT_LIFETIME_SECONDS = 900


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _atomic_json_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def run_trial(
    *,
    physical_path: Path = EVIDENCE_PATH,
    readiness_path: Path = READINESS_EVIDENCE_PATH,
    output_path: Path = TRIAL_EVIDENCE_PATH,
    now: int | None = None,
) -> dict[str, Any]:
    observed_at = int(time.time()) if now is None else int(now)
    readiness_spec = get_native_semantic_gap("adaptive_shell_live_trial_readiness")
    if readiness_spec is None:
        raise ValueError("adaptive-shell readiness spec is missing")
    readiness = apply_external_prerequisite_evidence_from_file(
        readiness_spec,
        path=physical_path,
        readiness_path=readiness_path,
        now=observed_at,
    )
    if not readiness.applied or readiness.evidence is None:
        raise ValueError(f"adaptive-shell readiness evidence rejected: {readiness.reason}")
    if any(readiness.spec.invocation_arguments.get(name) != "yes" for name in readiness.spec.parameters):
        raise ValueError("adaptive-shell readiness conditions are not all verified")

    readiness_bytes = readiness_path.read_bytes()
    if len(readiness_bytes) > 16384:
        raise ValueError("adaptive-shell readiness evidence exceeded the bounded size")
    readiness_sha256 = _sha256(readiness_bytes)
    readiness_trace = dict(readiness.evidence)
    node_id = str(readiness_trace.get("node_id") or "")
    route = str(readiness_trace.get("route") or "")
    readiness_expires_at = int(readiness_trace.get("expires_at") or 0)
    if not node_id or not route or readiness_expires_at <= observed_at:
        raise ValueError("adaptive-shell readiness binding is incomplete or expired")

    baseline = {
        "schema": "aurum-ephemeral-shell-state-v1",
        "mode": "safe",
        "panels": ["proof-view"],
        "protected": ["safe-layout", "user-pins", "accessibility"],
    }
    candidate = {
        "schema": "aurum-ephemeral-shell-state-v1",
        "mode": "coding",
        "panels": ["proof-view", "terminal"],
        "protected": ["safe-layout", "user-pins", "accessibility"],
    }
    baseline_bytes = _canonical(baseline)
    candidate_bytes = _canonical(candidate)
    baseline_sha256 = _sha256(baseline_bytes)
    candidate_sha256 = _sha256(candidate_bytes)

    workspace_cleaned = False
    restored_sha256 = ""
    with tempfile.TemporaryDirectory(prefix="aurum-adaptive-shell-live-trial-") as directory:
        state_path = Path(directory) / "shell-state.json"
        state_path.write_bytes(baseline_bytes)
        if _sha256(state_path.read_bytes()) != baseline_sha256:
            raise ValueError("ephemeral baseline readback failed")
        state_path.write_bytes(candidate_bytes)
        applied = json.loads(state_path.read_text(encoding="utf-8"))
        if (
            applied.get("mode") != "coding"
            or "terminal" not in applied.get("panels", [])
            or "safe-layout" not in applied.get("protected", [])
        ):
            raise ValueError("bounded adaptive-shell proposal did not apply in the ephemeral workspace")
        state_path.write_bytes(baseline_bytes)
        restored_sha256 = _sha256(state_path.read_bytes())
        if restored_sha256 != baseline_sha256:
            raise ValueError("ephemeral adaptive-shell rollback digest mismatch")
    workspace_cleaned = True

    expires_at = min(readiness_expires_at, observed_at + MAX_RESULT_LIFETIME_SECONDS)
    if expires_at <= observed_at:
        raise ValueError("adaptive-shell trial result would already be expired")
    core: dict[str, Any] = {
        "schema": TRIAL_EVIDENCE_SCHEMA,
        "kind": TRIAL_EVIDENCE_KIND,
        "source": TRIAL_EVIDENCE_SOURCE,
        "verified": True,
        "node_id": node_id,
        "route": route,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "readiness_evidence_sha256": readiness_sha256,
        "proposal": {
            "verified": True,
            "delta": PROPOSED_DELTA,
            "protected": ["safe-layout", "user-pins", "accessibility"],
        },
        "application": {
            "verified": True,
            "scope": "ephemeral-trial-workspace",
            "persistent": False,
            "candidate_sha256": candidate_sha256,
        },
        "rollback": {
            "verified": restored_sha256 == baseline_sha256,
            "baseline_sha256": baseline_sha256,
            "restored_sha256": restored_sha256,
            "workspace_cleaned": workspace_cleaned,
        },
        "safety": {
            "raw_disk_changed": False,
            "firmware_changed": False,
            "bootloader_changed": False,
            "service_state_changed": False,
            "persistent_interface_changed": False,
        },
        "authority_granted": False,
    }
    trial_identity = _sha256(_canonical(core))
    result = dict(core)
    result["trial_identity"] = trial_identity
    result["proof_view"] = {
        "present": True,
        "trial_identity": trial_identity,
        "readiness_evidence_sha256": readiness_sha256,
        "baseline_sha256": baseline_sha256,
        "candidate_sha256": candidate_sha256,
        "restored_sha256": restored_sha256,
    }
    _atomic_json_write(output_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physical-evidence", type=Path, default=EVIDENCE_PATH)
    parser.add_argument("--readiness-evidence", type=Path, default=READINESS_EVIDENCE_PATH)
    parser.add_argument("--output", type=Path, default=TRIAL_EVIDENCE_PATH)
    args = parser.parse_args()
    result = run_trial(
        physical_path=args.physical_evidence,
        readiness_path=args.readiness_evidence,
        output_path=args.output,
    )
    print(
        "AURUM_ADAPTIVE_SHELL_LIVE_TRIAL_OK "
        f"node_id={result['node_id']} route={result['route']} "
        f"trial_identity={result['trial_identity']} persistent_change=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
