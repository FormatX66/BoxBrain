import unittest

from Projects.StateWeave.stateweave import State, Transition, run


class StateWeaveTests(unittest.TestCase):
    def test_digest_is_order_independent(self):
        a = State.from_mapping({"b": 2, "a": 1})
        b = State.from_mapping({"a": 1, "b": 2})
        self.assertEqual(a.digest(), b.digest())

    def test_transition_requires_expected_state(self):
        initial = State.from_mapping({"boot.ready": True})
        transition = Transition.build(
            "enter-runtime",
            requires={"boot.ready": True},
            writes={"runtime.ready": True},
        )
        final, trace = run(initial, [transition])
        self.assertTrue(final.as_dict()["runtime.ready"])
        self.assertEqual(len(trace), 1)
        self.assertNotEqual(trace[0].before, trace[0].after)

    def test_invalid_transition_is_bounded(self):
        state = State.from_mapping({"boot.ready": False})
        transition = Transition.build("unsafe", requires={"boot.ready": True})
        with self.assertRaises(ValueError):
            transition.apply(state)


if __name__ == "__main__":
    unittest.main()
