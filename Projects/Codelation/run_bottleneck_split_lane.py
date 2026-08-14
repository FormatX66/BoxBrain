#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from run_native_frontier_gap import (
    FRONTIER_GAP_SCHEMA,
    load_converged_seed_expressions,
    run_gap,
)
from field_native_vm import compile_native, execute_native, verify_native
from native_gap_catalog import get_native_semantic_gap
from native_program_synthesis import synthesize_native_expression


SPLIT_LANE_SCHEMA = "aurum-bottleneck-split-lane-v1"
ADVENTUROUS_MAX_COST = 20
ADVENTUROUS_MAX_SIGNATURES = 30000


def _identity(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.blake2s(b"AURUM-BOTTLENECK-SPLIT-1\x00" + raw).hexdigest()


def _bounded_synthesis_candidate(safe_state: Mapping[str, Any]) -> dict:
    source_gap = str(safe_state.get("gap", ""))
    spec = get_native_semantic_gap(source_gap)
    if spec is None:
        payload = {
            "schema": SPLIT_LANE_SCHEMA,
            "source_gap": source_gap,
            "mode": "adventurous",
            "strategy": "expanded-bounded-native-synthesis",
            "status": "semantic-spec-missing",
            "progress_made": False,
            "source_block_preserved": True,
            "global_barrier": False,
        }
        return {**payload, "identity": _identity(payload)}

    seeds = load_converged_seed_expressions()
    max_cost = min(ADVENTUROUS_MAX_COST, max(spec.max_synthesis_cost + 8, 18))
    synthesis = synthesize_native_expression(
        spec.parameters,
        spec.examples,
        max_cost=max_cost,
        max_signatures=ADVENTUROUS_MAX_SIGNATURES,
        seed_expressions=seeds,
    )
    verified = False
    invocation_output: Any = None
    verification_identity: str | None = None
    if synthesis.found and synthesis.expression is not None:
        program = compile_native(spec.parameters, synthesis.expression)
        verification = verify_native(program, spec.examples)
        verified = verification.verified
        verification_identity = hashlib.sha256(
            json.dumps(
                {
                    "program": verification.program_identity,
                    "tape": verification.tape_identity,
                    "passed": verification.passed,
                    "examples": verification.examples,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if verified:
            invocation_output = execute_native(program, spec.invocation_arguments)

    payload = {
        "schema": SPLIT_LANE_SCHEMA,
        "source_gap": source_gap,
        "mode": "adventurous",
        "strategy": "expanded-bounded-native-synthesis",
        "status": "verified-candidate" if verified else "expanded-search-exhausted",
        "progress_made": verified,
        "source_block_preserved": True,
        "global_barrier": False,
        "safe_max_cost": spec.max_synthesis_cost,
        "adventurous_max_cost": max_cost,
        "candidates_evaluated": synthesis.candidates_evaluated,
        "signatures_retained": synthesis.signatures_retained,
        "synthesis_proof_identity": synthesis.proof_identity,
        "candidate_expression": dict(synthesis.expression) if verified and synthesis.expression is not None else None,
        "candidate_verification_identity": verification_identity,
        "candidate_invocation_output": invocation_output,
        "promotion_performed": False,
        "model_reasoning_used": False,
        "authority_granted": False,
    }
    return {**payload, "identity": _identity(payload)}


def _adjacent_frontier_candidate(safe_state: Mapping[str, Any]) -> dict:
    source_gap = str(safe_state.get("gap", ""))
    spec = get_native_semantic_gap(source_gap)
    target_gap = str(spec.next_gap if spec is not None else safe_state.get("next_gap") or "")
    if not target_gap or target_gap == source_gap:
        payload = {
            "schema": SPLIT_LANE_SCHEMA,
            "source_gap": source_gap,
            "mode": "adventurous",
            "strategy": "adjacent-frontier-lookahead",
            "status": "no-adjacent-frontier",
            "progress_made": False,
            "target_gap": target_gap or None,
            "source_block_preserved": True,
            "global_barrier": False,
            "promotion_performed": False,
            "model_reasoning_used": False,
            "authority_granted": False,
        }
        return {**payload, "identity": _identity(payload)}

    adjacent = run_gap(target_gap)
    payload = {
        "schema": SPLIT_LANE_SCHEMA,
        "source_gap": source_gap,
        "mode": "adventurous",
        "strategy": "adjacent-frontier-lookahead",
        "status": "progressed-around-block" if adjacent.get("progress_made") else "adjacent-frontier-blocked",
        "progress_made": bool(adjacent.get("progress_made")),
        "target_gap": target_gap,
        "target_status": adjacent.get("status"),
        "target_blocked_reason": adjacent.get("blocked_reason"),
        "target_latest_completed_gap": adjacent.get("latest_completed_gap"),
        "source_block_preserved": True,
        "global_barrier": False,
        "adjacent_frontier": adjacent,
        "promotion_performed": False,
        "model_reasoning_used": False,
        "authority_granted": False,
    }
    return {**payload, "identity": _identity(payload)}


def run_adventurous(safe_state: Mapping[str, Any]) -> dict:
    if safe_state.get("blocked_reason") == "native-synthesis-not-found":
        return _bounded_synthesis_candidate(safe_state)
    return _adjacent_frontier_candidate(safe_state)


def run_verifier(safe_state: Mapping[str, Any]) -> dict:
    source_gap = str(safe_state.get("gap", ""))
    checks: dict[str, bool] = {
        "frontier_schema_valid": safe_state.get("schema") == FRONTIER_GAP_SCHEMA,
        "gap_present": bool(source_gap),
        "block_explicit": safe_state.get("status") == "blocked" and bool(safe_state.get("blocked_reason")),
        "not_global_barrier": safe_state.get("global_barrier") is False,
        "does_not_block_siblings": safe_state.get("blocks_other_frontiers") is False,
    }

    independent_search: dict[str, Any] | None = None
    if safe_state.get("blocked_reason") == "native-synthesis-not-found":
        spec = get_native_semantic_gap(source_gap)
        if spec is None:
            checks["semantic_spec_present"] = False
        else:
            seeds = load_converged_seed_expressions()
            replay = synthesize_native_expression(
                spec.parameters,
                spec.examples,
                max_cost=spec.max_synthesis_cost,
                seed_expressions=seeds,
            )
            reproduced = not replay.found
            checks["safe_search_block_reproduced"] = reproduced
            independent_search = {
                "max_cost": spec.max_synthesis_cost,
                "found": replay.found,
                "proof_identity": replay.proof_identity,
                "candidates_evaluated": replay.candidates_evaluated,
                "signatures_retained": replay.signatures_retained,
            }

    verified = all(checks.values())
    payload = {
        "schema": SPLIT_LANE_SCHEMA,
        "source_gap": source_gap,
        "mode": "independent-verifier",
        "status": "verified-block-classification" if verified else "verification-failed",
        "verified": verified,
        "checks": checks,
        "independent_safe_search": independent_search,
        "blocked_reason": safe_state.get("blocked_reason"),
        "blocked_output": safe_state.get("blocked_output"),
        "source_block_preserved": True,
        "global_barrier": False,
        "promotion_performed": False,
        "model_reasoning_used": False,
        "authority_granted": False,
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
