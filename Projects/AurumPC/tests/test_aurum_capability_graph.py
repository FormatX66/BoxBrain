from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]

HARDWARE_SPEC = importlib.util.spec_from_file_location("aurum_hardware", ROOT / "aurum_hardware.py")
assert HARDWARE_SPEC and HARDWARE_SPEC.loader
aurum_hardware = importlib.util.module_from_spec(HARDWARE_SPEC)
HARDWARE_SPEC.loader.exec_module(aurum_hardware)
sys.modules["aurum_hardware"] = aurum_hardware

SPEC = importlib.util.spec_from_file_location("aurum_capability_graph", ROOT / "aurum_capability_graph.py")
assert SPEC and SPEC.loader
aurum_capability_graph = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aurum_capability_graph)


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


class CapabilityGraphTests(unittest.TestCase):
    def test_graph_converts_devices_to_capabilities_and_prefers_wake_hid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sys_root = root / "sys"
            proc_root = root / "proc"

            write(proc_root / "cpuinfo", "processor : 0\nmodel name : Test CPU\n")
            write(proc_root / "meminfo", "MemTotal:       1048576 kB\n")
            write(proc_root / "modules", "")
            write(proc_root / "cmdline", "")
            write(proc_root / "mounts", "")

            event = sys_root / "class" / "input" / "event5"
            write(event / "device" / "name", "ELAN Touchpad\n")
            write(event / "device" / "power" / "wakeup", "enabled\n")

            net = sys_root / "class" / "net" / "wlan0"
            write(net / "address", "00:11:22:33:44:55\n")
            write(net / "carrier", "1\n")
            write(net / "operstate", "up\n")
            write(net / "mtu", "1500\n")

            profile = aurum_hardware.collect_hardware_profile(sys_root=sys_root, proc_root=proc_root)
            graph = aurum_capability_graph.build_capability_graph(
                profile, sys_root=sys_root, proc_root=proc_root
            )

            self.assertTrue(graph["read_only"])
            self.assertIn("recover", graph["index"]["by_capability"])
            self.assertIn("transport", graph["index"]["by_capability"])

            plan = aurum_capability_graph.plan_intent(
                graph,
                {"requires": ["actuate", "recover"], "prefers": ["transport"]},
            )
            self.assertIsNotNone(plan["selected"])
            self.assertEqual(plan["selected"]["node_id"], "input:event5")
            self.assertFalse(plan["execution_authorized"])
            self.assertIn("wake-enabled", plan["selected"]["reasons"])

    def test_removable_storage_becomes_store_transport_recovery(self) -> None:
        profile = {
            "schema": "test-profile",
            "cpu": {},
            "memory": {},
            "block_devices": [
                {
                    "name": "sdb",
                    "partition": False,
                    "removable": 1,
                    "model": "Test USB",
                    "size_sectors": 2048,
                    "driver": "usb-storage",
                }
            ],
            "network_interfaces": [],
            "input_devices": [],
            "graphics_devices": [],
            "usb_devices": [],
            "pci_devices": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            graph = aurum_capability_graph.build_capability_graph(
                profile, sys_root=root / "sys", proc_root=root / "proc"
            )
        node = next(item for item in graph["nodes"] if item["id"] == "block:sdb")
        self.assertEqual(set(node["capabilities"]), {"store", "transport", "recover"})


if __name__ == "__main__":
    unittest.main()
