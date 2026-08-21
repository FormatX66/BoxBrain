from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Projects.AurumPC.aurum_input import (
    apply_pointer_wake_policy,
    classify_device,
    input_devices,
)


class AurumInputTests(unittest.TestCase):
    def test_pointer_classification_covers_hopper_input_paths(self) -> None:
        self.assertEqual(classify_device("ELAN ClickPad", rel=(), abs_axes=(1,)), "touchpad")
        self.assertEqual(classify_device("USB Optical Mouse", rel=(1,), abs_axes=()), "mouse")
        self.assertEqual(classify_device("Generic HID", rel=(3,), abs_axes=()), "relative-pointer")
        self.assertEqual(classify_device("Generic HID", rel=(), abs_axes=(3,)), "absolute-pointer")

    def test_wake_policy_changes_only_nearest_pointer_power_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sys_input = root / "sys" / "class" / "input"
            dev_input = root / "dev" / "input"
            device = sys_input / "event0" / "device"
            (device / "capabilities").mkdir(parents=True)
            dev_input.mkdir(parents=True)
            (dev_input / "event0").write_bytes(b"")
            (device / "name").write_text("ELAN Touchpad\n", encoding="utf-8")
            (device / "capabilities" / "rel").write_text("0\n", encoding="utf-8")
            (device / "capabilities" / "abs").write_text("3\n", encoding="utf-8")
            (device / "power").mkdir()
            (device / "power" / "control").write_text("auto\n", encoding="ascii")
            (device / "power" / "wakeup").write_text("disabled\n", encoding="ascii")
            (sys_input / "power").mkdir()
            (sys_input / "power" / "control").write_text("auto\n", encoding="ascii")

            devices = input_devices(sys_input=sys_input, dev_input=dev_input)
            result = apply_pointer_wake_policy(devices)

            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["managed_pointer_count"], 1)
            self.assertEqual((device / "power" / "control").read_text(encoding="ascii").strip(), "on")
            self.assertEqual((device / "power" / "wakeup").read_text(encoding="ascii").strip(), "enabled")
            self.assertEqual((sys_input / "power" / "control").read_text(encoding="ascii").strip(), "auto")


if __name__ == "__main__":
    unittest.main()
