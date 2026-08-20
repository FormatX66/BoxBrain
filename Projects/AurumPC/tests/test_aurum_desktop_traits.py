from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
DESKTOP = ROOT / "aurum_desktop.py"
TRAITS = ROOT / "aurum_traits.py"


class AurumDesktopTraitContractTests(unittest.TestCase):
    def test_desktop_exposes_traits_as_capabilities_not_apps(self) -> None:
        desktop = DESKTOP.read_text(encoding="utf-8")
        traits = TRAITS.read_text(encoding="utf-8")
        self.assertIn('tab_names = ["Home", "Traits", "Build", "Hardware", "Field", "Settings"]', desktop)
        self.assertIn("traits are capabilities, not apps", desktop)
        self.assertIn("foundation-ready", traits)
        for trait_id in (
            "TR8:WEB",
            "TR8:FILES",
            "TR8:MEDIA",
            "TR8:WRITE",
            "TR8:INTENT",
            "TR8:CONNECT",
            "TR8:RECOVER",
        ):
            self.assertIn(trait_id, traits)


if __name__ == "__main__":
    unittest.main()
