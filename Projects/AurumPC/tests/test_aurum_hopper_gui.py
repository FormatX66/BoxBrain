from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "aurum_hopper_gui.py"
SPEC = importlib.util.spec_from_file_location("aurum_hopper_gui", MODULE_PATH)
assert SPEC and SPEC.loader
hopper = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = hopper
SPEC.loader.exec_module(hopper)


class HopperGuiTests(unittest.TestCase):
    def test_adaptation_names_machine_and_adds_play_landmark(self) -> None:
        page = """<title>Aurum — BBPI4</title>
BBPI4 · Local adaptive shell
Good to see you.
This first GUI keeps dialogue separate from machine authority.
Pi connected
Pi unavailable
  </style>
<button class="nav" data-action="settings"><span>⚙</span><span>Settings</span></button>
    <div id="safeBanner"
      } else if (action === 'settings') {
        apiKey.focus();
      } else {
  refreshStatus();"""
        adapted = hopper._adapt_page(page)
        self.assertIn("Aurum — Hopper", adapted)
        self.assertIn("Hopper · Local adaptive shell", adapted)
        self.assertIn('data-action="play"', adapted)
        self.assertIn("http://127.0.0.1:8766/", adapted)
        self.assertNotIn("Pi connected", adapted)
        self.assertIn("Hopper is ready.", adapted)
        self.assertIn('data-hopper-profile="focus"', adapted)
        self.assertIn('data-hopper-profile="engineering"', adapted)
        self.assertIn("setHopperProfile('balanced')", adapted)
        self.assertNotIn("/api/actuate", adapted)


if __name__ == "__main__":
    unittest.main()
