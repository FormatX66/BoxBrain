from __future__ import annotations

import unittest

from future_branch import Disposition, FutureBranch, disposition, rank_branches


class FutureBranchTests(unittest.TestCase):
    def branch(self, name: str, **changes) -> FutureBranch:
        values = {
            "name": name,
            "probability": 0.8,
            "impact": 1.0,
            "user_time_saved": 1.0,
            "preparation_leverage": 1.0,
            "cost": 1.0,
        }
        values.update(changes)
        return FutureBranch(**values)

    def test_likely_question_is_answered_now(self):
        item = self.branch("what-next", informational=True)
        self.assertEqual(disposition(item), Disposition.ANSWER_NOW)

    def test_safe_dependency_satisfied_action_executes_now(self):
        item = self.branch(
            "run-next-verification",
            safe_reversible_action=True,
            dependencies_satisfied=True,
        )
        self.assertEqual(disposition(item), Disposition.EXECUTE_NOW)

    def test_dependency_blocked_action_is_prepared(self):
        item = self.branch(
            "flash-after-artifact",
            safe_reversible_action=True,
            dependencies_satisfied=False,
        )
        self.assertEqual(disposition(item), Disposition.PREPARE_NOW)

    def test_real_boundary_waits_even_if_action_would_otherwise_execute(self):
        item = self.branch(
            "physical-disk-write",
            safe_reversible_action=True,
            dependencies_satisfied=True,
            destructive_boundary=True,
        )
        self.assertEqual(disposition(item), Disposition.WAIT_BOUNDARY)

    def test_field_is_not_binary_pass_fail(self):
        field = rank_branches(
            [
                self.branch("success-next-action", safe_reversible_action=True, dependencies_satisfied=True),
                self.branch("partial-result-question", informational=True, probability=0.7),
                self.branch("stalled-run", probability=0.6),
                self.branch("likely-failure", probability=0.5),
                self.branch("adjacent-opportunity", probability=0.4),
                self.branch("physical-boundary", probability=0.3, physical_boundary=True),
            ],
            limit=6,
        )
        names = {item["name"] for item in field}
        self.assertIn("partial-result-question", names)
        self.assertIn("stalled-run", names)
        self.assertIn("adjacent-opportunity", names)
        self.assertGreater(len(names), 2)


if __name__ == "__main__":
    unittest.main()
