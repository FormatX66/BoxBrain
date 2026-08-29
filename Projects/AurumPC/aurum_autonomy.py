#!/usr/bin/env python3
"""Unattended bounded build loop for the explicitly authorized Aurum PC-01.

The loop is machine-bound by the install receipt and repository policy.  It
reconnects saved networking, fast-forwards the allowlisted Aurum trunk, applies
only the guarded installed-runtime allowlist, runs a local resumable self-build
without dirtying Git, starts the loopback GUI, and advances the adaptive driver
model lane.  It never pushes Git, loads synthesized drivers, replaces bound
drivers, writes firmware, or reboots unless a matching policy explicitly says
so. Published generations never move backward: a candidate is healed or
culled and a later descendant regrows forward.
"""
from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "aurum-pc-autonomy-v1"
REPOSITORY = "https://github.com/FormatX66/BoxBrain.git"
BRANCH = "aurum/trunk-v0.01"
DEFAULT_WORKSPACE = Path(os.environ.get("AURUM_GIT_WORKSPACE", "/var/lib/aurum/workspace/BoxBrain"))
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
DEFAULT_POLICY = Path(__file__).with_name("pc01_autonomy_policy.json")
DEFAULT_INSTALL_RECEIPT = Path("/etc/aurum-installed.json")


class AutonomyError(RuntimeError):
    pass


def _run(arguments: list[str], *, cwd: Path | None = None, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            arguments,
            cwd=str(cwd) if cwd else None,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AutonomyError(f"bounded autonomous operation failed: {type(exc).__name__}:{exc}") from exc


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def load_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    return _json_file(path)


def machine_authorized(policy: Mapping[str, Any], receipt_path: Path = DEFAULT_INSTALL_RECEIPT) -> tuple[bool, str]:
    if policy.get("schema") != "aurum-pc-autonomy-policy-v1" or policy.get("enabled") is not True:
        return False, "policy-disabled-or-invalid"
    receipt = _json_file(receipt_path)
    target = receipt.get("target") if isinstance(receipt.get("target"), dict) else {}
    match = policy.get("machine_match") if isinstance(policy.get("machine_match"), dict) else {}
    expected_serial = str(match.get("installed_target_serial") or "")
    expected_size = int(match.get("installed_target_size_bytes") or 0)
    if not expected_serial or expected_size <= 0:
        return False, "machine-match-incomplete"
    if str(target.get("serial") or "") != expected_serial:
        return False, "installed-target-serial-mismatch"
    if int(target.get("size_bytes") or 0) != expected_size:
        return False, "installed-target-size-mismatch"
    return True, "authorized-machine-match"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AutonomyError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class AutonomyManager:
    def __init__(
        self,
        *,
        workspace: Path = DEFAULT_WORKSPACE,
        state_dir: Path = DEFAULT_STATE,
        policy_path: Path = DEFAULT_POLICY,
        receipt_path: Path = DEFAULT_INSTALL_RECEIPT,
    ) -> None:
        self.workspace = workspace
        self.state_dir = state_dir
        self.policy_path = policy_path
        self.receipt_path = receipt_path
        self.policy = load_policy(policy_path)
        self.source = workspace / "Projects" / "AurumPC"
        self.codelation = workspace / "Projects" / "Codelation"
        self.state_path = state_dir / "autonomy.json"
        self.lock_path = state_dir / "autonomy.lock"

    def status(self) -> dict[str, Any]:
        current = _json_file(self.state_path)
        if current:
            return current
        authorized, reason = machine_authorized(self.policy, self.receipt_path)
        return {
            "schema": SCHEMA,
            "status": "never-started",
            "authorized": authorized,
            "authorization_reason": reason,
            "policy": str(self.policy_path),
        }

    def _network(self) -> dict[str, Any]:
        candidates = [self.source / "aurum_network.py", Path("/opt/aurum/aurum_network.py")]
        path = next((candidate for candidate in candidates if candidate.is_file()), None)
        if path is None:
            return {"status": "network-helper-missing", "online": False}
        module = _load_module(path, f"aurum_autonomy_network_{os.getpid()}_{time.time_ns()}")
        try:
            result = module.ensure_online(interactive=False)
            return dict(result)
        except Exception as exc:
            return {"status": "failed", "online": False, "detail": f"{type(exc).__name__}:{exc}"}

    def _git_head(self) -> str | None:
        result = _run(["git", "rev-parse", "HEAD"], cwd=self.workspace, timeout=20)
        return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None

    def _git_sync(self) -> dict[str, Any]:
        if not (self.workspace / ".git").is_dir():
            return {"status": "workspace-unavailable"}
        origin = _run(["git", "remote", "get-url", "origin"], cwd=self.workspace, timeout=20)
        if origin.returncode != 0 or origin.stdout.strip().rstrip("/").removesuffix(".git") != REPOSITORY.removesuffix(".git"):
            return {"status": "refused", "reason": "origin-outside-allowlist"}
        branch = _run(["git", "branch", "--show-current"], cwd=self.workspace, timeout=20)
        if branch.returncode != 0 or branch.stdout.strip() != BRANCH:
            return {"status": "refused", "reason": "branch-outside-allowlist", "branch": branch.stdout.strip()}
        dirty = _run(["git", "status", "--porcelain=v1"], cwd=self.workspace, timeout=30)
        if dirty.returncode != 0:
            return {"status": "failed", "phase": "status", "detail": dirty.stdout.strip()[-1000:]}
        before = self._git_head()
        checkpoint = None
        changes = [line for line in dirty.stdout.splitlines() if line]
        if changes:
            stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            checkpoint = f"aurum-auto-checkpoint-{stamp}"
            stashed = _run(["git", "stash", "push", "-u", "-m", checkpoint], cwd=self.workspace, timeout=120)
            if stashed.returncode != 0:
                return {
                    "status": "failed",
                    "phase": "checkpoint",
                    "detail": stashed.stdout.strip()[-1500:],
                    "before": before,
                }
            _atomic_json(
                self.state_dir / "last-workspace-checkpoint.json",
                {
                    "schema": "aurum-workspace-checkpoint-v1",
                    "at": stamp,
                    "repository": origin.stdout.strip(),
                    "branch": branch.stdout.strip(),
                    "head_before_sync": before,
                    "checkpoint": checkpoint,
                    "changes": changes,
                    "preserved": True,
                    "reapplied": False,
                    "source": "autonomy",
                },
            )
        fetched = _run(["git", "fetch", "--prune", "origin", BRANCH], cwd=self.workspace, timeout=180)
        if fetched.returncode != 0:
            return {"status": "failed", "phase": "fetch", "detail": fetched.stdout[-1500:], "before": before, "checkpoint": checkpoint}
        fetched_head_result = _run(["git", "rev-parse", "FETCH_HEAD"], cwd=self.workspace, timeout=20)
        fetched_head = fetched_head_result.stdout.strip() if fetched_head_result.returncode == 0 else None
        if not fetched_head:
            return {"status": "failed", "phase": "verify", "reason": "fetched-head-unavailable", "before": before, "checkpoint": checkpoint}
        if before:
            ancestry = _run(["git", "merge-base", "--is-ancestor", before, fetched_head], cwd=self.workspace, timeout=30)
            if ancestry.returncode != 0:
                return {
                    "status": "refused",
                    "phase": "verify",
                    "reason": "non-fast-forward-generation",
                    "before": before,
                    "fetched_head": fetched_head,
                    "checkpoint": checkpoint,
                }
        merged = _run(["git", "merge", "--ff-only", "FETCH_HEAD"], cwd=self.workspace, timeout=120)
        if merged.returncode != 0:
            return {"status": "failed", "phase": "merge", "detail": merged.stdout[-1500:], "before": before, "checkpoint": checkpoint}
        after = self._git_head()
        clean_after = _run(["git", "status", "--porcelain=v1"], cwd=self.workspace, timeout=30)
        verified = bool(after == fetched_head and clean_after.returncode == 0 and not clean_after.stdout.strip())
        result = {
            "status": "ready" if verified else "failed",
            "phase": "verified" if verified else "verify",
            "before": before,
            "head": after,
            "fetched_head": fetched_head,
            "changed": before != after,
            "verification": {
                "passed": verified,
                "exact_origin": True,
                "exact_branch": True,
                "fast_forward_only": True,
                "head_matches_fetched": after == fetched_head,
                "clean": clean_after.returncode == 0 and not clean_after.stdout.strip(),
            },
        }
        if checkpoint is not None:
            result.update(
                {
                    "checkpoint": checkpoint,
                    "checkpoint_preserved": True,
                    "checkpoint_reapplied": False,
                }
            )
        return result

    def _subprocess_json(self, script: Path, *arguments: str, timeout: int = 300) -> dict[str, Any]:
        if not script.is_file():
            return {"status": "script-missing", "script": str(script)}
        result = _run([sys.executable, str(script), *arguments], cwd=self.workspace, timeout=timeout)
        text = result.stdout.strip()
        try:
            payload = json.loads(text.splitlines()[-1]) if text else {}
        except json.JSONDecodeError:
            payload = {"status": "failed" if result.returncode else "completed", "detail": text[-3000:]}
        if result.returncode != 0 and payload.get("status") not in {"failed", "refused"}:
            payload["status"] = "failed"
        return payload

    def _runtime_sync(self) -> dict[str, Any]:
        return self._subprocess_json(self.source / "aurum_runtime_update.py", "apply", timeout=480)

    def _driver_cycle(self) -> dict[str, Any]:
        return self._subprocess_json(
            self.source / "aurum_driver_synthesis.py",
            "cycle",
            "--policy",
            str(self.policy_path),
            timeout=900,
        )

    def _gui_start(self) -> dict[str, Any]:
        return self._subprocess_json(self.source / "aurum_gui_runtime.py", "start", timeout=30)

    def _self_build(self, head: str | None) -> dict[str, Any]:
        module_path = self.source / "aurum_workspace.py"
        if not module_path.is_file() or not self.codelation.is_dir():
            return {"status": "source-missing"}
        module = _load_module(module_path, f"aurum_autonomy_workspace_{os.getpid()}_{time.time_ns()}")
        # Deliberately make repository_ready false while pointing installed_root
        # at the latest Git source. This keeps resumable autonomous checkpoints
        # under /var/lib/aurum/state instead of dirtying the fetched repository.
        workspace = module.AurumWorkspace(
            installed_root=self.codelation,
            workspace=self.state_dir / "autonomy-nonrepo-workspace",
            state_dir=self.state_dir,
            baseline_state=self.codelation / "autobuild" / "native_chain_state.json",
        )
        try:
            result = workspace.self_build()
        except module.WorkspaceError as exc:
            return {"status": "failed", "detail": str(exc), "source_head": head}
        return {"status": "passed", "source_head": head, "result": result}

    def cycle(self) -> dict[str, Any]:
        authorized, reason = machine_authorized(self.policy, self.receipt_path)
        if not authorized:
            result = {"schema": SCHEMA, "status": "disabled", "authorized": False, "authorization_reason": reason}
            _atomic_json(self.state_path, result)
            return result
        started = time.monotonic()
        previous = self.status()
        network = self._network()
        git: dict[str, Any] = {"status": "skipped"}
        if bool(self.policy.get("auto_git_sync")) and network.get("online"):
            git = self._git_sync()
        head = git.get("head") or self._git_head()
        runtime: dict[str, Any] = {"status": "skipped"}
        if bool(self.policy.get("auto_runtime_update")) and self.source.is_dir():
            runtime = self._runtime_sync()
        driver: dict[str, Any] = {"status": "skipped"}
        if bool(self.policy.get("auto_driver_synthesis")) and self.source.is_dir():
            driver = self._driver_cycle()
        self_build: dict[str, Any] = {"status": "skipped", "reason": "source-head-already-validated"}
        last_self_build_head = previous.get("last_self_build_head")
        if bool(self.policy.get("auto_self_build")) and head and head != last_self_build_head:
            self_build = self._self_build(head)
            if self_build.get("status") == "passed":
                last_self_build_head = head
        gui: dict[str, Any] = {"status": "skipped"}
        if bool(self.policy.get("auto_gui_start")) and self.source.is_dir():
            gui = self._gui_start()
        result = {
            "schema": SCHEMA,
            "status": "cycle-complete",
            "authorized": True,
            "authorization_reason": reason,
            "authorization_reference": self.policy.get("authorization_reference"),
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "network": network,
            "git": git,
            "head": head,
            "runtime": runtime,
            "driver": driver,
            "self_build": self_build,
            "last_self_build_head": last_self_build_head,
            "gui": gui,
            "generation": {
                "schema": "aurum.seed-generation-cycle.v1",
                "discover": {"status": "passed" if network.get("online") else "failed"},
                "pull": {"status": git.get("status"), "changed": bool(git.get("changed"))},
                "verify": git.get("verification") or {"passed": False, "reason": git.get("reason")},
                "stage": ((runtime.get("generation") or {}).get("stage") if isinstance(runtime.get("generation"), dict) else None),
                "apply": ((runtime.get("generation") or {}).get("apply") if isinstance(runtime.get("generation"), dict) else None),
                "prove": ((runtime.get("generation") or {}).get("prove") if isinstance(runtime.get("generation"), dict) else None),
                "disposition": ((runtime.get("generation") or {}).get("disposition") if isinstance(runtime.get("generation"), dict) else None),
                "lineage": runtime.get("lineage"),
                "become_next_seed": bool((runtime.get("generation") or {}).get("become_next_seed")) if isinstance(runtime.get("generation"), dict) else False,
            },
            "next_cycle_seconds": int(self.policy.get("poll_interval_seconds") or 300),
            "unattended": True,
            "pushes_git": False,
            "driver_physical_swap": False,
        }
        _atomic_json(self.state_path, result)
        return result

    def run(self, *, once: bool = False) -> int:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return 0
            authorized, reason = machine_authorized(self.policy, self.receipt_path)
            if not authorized:
                _atomic_json(self.state_path, {"schema": SCHEMA, "status": "disabled", "authorized": False, "authorization_reason": reason})
                return 0
            try:
                os.nice(5)
            except OSError:
                pass
            while True:
                try:
                    self.cycle()
                except Exception as exc:
                    previous = self.status()
                    failure = {
                        **previous,
                        "schema": SCHEMA,
                        "status": "cycle-failed",
                        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "detail": f"{type(exc).__name__}:{exc}",
                    }
                    _atomic_json(self.state_path, failure)
                if once:
                    return 0
                interval = max(60, min(int(self.policy.get("poll_interval_seconds") or 300), 3600))
                time.sleep(interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aurum PC unattended build loop")
    parser.add_argument("command", choices=("run", "cycle", "status"))
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_INSTALL_RECEIPT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    manager = AutonomyManager(workspace=args.workspace, state_dir=args.state_dir, policy_path=args.policy, receipt_path=args.receipt)
    if args.command == "status":
        print(json.dumps(manager.status(), sort_keys=True))
        return 0
    if args.command == "cycle":
        print(json.dumps(manager.cycle(), sort_keys=True))
        return 0
    return manager.run()


if __name__ == "__main__":
    raise SystemExit(main())
