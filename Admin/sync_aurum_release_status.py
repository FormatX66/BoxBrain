"""Synchronize Aurum completion-plan release and physical-flash truth."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HANDOFF_RELATIVE = Path("Projects/Aurum/Release/latest-tinyseed-handoff.json")
FLASH_RECEIPT_RELATIVE = Path("Projects/Aurum/Recovery/latest-tinyseed-flash-receipt.json")
PLAN_RELATIVE = Path("Projects/Aurum/completion-plan.json")
EXPECTED_SCHEMA = "aurum-tinyseed-handoff-v1"
EXPECTED_FLASH_SCHEMA = "aurum-tinyseed-flash-request-receipt-v1"
READY_TO_BOOT = "READY_TO_BOOT"


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


def _gate(plan: dict, gate_id: str) -> dict | None:
    gates = plan.get("gates")
    if gates is None:
        return None
    if not isinstance(gates, list):
        raise ReleaseStatusError("completion-plan gates must be an array")
    for gate in gates:
        if isinstance(gate, dict) and gate.get("id") == gate_id:
            return gate
    return None


def _project_physical_flash(plan: dict, *, source_commit: str, receipt: dict | None) -> bool:
    """Project only current-release raw-readback proof into physical x86 gates.

    A flash receipt proves media preparation only. It never proves that Hopper booted,
    that Guardian rolled back, or that a candidate may be promoted. A stale receipt is
    explicitly prevented from keeping a previous release's flash gate satisfied.
    """

    flash_gate = _gate(plan, "x86-physical-flash")
    boot_gate = _gate(plan, "x86-physical-boot")
    if flash_gate is None and boot_gate is None:
        return False

    matches = bool(
        receipt
        and receipt.get("schema") == EXPECTED_FLASH_SCHEMA
        and receipt.get("state") == READY_TO_BOOT
        and receipt.get("source_commit") == source_commit
        and receipt.get("raw_readback_verified") is True
    )

    changed = False
    if matches:
        if flash_gate is not None:
            desired = {
                "state": "passed-readback-verified",
                "ready_now": True,
            }
            for key, value in desired.items():
                if flash_gate.get(key) != value:
                    flash_gate[key] = value
                    changed = True
        if boot_gate is not None:
            desired = {
                "state": "ready-for-physical-boot-proof",
                "ready_now": False,
            }
            for key, value in desired.items():
                if boot_gate.get(key) != value:
                    boot_gate[key] = value
                    changed = True
        return changed

    # If the plan still claims a readback-proven flash from a previous release, fail
    # closed. Do not invent preflight readiness here; another projector owns that.
    if flash_gate is not None and flash_gate.get("state") == "passed-readback-verified":
        flash_gate["state"] = "blocked-on-current-release-flash-proof"
        flash_gate["ready_now"] = False
        changed = True
    if boot_gate is not None and boot_gate.get("state") == "ready-for-physical-boot-proof":
        boot_gate["state"] = "blocked-on-current-release-flash"
        boot_gate["ready_now"] = False
        changed = True
    return changed


def sync_release_status(root: Path = ROOT) -> dict:
    """Mirror canonical release identity and verified current-release flash proof.

    The handoff and durable flash receipt remain the authorities. This helper only
    projects their already-proven facts into the human completion graph; it does not
    grant write authority, infer physical boot, promote a candidate, or alter LKG.
    """

    handoff_path = root / HANDOFF_RELATIVE
    flash_path = root / FLASH_RECEIPT_RELATIVE
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

    receipt = _read_json(flash_path) if flash_path.is_file() else None
    if receipt is not None and receipt.get("schema") != EXPECTED_FLASH_SCHEMA:
        raise ReleaseStatusError("unexpected Tiny Seed flash receipt schema")

    plan = _read_json(plan_path)
    before = json.loads(json.dumps(plan))
    plan["latest_release_source_commit"] = source_commit
    plan["release_state"] = release_state
    _project_physical_flash(plan, source_commit=source_commit, receipt=receipt)

    changed = before != plan
    if changed:
        plan_path.write_text(
            json.dumps(plan, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )

    flash_ready_to_boot = bool(
        receipt
        and receipt.get("state") == READY_TO_BOOT
        and receipt.get("source_commit") == source_commit
        and receipt.get("raw_readback_verified") is True
    )
    return {
        "changed": changed,
        "source_commit": source_commit,
        "release_state": release_state,
        "flash_ready_to_boot": flash_ready_to_boot,
        "before": {
            "latest_release_source_commit": before.get("latest_release_source_commit"),
            "release_state": before.get("release_state"),
        },
        "after": {
            "latest_release_source_commit": source_commit,
            "release_state": release_state,
        },
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
        f"state={result['release_state']} "
        f"flash_ready_to_boot={str(result['flash_ready_to_boot']).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
