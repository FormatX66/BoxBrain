#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_native_autonomous_chain import run_chain


FRONTIER_GAP_SCHEMA = "aurum-native-frontier-gap-v0"
_NONBLOCKING_BOUNDARIES = frozenset({None, "generation-bound-reached"})


def run_gap(gap: str) -> dict:
    state = run_chain(start_gap=gap, max_generations=1)
    progress_made = bool(state.get("completed_generations"))
    blocked_reason = state.get("blocked_reason")
    blocked = blocked_reason not in _NONBLOCKING_BOUNDARIES
    return {
        "schema": FRONTIER_GAP_SCHEMA,
        "gap": gap,
        "status": "blocked" if blocked else "progressed",
        "progress_made": progress_made,
        "completed_generations": state.get("completed_generations", 0),
        "latest_completed_gap": state.get("latest_completed_gap"),
        "next_gap": state.get("next_gap"),
        "blocked_reason": blocked_reason,
        "blocked_output": state.get("blocked_output"),
        "external_evidence": state.get("external_evidence"),
        "failed_attempt": state.get("failed_attempt"),
        "reusable_native_capabilities": state.get("reusable_native_capabilities", []),
        "reusable_local_capabilities": state.get("reusable_local_capabilities", []),
        "internal_next_action": state.get("internal_next_action"),
        "reasoning_required": state.get("reasoning_required", False),
        "reasoning_request": state.get("reasoning_request"),
        "generation": state.get("generations", [None])[-1] if progress_made else None,
        "global_barrier": False,
        "blocks_other_frontiers": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run exactly one Aurum semantic frontier without serializing unrelated gaps."
    )
    parser.add_argument("--gap", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = run_gap(args.gap)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
