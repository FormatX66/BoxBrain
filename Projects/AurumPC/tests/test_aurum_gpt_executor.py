from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]


def load_executor():
    path = ROOT / "aurum_gpt_executor.py"
    spec = importlib.util.spec_from_file_location("test_aurum_gpt_executor_module", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AurumGPTExecutorTests(unittest.TestCase):
    def test_catalog_is_bounded_and_has_no_shell_or_git_push(self) -> None:
        module = load_executor()
        catalog = module.catalog()
        self.assertFalse(catalog["direct_shell_contract"])
        self.assertFalse(catalog["workspace"]["git_push"])
        self.assertTrue(catalog["workspace"]["validation"] == "required")
        self.assertTrue(catalog["workspace"]["rollback_on_validation_failure"])
        self.assertIn("gui-restart", catalog["control_actions"])
        self.assertIn("runtime-sync", catalog["control_actions"])

    def test_path_traversal_and_non_aurum_roots_are_rejected(self) -> None:
        module = load_executor()
        with self.assertRaises(module.GptExecutorError):
            module._safe_workspace_path("../etc/passwd")
        with self.assertRaises(module.GptExecutorError):
            module._safe_workspace_path("README.md")
        with self.assertRaises(module.GptExecutorError):
            module._safe_workspace_path("Projects/AurumPC/unsafe.sh")

    def test_exact_replace_validates_and_bad_python_rolls_back(self) -> None:
        module = load_executor()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "BoxBrain"
            source = workspace / "Projects" / "AurumPC"
            source.mkdir(parents=True)
            state = root / "state"
            target = source / "sample.py"
            original = "VALUE = 1\n"
            target.write_text(original, encoding="utf-8")
            with patch.object(module, "DEFAULT_WORKSPACE", workspace), patch.object(module, "DEFAULT_STATE", state):
                good = module.replace_workspace("Projects/AurumPC/sample.py", "VALUE = 1", "VALUE = 2")
                self.assertTrue(good["result"]["applied"])
                self.assertEqual(target.read_text(encoding="utf-8"), "VALUE = 2\n")
                bad = module.replace_workspace("Projects/AurumPC/sample.py", "VALUE = 2", "VALUE =")
                self.assertFalse(bad["result"]["applied"])
                self.assertEqual(bad["result"]["status"], "rolled-back")
                self.assertEqual(target.read_text(encoding="utf-8"), "VALUE = 2\n")


if __name__ == "__main__":
    unittest.main()
