from __future__ import annotations

import unittest
from pathlib import Path


BUILD_SCRIPT = Path(__file__).parents[1] / "build-iso.sh"


class BuildIsoContractTests(unittest.TestCase):
    def test_boot_requests_only_the_aurum_persistence_volume(self) -> None:
        script = BUILD_SCRIPT.read_text(encoding="utf-8")

        self.assertIn(" persistence ", script)
        self.assertIn("persistence-label=AURUM_PERSIST", script)
        self.assertIn("preempt=voluntary", script)
        self.assertIn("transparent_hugepage=madvise", script)


if __name__ == "__main__":
    unittest.main()
