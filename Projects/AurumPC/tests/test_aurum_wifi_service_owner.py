"""No real services: launch contract, dependency gate and cleanup race fixtures."""
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
import aurum_network as network


class WifiServiceOwnerTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(network, "RUN_DIR", self.root))
        self.stack.enter_context(patch.object(network, "PROC_ROOT", self.root / "proc"))
        self.unit = "aurum-wifi-" + "a" * 32 + ".service"

    def test_launch_has_independent_service_pid_tracking_and_bounded_start(self):
        with patch.object(network, "_command", side_effect=lambda name: "/usr/bin/" + name), \
             patch.object(network, "_run", return_value=SimpleNamespace(returncode=0, stdout="")) as run:
            network._start_owned_supplicant("wlan-test", self.root / "candidate.conf", "/usr/bin/systemd-run")
        args = run.call_args.args[0]
        self.assertEqual(args[0], "/usr/bin/systemd-run")
        for flag in ("--collect", "--no-ask-password", "--service-type=forking", "--property=Restart=no",
                     "--property=KillMode=control-group", "--property=TimeoutStartSec=8", "--property=UMask=0077",
                     f"--property=PIDFile={self.root / 'wpa-wlan-test.pid'}"):
            self.assertIn(flag, args)
        self.assertNotIn("--scope", args)
        self.assertNotIn("--no-block", args)
        self.assertEqual(args[args.index("--") + 1:], ["/usr/bin/wpa_supplicant", "-B", "-D", "nl80211,wext",
                         "-i", "wlan-test", "-c", str(self.root / "candidate.conf"), "-P", str(self.root / "wpa-wlan-test.pid")])
        tracked = (self.root / "wpa-wlan-test.unit").read_text().strip()
        self.assertIn("--unit=" + tracked, args)
        self.assertEqual(run.call_args.kwargs["timeout"], 15)

    def test_dependency_failure_does_not_stop_existing_connection(self):
        with patch.object(network, "wireless_interfaces", return_value=["wlan-test"]), \
             patch.object(network, "_command", side_effect=network.NetworkError("missing manager")), \
             patch.object(network, "_stop_owned_supplicant") as stop, patch.object(network, "_run") as run:
            with self.assertRaises(network.NetworkError):
                network._connect_config("wlan-test", self.root / "candidate.conf", timeout_seconds=3)
        stop.assert_not_called()
        run.assert_not_called()

    def test_cgroup_recognizes_only_exact_generated_wifi_units(self):
        process = self.root / "proc" / "55555"
        process.mkdir(parents=True)
        record = process / "cgroup"
        record.write_text(f"0::/system.slice/{self.unit}\n")
        self.assertEqual(network._managed_supplicant_unit(55555), self.unit)
        for other in ("aurum-pc-console.service", "NetworkManager.service", "aurum-wifi-unknown.service"):
            record.write_text(f"0::/system.slice/{other}\n")
            self.assertIsNone(network._managed_supplicant_unit(55555))

    def test_cleanup_waits_for_inactive_without_signaling_any_unit(self):
        values = ["LoadState=loaded\nActiveState=deactivating\n", "LoadState=loaded\nActiveState=inactive\n"]
        with patch.object(network, "_command", side_effect=lambda name: name), \
             patch.object(network, "_run", side_effect=[SimpleNamespace(returncode=0, stdout=v) for v in values]) as run, \
             patch.object(network.time, "sleep"):
            network._wait_owned_unit_cleanup(self.unit)
        self.assertEqual(run.call_count, 2)
        self.assertTrue(all(call.args[0][1] == "show" for call in run.call_args_list))

    def test_cleanup_failure_refuses_replacement(self):
        with patch.object(network, "_command", side_effect=lambda name: name), \
             patch.object(network, "_run", return_value=SimpleNamespace(returncode=1, stdout="")), \
             patch.object(network.time, "monotonic", side_effect=[0, 4]):
            with self.assertRaisesRegex(network.NetworkError, "cleanup incomplete"):
                network._wait_owned_unit_cleanup(self.unit)

    def test_collected_unit_is_already_clean(self):
        with patch.object(network, "_command", side_effect=lambda name: name), \
             patch.object(network, "_run", return_value=SimpleNamespace(returncode=1, stdout="LoadState=not-found\n")):
            network._wait_owned_unit_cleanup(self.unit)

    def test_exact_packaged_supplicant_is_stopped_through_its_unit(self):
        responses = [
            SimpleNamespace(returncode=0, stdout="LoadState=loaded\nActiveState=active\nMainPID=44444\n"),
            SimpleNamespace(returncode=0, stdout=""),
            SimpleNamespace(returncode=0, stdout="LoadState=loaded\nActiveState=inactive\n"),
        ]
        with patch.object(network, "_run", side_effect=responses) as run, \
             patch.object(network, "_packaged_supplicant_owner", return_value=True):
            self.assertTrue(network._stop_packaged_supplicant_service("/usr/bin/systemctl"))
        self.assertEqual(run.call_args_list[1].args[0], [
            "/usr/bin/systemctl", "stop", "wpa_supplicant.service",
        ])

    def test_packaged_owner_requires_root_binary_args_and_cgroup(self):
        process = self.root / "proc" / "44444"
        process.mkdir(parents=True)
        executable = self.root / "wpa_supplicant"
        executable.write_text("synthetic fixture, never executed")
        (process / "exe").symlink_to(executable)
        arguments = [str(executable), *network.PACKAGED_SUPPLICANT_ARGUMENTS]
        (process / "cmdline").write_bytes("\0".join(arguments).encode())
        (process / "cgroup").write_text("0::/system.slice/wpa_supplicant.service\n")
        original_stat = Path.stat

        def fake_stat(path, *args, **kwargs):
            return SimpleNamespace(st_uid=0) if path == process else original_stat(path, *args, **kwargs)

        with patch.object(network, "_command", return_value=str(executable)), \
             patch.object(Path, "stat", fake_stat):
            self.assertTrue(network._packaged_supplicant_owner(44444))
            (process / "cgroup").write_text("0::/system.slice/NetworkManager.service\n")
            self.assertFalse(network._packaged_supplicant_owner(44444))
            (process / "cgroup").write_text("0::/system.slice/wpa_supplicant.service\n")
            (process / "cmdline").write_bytes("\0".join([str(executable), "-i", "wlan-test"]).encode())
            self.assertFalse(network._packaged_supplicant_owner(44444))

    def test_unrecognized_packaged_main_pid_is_never_stopped(self):
        active = SimpleNamespace(
            returncode=0,
            stdout="LoadState=loaded\nActiveState=active\nMainPID=44444\n",
        )
        with patch.object(network, "_run", return_value=active) as run, \
             patch.object(network, "_packaged_supplicant_owner", return_value=False):
            with self.assertRaisesRegex(network.NetworkError, "unrecognized"):
                network._stop_packaged_supplicant_service("/usr/bin/systemctl")
        self.assertEqual(run.call_count, 1)

    @unittest.skipUnless(sys.platform == "linux", "Linux PID handles")
    def test_lost_pid_record_still_waits_for_tracked_service_cleanup(self):
        record = self.root / "wpa-wlan-test.unit"
        record.write_text(self.unit)
        with patch.object(network, "_find_owned_orphan_supplicant", return_value=None), \
             patch.object(network, "_wait_owned_unit_cleanup") as wait:
            network._stop_owned_supplicant("wlan-test")
        wait.assert_called_once_with(self.unit)
        self.assertFalse(record.exists())

    def test_invalid_service_record_never_operates_on_other_unit(self):
        (self.root / "wpa-wlan-test.unit").write_text("NetworkManager.service")
        with patch.object(network, "_run") as run:
            with self.assertRaisesRegex(network.NetworkError, "invalid"):
                network._stop_owned_supplicant("wlan-test")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
