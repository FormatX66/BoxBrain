from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MODULE_PATH = ROOT / "aurum_setup_gui.py"
SPEC = importlib.util.spec_from_file_location("aurum_setup_gui_test", MODULE_PATH)
assert SPEC and SPEC.loader
setup = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = setup
SPEC.loader.exec_module(setup)


class SetupGuiContractTests(unittest.TestCase):
    def test_drive_label_contains_only_human_readable_identity(self) -> None:
        label = setup._drive_label(
            {"model": "Internal NVMe", "size_gib": 476.8, "target_id": "drive-secret"}
        )
        self.assertEqual(label, "Internal NVMe  ·  476.8 GiB")
        self.assertNotIn("drive-secret", label)

    def test_raw_errors_are_replaced_with_safe_graphical_guidance(self) -> None:
        message = setup._friendly_reason("OSError: [Errno 98] Address already in use")
        self.assertNotIn("Errno", message)
        self.assertIn("Setup", message)


if __name__ == "__main__":
    unittest.main()
