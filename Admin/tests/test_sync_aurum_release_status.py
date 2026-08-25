"""Tests for canonical Aurum release-status projection."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from Admin.sync_aurum_release_status import ReleaseStatusError, sync_release_status


class AurumReleaseStatusSyncTests(unittest.TestCase):
    def write_json(self, root: Path, relative: str, value: dict) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def test_stale_completion_plan_is_synchronized(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.write_json(
                root,
                "Projects/Aurum/Release/latest-tinyseed-handoff.json",
                {
                    "schema": "aurum-tinyseed-handoff-v1",
                    "source_commit": "new-release",
                    "state": "READY_TO_FLASH",
                },
            )
            plan_path = self.write_json(
                root,
                "Projects/Aurum/completion-plan.json",
                {
                    "schema": "aurum-completion-plan-v1",
                    "latest_release_source_commit": "old-release",
                    "release_state": "WAIT",
                    "gates": [{"id": "physical", "state": "pending"}],
                },
            )

            result = sync_release_status(root)
            plan = json.loads(plan_path.read_text(encoding="utf-8"))

            self.assertTrue(result["changed"])
            self.assertEqual(plan["latest_release_source_commit"], "new-release")
            self.assertEqual(plan["release_state"], "READY_TO_FLASH")
            self.assertEqual(plan["gates"], [{"id": "physical", "state": "pending"}])

    def test_matching_plan_is_left_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.write_json(
                root,
                "Projects/Aurum/Release/latest-tinyseed-handoff.json",
                {
                    "schema": "aurum-tinyseed-handoff-v1",
                    "source_commit": "same-release",
                    "state": "READY_TO_FLASH",
                },
            )
            plan_path = self.write_json(
                root,
                "Projects/Aurum/completion-plan.json",
                {
                    "latest_release_source_commit": "same-release",
                    "release_state": "READY_TO_FLASH",
                },
            )
            before = plan_path.read_bytes()

            result = sync_release_status(root)

            self.assertFalse(result["changed"])
            self.assertEqual(plan_path.read_bytes(), before)

    def test_matching_readback_receipt_advances_only_flash_and_boot_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.write_json(
                root,
                "Projects/Aurum/Release/latest-tinyseed-handoff.json",
                {
                    "schema": "aurum-tinyseed-handoff-v1",
                    "source_commit": "release-a",
                    "state": "READY_TO_FLASH",
                },
            )
            self.write_json(
                root,
                "Projects/Aurum/Recovery/latest-tinyseed-flash-receipt.json",
                {
                    "schema": "aurum-tinyseed-flash-request-receipt-v1",
                    "state": "READY_TO_BOOT",
                    "source_commit": "release-a",
                    "raw_readback_verified": True,
                },
            )
            plan_path = self.write_json(
                root,
                "Projects/Aurum/completion-plan.json",
                {
                    "latest_release_source_commit": "release-a",
                    "release_state": "READY_TO_FLASH",
                    "gates": [
                        {
                            "id": "x86-physical-flash",
                            "state": "ready-for-guarded-preflight-explicit-authority-pending",
                            "ready_now": False,
                        },
                        {
                            "id": "x86-physical-boot",
                            "state": "blocked-on-physical-hardware",
                            "ready_now": False,
                        },
                        {
                            "id": "forced-rollback-proof",
                            "state": "unit-proven-physical-pending",
                            "ready_now": True,
                        },
                    ],
                },
            )

            result = sync_release_status(root)
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            gates = {gate["id"]: gate for gate in plan["gates"]}

            self.assertTrue(result["changed"])
            self.assertTrue(result["flash_ready_to_boot"])
            self.assertEqual(gates["x86-physical-flash"]["state"], "passed-readback-verified")
            self.assertTrue(gates["x86-physical-flash"]["ready_now"])
            self.assertEqual(gates["x86-physical-boot"]["state"], "ready-for-physical-boot-proof")
            self.assertFalse(gates["x86-physical-boot"]["ready_now"])
            self.assertEqual(gates["forced-rollback-proof"]["state"], "unit-proven-physical-pending")

    def test_stale_flash_receipt_cannot_keep_new_release_flash_gate_satisfied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.write_json(
                root,
                "Projects/Aurum/Release/latest-tinyseed-handoff.json",
                {
                    "schema": "aurum-tinyseed-handoff-v1",
                    "source_commit": "release-b",
                    "state": "READY_TO_FLASH",
                },
            )
            self.write_json(
                root,
                "Projects/Aurum/Recovery/latest-tinyseed-flash-receipt.json",
                {
                    "schema": "aurum-tinyseed-flash-request-receipt-v1",
                    "state": "READY_TO_BOOT",
                    "source_commit": "release-a",
                    "raw_readback_verified": True,
                },
            )
            plan_path = self.write_json(
                root,
                "Projects/Aurum/completion-plan.json",
                {
                    "latest_release_source_commit": "release-b",
                    "release_state": "READY_TO_FLASH",
                    "gates": [
                        {"id": "x86-physical-flash", "state": "passed-readback-verified", "ready_now": True},
                        {"id": "x86-physical-boot", "state": "ready-for-physical-boot-proof", "ready_now": False},
                    ],
                },
            )

            result = sync_release_status(root)
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            gates = {gate["id"]: gate for gate in plan["gates"]}

            self.assertTrue(result["changed"])
            self.assertFalse(result["flash_ready_to_boot"])
            self.assertEqual(gates["x86-physical-flash"]["state"], "blocked-on-current-release-flash-proof")
            self.assertEqual(gates["x86-physical-boot"]["state"], "blocked-on-current-release-flash")

    def test_invalid_handoff_fails_closed_without_changing_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.write_json(
                root,
                "Projects/Aurum/Release/latest-tinyseed-handoff.json",
                {
                    "schema": "wrong-schema",
                    "source_commit": "candidate",
                    "state": "READY_TO_FLASH",
                },
            )
            plan_path = self.write_json(
                root,
                "Projects/Aurum/completion-plan.json",
                {
                    "latest_release_source_commit": "proven",
                    "release_state": "READY_TO_FLASH",
                },
            )
            before = plan_path.read_bytes()

            with self.assertRaises(ReleaseStatusError):
                sync_release_status(root)

            self.assertEqual(plan_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
