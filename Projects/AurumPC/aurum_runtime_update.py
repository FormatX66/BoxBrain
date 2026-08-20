#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import py_compile
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

SCHEMA = "aurum-pc-runtime-update-v1"
DEFAULT_WORKSPACE = Path(os.environ.get("AURUM_GIT_WORKSPACE", "/var/lib/aurum/workspace/BoxBrain"))
DEFAULT_TARGET = Path(os.environ.get("AURUM_RUNTIME_ROOT", "/opt/aurum"))
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
DEFAULT_MARKER = Path("/etc/aurum-installed.json")
ALLOWLIST = (
    "aurum_autonomy.py",
    "aurum_bootstrap.py",
    "aurum_console.py",
    "aurum_driver_synthesis.py",
    "aurum_gui_runtime.py",
    "aurum_hardware.py",
    "aurum_installer.py",
    "aurum_network.py",
    "aurum_runtime_update.py",
    "aurum_time.py",
    "aurum_wifi_diag.py",
    "aurum_wifi_recovery.py",
    "aurum_workspace.py",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


class RuntimeUpdateError(RuntimeError):
    pass


class RuntimeUpdater:
    def __init__(
        self,
        *,
        workspace: Path = DEFAULT_WORKSPACE,
        target: Path = DEFAULT_TARGET,
        state_dir: Path = DEFAULT_STATE,
        installed_marker: Path = DEFAULT_MARKER,
    ) -> None:
        self.workspace = workspace
        self.source = workspace / "Projects" / "AurumPC"
        self.target = target
        self.state_dir = state_dir
        self.installed_marker = installed_marker

    def plan(self) -> dict[str, Any]:
        if not self.installed_marker.is_file():
            return {"schema": SCHEMA, "available": False, "reason": "not-installed-runtime", "files": []}
        if not (self.workspace / ".git").is_dir() or not self.source.is_dir():
            return {"schema": SCHEMA, "available": False, "reason": "git-workspace-unavailable", "files": []}
        files: list[dict[str, Any]] = []
        for name in ALLOWLIST:
            source = self.source / name
            target = self.target / name
            if not source.is_file():
                raise RuntimeUpdateError(f"allowlisted runtime source is missing: {name}")
            source_sha = _sha256(source)
            target_sha = _sha256(target) if target.is_file() else None
            files.append(
                {
                    "name": name,
                    "source_sha256": source_sha,
                    "target_sha256": target_sha,
                    "changed": source_sha != target_sha,
                }
            )
        return {
            "schema": SCHEMA,
            "available": True,
            "reason": "ready",
            "workspace": str(self.workspace),
            "target": str(self.target),
            "files": files,
            "changed": [item["name"] for item in files if item["changed"]],
        }

    def _validate_sources(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aurum-runtime-compile-") as temporary:
            output = Path(temporary)
            for name in ALLOWLIST:
                py_compile.compile(
                    str(self.source / name),
                    cfile=str(output / f"{name}.pyc"),
                    doraise=True,
                )

    def apply(self) -> dict[str, Any]:
        plan = self.plan()
        if not plan.get("available"):
            return plan
        changed = list(plan.get("changed") or [])
        if not changed:
            return {**plan, "status": "current", "reboot_required": False}
        if os.geteuid() != 0:
            raise RuntimeUpdateError("installed runtime update requires the root-owned Aurum console")
        self._validate_sources()
        self.target.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        backup = self.state_dir / "runtime-backup" / f"{stamp}-{os.getpid()}"
        backup.mkdir(parents=True, mode=0o700, exist_ok=False)
        applied: list[str] = []
        try:
            for name in changed:
                source = self.source / name
                target = self.target / name
                if target.is_file():
                    shutil.copy2(target, backup / name)
                temporary = target.with_name(f".{name}.{os.getpid()}.next")
                shutil.copy2(source, temporary)
                os.chmod(temporary, 0o755)
                os.replace(temporary, target)
                if _sha256(target) != _sha256(source):
                    raise RuntimeUpdateError(f"runtime hash verification failed after replacing {name}")
                applied.append(name)
        except Exception:
            for name in reversed(applied):
                saved = backup / name
                target = self.target / name
                if saved.is_file():
                    shutil.copy2(saved, target)
                else:
                    target.unlink(missing_ok=True)
            raise
        receipt = {
            "schema": SCHEMA,
            "status": "updated",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "workspace": str(self.workspace),
            "target": str(self.target),
            "changed": applied,
            "backup": str(backup),
            "reboot_required": True,
        }
        _atomic_json(self.state_dir / "runtime-update.json", receipt)
        return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Guarded Aurum installed-runtime updater")
    parser.add_argument("command", choices=("plan", "apply"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    updater = RuntimeUpdater()
    try:
        result = updater.plan() if args.command == "plan" else updater.apply()
    except (RuntimeUpdateError, py_compile.PyCompileError, OSError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "failed", "detail": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
