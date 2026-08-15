from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "server.py"
spec = importlib.util.spec_from_file_location("aurum_gui_server", MODULE_PATH)
assert spec is not None and spec.loader is not None
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class AurumGUIContractTests(unittest.TestCase):
    def test_status_contract_without_llm_probe(self) -> None:
        payload = server.build_status(include_llm_health=False)
        self.assertEqual(payload["schema"], "aurum-gui-status-v0")
        self.assertIn("machine", payload)
        self.assertIn("aurum", payload)
        self.assertEqual(payload["llm"]["state"], "not-probed")
        self.assertIn("architecture", payload["machine"])

    def test_message_normalization_adds_system_contract(self) -> None:
        messages = server._normalize_messages([{"role": "user", "content": "status"}])
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1], {"role": "user", "content": "status"})

    def test_message_normalization_preserves_supplied_system(self) -> None:
        messages = server._normalize_messages(
            [
                {"role": "system", "content": "bounded"},
                {"role": "user", "content": "hello"},
            ]
        )
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["content"], "bounded")

    def test_message_normalization_rejects_invalid_role(self) -> None:
        with self.assertRaises(ValueError):
            server._normalize_messages([{"role": "tool", "content": "unsafe"}])

    def test_static_assets_exist(self) -> None:
        self.assertTrue((server.STATIC_ROOT / "index.html").is_file())
        self.assertTrue((server.STATIC_ROOT / "app.css").is_file())
        self.assertTrue((server.STATIC_ROOT / "app.js").is_file())


if __name__ == "__main__":
    unittest.main()
