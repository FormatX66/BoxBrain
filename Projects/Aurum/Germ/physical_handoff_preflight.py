"""Side-effect-free Tiny Seed physical handoff preflight.

Consumes canonical release truth plus an optional privacy-safe USB discovery receipt
and collapses them into the next bounded handoff state. It never selects a raw disk
by itself and never grants write authority.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


READY_RELEASE_STATE = "READY_TO_FLASH"


def evaluate_physical_preflight(
    release: Mapping[str, Any],
    discovery: Mapping[str, Any] | None,
) -> dict[str, Any]:
    state = str(release.get("state") or "")
    gates = release.get("gates") or {}
    x86 = (release.get("artifacts") or {}).get("x86") or {}

    base = {
        "schema": "aurum-tinyseed-physical-preflight-v1",
        "release_state": state,
        "release_source_commit": release.get("source_commit"),
        "x86_artifact": x86.get("name"),
        "x86_sha256": x86.get("sha256"),
        "write_authority": False,
        "destructive_action_allowed": False,
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
    args = parser.parse_args()

    release = _read_json(Path(args.release))
    discovery_path = Path(args.discovery) if args.discovery else None
    discovery = _read_json(discovery_path) if discovery_path and discovery_path.exists() else None
    print(json.dumps(evaluate_physical_preflight(release, discovery), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
