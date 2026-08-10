from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boxbrain.cli import _access_point_request


ROOT = Path(__file__).resolve().parents[1]
HELPER = (ROOT / "scripts" / "boxbrain-access-point.sh").read_text(encoding="utf-8")
CONFIGURE = (ROOT / "scripts" / "configure-access-point.sh").read_text(
    encoding="utf-8"
)
SERVICE = (ROOT / "systemd" / "boxbrain-access-point.service").read_text(
    encoding="utf-8"
)
ROLLBACK = (
    ROOT / "systemd" / "boxbrain-access-point-rollback.timer"
).read_text(encoding="utf-8")
INSTALL = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
UPGRADE = (ROOT / "scripts" / "upgrade.sh").read_text(encoding="utf-8")


class AccessPointTests(unittest.TestCase):
    def test_virtual_ap_preserves_existing_wifi_and_uses_fixed_subnet(self) -> None:
        self.assertIn("physical_interface=${BOXBRAIN_AP_PHYSICAL_INTERFACE:-wlan0}", HELPER)
        self.assertIn("ap_interface=${BOXBRAIN_AP_INTERFACE:-bbap0}", HELPER)
        self.assertIn("10.42.194.1/24", HELPER)
        self.assertIn('interface add "$ap_interface" type __ap', HELPER)
        self.assertNotIn('connection down "$physical_interface"', HELPER)

    def test_ap_is_wpa_protected_and_does_not_forward_to_other_networks(self) -> None:
        self.assertIn("key-mgmt=wpa-psk", HELPER)
        self.assertIn("proto=rsn;", HELPER)
        self.assertIn("pairwise=ccmp;", HELPER)
        self.assertIn("psk=%s", HELPER)
        self.assertIn("iifname \"$ap_interface\" oifname != \"$ap_interface\" reject", HELPER)
        self.assertNotIn("open", HELPER.lower())

    def test_change_is_preview_first_and_has_timed_rollback(self) -> None:
        self.assertIn("STAGE ACCESS POINT", CONFIGURE)
        self.assertIn("COMMIT ACCESS POINT", CONFIGURE)
        self.assertIn("ROLL BACK ACCESS POINT", CONFIGURE)
        self.assertIn("rollback-pending", CONFIGURE)
        self.assertIn("OnActiveSec=15min", ROLLBACK)
        self.assertNotIn("systemctl reboot", CONFIGURE)
        self.assertNotIn("shutdown", CONFIGURE)

    def test_service_starts_after_network_manager(self) -> None:
        self.assertIn("After=NetworkManager.service network-online.target", SERVICE)
        self.assertIn("ConditionPathExists=/etc/boxbrain/access-point/psk", SERVICE)
        self.assertIn("ExecStart=/usr/local/libexec/boxbrain-access-point start", SERVICE)

    def test_install_is_inert_and_upgrade_can_restore_previous_state(self) -> None:
        self.assertIn("boxbrain-access-point.service", INSTALL)
        self.assertNotIn("enable boxbrain-access-point.service", INSTALL)
        for expected in (
            "ap_service_existed",
            "ap_rollback_service_existed",
            "ap_rollback_timer_existed",
            "ap_helper_existed",
            "ap_configure_helper_existed",
        ):
            self.assertIn(expected, UPGRADE)

    def test_cli_invokes_only_the_fixed_configurator_without_a_shell(self) -> None:
        completed = Mock(
            returncode=0,
            stdout='{"schema_version":1,"action":"preview","changed":false}',
            stderr="",
        )
        with patch("boxbrain.cli.subprocess.run", return_value=completed) as run:
            result = _access_point_request(
                "preview",
                authorized=False,
                confirmation="",
            )

        self.assertFalse(result["changed"])
        arguments, keywords = run.call_args
        self.assertEqual(
            arguments[0],
            ["/usr/local/sbin/boxbrain-access-point-config", "preview"],
        )
        self.assertNotIn("shell", keywords)

    def test_cli_exposes_access_point_command(self) -> None:
        from boxbrain.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["access-point"])
        self.assertEqual(args.command, "access-point")
        self.assertEqual(args.action, "preview")


if __name__ == "__main__":
    unittest.main()
