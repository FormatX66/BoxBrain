"""Synchronize Aurum Future Branch evidence from canonical release/preflight truth.

This helper projects only already-proven evidence. It never grants write authority,
changes recovery state, promotes a candidate, or infers physical proof. Operational
Future Branch prescriptions are projected from the same evidence so stale release,
flash-receipt, or boundary text cannot survive beside a newer canonical state.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HANDOFF_RELATIVE = Path("Projects/Aurum/Release/latest-tinyseed-handoff.json")
PREFLIGHT_RELATIVE = Path("Projects/Aurum/Recovery/latest-tinyseed-physical-preflight.json")
FLASH_RECEIPT_RELATIVE = Path("Projects/Aurum/Recovery/latest-tinyseed-flash-receipt.json")
BRANCH_RELATIVE = Path("Projects/Aurum/future-branches.json")
HANDOFF_SCHEMA = "aurum-tinyseed-handoff-v1"
FLASH_RECEIPT_SCHEMA = "aurum-tinyseed-flash-request-receipt-v1"
READY_PREFLIGHT = "READY_FOR_GUARDED_FLASH_PREFLIGHT"
WAIT_RECOVERY = "WAIT_HOPPER_PREEXECUTION_RECOVERY"
WAIT_USB_MEDIA = "WAIT_USB_MEDIA"
READY_TO_BOOT = "READY_TO_BOOT"


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


def _optional_flash_device(receipt: dict) -> dict | None:
    device = receipt.get("device")
    if device is None:
        return None
    if not isinstance(device, dict):
        raise FutureBranchEvidenceError("flash receipt device must be an object or null")
    return {
        "disk_number": device.get("disk_number"),
        "model": device.get("model"),
        "size_bytes": device.get("size_bytes"),
        "serial_sha256": device.get("serial_sha256"),
    }


def _update_input_family(branch: dict, family: str, **values: object) -> None:
    entries = branch.get("likely_user_inputs")
    if entries is None:
        return
    if not isinstance(entries, list):
        raise FutureBranchEvidenceError("likely_user_inputs must be an array")
    for entry in entries:
        if isinstance(entry, dict) and entry.get("input_family") == family:
            entry.update(values)
            return


def _normalize_input_ranks(entries: list[dict]) -> None:
    for rank, entry in enumerate(entries, start=1):
        entry["rank"] = rank


def _upsert_input_family(
    branch: dict,
    family: str,
    *,
    promote: bool = False,
    **values: object,
) -> None:
    entries = branch.get("likely_user_inputs")
    if entries is None:
        entries = []
        branch["likely_user_inputs"] = entries
    if not isinstance(entries, list):
        raise FutureBranchEvidenceError("likely_user_inputs must be an array")
    if any(not isinstance(entry, dict) for entry in entries):
        raise FutureBranchEvidenceError("likely_user_inputs entries must be objects")

    target = next((entry for entry in entries if entry.get("input_family") == family), None)
    if target is None:
        target = {"input_family": family}
        entries.append(target)
    target.update(values)
    if promote:
        entries.remove(target)
        entries.insert(0, target)
    _normalize_input_ranks(entries)


def _remove_input_family(branch: dict, family: str) -> None:
    entries = branch.get("likely_user_inputs")
    if entries is None:
        return
    if not isinstance(entries, list):
        raise FutureBranchEvidenceError("likely_user_inputs must be an array")
    if any(not isinstance(entry, dict) for entry in entries):
        raise FutureBranchEvidenceError("likely_user_inputs entries must be objects")
    filtered = [entry for entry in entries if entry.get("input_family") != family]
    if len(filtered) != len(entries):
        branch["likely_user_inputs"] = filtered
        _normalize_input_ranks(filtered)


def _promote_existing_input_family(branch: dict, family: str) -> None:
    entries = branch.get("likely_user_inputs")
    if entries is None:
        return
    if not isinstance(entries, list):
        raise FutureBranchEvidenceError("likely_user_inputs must be an array")
    if any(not isinstance(entry, dict) for entry in entries):
        raise FutureBranchEvidenceError("likely_user_inputs entries must be objects")
    target = next((entry for entry in entries if entry.get("input_family") == family), None)
    if target is None:
        return
    entries.remove(target)
    entries.insert(0, target)
    _normalize_input_ranks(entries)


def _update_top_machine_outcome(branch: dict, **values: object) -> None:
    entries = branch.get("likely_machine_outcomes")
    if entries is None:
        return
    if not isinstance(entries, list):
        raise FutureBranchEvidenceError("likely_machine_outcomes must be an array")
    ranked = [entry for entry in entries if isinstance(entry, dict)]
    if not ranked:
        return
    top = min(ranked, key=lambda entry: int(entry.get("rank", 10**9)))
    top.update(values)


def _project_live_prescriptions(branch: dict, evidence: dict, summary: str) -> dict:
    """Keep action-bearing branch text bound to the current proven evidence.

    Historical resolved outcomes are intentionally left untouched. Only live
    prescriptions are rewritten, because those are the fields that can cause a
    stale action to be treated as current.
    """

    release = evidence["release"]
    physical = evidence["physical_preflight"]
    recovery = evidence["preexecution_recovery"]
    flash = evidence["flash_receipt"]
    source = release["source_commit"]
    state = physical["state"] or "missing"
    next_gate = physical["next_gate"] or "none"
    eligible_count = physical["eligible_count"]
    candidate = physical["usb_candidate"]

    current_release_flash_ready_to_boot = bool(
        flash["present"]
        and flash["matches_current_release"]
        and flash["state"] == READY_TO_BOOT
        and flash["raw_readback_verified"]
    )

    waiting_for_usb_media = bool(
        release["state"] == "READY_TO_FLASH"
        and physical["matches_current_release"]
        and state == WAIT_USB_MEDIA
        and not current_release_flash_ready_to_boot
    )

    flash_authorization_eligible = bool(
        release["state"] == "READY_TO_FLASH"
        and physical["matches_current_release"]
        and state == READY_PREFLIGHT
        and recovery["terminal_receipt_present"]
        and recovery["manual_handoff_released"]
        and eligible_count == 1
        and isinstance(candidate, dict)
        and not physical["write_authority"]
        and not physical["destructive_action_allowed"]
        and not physical["destructive_action_performed"]
        and not current_release_flash_ready_to_boot
    )

    live = {
        "release_source_commit": source,
        "release_state": release["state"],
        "preflight_state": state,
        "next_gate": next_gate,
        "preflight_matches_current_release": physical["matches_current_release"],
        "eligible_usb_count": eligible_count,
        "terminal_recovery_receipt": recovery["terminal_receipt_present"],
        "manual_handoff_released": recovery["manual_handoff_released"],
        "flash_receipt_present": flash["present"],
        "flash_receipt_matches_current_release": flash["matches_current_release"],
        "current_release_flash_ready_to_boot": current_release_flash_ready_to_boot,
        "waiting_for_usb_media": waiting_for_usb_media,
        "flash_authorization_eligible": flash_authorization_eligible,
        "write_authority": False,
        "destructive_action_allowed": False,
    }

    if current_release_flash_ready_to_boot:
        authorization_response = (
            f"Do not request another flash by default. Canonical Tiny Seed release {source} "
            "already has a matching readback-verified READY_TO_BOOT flash receipt. "
            "That receipt proves the media write only; physical boot proof is still separate."
        )
        authorization_action = (
            "Keep new write authority false. Re-read the matching flash receipt and proceed "
            "to physical boot/boot-proof collection. Reflash only if later evidence invalidates "
            "the media or the operator explicitly starts a new bounded flash cycle."
        )
        top_state = "current-release-flash-readback-proven-awaiting-physical-boot"
        top_prepared = [
            "current release provenance",
            "matching flash receipt",
            "full raw readback proof",
            "Tiny Seed ready marker collection",
            "boot-proof receipt",
            "LKG-preserving repair/reseed continuation",
        ]
        top_next = (
            "boot the proven current-release media on the physical x86 target and collect "
            "formal Tiny Seed ready/boot-proof evidence without inferring success from the flash receipt"
        )
    elif flash_authorization_eligible:
        authorization_response = (
            f"Canonical Tiny Seed release {source} is READY_TO_FLASH and the current "
            "preflight is READY_FOR_GUARDED_FLASH_PREFLIGHT with one current-release "
            "USB candidate and terminal recovery evidence. Fresh one-shot authority "
            "may be bound only to this exact release and live-reproved device."
        )
        authorization_action = (
            "On fresh explicit one-shot authority, re-read canonical release and "
            "protected-media state, re-enumerate the USB live, require the same "
            "physical identity/provenance, verify the artifact checksum, run guarded "
            "dry-run/preflight, and only then permit the bounded write plus full raw "
            "readback."
        )
        top_state = "fresh-authority-triggers-live-reproof-and-guarded-preflight"
        top_prepared = [
            "canonical READY_TO_FLASH source/hash",
            "current USB candidate identity",
            "protected-media registry",
            "artifact checksum",
            "guarded dry-run",
            "live USB identity re-enumeration",
            "system/boot-disk refusal",
        ]
        top_next = (
            "write only if every live proof still matches the one-shot authority; "
            "otherwise fail closed and return to read-only discovery"
        )
    else:
        authorization_response = (
            f"Do not treat flash authorization as executable yet. Canonical Tiny Seed "
            f"release {source} is {release['state']}, but physical preflight is {state}; "
            f"the current next gate is {next_gate}. Write authority remains false."
        )
        authorization_action = (
            f"Keep write authority false and resolve {next_gate} using only read-only "
            "or already-authorized recovery paths. Reproject canonical preflight, and "
            "accept a fresh one-shot destructive authorization only after the state "
            "again proves READY_FOR_GUARDED_FLASH_PREFLIGHT for the same live release/device."
        )
        if state == WAIT_RECOVERY:
            top_state = "fresh-terminal-hopper-preexecution-recovery-resolves"
            top_prepared = [
                "canonical READY_TO_FLASH source/hash",
                "current release-bound USB evidence",
                "existing-authority recovery probe",
                "terminal v2 recovery receipt",
                "zero-authority preflight projector",
            ]
            top_next = (
                "project the fresh terminal recovery result; if manual handoff is released, "
                "advance to guarded-flash preflight, otherwise preserve the blocker without "
                "granting new authority"
            )
        elif not physical["matches_current_release"]:
            top_state = "refresh-current-release-physical-evidence"
            top_prepared = [
                "canonical release identity",
                "zero-authority USB rediscovery",
                "stale-provenance invalidation",
                "preflight projector",
            ]
            top_next = "rebuild current-release evidence before any destructive authority is accepted"
        else:
            top_state = "resolve-current-preflight-blocker"
            top_prepared = [
                "canonical release identity",
                "current physical preflight evidence",
                "zero-authority continuation",
            ]
            top_next = f"resolve {next_gate} and reproject the physical boundary"

    _update_input_family(
        branch,
        "explicit-guarded-flash-authorization",
        prepared_response=authorization_response,
        action_if_safe=authorization_action,
    )
    _update_input_family(
        branch,
        "status-or-so",
        prepared_response=summary,
        action_if_safe=(
            "Re-read canonical handoff, physical preflight, current USB evidence, "
            "recovery receipt, authorization freshness, and flash-receipt provenance before "
            "reporting; advance only safe zero-authority work until the proven next gate changes."
        ),
    )
    _update_input_family(
        branch,
        "generic-prompt-intent-expansion",
        prepared_response=(
            f"Treat a generic continuation prompt against the live canonical state: "
            f"preflight={state}, next_gate={next_gate}, "
            f"current_release_flash_ready_to_boot={str(current_release_flash_ready_to_boot).lower()}. "
            "Do all shared safe reversible work, but never infer destructive disk-write authority "
            "or physical boot proof."
        ),
        action_if_safe=(
            (
                "Advance to physical boot-proof collection from the matching readback-verified "
                "current-release flash receipt, without granting a new write."
            )
            if current_release_flash_ready_to_boot
            else (
                f"Advance the safe prefix through {next_gate}, refresh canonical evidence, "
                "and stop before any boundary that requires explicit new authority."
            )
        ),
    )

    if waiting_for_usb_media:
        _upsert_input_family(
            branch,
            "physical-media-present",
            promote=True,
            examples=[
                "USB is plugged in",
                "I plugged in the spare USB",
                "the test USB is connected",
            ],
            prepared_response=(
                f"Treat newly present removable media as evidence only for Tiny Seed release {source}. "
                "Re-read the canonical release and collect fresh release-bound USB identity, system/boot-disk, "
                "read-only, and protected-media evidence with zero write authority."
            ),
            action_if_safe=(
                "Run or consume fresh release-bound read-only USB discovery, require one uniquely eligible "
                "non-system/non-boot/non-protected device, resynchronize canonical preflight, and stop at the "
                "explicit guarded-flash authorization boundary. Never infer write authority from media presence."
            ),
        )
    else:
        _remove_input_family(branch, "physical-media-present")
        if current_release_flash_ready_to_boot:
            _promote_existing_input_family(branch, "physical-result-success")
        elif flash_authorization_eligible:
            _promote_existing_input_family(branch, "explicit-guarded-flash-authorization")

    _update_top_machine_outcome(
        branch,
        state=top_state,
        prepared=top_prepared,
        next=top_next,
    )
    return live


def sync_future_branch_evidence(root: Path = ROOT) -> dict:
    """Project canonical handoff, preflight, and flash receipt evidence into Future Branch."""

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

    flash_path = root / FLASH_RECEIPT_RELATIVE
    flash = _read_json(flash_path) if flash_path.is_file() else {}
    if flash and flash.get("schema") != FLASH_RECEIPT_SCHEMA:
        raise FutureBranchEvidenceError("unexpected Tiny Seed flash receipt schema")
    flash_source = _required_text(flash.get("source_commit"), "flash receipt source_commit") if flash else None
    flash_matches_release = flash_source == source_commit if flash else False

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
        "flash_receipt": {
            "present": bool(flash),
            "matches_current_release": flash_matches_release,
            "source_commit": flash_source,
            "state": flash.get("state") if flash else None,
            "image_sha256": flash.get("image_sha256") if flash else None,
            "raw_readback_verified": bool(flash.get("raw_readback_verified", False)) if flash else False,
            "write_authority_consumed": bool(flash.get("write_authority_consumed", False)) if flash else False,
            "observed_at_utc": flash.get("observed_at_utc") if flash else None,
            "device": _optional_flash_device(flash) if flash else None,
        },
    }

    terminal = evidence["preexecution_recovery"]
    flash_evidence = evidence["flash_receipt"]
    preflight_state = evidence["physical_preflight"]["state"] or "missing"
    summary = (
        f"Aurum Tiny Seed canonical release is {release_state} from source {source_commit} "
        f"with x86 SHA-256 {x86_sha256}. Physical preflight is {preflight_state}; "
        f"preflight_matches_current_release={str(preflight_matches_release).lower()}, "
        f"terminal_recovery_receipt={str(terminal['terminal_receipt_present']).lower()}, "
        f"terminal_reason={terminal['terminal_reason'] or 'none'}, "
        f"manual_handoff_released={str(terminal['manual_handoff_released']).lower()}, "
        f"eligible_usb_count={evidence['physical_preflight']['eligible_count']}, "
        f"flash_receipt_present={str(flash_evidence['present']).lower()}, "
        f"flash_receipt_matches_current_release={str(flash_evidence['matches_current_release']).lower()}, "
        f"flash_receipt_state={flash_evidence['state'] or 'none'}, "
        f"raw_readback_verified={str(flash_evidence['raw_readback_verified']).lower()}, "
        f"write_authority={str(evidence['physical_preflight']['write_authority']).lower()}, "
        f"destructive_action_performed={str(evidence['physical_preflight']['destructive_action_performed']).lower()}, "
        f"next_gate={evidence['physical_preflight']['next_gate'] or 'none'}. "
        "Canonical evidence may prepare a branch but never grants destructive authority or physical proof."
    )

    branch_path = root / BRANCH_RELATIVE
    branch = _read_json(branch_path)
    projected = copy.deepcopy(branch)
    projected["canonical_evidence"] = evidence
    projected["current_program"] = summary
    projected["live_controls"] = _project_live_prescriptions(projected, evidence, summary)

    changed = branch != projected
    if changed:
        branch_path.write_text(
            json.dumps(projected, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )

    return {
        "changed": changed,
        "source_commit": source_commit,
        "release_state": release_state,
        "preflight_state": preflight_state,
        "preflight_matches_release": preflight_matches_release,
        "flash_receipt_matches_release": flash_matches_release,
        "before": {
            "canonical_evidence": branch.get("canonical_evidence"),
            "current_program": branch.get("current_program"),
            "live_controls": branch.get("live_controls"),
        },
        "after": {
            "canonical_evidence": projected.get("canonical_evidence"),
            "current_program": projected.get("current_program"),
            "live_controls": projected.get("live_controls"),
        },
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
        f"preflight_matches_release={str(result['preflight_matches_release']).lower()} "
        f"flash_receipt_matches_release={str(result['flash_receipt_matches_release']).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
