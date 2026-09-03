from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MODULE_PATH = ROOT / "aurum_install_flow.py"
SPEC = importlib.util.spec_from_file_location("aurum_install_flow_test", MODULE_PATH)
assert SPEC and SPEC.loader
flow = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = flow
SPEC.loader.exec_module(flow)


def target(*, suffix: str = "A", repair: bool = False) -> dict[str, object]:
    return {
        "device": f"/dev/nvme0n1{suffix}",
        "kernel_name": "nvme0n1",
        "model": "Hopper Internal NVMe",
        "serial": f"PRIVATE-SERIAL-{suffix}",
        "transport": "nvme",
        "size_bytes": 512_000_000_000,
        "size_gib": 476.8,
        "existing_partitions": [{"label": "existing"}],
        "confirmation_code": f"ERASE-0000000{suffix}",
        "confirm_command": f"install confirm ERASE-0000000{suffix}",
        "repair_available": repair,
    }


class FakeInstaller:
    def __init__(self, targets: list[dict[str, object]], *, fail: bool = False) -> None:
        self.targets = targets
        self.fail = fail
        self.install_calls: list[str] = []
        self.repair_calls: list[str] = []

    def plan(self) -> dict[str, object]:
        return {
            "available": bool(self.targets),
            "reason": "ready" if self.targets else "no-unmounted-internal-disk-found",
            "targets": self.targets,
        }

    def install(self, confirmation_code: str, *, progress=None) -> dict[str, object]:
        self.install_calls.append(confirmation_code)
        if progress:
            for phase in ("preflight", "partition", "format", "copy", "bootloader", "verify"):
                progress({"phase": phase, "device": "/dev/private"})
        if self.fail:
            raise flow.InstallError("verification fixture failed")
        return {
            "status": "installed",
            "device": "/dev/private",
            "model": "Hopper Internal NVMe",
            "size_gib": 476.8,
            "boot_mode": "uefi-and-legacy-fallback",
            "other_disks_modified": False,
            "next_action": "poweroff, remove USB, then start",
        }

    def repair(self, confirmation_code: str, *, progress=None) -> dict[str, object]:
        self.repair_calls.append(confirmation_code)
        if progress:
            for phase in ("preflight", "filesystem", "copy", "bootloader", "verify"):
                progress({"phase": phase, "device": "/dev/private"})
        if self.fail:
            raise flow.InstallError("repair verification fixture failed")
        return {
            "status": "repaired",
            "device": "/dev/private",
            "model": "Hopper Internal NVMe",
            "size_gib": 476.8,
            "boot_mode": "uefi-and-legacy-fallback",
            "other_disks_modified": False,
            "next_action": "poweroff, remove USB, then start",
        }


class InstallFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.status_path = Path(self.temporary.name) / "install-status.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def wait_finished(self, coordinator) -> dict[str, object]:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            status = coordinator.status()
            if status.get("status") in {"complete", "failed"}:
                return status
            time.sleep(0.01)
        self.fail("installer worker did not finish")

    def test_ready_status_exposes_human_target_but_no_device_identity_or_code(self) -> None:
        coordinator = flow.InstallCoordinator(
            installer=FakeInstaller([target()]), status_path=self.status_path
        )
        status = coordinator.status()
        encoded = json.dumps(status)
        self.assertEqual(status["status"], "ready")
        self.assertEqual(status["target"]["model"], "Hopper Internal NVMe")
        self.assertTrue(status["target"]["contains_existing_data"])
        for private in ("/dev/", "PRIVATE-SERIAL", "ERASE-", "confirm_command"):
            self.assertNotIn(private, encoded)

    def test_one_confirmation_runs_all_phases_and_returns_verified_completion(self) -> None:
        installer = FakeInstaller([target()])
        coordinator = flow.InstallCoordinator(installer=installer, status_path=self.status_path)
        started = coordinator.start(confirmed=True)
        self.assertIn(started["status"], {"running", "complete"})
        completed = self.wait_finished(coordinator)
        self.assertEqual(completed["status"], "complete")
        self.assertEqual(completed["progress_percent"], 100)
        self.assertEqual(installer.install_calls, ["ERASE-0000000A"])
        self.assertNotIn("/dev/", self.status_path.read_text(encoding="utf-8"))

    def test_zero_targets_are_unavailable(self) -> None:
        installer = FakeInstaller([])
        coordinator = flow.InstallCoordinator(installer=installer, status_path=self.status_path)
        self.assertEqual(coordinator.status()["status"], "unavailable")
        with self.assertRaisesRegex(flow.InstallError, "eligible internal drive"):
            coordinator.start(confirmed=True)
        self.assertEqual(installer.install_calls, [])

    def test_multiple_targets_are_graphically_selectable_without_exposing_write_codes(self) -> None:
        installer = FakeInstaller([target(suffix="A"), target(suffix="B")])
        coordinator = flow.InstallCoordinator(installer=installer, status_path=self.status_path)
        status = coordinator.status()
        self.assertEqual(status["status"], "ready")
        self.assertEqual(status["target_count"], 2)
        self.assertEqual(len(status["targets"]), 2)
        self.assertNotIn("ERASE-", json.dumps(status))
        with self.assertRaisesRegex(flow.InstallError, "select exactly one"):
            coordinator.start(confirmed=True)
        coordinator.start(confirmed=True, target_id=status["targets"][1]["target_id"])
        self.wait_finished(coordinator)
        self.assertEqual(installer.install_calls, ["ERASE-0000000B"])

    def test_missing_confirmation_and_failed_verification_stop_safely(self) -> None:
        installer = FakeInstaller([target()], fail=True)
        coordinator = flow.InstallCoordinator(installer=installer, status_path=self.status_path)
        with self.assertRaisesRegex(flow.InstallError, "visible confirmation"):
            coordinator.start(confirmed=False)
        coordinator.start(confirmed=True)
        failed = self.wait_finished(coordinator)
        self.assertEqual(failed["status"], "failed")
        self.assertIn("verification fixture failed", failed["reason"])

    def test_poweroff_is_available_only_after_verified_completion(self) -> None:
        calls: list[list[str]] = []

        def power_runner(arguments: list[str], **_kwargs):
            calls.append(arguments)
            return subprocess.CompletedProcess(arguments, 0, "", "")

        coordinator = flow.InstallCoordinator(
            installer=FakeInstaller([target()]),
            status_path=self.status_path,
            power_runner=power_runner,
        )
        with self.assertRaisesRegex(flow.InstallError, "only after"):
            coordinator.poweroff()
        coordinator.start(confirmed=True)
        self.wait_finished(coordinator)
        with patch.object(flow.shutil, "which", return_value="/usr/bin/systemctl"):
            status = coordinator.poweroff()
        self.assertEqual(status["status"], "powering-off")
        self.assertEqual(calls, [["/usr/bin/systemctl", "poweroff"]])

    def test_verified_completion_survives_gui_restart_without_offering_reinstall(self) -> None:
        installer = FakeInstaller([target()])
        first = flow.InstallCoordinator(installer=installer, status_path=self.status_path)
        first.start(confirmed=True)
        self.wait_finished(first)

        restored = flow.InstallCoordinator(installer=installer, status_path=self.status_path)
        self.assertEqual(restored.status()["status"], "complete")
        with self.assertRaisesRegex(flow.InstallError, "already installed"):
            restored.start(confirmed=True)

    def test_interrupted_running_receipt_becomes_retryable_failure(self) -> None:
        self.status_path.write_text(
            json.dumps(
                {
                    "schema": flow.FLOW_SCHEMA,
                    "status": "running",
                    "phase": "copy",
                    "target": {"model": "Internal NVMe"},
                }
            ),
            encoding="utf-8",
        )
        restored = flow.InstallCoordinator(
            installer=FakeInstaller([target()]), status_path=self.status_path
        )
        status = restored.status()
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["reason"], "installer-interface-restarted")

    def test_repair_requires_repairable_selected_drive_and_uses_non_install_path(self) -> None:
        installer = FakeInstaller([target(repair=True)])
        coordinator = flow.InstallCoordinator(installer=installer, status_path=self.status_path)
        status = coordinator.status()
        coordinator.start(
            confirmed=True,
            target_id=status["target"]["target_id"],
            operation="repair",
        )
        completed = self.wait_finished(coordinator)
        self.assertEqual(completed["status"], "complete")
        self.assertEqual(completed["result"]["status"], "repaired")
        self.assertEqual(installer.repair_calls, ["ERASE-0000000A"])
        self.assertEqual(installer.install_calls, [])

    def test_failed_operation_can_reset_to_fresh_multi_drive_discovery(self) -> None:
        installer = FakeInstaller([target(suffix="A"), target(suffix="B")], fail=True)
        coordinator = flow.InstallCoordinator(installer=installer, status_path=self.status_path)
        ready = coordinator.status()
        coordinator.start(confirmed=True, target_id=ready["targets"][0]["target_id"])
        self.assertEqual(self.wait_finished(coordinator)["status"], "failed")
        reset = coordinator.reset()
        self.assertEqual(reset["status"], "ready")
        self.assertEqual(reset["target_count"], 2)


if __name__ == "__main__":
    unittest.main()
