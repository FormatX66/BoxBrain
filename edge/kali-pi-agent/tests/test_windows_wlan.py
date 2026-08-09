from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import threading
from unittest.mock import patch
from urllib.request import urlopen


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boxbrain.cli import build_parser  # noqa: E402
from boxbrain.diagnostics import DiagnosticError, TargetDiagnostics  # noqa: E402
from boxbrain.server import build_server  # noqa: E402
from boxbrain.windows_wlan import (  # noqa: E402
    WLAN_RECONNECT_AUTHORIZATION,
    WLAN_RECONNECT_CONFIRMATION,
    WindowsWlanError,
    build_powershell,
    diagnose_inventory,
    load_saved_inventories,
    parse_powershell_output,
)


def sample_inventory() -> dict[str, object]:
    return {
        "schema_version": 1,
        "collected_at": "2026-08-08T00:00:00Z",
        "source": "windows-supported-wlan-commands",
        "credential_material_included": False,
        "interfaces": [
            {
                "name": "Wi-Fi",
                "guid": "11111111-2222-3333-4444-555555555555",
                "description": "Test Wireless Adapter",
                "state": "connected",
                "current_ssid": "Authorized-Lab",
                "profile": "Authorized-Lab",
                "signal_percent": 82,
                "authentication": "WPA2-Personal",
                "encryption": "CCMP",
                "ipv4": ["192.168.1.20"],
                "gateway": ["192.168.1.1"],
                "dns": ["192.168.1.1"],
            }
        ],
        "profiles": [
            {
                "profile": "Authorized-Lab",
                "ssid": "Authorized-Lab",
                "interface": "Wi-Fi",
                "authentication": "WPA2-Personal",
                "encryption": "CCMP",
                "auto_connect": True,
                "priority": 1,
                "credential_available": True,
            }
        ],
    }


class WindowsWlanTests(unittest.TestCase):
    def test_collector_uses_supported_commands_without_key_material(self) -> None:
        script = build_powershell("status")
        lowered = script.lower()
        self.assertIn("netsh.exe", lowered)
        self.assertIn("get-netipconfiguration", lowered)
        self.assertIn("get-dnsclientserveraddress", lowered)
        self.assertIn("get-netadapter -physical", lowered)
        self.assertIn("$_.hardwareinterface -eq $true", lowered)
        self.assertIn("$adapters.count -eq 0", lowered)
        self.assertIn("get-boxbrainvalue $_ @('guid')", lowered)
        self.assertIn("$detailblocks = @(", lowered)
        self.assertIn("-ceq $profilename", lowered)
        self.assertNotIn("key=clear", lowered)
        self.assertNotIn("key content", lowered)
        self.assertNotIn("wlanprofiles\\", lowered)
        self.assertIn("credential_material_included = $false", script)

    def test_parameters_are_encoded_instead_of_interpolated(self) -> None:
        hostile = "profile'; Remove-Item C:\\*; '"
        script = build_powershell(
            "reconnect",
            profile=hostile,
            interface="Wi-Fi",
        )
        self.assertNotIn(hostile, script)
        self.assertIn("FromBase64String", script)

    def test_structured_inventory_and_diagnostics(self) -> None:
        payload = {
            "schema_version": 1,
            "action": "status",
            "inventory": sample_inventory(),
            "reconnect": None,
        }
        parsed = parse_powershell_output("noise\n" + json.dumps(payload))
        inventory = parsed["inventory"]
        self.assertFalse(inventory["credential_material_included"])
        self.assertNotIn("password", json.dumps(inventory).lower())
        diagnostics = diagnose_inventory(inventory)
        self.assertEqual(diagnostics["interface_count"], 1)
        self.assertEqual(diagnostics["profile_count"], 1)
        self.assertEqual(diagnostics["recognized_ssids"], ["Authorized-Lab"])

    def test_parser_rejects_inventory_that_cannot_prove_credential_exclusion(self) -> None:
        inventory = sample_inventory()
        inventory["credential_material_included"] = True
        with self.assertRaisesRegex(WindowsWlanError, "credential exclusion"):
            parse_powershell_output(
                json.dumps({"inventory": inventory, "action": "status"})
            )

    def test_parser_rejects_credential_material_despite_exclusion_flag(self) -> None:
        inventory = sample_inventory()
        inventory["profiles"][0]["passphrase"] = "test-only-secret"
        with self.assertRaisesRegex(WindowsWlanError, "credential material"):
            parse_powershell_output(
                json.dumps({"inventory": inventory, "action": "status"})
            )

    def test_saved_inventory_loader_rejects_credential_material(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "network-inventory"
            directory.mkdir()
            inventory = sample_inventory()
            inventory["profiles"][0]["key_content"] = "test-only-secret"
            record = {
                "target": {"hostname": "AUTHORIZED-PC"},
                "inventory": inventory,
            }
            (directory / "unsafe-windows-wlan.json").write_text(
                json.dumps(record),
                encoding="utf-8",
            )
            self.assertEqual(load_saved_inventories(temporary), [])

    def test_target_service_requires_authorized_windows_link_and_reconnect_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            diagnostics = TargetDiagnostics(temporary)
            inventory = sample_inventory()
            output = json.dumps(
                {
                    "schema_version": 1,
                    "action": "reconnect",
                    "inventory": inventory,
                    "reconnect": {
                        "requested": True,
                        "profile": "Authorized-Lab",
                        "interface": "Wi-Fi",
                        "connected": True,
                        "output_recorded": False,
                    },
                }
            )
            with (
                patch.object(
                    diagnostics,
                    "_link",
                    return_value={
                        "address": "10.12.194.2",
                        "hostname": "AUTHORIZED-PC",
                        "platform": "windows",
                        "status": "connected",
                    },
                ),
                patch.object(diagnostics, "_ssh", return_value=output),
            ):
                with self.assertRaisesRegex(DiagnosticError, "authorization"):
                    diagnostics.windows_wlan(
                        "10.12.194.2",
                        "reconnect",
                        profile="Authorized-Lab",
                        interface="Wi-Fi",
                    )
                result = diagnostics.windows_wlan(
                    "10.12.194.2",
                    "reconnect",
                    profile="Authorized-Lab",
                    interface="Wi-Fi",
                    authorization=WLAN_RECONNECT_AUTHORIZATION,
                    confirmation=WLAN_RECONNECT_CONFIRMATION,
                )
            self.assertTrue(result["reconnect"]["connected"])
            saved = load_saved_inventories(temporary)
            self.assertEqual(saved[0]["target"]["hostname"], "AUTHORIZED-PC")
            self.assertFalse(saved[0]["inventory"]["credential_material_included"])

    def test_cli_exposes_all_required_wlan_actions(self) -> None:
        parser = build_parser()
        for action in ("interfaces", "profiles", "status", "diagnose", "reconnect"):
            args = parser.parse_args(["windows-wlan", "10.12.194.2", action])
            self.assertEqual(args.action, action)

    def test_web_console_networks_section_uses_saved_metadata_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "network-inventory"
            directory.mkdir()
            record = {
                "schema_version": 1,
                "generated_at": "2026-08-08T00:00:00Z",
                "target": {"address": "10.12.194.2", "hostname": "AUTHORIZED-PC"},
                "inventory": sample_inventory(),
                "reconnect": None,
            }
            (directory / "10.12.194.2-windows-wlan.json").write_text(
                json.dumps(record),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"BOXBRAIN_STATE_DIR": temporary}):
                server = build_server("127.0.0.1", 0)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    host, port = server.server_address
                    with urlopen(f"http://{host}:{port}/", timeout=10) as response:
                        page = response.read().decode("utf-8")
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=3)
            self.assertIn("Networks / Windows WLAN interfaces", page)
            self.assertIn("AUTHORIZED-PC", page)
            self.assertIn("Authorized-Lab", page)
            self.assertIn("credential values are never displayed", page)
            self.assertNotIn("test-only-secret", page)
            self.assertNotIn("key content", page.lower())


if __name__ == "__main__":
    unittest.main()
