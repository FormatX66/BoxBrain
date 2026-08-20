from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "aurum_gui_runtime.py"
SPEC = importlib.util.spec_from_file_location("aurum_gui_runtime", MODULE_PATH)
assert SPEC and SPEC.loader
gui_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gui_module
SPEC.loader.exec_module(gui_module)
GuiRuntime = gui_module.GuiRuntime


class AurumGuiRuntimeTests(unittest.TestCase):
    def test_prepare_uses_private_state_root_and_keeps_workspace_clean(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            aurum_pc = workspace / "Projects" / "AurumPC"
            seed = workspace / "Projects" / "Codelation" / "seed"
            mind = workspace / "Projects" / "Codelation" / "mind"
            state = root / "state"
            run = root / "run"
            (workspace / ".git").mkdir(parents=True)
            aurum_pc.mkdir(parents=True)
            seed.mkdir(parents=True)
            mind.mkdir(parents=True)
            (seed / "aurum_gui.py").write_text("print('gui')\n", encoding="utf-8")
            (aurum_pc / "aurum_arcade.py").write_text("print('arcade')\n", encoding="utf-8")
            bootstrap = {
                "schema": "aurum.mind.v1",
                "identity": "BBPI4/Aurum",
                "version": 1,
                "name": "Aurum",
                "self_description": "test",
                "system_prompt": "test",
                "allowed_actions": ["answer", "propose_mind_replacement"],
            }
            (mind / "bootstrap_mind.json").write_text(json.dumps(bootstrap), encoding="utf-8")

            runtime = GuiRuntime(workspace=workspace, state_dir=state, run_dir=run)
            runtime.prepare()
            copied = state / "gui" / "mind" / "bootstrap_mind.json"
            self.assertTrue(copied.is_file())
            self.assertEqual(json.loads(copied.read_text(encoding="utf-8")), bootstrap)
            status = runtime.status()
            self.assertEqual(status["status"], "stopped")
            self.assertEqual(status["arcade"]["status"], "stopped")
            self.assertEqual(status["arcade"]["machine"], "Hopper")
            self.assertFalse((workspace / "Projects" / "Codelation" / "state").exists())


if __name__ == "__main__":
    unittest.main()
