import unittest

from Projects.StateWeave.stateweave import (
    BranchEvidenceRecord,
    BranchRecord,
    State,
    Transition,
    expire_stale_branches,
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
        basis = state.digest()
        records = (
            BranchRecord(
                branch_id="candidate-B",
                proposed_state="boot-slot-B",
                confidence=0.82,
                risk=0.20,
                rollback_target="boot-slot-A",
                basis_state_digest=basis,
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
                basis_state_digest=basis,
            ),
        )

        result = record_branch_set(state, records).as_dict()
        self.assertEqual(result["future.branch.count"], 2)
        self.assertEqual(result["future.branch.candidate-B.rollback_target"], "boot-slot-A")
        self.assertEqual(result["future.branch.candidate-B.basis_state_digest"], basis)
        self.assertFalse(result["future.branch.candidate-B.evidence.1.supports"])
        self.assertTrue(result["future.branch.lkg-A.is_last_known_good"])
        self.assertEqual(result["boot.slot"], "A")

    def test_future_branch_rejects_non_auditable_id(self):
        record = BranchRecord("bad branch/id", "state", 0.5, 0.1)
        with self.assertRaises(ValueError):
            record_branch_set(State.from_mapping({}), [record])

    def test_stale_warm_branch_expires_when_verified_state_basis_changes(self):
        original = State.from_mapping({"boot.slot": "A", "health": "green"})
        old_basis = original.digest()
        recorded = record_branch_set(
            original,
            [
                BranchRecord(
                    "candidate-B",
                    "boot-slot-B",
                    0.8,
                    0.2,
                    status="warm",
                    basis_state_digest=old_basis,
                ),
                BranchRecord(
                    "lkg-A",
                    "boot-slot-A",
                    1.0,
                    0.0,
                    status="verified",
                    is_last_known_good=True,
                    basis_state_digest=old_basis,
                ),
            ],
        )
        new_verified = State.from_mapping({"boot.slot": "A", "health": "green", "firmware.rev": "2"})
        expired = expire_stale_branches(recorded, current_verified_state_digest=new_verified.digest()).as_dict()
        self.assertEqual(expired["future.branch.candidate-B.status"], "expired")
        self.assertEqual(expired["future.branch.lkg-A.status"], "verified")
        self.assertEqual(
            expired["future.branch.candidate-B.expired_against_state_digest"],
            new_verified.digest(),
        )

    def test_matching_basis_keeps_branch_warm(self):
        state = State.from_mapping({"boot.slot": "A"})
        basis = state.digest()
        recorded = record_branch_set(
            state,
            [BranchRecord("candidate-B", "boot-slot-B", 0.8, 0.2, basis_state_digest=basis)],
        )
        unchanged = expire_stale_branches(recorded, current_verified_state_digest=basis).as_dict()
        self.assertEqual(unchanged["future.branch.candidate-B.status"], "warm")


if __name__ == "__main__":
    unittest.main()
