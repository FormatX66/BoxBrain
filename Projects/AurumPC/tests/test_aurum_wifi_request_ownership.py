"""No hardware access: all requests and connection subprocesses are mocked."""
from concurrent.futures import Future
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1]))
import aurum_network as network
import aurum_setup_gui as setup


class WifiRequestOwnershipTests(unittest.TestCase):
    def gui(self):
        gui = setup.AurumSetupGui.__new__(setup.AurumSetupGui)
        gui.executor = Mock()
        gui.executor.submit.side_effect = lambda *args: Future()
        gui.network_future = None
        gui.network_operation = None
        gui.scan_after_status = False
        gui.selected_ssid = "Synthetic network"
        gui.password = "synthetic-test-only"
        gui.password_focus = True
        gui.wifi_interface = "wlan-test"
        gui.view = "wifi"
        gui.focus_key = None
        gui.network_message = ""
        gui.ssids = [gui.selected_ssid]
        gui.network_online = False
        return gui

    def test_repeated_connect_cannot_submit_a_second_empty_password(self):
        gui = self.gui()
        gui._connect()
        first = gui.network_future
        message = gui.network_message
        gui._connect()
        gui.executor.submit.assert_called_once_with(setup.connect_wifi, "Synthetic network", "synthetic-test-only", "wlan-test")
        self.assertIs(gui.network_future, first)
        self.assertEqual(gui.network_message, message)
        self.assertEqual(gui.password, "synthetic-test-only")

    def test_backend_busy_keeps_masked_password_without_automatic_retry(self):
        gui = self.gui()
        gui._connect()
        gui.network_future.set_result({"status": "wifi-operation-busy", "online": False})
        gui._poll_network()
        self.assertEqual(gui.password, "synthetic-test-only")
        self.assertEqual(gui.executor.submit.call_count, 1)

    def test_finished_connection_clears_password(self):
        gui = self.gui()
        gui._connect()
        gui.network_future.set_result({"status": "online", "online": True})
        gui._poll_network()
        self.assertEqual(gui.password, "")

    def test_rescan_preserves_pending_connection_and_its_message(self):
        gui = self.gui()
        gui._connect()
        first = gui.network_future
        message = gui.network_message
        gui._open_wifi()
        self.assertEqual(gui.executor.submit.call_count, 1)
        self.assertIs(gui.network_future, first)
        self.assertEqual(gui.network_message, message)
        self.assertEqual(gui.ssids, ["Synthetic network"])

    def test_completed_result_is_consumed_before_another_request(self):
        gui = self.gui()
        gui._connect()
        gui.network_future.set_result({"status": "online", "online": True})
        gui._open_wifi()
        self.assertEqual(gui.executor.submit.call_count, 1)
        gui._poll_network()
        self.assertTrue(gui.network_online)
        gui._open_wifi()
        self.assertEqual(gui.executor.submit.call_count, 2)

    def test_back_and_reopen_do_not_replace_a_connection(self):
        gui = self.gui()
        gui._connect()
        first = gui.network_future
        gui._set_view("setup")
        gui._open_wifi()
        self.assertEqual(gui.view, "wifi")
        self.assertIs(gui.network_future, first)
        self.assertEqual(gui.executor.submit.call_count, 1)

    def test_exception_releases_ownership_and_allows_new_user_attempt(self):
        gui = self.gui()
        gui._connect()
        gui.network_future.set_exception(RuntimeError("synthetic failure"))
        gui._poll_network()
        self.assertFalse(gui._network_busy())
        gui.password = "new-synthetic-test-only"
        gui._connect()
        self.assertEqual(gui.executor.submit.call_count, 2)

    def test_direct_submit_cannot_replace_an_existing_request(self):
        gui = self.gui()
        self.assertTrue(gui._submit_network(setup.network_status))
        first = gui.network_future
        self.assertFalse(gui._submit_network(setup.scan_networks))
        self.assertIs(gui.network_future, first)

    def test_selection_cannot_change_during_a_connection(self):
        gui = self.gui()
        gui._connect()
        gui._select_ssid("Different network")
        self.assertEqual(gui.selected_ssid, "Synthetic network")

    def test_open_wifi_during_initial_status_automatically_scans_when_ready(self):
        gui = self.gui()
        gui._submit_network(setup.network_status)
        first = gui.network_future
        gui._open_wifi()
        gui._open_wifi()
        self.assertEqual(gui.executor.submit.call_count, 1)
        first.set_result({"online": False})
        gui._poll_network()
        self.assertEqual(gui.executor.submit.call_count, 2)
        gui.executor.submit.assert_called_with(setup.scan_networks)
        self.assertFalse(gui.scan_after_status)

    def test_back_cancels_a_scan_queued_behind_initial_status(self):
        gui = self.gui()
        gui._submit_network(setup.network_status)
        first = gui.network_future
        gui._open_wifi()
        gui._set_view("setup")
        first.set_result({"online": False})
        gui._poll_network()
        self.assertEqual(gui.executor.submit.call_count, 1)
        self.assertFalse(gui.scan_after_status)

    def test_failed_initial_status_still_allows_the_requested_scan(self):
        gui = self.gui()
        gui._submit_network(setup.network_status)
        first = gui.network_future
        gui._open_wifi()
        first.set_exception(RuntimeError("synthetic status failure"))
        gui._poll_network()
        gui.executor.submit.assert_called_with(setup.scan_networks)

    def test_timeout_without_association_does_not_claim_connected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "wifi.conf"
            config.touch()
            with (
                patch.object(network, "RUN_DIR", root),
                patch.object(network, "SAVED_WIFI", config),
                patch.object(network, "wireless_interfaces", return_value=["wlan-test"]),
                patch.object(network, "_command", side_effect=lambda value: value),
                patch.object(network.shutil, "which", return_value=None),
                patch.object(network, "_stop_owned_supplicant"),
                patch.object(network, "_supplicant_status", return_value={}),
                patch.object(network, "_run", return_value=subprocess.CompletedProcess([], 0, "")),
                patch.object(network, "network_status", return_value={"online": False, "addresses": [], "route_probe": ""}),
            ):
                result = network.connect_saved("wlan-test", timeout_seconds=0)
            self.assertEqual(result["status"], "wifi-connection-unverified")
            self.assertFalse(result["online"])
            self.assertIn("could not be verified", setup._friendly_reason(result["status"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
