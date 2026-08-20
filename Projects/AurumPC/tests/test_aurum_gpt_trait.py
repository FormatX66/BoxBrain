from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "aurum_gpt_trait.py"
SPEC = importlib.util.spec_from_file_location("aurum_gpt_trait", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class AurumGptTraitTests(unittest.TestCase):
    def test_status_never_persists_or_exposes_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            workspace = root / "workspace"
            state.mkdir()
            (workspace / ".git" / "refs" / "heads" / "aurum").mkdir(parents=True)
            (workspace / ".git" / "HEAD").write_text("ref: refs/heads/aurum/trunk-v0.01\n", encoding="utf-8")
            (workspace / ".git" / "refs" / "heads" / "aurum" / "trunk-v0.01").write_text("a" * 40 + "\n", encoding="utf-8")
            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-secret"}, clear=False), \
                 patch.object(module, "DEFAULT_STATE", state), \
                 patch.object(module, "DEFAULT_WORKSPACE", workspace):
                result = module.status()
            encoded = json.dumps(result)
            self.assertEqual(result["trait"], "TRAIT:GPT")
            self.assertEqual(result["status"], "ready-for-api-key")
            self.assertFalse(result["host_actuation"])
            self.assertFalse(result["key_persisted_by_trait"])
            self.assertNotIn("sk-test-secret", encoded)

    def test_extract_text_reads_responses_message_shape(self) -> None:
        payload = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "hello Hopper"}],
                }
            ]
        }
        self.assertEqual(module._extract_text(payload), "hello Hopper")


if __name__ == "__main__":
    unittest.main()
