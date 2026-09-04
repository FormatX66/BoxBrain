from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parents[1]))
import aurum_network as network
import aurum_wifi_persistence as persistence
import aurum_runtime_update as runtime


class WifiProofInterfaceTests(unittest.TestCase):
    def snapshot(self, interface="wlan0", verified=True, online=True, boot="before"):
        return {"configured": True, "profiles": [{"identity_sha256": "a", "content_sha256": "same"}],
                "network": {"online": online, "interface": interface, "wireless_verified": verified},
                "storage": {"cross_boot_capable": True}, "boot_identity_sha256": boot}

    def test_ethernet_is_not_wifi_online_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            value = persistence.capture(state_dir=Path(directory), system_root=Path(directory),
                network={"online": True, "interface": "eth0", "wireless_interfaces": ["wlan0"],
                         "associated": True, "route_matches_interface": True})
        self.assertFalse(value["network"]["online"])

    def test_legacy_unqualified_online_receipts_never_prove_wifi(self):
        before = self.snapshot(interface="eth0", verified=False)
        after = self.snapshot(interface="eth0", verified=False, boot="after")
        before["network"].pop("wireless_verified")
        after["network"].pop("wireless_verified")
        self.assertNotEqual(persistence.verify(before, after)["status"], "passed")

    def test_saved_wifi_boot_request_is_not_skipped_because_ethernet_is_online(self):
        with patch.object(sys, "argv", ["aurum_network.py", "--reconnect-saved"]), \
             patch.object(network, "network_status", return_value={"online": True, "interface": "eth0"}), \
             patch.object(network, "wireless_interfaces", return_value=["wlan-test"]), \
             patch.object(network, "_connection_state", return_value={"online": False}), \
             patch.object(network, "connect_saved", return_value={"online": False, "status": "pending"}) as connect, \
             redirect_stdout(io.StringIO()):
            network.main()
        connect.assert_called_once()

    def test_first_verified_wireless_sample_requires_a_later_reboot(self):
        before = self.snapshot(verified=False, online=False)
        connected = self.snapshot(boot="connected-boot")
        initial = persistence.verify(before, connected)
        self.assertEqual(initial["status"], "pending-reboot-observation")
        self.assertEqual(initial["before"], before)
        self.assertEqual(initial["next_baseline"], connected)
        same_boot = persistence.verify(initial["next_baseline"], connected)
        self.assertEqual(same_boot["status"], "pending-reboot-observation")
        rebooted = self.snapshot(boot="later-boot")
        self.assertEqual(persistence.verify(initial["next_baseline"], rebooted)["status"], "passed")

    def test_new_baseline_never_hides_changed_profile_or_loss_of_real_wifi(self):
        before = self.snapshot(online=False, verified=False)
        changed = self.snapshot()
        changed["profiles"] = [{"content_sha256": "different"}]
        self.assertEqual(persistence.verify(before, changed)["status"], "failed")
        self.assertIsNone(persistence.verify(before, changed)["next_baseline"])
        self.assertEqual(persistence.verify(self.snapshot(), self.snapshot(online=False))["status"], "failed")

    def test_association_and_selected_route_are_both_required(self):
        with tempfile.TemporaryDirectory() as directory:
            for association, route in ((False, True), (True, False)):
                value = persistence.capture(state_dir=Path(directory), system_root=Path(directory),
                    network={"online": True, "interface": "wlan0", "wireless_interfaces": ["wlan0"],
                             "associated": association, "route_matches_interface": route})
                self.assertFalse(value["network"]["online"])

    def test_runtime_uses_read_only_candidate_wireless_collector_not_global_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            updater = runtime.RuntimeUpdater(workspace=root, target=root / "installed", state_dir=root / "state")
            updater.source.mkdir(parents=True)
            source = updater.source / "aurum_network.py"
            source.write_text("synthetic fixture, not executed")
            module = SimpleNamespace(wireless_interfaces=lambda: ["wlan-test"],
                                     _connection_state=Mock(return_value={"online": False}), network_status=Mock())
            with patch.object(updater, "_load_module", return_value=module) as load:
                self.assertFalse(updater._network_snapshot()["online"])
            self.assertEqual(load.call_args.args[0], source)
            module._connection_state.assert_called_once_with("wlan-test")
            module.network_status.assert_not_called()

    def test_runtime_next_reboot_check_uses_newly_observed_wireless_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            updater = runtime.RuntimeUpdater(workspace=root, target=root / "installed", state_dir=root / "state")
            old = self.snapshot(verified=False, online=False)
            fresh = self.snapshot(boot="first-connected")
            with patch.object(runtime, "_json_file", return_value={"before": old, "next_baseline": fresh}), \
                 patch.object(updater, "_wifi_persistence_proof", return_value={"status": "pending-reboot-observation"}) as prove:
                updater._wifi_reboot_proof()
            prove.assert_called_once_with(fresh)


if __name__ == "__main__":
    unittest.main()
