from __future__ import annotations

import json

from adaptive_kernel import AdaptiveKernel, Candidate

BENCHMARK = "bounded_recovery_v1"


def build_candidates() -> list[Candidate]:
    return [
        Candidate(1, 1, 90, True, lambda s: {**s, 1: 9}),
        Candidate(2, 1, 80, True, lambda s: {**s, 1: 1, 2: 100}),
        Candidate(3, 2, 70, True, lambda s: {**s, 1: 1, 2: 45}),
    ]


def main() -> int:
    kernel = AdaptiveKernel({1: 0, 2: 40})
    verify = lambda s: s.get(1) == 1
    invariant = lambda s: s.get(2, 0) <= 80

    first_state, first_attempts = kernel.realize(build_candidates(), verify, invariant)
    kernel.state = {1: 0, 2: 40}
    second_state, second_attempts = kernel.realize(build_candidates(), verify, invariant)

    result = {
        "benchmark": BENCHMARK,
        "lane": "adaptive-kernel",
        "success": first_state.get(1) == 1 and second_state.get(1) == 1,
        "invariant_preserved": invariant(first_state) and invariant(second_state),
        "first_attempts": len(first_attempts),
        "second_attempts": len(second_attempts),
        "rollback_count": sum(a.rolled_back for a in first_attempts + second_attempts),
        "learned_avoidance": len(second_attempts) < len(first_attempts),
        "machine_native_representation": False,
        "semantic_planner": False,
        "adaptive_hardware": True,
        "confidence": dict(sorted(kernel.confidence.items())),
        "final_state": second_state,
    }
    with open("benchmark-result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["success"] and result["invariant_preserved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
