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
from typing import Any, Mapping


READY_RELEASE_STATE = "READY_TO_FLASH"
AUTHORIZED_REQUEST_STATE = "AUTHORIZED_ONCE"
AUTHORIZED_CONFIRMATION = "FLASH_TINY_SEED_TEST_USB"


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

    base = {
        "schema": "aurum-tinyseed-physical-preflight-v2",
        "release_state": state,
        "release_source_commit": release.get("source_commit"),
        "x86_artifact": x86.get("name"),
        "x86_sha256": x86.get("sha256"),
        "write_authority": False,
        "destructive_action_allowed": False,
        "authorization": authorization,
        "physical_boot_proven": gates.get("physical_boot") == "passed",
        "guardian_forced_rollback_proven": gates.get("guardian_forced_rollback") == "passed",
    }

    if state != READY_RELEASE_STATE:
        return {**base, "preflight_state": "WAIT_RELEASE", "eligible_count": 0}

    if discovery is None:
        return {**base, "preflight_state": "WAIT_USB_DISCOVERY", "eligible_count": 0}

    if bool(discovery.get("write_authority")):
        return {**base, "preflight_state": "REFUSE_DISCOVERY_AUTHORITY", "eligible_count": 0}

    eligible_count = int(discovery.get("eligible_count") or 0)
    selection = str(discovery.get("selection_state") or "")
    common = {
        **base,
        "discovery_request_id": discovery.get("request_id"),
        "discovery_selection_state": selection,
        "eligible_count": eligible_count,
    }

    if selection == "UNIQUE_SAFE_TO_PREFLIGHT_ONLY" and eligible_count == 1:
        if authorization["authorization_state"] == "VALID_ONE_SHOT_PENDING_LIVE_REPROOF":
            return {**common, "preflight_state": "AUTHORIZED_ONE_SHOT_PENDING_LIVE_REPROOF"}
        if str(authorization["authorization_state"]).startswith("REFUSE_"):
            return {**common, "preflight_state": "REFUSE_FLASH_AUTHORIZATION"}
        return {**common, "preflight_state": "READY_FOR_GUARDED_FLASH_PREFLIGHT"}
    if selection == "AMBIGUOUS_MULTIPLE_ELIGIBLE" or eligible_count > 1:
        return {**common, "preflight_state": "WAIT_USB_SELECTION"}
    if selection == "NO_ELIGIBLE_USB" or eligible_count == 0:
        return {**common, "preflight_state": "WAIT_USB_MEDIA"}
    return {**common, "preflight_state": "REFUSE_UNRECOGNIZED_DISCOVERY"}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--discovery")
    parser.add_argument("--flash-request")
    parser.add_argument("--now-utc")
    args = parser.parse_args()

    release = _read_json(Path(args.release))
    discovery_path = Path(args.discovery) if args.discovery else None
    discovery = _read_json(discovery_path) if discovery_path and discovery_path.exists() else None
    request_path = Path(args.flash_request) if args.flash_request else None
    request = _read_json(request_path) if request_path and request_path.exists() else None
    now = _parse_utc(args.now_utc) if args.now_utc else None
    print(
        json.dumps(
            evaluate_physical_preflight(release, discovery, request, now_utc=now),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
