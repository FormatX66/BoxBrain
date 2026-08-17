from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class AurumConsoleContractTests(unittest.TestCase):
    def test_console_source_keeps_bounded_commands(self) -> None:
        source = (ROOT / "aurum_console.py").read_text(encoding="utf-8")
        for token in (
            "status | hardware",
            "self-build-status",
            "git-sync authorize-network",
            "install confirm ERASE-CODE",
        ):
            self.assertIn(token, source)

    def test_bootstrap_forces_detailed_hardware_provider(self) -> None:
        source = (ROOT / "aurum_bootstrap.py").read_text(encoding="utf-8")
        self.assertIn("aurum_console.hardware = collect_hardware_profile", source)
        self.assertIn("AURUM_WIFI_DIAG", source)


if __name__ == "__main__":
    unittest.main()
