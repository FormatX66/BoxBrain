#!/usr/bin/env python3
from __future__ import annotations

import builtins
import contextlib
import io
import subprocess
import sys
import tempfile
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
            mock.patch.object(network, "_repository_https_ready") as https_ready,
            mock.patch.object(network, "_repository_sync_ready") as sync_ready,
        ):
            observed = network.connectivity()
        self.assertTrue(observed["link_connected"])
        self.assertFalse(observed["resolver_ready"])
        self.assertFalse(observed["repository_tcp_443"])
        self.assertFalse(observed["online"])
        tcp_ready.assert_not_called()
        https_ready.assert_not_called()
        sync_ready.assert_not_called()

    def test_dns_https_and_exact_git_route_are_required_for_online(self) -> None:
        with (
            mock.patch.object(network, "_networkmanager_connected", return_value=True),
            mock.patch.object(network, "_repository_addresses", return_value=["192.0.2.10"]),
            mock.patch.object(network, "_repository_tcp_ready", return_value=True),
            mock.patch.object(network, "_repository_https_ready", return_value=True),
            mock.patch.object(network, "_repository_sync_ready", return_value=True),
        ):
            observed = network.connectivity()
        self.assertTrue(observed["resolver_ready"])
        self.assertTrue(observed["repository_tcp_443"])
        self.assertTrue(observed["repository_https"])
        self.assertTrue(observed["repository_sync"])
        self.assertTrue(observed["online"])

    def test_tcp_without_https_is_not_online(self) -> None:
        with (
            mock.patch.object(network, "_networkmanager_connected", return_value=True),
            mock.patch.object(network, "_repository_addresses", return_value=["2001:db8::1"]),
            mock.patch.object(network, "_repository_tcp_ready", return_value=True),
            mock.patch.object(network, "_repository_https_ready", return_value=False),
            mock.patch.object(network, "_repository_sync_ready") as sync_ready,
        ):
            observed = network.connectivity()
        self.assertFalse(observed["repository_https"])
        self.assertFalse(observed["online"])
        sync_ready.assert_not_called()
        self.assertIn("HTTPS", network.failure_reason(observed))

    def test_https_without_exact_git_sync_is_not_online(self) -> None:
        with (
            mock.patch.object(network, "_networkmanager_connected", return_value=True),
            mock.patch.object(network, "_repository_addresses", return_value=["192.0.2.10"]),
            mock.patch.object(network, "_repository_tcp_ready", return_value=True),
            mock.patch.object(network, "_repository_https_ready", return_value=True),
            mock.patch.object(network, "_repository_sync_ready", return_value=False),
        ):
            observed = network.connectivity()
        self.assertFalse(observed["repository_sync"])
        self.assertFalse(observed["online"])
        self.assertIn("git sync", network.failure_reason(observed))

    def test_networkmanager_connected_variants_are_link_hints(self) -> None:
        completed = subprocess.CompletedProcess([], 0, stdout="connected (site)\n", stderr="")
        with (
            mock.patch.object(network.shutil, "which", return_value="/usr/bin/nmcli"),
            mock.patch.object(network, "_run", return_value=completed),
        ):
            self.assertTrue(network._networkmanager_connected())

    def test_repair_records_command_failures_instead_of_crashing(self) -> None:
        with (
            mock.patch.object(network.shutil, "which", return_value="/usr/bin/tool"),
            mock.patch.object(network, "_run", side_effect=network.NetworkError("timed out")),
            mock.patch.object(network, "connectivity", side_effect=network.NetworkError("not ready")),
            mock.patch.object(network.Path, "exists", return_value=False),
        ):
            repaired = network.repair()
        self.assertFalse(repaired["connectivity"]["online"])
        self.assertTrue(any(action.get("reason") == "timed out" for action in repaired["actions"]))
        self.assertTrue(any(action.get("command") == "connectivity-proof" for action in repaired["actions"]))

    def test_network_failure_requires_explicit_offline_choice(self) -> None:
        with (
            mock.patch.object(network, "status", side_effect=network.NetworkError("not ready")),
            mock.patch.object(
                network,
                "repair",
                return_value={"connectivity": {"online": False}, "reason": "still unavailable"},
            ),
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
                "repair",
                return_value={"connectivity": {"online": False}, "reason": "still unavailable"},
            ),
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

    def test_compact_ui_is_small_colored_and_legible(self) -> None:
        output = io.StringIO()
        with (
            mock.patch.object(tinyseed, "_plain_ui", return_value=False),
            contextlib.redirect_stdout(output),
        ):
            tinyseed._title("1 · NETWORK", "Sync current trusted genetics.")
        rendered = output.getvalue()
        self.assertIn("\033[", rendered)
        self.assertIn("A U R U M", rendered)
        self.assertIn("TINY SEED", rendered)
        self.assertIn("/\\", rendered)
        self.assertLessEqual(len(rendered.splitlines()), 7)

    def test_blind_ui_has_words_without_escapes_or_decorations(self) -> None:
        output = io.StringIO()
        with (
            mock.patch.object(tinyseed, "_plain_ui", return_value=True),
            contextlib.redirect_stdout(output),
        ):
            tinyseed._title("NETWORK", "Choose a connection.")
        rendered = output.getvalue()
        self.assertIn("AURUM TINY SEED", rendered)
        self.assertIn("NETWORK: Choose a connection.", rendered)
        self.assertNotIn("\033", rendered)
        self.assertNotIn("/\\", rendered)
        self.assertNotIn("─", rendered)

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

    def test_existing_seed_uses_verified_carrier_when_network_is_down(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            carrier_root = Path(temporary) / "carrier"
            carrier_root.mkdir()
            (carrier_root / "carrier.json").write_text("{}\n", encoding="utf-8")
            with (
                mock.patch.object(tinyseed, "OFFLINE_CARRIER", carrier_root),
                mock.patch.object(tinyseed, "_run"),
                mock.patch.object(tinyseed.bridge, "install", return_value={"status": "bridged"}),
                mock.patch.object(
                    tinyseed,
                    "_chroot_regrow",
                    return_value={"status": "trial-armed", "source_transport": "offline-carrier"},
                ) as regrow,
            ):
                result = tinyseed._repair_existing({"device": "/dev/test-root"}, online=False)
            self.assertEqual(result["regrow"]["status"], "trial-armed")
            regrow.assert_called_once_with(mock.ANY, offline=True)

    def test_installed_bootstrap_uses_carrier_when_sync_is_down(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            carrier_root = root / "carrier"
            carrier_root.mkdir()
            (carrier_root / "carrier.json").write_text("{}\n", encoding="utf-8")
            state = root / "slots.json"
            state.write_text('{"active":"A","lkg":"A","trial":null}\n', encoding="utf-8")
            completed = subprocess.CompletedProcess(
                [], 0, stdout='{"status":"deferred-offline"}\n', stderr=""
            )
            with (
                mock.patch.object(tinyseed, "OFFLINE_CARRIER", carrier_root),
                mock.patch.object(tinyseed, "SLOT_STATE", state),
                mock.patch.object(tinyseed, "_network_step", return_value=False),
                mock.patch.object(tinyseed, "_run", return_value=completed) as run,
                mock.patch.object(tinyseed, "_title"),
            ):
                self.assertEqual(tinyseed._installed_bootstrap_mode(), 1)
            arguments = run.call_args.args[0]
            self.assertIn("--offline-carrier", arguments)
            self.assertNotIn("--authorize-network", arguments)

    def test_no_safe_target_is_waiting_not_a_restart_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                mock.patch.object(tinyseed, "INSTALLED_MARKER", root / "not-installed"),
                mock.patch.object(tinyseed, "LIVE_MEDIUM", root / "live-medium"),
                mock.patch.object(tinyseed.os, "geteuid", return_value=0),
                mock.patch.object(tinyseed.machine, "detect", return_value={"architecture": "x86_64"}),
                mock.patch.object(tinyseed, "_network_step", return_value=True),
                mock.patch.object(tinyseed, "_installed_roots", return_value=[]),
                mock.patch.object(tinyseed.installer, "plan", return_value={"targets": []}),
                mock.patch.object(tinyseed, "_title"),
            ):
                self.assertEqual(tinyseed.main(), tinyseed.NO_SAFE_TARGET_EXIT)


if __name__ == "__main__":
    unittest.main()
