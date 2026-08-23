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
    def test_html_projection_has_conversation_receipts_and_no_browser_key(self) -> None:
        page = hopper.PAGE
        self.assertIn("Aurum · Hopper", page)
        self.assertIn('class="chat-panel"', page)
        self.assertIn('id="messages"', page)
        self.assertIn("receipts visible", page)
        self.assertIn("tool_receipts", page)
        self.assertIn("Pygame fallback", page)
        self.assertNotIn('id="apiKey"', page)
        self.assertNotIn("bootstrapKey", page)
        self.assertNotIn("body.api_key", page)
        self.assertNotIn("/api/actuate", page)

    def test_server_source_rejects_browser_credential_bootstrap(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('request_path == "/api/key-bootstrap"', source)
        self.assertIn("machine-sealed runtime credential", source)
        self.assertIn('{"prompt", "model"}', source)
        self.assertNotIn('issubset({"prompt", "api_key", "model"})', source)


if __name__ == "__main__":
    unittest.main()
