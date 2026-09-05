from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]


class WifiServiceOwnerTests(unittest.TestCase):
    def test_image_has_one_connection_manager(self) -> None:
        script = (ROOT / "build-iso.sh").read_text(encoding="utf-8")
        self.assertIn("network-manager", script)
        self.assertIn("multi-user.target.wants/NetworkManager.service", script)
        self.assertIn("ln -sfn /dev/null /etc/systemd/system/systemd-networkd.service", script)
        self.assertIn("ln -sfn /dev/null /etc/systemd/system/systemd-networkd.socket", script)
        self.assertIn("ln -sfn /dev/null /etc/systemd/system/NetworkManager-wait-online.service", script)
        self.assertNotIn("multi-user.target.wants/aurum-network-bootstrap.service", script)
        self.assertNotIn("dbus-fi.w1.wpa_supplicant1.service", script)

    def test_boot_unit_observes_manager_and_does_not_connect(self) -> None:
        service = (ROOT / "runtime-assets/etc/systemd/system/aurum-network-ready.service").read_text(encoding="utf-8")
        self.assertIn("After=local-fs.target systemd-udev-trigger.service NetworkManager.service", service)
        self.assertIn("Wants=NetworkManager.service", service)
        self.assertIn("--boot-status", service)
        self.assertNotIn("--reconnect-saved", service)
        self.assertIn("TimeoutStartSec=20", service)

    def test_gui_and_sync_order_after_manager_without_gating_gui_on_online(self) -> None:
        setup = (ROOT / "runtime-assets/etc/systemd/system/aurum-setup.service").read_text(encoding="utf-8")
        sync = (ROOT / "runtime-assets/etc/systemd/system/aurum-auto-sync.service").read_text(encoding="utf-8")
        self.assertIn("Wants=aurum-input-bootstrap.service NetworkManager.service", setup)
        self.assertNotIn("network-online.target", setup)
        self.assertIn("After=network-online.target aurum-network-ready.service", sync)


if __name__ == "__main__":
    unittest.main()
