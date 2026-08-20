import unittest

from stateweave import (
    Effect,
    MODE_ADD,
    MODE_SET,
    OP_EQ,
    OP_GE,
    OP_GT,
    Predicate,
    Transition,
    Weave,
)


class StateWeaveTests(unittest.TestCase):
    def test_thermal_goal(self):
        temp = 1
        fan = 2
        weave = Weave(
            state={temp: 95, fan: 0},
            goals=(Predicate(fan, OP_GE, 100),),
            invariants=(Predicate(fan, OP_GE, 0),),
            transitions=(
                Transition(
                    10,
                    1,
                    (Predicate(temp, OP_GT, 90),),
                    (Effect(fan, MODE_SET, 100),),
                    reversible=True,
                ),
            ),
        )
        plan = weave.plan()
        self.assertEqual([transition.transition_id for transition in plan], [10])
        final_state, receipts = weave.execute(plan)
        self.assertEqual(final_state[fan], 100)
        self.assertEqual(len(receipts), 1)
        self.assertNotEqual(receipts[0].before_hash, receipts[0].after_hash)

    def test_lowest_cost_path_wins(self):
        node = 7
        weave = Weave(
            state={node: 0},
            goals=(Predicate(node, OP_EQ, 2),),
            invariants=(Predicate(node, OP_GE, 0),),
            transitions=(
                Transition(1, 5, (Predicate(node, OP_EQ, 0),), (Effect(node, MODE_SET, 2),)),
                Transition(2, 1, (Predicate(node, OP_EQ, 0),), (Effect(node, MODE_ADD, 1),)),
                Transition(3, 1, (Predicate(node, OP_EQ, 1),), (Effect(node, MODE_ADD, 1),)),
            ),
        )
        self.assertEqual([transition.transition_id for transition in weave.plan()], [2, 3])

    def test_binary_round_trip_is_canonical(self):
        weave = Weave(
            state={9: -5, 2: 12},
            goals=(Predicate(2, OP_GE, 12),),
            invariants=(Predicate(9, OP_GE, -100),),
            transitions=(
                Transition(44, 3, (Predicate(2, OP_EQ, 12),), (Effect(9, MODE_ADD, 5),), True),
            ),
        )
        encoded = weave.to_bytes()
        restored = Weave.from_bytes(encoded)
        self.assertEqual(restored.to_bytes(), encoded)
        self.assertEqual(dict(restored.state), {2: 12, 9: -5})

    def test_invariant_blocks_invalid_transition(self):
        node = 3
        weave = Weave(
            state={node: 1},
            goals=(Predicate(node, OP_EQ, -1),),
            invariants=(Predicate(node, OP_GE, 0),),
            transitions=(
                Transition(9, 1, (Predicate(node, OP_EQ, 1),), (Effect(node, MODE_SET, -1),)),
            ),
        )
        with self.assertRaisesRegex(RuntimeError, "no valid plan"):
            weave.plan()


if __name__ == "__main__":
    unittest.main()
