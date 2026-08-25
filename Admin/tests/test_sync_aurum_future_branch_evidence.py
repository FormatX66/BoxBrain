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
                    "likely_machine_outcomes": [{"state": "keep-me"}],
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
            self.assertIn("explicit-guarded-flash-authorization", branch["current_program"])
            self.assertEqual(branch["likely_machine_outcomes"], [{"state": "keep-me"}])

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
