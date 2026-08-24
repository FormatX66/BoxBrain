from __future__ import annotations

from datetime import datetime, timezone
import unittest

from physical_handoff_preflight import evaluate_physical_preflight


class PhysicalHandoffPreflightTests(unittest.TestCase):
    def release(self, state: str = "READY_TO_FLASH") -> dict:
        return {
            "schema": "aurum-tinyseed-handoff-v1",
            "state": state,
            "source_commit": "a" * 40,
            "artifacts": {"x86": {"name": "Aurum-TinySeed-amd64.iso", "sha256": "d" * 64}},
            "gates": {
                "x86_build": "passed",
                "x86_uefi_boot_smoke": "passed",
                "x86_bios_boot_smoke": "passed",
                "x86_boot_proof_marker": "passed",
                "published_artifacts": "passed",
                "combined_hash_reverification": "passed",
                "physical_boot": "pending",
                "guardian_forced_rollback": "pending",
            },
        }

    def discovery(self, *, state: str, eligible: int) -> dict:
        devices = []
        for index in range(eligible):
            devices.append(
                {
                    "disk_number": index + 1,
                    "model": f"USB Test {index + 1}",
                    "size_bytes": 64_000_000_000,
                    "serial_sha256": f"{index + 1:064x}",
                    "is_boot": False,
                    "is_system": False,
                    "is_read_only": False,
                    "protected": False,
                    "eligible_for_preflight_only": True,
                    "refusal_reasons": [],
                }
            )
        return {
            "schema": "aurum-read-only-usb-discovery-v1",
            "request_id": "test-request",
            "release_source_commit": "a" * 40,
            "release_request_match": True,
            "write_authority": False,
            "eligible_count": eligible,
            "selection_state": state,
            "devices": devices,
        }

    def request(self, *, expires: str = "2026-08-24T14:00:00Z") -> dict:
        return {
            "schema": "aurum-tinyseed-flash-request-v1",
            "state": "AUTHORIZED_ONCE",
            "request_id": "flash-once",
            "write_authority": True,
            "confirmation": "FLASH_TINY_SEED_TEST_USB",
            "expires_at_utc": expires,
            "seed_sha": "a" * 40,
            "image_sha256": "d" * 64,
            "discovery_request_id": "test-request",
        }

    def now(self) -> datetime:
        return datetime(2026, 8, 24, 13, 0, tzinfo=timezone.utc)

    def recovery(self, *, remote_repair: str = "unavailable", observed_at: str = "2026-08-24T12:55:00Z") -> dict:
        return {
            "schema": "aurum.hopper.recovery-path-probe.v2",
            "observed_at": observed_at,
            "remote_repair": remote_repair,
            "terminal_reason": "boxbrain-unreachable",
        }

    def test_ready_release_without_receipt_waits_for_read_only_discovery(self):
        result = evaluate_physical_preflight(self.release(), None)
        self.assertEqual(result["preflight_state"], "WAIT_USB_DISCOVERY")
        self.assertFalse(result["write_authority"])
        self.assertFalse(result["destructive_action_allowed"])

    def test_unique_candidate_becomes_guarded_preflight_not_write_authority(self):
        result = evaluate_physical_preflight(
            self.release(),
            self.discovery(state="UNIQUE_SAFE_TO_PREFLIGHT_ONLY", eligible=1),
            preexecution_recovery=self.recovery(),
            now_utc=self.now(),
        )
        self.assertEqual(result["preflight_state"], "READY_FOR_GUARDED_FLASH_PREFLIGHT")
        self.assertEqual(result["state"], result["preflight_state"])
        self.assertEqual(result["release"]["source_commit"], "a" * 40)
        self.assertEqual(result["usb_discovery"]["candidate"]["model"], "USB Test 1")
        self.assertFalse(result["write_authority"])
        self.assertFalse(result["destructive_action_allowed"])

    def test_unique_candidate_without_terminal_recovery_receipt_waits(self):
        result = evaluate_physical_preflight(
            self.release(),
            self.discovery(state="UNIQUE_SAFE_TO_PREFLIGHT_ONLY", eligible=1),
            now_utc=self.now(),
        )
        self.assertEqual(result["preflight_state"], "WAIT_HOPPER_PREEXECUTION_RECOVERY")
        self.assertFalse(result["preexecution_recovery"]["manual_handoff_released"])

    def test_completed_remote_repair_suppresses_manual_flash_escalation(self):
        result = evaluate_physical_preflight(
            self.release(),
            self.discovery(state="UNIQUE_SAFE_TO_PREFLIGHT_ONLY", eligible=1),
            preexecution_recovery=self.recovery(remote_repair="completed"),
            now_utc=self.now(),
        )
        self.assertEqual(result["preflight_state"], "WAIT_HOPPER_HEALTH_REREAD")
        self.assertFalse(result["preexecution_recovery"]["manual_handoff_released"])

    def test_stale_terminal_recovery_receipt_cannot_release_manual_handoff(self):
        result = evaluate_physical_preflight(
            self.release(),
            self.discovery(state="UNIQUE_SAFE_TO_PREFLIGHT_ONLY", eligible=1),
            preexecution_recovery=self.recovery(observed_at="2026-08-24T11:00:00Z"),
            now_utc=self.now(),
        )
        self.assertEqual(result["preflight_state"], "WAIT_HOPPER_PREEXECUTION_RECOVERY")
        self.assertFalse(result["preexecution_recovery"]["manual_handoff_released"])

    def test_multiple_candidates_wait_for_selection(self):
        result = evaluate_physical_preflight(
            self.release(),
            self.discovery(state="AMBIGUOUS_MULTIPLE_ELIGIBLE", eligible=2),
        )
        self.assertEqual(result["preflight_state"], "WAIT_USB_SELECTION")

    def test_no_candidate_waits_for_media(self):
        result = evaluate_physical_preflight(
            self.release(),
            self.discovery(state="NO_ELIGIBLE_USB", eligible=0),
        )
        self.assertEqual(result["preflight_state"], "WAIT_USB_MEDIA")

    def test_unready_release_never_advances_to_media(self):
        result = evaluate_physical_preflight(
            self.release(state="BUILDING"),
            self.discovery(state="UNIQUE_SAFE_TO_PREFLIGHT_ONLY", eligible=1),
        )
        self.assertEqual(result["preflight_state"], "WAIT_RELEASE")

    def test_discovery_cannot_smuggle_write_authority(self):
        discovery = self.discovery(state="UNIQUE_SAFE_TO_PREFLIGHT_ONLY", eligible=1)
        discovery["write_authority"] = True
        result = evaluate_physical_preflight(self.release(), discovery)
        self.assertEqual(result["preflight_state"], "REFUSE_DISCOVERY_AUTHORITY")
        self.assertFalse(result["write_authority"])

    def test_discovery_count_or_selection_contradiction_is_refused(self):
        discovery = self.discovery(state="UNIQUE_SAFE_TO_PREFLIGHT_ONLY", eligible=1)
        discovery["eligible_count"] = 2
        result = evaluate_physical_preflight(self.release(), discovery)
        self.assertEqual(result["preflight_state"], "REFUSE_DISCOVERY_CONTRADICTION")
        self.assertFalse(result["destructive_action_allowed"])

    def test_candidate_with_unsafe_live_flags_is_refused(self):
        discovery = self.discovery(state="UNIQUE_SAFE_TO_PREFLIGHT_ONLY", eligible=1)
        discovery["devices"][0]["is_system"] = True
        result = evaluate_physical_preflight(self.release(), discovery)
        self.assertEqual(result["preflight_state"], "REFUSE_USB_CANDIDATE")
        self.assertFalse(result["destructive_action_allowed"])

    def test_missing_discovery_request_id_is_refused(self):
        discovery = self.discovery(state="UNIQUE_SAFE_TO_PREFLIGHT_ONLY", eligible=1)
        discovery["request_id"] = None
        result = evaluate_physical_preflight(self.release(), discovery)
        self.assertEqual(result["preflight_state"], "REFUSE_DISCOVERY_CONTRADICTION")

    def test_discovery_for_a_different_release_is_refused(self):
        discovery = self.discovery(state="UNIQUE_SAFE_TO_PREFLIGHT_ONLY", eligible=1)
        discovery["release_source_commit"] = "different"
        discovery["release_request_match"] = False
        result = evaluate_physical_preflight(self.release(), discovery)
        self.assertEqual(result["preflight_state"], "REFUSE_DISCOVERY_RELEASE")
        self.assertFalse(result["destructive_action_allowed"])

    def test_expired_one_shot_authorization_returns_to_human_boundary(self):
        result = evaluate_physical_preflight(
            self.release(),
            self.discovery(state="UNIQUE_SAFE_TO_PREFLIGHT_ONLY", eligible=1),
            self.request(expires="2026-08-24T12:20:00Z"),
            self.recovery(),
            now_utc=self.now(),
        )
        self.assertEqual(result["authorization"]["authorization_state"], "EXPIRED")
        self.assertEqual(result["preflight_state"], "READY_FOR_GUARDED_FLASH_PREFLIGHT")
        self.assertFalse(result["write_authority"])
        self.assertFalse(result["destructive_action_allowed"])

    def test_valid_one_shot_authorization_still_requires_live_reproof(self):
        result = evaluate_physical_preflight(
            self.release(),
            self.discovery(state="UNIQUE_SAFE_TO_PREFLIGHT_ONLY", eligible=1),
            self.request(),
            self.recovery(),
            now_utc=self.now(),
        )
        self.assertEqual(
            result["authorization"]["authorization_state"],
            "VALID_ONE_SHOT_PENDING_LIVE_REPROOF",
        )
        self.assertEqual(result["preflight_state"], "AUTHORIZED_ONE_SHOT_PENDING_LIVE_REPROOF")
        self.assertFalse(result["write_authority"])
        self.assertFalse(result["destructive_action_allowed"])

    def test_mismatched_release_or_discovery_refuses_authorization(self):
        request = self.request()
        request["seed_sha"] = "different"
        result = evaluate_physical_preflight(
            self.release(),
            self.discovery(state="UNIQUE_SAFE_TO_PREFLIGHT_ONLY", eligible=1),
            request,
            self.recovery(),
            now_utc=self.now(),
        )
        self.assertEqual(result["authorization"]["authorization_state"], "REFUSE_PROVENANCE_MISMATCH")
        self.assertEqual(result["preflight_state"], "REFUSE_FLASH_AUTHORIZATION")
        self.assertFalse(result["destructive_action_allowed"])


if __name__ == "__main__":
    unittest.main()
