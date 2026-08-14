from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kernel_selfbuild.boot_media import make_boot_media_plan
from kernel_selfbuild.hardware_profile import DeviceObservation, MachineProfile
from kernel_selfbuild.hotplug import diff_hardware


class SelfKernelHotplugTests(unittest.TestCase):
    def test_new_peripheral_becomes_module_work_not_full_kernel_rebuild(self):
        before = MachineProfile("x86_64", "x86_64", "seed", "uefi", "cpu", ())
        device = DeviceObservation(
            bus="usb",
            address="1-2",
            vendor="0x1234",
            device="0x5678",
            class_code=None,
            modalias="usb:v1234p5678",
            driver=None,
        )
        after = MachineProfile("x86_64", "x86_64", "seed", "uefi", "cpu", (device,))
        delta = diff_hardware(before, after)
        self.assertEqual(delta.added, (device,))
        self.assertFalse(delta.full_kernel_rebuild_required)
        self.assertEqual(delta.driver_work[0].action, "resolve-modalias")

    def test_x86_boot_media_keeps_seed_fallback(self):
        plan = make_boot_media_plan("x86_64")
        self.assertTrue(plan.fallback_required)
        self.assertEqual(plan.uefi_fallback_path, "EFI/BOOT/BOOTX64.EFI")

    def test_arm64_boot_media_records_board_bootstrap_constraint(self):
        plan = make_boot_media_plan("arm64")
        self.assertTrue(plan.fallback_required)
        self.assertEqual(plan.uefi_fallback_path, "EFI/BOOT/BOOTAA64.EFI")
        self.assertIsNotNone(plan.arm_board_bootstrap_note)


if __name__ == "__main__":
    unittest.main(verbosity=2)
