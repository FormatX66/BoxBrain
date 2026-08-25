"""Decide whether Tiny Seed USB identity evidence needs refreshing.

This is a zero-authority policy helper. It never authorizes media selection or a
write. Its purpose is to prevent repeated read-only discovery/recovery churn once
canonical evidence already proves that the current x86 release was written and
full raw-readback verified on physical media.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RefreshDecision:
    refresh: bool
    reason: str


def _norm(value: object) -> str:
    return str(value or "").strip().lower()


def decide_usb_refresh(release: dict | None, flash_receipt: dict | None) -> RefreshDecision:
    """Return whether read-only USB discovery should run for the canonical release.

    A matching ``READY_TO_BOOT`` receipt with full raw readback is terminal for the
    flash/discovery phase. Re-running USB discovery at that point adds repository,
    runner, and network churn without improving the next physical boot gate.

    Any release/provenance mismatch keeps refresh enabled so a newer release can
    invalidate older media evidence safely.
    """
    if not isinstance(release, dict):
        return RefreshDecision(False, "canonical-release-missing")
    if release.get("state") != "READY_TO_FLASH":
        return RefreshDecision(False, "canonical-release-not-ready-to-flash")

    source = _norm(release.get("source_commit"))
    x86 = (release.get("artifacts") or {}).get("x86") if isinstance(release.get("artifacts"), dict) else None
    image_sha = _norm((x86 or {}).get("sha256") if isinstance(x86, dict) else None)
    if not source or not image_sha:
        return RefreshDecision(False, "canonical-release-provenance-incomplete")

    if not isinstance(flash_receipt, dict):
        return RefreshDecision(True, "current-release-flash-receipt-missing")

    receipt_matches = (
        flash_receipt.get("schema") == "aurum-tinyseed-flash-request-receipt-v1"
        and flash_receipt.get("state") == "READY_TO_BOOT"
        and flash_receipt.get("raw_readback_verified") is True
        and _norm(flash_receipt.get("source_commit")) == source
        and _norm(flash_receipt.get("image_sha256")) == image_sha
    )
    if receipt_matches:
        return RefreshDecision(False, "current-release-media-already-readback-verified")

    return RefreshDecision(True, "current-release-media-proof-missing-or-stale")
