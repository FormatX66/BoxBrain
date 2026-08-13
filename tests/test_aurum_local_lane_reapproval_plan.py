import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "installer"))

from plan_aurum_local_lane_reapproval import plan_reapproval


def inspection(drift):
    return {
        "schema_version": 1,
        "approval_current": not drift,
        "drift": list(drift),
    }


def evidence(current="abc", tested="abc", passed=True):
    return {
        "schema_version": 1,
        "current_commit": current,
        "tested_commit": tested,
        "tests_passed": passed,
    }


class LocalLaneReapprovalPlanTests(unittest.TestCase):
    def test_current_approval_needs_no_refresh(self):
        result = plan_reapproval(inspection([]), evidence(passed=False))
        self.assertEqual("already-approved", result["decision"])
        self.assertEqual(["approval-current"], result["reason_codes"])
        self.assertFalse(result["apply"])
        self.assertFalse(result["authorization_mutated"])

    def test_codelation_only_drift_with_matching_passing_evidence_is_eligible(self):
        result = plan_reapproval(inspection(["codelation_tree_sha256"]), evidence())
        self.assertEqual("refresh-eligible", result["decision"])
        self.assertEqual(
            ["codelation-only-drift", "matching-tested-commit"],
            result["reason_codes"],
        )

    def test_deployer_drift_requires_review(self):
        result = plan_reapproval(inspection(["deployer_sha256"]), evidence())
        self.assertEqual("review-required", result["decision"])
        self.assertIn("deployer-drift-requires-review", result["reason_codes"])

    def test_watcher_drift_requires_review(self):
        result = plan_reapproval(inspection(["watcher_sha256"]), evidence())
        self.assertEqual("review-required", result["decision"])
        self.assertIn("watcher-drift-requires-review", result["reason_codes"])

    def test_missing_test_confirmation_requires_review(self):
        result = plan_reapproval(
            inspection(["codelation_tree_sha256"]),
            evidence(passed=False),
        )
        self.assertEqual("review-required", result["decision"])
        self.assertIn("tests-not-confirmed-passing", result["reason_codes"])

    def test_mismatched_tested_commit_requires_review(self):
        result = plan_reapproval(
            inspection(["codelation_tree_sha256"]),
            evidence(current="new", tested="old"),
        )
        self.assertEqual("review-required", result["decision"])
        self.assertIn("tested-commit-does-not-match-current", result["reason_codes"])

    def test_unknown_drift_requires_review(self):
        result = plan_reapproval(inspection(["mystery_hash"]), evidence())
        self.assertEqual("review-required", result["decision"])
        self.assertIn("unknown-drift-component", result["reason_codes"])

    def test_output_is_deterministic_for_drift_order(self):
        a = plan_reapproval(
            inspection(["watcher_sha256", "deployer_sha256"]),
            evidence(),
        )
        b = plan_reapproval(
            inspection(["deployer_sha256", "watcher_sha256"]),
            evidence(),
        )
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
