from __future__ import annotations

import unittest

from future_branch_calibrator import CalibrationEvent, probability_adjustment, summarize


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

    def test_adjustment_strengthens_useful_hit_and_weakens_miss(self):
        self.assertGreater(
            probability_adjustment(prediction="exact", execution="complete"),
            1.0,
        )
        self.assertLess(
            probability_adjustment(prediction="miss", execution="miss"),
            1.0,
        )

    def test_empty_summary_is_defined(self):
        self.assertEqual(summarize([])["events"], 0)


if __name__ == "__main__":
    unittest.main()
