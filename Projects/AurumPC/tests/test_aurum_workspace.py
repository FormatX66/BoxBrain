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
        self.baseline_state = self.root / "immutable-native-chain-state.json"
        self.runner = FakeRunner(self.workspace_path)
        self.workspace = aurum_workspace.AurumWorkspace(
            installed_root=self.installed,
            workspace=self.workspace_path,
            state_dir=self.state,
            baseline_state=self.baseline_state,
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
        self.baseline_state.write_text("{}\n", encoding="utf-8")

        progress_events: list[dict] = []

        def build_runner(arguments: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
            self.runner.calls.append((arguments, kwargs))
            if str(chain) in arguments:
                kwargs["progress"](
                    'AURUM_BUILD_PROGRESS {"status":"generation-completed","generation":2,"total_generations":24}'
                )
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
        result = self.workspace.self_build(progress=progress_events.append)
        self.assertEqual(result["tests"], "passed")
        self.assertEqual(result["completed_generations"], 2)
        self.assertTrue((self.state / "last-self-build.json").is_file())
        self.assertTrue((self.state / "self-build-progress.json").is_file())
        chain_call = next(call for call in self.runner.calls if str(chain) in call[0])
        self.assertIn("--resume", chain_call[0])
        self.assertEqual(
            chain_call[0][chain_call[0].index("--state-path") + 1],
            str(self.state / "native-chain-state.json"),
        )
        self.assertEqual(
            chain_call[0][chain_call[0].index("--resume-fallback-state") + 1],
            str(self.baseline_state),
        )
        self.assertTrue(
            any(event.get("generation") == 2 and event.get("stage") == "chain" for event in progress_events)
        )

    def test_git_self_build_keeps_promotable_checkpoint_in_workspace(self) -> None:
        (self.workspace_path / ".git").mkdir(parents=True)
        source = self.workspace_path / "Projects" / "Codelation"
        tests = source / "tests"
        tests.mkdir(parents=True)
        chain = source / "run_native_autonomous_chain.py"
        chain.write_text("# fixture\n", encoding="utf-8")

        def build_runner(arguments: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
            self.runner.calls.append((arguments, kwargs))
            if str(chain) in arguments:
                return subprocess.CompletedProcess(
                    arguments,
                    0,
                    json.dumps({"completed_generations": 1}),
                )
            return subprocess.CompletedProcess(arguments, 0, "OK\n")

        self.workspace.runner = build_runner
        self.workspace.self_build()

        chain_call = next(call for call in self.runner.calls if str(chain) in call[0])
        self.assertEqual(
            chain_call[0][chain_call[0].index("--state-path") + 1],
            str(source / "autobuild" / "native_chain_state.json"),
        )

    def test_self_build_can_cancel_before_the_next_stage(self) -> None:
        tests = self.installed / "tests"
        tests.mkdir(parents=True)
        (self.installed / "run_native_autonomous_chain.py").write_text("# fixture\n", encoding="utf-8")
        cancel = aurum_workspace.threading.Event()
        cancel.set()
        with self.assertRaisesRegex(aurum_workspace.WorkspaceError, "cancelled safely"):
            self.workspace.self_build(cancel_event=cancel)
        self.assertFalse(any("unittest" in arguments for arguments, _kwargs in self.runner.calls))

    def test_duplicate_self_build_is_refused_before_replaying_work(self) -> None:
        lock_path = self.state / "self-build.lock"
        with aurum_workspace._exclusive_build_lock(lock_path):
            with self.assertRaisesRegex(aurum_workspace.WorkspaceError, "already in progress"):
                self.workspace.self_build()
        self.assertEqual(self.runner.calls, [])

    def test_promotion_uses_fixed_identity_path_and_branch(self) -> None:
        (self.workspace_path / ".git").mkdir(parents=True)
        self.state.mkdir(parents=True)
        (self.state / "last-self-build.json").write_text(
            json.dumps({"source_commit": "a" * 40}), encoding="utf-8"
        )
        calls: list[list[str]] = []

        def promotion_runner(arguments: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
            calls.append(arguments)
            if arguments[:3] == ["git", "rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(arguments, 0, "a" * 40 + "\n")
            if arguments[:3] == ["git", "status", "--porcelain=v1"]:
                path = "Projects/Codelation/autobuild/native_chain_state.json"
                return subprocess.CompletedProcess(arguments, 0, f" M {path}\n")
            if arguments[:4] == ["git", "diff", "--cached", "--quiet"]:
                return subprocess.CompletedProcess(arguments, 1, "")
            return subprocess.CompletedProcess(arguments, 0, "")

        self.workspace.runner = promotion_runner
        result = self.workspace.git_promote(authorize_network=True, confirm_push=True)
        self.assertEqual(result["status"], "pushed")
        self.assertIn(["git", "config", "user.name", "Aurum x86 self-build"], calls)
        self.assertIn(["git", "config", "user.email", "aurum-x86@localhost"], calls)
        self.assertIn(
            ["git", "push", "origin", f"HEAD:refs/heads/{aurum_workspace.BRANCH}"], calls
        )


if __name__ == "__main__":
    unittest.main()
