from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Projects.AurumPC.aurum_wifi_persistence import capture, verify, write_receipt


class AurumWifiPersistenceTests(unittest.TestCase):
    def test_profiles_and_online_state_survive_without_disclosing_ssid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            system = root / "system"
            state.mkdir()
            nm = system / "etc/NetworkManager/system-connections"
            nm.mkdir(parents=True)
            (state / "wifi.conf").write_text(
                'network={\n\tssid="private-network"\n\tpsk=abcdef\n}\n',
                encoding="utf-8",
            )
            (nm / "private-network.nmconnection").write_text(
                "[connection]\nid=private-network\n",
                encoding="utf-8",
            )
            before = capture(
                state_dir=state,
                system_root=system,
                network={"online": True, "interface": "wlan0", "wireless_interfaces": ["wlan0"]},
            )
            after = capture(
                state_dir=state,
                system_root=system,
                network={"online": True, "interface": "wlan0", "wireless_interfaces": ["wlan0"]},
            )
            proof = verify(before, after)
            receipt = state / "wifi-persistence.json"
            write_receipt(receipt, proof)

            self.assertEqual(proof["status"], "passed")
            self.assertTrue(proof["profiles_unchanged"])
            self.assertTrue(proof["online_retained"])
            receipt_text = receipt.read_text(encoding="utf-8")
            self.assertNotIn("private-network", receipt_text)
            self.assertNotIn("abcdef", receipt_text)

    def test_profile_or_online_loss_fails_closed(self) -> None:
        before = {
            "configured": True,
            "profiles": [{"identity_sha256": "a", "content_sha256": "one"}],
            "network": {"online": True, "interface": "wlan0"},
        }
        after = {
            "configured": False,
            "profiles": [],
            "network": {"online": False, "interface": None},
        }
        proof = verify(before, after)
        self.assertEqual(proof["status"], "failed")
        self.assertFalse(proof["profiles_unchanged"])
        self.assertFalse(proof["configured_retained"])
        self.assertFalse(proof["online_retained"])


if __name__ == "__main__":
    unittest.main()
