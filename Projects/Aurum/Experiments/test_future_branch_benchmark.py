from __future__ import annotations

import unittest

from future_branch_benchmark import CandidateFuture, benchmark_decision, benchmark_suite


class FutureBranchBenchmarkTests(unittest.TestCase):
    def futures(self):
        return [
            CandidateFuture("likely-next", 0.70, 5000, human_value=2.0),
            CandidateFuture("possible-alt", 0.20, 3000, human_value=1.0),
            CandidateFuture("unlikely", 0.10, 1000, human_value=1.0),
        ]

    def test_idle_compute_reduces_wait_when_actual_branch_was_prepared(self):
        result = benchmark_decision(
            self.futures(),
            actual="likely-next",
            idle_window_ms=2000,
        )
        self.assertEqual(result["reactive_wait_ms"], 5000)
        self.assertEqual(result["future_branch_wait_ms"], 3000)
        self.assertEqual(result["wait_saved_ms"], 2000)
        self.assertEqual(result["foreground_regression_ms"], 0)

    def test_enough_idle_time_can_make_likely_branch_instant(self):
        result = benchmark_decision(
            self.futures(),
            actual="likely-next",
            idle_window_ms=5000,
        )
        self.assertEqual(result["future_branch_wait_ms"], 0)
        self.assertEqual(result["wait_saved_fraction"], 1.0)

    def test_wrong_future_can_be_gross_waste_without_making_foreground_slower(self):
        result = benchmark_decision(
            self.futures(),
            actual="possible-alt",
            idle_window_ms=2000,
        )
        self.assertEqual(result["future_branch_wait_ms"], result["reactive_wait_ms"])
        self.assertEqual(result["wait_saved_ms"], 0)
        self.assertEqual(result["gross_nonactual_speculative_ms"], 2000)
        self.assertEqual(result["net_speculative_waste_ms"], 2000)
        self.assertEqual(result["foreground_regression_ms"], 0)

    def test_reuse_and_learning_reduce_net_waste_after_a_near_term_miss(self):
        futures = [
            CandidateFuture(
                "prepared-but-not-next",
                0.7,
                2000,
                human_value=2.0,
                reusable_fraction=0.5,
                learning_credit_ms=400,
                avoided_error_credit_ms=200,
            ),
            CandidateFuture("actual", 0.3, 1000, human_value=1.0),
        ]
        result = benchmark_decision(
            futures,
            actual="actual",
            idle_window_ms=2000,
        )
        self.assertEqual(result["gross_nonactual_speculative_ms"], 2000)
        self.assertEqual(result["reusable_nonactual_ms"], 1000)
        self.assertEqual(result["learning_credit_ms"], 400)
        self.assertEqual(result["avoided_error_credit_ms"], 200)
        self.assertEqual(result["net_speculative_waste_ms"], 400)
        self.assertGreater(result["long_horizon_value_fraction"], result["immediate_speculation_efficiency"])

    def test_zero_idle_capacity_matches_reactive_computing(self):
        result = benchmark_decision(
            self.futures(),
            actual="likely-next",
            idle_window_ms=0,
        )
        self.assertEqual(result["future_branch_wait_ms"], result["reactive_wait_ms"])
        self.assertEqual(result["speculative_work_ms"], 0)

    def test_suite_reports_total_human_wait_saved(self):
        report = benchmark_suite(
            [
                {
                    "futures": self.futures(),
                    "actual": "likely-next",
                    "idle_window_ms": 2000,
                },
                {
                    "futures": self.futures(),
                    "actual": "possible-alt",
                    "idle_window_ms": 2000,
                },
            ]
        )
        self.assertEqual(report["cases"], 2)
        self.assertEqual(report["reactive_wait_ms"], 8000)
        self.assertEqual(report["future_branch_wait_ms"], 6000)
        self.assertEqual(report["wait_saved_ms"], 2000)
        self.assertEqual(report["foreground_regression_ms"], 0)

    def test_speculation_never_mutates_active_or_lkg_state(self):
        result = benchmark_decision(
            self.futures(),
            actual="likely-next",
            idle_window_ms=1000,
        )
        self.assertFalse(result["active_state_mutation_allowed"])
        self.assertFalse(result["lkg_mutation_allowed"])


if __name__ == "__main__":
    unittest.main()
