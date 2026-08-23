from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


MODULE_PATH = Path(__file__).parents[1] / "aurum_seed_recovery.py"
SPEC = importlib.util.spec_from_file_location("aurum_seed_recovery", MODULE_PATH)
assert SPEC and SPEC.loader
recovery_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = recovery_module
SPEC.loader.exec_module(recovery_module)


class AurumSeedRecoveryTests(unittest.TestCase):
    def _fixture(self, root: Path):
        installed = root / "installed"
        workspace = installed / "var/lib/aurum/workspace/BoxBrain"
        source = workspace / "Projects/AurumPC"
        source.mkdir(parents=True)
        for name in ("aurum_desktop.py", "aurum_hopper_gui.py", "untouched.py"):
            (source / name).write_text(f"VALUE = {name!r}\n", encoding="utf-8")
        subprocess.run(
            ["git", "init", "-b", recovery_module.BRANCH],
            cwd=workspace,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        for key, value in (
            ("user.name", "Aurum Recovery Test"),
            ("user.email", "aurum-recovery@example.invalid"),
            ("core.autocrlf", "false"),
        ):
            subprocess.run(["git", "config", key, value], cwd=workspace, check=True)
        subprocess.run(
            ["git", "remote", "add", "origin", recovery_module.REPOSITORY],
            cwd=workspace,
            check=True,
        )
        subprocess.run(["git", "add", "."], cwd=workspace, check=True)
        subprocess.run(
            ["git", "commit", "-m", "clean seed"],
            cwd=workspace,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=workspace,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        receipt = {
            "schema": recovery_module.INSTALL_RECEIPT_SCHEMA,
            "mode": "installed",
            "target": {"serial": "TEST-HOPPER", "size_bytes": 512000},
        }
        receipt_path = installed / "etc/aurum-installed.json"
        receipt_path.parent.mkdir(parents=True)
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        policy_path = root / "policy.json"
        policy_path.write_text(
            json.dumps(
                {
                    "schema": recovery_module.POLICY_SCHEMA,
                    "machine": {"serial": "TEST-HOPPER", "size_bytes": 512000},
                    "repository": recovery_module.REPOSITORY,
                    "branch": recovery_module.BRANCH,
                    "expected_head": head,
                    "workspace": "/var/lib/aurum/workspace/BoxBrain",
                    "state_directory": "/var/lib/aurum/state",
                    "dirty_worktree_paths": [
                        "Projects/AurumPC/aurum_desktop.py",
                        "Projects/AurumPC/aurum_hopper_gui.py",
                    ],
                }
            ),
            encoding="utf-8",
        )
        disk = recovery_module.DiskIdentity(
            path="/dev/testdisk",
            partition="/dev/testdisk2",
            serial="TEST-HOPPER",
            size_bytes=512000,
            transport="test",
        )
        return installed, workspace, source, policy_path, disk

    def test_exact_two_file_recovery_preserves_patch_and_proves_clean(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installed, workspace, source, policy_path, disk = self._fixture(root)
            (source / "aurum_desktop.py").write_text("BACKGROUND = 'orange'\n", encoding="utf-8")
            (source / "aurum_hopper_gui.py").write_text("BACKGROUND = 'orange'\n", encoding="utf-8")
            recovery = recovery_module.HopperSeedRecovery(
                recovery_module.RecoveryPolicy.load(policy_path)
            )

            result = recovery.repair_mounted_root(installed, disk)

            self.assertEqual(result["status"], "clean")
            self.assertEqual(result["head_before"], result["head_after"])
            self.assertEqual(result["status_after"], [])
            status = subprocess.run(
                ["git", "status", "--porcelain=v1"],
                cwd=workspace,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout
            self.assertEqual(status, "")
            evidence = installed / result["evidence_directory"]
            patch = evidence / "temporary-ui.patch"
            self.assertTrue(patch.is_file())
            self.assertIn("orange", patch.read_text(encoding="utf-8"))
            self.assertEqual(result["patch_sha256"], recovery_module._sha256(patch))
            self.assertTrue((evidence / "recovery-complete.json").is_file())
            self.assertTrue((installed / "var/lib/aurum/state/last-seed-recovery.json").is_file())

    def test_unrelated_dirty_file_stops_without_restoring_anything(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installed, _workspace, source, policy_path, disk = self._fixture(root)
            desktop = source / "aurum_desktop.py"
            hopper = source / "aurum_hopper_gui.py"
            untouched = source / "untouched.py"
            desktop.write_text("BACKGROUND = 'orange'\n", encoding="utf-8")
            hopper.write_text("BACKGROUND = 'orange'\n", encoding="utf-8")
            untouched.write_text("UNRELATED = True\n", encoding="utf-8")
            recovery = recovery_module.HopperSeedRecovery(
                recovery_module.RecoveryPolicy.load(policy_path)
            )

            with self.assertRaises(recovery_module.RecoveryError):
                recovery.repair_mounted_root(installed, disk)

            self.assertIn("orange", desktop.read_text(encoding="utf-8"))
            self.assertIn("orange", hopper.read_text(encoding="utf-8"))
            self.assertIn("UNRELATED", untouched.read_text(encoding="utf-8"))
            self.assertFalse((installed / "var/lib/aurum/state/recovery").exists())

    def test_policy_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "policy.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": recovery_module.POLICY_SCHEMA,
                        "machine": {"serial": "TEST", "size_bytes": 1},
                        "repository": recovery_module.REPOSITORY,
                        "branch": recovery_module.BRANCH,
                        "expected_head": "a" * 40,
                        "workspace": "/var/lib/aurum/workspace/BoxBrain",
                        "state_directory": "/var/lib/aurum/state",
                        "dirty_worktree_paths": ["Projects/AurumPC/../../etc/shadow.py"],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(recovery_module.RecoveryError):
                recovery_module.RecoveryPolicy.load(path)


if __name__ == "__main__":
    unittest.main()
