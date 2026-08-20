from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "stateweave"))

from stateweave import Effect, Predicate, Transition, Weave, MODE_SET, OP_EQ, OP_LE

BENCHMARK = "bounded_recovery_v1"


def main() -> int:
    weave = Weave(
        state={1: 0, 2: 40},
        goals=(Predicate(1, OP_EQ, 1),),
        invariants=(Predicate(2, OP_LE, 80),),
        transitions=(
            Transition(1, 1, (Predicate(1, OP_EQ, 0),), (Effect(1, MODE_SET, 9),), True),
            Transition(
                2,
                1,
                (Predicate(1, OP_EQ, 0),),
                (Effect(1, MODE_SET, 1), Effect(2, MODE_SET, 100)),
                True,
            ),
            Transition(
                3,
                2,
                (Predicate(1, OP_EQ, 0),),
                (Effect(1, MODE_SET, 1), Effect(2, MODE_SET, 45)),
                True,
            ),
        ),
    )
    plan = weave.plan()
    final_state, receipts = weave.execute(plan)
    encoded = weave.to_bytes()

    # StateWeave planning is deterministic; the second run should require the
    # same semantic path rather than learning hardware-specific failures.
    plan2 = weave.plan()
    final_state2, _ = weave.execute(plan2)

    result = {
        "benchmark": BENCHMARK,
        "lane": "stateweave",
        "success": final_state.get(1) == 1 and final_state2.get(1) == 1,
        "invariant_preserved": final_state.get(2, 0) <= 80 and final_state2.get(2, 0) <= 80,
        "first_attempts": len(receipts),
        "second_attempts": len(plan2),
        "rollback_count": 0,
        "learned_avoidance": False,
        "machine_native_representation": True,
        "semantic_planner": True,
        "adaptive_hardware": False,
        "representation_bytes": len(encoded),
        "chosen_transition_ids": [t.transition_id for t in plan],
        "final_state": final_state2,
    }
    with open("benchmark-result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["success"] and result["invariant_preserved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
