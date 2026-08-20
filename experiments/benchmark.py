from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "stateweave"))
sys.path.insert(0, str(ROOT / "stateweave_kernel"))

from stateweave import Effect, Predicate, Transition, Weave, MODE_SET, OP_EQ, OP_LE
from adaptive_kernel import AdaptiveKernelFabric, HardwareCandidate

BENCHMARK = "bounded_recovery_v1"


def build_weave() -> Weave:
    return Weave(
        state={1: 0, 2: 40},
        goals=(Predicate(1, OP_EQ, 1),),
        invariants=(Predicate(2, OP_LE, 80),),
        transitions=(
            Transition(
                10,
                1,
                (Predicate(1, OP_EQ, 0),),
                (Effect(1, MODE_SET, 1),),
                True,
            ),
        ),
    )


def bad(state, expected):
    state[1] = 9
    return True


def unsafe(state, expected):
    state[1] = 1
    state[2] = 100
    return True


def safe(state, expected):
    state[1] = expected[1]
    return True


def main() -> int:
    weave = build_weave()
    fabric = AdaptiveKernelFabric({1: 0, 2: 40})
    fabric.register(HardwareCandidate(1, 10, 1, 900, True, bad))
    fabric.register(HardwareCandidate(2, 10, 1, 800, True, unsafe))
    fabric.register(HardwareCandidate(3, 10, 2, 700, True, safe))

    first = fabric.execute_weave(weave)
    fabric.hardware_state.clear()
    fabric.hardware_state.update({1: 0, 2: 40})
    second = fabric.execute_weave(weave)

    result = {
        "benchmark": BENCHMARK,
        "lane": "stateweave-adaptive-kernel",
        "success": first.final_state.get(1) == 1 and second.final_state.get(1) == 1,
        "invariant_preserved": first.final_state.get(2, 0) <= 80 and second.final_state.get(2, 0) <= 80,
        "first_attempts": len(first.receipts) + len(first.failures),
        "second_attempts": len(second.receipts) + len(second.failures),
        "rollback_count": len(first.failures) + len(second.failures),
        "learned_avoidance": (len(second.receipts) + len(second.failures)) < (len(first.receipts) + len(first.failures)),
        "machine_native_representation": True,
        "semantic_planner": True,
        "adaptive_hardware": True,
        "candidate_confidence": {
            str(c.action_id): c.confidence for c in fabric.candidates_for(10)
        },
        "final_state": dict(second.final_state),
    }
    with open("benchmark-result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["success"] and result["invariant_preserved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
