import unittest

from installer.future_branch_recovery import recovery_manifest


class FutureBranchRecoveryTests(unittest.TestCase):
    def test_verified_lkg_and_rollback_are_explicit_before_mutation(self):
        payload = recovery_manifest(
            candidate_state="staged-seed-B",
            lkg_state="gold-seed-A",
            rollback_target="/opt/boxbrain/rollback/codelation-123",
            candidate_tests_passed=True,
            current_seed_present=True,
        )

        by_id = {item["branch_id"]: item for item in payload["branches"]}
        self.assertFalse(payload["promotion_performed"])
        self.assertFalse(payload["invariants"]["lkg_destroy_allowed"])
        self.assertEqual(by_id["seed-lkg"]["status"], "verified")
        self.assertTrue(by_id["seed-lkg"]["is_last_known_good"])
        self.assertEqual(by_id["seed-rollback"]["rollback_target"], "/opt/boxbrain/rollback/codelation-123")
        self.assertEqual(by_id["seed-candidate"]["status"], "warm")
        self.assertTrue(by_id["seed-candidate"]["requires_authorization"])
        self.assertFalse(by_id["seed-candidate"]["authorized"])

    def test_failed_candidate_is_quarantined_not_promoted(self):
        payload = recovery_manifest(
            candidate_state="bad-seed-B",
            lkg_state="gold-seed-A",
            rollback_target="rollback-A",
            candidate_tests_passed=False,
            current_seed_present=True,
        )
        candidate = next(item for item in payload["branches"] if item["branch_id"] == "seed-candidate")
        self.assertEqual(candidate["status"], "quarantined")
        self.assertLess(candidate["confidence"], 0.5)
        self.assertFalse(candidate["evidence"][0]["supports"])

    def test_remote_desired_state_is_evidence_not_authority(self):
        payload = recovery_manifest(
            candidate_state="seed-B",
            lkg_state="seed-A",
            rollback_target="rollback-A",
            candidate_tests_passed=True,
            current_seed_present=True,
            desired_state="previous",
        )
        candidate = next(item for item in payload["branches"] if item["branch_id"] == "seed-candidate")
        self.assertEqual(payload["desired_state_constraint"], "previous")
        self.assertEqual(payload["decision_authority"], "BrainConnect/StateGuardian")
        self.assertFalse(payload["promotion_performed"])
        self.assertTrue(any(item["ref"] == "desired-state:previous" for item in candidate["evidence"]))


if __name__ == "__main__":
    unittest.main()
