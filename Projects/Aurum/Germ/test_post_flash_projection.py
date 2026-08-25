from __future__ import annotations

import unittest

from post_flash_projection import (
    matching_ready_to_boot,
    project_post_flash_state,
    recovery_materially_changed,
)


class PostFlashProjectionTests(unittest.TestCase):
    def release(self):
        return {
            "schema": "aurum-tinyseed-handoff-v1",
            "state": "READY_TO_FLASH",
            "source_commit": "a" * 40,
            "artifacts": {
                "x86": {
                    "name": "Aurum-TinySeed-amd64.iso",
                    "sha256": "d" * 64,
                }
            },
        }

    def receipt(self):
        return {
            "schema": "aurum-tinyseed-flash-request-receipt-v1",
            "state": "READY_TO_BOOT",
            "request_id": "flash-once",
            "source_commit": "a" * 40,
            "image_sha256": "d" * 64,
            "raw_readback_verified": True,
            "write_authority_consumed": True,
            "observed_at_utc": "2026-08-25T15:26:09Z",
            "device": {
                "disk_number": 1,
                "model": "USB Test",
                "size_bytes": 64_000_000_000,
                "serial_sha256": "1" * 64,
            },
        }

    def recovery(self, observed_at: str = "2026-08-25T15:30:00Z"):
        return {
            "schema": "aurum.hopper.recovery-path-probe.v2",
            "observed_at": observed_at,
            "runner_host": "runner-a",
            "boxbrain_address": None,
            "hopper_candidate": None,
            "hopper_resolved": False,
            "remote_repair": "unavailable",
            "terminal_reason": "boxbrain-unreachable",
            "read_only_probe": True,
            "mutation_if_authorized": "none-read-only-refresh",
        }

    def test_matching_readback_receipt_advances_to_boot_not_reflash(self):
        self.assertTrue(matching_ready_to_boot(self.release(), self.receipt()))
        projected = project_post_flash_state(self.release(), self.receipt(), self.recovery())
        self.assertEqual(projected["preflight_state"], "READY_TO_BOOT")
        self.assertEqual(projected["next_gate"], "physical-hopper-boot-proof")
        self.assertTrue(projected["physical_flash_proven"])
        self.assertFalse(projected["physical_boot_proven"])
        self.assertFalse(projected["guardian_forced_rollback_proven"])
        self.assertFalse(projected["write_authority"])
        self.assertFalse(projected["destructive_action_allowed"])

    def test_release_or_hash_mismatch_cannot_activate_post_flash_state(self):
        receipt = self.receipt()
        receipt["source_commit"] = "b" * 40
        self.assertFalse(matching_ready_to_boot(self.release(), receipt))
        receipt = self.receipt()
        receipt["image_sha256"] = "e" * 64
        self.assertFalse(matching_ready_to_boot(self.release(), receipt))

    def test_unverified_readback_cannot_activate_post_flash_state(self):
        receipt = self.receipt()
        receipt["raw_readback_verified"] = False
        self.assertFalse(matching_ready_to_boot(self.release(), receipt))

    def test_timestamp_and_runner_only_refresh_is_not_material_change(self):
        old = self.recovery("2026-08-25T15:30:00Z")
        new = self.recovery("2026-08-25T16:30:00Z")
        new["runner_host"] = "runner-b"
        self.assertFalse(recovery_materially_changed(old, new))

    def test_recovery_result_change_remains_material(self):
        old = self.recovery()
        new = self.recovery("2026-08-25T16:30:00Z")
        new["terminal_reason"] = "authorized-recovery-unavailable"
        self.assertTrue(recovery_materially_changed(old, new))

    def test_projection_never_turns_consumed_authority_back_on(self):
        projected = project_post_flash_state(self.release(), self.receipt())
        self.assertFalse(projected["write_authority"])
        self.assertFalse(projected["destructive_action_allowed"])
        self.assertTrue(projected["flash_receipt"]["write_authority_consumed"])


if __name__ == "__main__":
    unittest.main()
