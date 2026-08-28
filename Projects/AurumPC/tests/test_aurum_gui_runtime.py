from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


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

    def test_stale_recognized_arcade_listener_is_stopped_before_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = GuiRuntime(run_dir=root / "run")
            runtime.arcade_pid_path.parent.mkdir(parents=True)
            runtime.arcade_pid_path.write_text("123\n", encoding="utf-8")
            with (
                mock.patch.object(runtime, "_listener_pids", side_effect=[[321], []]),
                mock.patch.object(runtime, "_recognized_aurum_arcade", return_value=True),
                mock.patch.object(gui_module.os, "kill") as kill,
            ):
                runtime._clear_stale_arcade_listener()
            kill.assert_called_once_with(321, gui_module.signal.SIGTERM)
            self.assertFalse(runtime.arcade_pid_path.exists())

    @unittest.skipIf(gui_module.fcntl is None, "Hopper operation locking is POSIX-only")
    def test_operation_lock_serializes_independent_runtime_processes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = root / "run"
            ready = root / "ready"
            code = """
import importlib.util
import sys
import time
from pathlib import Path
spec = importlib.util.spec_from_file_location('aurum_gui_runtime_child', Path(sys.argv[1]))
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
runtime = module.GuiRuntime(run_dir=Path(sys.argv[2]))
with runtime._operation_lock():
    Path(sys.argv[3]).write_text('ready', encoding='utf-8')
    time.sleep(0.8)
"""
            child = subprocess.Popen(
                [sys.executable, "-c", code, str(MODULE_PATH), str(run_dir), str(ready)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and not ready.is_file():
                    time.sleep(0.02)
                self.assertTrue(ready.is_file())
                runtime = GuiRuntime(run_dir=run_dir)
                started = time.monotonic()
                with runtime._operation_lock():
                    waited = time.monotonic() - started
                self.assertGreaterEqual(waited, 0.5)
            finally:
                stdout, stderr = child.communicate(timeout=3)
            self.assertEqual(child.returncode, 0, stdout + stderr)


if __name__ == "__main__":
    unittest.main()
