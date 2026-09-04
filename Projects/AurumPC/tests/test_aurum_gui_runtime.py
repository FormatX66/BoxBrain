from __future__ import annotations

import importlib.util
import json
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


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

    def test_gui_start_clears_only_the_known_legacy_core_share_collision(self) -> None:
        runtime = GuiRuntime(runtime_root=Path("/opt/aurum"), port=8765)
        legacy_command = (
            "/usr/bin/python3 /opt/aurum/aurum_core_share.py "
            "serve --bind 0.0.0.0 --port 8765"
        )
        with (
            patch.object(runtime, "_listener_pids", side_effect=[[42], []]),
            patch.object(runtime, "_cmdline", return_value=legacy_command),
            patch.object(gui_module.os, "kill") as kill,
            patch.object(gui_module.time, "sleep"),
        ):
            runtime._clear_stale_gui_listener()

        kill.assert_called_once_with(42, signal.SIGTERM)

    def test_gui_start_recognizes_legacy_core_share_default_port_form(self) -> None:
        runtime = GuiRuntime(runtime_root=Path("/opt/aurum"), port=8765)
        legacy_command = "/usr/bin/python3 /opt/aurum/aurum_core_share.py serve --bind 0.0.0.0"

        with patch.object(runtime, "_cmdline", return_value=legacy_command):
            self.assertTrue(runtime._legacy_core_share_on_gui_port(42))

    def test_gui_start_recognizes_legacy_core_share_equals_port_form(self) -> None:
        runtime = GuiRuntime(runtime_root=Path("/opt/aurum"), port=8765)
        legacy_command = (
            "/usr/bin/python3 /opt/aurum/aurum_core_share.py "
            "serve --bind 0.0.0.0 --port=8765"
        )

        with patch.object(runtime, "_cmdline", return_value=legacy_command):
            self.assertTrue(runtime._legacy_core_share_on_gui_port(42))

    def test_gui_start_retries_once_after_a_recognized_bind_race(self) -> None:
        runtime = GuiRuntime(runtime_root=Path("/opt/aurum"), port=8765)
        failed = Mock()
        failed.poll.return_value = 1
        replacement = Mock()

        with (
            patch.object(
                runtime,
                "_gui_status",
                side_effect=[{"status": "stopped"}, {"status": "stopped"}, {"status": "running"}],
            ),
            patch.object(runtime, "_clear_stale_gui_listener") as clear,
            patch.object(runtime, "_spawn", side_effect=[failed, replacement]) as spawn,
            patch.object(runtime, "_listener_pids", return_value=[42]),
        ):
            runtime._start_gui()

        self.assertEqual(clear.call_count, 2)
        self.assertEqual(spawn.call_count, 2)

    def test_gui_start_allows_a_live_child_bounded_slow_readiness(self) -> None:
        runtime = GuiRuntime(runtime_root=Path("/opt/aurum"), port=8765)
        child = Mock(pid=44)
        child.poll.return_value = None
        states = [{"status": "stopped"}] * 12 + [{"status": "running"}]
        clock = iter(range(100))
        with (
            patch.object(runtime, "_gui_status", side_effect=states),
            patch.object(runtime, "_clear_stale_gui_listener"),
            patch.object(runtime, "_spawn", return_value=child),
            patch.object(gui_module.time, "monotonic", side_effect=lambda: next(clock)),
            patch.object(gui_module.time, "sleep"),
        ):
            runtime._start_gui()
        child.terminate.assert_not_called()

    def test_gui_status_labels_owned_unready_child_as_starting(self) -> None:
        runtime = GuiRuntime(runtime_root=Path("/opt/aurum"), port=8765)
        with (
            patch.object(runtime, "_read_pid", return_value=44),
            patch.object(runtime, "_owned_gui", return_value=True),
            patch.object(runtime, "_json_probe", return_value={"reachable": False}),
        ):
            self.assertEqual(runtime._gui_status()["status"], "starting")

    def test_process_cpu_ticks_handles_parentheses_in_process_name(self) -> None:
        proc_stat = "44 (aurum gui worker) S 1 2 3 4 5 6 7 8 9 10 11 12\n"
        with patch.object(gui_module.Path, "read_text", return_value=proc_stat):
            self.assertEqual(GuiRuntime._process_cpu_ticks(44), 23)

    def test_gui_start_extends_soft_deadline_only_after_owned_child_cpu_progress(self) -> None:
        runtime = GuiRuntime(runtime_root=Path("/opt/aurum"), port=8765)
        child = Mock(pid=44)
        child.poll.return_value = None
        states = [{"status": "stopped"}] * 4 + [{"status": "running"}]
        clock = iter((0.0, 0.0, 0.5, 1.5, 2.5, 3.5))
        with (
            patch.object(runtime, "_gui_status", side_effect=states),
            patch.object(runtime, "_clear_stale_gui_listener"),
            patch.object(runtime, "_spawn", return_value=child),
            patch.object(runtime, "_process_cpu_ticks", side_effect=(10, 10, 11, 12)),
            patch.object(gui_module, "GUI_READY_TIMEOUT_SECONDS", 1),
            patch.object(gui_module, "GUI_PROGRESS_HARD_TIMEOUT_SECONDS", 10),
            patch.object(gui_module.time, "monotonic", side_effect=lambda: next(clock)),
            patch.object(gui_module.time, "sleep"),
        ):
            runtime._start_gui()
        child.terminate.assert_not_called()

    def test_gui_start_reaps_live_child_at_soft_deadline_without_cpu_progress(self) -> None:
        runtime = GuiRuntime(runtime_root=Path("/opt/aurum"), port=8765)
        child = Mock(pid=45)
        child.poll.return_value = None
        clock = iter((0.0, 0.0, 1.5, 2.0))
        with (
            patch.object(runtime, "_gui_status", return_value={"status": "stopped"}),
            patch.object(runtime, "_clear_stale_gui_listener"),
            patch.object(runtime, "_spawn", return_value=child),
            patch.object(runtime, "_process_cpu_ticks", return_value=10),
            patch.object(runtime, "_reap_failed_child") as reap,
            patch.object(gui_module, "GUI_READY_TIMEOUT_SECONDS", 1),
            patch.object(gui_module, "GUI_PROGRESS_HARD_TIMEOUT_SECONDS", 10),
            patch.object(gui_module.time, "monotonic", side_effect=lambda: next(clock)),
            patch.object(gui_module.time, "sleep"),
        ):
            with self.assertRaisesRegex(gui_module.GuiRuntimeError, "GUI did not become ready"):
                runtime._start_gui()
        reap.assert_called_once_with(child, runtime.pid_path)

    def test_gui_start_does_not_duplicate_an_owned_starting_child(self) -> None:
        runtime = GuiRuntime(runtime_root=Path("/opt/aurum"), port=8765)
        clock = iter((0.0, 0.0, 2.0))
        with (
            patch.object(runtime, "_gui_status", return_value={"status": "starting", "pid": 46}),
            patch.object(runtime, "_owned_gui", return_value=True),
            patch.object(runtime, "_spawn") as spawn,
            patch.object(gui_module, "GUI_READY_TIMEOUT_SECONDS", 1),
            patch.object(gui_module.time, "monotonic", side_effect=lambda: next(clock)),
            patch.object(gui_module.time, "sleep"),
        ):
            with self.assertRaisesRegex(gui_module.GuiRuntimeError, "refusing a duplicate child"):
                runtime._start_gui()
        spawn.assert_not_called()

    def test_failed_new_child_is_reaped_before_its_pid_record_is_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pid_path = Path(temporary) / "gui.pid"
            pid_path.write_text("45\n", encoding="utf-8")
            child = Mock(pid=45)
            child.poll.return_value = None
            child.wait.return_value = 0
            GuiRuntime._reap_failed_child(child, pid_path)
            child.terminate.assert_called_once_with()
            child.wait.assert_called_once_with(timeout=gui_module.FAILED_CHILD_STOP_SECONDS)
            child.kill.assert_not_called()
            self.assertFalse(pid_path.exists())

    def test_failed_child_keeps_pid_record_when_even_kill_is_unconfirmed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pid_path = Path(temporary) / "gui.pid"
            pid_path.write_text("46\n", encoding="utf-8")
            child = Mock(pid=46)
            child.poll.return_value = None
            child.wait.side_effect = subprocess.TimeoutExpired("gui", 5)
            with self.assertRaisesRegex(gui_module.GuiRuntimeError, "ownership retained"):
                GuiRuntime._reap_failed_child(child, pid_path)
            child.terminate.assert_called_once_with()
            child.kill.assert_called_once_with()
            self.assertTrue(pid_path.is_file())

    def test_gui_start_refuses_an_unrecognized_listener(self) -> None:
        runtime = GuiRuntime(runtime_root=Path("/opt/aurum"), port=8765)
        with (
            patch.object(runtime, "_listener_pids", return_value=[99]),
            patch.object(runtime, "_cmdline", return_value="/usr/bin/python3 /tmp/unrelated.py"),
            patch.object(gui_module.os, "kill") as kill,
        ):
            with self.assertRaises(gui_module.GuiRuntimeError):
                runtime._clear_stale_gui_listener()

        kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
