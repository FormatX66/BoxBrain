from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import aurum_bootstrap
import aurum_time
import aurum_wifi_recovery


class FirstBootResilienceTests(unittest.TestCase):
    def _profile(self) -> dict:
        return {
            "pci_devices": [], "usb_devices": [], "block_devices": [],
            "input_devices": [], "graphics_devices": [], "network_interfaces": [],
        }

    def _plan(self) -> dict:
        return {"required_existing_drivers": [], "unresolved_devices": []}

    def test_offline_network_never_blocks_local_self_build(self) -> None:
        with (
            patch.object(aurum_bootstrap, "_autonomous_first_boot_enabled", return_value=True),
            patch.object(aurum_bootstrap, "wireless_interfaces", return_value=["wlan0"]),
            patch.object(aurum_bootstrap, "ensure_online", return_value={"status": "offline", "online": False}),
            patch.object(aurum_bootstrap.aurum_console.WORKSPACE, "seed", return_value={"status": "seeded"}),
            patch.object(aurum_bootstrap.aurum_console, "selftest", return_value=(True, "ok")),
            patch.object(aurum_bootstrap.aurum_console.BUILDS, "start", return_value={"status": "started"}) as start,
            patch.object(aurum_bootstrap, "_write_assessment"),
        ):
            aurum_bootstrap._first_boot(self._profile(), self._plan())
        start.assert_called_once_with()

    def test_online_path_synchronizes_clock_before_git(self) -> None:
        order: list[str] = []
        def sync_clock() -> dict:
            order.append("clock")
            return {"status": "synchronized", "synchronized": True}
        def git_sync(*, authorize_network: bool) -> dict:
            self.assertTrue(authorize_network)
            order.append("git")
            return {"status": "cloned"}
        with (
            patch.object(aurum_bootstrap, "_autonomous_first_boot_enabled", return_value=True),
            patch.object(aurum_bootstrap, "wireless_interfaces", return_value=["wlan0"]),
            patch.object(aurum_bootstrap, "ensure_online", return_value={"status": "online", "online": True}),
            patch.object(aurum_bootstrap, "synchronize_clock", side_effect=sync_clock),
            patch.object(aurum_bootstrap.aurum_console.WORKSPACE, "git_sync", side_effect=git_sync),
            patch.object(aurum_bootstrap.aurum_console.WORKSPACE, "seed", return_value={"status": "seeded"}),
            patch.object(aurum_bootstrap.aurum_console, "selftest", return_value=(True, "ok")),
            patch.object(aurum_bootstrap.aurum_console.BUILDS, "start", return_value={"status": "started"}),
            patch.object(aurum_bootstrap, "_write_assessment"),
        ):
            aurum_bootstrap._first_boot(self._profile(), self._plan())
        self.assertEqual(order, ["clock", "git"])

    def test_wifi_recovery_targets_wireless_subclass_not_bound_ethernet(self) -> None:
        profile = {"pci_devices": [
            {"address": "0000:04:00.0", "class": "0x020000", "driver": "r8169", "modalias": "ethernet"},
            {"address": "0000:03:00.0", "class": "0x028000", "driver": None, "modalias": "pci:wifi"},
        ]}
        candidates = aurum_wifi_recovery._wifi_candidates(profile)
        self.assertEqual([item["address"] for item in candidates], ["0000:03:00.0"])

    def test_unresolved_wifi_stops_without_replacing_driver(self) -> None:
        profile = {"pci_devices": [
            {"address": "0000:03:00.0", "class": "0x028000", "driver": None, "modalias": "pci:unknown"}
        ]}
        no_module = subprocess.CompletedProcess(["modprobe"], 1, "", "")
        with (
            patch.object(aurum_wifi_recovery, "wireless_interfaces", return_value=[]),
            patch.object(aurum_wifi_recovery, "collect_hardware_profile", return_value=profile),
            patch.object(aurum_wifi_recovery.shutil, "which", side_effect=lambda name: "/sbin/modprobe" if name == "modprobe" else None),
            patch.object(aurum_wifi_recovery, "_run", return_value=no_module),
            patch.object(aurum_wifi_recovery, "_kernel_messages", return_value=[]),
        ):
            result = aurum_wifi_recovery.recover_existing_wifi_driver(settle_seconds=0)
        self.assertEqual(result["status"], "unresolved")
        self.assertEqual(result["attempts"][0]["status"], "no-existing-module")

    def test_clock_recovery_fails_soft_when_helpers_are_missing(self) -> None:
        with patch.object(aurum_time.shutil, "which", return_value=None):
            result = aurum_time.synchronize_clock(timeout_seconds=0)
        self.assertEqual(result["status"], "helper-unavailable")
        self.assertFalse(result["synchronized"])


if __name__ == "__main__":
    unittest.main()
