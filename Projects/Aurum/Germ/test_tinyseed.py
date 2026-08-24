#!/usr/bin/env python3
from __future__ import annotations

import builtins
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import network
import tinyseed


class TinySeedNetworkTests(unittest.TestCase):
    def test_link_without_dns_is_not_online(self) -> None:
        with (
            mock.patch.object(network, "_networkmanager_connected", return_value=True),
            mock.patch.object(network, "_repository_addresses", return_value=[]),
            mock.patch.object(network, "_repository_tcp_ready") as tcp_ready,
        ):
            observed = network.connectivity()
        self.assertTrue(observed["link_connected"])
        self.assertFalse(observed["resolver_ready"])
        self.assertFalse(observed["repository_tcp_443"])
        self.assertFalse(observed["online"])
        tcp_ready.assert_not_called()

    def test_dns_and_repository_route_are_required_for_online(self) -> None:
        with (
            mock.patch.object(network, "_networkmanager_connected", return_value=True),
            mock.patch.object(network, "_repository_addresses", return_value=["192.0.2.10"]),
            mock.patch.object(network, "_repository_tcp_ready", return_value=True),
        ):
            observed = network.connectivity()
        self.assertTrue(observed["resolver_ready"])
        self.assertTrue(observed["repository_tcp_443"])
        self.assertTrue(observed["online"])

    def test_network_failure_requires_explicit_offline_choice(self) -> None:
        with (
            mock.patch.object(network, "status", side_effect=network.NetworkError("not ready")),
            mock.patch.object(builtins, "input", return_value="o") as prompt,
            mock.patch.object(tinyseed, "_title"),
        ):
            self.assertFalse(tinyseed._network_step())
        prompt.assert_called_once()

    def test_scan_retry_can_join_wifi(self) -> None:
        answers = iter(["r", "1"])
        with (
            mock.patch.object(network, "status", side_effect=[network.NetworkError("warming up"), {"online": False}]),
            mock.patch.object(
                network,
                "wifi_scan",
                return_value=[{"ssid": "Test WiFi", "signal": 88, "security": "WPA2"}],
            ),
            mock.patch.object(network, "wifi_connect", return_value={"status": "connected"}) as connect,
            mock.patch.object(network, "wait_online", return_value=True),
            mock.patch.object(tinyseed.getpass, "getpass", return_value="secret"),
            mock.patch.object(builtins, "input", side_effect=lambda _prompt="": next(answers)),
            mock.patch.object(tinyseed, "_title"),
        ):
            self.assertTrue(tinyseed._network_step())
        connect.assert_called_once_with("Test WiFi", "secret")

    def test_offline_result_can_join_and_resume_without_reinstall(self) -> None:
        result = {"status": "prepared", "regrow": {"status": "deferred-offline"}}
        with (
            mock.patch.object(builtins, "input", return_value="1"),
            mock.patch.object(tinyseed, "_network_step", return_value=True),
            mock.patch.object(
                tinyseed,
                "_regrow_installed_root",
                return_value={"status": "trial-armed", "slot": "B"},
            ) as regrow,
            mock.patch.object(tinyseed, "_title"),
        ):
            self.assertTrue(tinyseed._finish_offline(result, "/dev/nvme0n1p2"))
        regrow.assert_called_once_with("/dev/nvme0n1p2")
        self.assertEqual(result["regrow"]["status"], "trial-armed")

    def test_offline_result_can_be_explicitly_deferred(self) -> None:
        result = {"status": "prepared", "regrow": {"status": "deferred-offline"}}
        with (
            mock.patch.object(builtins, "input", return_value="2"),
            mock.patch.object(tinyseed, "_network_step") as network_step,
            mock.patch.object(tinyseed, "_title"),
        ):
            self.assertFalse(tinyseed._finish_offline(result, "/dev/nvme0n1p2"))
        network_step.assert_not_called()


if __name__ == "__main__":
    unittest.main()
