#!/usr/bin/env python3
"""Machine-bound, one-shot repair for a dirty Hopper seed workspace.

This program is intended to run from a dedicated read-only recovery image.  It
does not install Aurum, fetch source, accept arbitrary paths, or expose a shell.
The image-bundled policy names one machine, one current commit, and the exact
worktree-only paths that may be restored from that commit.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable


POLICY_SCHEMA = "aurum.hopper-seed-recovery-policy.v1"
RECEIPT_SCHEMA = "aurum.hopper-seed-recovery-receipt.v1"
INSTALL_RECEIPT_SCHEMA = "aurum-pc-guided-installer-v1"
REPOSITORY = "https://github.com/FormatX66/BoxBrain.git"
BRANCH = "aurum/trunk-v0.01"
BOOT_TOKEN = "aurum_hopper_recovery=1"
DEFAULT_POLICY = Path("/etc/aurum/hopper-seed-recovery-policy.json")
DEFAULT_MOUNT_BASE = Path("/run/aurum-hopper-recovery")


class RecoveryError(RuntimeError):
    """Raised when recovery cannot be proven safe."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_bytes(path: Path, value: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_json(path: Path, value: dict[str, Any], mode: int = 0o600) -> None:
    _atomic_bytes(
        path,
        (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        mode,
    )


def _normalized_repository(value: str) -> str:
    return value.strip().rstrip("/").removesuffix(".git")


def _rooted(root: Path, absolute: PurePosixPath) -> Path:
    return root.joinpath(*absolute.parts[1:])


@dataclass(frozen=True)
class RecoveryPolicy:
    machine_serial: str
    machine_size_bytes: int
    repository: str
    branch: str
    expected_head: str
    workspace: PurePosixPath
    state_directory: PurePosixPath
    dirty_paths: tuple[PurePosixPath, ...]
    source_iso_sha256: str | None = None

    @classmethod
    def load(cls, path: Path) -> "RecoveryPolicy":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RecoveryError(f"Recovery policy is unreadable: {error}") from error
        if not isinstance(payload, dict) or payload.get("schema") != POLICY_SCHEMA:
            raise RecoveryError("Recovery policy schema is invalid")
        machine = payload.get("machine")
        if not isinstance(machine, dict):
            raise RecoveryError("Recovery policy machine identity is missing")
        serial = str(machine.get("serial") or "").strip()
        try:
            size_bytes = int(machine.get("size_bytes") or 0)
        except (TypeError, ValueError) as error:
            raise RecoveryError("Recovery policy machine size is invalid") from error
        repository = str(payload.get("repository") or "").strip()
        branch = str(payload.get("branch") or "").strip()
        expected_head = str(payload.get("expected_head") or "").strip().lower()
        workspace = cls._absolute_path(payload.get("workspace"), "workspace")
        state_directory = cls._absolute_path(payload.get("state_directory"), "state directory")
        raw_paths = payload.get("dirty_worktree_paths")
        if not isinstance(raw_paths, list) or not raw_paths:
            raise RecoveryError("Recovery policy must name at least one dirty path")
        dirty_paths: list[PurePosixPath] = []
        for raw in raw_paths:
            relative = PurePosixPath(str(raw))
            if (
                relative.is_absolute()
                or not relative.parts
                or ".." in relative.parts
                or relative.parts[:2] != ("Projects", "AurumPC")
                or relative.suffix != ".py"
            ):
                raise RecoveryError(f"Recovery path is outside the bounded Aurum source: {raw}")
            dirty_paths.append(relative)
        if len(set(dirty_paths)) != len(dirty_paths):
            raise RecoveryError("Recovery policy contains duplicate dirty paths")
        if not serial or size_bytes <= 0:
            raise RecoveryError("Recovery policy machine identity is incomplete")
        if _normalized_repository(repository) != _normalized_repository(REPOSITORY):
            raise RecoveryError("Recovery repository is outside the Aurum allowlist")
        if branch != BRANCH:
            raise RecoveryError("Recovery branch is outside the Aurum allowlist")
        if re.fullmatch(r"[0-9a-f]{40}", expected_head) is None:
            raise RecoveryError("Recovery expected head is invalid")
        source_sha = payload.get("source_iso_sha256")
        if source_sha is not None and re.fullmatch(r"[0-9a-f]{64}", str(source_sha)) is None:
            raise RecoveryError("Recovery source image hash is invalid")
        return cls(
            machine_serial=serial,
            machine_size_bytes=size_bytes,
            repository=repository,
            branch=branch,
            expected_head=expected_head,
            workspace=workspace,
            state_directory=state_directory,
            dirty_paths=tuple(dirty_paths),
            source_iso_sha256=str(source_sha) if source_sha else None,
        )

    @staticmethod
    def _absolute_path(raw: Any, label: str) -> PurePosixPath:
        value = PurePosixPath(str(raw or ""))
        if not value.is_absolute() or ".." in value.parts or len(value.parts) < 2:
            raise RecoveryError(f"Recovery {label} must be a bounded absolute path")
        return value

    def public_dict(self) -> dict[str, Any]:
        return {
            "schema": POLICY_SCHEMA,
            "machine": {
                "serial": self.machine_serial,
                "size_bytes": self.machine_size_bytes,
            },
            "repository": self.repository,
            "branch": self.branch,
            "expected_head": self.expected_head,
            "workspace": str(self.workspace),
            "state_directory": str(self.state_directory),
            "dirty_worktree_paths": [str(path) for path in self.dirty_paths],
            "source_iso_sha256": self.source_iso_sha256,
        }


@dataclass(frozen=True)
class DiskIdentity:
    path: str
    partition: str
    serial: str
    size_bytes: int
    transport: str


@dataclass(frozen=True)
class GitEvidence:
    origin: str
    branch: str
    head: str
    status_lines: tuple[str, ...]


class Reporter:
    def __init__(self, tty: Path = Path("/dev/tty1")) -> None:
        self.tty = tty

    def write(self, message: str, *, clear: bool = False) -> None:
        line = message.rstrip() + "\n"
        print(line, end="", flush=True)
        try:
            with self.tty.open("w", encoding="utf-8", errors="replace") as stream:
                if clear:
                    stream.write("\033[2J\033[H")
                stream.write(line)
                stream.flush()
        except OSError:
            pass


class HopperSeedRecovery:
    def __init__(
        self,
        policy: RecoveryPolicy,
        *,
        mount_base: Path = DEFAULT_MOUNT_BASE,
        runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
        reporter: Reporter | None = None,
    ) -> None:
        self.policy = policy
        self.mount_base = mount_base
        self.runner = runner
        self.reporter = reporter or Reporter()
        self.git = shutil.which("git") or "/usr/bin/git"

    def _command(
        self,
        arguments: list[str],
        *,
        check: bool = True,
        text: bool = True,
        timeout: int = 60,
    ) -> subprocess.CompletedProcess[Any]:
        result = self.runner(
            arguments,
            check=False,
            text=text,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        if check and result.returncode != 0:
            detail = result.stdout if isinstance(result.stdout, str) else result.stdout.decode("utf-8", "replace")
            raise RecoveryError(f"Bounded command failed ({arguments[0]}): {detail[-800:].strip()}")
        return result

    def _git(
        self,
        workspace: Path,
        *arguments: str,
        check: bool = True,
        text: bool = True,
    ) -> subprocess.CompletedProcess[Any]:
        return self._command(
            [self.git, "-c", f"safe.directory={workspace}", "-C", str(workspace), *arguments],
            check=check,
            text=text,
            timeout=120,
        )

    def _git_evidence(self, workspace: Path) -> GitEvidence:
        if not (workspace / ".git").is_dir():
            raise RecoveryError("The Hopper Git workspace is unavailable")
        origin = self._git(workspace, "remote", "get-url", "origin").stdout.strip()
        branch = self._git(workspace, "branch", "--show-current").stdout.strip()
        head = self._git(workspace, "rev-parse", "HEAD").stdout.strip().lower()
        status = self._git(
            workspace,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ).stdout.splitlines()
        return GitEvidence(origin=origin, branch=branch, head=head, status_lines=tuple(status))

    def _verify_git(self, workspace: Path, *, require_dirty: bool) -> GitEvidence:
        evidence = self._git_evidence(workspace)
        if _normalized_repository(evidence.origin) != _normalized_repository(self.policy.repository):
            raise RecoveryError("Hopper workspace origin does not match the recovery policy")
        if evidence.branch != self.policy.branch:
            raise RecoveryError("Hopper workspace branch does not match the recovery policy")
        if evidence.head != self.policy.expected_head:
            raise RecoveryError("Hopper workspace head does not match the recovery policy")
        expected = {f" M {path}" for path in self.policy.dirty_paths}
        actual = set(evidence.status_lines)
        if require_dirty and actual != expected:
            raise RecoveryError(
                "Hopper workspace changes are not the exact bounded recovery set: "
                + json.dumps(sorted(actual))
            )
        if not require_dirty and actual:
            raise RecoveryError("Hopper workspace is not clean after recovery")
        return evidence

    def _verify_receipt(self, root: Path, disk: DiskIdentity) -> dict[str, Any]:
        receipt_path = root / "etc" / "aurum-installed.json"
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RecoveryError("Aurum installed receipt is unavailable") from error
        target = receipt.get("target") if isinstance(receipt, dict) else None
        if (
            not isinstance(receipt, dict)
            or receipt.get("schema") != INSTALL_RECEIPT_SCHEMA
            or receipt.get("mode") != "installed"
            or not isinstance(target, dict)
            or str(target.get("serial") or "").strip() != self.policy.machine_serial
            or int(target.get("size_bytes") or 0) != self.policy.machine_size_bytes
        ):
            raise RecoveryError("Aurum installed receipt does not identify Hopper")
        if (
            disk.serial != self.policy.machine_serial
            or disk.size_bytes != self.policy.machine_size_bytes
        ):
            raise RecoveryError("Physical internal drive identity does not identify Hopper")
        return receipt

    def inspect_mounted_root(
        self,
        root: Path,
        disk: DiskIdentity,
        *,
        require_dirty: bool,
    ) -> tuple[dict[str, Any], GitEvidence]:
        receipt = self._verify_receipt(root, disk)
        workspace = _rooted(root, self.policy.workspace)
        evidence = self._verify_git(workspace, require_dirty=require_dirty)
        return receipt, evidence

    def repair_mounted_root(self, root: Path, disk: DiskIdentity) -> dict[str, Any]:
        """Preserve evidence and restore only policy-named worktree files."""
        receipt, before = self.inspect_mounted_root(root, disk, require_dirty=True)
        workspace = _rooted(root, self.policy.workspace)
        state_directory = _rooted(root, self.policy.state_directory)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        evidence_directory = state_directory / "recovery" / f"hopper-seed-{stamp}"
        evidence_directory.mkdir(parents=True, mode=0o700, exist_ok=False)

        paths = [str(path) for path in self.policy.dirty_paths]
        patch_result = self._git(
            workspace,
            "diff",
            "--binary",
            "--no-ext-diff",
            "--",
            *paths,
            text=False,
        )
        patch = bytes(patch_result.stdout)
        if not patch:
            raise RecoveryError("The bounded dirty files produced no preservable patch")
        patch_path = evidence_directory / "temporary-ui.patch"
        _atomic_bytes(patch_path, patch)
        _atomic_bytes(
            evidence_directory / "pre-status.txt",
            ("\n".join(before.status_lines) + "\n").encode("utf-8"),
        )
        _atomic_json(evidence_directory / "install-receipt.json", receipt)
        _atomic_json(evidence_directory / "recovery-policy.json", self.policy.public_dict())

        pre_hashes = {
            path: _sha256(workspace / PurePosixPath(path))
            for path in paths
        }
        restore_started = False
        try:
            restore_started = True
            self._git(
                workspace,
                "restore",
                "--source=HEAD",
                "--worktree",
                "--",
                *paths,
            )
            after = self._verify_git(workspace, require_dirty=False)
            clean_hashes: dict[str, str] = {}
            for path in paths:
                working_hash = self._git(workspace, "hash-object", path).stdout.strip()
                committed_hash = self._git(workspace, "rev-parse", f"HEAD:{path}").stdout.strip()
                if working_hash != committed_hash:
                    raise RecoveryError(f"Restored file does not match current seed: {path}")
                clean_hashes[path] = _sha256(workspace / PurePosixPath(path))
        except Exception as error:
            rollback: dict[str, Any] = {"attempted": restore_started, "restored_original_dirty_state": False}
            if restore_started:
                try:
                    self._git(workspace, "restore", "--source=HEAD", "--worktree", "--", *paths)
                    self._git(workspace, "apply", "--binary", "--whitespace=nowarn", str(patch_path))
                    rolled_back = self._verify_git(workspace, require_dirty=True)
                    rollback["restored_original_dirty_state"] = set(rolled_back.status_lines) == {
                        f" M {path}" for path in self.policy.dirty_paths
                    }
                except Exception as rollback_error:
                    rollback["error"] = str(rollback_error)
            failure = {
                "schema": RECEIPT_SCHEMA,
                "status": "failed",
                "error": str(error),
                "rollback": rollback,
                "evidence_directory": str(evidence_directory.relative_to(root)),
                "patch_sha256": _sha256(patch_path),
                "head": before.head,
            }
            _atomic_json(evidence_directory / "recovery-failed.json", failure)
            raise RecoveryError(f"Recovery failed after evidence capture: {error}") from error

        result = {
            "schema": RECEIPT_SCHEMA,
            "status": "clean",
            "machine": {
                "serial": disk.serial,
                "size_bytes": disk.size_bytes,
                "disk": disk.path,
                "partition": disk.partition,
                "transport": disk.transport,
            },
            "repository": before.origin,
            "branch": after.branch,
            "head_before": before.head,
            "head_after": after.head,
            "restored_paths": paths,
            "status_before": list(before.status_lines),
            "status_after": list(after.status_lines),
            "pre_restore_sha256": pre_hashes,
            "clean_sha256": clean_hashes,
            "patch": str(patch_path.relative_to(root)),
            "patch_sha256": _sha256(patch_path),
            "evidence_directory": str(evidence_directory.relative_to(root)),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "next_action": "normal-running-seed-generation",
        }
        _atomic_json(evidence_directory / "recovery-complete.json", result)
        _atomic_json(state_directory / "last-seed-recovery.json", result)
        return result

    @staticmethod
    def _bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes"}

    def _disk_candidates(self) -> list[DiskIdentity]:
        result = self._command(
            [
                "lsblk",
                "--json",
                "--bytes",
                "--output",
                "PATH,TYPE,FSTYPE,SIZE,SERIAL,RM,RO,TRAN",
            ]
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise RecoveryError("Block-device inventory is unreadable") from error
        devices = payload.get("blockdevices") if isinstance(payload, dict) else None
        if not isinstance(devices, list):
            raise RecoveryError("Block-device inventory is missing")
        candidates: list[DiskIdentity] = []
        for disk in devices:
            if not isinstance(disk, dict) or disk.get("type") != "disk":
                continue
            serial = str(disk.get("serial") or "").strip()
            try:
                size_bytes = int(disk.get("size") or 0)
            except (TypeError, ValueError):
                continue
            if (
                serial != self.policy.machine_serial
                or size_bytes != self.policy.machine_size_bytes
                or self._bool(disk.get("rm"))
                or self._bool(disk.get("ro"))
            ):
                continue
            for child in disk.get("children") or []:
                if (
                    isinstance(child, dict)
                    and child.get("type") == "part"
                    and str(child.get("fstype") or "").lower() == "ext4"
                    and isinstance(child.get("path"), str)
                ):
                    candidates.append(
                        DiskIdentity(
                            path=str(disk.get("path") or ""),
                            partition=str(child["path"]),
                            serial=serial,
                            size_bytes=size_bytes,
                            transport=str(disk.get("tran") or "unknown"),
                        )
                    )
        return candidates

    def _mount(self, disk: DiskIdentity, target: Path, *, read_only: bool) -> None:
        target.mkdir(parents=True, exist_ok=True)
        options = "ro,noload" if read_only else "rw"
        self._command(["mount", "-t", "ext4", "-o", options, disk.partition, str(target)])

    def _unmount(self, target: Path) -> None:
        self._command(["umount", str(target)], check=False)

    def find_hopper_root(self) -> DiskIdentity:
        self.mount_base.mkdir(parents=True, exist_ok=True)
        matches: list[DiskIdentity] = []
        for index, disk in enumerate(self._disk_candidates()):
            probe = self.mount_base / f"probe-{index}"
            mounted = False
            try:
                self._mount(disk, probe, read_only=True)
                mounted = True
                self.inspect_mounted_root(probe, disk, require_dirty=True)
                matches.append(disk)
            except RecoveryError:
                pass
            finally:
                if mounted:
                    self._unmount(probe)
                try:
                    probe.rmdir()
                except OSError:
                    pass
        if len(matches) != 1:
            raise RecoveryError(f"Expected one exact Hopper root; found {len(matches)}")
        return matches[0]

    def execute(self) -> dict[str, Any]:
        if os.geteuid() != 0:
            raise RecoveryError("One-shot seed recovery requires root")
        if BOOT_TOKEN not in Path("/proc/cmdline").read_text(encoding="utf-8", errors="replace").split():
            raise RecoveryError("One-shot seed recovery boot token is absent")
        self.reporter.write(
            "AURUM HOPPER ONE-SHOT RECOVERY\n\n"
            "Identifying the installed seed without writing...",
            clear=True,
        )
        disk = self.find_hopper_root()
        target = self.mount_base / "target"
        mounted = False
        try:
            self.reporter.write("Hopper identity proven. Preserving the temporary UI patch...")
            self._mount(disk, target, read_only=False)
            mounted = True
            result = self.repair_mounted_root(target, disk)
            self._command(["sync"], check=False)
        finally:
            if mounted:
                self._unmount(target)
        self.reporter.write(
            "\nAURUM RECOVERY COMPLETE\n\n"
            "The two temporary UI edits were preserved as a patch and restored\n"
            "to Hopper's current clean seed. No installer ran and no other source\n"
            "was changed. Hopper will power off; the next start returns to the\n"
            "normal running-seed lifecycle."
        )
        return result


def _poweroff(reporter: Reporter) -> None:
    reporter.write("\nPowering off safely in 12 seconds...")
    time.sleep(12)
    systemctl = shutil.which("systemctl")
    if systemctl:
        subprocess.run([systemctl, "poweroff", "--no-block"], check=False, timeout=15)
        return
    subprocess.run(["/sbin/poweroff", "-f"], check=False, timeout=15)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Machine-bound Hopper seed recovery")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--poweroff", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    reporter = Reporter()
    exit_code = 1
    try:
        policy = RecoveryPolicy.load(args.policy)
        if not args.execute:
            print(json.dumps({"status": "ready", "policy": policy.public_dict()}, sort_keys=True))
            return 0
        result = HopperSeedRecovery(policy, reporter=reporter).execute()
        print(json.dumps(result, sort_keys=True))
        exit_code = 0
    except Exception as error:
        reporter.write(
            "\nAURUM RECOVERY STOPPED\n\n"
            f"{type(error).__name__}: {error}\n\n"
            "A Hopper identity or exact-change proof did not pass. The recovery\n"
            "did not proceed beyond its bounded evidence/rollback rules."
        )
    finally:
        if args.execute and args.poweroff:
            _poweroff(reporter)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
