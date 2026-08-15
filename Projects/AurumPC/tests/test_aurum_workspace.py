from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "aurum_workspace.py"
SPEC = importlib.util.spec_from_file_location("aurum_workspace", MODULE_PATH)
assert SPEC and SPEC.loader
aurum_workspace = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aurum_workspace)


class FakeRunner:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, arguments: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        self.calls.append((arguments, kwargs))
        output = ""
        returncode = 0
        if arguments[:2] == ["git", "clone"]:
            (self.workspace / ".git").mkdir(parents=True)
            (self.workspace / "Projects" / "Codelation").mkdir(parents=True)
        elif arguments[:4] == ["git", "remote", "get-url", "origin"]:
            output = aurum_workspace.REPOSITORY + "\n"
        elif arguments[:3] == ["git", "branch", "--show-current"]:
            output = aurum_workspace.BRANCH + "\n"
        elif arguments[:3] == ["git", "rev-parse", "HEAD"]:
            output = "a" * 40 + "\n"
        elif arguments[:3] == ["git", "status", "--porcelain=v1"]:
            output = ""
        return subprocess.CompletedProcess(arguments, returncode, output)


class AurumWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workspace_path = self.root / "workspace" / "BoxBrain"
        self.installed = self.root / "installed"
        self.state = self.root / "state"
        self.runner = FakeRunner(self.workspace_path)
        self.workspace = aurum_workspace.AurumWorkspace(
            installed_root=self.installed,
            workspace=self.workspace_path,
            state_dir=self.state,
            runner=self.runner,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_repository_allowlist_rejects_arbitrary_git_endpoint(self) -> None:
        with self.assertRaisesRegex(aurum_workspace.WorkspaceError, "outside"):
            aurum_workspace.AurumWorkspace(repository="https://example.invalid/attacker/repo.git")

    def test_git_sync_requires_explicit_network_authorization(self) -> None:
        with self.assertRaisesRegex(aurum_workspace.WorkspaceError, "authorize-network"):
            self.workspace.git_sync(authorize_network=False)
        self.assertEqual(self.runner.calls, [])

    def test_authorized_git_sync_uses_fixed_repository_and_branch(self) -> None:
        result = self.workspace.git_sync(authorize_network=True)
        clone = self.runner.calls[0][0]
        self.assertEqual(clone[0:2], ["git", "clone"])
        self.assertIn(aurum_workspace.REPOSITORY, clone)
        self.assertIn(aurum_workspace.BRANCH, clone)
        self.assertEqual(result["status"], "ready")
        self.assertFalse(result["dirty"])

    def test_seed_uses_fixed_python_entrypoint_not_a_shell(self) -> None:
        seed = self.installed / "seed" / "codelation_seed.py"
        seed.parent.mkdir(parents=True)
        seed.write_text("# fixture\n", encoding="utf-8")

        def seed_runner(arguments: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
            self.runner.calls.append((arguments, kwargs))
            if "observe" in arguments:
                model = Path(arguments[arguments.index("--model") + 1])
                model.parent.mkdir(parents=True, exist_ok=True)
                model.write_bytes(b"seed")
                output = "state=fixture prediction=none result=unscored\n"
            else:
                output = "version=1 states=3 edges=2 observations=2 confirmations=0\n"
            return subprocess.CompletedProcess(arguments, 0, output)

        self.workspace.runner = seed_runner
        result = self.workspace.seed()
        self.assertEqual(result["status"], "seeded")
        self.assertEqual(len(result["observations"]), 3)
        for arguments, _kwargs in self.runner.calls:
            self.assertNotIn("sh", arguments[:1])
            self.assertNotIn("bash", arguments[:1])

    def test_self_build_records_verified_checkpoint(self) -> None:
        tests = self.installed / "tests"
        tests.mkdir(parents=True)
        chain = self.installed / "run_native_autonomous_chain.py"
        chain.write_text("# fixture\n", encoding="utf-8")

        def build_runner(arguments: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
            if str(chain) in arguments:
                output = json.dumps(
                    {
                        "completed_generations": 2,
                        "latest_completed_gap": "io_safe_port_choice",
                        "next_gap": "interface_mode_selection",
                        "blocked_reason": None,
                    }
                )
            else:
                output = "Ran 5 tests\nOK\n"
            return subprocess.CompletedProcess(arguments, 0, output)

        self.workspace.runner = build_runner
        result = self.workspace.self_build()
        self.assertEqual(result["tests"], "passed")
        self.assertEqual(result["completed_generations"], 2)
        self.assertTrue((self.state / "last-self-build.json").is_file())


if __name__ == "__main__":
    unittest.main()
