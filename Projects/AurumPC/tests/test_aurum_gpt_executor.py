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
        self.assertFalse(catalog["workspace"]["mutation"])
        self.assertFalse(catalog["workspace"]["exact_replace"])
        self.assertEqual(catalog["workspace"]["promotion"], "verified-next-seed-only")
        self.assertTrue(catalog["appearance"]["preview"])
        self.assertTrue(catalog["appearance"]["resets_on_reboot"])
        self.assertIn("gui-restart", catalog["control_actions"])
        self.assertIn("runtime-sync", catalog["control_actions"])
        self.assertIn("remote-seed-sync", catalog["control_actions"])
        self.assertIn("remote-desktop-start", catalog["control_actions"])
        self.assertFalse(catalog["remote_control"]["direct_lan_desktop"])
        self.assertFalse(catalog["remote_control"]["raw_shell"])

    def test_path_traversal_and_non_aurum_roots_are_rejected(self) -> None:
        module = load_executor()
        with self.assertRaises(module.GptExecutorError):
            module._safe_workspace_path("../etc/passwd")
        with self.assertRaises(module.GptExecutorError):
            module._safe_workspace_path("README.md")
        with self.assertRaises(module.GptExecutorError):
            module._safe_workspace_path("Projects/AurumPC/unsafe.sh")

    def test_tracked_seed_replacement_is_refused_without_modifying_source(self) -> None:
        module = load_executor()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "BoxBrain"
            source = workspace / "Projects" / "AurumPC"
            source.mkdir(parents=True)
            target = source / "sample.py"
            original = "VALUE = 1\n"
            target.write_text(original, encoding="utf-8")
            with patch.object(module, "DEFAULT_WORKSPACE", workspace):
                with self.assertRaises(module.GptExecutorError):
                    module.replace_workspace("Projects/AurumPC/sample.py", "VALUE = 1", "VALUE = 2")
            self.assertEqual(target.read_text(encoding="utf-8"), original)

    def test_appearance_preview_is_ephemeral_and_does_not_touch_workspace(self) -> None:
        module = load_executor()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "BoxBrain"
            workspace.mkdir()
            appearance = root / "run" / "aurum" / "appearance.json"
            state = root / "state"
            receipt = module.set_appearance(
                "ember", appearance_path=appearance, state_dir=state
            )
            self.assertEqual(receipt["operation"], "appearance-preview")
            self.assertEqual(receipt["result"]["theme"], "ember")
            self.assertEqual(receipt["result"]["background_start"], "#160b07")
            self.assertEqual(receipt["result"]["background_end"], "#241108")
            self.assertTrue(receipt["result"]["resets_on_reboot"])
            self.assertFalse(receipt["result"]["tracked_source_modified"])
            self.assertTrue(appearance.is_file())
            self.assertEqual(list(workspace.iterdir()), [])
            reset = module.set_appearance(
                "default", appearance_path=appearance, state_dir=state
            )
            self.assertEqual(reset["result"]["status"], "reset")
            self.assertFalse(appearance.exists())


if __name__ == "__main__":
    unittest.main()
