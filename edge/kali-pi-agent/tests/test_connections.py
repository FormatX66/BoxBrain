from __future__ import annotations

from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boxbrain.connections import build_connection_map  # noqa: E402


class ConnectionMapTests(unittest.TestCase):
    def test_reports_each_transport_and_only_observed_capabilities(self) -> None:
        existing = {
            "/sys/class/udc",
            "/sys/class/bluetooth",
            "/dev/hidg0",
            "/dev/hidg1",
        }
        network = {
            "interfaces": [
                {"name": "usb0", "state": "UP", "addresses": ["10.12.194.1"]},
                {"name": "wlan0", "state": "UP", "addresses": ["192.168.1.5"]},
                {"name": "eth0", "state": "DOWN", "addresses": []},
            ]
        }
        links = [
            {
                "status": "connected",
                "transport": "usb-ethernet-ssh",
                "interface": "usb0",
                "platform": "windows",
            }
        ]

        result = build_connection_map(
            network,
            links,
            path_exists=lambda value: value in existing,
            directory_has_entries=lambda value: value in existing,
        )

        self.assertEqual(result["schema_version"], 1)
        transports = {item["id"]: item for item in result["transports"]}
        self.assertEqual(
            set(transports),
            {"usb", "ethernet", "wifi", "bluetooth", "near-field"},
        )
        self.assertEqual(transports["usb"]["state"], "connected")
        self.assertEqual(transports["usb"]["target_count"], 1)
        usb_capabilities = {
            item["id"]: item["state"]
            for item in transports["usb"]["capabilities"]
        }
        self.assertEqual(usb_capabilities["keyboard"], "available")
        self.assertEqual(usb_capabilities["mouse"], "available")
        self.assertEqual(usb_capabilities["ssh"], "ready")
        self.assertEqual(usb_capabilities["powershell"], "bounded")
        self.assertEqual(transports["wifi"]["state"], "connected")
        self.assertEqual(transports["ethernet"]["state"], "available")
        self.assertEqual(transports["bluetooth"]["state"], "available")
        bluetooth_capabilities = {
            item["id"]: item["state"]
            for item in transports["bluetooth"]["capabilities"]
        }
        self.assertEqual(bluetooth_capabilities["keyboard"], "requires-pairing")
        self.assertEqual(bluetooth_capabilities["mouse"], "requires-pairing")
        self.assertEqual(transports["near-field"]["state"], "not-detected")

    def test_inventory_never_claims_session_features_when_nothing_is_detected(self) -> None:
        result = build_connection_map(
            {"interfaces": []},
            [],
            path_exists=lambda _value: False,
            directory_has_entries=lambda _value: False,
        )

        for transport in result["transports"]:
            for capability in transport["capabilities"]:
                if capability["id"] in {"dashboard", "keyboard", "mouse", "ssh"}:
                    self.assertNotEqual(capability["state"], "ready")


if __name__ == "__main__":
    unittest.main()
