from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "stateweave"))
sys.path.insert(0, str(ROOT / "stateweave_kernel"))

from stateweave import Effect, MODE_SET, OP_EQ, OP_LE, Predicate, Transition, Weave
from adaptive_kernel import AdaptiveKernelFabric, HardwareCandidate


NODE_READY = 1001
NODE_TEMP = 1002
TRANSITION_READY = 2001


def make_weave() -> Weave:
    return Weave(
        state={NODE_READY: 0, NODE_TEMP: 40},
        goals=(Predicate(NODE_READY, OP_EQ, 1),),
        invariants=(Predicate(NODE_TEMP, OP_LE, 85),),
        transitions=(
            Transition(
                transition_id=TRANSITION_READY,
                cost=1,
                preconditions=(Predicate(NODE_READY, OP_EQ, 0),),
                effects=(Effect(NODE_READY, MODE_SET, 1),),
                reversible=True,
            ),
        ),
    )


def correct_action(state, expected):
    state[NODE_READY] = expected[NODE_READY]
    return True


def wrong_action(state, expected):
    state[NODE_READY] = 9
    return True


def hot_action(state, expected):
    state[NODE_READY] = expected[NODE_READY]
    state[NODE_TEMP] = 95
    return True


class AdaptiveKernelTests(unittest.TestCase):
    def test_prefers_low_cost_exact_hardware_candidate(self):
        weave = make_weave()
        fabric = AdaptiveKernelFabric(weave.state)
        fabric.register(
            HardwareCandidate(101, TRANSITION_READY, 1, 800, True, correct_action)
        )
        fabric.register(
            HardwareCandidate(102, TRANSITION_READY, 4, 950, True, correct_action)
        )

        run = fabric.execute_weave(weave)

        self.assertEqual(run.final_state[NODE_READY], 1)
        self.assertEqual(run.receipts[0].action_id, 101)
        self.assertEqual(run.receipts[0].confidence_after, 825)
        self.assertEqual(run.failures, ())

    def test_misverified_candidate_rolls_back_and_falls_back(self):
        weave = make_weave()
        fabric = AdaptiveKernelFabric(weave.state)
        bad = HardwareCandidate(201, TRANSITION_READY, 1, 900, True, wrong_action)
        good = HardwareCandidate(202, TRANSITION_READY, 1, 800, True, correct_action)
        fabric.register(bad)
        fabric.register(good)

        run = fabric.execute_weave(weave)

        self.assertEqual(run.final_state[NODE_READY], 1)
        self.assertEqual(run.receipts[0].action_id, 202)
        self.assertEqual(run.failures[0].action_id, 201)
        self.assertEqual(run.failures[0].reason, "verification_mismatch")
        self.assertEqual(bad.confidence, 800)
        self.assertEqual(good.confidence, 825)

    def test_learning_avoids_previously_bad_equal_cost_candidate(self):
        weave = make_weave()
        fabric = AdaptiveKernelFabric(weave.state)
        bad = HardwareCandidate(301, TRANSITION_READY, 1, 900, True, wrong_action)
        good = HardwareCandidate(302, TRANSITION_READY, 1, 800, True, correct_action)
        fabric.register(bad)
        fabric.register(good)

        first = fabric.execute_weave(weave)
        self.assertEqual(first.receipts[0].action_id, 302)
        self.assertEqual(len(first.failures), 1)

        fabric.hardware_state.clear()
        fabric.hardware_state.update(weave.state)
        second = fabric.execute_weave(weave)

        self.assertEqual(second.receipts[0].action_id, 302)
        self.assertEqual(second.failures, ())
        self.assertGreater(good.confidence, bad.confidence)

    def test_stateweave_invariant_rejects_hot_candidate_and_uses_fallback(self):
        weave = make_weave()
        fabric = AdaptiveKernelFabric(weave.state)
        hot = HardwareCandidate(401, TRANSITION_READY, 1, 950, True, hot_action)
        safe = HardwareCandidate(402, TRANSITION_READY, 2, 700, True, correct_action)
        fabric.register(hot)
        fabric.register(safe)

        run = fabric.execute_weave(weave)

        self.assertEqual(run.final_state[NODE_TEMP], 40)
        self.assertEqual(run.receipts[0].action_id, 402)
        self.assertEqual(run.failures[0].reason, "invariant_violation")
        self.assertTrue(weave.invariants_hold(run.final_state))


if __name__ == "__main__":
    unittest.main()
