from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "aurum_driver_synthesis.py"
AURUM_PC = MODULE_PATH.parent
if str(AURUM_PC) not in sys.path:
    sys.path.insert(0, str(AURUM_PC))
SPEC = importlib.util.spec_from_file_location("aurum_driver_synthesis_tested", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def profile() -> dict:
    return {
        "schema": "aurum-x86-machine-profile-v1",
        "architecture": "x86_64",
        "kernel": "6.1-test",
        "pci_devices": [],
        "usb_devices": [],
        "network_interfaces": [
            {
                "name": "wlan-test",
                "mac": "02:00:00:00:00:01",
                "carrier": 1,
                "operstate": "up",
                "mtu": 1500,
                "modalias": "pci:test-wireless",
                "driver": None,
            }
        ],
        "graphics_devices": [],
        "input_devices": [],
        "block_devices": [
            {
                "name": "nvme0n1",
                "partition": False,
                "removable": 0,
                "size_sectors": 1000000,
                "logical_block_size": 512,
                "vendor": "TEST",
                "model": "BOOT",
                "modalias": "pci:test-storage",
                "driver": "nvme",
            }
        ],
        "loaded_modules": [],
        "boot_mount_evidence": [],
    }


class AdaptiveDriverSynthesisTests(unittest.TestCase):
    def test_cycle_models_devices_and_never_authorizes_physical_swap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            synth = module.AdaptiveDriverSynthesizer(
                state_dir=state,
                profile_provider=profile,
                policy={"driver_policy": {"compile_shadow_carrier": False}},
            )
            result = synth.cycle()
            self.assertEqual(result["status"], "cycle-complete")
            self.assertEqual(result["devices_modeled"], 2)
            self.assertEqual(result["selected_build"]["collection"], "network_interfaces")
            self.assertFalse(result["safety"]["physical_driver_swap"])
            self.assertFalse(result["safety"]["module_load"])
            storage = next(item for item in result["queue"] if item["collection"] == "block_devices")
            self.assertTrue(storage["gated"])
            contract = json.loads(Path(result["selected_build"]["contract"]).read_text(encoding="utf-8"))
            self.assertFalse(contract["physical_load_authorized"])
            self.assertFalse(contract["driver_replacement_authorized"])
            self.assertIn("unbounded-raw-mmio-pio", contract["forbidden_without_separate_gate"])


if __name__ == "__main__":
    unittest.main()
