#!/usr/bin/env python3
"""Physical local-display launcher for Hopper's first Aurum application.

The launcher is machine-bound to the installed Hopper receipt. It first tries
SDL's direct KMS/DRM path on VT2. If that is unavailable, it installs a minimal
Xorg fallback and starts the same native Echo Rally client there. It exposes no
network listener and grants no shell or host-control API.
"""
from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "aurum-hopper-display-v1"
DEFAULT_POLICY = Path(__file__).with_name("pc01_autonomy_policy.json")
DEFAULT_RECEIPT = Path("/etc/aurum-installed.json")
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
DEFAULT_RUN = Path("/run/aurum")
DEFAULT_GAME = Path("/opt/aurum/aurum_echo_native.py")


class DisplayRuntimeError(RuntimeError):
    pass


def _json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _authorized(policy: Mapping[str, Any], receipt: Mapping[str, Any]) -> tuple[bool, str]:
    if policy.get("schema") != "aurum-pc-autonomy-policy-v1" or policy.get("enabled") is not True:
        return False, "policy-disabled-or-invalid"
    match = policy.get("machine_match") if isinstance(policy.get("machine_match"), dict) else {}
    target = receipt.get("target") if isinstance(receipt.get("target"), dict) else {}
    expected_serial = str(match.get("installed_target_serial") or "")
    expected_size = int(match.get("installed_target_size_bytes") or 0)
    if str(target.get("serial") or "") != expected_serial:
        return False, "installed-target-serial-mismatch"
    if int(target.get("size_bytes") or 0) != expected_size:
        return False, "installed-target-size-mismatch"
    if str(policy.get("machine_display_name") or "") != "Hopper":
        return False, "machine-name-not-hopper"
    return True, "authorized-hopper"


def _run(arguments: list[str], *, timeout: int, env: Mapping[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            arguments,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            env=dict(env) if env is not None else None,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise DisplayRuntimeError(f"display operation failed: {type(exc).__name__}:{exc}") from exc


class HopperDisplay:
    def __init__(
        self,
        *,
        policy_path: Path = DEFAULT_POLICY,
        receipt_path: Path = DEFAULT_RECEIPT,
        state_dir: Path = DEFAULT_STATE,
        run_dir: Path = DEFAULT_RUN,
        game: Path = DEFAULT_GAME,
    ) -> None:
        self.policy_path = policy_path
        self.receipt_path = receipt_path
        self.state_dir = state_dir
        self.run_dir = run_dir
        self.game = game
        self.state_path = state_dir / "hopper-display.json"
        self.game_receipt = state_dir / "echo-native.json"
        self.game_pid = run_dir / "echo-native.pid"
        self.lock_path = run_dir / "hopper-display.lock"
        self.log_path = state_dir / "hopper-display.log"

    def authorization(self) -> tuple[bool, str]:
        return _authorized(_json_file(self.policy_path), _json_file(self.receipt_path))

    def _pid(self) -> int | None:
        try:
            pid = int(self.game_pid.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None
        return pid if pid > 1 else None

    def _owned(self, pid: int) -> bool:
        try:
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            return False
        return "aurum_echo_native.py" in cmdline

    def status(self) -> dict[str, Any]:
        authorized, reason = self.authorization()
        pid = self._pid()
        owned = bool(pid and self._owned(pid))
        game = _json_file(self.game_receipt)
        return {
            "schema": SCHEMA,
            "status": "running" if owned and game.get("status") == "running" else "stopped",
            "authorized": authorized,
            "authorization_reason": reason,
            "machine": "Hopper",
            "pid": pid if owned else None,
            "game": game,
            "physical_display": bool(owned and game.get("status") == "running"),
            "network_listener": False,
            "host_actuation_api": False,
        }

    def _ensure_pygame(self, policy: Mapping[str, Any]) -> dict[str, Any]:
        if importlib.util.find_spec("pygame") is not None:
            return {"status": "ready", "package": "python3-pygame", "installed": False}
        if not bool(policy.get("install_local_display_dependencies")):
            return {"status": "missing", "reason": "dependency-install-disabled"}
        apt = shutil.which("apt-get")
        if not apt or os.geteuid() != 0:
            return {"status": "missing", "reason": "apt-or-root-unavailable"}
        env = dict(os.environ)
        env["DEBIAN_FRONTEND"] = "noninteractive"
        update = _run([apt, "update"], timeout=300, env=env)
        if update.returncode != 0:
            return {"status": "failed", "phase": "apt-update", "detail": update.stdout[-1200:]}
        install = _run([apt, "install", "-y", "--no-install-recommends", "python3-pygame"], timeout=600, env=env)
        if install.returncode != 0:
            return {"status": "failed", "phase": "apt-install-pygame", "detail": install.stdout[-1600:]}
        return {"status": "ready" if importlib.util.find_spec("pygame") is not None else "missing-after-install", "package": "python3-pygame", "installed": True}

    def _ensure_x_fallback(self, policy: Mapping[str, Any]) -> dict[str, Any]:
        if shutil.which("xinit") and (shutil.which("Xorg") or shutil.which("X")):
            return {"status": "ready", "installed": False}
        if not bool(policy.get("install_local_display_dependencies")):
            return {"status": "missing", "reason": "dependency-install-disabled"}
        apt = shutil.which("apt-get")
        if not apt or os.geteuid() != 0:
            return {"status": "missing", "reason": "apt-or-root-unavailable"}
        env = dict(os.environ)
        env["DEBIAN_FRONTEND"] = "noninteractive"
        install = _run(
            [apt, "install", "-y", "--no-install-recommends", "xserver-xorg", "xinit", "x11-xserver-utils"],
            timeout=600,
            env=env,
        )
        ready = bool(shutil.which("xinit") and (shutil.which("Xorg") or shutil.which("X")))
        return {
            "status": "ready" if install.returncode == 0 and ready else "failed",
            "installed": True,
            "detail": "" if install.returncode == 0 else install.stdout[-1600:],
        }

    def _launch(self, command: list[str], mode: str) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        log = self.log_path.open("ab", buffering=0)
        try:
            subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                close_fds=True,
                start_new_session=True,
            )
        finally:
            log.close()
        _atomic_json(
            self.state_path,
            {
                "schema": SCHEMA,
                "status": "launching",
                "machine": "Hopper",
                "mode": mode,
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )

    def _wait_running(self, mode: str, seconds: float = 18.0) -> dict[str, Any] | None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            current = self.status()
            if current["status"] == "running":
                result = {
                    **current,
                    "mode": mode,
                    "status": "running",
                    "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                _atomic_json(self.state_path, result)
                return result
            game = _json_file(self.game_receipt)
            if game.get("status") == "failed":
                return None
            time.sleep(0.3)
        return None

    def _clear_failed_game(self) -> None:
        pid = self._pid()
        if pid and self._owned(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            time.sleep(0.5)
        self.game_pid.unlink(missing_ok=True)
        self.game_receipt.unlink(missing_ok=True)

    def start(self) -> dict[str, Any]:
        authorized, reason = self.authorization()
        if not authorized:
            result = {"schema": SCHEMA, "status": "refused", "authorized": False, "reason": reason}
            _atomic_json(self.state_path, result)
            return result
        if self.status()["status"] == "running":
            return self.status()
        if os.geteuid() != 0:
            raise DisplayRuntimeError("Hopper physical display startup requires root-owned Aurum runtime")
        if not self.game.is_file():
            raise DisplayRuntimeError(f"installed Echo client missing: {self.game}")
        policy = _json_file(self.policy_path)
        dependency = self._ensure_pygame(policy)
        if dependency.get("status") != "ready":
            result = {"schema": SCHEMA, "status": "failed", "phase": "pygame", "dependency": dependency}
            _atomic_json(self.state_path, result)
            return result
        openvt = shutil.which("openvt")
        env_tool = shutil.which("env") or "/usr/bin/env"
        python = shutil.which("python3") or sys.executable
        if not openvt:
            raise DisplayRuntimeError("openvt is required for the physical display lane")

        self._clear_failed_game()
        kms_command = [
            openvt,
            "-c",
            "2",
            "-s",
            "-f",
            "--",
            env_tool,
            "SDL_VIDEODRIVER=kmsdrm",
            f"AURUM_STATE_DIR={self.state_dir}",
            python,
            str(self.game),
            "--state-dir",
            str(self.state_dir),
            "--run-dir",
            str(self.run_dir),
        ]
        self._launch(kms_command, "kmsdrm-vt2")
        ready = self._wait_running("kmsdrm-vt2")
        if ready is not None:
            ready["dependency"] = dependency
            _atomic_json(self.state_path, ready)
            return ready

        self._clear_failed_game()
        xdeps = self._ensure_x_fallback(policy)
        if xdeps.get("status") != "ready":
            result = {
                "schema": SCHEMA,
                "status": "failed",
                "phase": "x-fallback-dependencies",
                "kms_failure": _json_file(self.game_receipt),
                "dependency": dependency,
                "x_dependencies": xdeps,
            }
            _atomic_json(self.state_path, result)
            return result
        xinit = shutil.which("xinit")
        if not xinit:
            raise DisplayRuntimeError("xinit disappeared after dependency setup")
        x_command = [
            openvt,
            "-c",
            "2",
            "-s",
            "-f",
            "--",
            xinit,
            env_tool,
            "SDL_VIDEODRIVER=x11",
            f"AURUM_STATE_DIR={self.state_dir}",
            python,
            str(self.game),
            "--state-dir",
            str(self.state_dir),
            "--run-dir",
            str(self.run_dir),
            "--",
            ":0",
            "vt2",
            "-nolisten",
            "tcp",
        ]
        self._launch(x_command, "x11-vt2")
        ready = self._wait_running("x11-vt2", seconds=25.0)
        if ready is not None:
            ready["dependency"] = dependency
            ready["x_dependencies"] = xdeps
            _atomic_json(self.state_path, ready)
            return ready
        result = {
            "schema": SCHEMA,
            "status": "failed",
            "phase": "physical-display",
            "dependency": dependency,
            "x_dependencies": xdeps,
            "game": _json_file(self.game_receipt),
            "detail": self.log_path.read_text(encoding="utf-8", errors="replace")[-2500:] if self.log_path.is_file() else "",
        }
        _atomic_json(self.state_path, result)
        return result

    def stop(self) -> dict[str, Any]:
        pid = self._pid()
        if pid and self._owned(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and pid and self._owned(pid):
            time.sleep(0.1)
        self.game_pid.unlink(missing_ok=True)
        result = self.status()
        _atomic_json(self.state_path, result)
        return result

    def locked_start(self) -> dict[str, Any]:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"schema": SCHEMA, "status": "busy", "machine": "Hopper"}
            return self.start()


def main() -> int:
    parser = argparse.ArgumentParser(description="Hopper physical Echo display manager")
    parser.add_argument("command", choices=("status", "start", "stop"))
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--game", type=Path, default=DEFAULT_GAME)
    args = parser.parse_args()
    runtime = HopperDisplay(
        policy_path=args.policy,
        receipt_path=args.receipt,
        state_dir=args.state_dir,
        run_dir=args.run_dir,
        game=args.game,
    )
    try:
        if args.command == "start":
            result = runtime.locked_start()
        elif args.command == "stop":
            result = runtime.stop()
        else:
            result = runtime.status()
    except (DisplayRuntimeError, OSError, ValueError) as exc:
        result = {"schema": SCHEMA, "status": "failed", "detail": f"{type(exc).__name__}:{exc}"}
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("status") in {"running", "stopped", "busy"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
