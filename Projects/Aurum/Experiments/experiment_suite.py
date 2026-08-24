"""Executable experimental harnesses for Aurum machine-state and kernel-policy research.

These are deliberately non-production experiments. They model state capture, candidate
selection, evidence, and recovery-control invariants without mutating a host kernel.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


STATEWEAVE_SCHEMA = "aurum-stateweave-v0"
KERNEL_PLAN_SCHEMA = "aurum-adaptive-kernel-plan-v0"
COMBINED_SCHEMA = "aurum-stateweave-kernel-trial-v0"
RECOVERY_REQUEST_SCHEMA = "aurum-recovery-request-v0"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def stateweave_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    """Create a deterministic snapshot with a content digest."""
    payload = json.loads(_canonical_json(state).decode("utf-8"))
    digest = hashlib.sha256(_canonical_json(payload)).hexdigest()
    return {"schema": STATEWEAVE_SCHEMA, "digest": f"sha256:{digest}", "state": payload}


def stateweave_restore(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Verify and restore a StateWeave snapshot, refusing tampered state."""
    if snapshot.get("schema") != STATEWEAVE_SCHEMA:
        raise ValueError("unknown StateWeave schema")
    state = snapshot.get("state")
    if not isinstance(state, dict):
        raise ValueError("StateWeave state must be an object")
    expected = stateweave_snapshot(state)["digest"]
    if snapshot.get("digest") != expected:
        raise ValueError("StateWeave digest mismatch")
    return json.loads(_canonical_json(state).decode("utf-8"))


def adaptive_kernel_plan(
    hardware: dict[str, Any],
    *,
    active_profile: str,
    lkg_profile: str,
) -> dict[str, Any]:
    """Build a bounded candidate plan without changing the active/LKG profiles."""
    arch = str(hardware.get("arch", "unknown")).lower()
    cores = int(hardware.get("cores", 1))
    ram_mb = int(hardware.get("ram_mb", 0))
    devices = sorted(str(item) for item in hardware.get("devices", []))

    if arch in {"x86_64", "amd64"}:
        family = "x86_64"
    elif arch in {"aarch64", "arm64"}:
        family = "arm64"
    else:
        family = "unsupported"

    if family == "unsupported" or ram_mb < 256:
        action = "hold"
        candidate = None
        reason = "unsupported-or-insufficient-hardware"
    else:
        action = "stage-candidate"
        density = "small" if ram_mb < 2048 or cores <= 2 else "balanced"
        candidate = f"{family}-{density}"
        reason = "bounded-hardware-fit"

    return {
        "schema": KERNEL_PLAN_SCHEMA,
        "action": action,
        "candidate": candidate,
        "reason": reason,
        "evidence": {"arch": arch, "cores": cores, "ram_mb": ram_mb, "devices": devices},
        "active_profile": active_profile,
        "lkg_profile": lkg_profile,
        "promotion_allowed": False,
    }


def combined_trial(
    hardware: dict[str, Any],
    machine_state: dict[str, Any],
    *,
    active_profile: str,
    lkg_profile: str,
) -> dict[str, Any]:
    """Bind a pre-change StateWeave receipt to an adaptive-kernel candidate plan."""
    before = stateweave_snapshot(machine_state)
    plan = adaptive_kernel_plan(hardware, active_profile=active_profile, lkg_profile=lkg_profile)
    return {
        "schema": COMBINED_SCHEMA,
        "before": before,
        "kernel_plan": plan,
        "rollback_target": lkg_profile,
        "promotion_allowed": False,
    }


def validate_recovery_request(
    request: dict[str, Any],
    *,
    signature_verified: bool,
    trusted_refs: set[str],
) -> dict[str, Any]:
    """Validate the non-cryptographic recovery contract after signature verification.

    Cryptographic verification is intentionally external to this experiment. This function
    fails closed unless a caller has already established signature_verified=True.
    """
    if request.get("schema") != RECOVERY_REQUEST_SCHEMA:
        raise ValueError("unknown recovery request schema")
    if not signature_verified:
        raise PermissionError("recovery request signature not verified")

    target = request.get("target")
    if target not in {"previous", "last-known-good", "specific"}:
        raise ValueError("unsupported recovery target")

    ref = request.get("ref")
    if target == "specific":
        if not isinstance(ref, str) or ref not in trusted_refs:
            raise PermissionError("specific recovery ref is not trusted")
    elif ref is not None:
        raise ValueError("ref is only valid with target=specific")

    return {
        "schema": RECOVERY_REQUEST_SCHEMA,
        "accepted": True,
        "target": target,
        "ref": ref,
        "preserve_lkg": True,
        "promotion_allowed": False,
    }
