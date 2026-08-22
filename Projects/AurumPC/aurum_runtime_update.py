#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

SCHEMA = "aurum-pc-runtime-update-v4"
DEFAULT_WORKSPACE = Path(os.environ.get("AURUM_GIT_WORKSPACE", "/var/lib/aurum/workspace/BoxBrain"))
DEFAULT_TARGET = Path(os.environ.get("AURUM_RUNTIME_ROOT", "/opt/aurum"))
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
DEFAULT_MARKER = Path("/etc/aurum-installed.json")
DEFAULT_SYSTEM_ROOT = Path(os.environ.get("AURUM_SYSTEM_ROOT", "/"))
ALLOWLIST = (
    "aurum_arcade.py",
    "aurum_autonomy.py",
    "aurum_boot_screen.py",
    "aurum_bootstrap.py",
    "aurum_console.py",
    "aurum_control_plane.py",
    "aurum_desktop.py",
    "aurum_desktop_runtime.py",
    "aurum_display_runtime.py",
    "aurum_driver_synthesis.py",
    "aurum_echo_native.py",
    "aurum_gpt_trait.py",
    "aurum_gpt_executor.py",
    "aurum_gui_runtime.py",
    "aurum_hardware.py",
    "aurum_hopper_gui.py",
    "aurum_projection_runtime.py",
    "aurum_web_surface.py",
    "aurum_input.py",
    "aurum_installer.py",
    "aurum_network.py",
    "aurum_runtime_update.py",
    "aurum_time.py",
    "aurum_traits.py",
    "aurum_wifi_diag.py",
    "aurum_wifi_recovery.py",
    "aurum_workspace.py",
)
SYSTEM_ASSETS = (
    ("etc/X11/xorg.conf.d/40-aurum-libinput.conf", 0o644),
    ("etc/systemd/system/aurum-input-bootstrap.service", 0o644),
    ("etc/systemd/system/aurum-pc-console.service", 0o644),
    ("usr/lib/systemd/system-sleep/aurum-input-wake", 0o755),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _atomic_text(path: Path, text: str, mode: int = 0o644) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.chmod(temporary, mode)
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
        system_root: Path = DEFAULT_SYSTEM_ROOT,
    ) -> None:
        self.workspace = workspace
        self.source = workspace / "Projects" / "AurumPC"
        self.target = target
        self.state_dir = state_dir
        self.installed_marker = installed_marker
        self.system_root = system_root
        self.asset_source = self.source / "runtime-assets"

    def _identity_plan(self) -> dict[str, Any]:
        policy = _json_file(self.source / "pc01_autonomy_policy.json")
        receipt = _json_file(self.installed_marker)
        match = policy.get("machine_match") if isinstance(policy.get("machine_match"), dict) else {}
        target = receipt.get("target") if isinstance(receipt.get("target"), dict) else {}
        expected_serial = str(match.get("installed_target_serial") or "")
        expected_size = int(match.get("installed_target_size_bytes") or 0)
        authorized = bool(
            expected_serial
            and expected_size > 0
            and str(target.get("serial") or "") == expected_serial
            and int(target.get("size_bytes") or 0) == expected_size
        )
        hostname = str(policy.get("hostname") or "").strip().lower()
        display = str(policy.get("machine_display_name") or "").strip()
        if hostname and re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", hostname) is None:
            raise RuntimeUpdateError("configured Aurum hostname is invalid")
        if len(display) > 64:
            raise RuntimeUpdateError("configured Aurum display name is too long")
        current_hostname = ""
        try:
            current_hostname = Path("/etc/hostname").read_text(encoding="utf-8").strip()
        except OSError:
            pass
        return {
            "authorized": authorized,
            "hostname": hostname,
            "display_name": display,
            "current_hostname": current_hostname,
            "change_needed": bool(authorized and hostname and current_hostname != hostname),
            "machine_match": {"serial": expected_serial, "size_bytes": expected_size},
        }

    def _apply_identity(self) -> dict[str, Any]:
        plan = self._identity_plan()
        if not plan["authorized"] or not plan["hostname"]:
            return {**plan, "status": "skipped"}
        if os.geteuid() != 0:
            raise RuntimeUpdateError("machine identity update requires root")
        old = plan["current_hostname"]
        identity_dir = self.state_dir / "identity"
        identity_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        backup = identity_dir / "previous-hostname.txt"
        if old and not backup.exists():
            _atomic_text(backup, old + "\n", 0o600)
        if plan["change_needed"]:
            _atomic_text(Path("/etc/hostname"), str(plan["hostname"]) + "\n", 0o644)
            hostnamectl = shutil.which("hostnamectl")
            runtime_command: dict[str, Any] = {"attempted": False}
            if hostnamectl:
                result = subprocess.run(
                    [hostnamectl, "set-hostname", str(plan["hostname"])],
                    check=False,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=20,
                )
                runtime_command = {
                    "attempted": True,
                    "tool": "hostnamectl",
                    "returncode": result.returncode,
                    "detail": result.stdout.strip()[-500:],
                }
        else:
            runtime_command = {"attempted": False, "reason": "already-named"}
        receipt = {
            "schema": "aurum-machine-identity-v1",
            "status": "named",
            "display_name": plan["display_name"],
            "hostname": plan["hostname"],
            "previous_hostname": old,
            "runtime_command": runtime_command,
            "machine_match": plan["machine_match"],
            "updated_at": time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime()),
        }
        _atomic_json(self.state_dir / "machine-identity.json", receipt)
        return receipt

    def _launch_physical_echo(self) -> dict[str, Any]:
        policy_path = self.source / "pc01_autonomy_policy.json"
        policy = _json_file(policy_path)
        identity = self._identity_plan()
        if not identity.get("authorized"):
            return {"status": "skipped", "reason": "machine-not-authorized"}
        if not bool(policy.get("auto_local_echo_display")):
            return {"status": "skipped", "reason": "physical-echo-disabled"}
        display = self.target / "aurum_display_runtime.py"
        game = self.target / "aurum_echo_native.py"
        if not display.is_file() or not game.is_file():
            return {"status": "skipped", "reason": "display-runtime-not-installed"}
        self.state_dir.mkdir(parents=True, exist_ok=True)
        log = (self.state_dir / "hopper-display-bootstrap.log").open("ab", buffering=0)
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(display),
                    "start",
                    "--policy",
                    str(policy_path),
                    "--receipt",
                    str(self.installed_marker),
                    "--state-dir",
                    str(self.state_dir),
                    "--game",
                    str(game),
                ],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                close_fds=True,
                start_new_session=True,
            )
        finally:
            log.close()
        return {
            "status": "launched",
            "pid": process.pid,
            "machine": "Hopper",
            "game": "Echo Rally",
            "physical_display": True,
        }

    def _refresh_input(self) -> dict[str, Any]:
        helper = self.target / "aurum_input.py"
        if not helper.is_file():
            return {"status": "skipped", "reason": "input-helper-not-installed"}
        result = subprocess.run(
            [
                sys.executable,
                str(helper),
                "--apply-wake-policy",
                "--write-state",
                "/run/aurum-input-status.json",
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=15,
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload = {"status": "failed", "detail": result.stdout[-1200:]}
        if not isinstance(payload, dict):
            payload = {"status": "failed", "detail": "input helper returned non-object"}
        payload["returncode"] = result.returncode
        return payload

    def _activate_system_integration(
        self, changed: list[str], system_changed: list[str]
    ) -> dict[str, Any]:
        if self.system_root.resolve() != Path("/"):
            return {"status": "skipped", "reason": "simulated-system-root"}
        systemctl = shutil.which("systemctl")
        if not systemctl:
            return {"status": "skipped", "reason": "systemctl-unavailable"}
        commands: list[dict[str, Any]] = []

        def run(*arguments: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
            result = subprocess.run(
                [systemctl, *arguments],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
            commands.append(
                {
                    "arguments": list(arguments),
                    "returncode": result.returncode,
                    "detail": result.stdout.strip()[-800:],
                }
            )
            return result

        if system_changed:
            run("daemon-reload")
        enable = run("enable", "aurum-input-bootstrap.service", "aurum-pc-console.service")
        active = run("is-active", "--quiet", "aurum-input-bootstrap.service")
        input_changed = "aurum_input.py" in changed or any(
            name.endswith("aurum-input-bootstrap.service") or name.endswith("aurum-input-wake")
            for name in system_changed
        )
        restart = run("restart", "aurum-input-bootstrap.service") if input_changed or active.returncode != 0 else None
        failed = enable.returncode != 0 or any(
            item["returncode"] != 0 and item["arguments"] == ["daemon-reload"] for item in commands
        )
        if restart is not None and restart.returncode != 0:
            failed = True
        return {
            "status": "failed" if failed else "ready",
            "commands": commands,
            "console_restart_deferred": True,
            "boot_screen_visible_on_next_boot": True,
        }

    def _restart_gui(self, changed: list[str], system_changed: list[str]) -> dict[str, Any]:
        policy = _json_file(self.source / "pc01_autonomy_policy.json")
        if policy.get("auto_gui_start") is not True:
            return {"status": "skipped", "reason": "automatic-gui-disabled"}
        gui_files = {
            "aurum_desktop.py",
            "aurum_desktop_runtime.py",
            "aurum_gui_runtime.py",
            "aurum_hopper_gui.py",
            "aurum_input.py",
        }
        libinput_changed = "etc/X11/xorg.conf.d/40-aurum-libinput.conf" in system_changed
        if not gui_files.intersection(changed) and not libinput_changed:
            return {"status": "skipped", "reason": "gui-runtime-unchanged"}
        runtime = self.target / "aurum_gui_runtime.py"
        if not runtime.is_file():
            return {"status": "skipped", "reason": "gui-runtime-not-installed"}
        stop = subprocess.run(
            [sys.executable, str(runtime), "stop"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=15,
        )
        start = subprocess.run(
            [sys.executable, str(runtime), "start"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=70,
        )
        try:
            payload = json.loads(start.stdout.strip().splitlines()[-1]) if start.stdout.strip() else {}
        except json.JSONDecodeError:
            payload = {"status": "failed", "detail": start.stdout[-1600:]}
        if not isinstance(payload, dict):
            payload = {"status": "failed", "detail": "GUI runtime returned non-object"}
        payload["stop_returncode"] = stop.returncode
        payload["start_returncode"] = start.returncode
        return payload

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
        system_files: list[dict[str, Any]] = []
        for relative, mode in SYSTEM_ASSETS:
            source = self.asset_source / relative
            target = self.system_root / relative
            if not source.is_file():
                raise RuntimeUpdateError(f"allowlisted system asset is missing: {relative}")
            source_sha = _sha256(source)
            target_sha = _sha256(target) if target.is_file() else None
            target_mode = (target.stat().st_mode & 0o777) if target.is_file() else None
            system_files.append(
                {
                    "name": relative,
                    "source_sha256": source_sha,
                    "target_sha256": target_sha,
                    "mode": mode,
                    "target_mode": target_mode,
                    "changed": source_sha != target_sha or target_mode != mode,
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
            "system_files": system_files,
            "system_changed": [item["name"] for item in system_files if item["changed"]],
            "identity": self._identity_plan(),
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
        for relative, _mode in SYSTEM_ASSETS:
            source = self.asset_source / relative
            if not source.is_file() or source.stat().st_size == 0:
                raise RuntimeUpdateError(f"allowlisted system asset is empty or missing: {relative}")

    def apply(self) -> dict[str, Any]:
        plan = self.plan()
        if not plan.get("available"):
            return plan
        if os.geteuid() != 0:
            raise RuntimeUpdateError("installed runtime update requires the root-owned Aurum console")
        self._validate_sources()
        identity = self._apply_identity()
        changed = list(plan.get("changed") or [])
        system_changed = list(plan.get("system_changed") or [])
        if not changed and not system_changed:
            activation = self._launch_physical_echo()
            input_activation = self._refresh_input()
            system_activation = self._activate_system_integration([], [])
            result = {
                **plan,
                "status": "current",
                "reboot_required": False,
                "identity": identity,
                "physical_echo_activation": activation,
                "input_activation": input_activation,
                "system_activation": system_activation,
            }
            _atomic_json(self.state_dir / "runtime-update.json", result)
            return result
        self.target.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        backup = self.state_dir / "runtime-backup" / f"{stamp}-{os.getpid()}"
        backup.mkdir(parents=True, mode=0o700, exist_ok=False)
        applied: list[str] = []
        applied_system: list[str] = []
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
            for relative, mode in SYSTEM_ASSETS:
                if relative not in system_changed:
                    continue
                source = self.asset_source / relative
                target = self.system_root / relative
                saved = backup / "system" / relative
                if target.is_file():
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, saved)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(f".{target.name}.{os.getpid()}.next")
                shutil.copy2(source, temporary)
                os.chmod(temporary, mode)
                os.replace(temporary, target)
                if _sha256(target) != _sha256(source) or (target.stat().st_mode & 0o777) != mode:
                    raise RuntimeUpdateError(f"system asset verification failed after replacing {relative}")
                applied_system.append(relative)
        except Exception:
            for relative in reversed(applied_system):
                saved = backup / "system" / relative
                target = self.system_root / relative
                if saved.is_file():
                    shutil.copy2(saved, target)
                else:
                    target.unlink(missing_ok=True)
            for name in reversed(applied):
                saved = backup / name
                target = self.target / name
                if saved.is_file():
                    shutil.copy2(saved, target)
                else:
                    target.unlink(missing_ok=True)
            raise
        system_activation = self._activate_system_integration(applied, applied_system)
        activation = self._launch_physical_echo()
        input_activation = self._refresh_input()
        gui_activation = self._restart_gui(applied, applied_system)
        receipt = {
            "schema": SCHEMA,
            "status": "updated",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "workspace": str(self.workspace),
            "target": str(self.target),
            "changed": applied,
            "system_changed": applied_system,
            "backup": str(backup),
            "reboot_required": False,
            "identity": identity,
            "physical_echo_activation": activation,
            "input_activation": input_activation,
            "system_activation": system_activation,
            "gui_activation": gui_activation,
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
    except (RuntimeUpdateError, py_compile.PyCompileError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "failed", "detail": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
