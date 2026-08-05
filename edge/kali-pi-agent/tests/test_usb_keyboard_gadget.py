from __future__ import annotations

import json
from pathlib import Path
import re
import unittest
from unittest.mock import Mock, patch

from boxbrain.cli import _usb_keyboard_request


ROOT = Path(__file__).resolve().parents[1]
COMPOSITE = (ROOT / "scripts" / "boxbrain-usb-composite.sh").read_text(
    encoding="utf-8"
)
CONFIGURE = (ROOT / "scripts" / "configure-usb-keyboard.sh").read_text(
    encoding="utf-8"
)
INSTALL = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
UPGRADE = (ROOT / "scripts" / "upgrade.sh").read_text(encoding="utf-8")
SERVICE = (ROOT / "systemd" / "boxbrain-usb-gadget.service").read_text(
    encoding="utf-8"
)
HID_KVM_SERVICE = (ROOT / "systemd" / "boxbrain-hid-kvm.service").read_text(
    encoding="utf-8"
)
ROLLBACK_SERVICE = (
    ROOT / "systemd" / "boxbrain-usb-gadget-rollback.service"
).read_text(encoding="utf-8")
ROLLBACK_TIMER = (
    ROOT / "systemd" / "boxbrain-usb-gadget-rollback.timer"
).read_text(encoding="utf-8")


class UsbHidGadgetTests(unittest.TestCase):
    def test_composite_preserves_ethernet_and_adds_keyboard_and_mouse(self) -> None:
        for expected in (
            "functions/rndis.usb0",
            "functions/hid.keyboard",
            "functions/hid.mouse",
            "usb_f_rndis",
            "usb_f_hid",
            'printf \'usb%%d\'',
            'printf \'8\' >"$gadget/functions/hid.keyboard/report_length"',
            'printf \'4\' >"$gadget/functions/hid.mouse/report_length"',
            "/dev/hidg0",
            "/dev/hidg1",
            "/sys/class/net/usb0",
            "BoxBrain USB Ethernet + Keyboard + Mouse",
        ):
            self.assertIn(expected, COMPOSITE)
        self.assertIn("modprobe g_ether", COMPOSITE)
        self.assertIn("legacy_fallback", COMPOSITE)
        self.assertNotIn("g_mass_storage", COMPOSITE)
        self.assertNotIn("functions/acm", COMPOSITE)
        descriptor = re.search(
            r"mouse_report_descriptor='([^']+)'",
            COMPOSITE,
        )
        self.assertIsNotNone(descriptor)
        self.assertEqual(len(re.findall(r"\\[0-7]{3}", descriptor.group(1))), 52)
        self.assertIn(
            'printf \'2\' >"$gadget/functions/hid.mouse/protocol"',
            COMPOSITE,
        )

    def test_migration_is_staged_with_alternate_access_and_timed_rollback(self) -> None:
        self.assertIn("STAGE USB HID", CONFIGURE)
        self.assertIn("COMMIT USB HID", CONFIGURE)
        self.assertIn("ROLL BACK USB HID", CONFIGURE)
        self.assertIn("A non-USB alternate management interface is required", CONFIGURE)
        self.assertIn("rollback-pending", CONFIGURE)
        self.assertIn("OnBootSec=15min", ROLLBACK_TIMER)
        self.assertIn("ConditionPathExists=/var/lib/boxbrain/usb-gadget/pending", ROLLBACK_SERVICE)
        self.assertNotIn("systemctl reboot", CONFIGURE)
        self.assertNotIn("shutdown", CONFIGURE)

    def test_systemd_builds_composite_before_network_manager(self) -> None:
        self.assertIn("Requires=sys-kernel-config.mount", SERVICE)
        self.assertIn("After=systemd-modules-load.service sys-kernel-config.mount", SERVICE)
        self.assertIn("Before=NetworkManager.service rpi-usb-gadget-ics.service", SERVICE)
        self.assertIn("ConditionPathExists=/etc/boxbrain/usb-keyboard-enabled", SERVICE)
        self.assertIn("ExecStart=/usr/local/libexec/boxbrain-usb-composite start", SERVICE)

    def test_hid_kvm_broker_is_installed_with_a_narrow_device_boundary(self) -> None:
        self.assertIn("boxbrain-hid-kvm.service", INSTALL)
        self.assertIn("/var/lib/boxbrain/hid-kvm", INSTALL)
        self.assertIn("DevicePolicy=closed", HID_KVM_SERVICE)
        self.assertIn("DeviceAllow=/dev/hidg0 rw", HID_KVM_SERVICE)
        self.assertIn("DeviceAllow=/dev/hidg1 rw", HID_KVM_SERVICE)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", HID_KVM_SERVICE)

    def test_default_install_is_inert_and_upgrade_is_rollback_complete(self) -> None:
        self.assertIn("boxbrain-usb-composite.sh", INSTALL)
        self.assertIn("configure-usb-keyboard.sh", INSTALL)
        self.assertIn("boxbrain-usb-gadget.service", INSTALL)
        self.assertNotIn("enable boxbrain-usb-gadget.service", INSTALL)
        for expected in (
            "usb_gadget_service_existed",
            "usb_rollback_service_existed",
            "usb_rollback_timer_existed",
            "usb_composite_helper_existed",
            "usb_configure_helper_existed",
        ):
            self.assertIn(expected, UPGRADE)

    def test_cli_invokes_only_the_fixed_configurator_without_a_shell(self) -> None:
        response = {
            "schema_version": 1,
            "action": "preview",
            "changed": False,
        }
        completed = Mock(
            returncode=0,
            stdout=json.dumps(response),
            stderr="",
        )
        with patch("boxbrain.cli.subprocess.run", return_value=completed) as run:
            result = _usb_keyboard_request(
                "preview",
                authorized=False,
                confirmation="",
                alternate_interface="wlan0",
            )

        self.assertEqual(result, response)
        arguments, keywords = run.call_args
        self.assertEqual(
            arguments[0],
            ["/usr/local/sbin/boxbrain-usb-keyboard-config", "preview"],
        )
        self.assertNotIn("shell", keywords)

    def test_cli_exposes_usb_hid_and_keeps_legacy_keyboard_alias(self) -> None:
        from boxbrain.cli import build_parser

        parser = build_parser()
        self.assertEqual(parser.parse_args(["usb-hid"]).command, "usb-hid")
        self.assertEqual(
            parser.parse_args(["usb-keyboard"]).command,
            "usb-keyboard",
        )


if __name__ == "__main__":
    unittest.main()
