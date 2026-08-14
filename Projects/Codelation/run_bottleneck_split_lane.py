#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from run_native_frontier_gap import FRONTIER_GAP_SCHEMA, run_gap


SPLIT_LANE_SCHEMA = "aurum-bottleneck-split-lane-v0"


def _identity(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.blake2s(b"AURUM-BOTTLENECK-SPLIT-0\x00" + raw).hexdigest()


def run_adventurous(safe_state: dict) -> dict:
    source_gap = str(safe_state.get("gap", ""))
    target_gap = str(safe_state.get("next_gap") or "")
    if not target_gap or target_gap == source_gap:
        payload = {
            "schema": SPLIT_LANE_SCHEMA,
            "source_gap": source_gap,
            "mode": "adventurous",
            "status": "no-adjacent-frontier",
            "progress_made": False,
            "target_gap": target_gap or None,
            "source_block_preserved": True,
            "global_barrier": False,
        }
        return {**payload, "identity": _identity(payload)}

    adjacent = run_gap(target_gap)
    payload = {
        "schema": SPLIT_LANE_SCHEMA,
        "source_gap": source_gap,
        "mode": "adventurous",
        "status": "progressed-around-block" if adjacent.get("progress_made") else "adjacent-frontier-blocked",
        "progress_made": bool(adjacent.get("progress_made")),
        "target_gap": target_gap,
        "target_status": adjacent.get("status"),
        "target_blocked_reason": adjacent.get("blocked_reason"),
        "target_latest_completed_gap": adjacent.get("latest_completed_gap"),
        "source_block_preserved": True,
        "global_barrier": False,
        "adjacent_frontier": adjacent,
    }
    return {**payload, "identity": _identity(payload)}


def run_verifier(safe_state: dict) -> dict:
    source_gap = str(safe_state.get("gap", ""))
    checks = {
        "frontier_schema_valid": safe_state.get("schema") == FRONTIER_GAP_SCHEMA,
        "gap_present": bool(source_gap),
        "block_explicit": safe_state.get("status") == "blocked" and bool(safe_state.get("blocked_reason")),
        "not_global_barrier": safe_state.get("global_barrier") is False,
        "does_not_block_siblings": safe_state.get("blocks_other_frontiers") is False,
    }
    verified = all(checks.values())
    payload = {
        "schema": SPLIT_LANE_SCHEMA,
        "source_gap": source_gap,
        "mode": "independent-verifier",
        "status": "verified-block-classification" if verified else "verification-failed",
        "verified": verified,
        "checks": checks,
        "blocked_reason": safe_state.get("blocked_reason"),
        "blocked_output": safe_state.get("blocked_output"),
        "source_block_preserved": True,
        "global_barrier": False,
    }
    return {**payload, "identity": _identity(payload)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument(
        "--mode",
        required=True,
        choices=("adventurous", "independent-verifier"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    safe_state = json.loads(args.state.read_text(encoding="utf-8"))
    if args.mode == "adventurous":
        result = run_adventurous(safe_state)
        returncode = 0
    else:
        result = run_verifier(safe_state)
        returncode = 0 if result.get("verified") else 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
