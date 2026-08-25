from pathlib import Path
import unittest

from installer.future_branch_recovery import recovery_manifest


RECONCILER = Path(__file__).resolve().parents[1] / "reconcile-existing-aurum-gold-seed-on-pi.ps1"


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
        self.assertFalse(candidate["authorized"])
        self.assertFalse(payload["promotion_performed"])
        self.assertFalse(payload["invariants"]["candidate_direct_promotion_allowed"])

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
        self.assertFalse(candidate["authorized"])
        self.assertTrue(any(item["ref"] == "desired-state:previous" for item in candidate["evidence"]))

    def test_bbpi4_reconciler_persists_manifest_before_candidate_mutation(self):
        text = RECONCILER.read_text(encoding="utf-8")
        overlay_tests = text.index("aurum_overlay_tests=passed")
        rollback_snapshot = text.index('sudo -n cp -a "$INSTALL" "$ROLLBACK"')
        manifest_hook = text.index('future_branch_recovery.py"')
        quarantine_gate = text.index("AURUM_FUTURE_BRANCH_CANDIDATE_QUARANTINED")
        first_live_candidate_mutation = text.index('sudo -n install -d -o "$PI_USER" -g "$PI_USER" -m 700')
        candidate_file_install = text.index('sudo -n install -o "$PI_USER" -g "$PI_USER" -m 600')

        self.assertLess(overlay_tests, rollback_snapshot)
        self.assertLess(rollback_snapshot, manifest_hook)
        self.assertLess(manifest_hook, quarantine_gate)
        self.assertLess(quarantine_gate, first_live_candidate_mutation)
        self.assertLess(manifest_hook, candidate_file_install)
        self.assertIn("future_branch_manifest_phase=pre-mutation", text)
        self.assertIn("--desired-state", text)


if __name__ == "__main__":
    unittest.main()
