#!/usr/bin/env python3
"""Machine-bound launcher for Aurum's native Hopper desktop on VT2."""
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

SCHEMA = "aurum-hopper-desktop-runtime-v1"
DEFAULT_POLICY = Path(__file__).with_name("pc01_autonomy_policy.json")
DEFAULT_RECEIPT = Path("/etc/aurum-installed.json")
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
DEFAULT_RUN = Path(os.environ.get("AURUM_RUN_DIR", "/run/aurum"))
DEFAULT_DESKTOP = Path("/opt/aurum/aurum_desktop.py")
DEFAULT_INPUT_DEVICES = Path("/proc/bus/input/devices")
TOUCHPAD_MARKERS = ("touchpad", "clickpad", "glidepoint", "trackpad")
XORG_LIBINPUT_DRIVERS = (
    Path("/usr/lib/xorg/modules/input/libinput_drv.so"),
    Path("/usr/lib/x86_64-linux-gnu/xorg/modules/input/libinput_drv.so"),
)


class DesktopRuntimeError(RuntimeError):
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
    if str(policy.get("machine_display_name") or "") != "Hopper":
        return False, "machine-name-not-hopper"
    match = policy.get("machine_match") if isinstance(policy.get("machine_match"), dict) else {}
    target = receipt.get("target") if isinstance(receipt.get("target"), dict) else {}
    expected_serial = str(match.get("installed_target_serial") or "")
    expected_size = int(match.get("installed_target_size_bytes") or 0)
    if not expected_serial or str(target.get("serial") or "") != expected_serial:
        return False, "installed-target-serial-mismatch"
    if expected_size <= 0 or int(target.get("size_bytes") or 0) != expected_size:
        return False, "installed-target-size-mismatch"
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
        raise DesktopRuntimeError(f"desktop operation failed: {type(exc).__name__}:{exc}") from exc


def _touchpad_present(path: Path = DEFAULT_INPUT_DEVICES) -> bool:
    """Detect a laptop-style pointer that benefits from libinput translation."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return False
    for block in text.split("\n\n"):
        if not any(marker in block for marker in TOUCHPAD_MARKERS):
            continue
        if "handlers=" in block and "event" in block:
            return True
    return False


def _xorg_libinput_ready() -> bool:
    return any(path.is_file() for path in XORG_LIBINPUT_DRIVERS)


class HopperDesktopRuntime:
    def __init__(
        self,
        *,
        policy_path: Path = DEFAULT_POLICY,
        receipt_path: Path = DEFAULT_RECEIPT,
        state_dir: Path = DEFAULT_STATE,
        run_dir: Path = DEFAULT_RUN,
        desktop: Path = DEFAULT_DESKTOP,
    ) -> None:
        self.policy_path = policy_path
        self.receipt_path = receipt_path
        self.state_dir = state_dir
        self.run_dir = run_dir
        self.desktop = desktop
        self.state_path = state_dir / "hopper-desktop.json"
        self.desktop_receipt = state_dir / "desktop-ui.json"
        self.desktop_pid = run_dir / "aurum-desktop.pid"
        self.lock_path = run_dir / "hopper-desktop.lock"
        self.log_path = state_dir / "hopper-desktop.log"

    def authorization(self) -> tuple[bool, str]:
        return _authorized(_json_file(self.policy_path), _json_file(self.receipt_path))

    def _pid(self) -> int | None:
        try:
            pid = int(self.desktop_pid.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None
        return pid if pid > 1 else None

    def _owned(self, pid: int) -> bool:
        try:
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            return False
        return "aurum_desktop.py" in cmdline

    def _echo_owns_vt2(self) -> bool:
        try:
            pid = int((self.run_dir / "echo-native.pid").read_text(encoding="utf-8").strip())
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except (OSError, ValueError):
            return False
        return "aurum_echo_native.py" in cmdline

    def status(self) -> dict[str, Any]:
        authorized, reason = self.authorization()
        pid = self._pid()
        owned = bool(pid and self._owned(pid))
        receipt = _json_file(self.desktop_receipt)
        running = bool(owned and receipt.get("status") == "running" and receipt.get("schema") == "aurum.desktop.v1")
        state = _json_file(self.state_path)
        return {
            "schema": SCHEMA,
            "status": "running" if running else "stopped",
            "authorized": authorized,
            "authorization_reason": reason,
            "machine": "Hopper",
            "pid": pid if owned else None,
            "surface": "physical",
            "vt": 2,
            "mode": state.get("mode"),
            "desktop": receipt,
            "host_actuation_api": False,
            "recovery_console": "tty1",
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
        install = _run([apt, "install", "-y", "--no-install-recommends", "python3-pygame"], timeout=600, env=env)
        return {
            "status": "ready" if install.returncode == 0 and importlib.util.find_spec("pygame") is not None else "failed",
            "package": "python3-pygame",
            "installed": True,
            "detail": "" if install.returncode == 0 else install.stdout[-1600:],
        }

    def _ensure_openvt(self, policy: Mapping[str, Any]) -> dict[str, Any]:
        openvt = shutil.which("openvt")
        if openvt:
            return {"status": "ready", "package": "kbd", "installed": False, "path": openvt}
        if not bool(policy.get("install_local_display_dependencies")):
            return {"status": "missing", "reason": "dependency-install-disabled", "package": "kbd"}
        apt = shutil.which("apt-get")
        if not apt or os.geteuid() != 0:
            return {"status": "missing", "reason": "apt-or-root-unavailable", "package": "kbd"}
        env = dict(os.environ)
        env["DEBIAN_FRONTEND"] = "noninteractive"
        install = _run([apt, "install", "-y", "--no-install-recommends", "kbd"], timeout=600, env=env)
        openvt = shutil.which("openvt")
        return {
            "status": "ready" if install.returncode == 0 and openvt else "failed",
            "package": "kbd",
            "installed": True,
            "path": openvt,
            "detail": "" if install.returncode == 0 else install.stdout[-1600:],
        }

    def _ensure_x_fallback(self, policy: Mapping[str, Any]) -> dict[str, Any]:
        x_ready = bool(shutil.which("xinit") and (shutil.which("Xorg") or shutil.which("X")))
        if x_ready and _xorg_libinput_ready():
            return {
                "status": "ready",
                "installed": False,
                "input_driver": "xserver-xorg-input-libinput",
            }
        if not bool(policy.get("install_local_display_dependencies")):
            return {
                "status": "missing",
                "reason": "dependency-install-disabled",
                "input_driver": "xserver-xorg-input-libinput",
            }
        apt = shutil.which("apt-get")
        if not apt or os.geteuid() != 0:
            return {
                "status": "missing",
                "reason": "apt-or-root-unavailable",
                "input_driver": "xserver-xorg-input-libinput",
            }
        env = dict(os.environ)
        env["DEBIAN_FRONTEND"] = "noninteractive"
        install = _run(
            [
                apt,
                "install",
                "-y",
                "--no-install-recommends",
                "xserver-xorg",
                "xinit",
                "x11-xserver-utils",
                "xserver-xorg-input-libinput",
            ],
            timeout=600,
            env=env,
        )
        ready = bool(
            shutil.which("xinit")
            and (shutil.which("Xorg") or shutil.which("X"))
            and _xorg_libinput_ready()
        )
        return {
            "status": "ready" if install.returncode == 0 and ready else "failed",
            "installed": True,
            "input_driver": "xserver-xorg-input-libinput",
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
        _atomic_json(self.state_path, {
            "schema": SCHEMA,
            "status": "launching",
            "authorized": True,
            "machine": "Hopper",
            "mode": mode,
            "vt": 2,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

    def _wait_running(self, mode: str, seconds: float = 18.0) -> dict[str, Any] | None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            current = self.status()
            if current["status"] == "running":
                result = {
                    **current,
                    "mode": mode,
                    "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                _atomic_json(self.state_path, result)
                return result
            receipt = _json_file(self.desktop_receipt)
            if receipt.get("status") == "failed":
                return None
            time.sleep(0.3)
        return None

    def _clear_desktop(self) -> None:
        pid = self._pid()
        if pid and self._owned(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and self._owned(pid):
                time.sleep(0.1)
            if self._owned(pid):
                raise DesktopRuntimeError("Aurum desktop did not stop after bounded SIGTERM window")
        self.desktop_pid.unlink(missing_ok=True)

    def _x_command(self, *, openvt: str, env_tool: str, python: str) -> list[str]:
        xinit = shutil.which("xinit")
        if not xinit:
            raise DesktopRuntimeError("xinit disappeared after dependency setup")
        return [
            openvt, "-c", "2", "-s", "-f", "--",
            xinit,
            env_tool,
            "SDL_VIDEODRIVER=x11",
            f"AURUM_STATE_DIR={self.state_dir}",
            f"AURUM_RUN_DIR={self.run_dir}",
            python, str(self.desktop), "run",
            "--state-dir", str(self.state_dir),
            "--run-dir", str(self.run_dir),
            "--", ":0", "vt2", "-nolisten", "tcp",
        ]

    def _try_x11(
        self,
        *,
        policy: Mapping[str, Any],
        openvt: str,
        env_tool: str,
        python: str,
        pygame_dep: Mapping[str, Any],
        console_dep: Mapping[str, Any],
        input_policy: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        xdeps = self._ensure_x_fallback(policy)
        if xdeps.get("status") != "ready":
            return None, xdeps
        self._clear_desktop()
        self._launch(self._x_command(openvt=openvt, env_tool=env_tool, python=python), "x11-vt2")
        ready = self._wait_running("x11-vt2", seconds=25.0)
        if ready is not None:
            ready["dependency"] = dict(pygame_dep)
            ready["console_dependency"] = dict(console_dep)
            ready["x_dependencies"] = xdeps
            ready["input_policy"] = input_policy
            _atomic_json(self.state_path, ready)
            return ready, xdeps
        return None, xdeps

    def start(self) -> dict[str, Any]:
        authorized, reason = self.authorization()
        if not authorized:
            result = {"schema": SCHEMA, "status": "refused", "authorized": False, "reason": reason}
            _atomic_json(self.state_path, result)
            return result
        current = self.status()
        touchpad = _touchpad_present()
        if current["status"] == "running":
            if not touchpad or current.get("mode") == "x11-vt2":
                return current
            # Pixels are healthy, but a laptop touchpad needs libinput translation.
            # Restart the presentation surface on X11 without touching tty1.
            self._clear_desktop()
        if self._echo_owns_vt2():
            return {"schema": SCHEMA, "status": "refused", "reason": "vt2-owned-by-echo", "machine": "Hopper"}
        if os.geteuid() != 0:
            raise DesktopRuntimeError("Hopper desktop startup requires root-owned Aurum runtime")
        if not self.desktop.is_file():
            raise DesktopRuntimeError(f"installed Aurum desktop missing: {self.desktop}")

        policy = _json_file(self.policy_path)
        pygame_dep = self._ensure_pygame(policy)
        if pygame_dep.get("status") != "ready":
            result = {"schema": SCHEMA, "status": "failed", "phase": "pygame", "dependency": pygame_dep}
            _atomic_json(self.state_path, result)
            return result
        console_dep = self._ensure_openvt(policy)
        if console_dep.get("status") != "ready":
            result = {"schema": SCHEMA, "status": "failed", "phase": "console-tools", "dependency": console_dep}
            _atomic_json(self.state_path, result)
            return result

        openvt = str(console_dep.get("path") or "")
        env_tool = shutil.which("env") or "/usr/bin/env"
        python = shutil.which("python3") or sys.executable
        self._clear_desktop()

        xdeps: dict[str, Any] = {}
        if touchpad:
            ready, xdeps = self._try_x11(
                policy=policy,
                openvt=openvt,
                env_tool=env_tool,
                python=python,
                pygame_dep=pygame_dep,
                console_dep=console_dep,
                input_policy="touchpad-libinput-x11",
            )
            if ready is not None:
                return ready
            self._clear_desktop()

        kms_command = [
            openvt, "-c", "2", "-s", "-f", "--",
            env_tool,
            "SDL_VIDEODRIVER=kmsdrm",
            f"AURUM_STATE_DIR={self.state_dir}",
            f"AURUM_RUN_DIR={self.run_dir}",
            python, str(self.desktop), "run",
            "--state-dir", str(self.state_dir),
            "--run-dir", str(self.run_dir),
        ]
        self._launch(kms_command, "kmsdrm-vt2")
        ready = self._wait_running("kmsdrm-vt2")
        if ready is not None:
            ready["dependency"] = pygame_dep
            ready["console_dependency"] = console_dep
            ready["input_policy"] = "direct-kms" if not touchpad else "touchpad-x11-unavailable-kms-fallback"
            if xdeps:
                ready["x_dependencies"] = xdeps
            _atomic_json(self.state_path, ready)
            return ready

        self._clear_desktop()
        ready, xdeps = self._try_x11(
            policy=policy,
            openvt=openvt,
            env_tool=env_tool,
            python=python,
            pygame_dep=pygame_dep,
            console_dep=console_dep,
            input_policy="x11-libinput-fallback",
        )
        if ready is not None:
            return ready

        result = {
            "schema": SCHEMA,
            "status": "failed",
            "phase": "physical-desktop",
            "dependency": pygame_dep,
            "console_dependency": console_dep,
            "x_dependencies": xdeps,
            "desktop": _json_file(self.desktop_receipt),
            "touchpad_detected": touchpad,
            "detail": self.log_path.read_text(encoding="utf-8", errors="replace")[-2500:] if self.log_path.is_file() else "",
        }
        _atomic_json(self.state_path, result)
        return result

    def stop(self) -> dict[str, Any]:
        self._clear_desktop()
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
    parser = argparse.ArgumentParser(description="Hopper native physical desktop manager")
    parser.add_argument("command", choices=("status", "start", "stop"))
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--desktop", type=Path, default=DEFAULT_DESKTOP)
    args = parser.parse_args()
    runtime = HopperDesktopRuntime(
        policy_path=args.policy,
        receipt_path=args.receipt,
        state_dir=args.state_dir,
        run_dir=args.run_dir,
        desktop=args.desktop,
    )
    try:
        if args.command == "start":
            result = runtime.locked_start()
        elif args.command == "stop":
            result = runtime.stop()
        else:
            result = runtime.status()
    except (DesktopRuntimeError, OSError, ValueError) as exc:
        result = {"schema": SCHEMA, "status": "failed", "detail": f"{type(exc).__name__}:{exc}"}
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("status") in {"running", "stopped", "busy", "refused"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
