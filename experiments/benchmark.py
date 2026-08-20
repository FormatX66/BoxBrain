from __future__ import annotations

import json

BENCHMARK = "bounded_recovery_v1"


def run_once(learned_bad: set[int]) -> tuple[dict[int, int], int, int, bool]:
    initial = {1: 0, 2: 40}
    candidates = (
        (1, lambda s: {**s, 1: 9}),
        (2, lambda s: {**s, 1: 1, 2: 100}),
        (3, lambda s: {**s, 1: 1, 2: 45}),
    )
    attempts = 0
    rollbacks = 0
    state = dict(initial)
    for candidate_id, apply in candidates:
        if candidate_id in learned_bad:
            continue
        attempts += 1
        before = dict(state)
        proposed = apply(dict(state))
        goal = proposed.get(1) == 1
        invariant = proposed.get(2, 0) <= 80
        if goal and invariant:
            state = proposed
            return state, attempts, rollbacks, True
        learned_bad.add(candidate_id)
        state = before
        rollbacks += 1
    return state, attempts, rollbacks, False


def main() -> int:
    learned_bad: set[int] = set()
    first_state, first_attempts, first_rollbacks, first_success = run_once(learned_bad)
    second_state, second_attempts, second_rollbacks, second_success = run_once(learned_bad)
    result = {
        "benchmark": BENCHMARK,
        "lane": "conventional-aurum",
        "success": first_success and second_success,
        "invariant_preserved": first_state.get(2, 0) <= 80 and second_state.get(2, 0) <= 80,
        "first_attempts": first_attempts,
        "second_attempts": second_attempts,
        "rollback_count": first_rollbacks + second_rollbacks,
        "learned_avoidance": second_attempts < first_attempts,
        "machine_native_representation": False,
        "semantic_planner": False,
        "adaptive_hardware": False,
        "final_state": second_state,
    }
    with open("benchmark-result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["success"] and result["invariant_preserved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
