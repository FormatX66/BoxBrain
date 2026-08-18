#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

from Projects.Codelation import run_native_autonomous_chain as legacy_executor


DEFAULT_STATE_PATH = Path(__file__).resolve().parent / "autobuild" / "native_frontier_state.json"
DEFAULT_BOOTSTRAP_PATH = Path(__file__).resolve().parent / "autobuild" / "native_chain_state.json"
STATE_SCHEMA = "aurum-native-frontier-v1"
PROGRESS_PREFIX = "AURUM_FRONTIER_PROGRESS "


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _read_mapping(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return dict(value) if isinstance(value, Mapping) else None


def _strip_sequence_semantics(value: Any) -> Any:
    """Remove obsolete age/sequence bookkeeping from executor evidence.

    Aurum cares about capabilities, dependencies, evidence, and the unresolved frontier.
    Historic ordinal labels are compatibility detail and never enter authoritative state.
    """
    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if "generation" in lowered:
                continue
            cleaned[str(key)] = _strip_sequence_semantics(item)
        return cleaned
    if isinstance(value, list):
        return [_strip_sequence_semantics(item) for item in value]
    if isinstance(value, tuple):
        return [_strip_sequence_semantics(item) for item in value]
    return value


def _canonical_hash(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _executor_seed(checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": legacy_executor.STATE_SCHEMA,
        "catalog_revision": legacy_executor.CATALOG_REVISION,
        "synthesis_revision": legacy_executor.SYNTHESIS_REVISION,
        "self_debug_revision": legacy_executor.SELF_DEBUG_REVISION,
        "local_verification_revision": legacy_executor.LOCAL_VERIFICATION_REVISION,
        "_checkpoint": dict(checkpoint),
    }


def _bootstrap_frontier(bootstrap: Mapping[str, Any] | None) -> dict[str, Any]:
    if bootstrap:
        checkpoint = bootstrap.get("_checkpoint")
        current = bootstrap.get("next_gap") or bootstrap.get("start_gap") or "learning_delta_score"
        external = bootstrap.get("external_evidence")
        if isinstance(checkpoint, Mapping):
            return {
                "schema": STATE_SCHEMA,
                "frontier": [str(current)],
                "verified_work": {},
                "executor_checkpoint": _strip_sequence_semantics(dict(checkpoint)),
                "external_evidence": _strip_sequence_semantics(external),
                "blocked_reason": None,
                "reasoning_required": False,
                "reasoning_request": None,
                "yield_reason": "compatibility-import",
                "last_work": None,
                "timer_dependency": False,
            }
    return {
        "schema": STATE_SCHEMA,
        "frontier": ["learning_delta_score"],
        "verified_work": {},
        "executor_checkpoint": {
            "schema": "aurum-native-chain-resume-v1",
            "learned_expressions": {},
            "verified_local_capabilities": [],
        },
        "external_evidence": None,
        "blocked_reason": None,
        "reasoning_required": False,
        "reasoning_request": None,
        "yield_reason": "new-frontier",
        "last_work": None,
        "timer_dependency": False,
    }


def _valid_frontier_state(state: Mapping[str, Any] | None) -> bool:
    return bool(
        isinstance(state, Mapping)
        and state.get("schema") == STATE_SCHEMA
        and isinstance(state.get("frontier"), list)
        and isinstance(state.get("verified_work"), Mapping)
        and isinstance(state.get("executor_checkpoint"), Mapping)
    )


def advance_frontier(
    state: Mapping[str, Any],
    *,
    work_budget: int = 32,
    evidence_now: int | None = None,
) -> dict[str, Any]:
    if work_budget < 1:
        raise ValueError("work_budget must be positive")
    if not _valid_frontier_state(state):
        raise ValueError("invalid Aurum frontier state")

    result = dict(state)
    verified_work = dict(result.get("verified_work") or {})
    frontier = [str(item) for item in result.get("frontier") or [] if str(item)]
    checkpoint = dict(result.get("executor_checkpoint") or {})
    result["blocked_reason"] = None
    result["reasoning_required"] = False
    result["reasoning_request"] = None
    result["yield_reason"] = None

    work_done = 0
    while frontier and work_done < work_budget:
        gap = frontier[0]
        executor_result = legacy_executor.run_chain(
            start_gap=gap,
            max_generations=1,
            evidence_now=evidence_now,
            seed_state=_executor_seed(checkpoint),
        )

        raw_records = executor_result.get("generations") or []
        if raw_records:
            clean_record = _strip_sequence_semantics(raw_records[-1])
            if not isinstance(clean_record, Mapping):
                raise ValueError("executor returned invalid work evidence")
            record = dict(clean_record)
            record["frontier_input"] = gap
            work_id = _canonical_hash(record)
            verified_work[work_id] = record
            result["last_work"] = work_id
            work_done += 1

        raw_checkpoint = executor_result.get("_checkpoint")
        if isinstance(raw_checkpoint, Mapping):
            checkpoint = dict(_strip_sequence_semantics(raw_checkpoint))

        next_gap = executor_result.get("next_gap")
        blocked_reason = executor_result.get("blocked_reason")
        reasoning_required = bool(executor_result.get("reasoning_required"))

        result["external_evidence"] = _strip_sequence_semantics(
            executor_result.get("external_evidence")
        )
        result["reasoning_required"] = reasoning_required
        result["reasoning_request"] = _strip_sequence_semantics(
            executor_result.get("reasoning_request")
        )

        # A one-item executor slice reports its private budget as exhausted after a
        # successful item. That is not a system blocker; the frontier simply advances.
        if raw_records and blocked_reason == "generation-bound-reached":
            blocked_reason = None

        if blocked_reason:
            result["blocked_reason"] = str(blocked_reason)
            frontier = [str(next_gap or gap)]
            break

        if next_gap:
            frontier = [str(next_gap)]
            continue

        frontier = []
        result["yield_reason"] = "frontier-converged"
        break

    if frontier and not result.get("blocked_reason") and work_done >= work_budget:
        result["yield_reason"] = "work-budget-yield"
    elif frontier and result.get("blocked_reason"):
        result["yield_reason"] = "blocked-on-evidence-or-capability"
    elif not frontier and result.get("yield_reason") is None:
        result["yield_reason"] = "frontier-converged"

    result["schema"] = STATE_SCHEMA
    result["frontier"] = frontier
    result["verified_work"] = verified_work
    result["executor_checkpoint"] = checkpoint
    result["work_done_this_burst"] = work_done
    result["timer_dependency"] = False
    return result


def _work_budget(value: str) -> int:
    budget = int(value)
    if budget < 1 or budget > 128:
        raise argparse.ArgumentTypeError("work budget must be between 1 and 128")
    return budget


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Advance Aurum's capability frontier until blocked, converged, or the current compute burst yields"
    )
    parser.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--bootstrap-state", type=Path, default=DEFAULT_BOOTSTRAP_PATH)
    parser.add_argument("--work-budget", type=_work_budget, default=32)
    parser.add_argument("--evidence-now", type=int)
    args = parser.parse_args()

    state_path = args.state_path.resolve()
    current = _read_mapping(state_path)
    if not _valid_frontier_state(current):
        current = _bootstrap_frontier(_read_mapping(args.bootstrap_state.resolve()))

    advanced = advance_frontier(
        current,
        work_budget=args.work_budget,
        evidence_now=args.evidence_now,
    )
    _atomic_write(state_path, advanced)
    print(PROGRESS_PREFIX + json.dumps({
        "frontier": advanced.get("frontier"),
        "yield_reason": advanced.get("yield_reason"),
        "blocked_reason": advanced.get("blocked_reason"),
        "work_done_this_burst": advanced.get("work_done_this_burst"),
    }, sort_keys=True), file=sys.stderr)
    print(json.dumps(advanced, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
