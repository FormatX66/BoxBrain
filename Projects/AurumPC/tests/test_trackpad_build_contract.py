from __future__ import annotations

import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "build-iso-trackpad.sh"


class TrackpadBuildContractTests(unittest.TestCase):
    def test_image_contains_explicit_pointer_stack(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        for package in (
            "udev",
            "libinput-tools",
            "xserver-xorg-core",
            "xserver-xorg-input-libinput",
            "xinit",
        ):
            self.assertIn(package, script)

    def test_bootstrap_probes_common_trackpad_paths(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        for module in ("i2c_hid_acpi", "hid_multitouch", "psmouse", "usbhid"):
            self.assertIn(f"modprobe {module}", script)
        self.assertIn("udevadm settle", script)
        self.assertIn("aurum_input.py", script)
        self.assertIn("/run/aurum-input-status.json", script)

    def test_xorg_uses_libinput_for_pointer_and_touchpad(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('MatchIsPointer "on"', script)
        self.assertIn('MatchIsTouchpad "on"', script)
        self.assertIn('Driver "libinput"', script)
        self.assertIn('Option "Tapping" "on"', script)
        self.assertIn('Option "DisableWhileTyping" "on"', script)

    def test_trackpad_bootstrap_precedes_primary_console(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("Before=aurum-pc-console.service", script)
        self.assertIn("Requires=aurum-input-bootstrap.service", script)
        self.assertIn("aurum-input-bootstrap.service", script)


if __name__ == "__main__":
    unittest.main()
