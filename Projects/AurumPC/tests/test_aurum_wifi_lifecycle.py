"""Synthetic config/process fixtures. Never drives a real network interface."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
import aurum_network as network


@unittest.skipUnless(sys.platform == "linux", "Linux operation-lock and pidfd contract")
class WifiLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.saved = self.root / "state" / "wifi.conf"
        self.run = self.root / "run"
        self.run.mkdir()
        for name, value in (("SAVED_WIFI", self.saved), ("STATE_DIR", self.saved.parent), ("RUN_DIR", self.run)):
            self.stack.enter_context(patch.object(network, name, value))
        self.stack.enter_context(patch.object(network, "wireless_interfaces", return_value=["wlan-test"]))

    def save_old(self):
        network._write_config(self.saved, "synthetic-known-good")

    def test_failed_candidate_preserves_saved_config_and_attempts_one_recovery(self):
        self.save_old()
        failure = {"status": "wifi-association-pending", "online": False, "started": True}
        recovered = {"status": "online", "online": True}
        with patch.object(network, "_make_config", return_value="synthetic-candidate"), patch.object(
            network, "_connect_config", side_effect=[failure, recovered]
        ) as connect, patch.object(network, "_stop_owned_supplicant") as stop:
            result = network.connect_wifi("Synthetic", "test-only")
        self.assertEqual(self.saved.read_text(), "synthetic-known-good")
        self.assertFalse(result["saved"])
        self.assertFalse(result["online"])
        self.assertTrue(result["recovery"]["online"])
        self.assertEqual(connect.call_count, 2)
        connect.assert_called_with("wlan-test", self.saved, timeout_seconds=15)
        stop.assert_called_once_with("wlan-test")

    def test_verified_exact_ssid_commits_and_keeps_previous_copy(self):
        self.save_old()
        def connect(interface, path, **kwargs):
            self.assertEqual(self.saved.read_text(), "synthetic-known-good")
            self.assertEqual(path.read_text(), "synthetic-candidate")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            return {"status": "online", "online": True, "associated": True, "ssid": "Synthetic"}
        with patch.object(network, "_make_config", return_value="synthetic-candidate"), patch.object(network, "_connect_config", side_effect=connect):
            result = network.connect_wifi("Synthetic", "test-only")
        self.assertTrue(result["saved"])
        self.assertEqual(self.saved.read_text(), "synthetic-candidate")
        self.assertEqual(self.saved.with_name("wifi.previous.conf").read_text(), "synthetic-known-good")
        self.assertEqual(self.saved.stat().st_mode & 0o777, 0o600)

    def test_wrong_ssid_cannot_promote_even_when_internet_probe_passes(self):
        self.save_old()
        with patch.object(network, "_make_config", return_value="synthetic-candidate"), patch.object(network, "_connect_config", return_value={"online": True, "associated": True, "ssid": "Other", "status": "online"}):
            result = network.connect_wifi("Synthetic", "test-only")
        self.assertFalse(result["saved"])
        self.assertFalse(result["online"])
        self.assertEqual(self.saved.read_text(), "synthetic-known-good")

    def test_invalid_interface_cannot_write_candidate_path(self):
        with patch.object(network, "network_status", return_value={"online": False}), patch.object(network, "_write_config") as write:
            result = network.connect_wifi("Synthetic", "test-only", "../invalid")
        self.assertEqual(result["status"], "no-wifi-interface")
        write.assert_not_called()

    def test_real_cross_process_lock_rejects_overlap_then_releases(self):
        program = "import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);import aurum_network as n;n.RUN_DIR=Path(sys.argv[2]);print(json.dumps(n._serialized(lambda:{'status':'entered'})()))"
        def child():
            result = subprocess.run([sys.executable, "-c", program, str(ROOT), str(self.run)], capture_output=True, text=True, timeout=5, check=True)
            return json.loads(result.stdout)
        with network._operation_lock():
            self.assertEqual(child()["status"], "wifi-operation-busy")
            with patch.object(network, "_make_config") as make:
                self.assertEqual(network.connect_wifi("Synthetic", "test-only")["status"], "wifi-operation-busy")
                make.assert_not_called()
        self.assertEqual(child()["status"], "entered")

    def test_stop_timeout_retains_pid_and_uses_no_raw_pid_signal(self):
        pid_path = self.run / "wpa-wlan-test.pid"
        pid_path.write_text("44444")
        args = ["/sbin/wpa_supplicant", "-i", "wlan-test", "-c", str(self.saved), "-P", str(pid_path)]
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, read_fd)
        self.addCleanup(os.close, write_fd)
        with patch.object(network.os, "pidfd_open", side_effect=lambda pid: os.dup(read_fd)), patch.object(
            Path, "read_bytes", return_value="\0".join(args).encode()
        ), patch.object(network.signal, "pidfd_send_signal") as send, patch.object(
            network.select, "select", return_value=([], [], [])
        ) as wait, patch.object(network.os, "kill") as raw_signal:
            with self.assertRaisesRegex(network.NetworkError, "did not stop"):
                network._stop_owned_supplicant("wlan-test")
        self.assertTrue(pid_path.is_file())
        send.assert_called_once()
        self.assertEqual(wait.call_args.args[-1], 5)
        raw_signal.assert_not_called()

    def test_unrecognized_process_is_never_signaled(self):
        (self.run / "wpa-wlan-test.pid").write_text("44444")
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, read_fd)
        self.addCleanup(os.close, write_fd)
        with patch.object(network.os, "pidfd_open", side_effect=lambda pid: os.dup(read_fd)), patch.object(
            Path, "read_bytes", return_value=b"unrelated-process\0-i\0wlan-test"
        ), patch.object(network.signal, "pidfd_send_signal") as send, patch.object(network.select, "select", return_value=([], [], [])):
            with self.assertRaisesRegex(network.NetworkError, "unrecognized"):
                network._stop_owned_supplicant("wlan-test")
        send.assert_not_called()

    def test_stuck_old_daemon_prevents_any_new_supplicant_launch(self):
        with patch.object(network.shutil, "which", return_value=None), patch.object(network, "_command", side_effect=lambda name: name), patch.object(
            network, "_run", return_value=SimpleNamespace(returncode=0, stdout="")
        ) as run, patch.object(network, "_stop_owned_supplicant", side_effect=network.NetworkError("stop failed")):
            with self.assertRaises(network.NetworkError):
                network._connect_config("wlan-test", self.saved, timeout_seconds=3)
        self.assertFalse(any(call.args[0][0] == "wpa_supplicant" for call in run.call_args_list))

    def test_foreign_manager_is_not_replaced(self):
        with patch.object(network.shutil, "which", return_value=None), patch.object(network, "_command", side_effect=lambda name: name), patch.object(
            network, "_run", return_value=SimpleNamespace(returncode=0, stdout="")
        ) as run, patch.object(network, "_stop_packaged_supplicant_service", return_value=False), patch.object(network, "_stop_owned_supplicant"), patch.object(network, "_supplicant_status", return_value={"wpa_state": "COMPLETED"}):
            result = network._connect_config("wlan-test", self.saved, timeout_seconds=3)
        self.assertEqual(result["status"], "wifi-manager-conflict")
        self.assertFalse(any(call.args[0][0] == "wpa_supplicant" for call in run.call_args_list))

    def test_dhcp_is_reconfigured_once_not_on_every_poll(self):
        with patch.object(network.shutil, "which", side_effect=lambda name: name if name == "networkctl" else None), patch.object(
            network, "_command", side_effect=lambda name: name
        ), patch.object(network, "_run", return_value=SimpleNamespace(returncode=0, stdout="")) as run, patch.object(
            network, "_stop_packaged_supplicant_service", return_value=False
        ), patch.object(
            network, "_stop_owned_supplicant"
        ), patch.object(network, "_supplicant_status", return_value={}), patch.object(
            network, "_connection_state", side_effect=[{"online": False}, {"online": False}, {"online": True}]
        ), patch.object(network.time, "sleep"):
            result = network._connect_config("wlan-test", self.saved, timeout_seconds=3)
        self.assertTrue(result["online"])
        self.assertEqual(sum(call.args[0] == ["networkctl", "reconfigure", "wlan-test"] for call in run.call_args_list), 1)

    def test_association_address_route_dns_and_tcp_have_distinct_results(self):
        base = {"online": True, "ip": "192.168.1.5", "route_matches_interface": True, "dns_github": True, "github_tcp_443": True, "probe_status": "complete"}
        cases = [({}, {"wpa_state": "SCANNING"}, "wifi-association-pending"),
                 ({"ip": None}, {"wpa_state": "COMPLETED"}, "wifi-address-pending"),
                 ({"route_matches_interface": False}, {"wpa_state": "COMPLETED"}, "wifi-route-pending"),
                 ({"dns_github": False}, {"wpa_state": "COMPLETED"}, "wifi-dns-unavailable"),
                 ({"github_tcp_443": False}, {"wpa_state": "COMPLETED"}, "wifi-internet-unreachable")]
        for changes, association, expected in cases:
            with self.subTest(expected=expected), patch.object(network, "network_status", return_value={**base, **changes, "online": False}), patch.object(network, "_supplicant_status", return_value=association):
                result = network._connection_state("wlan-test")
            self.assertEqual(result["status"], expected)
            self.assertFalse(result["online"])

    def test_probe_is_a_bounded_child_bound_to_exact_interface_and_source(self):
        with patch.object(network, "_run", return_value=SimpleNamespace(returncode=0, stdout='{"dns_github":true,"github_tcp_443":true,"probe_status":"complete"}')) as run:
            self.assertTrue(network._internet_probe("wlan-test", "192.168.1.5")["github_tcp_443"])
        self.assertEqual(run.call_args.kwargs["timeout"], 5)
        self.assertEqual(run.call_args.args[0][-2:], ["wlan-test", "192.168.1.5"])
        self.assertIn("SO_BINDTODEVICE", run.call_args.args[0][2])
        with patch.object(network, "_run", side_effect=network.NetworkError("synthetic timeout")):
            self.assertEqual(network._internet_probe("wlan-test", "192.168.1.5")["probe_status"], "timeout-or-unavailable")

    def test_real_stalled_resolver_child_is_timed_out_without_network_io(self):
        original_run = network._run
        def stalled_run(arguments, **kwargs):
            replaced = list(arguments)
            replaced[2] = "import socket,time\nsocket.getaddrinfo=lambda *a,**k: time.sleep(30)\n" + replaced[2]
            return original_run(replaced, **kwargs)
        started = time.monotonic()
        with patch.object(network, "_run", side_effect=stalled_run):
            result = network._internet_probe("wlan-test", "192.168.1.5")
        self.assertEqual(result["probe_status"], "timeout-or-unavailable")
        self.assertLess(time.monotonic() - started, 8)

    def test_online_rejects_link_local_and_wrong_interface_even_with_passing_probe(self):
        for address, route in (
            ("169.254.1.2", "1.1.1.1 dev wlan-test src 169.254.1.2"),
            ("192.168.1.5", "1.1.1.1 dev eth0 src 10.0.0.5"),
        ):
            with self.subTest(address=address), patch.object(network.shutil, "which", return_value="ip"), patch.object(
                network, "_run", return_value=SimpleNamespace(returncode=0, stdout=route)
            ), patch.object(network, "_addresses", return_value=[f"wlan-test:{address}"]), patch.object(
                network, "_internet_probe", return_value={"dns_github": True, "github_tcp_443": True, "probe_status": "complete"}
            ) as probe:
                self.assertFalse(network.network_status("wlan-test")["online"])
                probe.assert_not_called()

    def test_route_and_probe_are_explicitly_selected_even_with_ethernet_available(self):
        with patch.object(network.shutil, "which", return_value="ip"), patch.object(
            network, "_run", return_value=SimpleNamespace(returncode=0, stdout="1.1.1.1 dev wlan-test src 192.168.1.5")
        ) as run, patch.object(network, "_addresses", return_value=["wlan-test:192.168.1.5"]), patch.object(
            network, "_internet_probe", return_value={"dns_github": True, "github_tcp_443": True, "probe_status": "complete"}
        ) as probe:
            self.assertTrue(network.network_status("wlan-test")["online"])
        self.assertIn(unittest.mock.call(["ip", "route", "get", "1.1.1.1", "oif", "wlan-test"], timeout=2), run.call_args_list)
        probe.assert_called_once_with("wlan-test", "192.168.1.5")


if __name__ == "__main__":
    unittest.main(verbosity=2)
