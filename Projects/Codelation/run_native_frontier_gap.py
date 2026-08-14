#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from run_native_autonomous_chain import run_chain


FRONTIER_GAP_SCHEMA = "aurum-native-frontier-gap-v2"
FRONTIER_STATE_PATH = Path(__file__).resolve().parent / "autobuild" / "native_frontier_state.json"
_NONBLOCKING_BOUNDARIES = frozenset({None, "generation-bound-reached"})


def load_converged_seed_expressions(
    path: Path = FRONTIER_STATE_PATH,
) -> dict[str, Mapping[str, Any]]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    seeds = raw.get("converged_native_expressions", {})
    if not isinstance(seeds, Mapping):
        return {}
    normalized: dict[str, Mapping[str, Any]] = {}
    for name, expression in sorted(seeds.items()):
        if isinstance(name, str) and name and isinstance(expression, Mapping):
            normalized[name] = dict(expression)
    return normalized


def run_gap(
    gap: str,
    *,
    seed_expressions: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict:
    seeds = (
        load_converged_seed_expressions()
        if seed_expressions is None
        else {name: dict(expression) for name, expression in seed_expressions.items()}
    )
    state = run_chain(
        start_gap=gap,
        max_generations=1,
        seed_expressions=seeds,
    )
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
        "initial_seed_capabilities": state.get("initial_seed_capabilities", []),
        "initial_seed_expressions": {
            name: dict(expression) for name, expression in sorted(seeds.items())
        },
        "reusable_native_capabilities": state.get("reusable_native_capabilities", []),
        "reusable_native_expressions": state.get("reusable_native_expressions", {}),
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
