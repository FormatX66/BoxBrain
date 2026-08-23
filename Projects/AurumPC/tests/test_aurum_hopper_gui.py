from __future__ import annotations

import importlib.util
import hashlib
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
        self.assertIn("HTML5 living surface", page)
        self.assertIn("AinWeave · StateWeave · ComputeWeave", page)
        self.assertEqual(page.count("data-aurum-logo"), 5)
        self.assertIn("logo-crop--landscape", page)
        self.assertIn("aurum-seven-leaf-logo.jpeg", page)
        self.assertIn("prefers-reduced-motion", page)
        self.assertNotIn('id="apiKey"', page)
        self.assertNotIn("bootstrapKey", page)
        self.assertNotIn("body.api_key", page)
        self.assertNotIn("/api/actuate", page)

    def test_html5_browser_is_bounded_and_has_landscape_controls(self) -> None:
        page = hopper.PAGE
        self.assertIn('data-nav="browser"', page)
        self.assertIn('id="web-browser"', page)
        self.assertIn('id="web-address"', page)
        self.assertIn('id="web-back"', page)
        self.assertIn('id="web-forward"', page)
        self.assertIn('id="web-reload"', page)
        self.assertIn('sandbox="allow-forms allow-scripts"', page)
        self.assertIn('referrerpolicy="no-referrer"', page)
        self.assertIn("normalizeWebTarget", page)
        self.assertIn("target.protocol!=='https:'", page)
        self.assertIn("privateWebHost", page)
        self.assertIn("No Aurum proxy", page)
        self.assertIn('frame_source_policy = "https:"', MODULE_PATH.read_text(encoding="utf-8"))
        self.assertNotIn("allow-same-origin", page)
        self.assertNotIn("allow-top-navigation", page)

    def test_server_source_rejects_browser_credential_bootstrap(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('request_path == "/api/key-bootstrap"', source)
        self.assertIn("machine-sealed runtime credential", source)
        self.assertIn('{"prompt", "model"}', source)
        self.assertNotIn('issubset({"prompt", "api_key", "model"})', source)

    def test_seven_leaf_mark_is_checksum_sealed_before_html5_projection(self) -> None:
        mark = MODULE_PATH.parents[1] / "Codelation" / "assets" / "identity" / "aurum-seven-leaf-logo-matrix.jpeg"
        payload = hopper._verified_logo_bytes(mark)
        self.assertIsNotNone(payload)
        self.assertEqual(hashlib.sha256(payload or b"").hexdigest(), hopper.LOGO_SHA256)
        self.assertIn('"scope": "aurum-native-seven-leaf"', MODULE_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
