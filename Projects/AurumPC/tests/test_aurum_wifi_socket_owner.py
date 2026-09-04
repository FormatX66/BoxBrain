"""Synthetic process records and real temporary UNIX sockets; no host networking."""
from contextlib import ExitStack
import os
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
import aurum_network as network


@unittest.skipUnless(sys.platform == "linux", "Linux process and UNIX socket ownership")
class WifiSocketOwnerTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.proc = self.root / "proc"
        self.control = self.root / "ctrl"
        self.run = self.root / "run"
        for directory in (self.proc / "net", self.control, self.run):
            directory.mkdir(parents=True, exist_ok=True)
        self.table = self.proc / "net" / "unix"
        self.table.write_text("Num RefCount Protocol Flags Type St Inode Path\n")
        self.saved = self.root / "saved.conf"
        for name, value in (("PROC_ROOT", self.proc), ("CONTROL_DIR", self.control),
                            ("RUN_DIR", self.run), ("SAVED_WIFI", self.saved)):
            self.stack.enter_context(patch.object(network, name, value))

    def args(self):
        return ["/sbin/wpa_supplicant", "-B", "-D", "nl80211,wext", "-i", "wlan-test",
                "-c", str(self.saved), "-P", str(self.run / "wpa-wlan-test.pid")]

    def record(self, pid=44444, inode="9001"):
        directory = self.proc / str(pid)
        (directory / "fd").mkdir(parents=True)
        (directory / "cmdline").write_bytes("\0".join(self.args()).encode())
        self.table.write_text(f"0000: 00000002 00000000 00000000 0002 01 {inode} {self.control / 'wlan-test'}\n")
        return directory

    def test_missing_pid_record_discovers_only_proven_socket_owner(self):
        self.record()
        (self.proc / "55555").mkdir()
        with patch.object(network, "_orphan_identity_matches", side_effect=lambda pid, iface, inode: pid == 44444):
            self.assertEqual(network._find_owned_orphan_supplicant("wlan-test"), (44444, "9001"))
        self.assertFalse((self.run / "wpa-wlan-test.pid").exists())

    def test_other_interfaces_and_unnamed_sockets_are_not_adopted(self):
        self.table.write_text("0000: 00000002 00000000 00000000 0002 01 9001 /run/unrelated\n")
        with patch.object(network, "_orphan_identity_matches") as inspect:
            self.assertIsNone(network._find_owned_orphan_supplicant("wlan-test"))
        inspect.assert_not_called()

    def test_ambiguous_owner_is_refused(self):
        self.record()
        (self.proc / "55555").mkdir()
        with patch.object(network, "_orphan_identity_matches", return_value=True):
            with self.assertRaisesRegex(network.NetworkError, "ambiguous"):
                network._find_owned_orphan_supplicant("wlan-test")

    def test_exact_args_reject_other_config_interface_and_multi_interface_process(self):
        original = self.args()
        self.assertTrue(network._aurum_supplicant_arguments(original, "wlan-test"))
        for changed in (original + ["-N"], original + ["-i", "wlan-test"],
                        ["/sbin/other", *original[1:]],
                        [value.replace("wlan-test", "wlan-other") for value in original],
                        ["/etc/other.conf" if value == str(self.saved) else value for value in original]):
            self.assertFalse(network._aurum_supplicant_arguments(changed, "wlan-test"))

    def test_orphan_requires_root_exact_executable_and_actual_socket_descriptor(self):
        directory = self.record()
        executable = self.root / "wpa_supplicant"
        executable.write_text("synthetic fixture, never executed")
        (directory / "exe").symlink_to(executable)
        (directory / "fd" / "5").symlink_to("socket:[9001]")
        original_stat = Path.stat
        def fake_stat(path, *args, **kwargs):
            return SimpleNamespace(st_uid=0) if path == directory else original_stat(path, *args, **kwargs)
        with patch.object(network, "_command", return_value=str(executable)), patch.object(Path, "stat", fake_stat):
            self.assertTrue(network._orphan_identity_matches(44444, "wlan-test", "9001"))
            self.assertFalse(network._orphan_identity_matches(44444, "wlan-test", "9002"))
            with patch.object(network, "_command", return_value=str(self.root / "missing-binary")):
                self.assertFalse(network._orphan_identity_matches(44444, "wlan-test", "9001"))
        with patch.object(Path, "stat", return_value=SimpleNamespace(st_uid=1234)):
            self.assertFalse(network._orphan_identity_matches(44444, "wlan-test", "9001"))

    def test_adopted_owner_is_revalidated_after_pid_handle_is_acquired(self):
        self.record()
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, read_fd)
        self.addCleanup(os.close, write_fd)
        with patch.object(network, "_find_owned_orphan_supplicant", return_value=(44444, "9001")), \
             patch.object(network.os, "pidfd_open", side_effect=lambda pid: os.dup(read_fd)), \
             patch.object(network, "_orphan_identity_matches", return_value=False), \
             patch.object(network.select, "select", return_value=([], [], [])), \
             patch.object(network.signal, "pidfd_send_signal") as signal:
            with self.assertRaisesRegex(network.NetworkError, "unrecognized"):
                network._stop_owned_supplicant("wlan-test")
        signal.assert_not_called()

    def test_dead_pid_record_still_checks_for_an_orphan_without_deleting_record(self):
        pid_path = self.run / "wpa-wlan-test.pid"
        pid_path.write_text("44444")
        with patch.object(network.os, "pidfd_open", side_effect=ProcessLookupError), \
             patch.object(network, "_find_owned_orphan_supplicant", return_value=None) as find, \
             patch.object(network.signal, "pidfd_send_signal") as signal:
            network._stop_owned_supplicant("wlan-test")
        find.assert_called_once_with("wlan-test")
        signal.assert_not_called()
        self.assertEqual(pid_path.read_text(), "44444")

    def test_descriptor_inspection_refuses_an_incomplete_snapshot(self):
        directory = self.record()
        executable = self.root / "wpa_supplicant"
        executable.write_text("synthetic fixture, never executed")
        (directory / "exe").symlink_to(executable)
        original_stat = Path.stat
        original_iterdir = Path.iterdir
        original_readlink = os.readlink
        def fake_stat(path, *args, **kwargs):
            return SimpleNamespace(st_uid=0) if path == directory else original_stat(path, *args, **kwargs)
        def fake_iterdir(path):
            return iter([path / "5"] * 257) if path == directory / "fd" else original_iterdir(path)
        def fake_readlink(path, *args, **kwargs):
            return "socket:[unrelated]" if Path(path).parent == directory / "fd" else original_readlink(path, *args, **kwargs)
        with patch.object(network, "_command", return_value=str(executable)), \
             patch.object(Path, "stat", fake_stat), patch.object(Path, "iterdir", fake_iterdir), \
             patch.object(network.os, "readlink", side_effect=fake_readlink):
            with self.assertRaisesRegex(network.NetworkError, "inspection incomplete"):
                network._orphan_identity_matches(44444, "wlan-test", "9001")

    def test_proven_orphan_is_signaled_by_handle_and_waited_without_socket_unlink(self):
        self.record()
        socket_path = self.control / "wlan-test"
        server = self.stack.enter_context(socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM))
        server.bind(str(socket_path))
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, read_fd)
        self.addCleanup(os.close, write_fd)
        with patch.object(network, "_find_owned_orphan_supplicant", return_value=(44444, "9001")), \
             patch.object(network.os, "pidfd_open", side_effect=lambda pid: os.dup(read_fd)), \
             patch.object(network, "_orphan_identity_matches", return_value=True), \
             patch.object(network.select, "select", return_value=([read_fd], [], [])) as wait, \
             patch.object(network.signal, "pidfd_send_signal") as signal, \
             patch.object(network.os, "kill") as raw_signal:
            network._stop_owned_supplicant("wlan-test")
        signal.assert_called_once()
        self.assertEqual(wait.call_args.args[-1], 5)
        raw_signal.assert_not_called()
        self.assertTrue(socket_path.exists())

    def test_real_bound_socket_is_detected_even_without_responding_to_ping(self):
        server = self.stack.enter_context(socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM))
        path = self.control / "wlan-test"
        server.bind(str(path))
        self.assertTrue(network._control_socket_is_bound("wlan-test"))
        self.assertTrue(path.exists())

    def test_unbound_stale_socket_and_missing_socket_are_never_deleted(self):
        path = self.control / "wlan-test"
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as server:
            server.bind(str(path))
        self.assertFalse(network._control_socket_is_bound("wlan-test"))
        self.assertTrue(path.exists())
        self.assertFalse(network._control_socket_is_bound("missing"))

    def test_bound_foreign_socket_prevents_new_daemon_when_status_is_unresponsive(self):
        server = self.stack.enter_context(socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM))
        server.bind(str(self.control / "wlan-test"))
        with patch.object(network, "wireless_interfaces", return_value=["wlan-test"]), \
             patch.object(network, "_stop_owned_supplicant"), \
             patch.object(network, "_supplicant_status", return_value={}), \
             patch.object(network.shutil, "which", return_value=None), \
             patch.object(network, "_command", side_effect=lambda name: name), \
             patch.object(network, "_run", return_value=SimpleNamespace(returncode=0, stdout="")) as run:
            result = network._connect_config("wlan-test", self.saved, timeout_seconds=2)
        self.assertEqual(result["status"], "wifi-manager-conflict")
        self.assertFalse(any(call.args[0][0] == "wpa_supplicant" for call in run.call_args_list))

    def test_startup_collision_is_classified_without_returning_raw_diagnostic_text(self):
        def run(arguments, **kwargs):
            if "wpa_supplicant" in arguments:
                return SimpleNamespace(returncode=1, stdout="ctrl_iface exists and seems to be in use secret-fixture")
            return SimpleNamespace(returncode=0, stdout="")
        with patch.object(network, "wireless_interfaces", return_value=["wlan-test"]), \
             patch.object(network, "_stop_owned_supplicant"), \
             patch.object(network, "_supplicant_status", return_value={}), \
             patch.object(network.shutil, "which", return_value=None), \
             patch.object(network, "_command", side_effect=lambda name: name), \
             patch.object(network, "_run", side_effect=run):
            result = network._connect_config("wlan-test", self.saved, timeout_seconds=2)
        self.assertEqual(result["status"], "wifi-manager-conflict")
        self.assertNotIn("secret-fixture", str(result))


if __name__ == "__main__":
    unittest.main()
