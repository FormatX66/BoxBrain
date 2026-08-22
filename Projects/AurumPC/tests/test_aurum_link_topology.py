from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("aurum_link_topology", ROOT / "aurum_link_topology.py")
assert SPEC and SPEC.loader
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class LinkTopologyTests(unittest.TestCase):
    def test_usb_host_to_host_is_rejected(self) -> None:
        pi_a = m.endpoint("pi4", "usb-a3", "usb", {"host"})
        hopper = m.endpoint("hopper", "usb-c", "usb", {"host"})
        ok, reason = m.compatible(pi_a, hopper)
        self.assertFalse(ok)
        self.assertEqual(reason, "usb-role-conflict")

    def test_pi_otg_to_pc_host_is_valid(self) -> None:
        pi = m.endpoint("pi4", "usb-c-otg", "usb", {"device", "dual-role"})
        pc = m.endpoint("main", "usb-c", "usb", {"host"})
        ok, _ = m.compatible(pi, pc)
        self.assertTrue(ok)

    def test_hdmi_source_to_capture_is_valid(self) -> None:
        hopper = m.endpoint("hopper", "hdmi-out", "hdmi", {"source"})
        cap = m.endpoint("pi4", "capture", "hdmi", {"capture"})
        ok, _ = m.compatible(hopper, cap)
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
