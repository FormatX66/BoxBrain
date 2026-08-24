import unittest

from surprise_budget import (
    FailureFamily,
    boundary_expansion_required,
    calibrated_leader_confidence,
    failure_family_coverage,
    surprise_reserve,
)


class SurpriseBudgetTests(unittest.TestCase):
    def test_keeps_unknown_reserve_even_before_surprises(self):
        self.assertEqual(surprise_reserve(unpredicted_failures=0, total_failures=0), 0.10)

    def test_repeated_unpredicted_failures_raise_reserve(self):
        low = surprise_reserve(unpredicted_failures=1, total_failures=5)
        high = surprise_reserve(unpredicted_failures=4, total_failures=5)
        self.assertGreater(high, low)
        self.assertLessEqual(high, 0.35)

    def test_surprise_reserve_reduces_leader_overconfidence(self):
        self.assertAlmostEqual(
            calibrated_leader_confidence(leader_probability=0.90, reserve=0.25),
            0.675,
        )

    def test_failure_family_gaps_force_expansion(self):
        coverage = failure_family_coverage({FailureFamily.TARGET_IDENTITY})
        self.assertFalse(coverage["coverage_complete"])
        self.assertTrue(coverage["unknown_branch_required"])
        self.assertTrue(
            boundary_expansion_required(
                reserve=0.10,
                missing_families=len(coverage["missing"]),
            )
        )

    def test_full_family_coverage_can_still_expand_for_surprise_mass(self):
        modeled = {
            FailureFamily.TARGET_IDENTITY,
            FailureFamily.ORCHESTRATION_TRIGGER,
            FailureFamily.ENVIRONMENT_SEMANTICS,
            FailureFamily.RUNNER_AVAILABILITY,
            FailureFamily.DEVICE_READINESS,
            FailureFamily.BOOT_PRESENTATION,
        }
        coverage = failure_family_coverage(modeled)
        self.assertTrue(coverage["coverage_complete"])
        self.assertTrue(boundary_expansion_required(reserve=0.20, missing_families=0))


if __name__ == "__main__":
    unittest.main()
