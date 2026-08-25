#!/usr/bin/env python3
"""Reconstruct Aurum from canonical repository truth plus a local runtime checkpoint.

This is the restart-side companion to ``checkpoint_aurum_runtime.py``. It validates
that a local checkpoint still matches the current durable Aurum state before
surfacing checkpointed running/retrying/runnable jobs and resume hints.

The checkpoint is evidence only. Loading it can never grant destructive authority,
promote a candidate, infer physical proof, or mutate Last Known Good state. Any
resumed job still requires a live dependency/authority recheck before side effects.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from Admin.checkpoint_aurum_runtime import DEFAULT_OUTPUT, normalize_jobs, stable_digest
    from Admin.reconstruct_aurum_state import ROOT, ReconstructionError, reconstruct
except ModuleNotFoundError:  # Support `python Admin/resume_aurum_runtime.py`.
    from checkpoint_aurum_runtime import DEFAULT_OUTPUT, normalize_jobs, stable_digest
    from reconstruct_aurum_state import ROOT, ReconstructionError, reconstruct

DEFAULT_MAX_AGE_SECONDS = 24 * 60 * 60


class ResumeError(ValueError):
    """Checkpoint evidence is missing, stale, incomplete, contradictory, or unsafe."""


def read_checkpoint(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ResumeError(f"runtime checkpoint missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ResumeError(f"runtime checkpoint invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ResumeError("runtime checkpoint must be a JSON object")
    if value.get("schema") != "aurum-runtime-checkpoint-v1":
        raise ResumeError(f"unsupported runtime checkpoint schema: {value.get('schema')!r}")
    return value


def parse_checkpoint_time(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ResumeError("runtime checkpoint created_at_utc missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResumeError(f"runtime checkpoint created_at_utc invalid: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ResumeError("runtime checkpoint created_at_utc must include timezone")
    return parsed.astimezone(timezone.utc)


def _require_zero_authority(checkpoint: dict[str, Any]) -> None:
    authority = checkpoint.get("authority")
    if not isinstance(authority, dict):
        raise ResumeError("runtime checkpoint authority block missing")
    forbidden = (
        "authority_granted",
        "checkpoint_authoritative_for_destructive_action",
        "candidate_promotion_allowed",
        "lkg_mutation_allowed",
    )
    asserted = [key for key in forbidden if bool(authority.get(key))]
    if asserted:
        raise ResumeError(f"runtime checkpoint asserts forbidden authority: {asserted}")
    if authority.get("live_recheck_required") is not True:
        raise ResumeError("runtime checkpoint must require live recheck")


def resume_state(
    *,
    root: Path = ROOT,
    checkpoint_path: Path = DEFAULT_OUTPUT,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate and merge durable repository truth with checkpointed runtime evidence."""
    if max_age_seconds < 0:
        raise ResumeError("max_age_seconds must be non-negative")
    root = root.resolve()
    durable = reconstruct(root)
    checkpoint = read_checkpoint(checkpoint_path)
    _require_zero_authority(checkpoint)

    durable_digest = stable_digest(durable)
    checkpoint_digest = checkpoint.get("durable_state_sha256")
    if checkpoint_digest != durable_digest:
        raise ResumeError(
            "runtime checkpoint durable-state digest mismatch; canonical state changed since checkpoint"
        )

    release_source = durable.get("release", {}).get("source_commit")
    if checkpoint.get("release_source_commit") != release_source:
        raise ResumeError("runtime checkpoint release provenance mismatch")

    canonical_next_gate = (
        durable.get("answers", {})
        .get("what_should_execute_next", {})
        .get("canonical_next_gate")
    )
    if checkpoint.get("canonical_next_gate") != canonical_next_gate:
        raise ResumeError("runtime checkpoint canonical next gate mismatch")

    created_at = parse_checkpoint_time(checkpoint.get("created_at_utc"))
    observed_now = now or datetime.now(timezone.utc)
    if observed_now.tzinfo is None:
        raise ResumeError("now must include timezone")
    observed_now = observed_now.astimezone(timezone.utc)
    age_seconds = (observed_now - created_at).total_seconds()
    if age_seconds < -300:
        raise ResumeError("runtime checkpoint timestamp is implausibly in the future")
    age_seconds = max(0.0, age_seconds)
    if age_seconds > max_age_seconds:
        raise ResumeError(
            f"runtime checkpoint stale: age_seconds={int(age_seconds)} max_age_seconds={max_age_seconds}"
        )

    runtime = checkpoint.get("runtime")
    if not isinstance(runtime, dict):
        raise ResumeError("runtime checkpoint runtime block missing")
    jobs = normalize_jobs(runtime.get("jobs"))
    checkpointed_running = [job for job in jobs if job["state"] == "running"]
    checkpointed_retrying = [job for job in jobs if job["state"] == "retrying"]
    checkpointed_runnable = [job for job in jobs if job["state"] == "runnable"]
    checkpointed_failed = [job for job in jobs if job["state"] == "failed"]
    checkpointed_blocked = [job for job in jobs if job["state"] == "blocked"]

    repository_head = checkpoint.get("repository_head")
    live_head = None
    try:
        from Admin.checkpoint_aurum_runtime import repository_head as read_repository_head
    except ModuleNotFoundError:
        from checkpoint_aurum_runtime import repository_head as read_repository_head
    try:
        live_head = read_repository_head(root)
    except Exception:
        live_head = None
    head_changed = bool(repository_head and live_head and repository_head != live_head)

    return {
        "schema": "aurum-runtime-resume-v1",
        "mode": "durable-repository-plus-local-checkpoint",
        "checkpoint": {
            "path": str(checkpoint_path),
            "created_at_utc": created_at.isoformat(),
            "age_seconds": int(age_seconds),
            "repository_head_at_checkpoint": repository_head,
            "repository_head_now": live_head,
            "repository_head_changed": head_changed,
            "durable_state_sha256": durable_digest,
            "release_source_commit": release_source,
            "canonical_next_gate": canonical_next_gate,
        },
        "durable": durable,
        "runtime": {
            "jobs": jobs,
            "checkpointed_running": checkpointed_running,
            "checkpointed_retrying": checkpointed_retrying,
            "checkpointed_runnable": checkpointed_runnable,
            "checkpointed_failed": checkpointed_failed,
            "checkpointed_blocked": checkpointed_blocked,
            "hardware_fingerprint": runtime.get("hardware_fingerprint", {}),
            "software_fingerprint": runtime.get("software_fingerprint", {}),
            "active_hypotheses": runtime.get("active_hypotheses", []),
            "local_artifacts": runtime.get("local_artifacts", []),
            "live_process_inferred": False,
            "resume_policy": "checkpointed jobs are evidence/resume hints only; revalidate live dependencies before execution",
            "repository_head_change_requires_job_revalidation": head_changed,
        },
        "answers": {
            **durable.get("answers", {}),
            "what_is_running_or_runnable": {
                "running_live": [],
                "checkpointed_running": checkpointed_running,
                "checkpointed_retrying": checkpointed_retrying,
                "checkpointed_runnable": checkpointed_runnable,
                "durable_runnable": durable.get("answers", {})
                .get("what_is_running_or_runnable", {})
                .get("runnable", []),
                "truth": "Runtime jobs are restored from a validated checkpoint but are not claimed live until the runtime re-observes them.",
            },
            "what_is_blocked_or_failed_locally": {
                "checkpointed_blocked": checkpointed_blocked,
                "checkpointed_failed": checkpointed_failed,
            },
        },
        "authority": {
            "checkpoint_authoritative_for_destructive_action": False,
            "authority_granted": False,
            "candidate_promotion_allowed": False,
            "lkg_mutation_allowed": False,
            "physical_proof_inferred": False,
            "live_recheck_required": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-age-seconds", type=int, default=DEFAULT_MAX_AGE_SECONDS)
    args = parser.parse_args()
    try:
        result = resume_state(
            root=args.root,
            checkpoint_path=args.checkpoint,
            max_age_seconds=args.max_age_seconds,
        )
    except (ResumeError, ReconstructionError) as exc:
        raise SystemExit(f"AURUM_RUNTIME_RESUME_REFUSED reason={exc}") from exc
    print(json.dumps(result, indent=2, sort_keys=False))


if __name__ == "__main__":
    main()
