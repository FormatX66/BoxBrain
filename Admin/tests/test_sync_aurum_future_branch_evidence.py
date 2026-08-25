"""Tests for canonical Aurum Future Branch evidence projection."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from Admin.sync_aurum_future_branch_evidence import (
    FutureBranchEvidenceError,
    sync_future_branch_evidence,
)


class AurumFutureBranchEvidenceSyncTests(unittest.TestCase):
    def write_json(self, root: Path, relative: str, value: dict) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def handoff(self) -> dict:
        return {
            "schema": "aurum-tinyseed-handoff-v1",
            "source_commit": "a" * 40,
            "state": "READY_TO_FLASH",
            "artifacts": {
                "x86": {
                    "name": "Aurum-TinySeed-amd64.iso",
                    "sha256": "b" * 64,
                }
            },
        }

    def preflight(self, *, source_commit: str | None = None) -> dict:
        return {
            "schema": "aurum-tinyseed-physical-preflight-v2",
            "release_source_commit": source_commit or "a" * 40,
            "state": "READY_FOR_GUARDED_FLASH_PREFLIGHT",
            "next_gate": "explicit-guarded-flash-authorization",
            "write_authority": False,
            "destructive_action_allowed": False,
            "destructive_action_performed": False,
            "eligible_count": 1,
            "usb_candidate": {
                "disk_number": 1,
                "model": "USB Test",
                "size_bytes": 64000000000,
                "serial_sha256": "c" * 64,
                "is_boot": False,
                "is_system": False,
                "is_read_only": False,
                "protected": False,
                "eligible_for_preflight_only": True,
            },
            "preexecution_recovery": {
                "terminal_receipt_present": True,
                "manual_handoff_released": True,
                "remote_repair": "unavailable",
                "terminal_reason": "boxbrain-unreachable",
                "observed_at": "2026-08-24T21:09:24Z",
            },
        }

    def flash_receipt(self, *, source_commit: str | None = None) -> dict:
        return {
            "schema": "aurum-tinyseed-flash-request-receipt-v1",
            "state": "READY_TO_BOOT",
            "request_id": "test-flash",
            "source_commit": source_commit or "a" * 40,
            "image_sha256": "b" * 64,
            "device": {
                "disk_number": 1,
                "model": "USB Test",
                "size_bytes": 64000000000,
                "serial_sha256": "c" * 64,
            },
            "raw_readback_verified": True,
            "write_authority_consumed": True,
            "observed_at_utc": "2026-08-24T22:00:00Z",
        }

    def live_branch(self) -> dict:
        return {
            "schema": "aurum-future-branch-state-test",
            "current_program": "stale release",
            "canonical_evidence": {"release": {"source_commit": "old"}},
            "likely_user_inputs": [
                {
                    "rank": 1,
                    "input_family": "explicit-guarded-flash-authorization",
                    "prepared_response": "bind old-release-now",
                    "action_if_safe": "write old release",
                },
                {
                    "rank": 2,
                    "input_family": "status-or-so",
                    "prepared_response": "old status",
                    "action_if_safe": "old status action",
                },
                {
                    "rank": 3,
                    "input_family": "generic-prompt-intent-expansion",
                    "prepared_response": "old generic",
                    "action_if_safe": "old generic action",
                },
            ],
            "likely_machine_outcomes": [
                {
                    "rank": 1,
                    "state": "stale-authority-first",
                    "prepared": ["old"],
                    "next": "old",
                },
                {"rank": 2, "state": "keep-second"},
            ],
        }

    def input_family(self, branch: dict, family: str) -> dict:
        return next(
            item
            for item in branch.get("likely_user_inputs", [])
            if item.get("input_family") == family
        )

    def test_stale_branch_evidence_is_synchronized_without_granting_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.write_json(root, "Projects/Aurum/Release/latest-tinyseed-handoff.json", self.handoff())
            self.write_json(root, "Projects/Aurum/Recovery/latest-tinyseed-physical-preflight.json", self.preflight())
            branch_path = self.write_json(
                root,
                "Projects/Aurum/future-branches.json",
                {
                    "schema": "aurum-future-branch-state-test",
                    "current_program": "stale release",
                    "canonical_evidence": {"release": {"source_commit": "old"}},
                    "likely_machine_outcomes": [],
                },
            )

            result = sync_future_branch_evidence(root)
            branch = json.loads(branch_path.read_text(encoding="utf-8"))
            evidence = branch["canonical_evidence"]

            self.assertTrue(result["changed"])
            self.assertEqual(evidence["release"]["source_commit"], "a" * 40)
            self.assertEqual(evidence["release"]["x86_sha256"], "b" * 64)
            self.assertEqual(evidence["physical_preflight"]["state"], "READY_FOR_GUARDED_FLASH_PREFLIGHT")
            self.assertTrue(evidence["physical_preflight"]["matches_current_release"])
            self.assertFalse(evidence["physical_preflight"]["write_authority"])
            self.assertFalse(evidence["physical_preflight"]["destructive_action_allowed"])
            self.assertFalse(evidence["physical_preflight"]["destructive_action_performed"])
            self.assertEqual(evidence["preexecution_recovery"]["terminal_reason"], "boxbrain-unreachable")
            self.assertTrue(evidence["preexecution_recovery"]["manual_handoff_released"])
            self.assertFalse(evidence["flash_receipt"]["present"])
            self.assertIn("explicit-guarded-flash-authorization", branch["current_program"])
            self.assertEqual(branch["likely_machine_outcomes"], [])
            self.assertTrue(branch["live_controls"]["flash_authorization_eligible"])

    def test_waiting_recovery_rewrites_stale_flash_prescription_and_top_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.write_json(root, "Projects/Aurum/Release/latest-tinyseed-handoff.json", self.handoff())
            preflight = self.preflight()
            preflight["state"] = "WAIT_HOPPER_PREEXECUTION_RECOVERY"
            preflight["next_gate"] = "fresh-terminal-hopper-preexecution-recovery-receipt"
            preflight["preexecution_recovery"]["manual_handoff_released"] = False
            self.write_json(root, "Projects/Aurum/Recovery/latest-tinyseed-physical-preflight.json", preflight)
            branch_path = self.write_json(root, "Projects/Aurum/future-branches.json", self.live_branch())

            sync_future_branch_evidence(root)
            branch = json.loads(branch_path.read_text(encoding="utf-8"))
            authorization = self.input_family(branch, "explicit-guarded-flash-authorization")
            status = self.input_family(branch, "status-or-so")
            generic = self.input_family(branch, "generic-prompt-intent-expansion")

            self.assertFalse(branch["live_controls"]["flash_authorization_eligible"])
            self.assertEqual(branch["live_controls"]["preflight_state"], "WAIT_HOPPER_PREEXECUTION_RECOVERY")
            self.assertIn("WAIT_HOPPER_PREEXECUTION_RECOVERY", authorization["prepared_response"])
            self.assertIn("fresh-terminal-hopper-preexecution-recovery-receipt", authorization["action_if_safe"])
            self.assertNotIn("old-release-now", authorization["prepared_response"])
            self.assertIn("WAIT_HOPPER_PREEXECUTION_RECOVERY", status["prepared_response"])
            self.assertIn("fresh-terminal-hopper-preexecution-recovery-receipt", generic["action_if_safe"])
            self.assertEqual(
                branch["likely_machine_outcomes"][0]["state"],
                "fresh-terminal-hopper-preexecution-recovery-resolves",
            )
            self.assertEqual(branch["likely_machine_outcomes"][1], {"rank": 2, "state": "keep-second"})

    def test_ready_preflight_rewrites_authorization_to_exact_current_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.write_json(root, "Projects/Aurum/Release/latest-tinyseed-handoff.json", self.handoff())
            self.write_json(root, "Projects/Aurum/Recovery/latest-tinyseed-physical-preflight.json", self.preflight())
            branch_path = self.write_json(root, "Projects/Aurum/future-branches.json", self.live_branch())

            sync_future_branch_evidence(root)
            branch = json.loads(branch_path.read_text(encoding="utf-8"))
            authorization = self.input_family(branch, "explicit-guarded-flash-authorization")

            self.assertTrue(branch["live_controls"]["flash_authorization_eligible"])
            self.assertIn("a" * 40, authorization["prepared_response"])
            self.assertIn("Fresh one-shot authority", authorization["prepared_response"])
            self.assertIn("full raw readback", authorization["action_if_safe"])
            self.assertEqual(
                branch["likely_machine_outcomes"][0]["state"],
                "fresh-authority-triggers-live-reproof-and-guarded-preflight",
            )

    def test_stale_flash_receipt_is_projected_but_cannot_block_current_release_flash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.write_json(root, "Projects/Aurum/Release/latest-tinyseed-handoff.json", self.handoff())
            self.write_json(root, "Projects/Aurum/Recovery/latest-tinyseed-physical-preflight.json", self.preflight())
            self.write_json(
                root,
                "Projects/Aurum/Recovery/latest-tinyseed-flash-receipt.json",
                self.flash_receipt(source_commit="d" * 40),
            )
            branch_path = self.write_json(root, "Projects/Aurum/future-branches.json", self.live_branch())

            sync_future_branch_evidence(root)
            branch = json.loads(branch_path.read_text(encoding="utf-8"))
            flash = branch["canonical_evidence"]["flash_receipt"]

            self.assertTrue(flash["present"])
            self.assertFalse(flash["matches_current_release"])
            self.assertTrue(flash["raw_readback_verified"])
            self.assertFalse(branch["live_controls"]["current_release_flash_ready_to_boot"])
            self.assertTrue(branch["live_controls"]["flash_authorization_eligible"])
            self.assertIn("flash_receipt_matches_current_release=false", branch["current_program"])

    def test_matching_readback_verified_flash_moves_to_physical_boot_without_reflash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.write_json(root, "Projects/Aurum/Release/latest-tinyseed-handoff.json", self.handoff())
            self.write_json(root, "Projects/Aurum/Recovery/latest-tinyseed-physical-preflight.json", self.preflight())
            self.write_json(
                root,
                "Projects/Aurum/Recovery/latest-tinyseed-flash-receipt.json",
                self.flash_receipt(),
            )
            branch_path = self.write_json(root, "Projects/Aurum/future-branches.json", self.live_branch())

            sync_future_branch_evidence(root)
            branch = json.loads(branch_path.read_text(encoding="utf-8"))
            authorization = self.input_family(branch, "explicit-guarded-flash-authorization")
            generic = self.input_family(branch, "generic-prompt-intent-expansion")

            self.assertTrue(branch["canonical_evidence"]["flash_receipt"]["matches_current_release"])
            self.assertTrue(branch["live_controls"]["current_release_flash_ready_to_boot"])
            self.assertFalse(branch["live_controls"]["flash_authorization_eligible"])
            self.assertIn("already has a matching readback-verified READY_TO_BOOT flash receipt", authorization["prepared_response"])
            self.assertIn("physical boot/boot-proof", authorization["action_if_safe"])
            self.assertIn("physical boot-proof collection", generic["action_if_safe"])
            self.assertEqual(
                branch["likely_machine_outcomes"][0]["state"],
                "current-release-flash-readback-proven-awaiting-physical-boot",
            )

    def test_stale_preflight_release_is_projected_as_mismatch_not_silently_current(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.write_json(root, "Projects/Aurum/Release/latest-tinyseed-handoff.json", self.handoff())
            self.write_json(
                root,
                "Projects/Aurum/Recovery/latest-tinyseed-physical-preflight.json",
                self.preflight(source_commit="d" * 40),
            )
            branch_path = self.write_json(root, "Projects/Aurum/future-branches.json", {"current_program": "old"})

            result = sync_future_branch_evidence(root)
            branch = json.loads(branch_path.read_text(encoding="utf-8"))

            self.assertTrue(result["changed"])
            self.assertFalse(branch["canonical_evidence"]["physical_preflight"]["matches_current_release"])
            self.assertIn("preflight_matches_current_release=false", branch["current_program"])
            self.assertFalse(branch["live_controls"]["flash_authorization_eligible"])

    def test_invalid_candidate_fails_closed_without_changing_branch_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.write_json(root, "Projects/Aurum/Release/latest-tinyseed-handoff.json", self.handoff())
            preflight = self.preflight()
            preflight["usb_candidate"] = ["not", "an", "object"]
            self.write_json(root, "Projects/Aurum/Recovery/latest-tinyseed-physical-preflight.json", preflight)
            branch_path = self.write_json(root, "Projects/Aurum/future-branches.json", {"current_program": "proven"})
            before = branch_path.read_bytes()

            with self.assertRaises(FutureBranchEvidenceError):
                sync_future_branch_evidence(root)

            self.assertEqual(branch_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
