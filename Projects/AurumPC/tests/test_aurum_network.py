from __future__ import annotations

import importlib.util
import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "aurum_network.py"
SPEC = importlib.util.spec_from_file_location("aurum_network_test", MODULE_PATH)
assert SPEC and SPEC.loader
network = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = network
SPEC.loader.exec_module(network)


class AurumNetworkTests(unittest.TestCase):
    def test_status_projects_active_interface_and_ip_for_gui(self) -> None:
        def fake_run(arguments, **_kwargs):
            if arguments[-3:] == ["route", "show", "default"]:
                return SimpleNamespace(returncode=0, stdout="default via 10.12.194.1 dev usb0\n")
            return SimpleNamespace(
                returncode=0,
                stdout="1.1.1.1 via 10.12.194.1 dev usb0 src 10.12.194.5\n",
            )

        connection = unittest.mock.MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False
        with patch.object(network.shutil, "which", return_value="/sbin/ip"), patch.object(
            network, "_run", side_effect=fake_run
        ), patch.object(network, "_addresses", return_value=["usb0:10.12.194.5"]), patch.object(
            network, "wireless_interfaces", return_value=[]
        ), patch.object(socket, "getaddrinfo", return_value=[object()]), patch.object(
            socket, "create_connection", return_value=connection
        ):
            status = network.network_status()

        self.assertEqual(status["interface"], "usb0")
        self.assertEqual(status["ip"], "10.12.194.5")
        self.assertTrue(status["online"])

    def test_boot_reconnect_cli_writes_a_bounded_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "network.json"
            with (
                patch.object(sys, "argv", [
                    "aurum_network.py",
                    "--reconnect-saved",
                    "--timeout-seconds",
                    "20",
                    "--write-state",
                    str(receipt),
                ]),
                patch.object(network, "network_status", return_value={"online": False}),
                patch.object(
                    network,
                    "connect_saved",
                    return_value={"status": "online", "online": True, "interface": "wlan0"},
                ) as reconnect,
            ):
                returncode = network.main()

            payload = json.loads(receipt.read_text(encoding="utf-8"))

        self.assertEqual(returncode, 0)
        self.assertEqual(payload["status"], "online")
        reconnect.assert_called_once_with(timeout_seconds=20)


if __name__ == "__main__":
    unittest.main()
