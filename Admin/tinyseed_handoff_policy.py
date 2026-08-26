"""Monotonic policy helpers for Tiny Seed handoff automation."""
from __future__ import annotations

from typing import Any


def workflow_run_is_canonical(event_name: object, head_branch: object) -> bool:
    """Only main-branch build completions may advance the canonical handoff."""
    event = str(event_name or "").strip()
    branch = str(head_branch or "").strip()
    return event != "workflow_run" or branch == "main"


def release_identity(value: object) -> tuple[str, str, str, str, str] | None:
    """Return immutable release identity, excluding timestamps and runner ids."""
    if not isinstance(value, dict) or value.get("state") != "READY_TO_FLASH":
        return None
    source = str(value.get("source_commit") or "").strip().lower()
    artifacts = value.get("artifacts")
    if not source or not isinstance(artifacts, dict):
        return None
    parts: list[str] = [source]
    for architecture in ("x86", "pi"):
        artifact = artifacts.get(architecture)
        if not isinstance(artifact, dict):
            return None
        name = str(artifact.get("name") or "").strip()
        digest = str(artifact.get("sha256") or "").strip().lower()
        if not name or len(digest) != 64:
            return None
        parts.extend((name, digest))
    return tuple(parts)  # type: ignore[return-value]


def same_release_identity(current: object, candidate: object) -> bool:
    current_identity = release_identity(current)
    return current_identity is not None and current_identity == release_identity(candidate)
