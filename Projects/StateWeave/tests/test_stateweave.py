import unittest

from Projects.StateWeave.stateweave import (
    BranchEvidenceRecord,
    BranchRecord,
    State,
    Transition,
    record_branch_set,
    run,
)


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

    def test_future_branch_records_decision_facts_without_selecting(self):
        state = State.from_mapping({"boot.slot": "A"})
        records = (
            BranchRecord(
                branch_id="candidate-B",
                proposed_state="boot-slot-B",
                confidence=0.82,
                risk=0.20,
                rollback_target="boot-slot-A",
                evidence=(
                    BranchEvidenceRecord("health.canary", 0.8, 1.0, True),
                    BranchEvidenceRecord("resume.regression", 1.0, 1.0, False),
                ),
            ),
            BranchRecord(
                branch_id="lkg-A",
                proposed_state="boot-slot-A",
                confidence=0.95,
                risk=0.05,
                status="verified",
                is_last_known_good=True,
            ),
        )

        result = record_branch_set(state, records).as_dict()
        self.assertEqual(result["future.branch.count"], 2)
        self.assertEqual(result["future.branch.candidate-B.rollback_target"], "boot-slot-A")
        self.assertFalse(result["future.branch.candidate-B.evidence.1.supports"])
        self.assertTrue(result["future.branch.lkg-A.is_last_known_good"])
        self.assertEqual(result["boot.slot"], "A")

    def test_future_branch_rejects_non_auditable_id(self):
        record = BranchRecord("bad branch/id", "state", 0.5, 0.1)
        with self.assertRaises(ValueError):
            record_branch_set(State.from_mapping({}), [record])


if __name__ == "__main__":
    unittest.main()
