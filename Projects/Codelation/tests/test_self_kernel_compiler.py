from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kernel_selfbuild.driver_plan import build_driver_plan
from kernel_selfbuild.hardware_profile import collect_machine_profile, normalize_arch
from kernel_selfbuild.kernel_plan import make_kernel_build_plan


class SelfKernelCompilerTests(unittest.TestCase):
    def test_arch_normalization(self):
        self.assertEqual(normalize_arch("AMD64"), "x86_64")
        self.assertEqual(normalize_arch("aarch64"), "arm64")

    def test_profiles_bound_and_unbound_devices_without_host_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sys_root = root / "sys"
            proc_root = root / "proc"
            (proc_root).mkdir(parents=True)
            (proc_root / "cpuinfo").write_text("model name : Test CPU\n", encoding="utf-8")
            pci = sys_root / "bus" / "pci" / "devices" / "0000:00:01.0"
            pci.mkdir(parents=True)
            (pci / "vendor").write_text("0x8086\n", encoding="utf-8")
            (pci / "device").write_text("0x1234\n", encoding="utf-8")
            (pci / "class").write_text("0x020000\n", encoding="utf-8")
            (pci / "modalias").write_text("pci:v00008086d00001234\n", encoding="utf-8")
            driver_dir = sys_root / "bus" / "pci" / "drivers" / "testnet"
            driver_dir.mkdir(parents=True)
            (pci / "driver").symlink_to(driver_dir)

            usb = sys_root / "bus" / "usb" / "devices" / "1-1"
            usb.mkdir(parents=True)
            (usb / "modalias").write_text("usb:v1234p5678\n", encoding="utf-8")

            profile = collect_machine_profile(
                sys_root=sys_root,
                proc_root=proc_root,
                machine="x86_64",
                kernel_release="test",
            )
            self.assertEqual(profile.cpu_model, "Test CPU")
            self.assertEqual(len(profile.devices), 2)
            items = build_driver_plan(profile)
            self.assertEqual(items[0].action, "reuse-bound-driver")
            self.assertEqual(items[0].observed_driver, "testnet")
            self.assertEqual(items[1].action, "resolve-modalias")

            plan = make_kernel_build_plan(profile, items)
            self.assertIn("testnet", plan.required_modules)
            self.assertIn("usb:v1234p5678", plan.unresolved_modaliases)
            self.assertTrue(plan.ready_for_compile)
            self.assertIn("a-b-fallback-preserved", plan.verification_gates)

    def test_unknown_device_blocks_compile_readiness_but_not_planning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sys_root = root / "sys"
            proc_root = root / "proc"
            proc_root.mkdir(parents=True)
            platform_device = sys_root / "bus" / "platform" / "devices" / "mystery"
            platform_device.mkdir(parents=True)
            # Platform inventory only emits entries with alias/driver; use a PCI device
            # with no usable identity to exercise the unknown-hardware contract.
            pci = sys_root / "bus" / "pci" / "devices" / "0000:00:02.0"
            pci.mkdir(parents=True)
            profile = collect_machine_profile(sys_root=sys_root, proc_root=proc_root, machine="aarch64", kernel_release="test")
            items = build_driver_plan(profile)
            self.assertEqual(items[0].action, "research-hardware-contract")
            plan = make_kernel_build_plan(profile, items)
            self.assertFalse(plan.ready_for_compile)
            self.assertEqual(plan.architecture, "arm64")
            self.assertEqual(plan.unknown_devices, ("pci:0000:00:02.0",))


if __name__ == "__main__":
    unittest.main(verbosity=2)
