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
    @staticmethod
    def _write_sources(root: Path) -> dict[str, object]:
        aurum_pc = root / "aurum-pc"
        seed = root / "seed"
        mind = root / "mind"
        aurum_pc.mkdir(parents=True)
        seed.mkdir(parents=True)
        mind.mkdir(parents=True)
        (seed / "aurum_gui.py").write_text("print('gui')\n", encoding="utf-8")
        (aurum_pc / "aurum_hopper_gui.py").write_text("print('hopper gui')\n", encoding="utf-8")
        (aurum_pc / "aurum_arcade.py").write_text("print('arcade')\n", encoding="utf-8")
        (aurum_pc / "pc01_autonomy_policy.json").write_text("{}\n", encoding="utf-8")
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
        return {"aurum_pc": aurum_pc, "seed": seed, "mind": mind, "bootstrap": bootstrap}

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
            (aurum_pc / "aurum_hopper_gui.py").write_text("print('hopper gui')\n", encoding="utf-8")
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

    def test_prepare_uses_self_contained_runtime_without_git_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_root = root / "runtime"
            codelation = runtime_root / "codelation"
            sources = self._write_sources(root / "sources")
            (codelation / "seed").mkdir(parents=True)
            (codelation / "mind").mkdir(parents=True)
            for filename in ("aurum_hopper_gui.py", "aurum_arcade.py", "pc01_autonomy_policy.json"):
                (runtime_root / filename).write_bytes((sources["aurum_pc"] / filename).read_bytes())
            (codelation / "seed" / "aurum_gui.py").write_bytes((sources["seed"] / "aurum_gui.py").read_bytes())
            (codelation / "mind" / "bootstrap_mind.json").write_bytes(
                (sources["mind"] / "bootstrap_mind.json").read_bytes()
            )

            runtime = GuiRuntime(
                workspace=root / "missing-workspace",
                runtime_root=runtime_root,
                state_dir=root / "state",
                run_dir=root / "run",
            )
            runtime.prepare()

            self.assertEqual(runtime.source_mode, "installed-runtime")
            self.assertEqual(runtime.gui_script, runtime_root / "aurum_hopper_gui.py")
            copied = root / "state" / "gui" / "mind" / "bootstrap_mind.json"
            self.assertEqual(json.loads(copied.read_text(encoding="utf-8")), sources["bootstrap"])


if __name__ == "__main__":
    unittest.main()
