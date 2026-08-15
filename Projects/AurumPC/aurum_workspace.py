#!/usr/bin/env python3
"""Bounded seed, self-build, and Git workspace operations for Aurum PC."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPOSITORY = "https://github.com/FormatX66/BoxBrain.git"
BRANCH = "aurum/pi3-v0.01"
ALLOWED_PROMOTION_PATHS = frozenset({"Projects/Codelation/autobuild/native_chain_state.json"})


class WorkspaceError(RuntimeError):
    pass


def _run(
    arguments: list[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
    timeout: int = 300,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            arguments,
            cwd=str(cwd) if cwd else None,
            input=input_text,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorkspaceError(f"Bounded operation failed to start: {exc}") from exc
    if check and result.returncode != 0:
        raise WorkspaceError(result.stdout.strip()[-2000:] or f"Command exited {result.returncode}")
    return result


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


class AurumWorkspace:
    def __init__(
        self,
        *,
        installed_root: Path = Path("/opt/aurum/codelation"),
        workspace: Path = Path("/var/lib/aurum/workspace/BoxBrain"),
        state_dir: Path = Path("/var/lib/aurum/state"),
        repository: str = REPOSITORY,
        branch: str = BRANCH,
        runner: Any = _run,
    ):
        if repository.rstrip("/").removesuffix(".git") != REPOSITORY.removesuffix(".git"):
            raise WorkspaceError("Repository is outside the Aurum BoxBrain allowlist")
        if not re.fullmatch(r"[A-Za-z0-9._/-]{1,128}", branch) or ".." in branch:
            raise WorkspaceError("Configured Git branch is invalid")
        self.installed_root = installed_root
        self.workspace = workspace
        self.state_dir = state_dir
        self.repository = repository
        self.branch = branch
        self.runner = runner

    @property
    def repository_ready(self) -> bool:
        return (self.workspace / ".git").is_dir()

    @property
    def codelation(self) -> Path:
        candidate = self.workspace / "Projects" / "Codelation"
        return candidate if self.repository_ready and candidate.is_dir() else self.installed_root

    def _git(self, *arguments: str, check: bool = True, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
        if not self.repository_ready:
            raise WorkspaceError("Git workspace is not initialized; run git-sync authorize-network")
        return self.runner(
            ["git", *arguments], cwd=self.workspace, check=check, input_text=input_text, timeout=300
        )

    def git_status(self) -> dict[str, Any]:
        if not self.repository_ready:
            return {
                "status": "not-initialized",
                "repository": self.repository,
                "branch": self.branch,
                "workspace": str(self.workspace),
            }
        origin = self._git("remote", "get-url", "origin").stdout.strip()
        branch = self._git("branch", "--show-current").stdout.strip()
        head = self._git("rev-parse", "HEAD").stdout.strip()
        changes = [line for line in self._git("status", "--porcelain=v1").stdout.splitlines() if line]
        return {
            "status": "ready",
            "repository": origin,
            "branch": branch,
            "configured_branch": self.branch,
            "head": head,
            "workspace": str(self.workspace),
            "dirty": bool(changes),
            "changes": changes,
        }

    def git_sync(self, *, authorize_network: bool) -> dict[str, Any]:
        if not authorize_network:
            raise WorkspaceError("Git network access requires the exact authorize-network token")
        if not self.repository_ready:
            self.workspace.parent.mkdir(parents=True, exist_ok=True)
            self.runner(
                [
                    "git",
                    "clone",
                    "--filter=blob:none",
                    "--single-branch",
                    "--branch",
                    self.branch,
                    self.repository,
                    str(self.workspace),
                ],
                timeout=300,
            )
            return {"status": "cloned", **self.git_status()}

        origin = self._git("remote", "get-url", "origin").stdout.strip()
        if origin.rstrip("/").removesuffix(".git") != self.repository.removesuffix(".git"):
            raise WorkspaceError("Workspace origin is outside the Aurum BoxBrain allowlist")
        changes = self._git("status", "--porcelain=v1").stdout.strip()
        if changes:
            raise WorkspaceError("Workspace has local changes; refusing to overwrite or merge them")
        self._git("fetch", "--prune", "origin", self.branch)
        self._git("merge", "--ff-only", "FETCH_HEAD")
        return {"status": "fast-forwarded", **self.git_status()}

    def git_auth(self, token: str) -> dict[str, Any]:
        if not self.repository_ready:
            raise WorkspaceError("Initialize the Git workspace before authentication")
        if len(token) < 20 or any(character.isspace() for character in token):
            raise WorkspaceError("GitHub token format is invalid")
        self._git("config", "credential.helper", "cache --timeout=3600")
        credential = (
            "protocol=https\n"
            "host=github.com\n"
            "username=x-access-token\n"
            f"password={token}\n\n"
        )
        self._git("credential", "approve", input_text=credential)
        return {"status": "authenticated-in-memory", "expires_in_seconds": 3600, "token_persisted": False}

    def seed_status(self) -> dict[str, Any]:
        seed_script = self.codelation / "seed" / "codelation_seed.py"
        model = self.state_dir / "seed.bin"
        if not seed_script.is_file():
            raise WorkspaceError("Codelation bootstrap seed is unavailable")
        if not model.is_file():
            return {"status": "unseeded", "model": str(model), "source": str(self.codelation)}
        summary = self.runner(
            [sys.executable, str(seed_script), "summary", "--model", str(model)], timeout=30
        ).stdout.strip()
        return {"status": "seeded", "model": str(model), "source": str(self.codelation), "summary": summary}

    def seed(self) -> dict[str, Any]:
        seed_script = self.codelation / "seed" / "codelation_seed.py"
        if not seed_script.is_file():
            raise WorkspaceError("Codelation bootstrap seed is unavailable")
        model = self.state_dir / "seed.bin"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        observations = ("aurum-x86-boot", "aurum-x86-ready", "aurum-self-build-requested")
        results = []
        for observation in observations:
            result = self.runner(
                [sys.executable, str(seed_script), "observe", "--model", str(model), observation],
                timeout=30,
            )
            results.append(result.stdout.strip())
        status = self.seed_status()
        status["observations"] = results
        return status

    def self_build(self) -> dict[str, Any]:
        source = self.codelation
        chain = source / "run_native_autonomous_chain.py"
        tests = source / "tests"
        if not chain.is_file() or not tests.is_dir():
            raise WorkspaceError("Codelation self-build source is incomplete")
        core_patterns = (
            "test_seed.py",
            "test_native*.py",
            "test_field_native*.py",
            "test_local_capability_verification.py",
            "test_self_build*.py",
        )
        for pattern in core_patterns:
            self.runner(
                [sys.executable, "-m", "unittest", "discover", "-s", str(tests), "-p", pattern],
                cwd=source,
                timeout=300,
            )
        build = self.runner([sys.executable, str(chain)], cwd=source, timeout=900)
        try:
            state = json.loads(build.stdout)
        except json.JSONDecodeError as exc:
            raise WorkspaceError("Self-build did not return its required JSON state") from exc
        if int(state.get("completed_generations", 0)) < 1:
            raise WorkspaceError(f"Self-build completed no generations: {state.get('blocked_reason')}")
        head = None
        if self.repository_ready:
            head = self._git("rev-parse", "HEAD").stdout.strip()
        checkpoint = {
            "schema": "aurum-x86-self-build-checkpoint-v1",
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": str(source),
            "source_commit": head,
            "tests": "passed",
            "test_patterns": list(core_patterns),
            "completed_generations": state.get("completed_generations"),
            "latest_completed_gap": state.get("latest_completed_gap"),
            "next_gap": state.get("next_gap"),
            "blocked_reason": state.get("blocked_reason"),
            "trusted_for_continuation": (state.get("workflow_verification") or {}).get(
                "trusted_for_continuation"
            ),
        }
        _atomic_json(self.state_dir / "last-self-build.json", checkpoint)
        return checkpoint

    def git_promote(self, *, authorize_network: bool, confirm_push: bool) -> dict[str, Any]:
        if not authorize_network or not confirm_push:
            raise WorkspaceError("Promotion requires authorize-network and confirm-push")
        if not self.repository_ready:
            raise WorkspaceError("Git workspace is not initialized")
        checkpoint_path = self.state_dir / "last-self-build.json"
        if not checkpoint_path.is_file():
            raise WorkspaceError("Run a successful self-build before promotion")
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        current_head = self._git("rev-parse", "HEAD").stdout.strip()
        if checkpoint.get("source_commit") != current_head:
            raise WorkspaceError("Repository changed after the verified self-build; run self-build again")
        status_lines = [line for line in self._git("status", "--porcelain=v1").stdout.splitlines() if line]
        changed_paths = {line[3:].split(" -> ")[-1] for line in status_lines if len(line) >= 4}
        if not changed_paths:
            return {"status": "nothing-to-promote", "head": current_head}
        if not changed_paths.issubset(ALLOWED_PROMOTION_PATHS):
            blocked = sorted(changed_paths - ALLOWED_PROMOTION_PATHS)
            raise WorkspaceError(f"Self-build changed non-promotable paths: {blocked}")
        for path in sorted(changed_paths):
            self._git("add", "--", path)
        staged = self._git("diff", "--cached", "--quiet", check=False)
        if staged.returncode == 0:
            return {"status": "nothing-to-promote", "head": current_head}
        if staged.returncode != 1:
            raise WorkspaceError(staged.stdout.strip() or "Could not inspect the staged self-build checkpoint")
        self._git("config", "user.name", "Aurum x86 self-build")
        self._git("config", "user.email", "aurum-x86@localhost")
        self._git("commit", "-m", "Record Aurum x86 self-build checkpoint")
        self._git("push", "origin", f"HEAD:refs/heads/{self.branch}")
        new_head = self._git("rev-parse", "HEAD").stdout.strip()
        return {"status": "pushed", "branch": self.branch, "head": new_head, "paths": sorted(changed_paths)}
