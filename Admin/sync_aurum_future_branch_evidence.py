"""Synchronize Aurum Future Branch evidence from canonical release/preflight truth.

This helper projects only already-proven evidence. It never grants write authority,
changes recovery state, promotes a candidate, or infers physical proof.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HANDOFF_RELATIVE = Path("Projects/Aurum/Release/latest-tinyseed-handoff.json")
PREFLIGHT_RELATIVE = Path("Projects/Aurum/Recovery/latest-tinyseed-physical-preflight.json")
BRANCH_RELATIVE = Path("Projects/Aurum/future-branches.json")
HANDOFF_SCHEMA = "aurum-tinyseed-handoff-v1"


class FutureBranchEvidenceError(ValueError):
    """Raised when canonical evidence is missing or malformed."""


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FutureBranchEvidenceError(f"cannot read valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise FutureBranchEvidenceError(f"expected JSON object: {path}")
    return value


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FutureBranchEvidenceError(f"{name} is required")
    return value.strip()


def _optional_candidate(preflight: dict) -> dict | None:
    candidate = preflight.get("usb_candidate")
    if candidate is None:
        return None
    if not isinstance(candidate, dict):
        raise FutureBranchEvidenceError("usb_candidate must be an object or null")
    return {
        "disk_number": candidate.get("disk_number"),
        "model": candidate.get("model"),
        "size_bytes": candidate.get("size_bytes"),
        "serial_sha256": candidate.get("serial_sha256"),
        "is_boot": candidate.get("is_boot"),
        "is_system": candidate.get("is_system"),
        "is_read_only": candidate.get("is_read_only"),
        "protected": candidate.get("protected"),
        "eligible_for_preflight_only": candidate.get("eligible_for_preflight_only"),
    }


def sync_future_branch_evidence(root: Path = ROOT) -> dict:
    """Project canonical handoff and physical-preflight evidence into Future Branch."""

    handoff = _read_json(root / HANDOFF_RELATIVE)
    if handoff.get("schema") != HANDOFF_SCHEMA:
        raise FutureBranchEvidenceError("unexpected Tiny Seed handoff schema")

    source_commit = _required_text(handoff.get("source_commit"), "handoff source_commit")
    release_state = _required_text(handoff.get("state"), "handoff state")
    artifacts = handoff.get("artifacts")
    if not isinstance(artifacts, dict) or not isinstance(artifacts.get("x86"), dict):
        raise FutureBranchEvidenceError("handoff x86 artifact evidence is required")
    x86 = artifacts["x86"]
    x86_name = _required_text(x86.get("name"), "handoff x86 artifact name")
    x86_sha256 = _required_text(x86.get("sha256"), "handoff x86 sha256")

    preflight_path = root / PREFLIGHT_RELATIVE
    preflight = _read_json(preflight_path) if preflight_path.is_file() else {}
    preflight_source = preflight.get("release_source_commit")
    preflight_matches_release = preflight_source == source_commit if preflight else False
    preexecution = preflight.get("preexecution_recovery")
    if preexecution is not None and not isinstance(preexecution, dict):
        raise FutureBranchEvidenceError("preexecution_recovery must be an object or null")
    preexecution = preexecution or {}

    evidence = {
        "release": {
            "source_commit": source_commit,
            "state": release_state,
            "x86_artifact": x86_name,
            "x86_sha256": x86_sha256,
        },
        "physical_preflight": {
            "present": bool(preflight),
            "matches_current_release": preflight_matches_release,
            "state": preflight.get("state") if preflight else None,
            "next_gate": preflight.get("next_gate") if preflight else None,
            "write_authority": bool(preflight.get("write_authority", False)) if preflight else False,
            "destructive_action_allowed": bool(preflight.get("destructive_action_allowed", False)) if preflight else False,
            "destructive_action_performed": bool(preflight.get("destructive_action_performed", False)) if preflight else False,
            "eligible_count": preflight.get("eligible_count") if preflight else None,
            "usb_candidate": _optional_candidate(preflight) if preflight else None,
        },
        "preexecution_recovery": {
            "terminal_receipt_present": bool(preexecution.get("terminal_receipt_present", False)),
            "manual_handoff_released": bool(preexecution.get("manual_handoff_released", False)),
            "remote_repair": preexecution.get("remote_repair"),
            "terminal_reason": preexecution.get("terminal_reason"),
            "observed_at": preexecution.get("observed_at"),
        },
    }

    if evidence["physical_preflight"]["destructive_action_performed"]:
        # A preflight record is not itself sufficient proof of a successful flash.
        # Keep the projection factual and do not infer READY_TO_BOOT/physical proof.
        pass

    terminal = evidence["preexecution_recovery"]
    preflight_state = evidence["physical_preflight"]["state"] or "missing"
    summary = (
        f"Aurum Tiny Seed canonical release is {release_state} from source {source_commit} "
        f"with x86 SHA-256 {x86_sha256}. Physical preflight is {preflight_state}; "
        f"preflight_matches_current_release={str(preflight_matches_release).lower()}, "
        f"terminal_recovery_receipt={str(terminal['terminal_receipt_present']).lower()}, "
        f"terminal_reason={terminal['terminal_reason'] or 'none'}, "
        f"manual_handoff_released={str(terminal['manual_handoff_released']).lower()}, "
        f"eligible_usb_count={evidence['physical_preflight']['eligible_count']}, "
        f"write_authority={str(evidence['physical_preflight']['write_authority']).lower()}, "
        f"destructive_action_performed={str(evidence['physical_preflight']['destructive_action_performed']).lower()}, "
        f"next_gate={evidence['physical_preflight']['next_gate'] or 'none'}. "
        "Canonical evidence may prepare a branch but never grants destructive authority or physical proof."
    )

    branch_path = root / BRANCH_RELATIVE
    branch = _read_json(branch_path)
    before = {
        "canonical_evidence": branch.get("canonical_evidence"),
        "current_program": branch.get("current_program"),
    }
    after = {
        "canonical_evidence": evidence,
        "current_program": summary,
    }
    changed = before != after
    if changed:
        branch["canonical_evidence"] = evidence
        branch["current_program"] = summary
        branch_path.write_text(json.dumps(branch, indent=2, sort_keys=False) + "\n", encoding="utf-8")

    return {
        "changed": changed,
        "source_commit": source_commit,
        "release_state": release_state,
        "preflight_state": preflight_state,
        "preflight_matches_release": preflight_matches_release,
        "before": before,
        "after": after,
    }


def main() -> int:
    try:
        result = sync_future_branch_evidence()
    except FutureBranchEvidenceError as exc:
        print(f"AURUM_FUTURE_BRANCH_EVIDENCE_SYNC_REFUSED reason={exc}", file=sys.stderr)
        return 1
    print(
        "AURUM_FUTURE_BRANCH_EVIDENCE_SYNC "
        f"changed={str(result['changed']).lower()} "
        f"source_commit={result['source_commit']} "
        f"release_state={result['release_state']} "
        f"preflight_state={result['preflight_state']} "
        f"preflight_matches_release={str(result['preflight_matches_release']).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
