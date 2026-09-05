from __future__ import annotations

from contextlib import nullcontext
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
import aurum_network as network


class AurumNetworkTests(unittest.TestCase):
    def test_nmcli_terse_parser_preserves_escaped_separators(self) -> None:
        self.assertEqual(
            network._split_nmcli(r"Cafe\: East:70:WPA2"),
            ["Cafe: East", "70", "WPA2"],
        )

    def test_profile_is_private_and_credentials_never_enter_nmcli_argv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_profiles = root / "run"
            system_profiles = root / "system"
            secret = "test-secret-only"
            observed_arguments: list[list[str]] = []

            def fake_nmcli(arguments, **_kwargs):
                observed_arguments.append(list(arguments))
                return subprocess.CompletedProcess(arguments, 0, "")

            profile_uuid = "11111111-1111-4111-8111-111111111111"
            verified = {
                "status": "online",
                "online": True,
                "associated": True,
                "ssid": "Test Network",
                "connection_uuid": profile_uuid,
                "manager": network.MANAGER,
            }
            with (
                patch.object(network, "_operation_lock", return_value=nullcontext()),
                patch.object(network, "RUNTIME_CONNECTIONS", run_profiles),
                patch.object(network, "SYSTEM_CONNECTIONS", system_profiles),
                patch.object(network, "wireless_interfaces", return_value=["wlan0"]),
                patch.object(network, "_manager_ready", return_value=True),
                patch.object(network, "_active_for", return_value=None),
                patch.object(network.uuid, "uuid4", return_value=profile_uuid),
                patch.object(network, "_activate_profile", return_value=verified),
                patch.object(network, "_nmcli", side_effect=fake_nmcli),
            ):
                result = network.connect_wifi(" Test Network ", secret, "wlan0")

            persistent = system_profiles / f"{network.PROFILE_PREFIX}{profile_uuid}.nmconnection"
            self.assertTrue(result["online"])
            self.assertTrue(result["saved"])
            if os.name == "posix":
                self.assertEqual(os.stat(persistent).st_mode & 0o777, 0o600)
                self.assertEqual(os.stat(system_profiles).st_mode & 0o777, 0o700)
            self.assertIn("psk=test-secret-only", persistent.read_text(encoding="utf-8"))
            self.assertNotIn(secret, json.dumps(observed_arguments))

    def test_saved_profile_is_not_tied_to_one_adapter_name(self) -> None:
        content = network._profile_content(
            "Portable Network",
            "portable-secret",
            "55555555-5555-4555-8555-555555555555",
        )
        self.assertNotIn("interface-name", content)

    @unittest.skipUnless(os.name == "posix", "driver symlink semantics are Linux-specific")
    def test_hardware_report_distinguishes_bound_and_unbound_wifi(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sys_root = Path(temporary)
            interface = sys_root / "class/net/wlan0"
            driver = sys_root / "drivers/iwlwifi"
            interface.joinpath("wireless").mkdir(parents=True)
            driver.mkdir(parents=True)
            interface.joinpath("device").mkdir()
            interface.joinpath("device/driver").symlink_to(driver)
            pci = sys_root / "bus/pci/devices/0000:01:00.0"
            pci.mkdir(parents=True)
            pci.joinpath("class").write_text("0x028000\n", encoding="ascii")
            with patch.object(network, "_device_rows", return_value=[]):
                report = network.wireless_hardware(sys_root)
        self.assertTrue(report["driver_ready"])
        self.assertEqual(report["adapters"][0]["driver"], "iwlwifi")
        self.assertEqual(report["unbound_pci_wifi_count"], 1)

    def test_status_projects_exact_interface_without_global_route_guessing(self) -> None:
        rows = [{"DEVICE": "usb0", "TYPE": "ethernet", "STATE": "connected", "CONNECTION": "wired"}]
        properties = {
            "GENERAL.STATE": ["100 (connected)"],
            "IP4.ADDRESS": ["10.12.194.5/24"],
            "IP4.GATEWAY": ["10.12.194.1"],
        }
        with (
            patch.object(network, "wireless_interfaces", return_value=[]),
            patch.object(network, "wireless_hardware", return_value={"adapters": [], "unbound_pci_wifi_count": 0}),
            patch.object(network, "_manager_ready", return_value=True),
            patch.object(network, "_device_rows", return_value=rows),
            patch.object(network, "_device_properties", return_value=properties),
            patch.object(network, "_active_for", return_value={"UUID": "wired", "TYPE": "ethernet"}),
            patch.object(network, "_internet_probe", return_value={"dns_github": True, "github_tcp_443": True, "probe_status": "complete"}),
        ):
            status = network.network_status()
        self.assertEqual(status["interface"], "usb0")
        self.assertEqual(status["ip"], "10.12.194.5")
        self.assertTrue(status["online"])

    def test_boot_observer_never_attempts_reconnection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "network.json"
            with (
                patch.object(sys, "argv", ["aurum_network.py", "--boot-status", "--write-state", str(receipt)]),
                patch.object(network, "network_status", return_value={"status": "offline", "online": False}) as status,
                patch.object(network, "connect_saved") as reconnect,
            ):
                returncode = network.main()
            payload = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(returncode, 0)
        self.assertEqual(payload["status"], "offline")
        status.assert_called_once()
        reconnect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
