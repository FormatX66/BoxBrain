"""Post-flash Tiny Seed state projection helpers.

A release artifact can remain READY_TO_FLASH after matching physical media has
already been written and full-readback verified. This module prevents downstream
read-only recovery/preflight refreshes from regressing that physical truth back to
a pre-flash authorization state. It is side-effect free and never grants authority
or infers physical boot/rollback proof.
"""
from __future__ import annotations

from typing import Any, Mapping
import re


RELEASE_SCHEMA = "aurum-tinyseed-handoff-v1"
FLASH_RECEIPT_SCHEMA = "aurum-tinyseed-flash-request-receipt-v1"
READY_RELEASE_STATE = "READY_TO_FLASH"
READY_MEDIA_STATE = "READY_TO_BOOT"
PREFLIGHT_SCHEMA = "aurum-tinyseed-physical-preflight-v2"


TRANSIENT_RECOVERY_FIELDS = {"observed_at", "runner_host"}


def matching_ready_to_boot(
    release: Mapping[str, Any] | None,
    flash_receipt: Mapping[str, Any] | None,
) -> bool:
    """Return true only for a provenance-matching, raw-readback-verified receipt."""
    if not isinstance(release, Mapping) or not isinstance(flash_receipt, Mapping):
        return False
    x86 = (release.get("artifacts") or {}).get("x86") or {}
    release_source = str(release.get("source_commit") or "").lower()
    release_image = str(x86.get("sha256") or "").lower()
    receipt_source = str(flash_receipt.get("source_commit") or "").lower()
    receipt_image = str(flash_receipt.get("image_sha256") or "").lower()
    return bool(
        str(release.get("schema") or "") == RELEASE_SCHEMA
        and str(release.get("state") or "") == READY_RELEASE_STATE
        and re.fullmatch(r"[0-9a-f]{40}", release_source)
        and re.fullmatch(r"[0-9a-f]{64}", release_image)
        and str(flash_receipt.get("schema") or "") == FLASH_RECEIPT_SCHEMA
        and str(flash_receipt.get("state") or "") == READY_MEDIA_STATE
        and receipt_source == release_source
        and receipt_image == release_image
        and bool(flash_receipt.get("raw_readback_verified"))
        and bool(flash_receipt.get("write_authority_consumed"))
    )


def semantic_recovery_view(receipt: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Remove timestamp/runner noise while retaining every operational observation."""
    if not isinstance(receipt, Mapping):
        return None
    return {
        str(key): value
        for key, value in receipt.items()
        if str(key) not in TRANSIENT_RECOVERY_FIELDS
    }


def recovery_materially_changed(
    previous: Mapping[str, Any] | None,
    current: Mapping[str, Any] | None,
) -> bool:
    """Timestamp-only terminal re-observation is not new post-flash information."""
    return semantic_recovery_view(previous) != semantic_recovery_view(current)


def project_post_flash_state(
    release: Mapping[str, Any],
    flash_receipt: Mapping[str, Any],
    recovery: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project current physical media truth without inferring boot or authority."""
    if not matching_ready_to_boot(release, flash_receipt):
        raise ValueError("flash receipt does not prove current-release READY_TO_BOOT media")
    x86 = (release.get("artifacts") or {}).get("x86") or {}
    device = flash_receipt.get("device") if isinstance(flash_receipt.get("device"), Mapping) else None
    payload = {
        "schema": PREFLIGHT_SCHEMA,
        "state": READY_MEDIA_STATE,
        "preflight_state": READY_MEDIA_STATE,
        "next_gate": "physical-hopper-boot-proof",
        "release_state": release.get("state"),
        "release_source_commit": release.get("source_commit"),
        "x86_artifact": x86.get("name"),
        "x86_sha256": x86.get("sha256"),
        "release": {
            "state": release.get("state"),
            "source_commit": release.get("source_commit"),
            "x86_artifact": x86.get("name"),
            "x86_sha256": x86.get("sha256"),
        },
        "flash_receipt": {
            "state": flash_receipt.get("state"),
            "request_id": flash_receipt.get("request_id"),
            "source_commit": flash_receipt.get("source_commit"),
            "image_sha256": flash_receipt.get("image_sha256"),
            "raw_readback_verified": True,
            "write_authority_consumed": True,
            "observed_at_utc": flash_receipt.get("observed_at_utc"),
            "device": dict(device) if device is not None else None,
        },
        "write_authority": False,
        "destructive_action_allowed": False,
        "destructive_action_performed": False,
        "physical_flash_proven": True,
        "physical_boot_proven": False,
        "guardian_forced_rollback_proven": False,
        "invariants": {
            "preserve_hopper_existing_recovery_media": True,
            "no_reflash_without_new_invalidating_evidence": True,
            "physical_boot_proof_required_after_flash": True,
            "guardian_forced_rollback_proof_required": True,
        },
    }
    if recovery is not None:
        payload["preexecution_recovery"] = {
            "schema": recovery.get("schema"),
            "remote_repair": recovery.get("remote_repair"),
            "terminal_reason": recovery.get("terminal_reason"),
            "observed_at": recovery.get("observed_at"),
            "read_only_probe": recovery.get("read_only_probe"),
        }
    return payload
