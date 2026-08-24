from __future__ import annotations

import unittest

from physical_handoff_preflight import evaluate_physical_preflight


class PhysicalHandoffPreflightTests(unittest.TestCase):
    def release(self, state: str = "READY_TO_FLASH") -> dict:
        return {
            "state": state,
            "source_commit": "abc123",
            "artifacts": {"x86": {"name": "Aurum-TinySeed-amd64.iso", "sha256": "deadbeef"}},
            "gates": {"physical_boot": "pending", "guardian_forced_rollback": "pending"},
        }

    def discovery(self, *, state: str, eligible: int) -> dict:
        return {
            "schema": "aurum-read-only-usb-discovery-v1",
            "request_id": "test-request",
            "write_authority": False,
            "eligible_count": eligible,
            "selection_state": state,
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
        )
        self.assertEqual(result["preflight_state"], "READY_FOR_GUARDED_FLASH_PREFLIGHT")
        self.assertFalse(result["write_authority"])
        self.assertFalse(result["destructive_action_allowed"])

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


if __name__ == "__main__":
    unittest.main()
