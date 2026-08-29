from __future__ import annotations

import importlib.util
import json
import os
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
    def test_pending_physical_or_reboot_proof_is_not_a_failed_generation(self) -> None:
        pending = runtime_module._proof_disposition({
            "runtime": {"status": "passed"},
            "input": {"status": "pending-physical-input"},
            "wifi": {"status": "pending-reboot-observation"},
        })
        failed = runtime_module._proof_disposition({
            "runtime": {"status": "passed"},
            "physical": {"status": "failed"},
            "input": {"status": "pending-physical-input"},
        })

        self.assertEqual(pending["status"], "pending")
        self.assertEqual(set(pending["pending"]), {"input", "wifi"})
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["failed"], ["physical"])

    def test_generation_transition_accepts_only_forward_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            subprocess.run(["git", "init", "-b", runtime_module.BRANCH], cwd=workspace, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.name", "Aurum Test"], cwd=workspace, check=True)
            subprocess.run(["git", "config", "user.email", "aurum-test@example.invalid"], cwd=workspace, check=True)
            subprocess.run(["git", "remote", "add", "origin", runtime_module.REPOSITORY], cwd=workspace, check=True)
            source_file = workspace / "seed.txt"
            source_file.write_text("first\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=workspace, check=True)
            subprocess.run(["git", "commit", "-m", "first seed"], cwd=workspace, check=True, stdout=subprocess.DEVNULL)
            first = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workspace, check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
            source_file.write_text("second\n", encoding="utf-8")
            subprocess.run(["git", "commit", "-am", "forward seed"], cwd=workspace, check=True, stdout=subprocess.DEVNULL)
            second = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workspace, check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
            tree = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=workspace, check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
            updater = RuntimeUpdater(workspace=workspace, state_dir=root / "state")
            previous = {"source": {"head": first}, "generation": {"become_next_seed": True}}

            forward = updater._generation_transition({"head": second, "tree": tree}, previous)
            refused = updater._generation_transition({"head": "f" * 40, "tree": tree}, previous)

        self.assertEqual(forward["status"], "passed")
        self.assertEqual(forward["relation"], "forward-successor")
        self.assertEqual(refused["status"], "refused")
        self.assertEqual(refused["reason"], "non-forward-generation")
        self.assertFalse(refused["policy"]["generation_rollback"])

    def test_culled_head_is_not_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            state.mkdir()
            head = "a" * 40
            tree = "b" * 40
            (state / "seed-lineage.json").write_text(
                json.dumps({
                    "schema": runtime_module.LINEAGE_SCHEMA,
                    "observed_head": head,
                    "last_culled": {"head": head, "tree": tree},
                    "culled_count": 1,
                }),
                encoding="utf-8",
            )
            updater = RuntimeUpdater(workspace=root / "workspace", state_dir=state)
            transition = updater._generation_transition({"head": head, "tree": tree}, {})

        self.assertEqual(transition["status"], "refused")
        self.assertEqual(transition["reason"], "culled-generation-awaiting-forward-successor")

    def test_displaced_runtime_heals_without_changing_git(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            displaced = root / "displaced"
            target.mkdir()
            displaced.mkdir()
            (target / "aurum_runtime_update.py").write_text("new candidate\n", encoding="utf-8")
            (displaced / "aurum_runtime_update.py").write_text("current seed\n", encoding="utf-8")
            updater = RuntimeUpdater(target=target, state_dir=root / "state", system_root=root / "system")
            with (
                patch.object(updater, "_activate_system_integration", return_value={"status": "ready"}),
                patch.object(updater, "_restart_gui", return_value={"status": "running"}),
            ):
                healed = updater._heal_from_displaced_state(
                    runtime_files=["aurum_runtime_update.py"],
                    system_files=[],
                    displaced_state=displaced,
                )

            self.assertEqual(healed["status"], "passed")
            self.assertEqual((target / "aurum_runtime_update.py").read_text(encoding="utf-8"), "current seed\n")
            self.assertFalse(healed["branch_moved_backward"])
            self.assertFalse(healed["git_ref_changed"])

    def test_gui_console_proof_covers_primary_and_fallback_renderers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            updater = RuntimeUpdater(target=MODULE_PATH.parent, state_dir=Path(temporary))
            proof = updater._gui_console_proof()

        self.assertEqual(proof["status"], "passed")
        self.assertTrue(proof["html_panel_present"])
        self.assertTrue(proof["fallback_panel_present"])
        self.assertFalse(proof["raw_shell"])

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
                patch.object(updater, "_wifi_snapshot", return_value={"schema": "aurum.wifi-persistence.v1"}),
                patch.object(updater, "_wifi_persistence_proof", return_value={"status": "passed"}),
                patch.object(updater, "_wifi_reboot_proof", return_value={"status": "passed"}),
                patch.object(updater, "_input_proof", return_value={"status": "passed"}),
                patch.object(updater, "_gui_console_proof", return_value={"status": "passed"}),
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
            self.assertEqual(receipt["backup"], receipt["displaced_state"])
            self.assertEqual(result["generation"]["disposition"], "regrown-and-promoted")
            self.assertEqual(receipt["generation"]["disposition"], "healed-and-proven")
            self.assertFalse(receipt["generation"]["lineage_policy"]["generation_rollback"])
            self.assertEqual(result["system_activation"]["reason"], "simulated-system-root")
            self.assertTrue(receipt["generation"]["become_next_seed"])
            self.assertEqual(receipt["generation"]["prove"]["wifi"]["status"], "passed")
            self.assertEqual(receipt["generation"]["prove"]["input"]["status"], "passed")
            self.assertEqual(receipt["generation"]["prove"]["gui_console"]["status"], "passed")
            self.assertEqual(finalized["status"], "current")
            self.assertTrue(finalized["generation"]["become_next_seed"])
            self.assertEqual(finalized["generation"]["stage"]["status"], "verified")
            for name in ALLOWLIST:
                self.assertEqual((target / name).read_text(encoding="utf-8"), f"VALUE = {name!r}\n")
            for relative, mode in SYSTEM_ASSETS:
                installed = system_root / relative
                self.assertEqual(installed.read_text(encoding="utf-8"), f"managed asset: {relative}\n")
                if os.name == "posix":
                    self.assertEqual(installed.stat().st_mode & 0o777, mode)

    def test_failed_candidate_path_culls_and_heals_instead_of_rolling_back_git(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('"culled-awaiting-forward-regrow"', source)
        self.assertIn("_heal_from_displaced_state", source)
        self.assertIn('"branch_moved_backward": False', source)
        self.assertNotIn('self._git("reset"', source)
        self.assertNotIn('self._git("revert"', source)

    def test_failed_physical_proof_culls_candidate_heals_runtime_and_blocks_retry(self) -> None:
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
                (target / name).write_text("VALUE = 'current-seed'\n", encoding="utf-8")
            for relative, _mode in SYSTEM_ASSETS:
                asset = source / "runtime-assets" / relative
                asset.parent.mkdir(parents=True, exist_ok=True)
                asset.write_text(f"candidate asset: {relative}\n", encoding="utf-8")
            subprocess.run(["git", "init", "-b", runtime_module.BRANCH], cwd=workspace, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.name", "Aurum Test"], cwd=workspace, check=True)
            subprocess.run(["git", "config", "user.email", "aurum-test@example.invalid"], cwd=workspace, check=True)
            subprocess.run(["git", "remote", "add", "origin", runtime_module.REPOSITORY], cwd=workspace, check=True)
            subprocess.run(["git", "add", "."], cwd=workspace, check=True)
            subprocess.run(["git", "commit", "-m", "candidate seed"], cwd=workspace, check=True, stdout=subprocess.DEVNULL)
            head_before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workspace, check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
            updater = RuntimeUpdater(
                workspace=workspace,
                target=target,
                state_dir=state,
                installed_marker=marker,
                system_root=system_root,
            )
            with (
                patch.object(runtime_module.os, "geteuid", return_value=0, create=True),
                patch.object(updater, "_activate_system_integration", return_value={"status": "ready"}),
                patch.object(updater, "_restart_gui", side_effect=[
                    {"status": "failed", "physical_desktop": False, "desktop": {"status": "failed"}},
                    {"status": "running", "physical_desktop": True, "desktop": {"status": "running"}},
                ]),
                patch.object(updater, "_gpt_proof", return_value={"status": "passed"}),
                patch.object(updater, "_refresh_input", return_value={"status": "ready"}),
                patch.object(updater, "_launch_physical_echo", return_value={"status": "skipped"}),
                patch.object(updater, "_wifi_snapshot", return_value={"schema": "aurum.wifi-persistence.v1"}),
                patch.object(updater, "_wifi_persistence_proof", return_value={"status": "passed"}),
                patch.object(updater, "_wifi_reboot_proof", return_value={"status": "passed"}),
            ):
                culled = updater.apply()
            head_after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workspace, check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
            with patch.object(runtime_module.os, "geteuid", return_value=0, create=True):
                retry = updater.apply()

            self.assertEqual(culled["status"], "culled-awaiting-forward-regrow")
            self.assertEqual(culled["generation"]["disposition"], "culled-awaiting-forward-regrow")
            self.assertEqual(culled["healing"]["status"], "passed")
            self.assertFalse(culled["branch_moved_backward"])
            self.assertEqual(head_before, head_after)
            self.assertEqual(retry["status"], "refused")
            self.assertEqual(retry["reason"], "culled-generation-awaiting-forward-successor")
            for name in ALLOWLIST:
                self.assertEqual((target / name).read_text(encoding="utf-8"), "VALUE = 'current-seed'\n")

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
        self.assertIn(
            [
                "enable",
                "aurum-input-bootstrap.service",
                "aurum-network-bootstrap.service",
                "aurum-pc-console.service",
                "aurum-auto-sync.service",
                "aurum-core-share.service",
            ],
            invocations,
        )
        self.assertIn(["restart", "aurum-input-bootstrap.service"], invocations)
        self.assertIn(["restart", "aurum-core-share.service"], invocations)
        self.assertIn(["is-enabled", "--quiet", "aurum-auto-sync.service"], invocations)
        self.assertTrue(result["boot_screen_visible_on_next_boot"])
        self.assertFalse(result["authentication_required"])
        self.assertFalse(result["personal_slush_exported"])

    def test_system_integration_restarts_monitor_when_updater_schema_changes(self) -> None:
        updater = RuntimeUpdater(system_root=Path("/"))

        def completed(arguments, **_kwargs):
            return CompletedProcess(arguments, 0, stdout="")

        with (
            patch.object(runtime_module.shutil, "which", return_value="/usr/bin/systemctl"),
            patch.object(runtime_module.subprocess, "run", side_effect=completed) as runner,
        ):
            result = updater._activate_system_integration(["aurum_runtime_update.py"], [])

        self.assertEqual(result["status"], "ready")
        invocations = [call.args[0][1:] for call in runner.call_args_list]
        self.assertIn(["restart", "aurum-input-bootstrap.service"], invocations)

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
