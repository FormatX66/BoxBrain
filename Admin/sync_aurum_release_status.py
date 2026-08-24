"""Synchronize Aurum completion-plan release identity from canonical handoff truth."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HANDOFF_RELATIVE = Path("Projects/Aurum/Release/latest-tinyseed-handoff.json")
PLAN_RELATIVE = Path("Projects/Aurum/completion-plan.json")
EXPECTED_SCHEMA = "aurum-tinyseed-handoff-v1"


class ReleaseStatusError(ValueError):
    """Raised when canonical release evidence is missing or malformed."""


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseStatusError(f"cannot read valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ReleaseStatusError(f"expected JSON object: {path}")
    return value


def sync_release_status(root: Path = ROOT) -> dict:
    """Make completion-plan release identity mirror the canonical handoff.

    The handoff remains the authority. This helper only projects its immutable
    source identity and release state into the human completion plan; it does not
    infer physical proof, grant flash authority, or alter any recovery state.
    """

    handoff_path = root / HANDOFF_RELATIVE
    plan_path = root / PLAN_RELATIVE
    handoff = _read_json(handoff_path)
    if handoff.get("schema") != EXPECTED_SCHEMA:
        raise ReleaseStatusError("unexpected Tiny Seed handoff schema")

    source_commit = handoff.get("source_commit")
    release_state = handoff.get("state")
    if not isinstance(source_commit, str) or not source_commit.strip():
        raise ReleaseStatusError("Tiny Seed handoff source_commit is required")
    if not isinstance(release_state, str) or not release_state.strip():
        raise ReleaseStatusError("Tiny Seed handoff state is required")

    plan = _read_json(plan_path)
    before = {
        "latest_release_source_commit": plan.get("latest_release_source_commit"),
        "release_state": plan.get("release_state"),
    }
    after = {
        "latest_release_source_commit": source_commit,
        "release_state": release_state,
    }
    changed = before != after
    if changed:
        plan.update(after)
        plan_path.write_text(
            json.dumps(plan, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )

    return {
        "changed": changed,
        "source_commit": source_commit,
        "release_state": release_state,
        "before": before,
        "after": after,
    }


def main() -> int:
    try:
        result = sync_release_status()
    except ReleaseStatusError as exc:
        print(f"AURUM_RELEASE_STATUS_SYNC_REFUSED reason={exc}", file=sys.stderr)
        return 1
    print(
        "AURUM_RELEASE_STATUS_SYNC "
        f"changed={str(result['changed']).lower()} "
        f"source_commit={result['source_commit']} "
        f"state={result['release_state']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
