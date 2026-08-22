from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from subprocess import CompletedProcess
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "aurum_runtime_update.py"
SPEC = importlib.util.spec_from_file_location("aurum_runtime_update", MODULE_PATH)
assert SPEC and SPEC.loader
runtime_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime_module
SPEC.loader.exec_module(runtime_module)
ALLOWLIST = runtime_module.ALLOWLIST
SYSTEM_ASSETS = runtime_module.SYSTEM_ASSETS
RuntimeUpdater = runtime_module.RuntimeUpdater


class AurumRuntimeUpdateTests(unittest.TestCase):
    def test_plan_and_apply_are_allowlisted_atomic_and_receipted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            source = workspace / "Projects" / "AurumPC"
            target = root / "target"
            system_root = root / "system"
            state = root / "state"
            marker = root / "aurum-installed.json"
            source.mkdir(parents=True)
            target.mkdir()
            marker.write_text("{}\n", encoding="utf-8")
            for name in ALLOWLIST:
                (source / name).write_text(f"VALUE = {name!r}\n", encoding="utf-8")
                (target / name).write_text("VALUE = 'old'\n", encoding="utf-8")
            for relative, _mode in SYSTEM_ASSETS:
                asset = source / "runtime-assets" / relative
                asset.parent.mkdir(parents=True, exist_ok=True)
                asset.write_text(f"managed asset: {relative}\n", encoding="utf-8")
            subprocess.run(["git", "init", "-b", runtime_module.BRANCH], cwd=workspace, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.name", "Aurum Test"], cwd=workspace, check=True)
            subprocess.run(["git", "config", "user.email", "aurum-test@example.invalid"], cwd=workspace, check=True)
            subprocess.run(["git", "remote", "add", "origin", runtime_module.REPOSITORY], cwd=workspace, check=True)
            subprocess.run(["git", "add", "."], cwd=workspace, check=True)
            subprocess.run(["git", "commit", "-m", "test generation"], cwd=workspace, check=True, stdout=subprocess.DEVNULL)

            updater = RuntimeUpdater(
                workspace=workspace,
                target=target,
                state_dir=state,
                installed_marker=marker,
                system_root=system_root,
            )
            plan = updater.plan()
            self.assertTrue(plan["available"])
            self.assertEqual(set(plan["changed"]), set(ALLOWLIST))
            self.assertEqual(set(plan["system_changed"]), {name for name, _mode in SYSTEM_ASSETS})
            self.assertFalse(plan["identity"]["authorized"])

            with (
                patch.object(runtime_module.os, "geteuid", return_value=0, create=True),
                patch.object(updater, "_activate_system_integration", return_value={"status": "ready", "reason": "simulated-system-root"}),
                patch.object(updater, "_restart_gui", return_value={
                    "status": "running",
                    "physical_desktop": True,
                    "desktop": {"status": "running", "renderer": "html5", "primary": True},
                }),
                patch.object(updater, "_gpt_proof", return_value={"status": "passed", "model_call_proven": False}),
                patch.object(updater, "_system_proof", return_value={"status": "passed", "service": "test"}),
            ):
                result = updater.apply()
                finalized = updater.prove_current({
                    "status": "running",
                    "physical_desktop": True,
                    "desktop": {"status": "running", "renderer": "html5", "primary": True},
                })
            self.assertEqual(result["status"], "updated")
            self.assertFalse(result["reboot_required"])
            self.assertEqual(set(result["changed"]), set(ALLOWLIST))
            receipt = json.loads((state / "runtime-update.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["schema"], "aurum-pc-runtime-update-seed")
            self.assertTrue(Path(receipt["backup"]).is_dir())
            self.assertEqual(result["system_activation"]["reason"], "simulated-system-root")
            self.assertTrue(receipt["generation"]["become_next_seed"])
            self.assertEqual(finalized["status"], "current")
            self.assertTrue(finalized["generation"]["become_next_seed"])
            self.assertEqual(finalized["generation"]["stage"]["status"], "verified")
            for name in ALLOWLIST:
                self.assertEqual((target / name).read_text(encoding="utf-8"), f"VALUE = {name!r}\n")
            for relative, mode in SYSTEM_ASSETS:
                installed = system_root / relative
                self.assertEqual(installed.read_text(encoding="utf-8"), f"managed asset: {relative}\n")
                self.assertEqual(installed.stat().st_mode & 0o777, mode)

    def test_system_integration_reloads_enables_and_recovers_inactive_input_service(self) -> None:
        updater = RuntimeUpdater(system_root=Path("/"))

        def completed(arguments, **_kwargs):
            returncode = 3 if "is-active" in arguments else 0
            return CompletedProcess(arguments, returncode, stdout="")

        with (
            patch.object(runtime_module.shutil, "which", return_value="/usr/bin/systemctl"),
            patch.object(runtime_module.subprocess, "run", side_effect=completed) as runner,
        ):
            result = updater._activate_system_integration(
                ["aurum_input.py"],
                ["etc/systemd/system/aurum-input-bootstrap.service"],
            )

        self.assertEqual(result["status"], "ready")
        invocations = [call.args[0][1:] for call in runner.call_args_list]
        self.assertIn(["daemon-reload"], invocations)
        self.assertIn(["enable", "aurum-input-bootstrap.service", "aurum-pc-console.service"], invocations)
        self.assertIn(["restart", "aurum-input-bootstrap.service"], invocations)
        self.assertTrue(result["boot_screen_visible_on_next_boot"])

    def test_plan_refuses_when_not_installed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            updater = RuntimeUpdater(
                workspace=root / "workspace",
                target=root / "target",
                state_dir=root / "state",
                installed_marker=root / "missing-marker",
            )
            plan = updater.plan()
            self.assertFalse(plan["available"])
            self.assertEqual(plan["reason"], "not-installed-runtime")


if __name__ == "__main__":
    unittest.main()
