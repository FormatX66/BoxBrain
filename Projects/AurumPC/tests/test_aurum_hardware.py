from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "aurum_hardware.py"
SPEC = importlib.util.spec_from_file_location("aurum_hardware", MODULE_PATH)
assert SPEC and SPEC.loader
aurum_hardware = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aurum_hardware)


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


class HardwareEvidenceTests(unittest.TestCase):
    def test_profile_and_plan_are_read_only_and_keep_observed_driver(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sys_root = root / "sys"
            proc_root = root / "proc"
            pci = sys_root / "bus" / "pci" / "devices" / "0000:04:00.0"
            driver = sys_root / "bus" / "pci" / "drivers" / "r8169"
            driver.mkdir(parents=True)
            write(pci / "vendor", "0x10ec\n")
            write(pci / "device", "0x8168\n")
            write(pci / "class", "0x020000\n")
            write(pci / "modalias", "pci:v000010ECd00008168\n")
            os.symlink(driver, pci / "driver")

            net = sys_root / "class" / "net" / "enp4s0"
            net.mkdir(parents=True)
            os.symlink(pci, net / "device")
            write(net / "address", "04:0e:3c:54:54:49\n")
            write(net / "carrier", "0\n")
            write(net / "operstate", "down\n")
            write(net / "mtu", "1500\n")

            write(proc_root / "cpuinfo", "processor : 0\nvendor_id : GenuineIntel\nmodel name : Test CPU\nflags : sse sse2\n")
            write(proc_root / "meminfo", "MemTotal:       1048576 kB\n")
            write(proc_root / "modules", "r8169 123 0 - Live 0x0\n")
            write(proc_root / "cmdline", "boot=live persistence\n")
            write(proc_root / "mounts", "overlay / overlay rw 0 0\n/dev/sdb1 /run/live/medium iso9660 ro 0 0\n")

            profile_path = root / "run" / "aurum" / "machine-profile.json"
            plan_path = root / "run" / "aurum" / "kernel-driver-plan.json"
            profile, plan = aurum_hardware.capture_hardware_evidence(
                profile_path=profile_path,
                plan_path=plan_path,
                sys_root=sys_root,
                proc_root=proc_root,
            )

            self.assertTrue(profile["observation_policy"]["read_only"])
            self.assertFalse(profile["observation_policy"]["network_required"])
            self.assertFalse(profile["observation_policy"]["internal_disk_writes"])
            self.assertEqual(profile["pci_devices"][0]["driver"], "r8169")
            self.assertEqual(profile["network_interfaces"][0]["driver"], "r8169")
            self.assertEqual(profile["network_interfaces"][0]["carrier"], 0)
            self.assertIn("r8169", plan["required_existing_drivers"])
            self.assertTrue(plan["seed_recovery"]["preserve_current_removable_boot"])
            self.assertFalse(plan["seed_recovery"]["overwrite_only_known_good_boot"])
            self.assertIn("storage-or-boot-critical-replacement", plan["separate_explicit_gate_required"])
            self.assertTrue(profile_path.is_file())
            self.assertTrue(plan_path.is_file())


if __name__ == "__main__":
    unittest.main()
