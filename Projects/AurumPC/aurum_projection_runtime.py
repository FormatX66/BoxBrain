#!/usr/bin/env python3
"""HTML-first physical projection runtime for Hopper.

The primary human surface is the loopback Aurum HTML projection rendered in a
sandboxed kiosk browser on VT2.  The existing Pygame desktop runtime remains an
automatic fallback if the web renderer cannot be prepared or verified.
"""
from __future__ import annotations

import argparse
import fcntl
import grp
import importlib.util
import json
import os
import pwd
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCHEMA = "aurum.hopper-projection.gen1-html-primary"
DEFAULT_POLICY = Path(__file__).with_name("pc01_autonomy_policy.json")
DEFAULT_RECEIPT = Path("/etc/aurum-installed.json")
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
DEFAULT_RUN = Path(os.environ.get("AURUM_RUN_DIR", "/run/aurum"))
DEFAULT_FALLBACK = Path("/opt/aurum/aurum_desktop_runtime.py")
DEFAULT_DESKTOP = Path("/opt/aurum/aurum_desktop.py")
DEFAULT_SURFACE = Path("/opt/aurum/aurum_web_surface.py")
DEFAULT_URL = "http://127.0.0.1:8765/"
UI_USER = "aurum-ui"


def _boot_id() -> str | None:
    try:
        value = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _load(path: Path, prefix: str):
    if not path.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location(f"{prefix}_{os.getpid()}_{time.time_ns()}", path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def _browser() -> str | None:
    configured = os.environ.get("AURUM_WEB_RENDERER", "").strip()
    if configured and Path(configured).is_file():
        return configured
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        found = shutil.which(name)
        if found:
            return found
    return None


class ProjectionRuntime:
    def __init__(self, *, policy: Path, receipt: Path, state_dir: Path, run_dir: Path, desktop: Path) -> None:
        self.policy_path = policy
        self.receipt_path = receipt
        self.state_dir = state_dir
        self.run_dir = run_dir
        self.desktop = desktop
        self.surface = Path(os.environ.get("AURUM_WEB_SURFACE", str(DEFAULT_SURFACE)))
        self.fallback = Path(os.environ.get("AURUM_PYGAME_RUNTIME", str(DEFAULT_FALLBACK)))
        self.state_path = state_dir / "hopper-projection.json"
        self.receipt = state_dir / "desktop-ui.json"
        self.pid_path = run_dir / "aurum-web-surface.pid"
        self.log_path = state_dir / "hopper-projection.log"
        self.lock_path = run_dir / "aurum-projection.lock"

    def _authorized(self) -> tuple[bool, str]:
        fallback = _load(self.fallback, "aurum_desktop_runtime_auth")
        if fallback is None:
            return False, "fallback-runtime-unavailable"
        try:
            runtime = fallback.HopperDesktopRuntime(
                policy_path=self.policy_path,
                receipt_path=self.receipt_path,
                state_dir=self.state_dir,
                run_dir=self.run_dir,
                desktop=self.desktop,
            )
            return runtime.authorization()
        except Exception as exc:
            return False, f"authorization-error:{type(exc).__name__}"

    def _pid(self) -> int | None:
        try:
            pid = int(self.pid_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None
        return pid if pid > 1 else None

    @staticmethod
    def _cmdline(pid: int) -> str:
        try:
            return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            return ""

    def _owned(self, pid: int) -> bool:
        return "aurum_web_surface.py" in self._cmdline(pid)

    @staticmethod
    def _process_state(pid: int) -> str | None:
        try:
            value = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        try:
            return value.rsplit(")", 1)[1].strip().split()[0]
        except (IndexError, ValueError):
            return None

    def _process_record(self, pid: int) -> dict[str, Any] | None:
        try:
            group = os.getpgid(pid)
            session = os.getsid(pid)
        except (OSError, ProcessLookupError):
            return None
        try:
            wait_channel = Path(f"/proc/{pid}/wchan").read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            wait_channel = ""
        return {
            "command": self._cmdline(pid)[:500],
            "group": group,
            "session": session,
            "state": self._process_state(pid),
            "wait_channel": wait_channel or None,
        }

    def _recognized_vt2_processes(self) -> dict[int, dict[str, Any]]:
        """Return exact Aurum presentation clients and their launch sessions.

        ``openvt`` and ``xinit`` can outlive a child that was signalled by PID
        and leave the rest of its VT2 launch tree behind.  Aurum starts each
        presentation in a new session, although xinit may split that session
        into multiple process groups.  The session is therefore the narrow
        ownership boundary that includes the wrappers and Xorg without
        touching unrelated system processes.
        """
        found: dict[int, dict[str, Any]] = {}
        try:
            entries = list(Path("/proc").iterdir())
        except OSError:
            return found
        surface = str(self.surface)
        desktop = str(self.desktop)
        current_session = os.getsid(0)
        for entry in entries:
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            if pid <= 1 or pid == os.getpid():
                continue
            command = self._cmdline(pid)
            if not command:
                continue
            aurum_client = surface in command or f"{desktop} run" in command
            if not aurum_client:
                continue
            record = self._process_record(pid)
            if record is None:
                continue
            if int(record["session"]) <= 1 or int(record["session"]) == current_session:
                continue
            found[pid] = record
        return found

    def _session_members(self, sessions: set[int]) -> dict[int, dict[str, Any]]:
        found: dict[int, dict[str, Any]] = {}
        if not sessions:
            return found
        try:
            entries = list(Path("/proc").iterdir())
        except OSError:
            return found
        current_session = os.getsid(0)
        for entry in entries:
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            if pid <= 1 or pid == os.getpid():
                continue
            record = self._process_record(pid)
            if record is None:
                continue
            session = int(record["session"])
            if session in sessions and session != current_session:
                found[pid] = record
        return found

    @staticmethod
    def _signal_processes(pids: set[int], sig: signal.Signals) -> dict[int, str]:
        errors: dict[int, str] = {}
        for pid in sorted(pids, reverse=True):
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
            except (OSError, PermissionError) as exc:
                errors[pid] = f"{type(exc).__name__}:{exc}"
        return errors

    @staticmethod
    def _vt2_servers(processes: dict[int, dict[str, Any]]) -> list[int]:
        return sorted(
            pid
            for pid, item in processes.items()
            if "vt2" in str(item.get("command") or "")
            and ("Xorg" in str(item.get("command") or "") or "/X " in str(item.get("command") or ""))
        )

    def _clear_stale_vt2(self) -> dict[str, Any]:
        before = self._recognized_vt2_processes()
        if not before:
            return {"status": "cleared", "terminated": [], "boot_id": _boot_id()}
        groups = {int(item["group"]) for item in before.values()}
        sessions = {int(item["session"]) for item in before.values()}
        members = self._session_members(sessions)
        errors = self._signal_processes(set(members), signal.SIGTERM)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            remaining = self._session_members(sessions)
            if not remaining:
                break
            time.sleep(0.15)
        remaining = self._session_members(sessions)
        errors.update(self._signal_processes(set(remaining), signal.SIGKILL))
        kill_deadline = time.monotonic() + 3
        while time.monotonic() < kill_deadline and self._session_members(sessions):
            time.sleep(0.1)
        after = self._session_members(sessions)
        remaining_servers = self._vt2_servers(after)
        kernel_waits = sorted(pid for pid, item in after.items() if item.get("state") == "D")
        self.pid_path.unlink(missing_ok=True)
        (self.run_dir / "aurum-desktop.pid").unlink(missing_ok=True)
        status = "failed" if remaining_servers else ("blocked" if kernel_waits else "cleared")
        reason = None
        if remaining_servers:
            reason = "vt2-server-survived-cleanup"
        elif kernel_waits:
            reason = "aurum-display-clients-in-uninterruptible-kernel-wait"
        return {
            "status": status,
            "reason": reason,
            "reboot_required": bool(kernel_waits),
            "boot_id": _boot_id(),
            "terminated": sorted(before),
            "groups": sorted(groups),
            "sessions": sorted(sessions),
            "commands": [str(before[pid]["command"]) for pid in sorted(before)],
            "remaining": sorted(after),
            "remaining_states": {str(pid): after[pid].get("state") for pid in sorted(after)},
            "remaining_wait_channels": {str(pid): after[pid].get("wait_channel") for pid in sorted(after)},
            "remaining_vt2_servers": remaining_servers,
            "signal_errors": {str(pid): detail for pid, detail in sorted(errors.items())},
        }

    def _log_tail(self) -> str:
        try:
            return self.log_path.read_text(encoding="utf-8", errors="replace")[-2400:]
        except OSError:
            return ""

    def _fallback_runtime(self):
        module = _load(self.fallback, "aurum_desktop_runtime_fallback")
        if module is None:
            return None
        return module.HopperDesktopRuntime(
            policy_path=self.policy_path,
            receipt_path=self.receipt_path,
            state_dir=self.state_dir,
            run_dir=self.run_dir,
            desktop=self.desktop,
        )

    def status(self) -> dict[str, Any]:
        authorized, reason = self._authorized()
        pid = self._pid()
        receipt = _json(self.receipt)
        if pid and self._owned(pid) and receipt.get("status") == "running" and receipt.get("renderer") == "html5":
            return {
                "schema": SCHEMA,
                "status": "running",
                "authorized": authorized,
                "authorization_reason": reason,
                "machine": "Hopper",
                "surface": "physical",
                "renderer": "html5",
                "primary": True,
                "fallback": "pygame",
                "pid": pid,
                "vt": 2,
                "desktop": receipt,
            }
        fallback = self._fallback_runtime()
        if fallback is not None:
            try:
                current = fallback.status()
            except Exception:
                current = {}
            if current.get("status") == "running":
                return {
                    "schema": SCHEMA,
                    "status": "running",
                    "authorized": authorized,
                    "authorization_reason": reason,
                    "machine": "Hopper",
                    "surface": "physical",
                    "renderer": "pygame-fallback",
                    "primary": False,
                    "fallback": "pygame",
                    "vt": current.get("vt", 2),
                    "desktop": current.get("desktop") or {},
                }
        last_attempt = _json(self.state_path)
        html_failure = last_attempt.get("html_failure") if isinstance(last_attempt.get("html_failure"), dict) else {}
        blocked_boot = last_attempt.get("boot_id") or html_failure.get("boot_id")
        reboot_marked = bool(last_attempt.get("reboot_required") or html_failure.get("reboot_required"))
        return {
            "schema": SCHEMA,
            "status": "stopped",
            "authorized": authorized,
            "authorization_reason": reason,
            "machine": "Hopper",
            "surface": "physical",
            "renderer": None,
            "primary": False,
            "fallback": "pygame",
            "vt": 2,
            "reboot_required": bool(reboot_marked and blocked_boot and blocked_boot == _boot_id()),
        }

    def _ensure_ui_user(self) -> dict[str, Any]:
        try:
            account = pwd.getpwnam(UI_USER)
            return {"status": "ready", "user": UI_USER, "uid": account.pw_uid, "created": False}
        except KeyError:
            pass
        useradd = shutil.which("useradd")
        if not useradd or os.geteuid() != 0:
            return {"status": "missing", "reason": "useradd-or-root-unavailable"}
        home = "/var/lib/aurum/ui"
        result = subprocess.run(
            [useradd, "--system", "--create-home", "--home-dir", home, "--shell", "/usr/sbin/nologin", UI_USER],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
        )
        if result.returncode != 0:
            return {"status": "failed", "detail": result.stdout[-1000:]}
        account = pwd.getpwnam(UI_USER)
        return {"status": "ready", "user": UI_USER, "uid": account.pw_uid, "created": True}

    def _ensure_dependencies(self) -> dict[str, Any]:
        browser = _browser()
        ready = bool(browser and shutil.which("xinit") and shutil.which("openvt") and shutil.which("xhost"))
        if ready:
            return {"status": "ready", "browser": browser, "installed": False}
        policy = _json(self.policy_path)
        if policy.get("install_local_display_dependencies") is not True:
            return {"status": "missing", "reason": "dependency-install-disabled", "browser": browser}
        apt = shutil.which("apt-get")
        if not apt or os.geteuid() != 0:
            return {"status": "missing", "reason": "apt-or-root-unavailable", "browser": browser}
        env = dict(os.environ)
        env["DEBIAN_FRONTEND"] = "noninteractive"
        result = subprocess.run(
            [apt, "install", "-y", "--no-install-recommends", "chromium", "xserver-xorg", "xinit", "x11-xserver-utils", "xserver-xorg-input-libinput", "kbd"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=300,
            env=env,
        )
        browser = _browser()
        ready = bool(result.returncode == 0 and browser and shutil.which("xinit") and shutil.which("openvt") and shutil.which("xhost"))
        return {
            "status": "ready" if ready else "failed",
            "browser": browser,
            "installed": True,
            "detail": "" if ready else result.stdout[-1800:],
        }

    def _stop_web(self) -> None:
        pid = self._pid()
        if pid and self._owned(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + 6
            while time.monotonic() < deadline and self._owned(pid):
                time.sleep(0.1)
            if self._owned(pid):
                os.kill(pid, signal.SIGKILL)
        self.pid_path.unlink(missing_ok=True)

    def _start_web(self) -> dict[str, Any] | None:
        deps = self._ensure_dependencies()
        user = self._ensure_ui_user()
        if deps.get("status") != "ready" or user.get("status") != "ready" or not self.surface.is_file():
            _atomic(self.state_path, {"schema": SCHEMA, "status": "web-unavailable", "dependencies": deps, "ui_user": user})
            return None
        self._stop_web()
        stale_cleanup = self._clear_stale_vt2()
        if stale_cleanup.get("status") != "cleared":
            reason = (
                "kernel-display-waits-require-reboot"
                if stale_cleanup.get("reboot_required")
                else "stale-vt2-owner-not-cleared"
            )
            _atomic(self.state_path, {
                "schema": SCHEMA,
                "status": "web-unavailable",
                "reason": reason,
                "reboot_required": bool(stale_cleanup.get("reboot_required")),
                "boot_id": stale_cleanup.get("boot_id"),
                "stale_cleanup": stale_cleanup,
            })
            return None
        openvt = shutil.which("openvt")
        xinit = shutil.which("xinit")
        env_tool = shutil.which("env") or "/usr/bin/env"
        python = shutil.which("python3") or sys.executable
        assert openvt and xinit
        command = [
            openvt, "-c", "2", "-s", "-f", "--",
            xinit,
            env_tool,
            f"AURUM_STATE_DIR={self.state_dir}",
            f"AURUM_RUN_DIR={self.run_dir}",
            f"AURUM_WEB_RENDERER={deps.get('browser')}",
            python, str(self.surface),
            "--url", DEFAULT_URL,
            "--state-dir", str(self.state_dir),
            "--run-dir", str(self.run_dir),
            "--ui-user", UI_USER,
            "--", ":0", "vt2", "-nolisten", "tcp",
        ]
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        log = self.log_path.open("ab", buffering=0)
        try:
            subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log, close_fds=True, start_new_session=True)
        finally:
            log.close()
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            current = self.status()
            if current.get("renderer") == "html5" and current.get("status") == "running":
                current["dependencies"] = deps
                current["ui_user"] = user
                current["stale_cleanup"] = stale_cleanup
                _atomic(self.state_path, current)
                return current
            receipt = _json(self.receipt)
            if receipt.get("renderer") == "html5" and receipt.get("status") == "failed":
                break
            time.sleep(0.35)
        self._stop_web()
        _atomic(self.state_path, {
            "schema": SCHEMA,
            "status": "web-unavailable",
            "reason": "html-launch-not-verified",
            "dependencies": deps,
            "ui_user": user,
            "stale_cleanup": stale_cleanup,
            "log_tail": self._log_tail(),
        })
        return None

    def _start_locked(self) -> dict[str, Any]:
        authorized, reason = self._authorized()
        if not authorized:
            result = {"schema": SCHEMA, "status": "refused", "authorized": False, "reason": reason}
            _atomic(self.state_path, result)
            return result
        if os.geteuid() != 0:
            return {"schema": SCHEMA, "status": "failed", "reason": "root-owned-runtime-required"}
        current = self.status()
        if current.get("status") == "running" and current.get("renderer") == "html5":
            return current
        web = self._start_web()
        if web is not None:
            return web
        html_failure = _json(self.state_path)
        if html_failure.get("reboot_required"):
            result = {
                "schema": SCHEMA,
                "status": "failed",
                "authorized": True,
                "machine": "Hopper",
                "surface": "physical",
                "renderer": None,
                "primary": False,
                "fallback": "pygame",
                "fallback_result": {
                    "status": "skipped",
                    "reason": "kernel-display-waits-require-reboot",
                },
                "html_failure": html_failure,
                "reboot_required": True,
                "boot_id": html_failure.get("boot_id"),
            }
            _atomic(self.state_path, result)
            return result
        fallback = self._fallback_runtime()
        if fallback is None:
            result = {"schema": SCHEMA, "status": "failed", "reason": "web-and-fallback-unavailable"}
            _atomic(self.state_path, result)
            return result
        try:
            fallback_result = fallback.start()
        except Exception as exc:
            fallback_result = {"status": "failed", "detail": f"{type(exc).__name__}:{exc}"}
        result = {
            "schema": SCHEMA,
            "status": fallback_result.get("status", "failed"),
            "authorized": True,
            "machine": "Hopper",
            "surface": "physical",
            "renderer": "pygame-fallback" if fallback_result.get("status") == "running" else None,
            "primary": False,
            "fallback": "pygame",
            "fallback_result": fallback_result,
            "html_failure": html_failure,
        }
        _atomic(self.state_path, result)
        return result

    def start(self) -> dict[str, Any]:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {
                    "schema": SCHEMA,
                    "status": "busy",
                    "reason": "projection-transition-in-progress",
                    "machine": "Hopper",
                    "surface": "physical",
                    "fallback": "pygame",
                }
            return self._start_locked()

    def _stop_locked(self) -> dict[str, Any]:
        self._stop_web()
        fallback = self._fallback_runtime()
        if fallback is not None:
            try:
                fallback.stop()
            except Exception:
                pass
        result = self.status()
        _atomic(self.state_path, result)
        return result

    def stop(self) -> dict[str, Any]:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {
                    "schema": SCHEMA,
                    "status": "busy",
                    "reason": "projection-transition-in-progress",
                    "machine": "Hopper",
                    "surface": "physical",
                    "fallback": "pygame",
                }
            return self._stop_locked()


def main() -> int:
    parser = argparse.ArgumentParser(description="Hopper HTML-first physical projection manager")
    parser.add_argument("command", choices=("status", "start", "stop"))
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--desktop", type=Path, default=DEFAULT_DESKTOP)
    args = parser.parse_args()
    runtime = ProjectionRuntime(policy=args.policy, receipt=args.receipt, state_dir=args.state_dir, run_dir=args.run_dir, desktop=args.desktop)
    try:
        if args.command == "start":
            result = runtime.start()
        elif args.command == "stop":
            result = runtime.stop()
        else:
            result = runtime.status()
    except Exception as exc:
        result = {"schema": SCHEMA, "status": "failed", "detail": f"{type(exc).__name__}:{exc}"}
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("status") in {"running", "stopped", "refused"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
