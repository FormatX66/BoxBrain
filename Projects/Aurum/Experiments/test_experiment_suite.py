from __future__ import annotations

import unittest

from experiment_suite import (
    adaptive_kernel_plan,
    combined_trial,
    stateweave_restore,
    stateweave_snapshot,
    validate_recovery_request,
)


class StateWeaveTests(unittest.TestCase):
    def test_snapshot_is_deterministic(self) -> None:
        a = stateweave_snapshot({"b": 2, "a": 1})
        b = stateweave_snapshot({"a": 1, "b": 2})
        self.assertEqual(a, b)

    def test_tamper_is_refused(self) -> None:
        snapshot = stateweave_snapshot({"active": "A", "lkg": "A"})
        snapshot["state"]["active"] = "B"
        with self.assertRaises(ValueError):
            stateweave_restore(snapshot)


class AdaptiveKernelTests(unittest.TestCase):
    def test_pi_candidate_preserves_active_and_lkg(self) -> None:
        plan = adaptive_kernel_plan(
            {"arch": "aarch64", "cores": 4, "ram_mb": 4096, "devices": ["usb", "wifi"]},
            active_profile="arm64-gold",
            lkg_profile="arm64-gold",
        )
        self.assertEqual(plan["action"], "stage-candidate")
        self.assertEqual(plan["active_profile"], "arm64-gold")
        self.assertEqual(plan["lkg_profile"], "arm64-gold")
        self.assertFalse(plan["promotion_allowed"])

    def test_unknown_arch_holds(self) -> None:
        plan = adaptive_kernel_plan(
            {"arch": "mystery", "cores": 8, "ram_mb": 8192},
            active_profile="gold",
            lkg_profile="gold",
        )
        self.assertEqual(plan["action"], "hold")
        self.assertIsNone(plan["candidate"])


class CombinedExperimentTests(unittest.TestCase):
    def test_trial_binds_prechange_state_and_rollback(self) -> None:
        trial = combined_trial(
            {"arch": "x86_64", "cores": 8, "ram_mb": 16384},
            {"active_slot": "A", "lkg_slot": "A", "health": "green"},
            active_profile="x86-gold",
            lkg_profile="x86-gold",
        )
        restored = stateweave_restore(trial["before"])
        self.assertEqual(restored["lkg_slot"], "A")
        self.assertEqual(trial["rollback_target"], "x86-gold")
        self.assertFalse(trial["promotion_allowed"])


class RecoveryControlTests(unittest.TestCase):
    def test_unsigned_request_is_refused(self) -> None:
        with self.assertRaises(PermissionError):
            validate_recovery_request(
                {"schema": "aurum-recovery-request-v0", "target": "last-known-good"},
                signature_verified=False,
                trusted_refs=set(),
            )

    def test_untrusted_specific_ref_is_refused(self) -> None:
        with self.assertRaises(PermissionError):
            validate_recovery_request(
                {"schema": "aurum-recovery-request-v0", "target": "specific", "ref": "bad"},
                signature_verified=True,
                trusted_refs={"good"},
            )

    def test_verified_lkg_request_preserves_lkg(self) -> None:
        result = validate_recovery_request(
            {"schema": "aurum-recovery-request-v0", "target": "last-known-good"},
            signature_verified=True,
            trusted_refs=set(),
        )
        self.assertTrue(result["accepted"])
        self.assertTrue(result["preserve_lkg"])
        self.assertFalse(result["promotion_allowed"])


if __name__ == "__main__":
    unittest.main()
