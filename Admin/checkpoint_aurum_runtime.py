#!/usr/bin/env python3
"""Write Aurum's local operational checkpoint atomically.

The checkpoint complements, but never overrides, durable repository authority.
It is intended for local/resumable execution state that should survive a process
restart without being committed to Git: running/retrying/failed jobs, local
hardware/software fingerprints, active hypotheses, local artifact references,
and a bounded resume hint.

On nodes where Aurum Farmer is the persistent controller, Farmer's sealed SQLite
ledger is the production local operational-state authority. This generic JSON
checkpoint is then a compatibility/reconstruction projection and must be derived
from Farmer rather than maintained as a competing state store. On nodes without
Farmer, the generic checkpoint remains the bounded fallback local state layer.

The default path lives under data/, which is repository-ignored. The checkpoint
contains no destructive authority and cannot promote candidates or mutate LKG.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from Admin.reconstruct_aurum_state import ROOT, ReconstructionError, reconstruct
except ModuleNotFoundError:  # Support `python Admin/checkpoint_aurum_runtime.py`.
    from reconstruct_aurum_state import ROOT, ReconstructionError, reconstruct

DEFAULT_OUTPUT = ROOT / "data/aurum/runtime-checkpoint.json"
ALLOWED_JOB_STATES = {"running", "runnable", "blocked", "failed", "retrying", "completed"}


class CheckpointError(ValueError):
    """Local runtime overlay is invalid or unsafe to persist."""


def stable_digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def repository_head(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value if value else None


def read_overlay(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CheckpointError(f"runtime overlay missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CheckpointError(f"runtime overlay invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CheckpointError("runtime overlay must be a JSON object")
    return value


def normalize_jobs(value: object) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise CheckpointError("runtime jobs must be an array")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise CheckpointError("each runtime job must be an object")
        job_id = raw.get("id")
        state = raw.get("state")
        if not isinstance(job_id, str) or not job_id.strip():
            raise CheckpointError("runtime job id required")
        job_id = job_id.strip()
        if job_id in seen:
            raise CheckpointError(f"duplicate runtime job id: {job_id}")
        seen.add(job_id)
        if state not in ALLOWED_JOB_STATES:
            raise CheckpointError(f"invalid runtime job state for {job_id}: {state!r}")
        dependencies = raw.get("depends_on", [])
        if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
            raise CheckpointError(f"runtime job dependencies must be strings: {job_id}")
        result.append(
            {
                "id": job_id,
                "state": state,
                "depends_on": dependencies,
                "checkpoint": raw.get("checkpoint"),
                "evidence": raw.get("evidence"),
                "resume_hint": raw.get("resume_hint"),
            }
        )
    return result


def _dict_or_empty(value: object, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise CheckpointError(f"{name} must be an object")
    return value


def build_checkpoint(root: Path = ROOT, overlay: dict[str, Any] | None = None) -> dict[str, Any]:
    root = root.resolve()
    overlay = overlay or {}
    durable = reconstruct(root)
    jobs = normalize_jobs(overlay.get("jobs"))

    operational_state_source = overlay.get("operational_state_source", "generic-runtime-overlay")
    if not isinstance(operational_state_source, str) or not operational_state_source.strip():
        raise CheckpointError("operational_state_source must be a non-empty string")
    source_metadata = _dict_or_empty(overlay.get("source_metadata"), "source_metadata")

    resumable = [
        {
            "id": job["id"],
            "state": job["state"],
            "checkpoint": job.get("checkpoint"),
            "resume_hint": job.get("resume_hint"),
        }
        for job in jobs
        if job["state"] in {"running", "runnable", "retrying"}
    ]

    return {
        "schema": "aurum-runtime-checkpoint-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository_head": repository_head(root),
        "durable_reconstruction_schema": durable.get("schema"),
        "durable_state_sha256": stable_digest(durable),
        "release_source_commit": durable.get("release", {}).get("source_commit"),
        "canonical_next_gate": durable.get("answers", {})
        .get("what_should_execute_next", {})
        .get("canonical_next_gate"),
        "runtime": {
            "operational_state_source": operational_state_source.strip(),
            "source_metadata": source_metadata,
            "jobs": jobs,
            "resumable": resumable,
            "hardware_fingerprint": _dict_or_empty(overlay.get("hardware_fingerprint"), "hardware_fingerprint"),
            "software_fingerprint": _dict_or_empty(overlay.get("software_fingerprint"), "software_fingerprint"),
            "active_hypotheses": overlay.get("active_hypotheses", []),
            "local_artifacts": overlay.get("local_artifacts", []),
        },
        "recovery": durable.get("answers", {}).get("what_recovery_or_fallback_exists"),
        "authority": {
            "checkpoint_authoritative_for_destructive_action": False,
            "live_recheck_required": True,
            "authority_granted": False,
            "candidate_promotion_allowed": False,
            "lkg_mutation_allowed": False,
        },
    }


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(value, indent=2, sort_keys=False) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def checkpoint(
    *,
    root: Path = ROOT,
    output: Path = DEFAULT_OUTPUT,
    overlay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = build_checkpoint(root=root, overlay=overlay)
    atomic_write_json(output, value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--runtime-overlay", type=Path)
    args = parser.parse_args()
    try:
        value = checkpoint(
            root=args.root,
            output=args.output,
            overlay=read_overlay(args.runtime_overlay),
        )
    except (CheckpointError, ReconstructionError) as exc:
        raise SystemExit(f"AURUM_RUNTIME_CHECKPOINT_REFUSED reason={exc}") from exc
    print(
        json.dumps(
            {
                "schema": value["schema"],
                "output": str(args.output),
                "operational_state_source": value["runtime"]["operational_state_source"],
                "jobs": len(value["runtime"]["jobs"]),
                "resumable": len(value["runtime"]["resumable"]),
                "authority_granted": value["authority"]["authority_granted"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
