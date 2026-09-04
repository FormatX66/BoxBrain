from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Projects.AurumPC.aurum_wifi_persistence import capture, storage_evidence, verify, write_receipt


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
                network={"online": True, "interface": "wlan0", "wireless_interfaces": ["wlan0"], "associated": True, "route_matches_interface": True},
                storage={"status": "durable", "cross_boot_capable": True, "filesystem": "ext4"},
                boot_identity_sha256="boot-before",
            )
            after = capture(
                state_dir=state,
                system_root=system,
                network={"online": True, "interface": "wlan0", "wireless_interfaces": ["wlan0"], "associated": True, "route_matches_interface": True},
                storage={"status": "durable", "cross_boot_capable": True, "filesystem": "ext4"},
                boot_identity_sha256="boot-after",
            )
            proof = verify(before, after)
            receipt = state / "wifi-persistence.json"
            write_receipt(receipt, proof)

            self.assertEqual(proof["status"], "passed")
            self.assertTrue(proof["profiles_unchanged"])
            self.assertTrue(proof["online_retained"])
            self.assertTrue(proof["cross_boot_capable"])
            receipt_text = receipt.read_text(encoding="utf-8")
            self.assertNotIn("private-network", receipt_text)
            self.assertNotIn("abcdef", receipt_text)

    def test_profile_or_online_loss_fails_closed(self) -> None:
        before = {
            "configured": True,
            "profiles": [{"identity_sha256": "a", "content_sha256": "one"}],
            "network": {"online": True, "interface": "wlan0", "wireless_verified": True},
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

    def test_live_overlay_is_pending_and_never_claims_reboot_persistence(self) -> None:
        profile = [{"identity_sha256": "a", "content_sha256": "one"}]
        snapshot = {
            "configured": True,
            "profiles": profile,
            "network": {"online": True, "interface": "wlan0", "wireless_verified": True},
            "storage": {
                "status": "volatile",
                "cross_boot_capable": False,
                "filesystem": "overlay",
            },
            "boot_identity_sha256": "same-boot",
        }

        proof = verify(snapshot, snapshot)

        self.assertEqual(proof["status"], "pending-reboot-storage")
        self.assertTrue(proof["same_session_passed"])
        self.assertFalse(proof["cross_boot_capable"])

    def test_mount_evidence_distinguishes_installed_and_live_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mountinfo = root / "mountinfo"
            mountinfo.write_text(
                "1 0 8:2 / / rw - ext4 /dev/nvme0n1p2 rw\n"
                "2 1 0:42 / /live rw - overlay overlay rw\n",
                encoding="utf-8",
            )

            installed = storage_evidence(Path("/var/lib/aurum/state"), mountinfo_path=mountinfo)
            live = storage_evidence(Path("/live/var/lib/aurum/state"), mountinfo_path=mountinfo)

        self.assertTrue(installed["cross_boot_capable"])
        self.assertFalse(live["cross_boot_capable"])


if __name__ == "__main__":
    unittest.main()
