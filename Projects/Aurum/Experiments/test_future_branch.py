from __future__ import annotations

import unittest

from future_branch import (
    Disposition,
    FutureBranch,
    LookaheadMode,
    calibration_question_budget,
    disposition,
    human_confidence_feedback,
    lookahead_depth,
    lookahead_mode,
    rank_branches,
    should_ask_calibration,
)


class FutureBranchTests(unittest.TestCase):
    def branch(self, name: str, **changes) -> FutureBranch:
        values = {
            "name": name,
            "probability": 0.8,
            "impact": 1.0,
            "user_time_saved": 1.0,
            "preparation_leverage": 1.0,
            "cost": 1.0,
            "linearity": 0.5,
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

    def test_high_probability_linear_branch_goes_deeper(self):
        deep = self.branch("linear", probability=0.97, linearity=0.96)
        shallow = self.branch("forky", probability=0.55, linearity=0.3)
        self.assertGreater(lookahead_depth(deep), lookahead_depth(shallow))
        self.assertEqual(lookahead_depth(deep), 6)

    def test_very_high_linear_branch_prepares_to_boundary_when_resources_allow(self):
        branch = self.branch("hot-linear", probability=0.95, linearity=0.94)
        self.assertEqual(
            lookahead_mode(branch, resource_headroom=0.8),
            LookaheadMode.TO_BOUNDARY,
        )

    def test_same_branch_stays_shallow_when_resources_are_tight(self):
        branch = self.branch("hot-but-starved", probability=0.95, linearity=0.94)
        self.assertNotEqual(
            lookahead_mode(branch, resource_headroom=0.15),
            LookaheadMode.TO_BOUNDARY,
        )

    def test_question_budget_tracks_uncertainty_shape(self):
        self.assertEqual(calibration_question_budget([0.34, 0.33, 0.30]), 3)
        self.assertEqual(calibration_question_budget([0.52, 0.48]), 2)
        self.assertEqual(calibration_question_budget([0.92, 0.05, 0.03]), 1)

    def test_feedback_signals_expectedness_without_claiming_certainty(self):
        expected = self.branch("expected", probability=0.93)
        surprise = self.branch("surprise", probability=0.2)
        self.assertIn("warm", human_confidence_feedback(expected))
        self.assertIn("outside", human_confidence_feedback(surprise))

    def test_feedback_variants_mix_surface_language(self):
        branch = self.branch("expected", probability=0.93)
        self.assertNotEqual(
            human_confidence_feedback(branch, variant=0),
            human_confidence_feedback(branch, variant=1),
        )

    def test_early_training_asks_when_top_branches_are_close(self):
        self.assertTrue(
            should_ask_calibration(
                top_probability=0.74,
                runner_up_probability=0.66,
                wrong_branch_cost=0.5,
            )
        )

    def test_strong_clear_branch_does_not_interrupt_with_question(self):
        self.assertFalse(
            should_ask_calibration(
                top_probability=0.94,
                runner_up_probability=0.18,
                wrong_branch_cost=0.3,
            )
        )


if __name__ == "__main__":
    unittest.main()
