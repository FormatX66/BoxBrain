"""Side-effect-free Tiny Seed physical handoff preflight.

Consumes canonical release truth plus optional privacy-safe USB discovery and
one-shot flash-authorization receipts, then collapses them into the next bounded
handoff state. It never selects a raw disk by itself, never grants write authority,
and never permits a destructive action. Live disk identity must still be re-proven
by the guarded flasher immediately before any authorized write.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping


READY_RELEASE_STATE = "READY_TO_FLASH"
HANDOFF_SCHEMA = "aurum-tinyseed-handoff-v1"
AUTHORIZED_REQUEST_STATE = "AUTHORIZED_ONCE"
AUTHORIZED_CONFIRMATION = "FLASH_TINY_SEED_TEST_USB"
DISCOVERY_SCHEMA = "aurum-read-only-usb-discovery-v1"
PREFLIGHT_SCHEMA = "aurum-tinyseed-physical-preflight-v2"
PREEXECUTION_SCHEMA = "aurum.hopper.recovery-path-probe.v2"
PREEXECUTION_TERMINAL_REASONS = {
    "boxbrain-unreachable",
    "authorized-recovery-unavailable",
    "remote-repair-failed",
}
REQUIRED_RELEASE_GATES = {
    "x86_build",
    "x86_uefi_boot_smoke",
    "x86_bios_boot_smoke",
    "x86_boot_proof_marker",
    "published_artifacts",
    "combined_hash_reverification",
}


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def evaluate_flash_authorization(
    release: Mapping[str, Any],
    discovery: Mapping[str, Any] | None,
    request: Mapping[str, Any] | None,
    *,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Describe one-shot authorization freshness without granting write authority."""

    base = {
        "authorization_state": "NONE",
        "request_id": None,
        "request_write_authority": False,
        "destructive_action_allowed": False,
    }
    if request is None:
        return base

    request_id = request.get("request_id")
    common = {**base, "request_id": request_id}
    if str(request.get("schema") or "") != "aurum-tinyseed-flash-request-v1":
        return {**common, "authorization_state": "REFUSE_SCHEMA"}
    if str(request.get("state") or "") != AUTHORIZED_REQUEST_STATE or not bool(request.get("write_authority")):
        return {**common, "authorization_state": "INACTIVE"}
    if str(request.get("confirmation") or "") != AUTHORIZED_CONFIRMATION:
        return {**common, "authorization_state": "REFUSE_CONFIRMATION"}

    expires_raw = str(request.get("expires_at_utc") or "")
    try:
        expires = _parse_utc(expires_raw)
    except (TypeError, ValueError):
        return {**common, "authorization_state": "REFUSE_EXPIRY"}
    now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if now > expires:
        return {
            **common,
            "authorization_state": "EXPIRED",
            "expires_at_utc": expires.isoformat(),
        }

    if discovery is None:
        return {**common, "authorization_state": "WAIT_DISCOVERY"}

    x86 = (release.get("artifacts") or {}).get("x86") or {}
    release_sha = str(release.get("source_commit") or "").lower()
    image_sha = str(x86.get("sha256") or "").lower()
    request_seed = str(request.get("seed_sha") or "").lower()
    request_image = str(request.get("image_sha256") or "").lower()
    discovery_id = str(discovery.get("request_id") or "")
    request_discovery_id = str(request.get("discovery_request_id") or "")

    if request_seed != release_sha or request_image != image_sha or request_discovery_id != discovery_id:
        return {**common, "authorization_state": "REFUSE_PROVENANCE_MISMATCH"}

    return {
        **common,
        "authorization_state": "VALID_ONE_SHOT_PENDING_LIVE_REPROOF",
        "request_write_authority": True,
        "expires_at_utc": expires.isoformat(),
        "destructive_action_allowed": False,
    }


def evaluate_physical_preflight(
    release: Mapping[str, Any],
    discovery: Mapping[str, Any] | None,
    flash_request: Mapping[str, Any] | None = None,
    preexecution_recovery: Mapping[str, Any] | None = None,
    *,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    state = str(release.get("state") or "")
    gates = release.get("gates") or {}
    x86 = (release.get("artifacts") or {}).get("x86") or {}

    authorization = evaluate_flash_authorization(
        release,
        discovery,
        flash_request,
        now_utc=now_utc,
    )

    release_receipt = {
        "state": state,
        "source_commit": release.get("source_commit"),
        "x86_artifact": x86.get("name"),
        "x86_sha256": x86.get("sha256"),
    }
    base = {
        "schema": PREFLIGHT_SCHEMA,
        "release_state": state,
        "release_source_commit": release.get("source_commit"),
        "x86_artifact": x86.get("name"),
        "x86_sha256": x86.get("sha256"),
        "release": release_receipt,
        "write_authority": False,
        "destructive_action_allowed": False,
        "destructive_action_performed": False,
        "authorization": authorization,
        "physical_boot_proven": gates.get("physical_boot") == "passed",
        "guardian_forced_rollback_proven": gates.get("guardian_forced_rollback") == "passed",
        "invariants": {
            "preserve_hopper_existing_recovery_media": True,
            "reprove_raw_usb_identity_before_write": True,
            "full_raw_readback_required_after_write": True,
            "physical_boot_proof_required_after_flash": True,
            "guardian_forced_rollback_proof_required": True,
            "preexecution_toolside_recovery_before_manual_handoff": True,
        },
    }

    def finish(preflight_state: str, **extra: Any) -> dict[str, Any]:
        # ``state`` is retained as an explicit compatibility field for the
        # guarded Windows flasher. It must always equal the canonical v2 name.
        return {
            **base,
            **extra,
            "state": preflight_state,
            "preflight_state": preflight_state,
            "next_gate": {
                "READY_FOR_GUARDED_FLASH_PREFLIGHT": "explicit-guarded-flash-authorization",
                "AUTHORIZED_ONE_SHOT_PENDING_LIVE_REPROOF": "live-usb-identity-and-recovery-reproof",
                "WAIT_HOPPER_HEALTH_REREAD": "fresh-hopper-health-evidence",
                "WAIT_HOPPER_PREEXECUTION_RECOVERY": "fresh-terminal-hopper-preexecution-recovery-receipt",
                "WAIT_USB_SELECTION": "explicit-nondestructive-usb-selection",
                "WAIT_USB_MEDIA": "eligible-test-usb-presence",
                "WAIT_USB_DISCOVERY": "fresh-current-release-read-only-usb-discovery",
                "WAIT_RELEASE": "verified-ready-to-flash-release",
                "REFUSE_DISCOVERY_RELEASE": "fresh-current-release-read-only-usb-discovery",
                "REFUSE_DISCOVERY_SCHEMA": "fresh-current-release-read-only-usb-discovery",
                "REFUSE_DISCOVERY_AUTHORITY": "fresh-current-release-read-only-usb-discovery",
                "REFUSE_DISCOVERY_CONTRADICTION": "fresh-current-release-read-only-usb-discovery",
            }.get(preflight_state, "resolve-preflight-refusal"),
        }

    release_source = str(release.get("source_commit") or "").lower()
    image_sha256 = str(x86.get("sha256") or "").lower()
    release_is_verified = (
        str(release.get("schema") or "") == HANDOFF_SCHEMA
        and state == READY_RELEASE_STATE
        and re.fullmatch(r"[0-9a-f]{40}", release_source) is not None
        and str(x86.get("name") or "") == "Aurum-TinySeed-amd64.iso"
        and re.fullmatch(r"[0-9a-f]{64}", image_sha256) is not None
        and all(gates.get(name) == "passed" for name in REQUIRED_RELEASE_GATES)
    )
    if not release_is_verified:
        return finish("WAIT_RELEASE", eligible_count=0)

    if discovery is None:
        return finish("WAIT_USB_DISCOVERY", eligible_count=0)

    if str(discovery.get("schema") or "") != DISCOVERY_SCHEMA:
        return finish("REFUSE_DISCOVERY_SCHEMA", eligible_count=0)

    if bool(discovery.get("write_authority")):
        return finish("REFUSE_DISCOVERY_AUTHORITY", eligible_count=0)

    discovery_release_source = str(discovery.get("release_source_commit") or "").lower()
    if not bool(discovery.get("release_request_match")) or discovery_release_source != release_source:
        return finish("REFUSE_DISCOVERY_RELEASE", eligible_count=0)

    devices = discovery.get("devices")
    if not isinstance(devices, list):
        return finish("REFUSE_DISCOVERY_CONTRADICTION", eligible_count=0)

    eligible_devices = [
        device
        for device in devices
        if isinstance(device, Mapping) and bool(device.get("eligible_for_preflight_only"))
    ]
    reported_count = int(discovery.get("eligible_count") or 0)
    eligible_count = len(eligible_devices)
    selection = str(discovery.get("selection_state") or "")
    expected_selection = (
        "UNIQUE_SAFE_TO_PREFLIGHT_ONLY"
        if eligible_count == 1
        else "AMBIGUOUS_MULTIPLE_ELIGIBLE"
        if eligible_count > 1
        else "NO_ELIGIBLE_USB"
    )
    request_id = str(discovery.get("request_id") or "")
    if reported_count != eligible_count or selection != expected_selection or not request_id:
        return finish(
            "REFUSE_DISCOVERY_CONTRADICTION",
            discovery_request_id=request_id or None,
            discovery_selection_state=selection,
            eligible_count=eligible_count,
        )

    candidate = dict(eligible_devices[0]) if eligible_count == 1 else None
    if candidate is not None:
        serial_sha256 = str(candidate.get("serial_sha256") or "").lower()
        invalid_candidate = (
            not str(candidate.get("model") or "").strip()
            or int(candidate.get("size_bytes") or 0) <= 0
            or re.fullmatch(r"[0-9a-f]{64}", serial_sha256) is None
            or bool(candidate.get("is_boot"))
            or bool(candidate.get("is_system"))
            or bool(candidate.get("is_read_only"))
            or bool(candidate.get("protected"))
        )
        if invalid_candidate:
            return finish(
                "REFUSE_USB_CANDIDATE",
                discovery_request_id=request_id,
                discovery_selection_state=selection,
                eligible_count=eligible_count,
            )

    discovery_receipt = {
        "request_id": request_id,
        "observed_at_utc": discovery.get("observed_at_utc"),
        "release_source_commit": discovery_release_source,
        "release_request_match": True,
        "selection_state": selection,
        "eligible_count": eligible_count,
        "write_authority": False,
        "candidate": candidate,
    }
    common = {
        **base,
        "discovery_request_id": request_id,
        "discovery_selection_state": selection,
        "eligible_count": eligible_count,
        "usb_candidate": candidate,
        "usb_discovery": discovery_receipt,
    }

    if selection == "UNIQUE_SAFE_TO_PREFLIGHT_ONLY" and eligible_count == 1:
        recovery_common = {
            "required_schema": PREEXECUTION_SCHEMA,
            "terminal_receipt_present": preexecution_recovery is not None,
            "remote_repair": None,
            "terminal_reason": None,
            "observed_at": None,
            "manual_handoff_released": False,
            "reason": "terminal Hopper recovery receipt is missing",
        }
        if preexecution_recovery is None:
            return finish(
                "WAIT_HOPPER_PREEXECUTION_RECOVERY",
                preexecution_recovery=recovery_common,
                **common,
            )

        recovery_common.update(
            {
                "remote_repair": preexecution_recovery.get("remote_repair"),
                "terminal_reason": preexecution_recovery.get("terminal_reason"),
                "observed_at": preexecution_recovery.get("observed_at"),
            }
        )
        if str(preexecution_recovery.get("schema") or "") != PREEXECUTION_SCHEMA:
            recovery_common["reason"] = "Hopper recovery receipt schema is invalid"
            return finish(
                "WAIT_HOPPER_PREEXECUTION_RECOVERY",
                preexecution_recovery=recovery_common,
                **common,
            )

        now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        try:
            observed = _parse_utc(str(preexecution_recovery.get("observed_at") or ""))
            age_seconds = (now - observed).total_seconds()
        except (TypeError, ValueError):
            age_seconds = 10**9
        if age_seconds < -300 or age_seconds > 3600:
            recovery_common["reason"] = "Hopper recovery receipt is not fresh"
            return finish(
                "WAIT_HOPPER_PREEXECUTION_RECOVERY",
                preexecution_recovery=recovery_common,
                **common,
            )

        remote_repair = str(preexecution_recovery.get("remote_repair") or "").strip().lower()
        terminal_reason = str(preexecution_recovery.get("terminal_reason") or "").strip().lower()
        if remote_repair == "completed":
            recovery_common["reason"] = "remote repair completed; stale manual flash escalation is suppressed"
            return finish(
                "WAIT_HOPPER_HEALTH_REREAD",
                preexecution_recovery=recovery_common,
                **common,
            )
        if remote_repair not in {"unavailable", "failed"} or terminal_reason not in PREEXECUTION_TERMINAL_REASONS:
            recovery_common["reason"] = "Hopper recovery receipt is not a permitted terminal unrepaired outcome"
            return finish(
                "WAIT_HOPPER_PREEXECUTION_RECOVERY",
                preexecution_recovery=recovery_common,
                **common,
            )

        recovery_common["manual_handoff_released"] = True
        recovery_common["reason"] = (
            "fresh terminal unrepaired Hopper recovery receipt and current release-bound unique USB evidence are present"
        )
        if authorization["authorization_state"] == "VALID_ONE_SHOT_PENDING_LIVE_REPROOF":
            return finish(
                "AUTHORIZED_ONE_SHOT_PENDING_LIVE_REPROOF",
                preexecution_recovery=recovery_common,
                **common,
            )
        if str(authorization["authorization_state"]).startswith("REFUSE_"):
            return finish(
                "REFUSE_FLASH_AUTHORIZATION",
                preexecution_recovery=recovery_common,
                **common,
            )
        return finish(
            "READY_FOR_GUARDED_FLASH_PREFLIGHT",
            preexecution_recovery=recovery_common,
            **common,
        )
    if selection == "AMBIGUOUS_MULTIPLE_ELIGIBLE" or eligible_count > 1:
        return finish("WAIT_USB_SELECTION", **common)
    if selection == "NO_ELIGIBLE_USB" or eligible_count == 0:
        return finish("WAIT_USB_MEDIA", **common)
    return finish("REFUSE_UNRECOGNIZED_DISCOVERY", **common)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--discovery")
    parser.add_argument("--flash-request")
    parser.add_argument("--preexecution-recovery")
    parser.add_argument("--now-utc")
    args = parser.parse_args()

    release = _read_json(Path(args.release))
    discovery_path = Path(args.discovery) if args.discovery else None
    discovery = _read_json(discovery_path) if discovery_path and discovery_path.exists() else None
    request_path = Path(args.flash_request) if args.flash_request else None
    request = _read_json(request_path) if request_path and request_path.exists() else None
    recovery_path = Path(args.preexecution_recovery) if args.preexecution_recovery else None
    recovery = _read_json(recovery_path) if recovery_path and recovery_path.exists() else None
    now = _parse_utc(args.now_utc) if args.now_utc else None
    print(
        json.dumps(
            evaluate_physical_preflight(release, discovery, request, recovery, now_utc=now),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
