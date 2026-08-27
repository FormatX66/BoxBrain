from __future__ import annotations

import unittest

from future_branch_calibrator import (
    CalibrationEvent,
    branch_priority,
    calibration_question_budget,
    feedback_cue_mode,
    prediction_debt,
    probability_adjustment,
    speculation_decision,
    summarize,
)


class FutureBranchCalibrationTests(unittest.TestCase):
    def test_prediction_without_execution_is_not_full_hit(self):
        event = CalibrationEvent(
            family="predicted-followup-not-executed",
            prediction="exact",
            execution="miss",
        )
        self.assertEqual(event.prediction_value, 1.0)
        self.assertEqual(event.execution_value, 0.0)
        self.assertEqual(event.useful_hit_value, 0.0)

    def test_exact_prepared_branch_gets_partial_execution_credit(self):
        event = CalibrationEvent(
            family="dependency-blocked-prepared",
            prediction="exact",
            execution="prepared",
            user_turns_avoided=1,
            estimated_wait_seconds_saved=20,
        )
        summary = summarize([event])
        self.assertEqual(summary["prediction_accuracy"], 1.0)
        self.assertEqual(summary["execution_completeness"], 0.75)
        self.assertEqual(summary["useful_hit_rate"], 0.75)
        self.assertEqual(summary["user_turns_avoided"], 1)

    def test_boundary_correct_is_not_penalized(self):
        event = CalibrationEvent(
            family="physical-write-boundary",
            prediction="exact",
            execution="boundary-correct",
        )
        self.assertEqual(event.useful_hit_value, 1.0)

    def test_surface_only_typo_match_never_counts_as_prediction_win(self):
        event = CalibrationEvent(
            family="surface-form-only",
            prediction="exact",
            execution="complete",
            prediction_basis="surface-only",
        )
        self.assertEqual(event.prediction_value, 0.0)
        self.assertEqual(event.useful_hit_value, 0.0)
        self.assertLess(
            probability_adjustment(
                prediction="exact", execution="complete", prediction_basis="surface-only"
            ),
            1.0,
        )

    def test_adjustment_strengthens_useful_hit_and_weakens_miss(self):
        self.assertGreater(
            probability_adjustment(prediction="exact", execution="complete"),
            1.0,
        )
        self.assertLess(
            probability_adjustment(prediction="miss", execution="miss"),
            1.0,
        )

    def test_immediate_wait_and_compounding_value_are_separate(self):
        event = CalibrationEvent(
            family="reusable-partial-state",
            prediction="partial",
            execution="prepared",
            estimated_wait_seconds_saved=12,
            reusable_partial_state_units=2,
            cached_artifact_units=1,
            calibration_learning_units=0.5,
            avoided_future_error_units=1.5,
            branch_shared_work_units=1,
            gross_speculative_work_units=8,
        )
        summary = summarize([event])
        self.assertEqual(summary["estimated_wait_seconds_saved"], 12)
        self.assertEqual(summary["compounding_value_units"], 6)
        self.assertEqual(summary["gross_speculative_work_units"], 8)
        self.assertEqual(summary["net_speculative_waste_units"], 2)

    def test_durable_value_can_make_net_waste_zero_without_creating_prediction_credit(self):
        event = CalibrationEvent(
            family="cooled-branch-shared-artifact",
            prediction="miss",
            execution="partial",
            reusable_partial_state_units=2,
            branch_shared_work_units=2,
            gross_speculative_work_units=3,
        )
        self.assertEqual(event.useful_hit_value, 0.0)
        self.assertEqual(event.compounding_value_units, 4)
        self.assertEqual(event.net_speculative_waste_units, 0.0)

    def test_clear_safe_cheap_linear_path_asks_zero_questions(self):
        plan = calibration_question_budget(
            [0.82, 0.12, 0.06], path_clear=True, safe=True, cheap=True, linear=True
        )
        self.assertEqual(plan["max_questions"], 0)
        self.assertEqual(plan["goal"], "proceed")

    def test_dominant_branch_allows_at_most_one_discriminating_question(self):
        plan = calibration_question_budget([0.74, 0.18, 0.08])
        self.assertEqual(plan["max_questions"], 1)
        self.assertEqual(plan["goal"], "confirm-or-disprove-leader")

    def test_two_competitive_branches_allow_about_two_questions(self):
        plan = calibration_question_budget([0.52, 0.44, 0.04])
        self.assertEqual(plan["max_questions"], 2)
        self.assertEqual(plan["shape"], "two-competitive-branches")

    def test_clustered_plausible_branches_allow_up_to_three_questions(self):
        plan = calibration_question_budget([0.34, 0.33, 0.28, 0.05])
        self.assertEqual(plan["max_questions"], 3)
        self.assertEqual(plan["shape"], "several-plausible-branches")

    def test_priority_and_prediction_debt_reward_high_value_unprepared_work(self):
        priority = branch_priority(
            probability=0.8,
            impact=2,
            user_time_saved=30,
            preparation_leverage=3,
            cost=4,
        )
        self.assertGreater(priority, 0)
        self.assertEqual(
            prediction_debt(
                probability=0.8,
                impact=2,
                user_time_saved=30,
                preparation_leverage=3,
                cost=4,
                prepared_fraction=0,
            ),
            priority,
        )
        self.assertEqual(
            prediction_debt(
                probability=0.8,
                impact=2,
                user_time_saved=30,
                preparation_leverage=3,
                cost=4,
                prepared_fraction=1,
            ),
            0,
        )

    def test_speculation_requires_positive_net_value_and_hard_gates(self):
        profitable = speculation_decision(
            expected_long_horizon_benefit=10,
            compute_cost=1,
            energy_cost=1,
            ram_cost=1,
            storage_cost=1,
            network_cost=1,
            privacy_cost=0,
            foreground_cost=1,
        )
        self.assertTrue(profitable["continue"])
        self.assertGreater(profitable["net_expected_value"], 0)

        expensive = speculation_decision(expected_long_horizon_benefit=2, compute_cost=3)
        self.assertFalse(expensive["continue"])

        foreground_blocked = speculation_decision(
            expected_long_horizon_benefit=100,
            compute_cost=1,
            foreground_headroom_healthy=False,
        )
        self.assertFalse(foreground_blocked["continue"])
        self.assertFalse(foreground_blocked["hard_gate_passed"])

    def test_feedback_cues_deliberately_include_uncued_meaningful_turns(self):
        modes = [feedback_cue_mode(index) for index in range(7)]
        self.assertIn("none", modes)
        self.assertIn("brief", modes)
        self.assertIn("detailed", modes)
        self.assertEqual(feedback_cue_mode(3, meaningful_turn=False), "none")

    def test_empty_summary_is_defined(self):
        summary = summarize([])
        self.assertEqual(summary["events"], 0)
        self.assertEqual(summary["compounding_value_units"], 0.0)
        self.assertEqual(summary["net_speculative_waste_units"], 0.0)


if __name__ == "__main__":
    unittest.main()
