from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
import aurum_network as network


class WifiLifecycleTests(unittest.TestCase):
    def test_failed_candidate_is_removed_and_prior_profile_is_restored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate_root = root / "run"
            profile_uuid = "11111111-1111-4111-8111-111111111111"
            with (
                patch.object(network, "_operation_lock", return_value=nullcontext()),
                patch.object(network, "RUNTIME_CONNECTIONS", candidate_root),
                patch.object(network, "SYSTEM_CONNECTIONS", root / "system"),
                patch.object(network, "wireless_interfaces", return_value=["wlan0"]),
                patch.object(network, "_manager_ready", return_value=True),
                patch.object(network, "_active_for", return_value={"UUID": "prior-uuid"}),
                patch.object(network.uuid, "uuid4", return_value=profile_uuid),
                patch.object(network, "_load_profile"),
                patch.object(network, "_activate_profile", return_value={"status": "wifi-association-failed", "online": False}),
                patch.object(network, "_remove_candidate") as remove,
                patch.object(network, "_restore_profile", return_value={"status": "online", "online": True}) as restore,
            ):
                result = network.connect_wifi("Test Network", "test-secret", "wlan0")
            candidate = candidate_root / f"{network.PROFILE_PREFIX}{profile_uuid}.nmconnection"
            self.assertFalse(result["online"])
            self.assertFalse(result["saved"])
            remove.assert_called_once_with(candidate, profile_uuid)
            restore.assert_called_once_with("prior-uuid", "wlan0")

    def test_saved_connection_uses_only_owned_persistent_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile_uuid = "22222222-2222-4222-8222-222222222222"
            profile = root / f"{network.PROFILE_PREFIX}{profile_uuid}.nmconnection"
            profile.write_text(f"[connection]\nuuid={profile_uuid}\n", encoding="utf-8")
            with (
                patch.object(network, "_operation_lock", return_value=nullcontext()),
                patch.object(network, "SYSTEM_CONNECTIONS", root),
                patch.object(network, "wireless_interfaces", return_value=["wlan0"]),
                patch.object(network, "_manager_ready", return_value=True),
                patch.object(network, "_connection_state", return_value={"status": "wifi-disconnected", "online": False}),
                patch.object(network, "_profile_ssid", return_value="Test Network"),
                patch.object(network, "_activate_profile", return_value={"status": "online", "online": True}) as activate,
            ):
                result = network.connect_saved("wlan0", timeout_seconds=25)
            self.assertTrue(result["online"])
            activate.assert_called_once_with(profile_uuid, "wlan0", "Test Network", timeout_seconds=25)

    def test_forget_deletes_only_aurum_owned_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            owned_uuid = "33333333-3333-4333-8333-333333333333"
            owned = root / f"{network.PROFILE_PREFIX}{owned_uuid}.nmconnection"
            unrelated = root / "user-home.nmconnection"
            owned.write_text(f"[connection]\nuuid={owned_uuid}\n", encoding="utf-8")
            unrelated.write_text("[connection]\nuuid=44444444-4444-4444-8444-444444444444\n", encoding="utf-8")
            calls: list[list[str]] = []

            def fake_nmcli(arguments, **_kwargs):
                calls.append(list(arguments))
                return subprocess.CompletedProcess(arguments, 0, "")

            with (
                patch.object(network, "_operation_lock", return_value=nullcontext()),
                patch.object(network, "SYSTEM_CONNECTIONS", root),
                patch.object(network, "RUNTIME_CONNECTIONS", root / "run"),
                patch.object(network, "wireless_interfaces", return_value=["wlan0"]),
                patch.object(network, "_manager_ready", return_value=True),
                patch.object(network, "_nmcli", side_effect=fake_nmcli),
            ):
                result = network.disconnect_wifi(forget=True)
            self.assertEqual(result["status"], "saved-network-forgotten")
            self.assertFalse(owned.exists())
            self.assertTrue(unrelated.exists())
            self.assertFalse(any("44444444-4444-4444-8444-444444444444" in call for call in calls))

    def test_text_recovery_never_prompts_for_credentials(self) -> None:
        with patch("builtins.input") as input_prompt:
            result = network.interactive_wifi_setup("wlan0")
        self.assertEqual(result["status"], "use-gui-wifi-setup")
        input_prompt.assert_not_called()

    def test_cleanup_failure_preserves_superseded_profile_for_later_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_uuid = "66666666-6666-4666-8666-666666666666"
            old = root / f"{network.PROFILE_PREFIX}{old_uuid}.nmconnection"
            old.write_text(f"[connection]\nuuid={old_uuid}\n", encoding="utf-8")

            def fake_nmcli(arguments, **_kwargs):
                returncode = 10 if "delete" in arguments else 0
                return subprocess.CompletedProcess(arguments, returncode, "")

            with (
                patch.object(network, "SYSTEM_CONNECTIONS", root),
                patch.object(network, "RUNTIME_CONNECTIONS", root / "run"),
                patch.object(network, "_nmcli", side_effect=fake_nmcli),
            ):
                complete = network._remove_superseded_profiles(
                    "77777777-7777-4777-8777-777777777777"
                )
            self.assertFalse(complete)
            self.assertTrue(old.exists())


if __name__ == "__main__":
    unittest.main()
