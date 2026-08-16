"""Pure abstract driver-program synthesis from verified hardware transitions.

This layer deliberately stops before hardware lowering. It composes independently
verified state transitions into deterministic behavior programs that can be
replayed and checked without MMIO/PIO, DMA, firmware access, device writes, or
physical hardware. Human labels are metadata only; correctness comes from state,
action, ordering, provenance, and invariants.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from Projects.Codelation.driver_transition_synthesis import TRANSITION_MODEL_SCHEMA

PROGRAM_SET_SCHEMA = "aurum.driver.abstract-program-set.v0"
PROGRAM_VERIFICATION_SCHEMA = "aurum.driver.abstract-program-verification.v0"
MAX_PROGRAM_STEPS = 4096


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _identity(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _verified_transitions(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if model.get("schema") != TRANSITION_MODEL_SCHEMA:
        raise ValueError("transition model schema mismatch")
    transitions = model.get("transitions")
    if not isinstance(transitions, dict):
        raise ValueError("transition model is missing transitions")

    verified: dict[str, dict[str, Any]] = {}
    for key, entry in sorted(transitions.items()):
        if not isinstance(key, str) or not key:
            raise ValueError("transition key is invalid")
        if not isinstance(entry, dict):
            raise ValueError("transition entry is invalid")
        if entry.get("state") != "verified":
            continue
        transition = entry.get("transition")
        if not isinstance(transition, dict) or set(transition) != {"before", "action", "after"}:
            raise ValueError("verified transition shape mismatch")
        if not all(isinstance(transition[name], dict) for name in ("before", "action", "after")):
            raise ValueError("verified transition states and action must be objects")
        if not isinstance(transition["action"].get("kind"), str) or not transition["action"]["kind"]:
            raise ValueError("verified transition action kind is required")
        verified[key] = transition
    return verified


def synthesize_abstract_driver_programs(model: dict[str, Any]) -> dict[str, Any]:
    """Compose verified transitions into deterministic non-actuating chains.

    A chain is extended only when exactly one verified transition consumes the
    exact prior state and that state has only one predecessor. Branches and joins
    are preserved as separate programs instead of guessing a preferred path.
    """

    verified = _verified_transitions(model)
    if not verified:
        raise ValueError("no verified transitions are available for program synthesis")

    by_before: dict[str, list[str]] = {}
    by_after: dict[str, list[str]] = {}
    for key, transition in verified.items():
        by_before.setdefault(_canonical(transition["before"]), []).append(key)
        by_after.setdefault(_canonical(transition["after"]), []).append(key)
    for mapping in (by_before, by_after):
        for keys in mapping.values():
            keys.sort()

    branch_states = sorted(state for state, keys in by_before.items() if len(keys) > 1)
    join_states = sorted(state for state, keys in by_after.items() if len(keys) > 1)

    def can_follow(current_key: str, candidate_key: str) -> bool:
        current = verified[current_key]
        candidate = verified[candidate_key]
        state = _canonical(current["after"])
        return (
            state == _canonical(candidate["before"])
            and len(by_before.get(state, [])) == 1
            and len(by_after.get(state, [])) == 1
        )

    predecessors: dict[str, list[str]] = {key: [] for key in verified}
    for key, transition in verified.items():
        before = _canonical(transition["before"])
        for predecessor in by_after.get(before, []):
            if can_follow(predecessor, key):
                predecessors[key].append(predecessor)

    starts = sorted(key for key, preds in predecessors.items() if not preds)
    visited: set[str] = set()
    chains: list[list[str]] = []

    def walk(start: str) -> list[str]:
        chain: list[str] = []
        current = start
        local_seen: set[str] = set()
        while current not in local_seen and current not in visited:
            local_seen.add(current)
            visited.add(current)
            chain.append(current)
            after = _canonical(verified[current]["after"])
            candidates = [
                key for key in by_before.get(after, [])
                if key not in visited and can_follow(current, key)
            ]
            if len(candidates) != 1:
                break
            current = candidates[0]
        return chain

    for start in starts:
        chain = walk(start)
        if chain:
            chains.append(chain)

    # Cycles or isolated remnants are kept, but never silently discarded.
    for key in sorted(set(verified) - visited):
        chain = walk(key)
        if chain:
            chains.append(chain)

    programs: list[dict[str, Any]] = []
    for chain in chains:
        steps = []
        for index, key in enumerate(chain):
            transition = verified[key]
            steps.append({
                "step": index,
                "transition_key": key,
                "expected_before": transition["before"],
                "abstract_action": transition["action"],
                "expected_after": transition["after"],
            })
        program = {
            "mode": "abstract-non-actuating",
            "actuating": False,
            "model_identity": model.get("model_identity"),
            "initial_state": steps[0]["expected_before"],
            "final_state": steps[-1]["expected_after"],
            "steps": steps,
            "hardware_lowering": None,
            "requires_hardware_lowering_before_execution": True,
        }
        program["program_identity"] = _identity(program)
        programs.append(program)

    programs.sort(key=lambda item: item["program_identity"])
    covered = sorted(
        step["transition_key"] for program in programs for step in program["steps"]
    )
    uncertain = sorted(
        key for key, entry in model["transitions"].items()
        if isinstance(entry, dict) and entry.get("state") != "verified"
    )

    result = {
        "schema": PROGRAM_SET_SCHEMA,
        "mode": "abstract-non-actuating",
        "actuating": False,
        "physical_hardware_proof": False,
        "model_identity": model.get("model_identity"),
        "programs": programs,
        "verified_transition_keys": sorted(verified),
        "covered_transition_keys": covered,
        "uncertain_transition_keys": uncertain,
        "unresolved_branch_states": [json.loads(state) for state in branch_states],
        "unresolved_join_states": [json.loads(state) for state in join_states],
        "lowering": {
            "performed": False,
            "register_addresses_emitted": False,
            "physical_writes_authorized": False,
            "firmware_changes_authorized": False,
        },
    }
    result["program_set_identity"] = _identity(result)
    return result


def verify_abstract_driver_programs(
    model: dict[str, Any],
    program_set: dict[str, Any],
) -> dict[str, Any]:
    """Fail-closed proof that abstract programs exactly preserve verified rules."""

    verified = _verified_transitions(model)
    if not isinstance(program_set, dict) or program_set.get("schema") != PROGRAM_SET_SCHEMA:
        raise ValueError("abstract driver program schema mismatch")
    if program_set.get("actuating") is not False or program_set.get("mode") != "abstract-non-actuating":
        raise ValueError("abstract driver programs must be explicitly non-actuating")
    if program_set.get("model_identity") != model.get("model_identity"):
        raise ValueError("abstract driver program model identity mismatch")
    lowering = program_set.get("lowering")
    if not isinstance(lowering, dict) or lowering.get("performed") is not False:
        raise ValueError("hardware-lowered programs are outside this safety lane")
    if lowering.get("physical_writes_authorized") is not False:
        raise ValueError("physical writes are outside this safety lane")

    programs = program_set.get("programs")
    if not isinstance(programs, list) or not programs:
        raise ValueError("abstract driver programs are required")

    seen: set[str] = set()
    counts = {"matched": 0, "mismatched": 0, "discontinuous": 0, "duplicate": 0, "unknown": 0}
    results: list[dict[str, Any]] = []
    total_steps = 0

    for program in programs:
        if not isinstance(program, dict) or program.get("actuating") is not False:
            raise ValueError("program must be explicitly non-actuating")
        if program.get("hardware_lowering") is not None:
            raise ValueError("program contains hardware lowering")
        steps = program.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError("program steps are required")
        total_steps += len(steps)
        if total_steps > MAX_PROGRAM_STEPS:
            raise ValueError("abstract driver program set exceeded step limit")

        prior_after: dict[str, Any] | None = None
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                raise ValueError("program step must be an object")
            expected_keys = {"step", "transition_key", "expected_before", "abstract_action", "expected_after"}
            if set(step) != expected_keys or step["step"] != index:
                raise ValueError("program step shape or order mismatch")
            key = step["transition_key"]
            transition = verified.get(key) if isinstance(key, str) else None
            observed = {
                "before": step["expected_before"],
                "action": step["abstract_action"],
                "after": step["expected_after"],
            }

            if key in seen:
                outcome = "duplicate"
            elif transition is None:
                outcome = "unknown"
            elif _canonical(transition) != _canonical(observed):
                outcome = "mismatched"
            elif prior_after is not None and _canonical(prior_after) != _canonical(step["expected_before"]):
                outcome = "discontinuous"
            else:
                outcome = "matched"
                seen.add(key)
            if outcome != "matched" and isinstance(key, str) and key in verified:
                seen.add(key)
            counts[outcome] += 1
            prior_after = step["expected_after"]
            results.append({
                "program_identity": program.get("program_identity"),
                "step": index,
                "transition_key": key,
                "outcome": outcome,
            })

    missing = sorted(set(verified) - seen)
    covered = len(set(verified) & seen)
    coverage = covered / len(verified) if verified else 0.0
    passed = (
        bool(verified)
        and coverage == 1.0
        and not missing
        and all(counts[name] == 0 for name in ("mismatched", "discontinuous", "duplicate", "unknown"))
    )
    verification = {
        "schema": PROGRAM_VERIFICATION_SCHEMA,
        "status": "passed" if passed else "failed",
        "actuating": False,
        "physical_hardware_proof": False,
        "model_identity": model.get("model_identity"),
        "program_set_identity": program_set.get("program_set_identity"),
        "verified_transition_coverage": coverage,
        "missing_verified_transitions": missing,
        "counts": counts,
        "steps": results,
        "safety": {
            "hardware_access_performed": False,
            "hardware_lowering_performed": False,
            "physical_writes_authorized": False,
            "firmware_changes_authorized": False,
        },
    }
    verification["verification_identity"] = _identity(verification)
    return verification
