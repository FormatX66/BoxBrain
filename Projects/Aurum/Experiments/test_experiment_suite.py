from __future__ import annotations

import unittest

from experiment_suite import (
    RECOVERY_REQUEST_SCHEMA,
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
    NOW = 1_800_000_000

    def request(self, target: str = "last-known-good", **changes) -> dict:
        value = {
            "schema": RECOVERY_REQUEST_SCHEMA,
            "target": target,
            "nonce": "recovery-nonce-0001",
            "issued_at_unix": self.NOW - 30,
            "expires_at_unix": self.NOW + 120,
        }
        value.update(changes)
        return value

    def validate(self, request: dict, **changes):
        values = {
            "signature_verified": True,
            "trusted_refs": set(),
            "now_unix": self.NOW,
            "seen_nonces": set(),
        }
        values.update(changes)
        return validate_recovery_request(request, **values)

    def test_unsigned_request_is_refused(self) -> None:
        with self.assertRaises(PermissionError):
            self.validate(self.request(), signature_verified=False)

    def test_untrusted_specific_ref_is_refused(self) -> None:
        with self.assertRaises(PermissionError):
            self.validate(
                self.request("specific", ref="bad"),
                trusted_refs={"good"},
            )

    def test_verified_lkg_request_preserves_lkg(self) -> None:
        result = self.validate(self.request())
        self.assertTrue(result["accepted"])
        self.assertTrue(result["freshness_checked"])
        self.assertTrue(result["replay_checked"])
        self.assertTrue(result["preserve_lkg"])
        self.assertFalse(result["promotion_allowed"])

    def test_expired_request_is_refused(self) -> None:
        with self.assertRaises(PermissionError):
            self.validate(
                self.request(
                    issued_at_unix=self.NOW - 400,
                    expires_at_unix=self.NOW - 1,
                )
            )

    def test_future_dated_request_is_refused(self) -> None:
        with self.assertRaises(PermissionError):
            self.validate(
                self.request(
                    issued_at_unix=self.NOW + 31,
                    expires_at_unix=self.NOW + 60,
                )
            )

    def test_replayed_nonce_is_refused(self) -> None:
        request = self.request(nonce="already-seen")
        with self.assertRaises(PermissionError):
            self.validate(request, seen_nonces={"already-seen"})

    def test_overlong_validity_window_is_refused(self) -> None:
        with self.assertRaises(PermissionError):
            self.validate(
                self.request(
                    issued_at_unix=self.NOW - 10,
                    expires_at_unix=self.NOW + 301,
                )
            )

    def test_legacy_schema_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.validate(self.request(schema="aurum-recovery-request-v0"))


if __name__ == "__main__":
    unittest.main()
