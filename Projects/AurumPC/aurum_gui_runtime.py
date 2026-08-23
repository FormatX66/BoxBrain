#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SCHEMA = "aurum-pc-gui-runtime-v3"
DEFAULT_WORKSPACE = Path(os.environ.get("AURUM_GIT_WORKSPACE", "/var/lib/aurum/workspace/BoxBrain"))
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
DEFAULT_RUN = Path(os.environ.get("AURUM_RUN_DIR", "/run/aurum"))
DEFAULT_RUNTIME = Path(os.environ.get("AURUM_RUNTIME_ROOT", "/opt/aurum"))
DEFAULT_PORT = 8765
DEFAULT_ARCADE_PORT = 8766


class GuiRuntimeError(RuntimeError):
    pass


class GuiRuntime:
    def __init__(
        self,
        *,
        workspace: Path = DEFAULT_WORKSPACE,
        state_dir: Path = DEFAULT_STATE,
        run_dir: Path = DEFAULT_RUN,
        runtime_root: Path = DEFAULT_RUNTIME,
        port: int = DEFAULT_PORT,
        arcade_port: int = DEFAULT_ARCADE_PORT,
    ) -> None:
        self.workspace = workspace
        self.state_dir = state_dir
        self.root = state_dir / "gui"
        self.run_dir = run_dir
        self.runtime_root = runtime_root
        self.port = port
        self.arcade_port = arcade_port
        self.seed_dir = workspace / "Projects" / "Codelation" / "seed"
        self.base_gui_script = self.seed_dir / "aurum_gui.py"
        self.gui_script = workspace / "Projects" / "AurumPC" / "aurum_hopper_gui.py"
        self.arcade_script = workspace / "Projects" / "AurumPC" / "aurum_arcade.py"
        self.policy_path = workspace / "Projects" / "AurumPC" / "pc01_autonomy_policy.json"
        self.desktop_runtime = runtime_root / "aurum_projection_runtime.py"
        self.desktop_script = runtime_root / "aurum_desktop.py"
        self.bootstrap_mind = workspace / "Projects" / "Codelation" / "mind" / "bootstrap_mind.json"
        self.pid_path = run_dir / "aurum-gui.pid"
        self.log_path = run_dir / "aurum-gui.log"
        self.arcade_pid_path = run_dir / "aurum-arcade.pid"
        self.arcade_log_path = run_dir / "aurum-arcade.log"

    @staticmethod
    def _read_pid(path: Path) -> int | None:
        try:
            pid = int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None
        return pid if pid > 1 else None

    @staticmethod
    def _cmdline(pid: int) -> str:
        try:
            return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            return ""

    def _owned_gui(self, pid: int) -> bool:
        cmdline = self._cmdline(pid)
        return "aurum_hopper_gui.py" in cmdline and str(self.gui_script) in cmdline

    def _recognized_aurum_gui(self, pid: int) -> bool:
        cmdline = self._cmdline(pid)
        return "aurum_hopper_gui.py" in cmdline or "aurum_gui.py" in cmdline

    def _owned_arcade(self, pid: int) -> bool:
        cmdline = self._cmdline(pid)
        return "aurum_arcade.py" in cmdline and str(self.arcade_script) in cmdline

    @staticmethod
    def _listener_inodes(port: int) -> set[str]:
        wanted = f"{port:04X}"
        found: set[str] = set()
        for table in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
            try:
                lines = table.read_text(encoding="utf-8", errors="replace").splitlines()[1:]
            except OSError:
                continue
            for line in lines:
                fields = line.split()
                if len(fields) < 10:
                    continue
                local = fields[1]
                state = fields[3]
                if ":" not in local or state != "0A":
                    continue
                if local.rsplit(":", 1)[1].upper() == wanted:
                    found.add(fields[9])
        return found

    @classmethod
    def _listener_pids(cls, port: int) -> list[int]:
        inodes = cls._listener_inodes(port)
        if not inodes:
            return []
        found: list[int] = []
        try:
            proc_entries = list(Path("/proc").iterdir())
        except OSError:
            return found
        for entry in proc_entries:
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            fd_dir = entry / "fd"
            try:
                fds = list(fd_dir.iterdir())
            except OSError:
                continue
            for fd in fds:
                try:
                    target = os.readlink(fd)
                except OSError:
                    continue
                if target.startswith("socket:[") and target[8:-1] in inodes:
                    found.append(pid)
                    break
        return sorted(set(found))

    def _clear_stale_gui_listener(self) -> None:
        listeners = self._listener_pids(self.port)
        if not listeners:
            return
        unknown = [pid for pid in listeners if not self._recognized_aurum_gui(pid)]
        if unknown:
            details = ", ".join(f"pid={pid} cmd={self._cmdline(pid)[:180]!r}" for pid in unknown)
            raise GuiRuntimeError(f"port {self.port} is occupied by an unrecognized process: {details}")
        for pid in listeners:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if not self._listener_pids(self.port):
                self.pid_path.unlink(missing_ok=True)
                return
            time.sleep(0.1)
        raise GuiRuntimeError(f"stale Aurum GUI listener on port {self.port} did not stop")

    @staticmethod
    def _json_probe(port: int, path: str, user_agent: str) -> dict[str, Any]:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            headers={"Host": f"127.0.0.1:{port}", "User-Agent": user_agent},
        )
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                raw = response.read(65536)
                payload = json.loads(raw.decode("utf-8"))
                return {"reachable": response.status == 200, "http_status": response.status, "payload": payload}
        except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
            return {"reachable": False}

    def _gui_status(self) -> dict[str, Any]:
        pid = self._read_pid(self.pid_path)
        owned = bool(pid and self._owned_gui(pid))
        probe = self._json_probe(self.port, "/api/status", "Aurum-PC-GUI-Probe/3") if owned else {"reachable": False}
        if pid and not owned:
            self.pid_path.unlink(missing_ok=True)
            pid = None
        payload = probe.get("payload") if isinstance(probe.get("payload"), dict) else {}
        return {
            "status": "running" if owned and probe.get("reachable") else "stopped",
            "pid": pid if owned else None,
            "address": "127.0.0.1",
            "port": self.port,
            "loopback_only": True,
            "probe": {
                "reachable": bool(probe.get("reachable")),
                "http_status": probe.get("http_status"),
                "gui_schema": payload.get("schema"),
                "loopback_only": bool((payload.get("transport") or {}).get("loopback_only")),
                "dialogue_only": bool((payload.get("authority") or {}).get("dialogue_only")),
                "host_actuation": bool((payload.get("authority") or {}).get("host_actuation")),
                "identity_mark": ((payload.get("hopper") or {}).get("projection") or {}).get("identity_mark"),
            },
        }

    def _arcade_status(self) -> dict[str, Any]:
        pid = self._read_pid(self.arcade_pid_path)
        owned = bool(pid and self._owned_arcade(pid))
        probe = self._json_probe(self.arcade_port, "/api/status", "Aurum-PC-Arcade-Probe/1") if owned else {"reachable": False}
        if pid and not owned:
            self.arcade_pid_path.unlink(missing_ok=True)
            pid = None
        payload = probe.get("payload") if isinstance(probe.get("payload"), dict) else {}
        return {
            "status": "running" if owned and probe.get("reachable") else "stopped",
            "pid": pid if owned else None,
            "address": "127.0.0.1",
            "port": self.arcade_port,
            "loopback_only": True,
            "game": payload.get("game", "Echo Rally"),
            "machine": payload.get("machine", "Hopper"),
            "host_actuation": bool(payload.get("host_actuation", False)),
            "probe": {"reachable": bool(probe.get("reachable")), "http_status": probe.get("http_status")},
        }

    def _desktop(self, action: str) -> dict[str, Any]:
        if not self.desktop_runtime.is_file() or not self.desktop_script.is_file():
            return {"status": "unavailable", "reason": "desktop-runtime-not-installed", "surface": "physical"}
        arguments = [
            sys.executable,
            str(self.desktop_runtime),
            action,
            "--policy",
            str(self.policy_path if self.policy_path.is_file() else self.runtime_root / "pc01_autonomy_policy.json"),
            "--state-dir",
            str(self.state_dir),
            "--run-dir",
            str(self.run_dir),
            "--desktop",
            str(self.desktop_script),
        ]
        try:
            result = subprocess.run(
                arguments,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                # First HTML projection may need to install the bounded local
                # renderer set before it can claim VT2.  Keep the caller alive
                # long enough to finish that one-time preparation and still
                # fall back to Pygame deterministically if verification fails.
                timeout=360 if action == "start" else 8,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {"status": "failed", "detail": f"{type(exc).__name__}:{exc}", "surface": "physical"}
        text = result.stdout.strip()
        try:
            payload = json.loads(text.splitlines()[-1]) if text else {}
        except json.JSONDecodeError:
            payload = {"status": "failed", "detail": text[-1800:]}
        if not isinstance(payload, dict):
            payload = {"status": "failed", "detail": "desktop-runtime-returned-non-object"}
        return payload

    def prepare(self) -> None:
        if not (self.workspace / ".git").is_dir():
            raise GuiRuntimeError("Git workspace is not initialized")
        if not self.base_gui_script.is_file() or not self.gui_script.is_file() or not self.bootstrap_mind.is_file():
            raise GuiRuntimeError("Aurum GUI source is incomplete")
        if not self.arcade_script.is_file():
            raise GuiRuntimeError("Aurum arcade source is incomplete")
        self.root.mkdir(parents=True, exist_ok=True)
        mind_dir = self.root / "mind"
        mind_dir.mkdir(parents=True, exist_ok=True)
        bootstrap_target = mind_dir / "bootstrap_mind.json"
        if not bootstrap_target.is_file():
            shutil.copy2(self.bootstrap_mind, bootstrap_target)
            os.chmod(bootstrap_target, 0o600)
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def status(self) -> dict[str, Any]:
        gui = self._gui_status()
        arcade = self._arcade_status()
        desktop = self._desktop("status")
        return {
            "schema": SCHEMA,
            "status": "running" if gui["status"] == "running" else "stopped",
            "pid": gui["pid"],
            "address": gui["address"],
            "port": gui["port"],
            "loopback_only": True,
            "probe": gui["probe"],
            "root": str(self.root),
            "arcade": arcade,
            "desktop": desktop,
            "physical_desktop": desktop.get("status") == "running",
            "machine": "Hopper",
        }

    @staticmethod
    def _spawn(script: Path, arguments: list[str], pid_path: Path, log_path: Path) -> subprocess.Popen[bytes]:
        log = log_path.open("ab", buffering=0)
        try:
            process = subprocess.Popen(
                [sys.executable, str(script), *arguments],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                close_fds=True,
                start_new_session=True,
            )
        finally:
            log.close()
        pid_path.write_text(str(process.pid) + "\n", encoding="utf-8")
        return process

    def _start_gui(self) -> None:
        if self._gui_status()["status"] == "running":
            return
        self._clear_stale_gui_listener()
        process = self._spawn(
            self.gui_script,
            ["--root", str(self.root), "--host", "127.0.0.1", "--port", str(self.port)],
            self.pid_path,
            self.log_path,
        )
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if self._gui_status()["status"] == "running":
                return
            if process.poll() is not None:
                break
            time.sleep(0.25)
        self.pid_path.unlink(missing_ok=True)
        detail = self.log_path.read_text(encoding="utf-8", errors="replace")[-1000:] if self.log_path.is_file() else ""
        raise GuiRuntimeError("GUI did not become ready" + (f": {detail}" if detail else ""))

    def _start_arcade(self) -> None:
        if self._arcade_status()["status"] == "running":
            return
        process = self._spawn(
            self.arcade_script,
            ["--host", "127.0.0.1", "--port", str(self.arcade_port)],
            self.arcade_pid_path,
            self.arcade_log_path,
        )
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if self._arcade_status()["status"] == "running":
                return
            if process.poll() is not None:
                break
            time.sleep(0.25)
        self.arcade_pid_path.unlink(missing_ok=True)
        detail = self.arcade_log_path.read_text(encoding="utf-8", errors="replace")[-1000:] if self.arcade_log_path.is_file() else ""
        raise GuiRuntimeError("Arcade did not become ready" + (f": {detail}" if detail else ""))

    def start(self) -> dict[str, Any]:
        self.prepare()
        old_pid = self._read_pid(self.pid_path)
        if old_pid and not self._owned_gui(old_pid):
            old_cmdline = self._cmdline(old_pid)
            if "aurum_gui.py" in old_cmdline or "aurum_hopper_gui.py" in old_cmdline:
                try:
                    os.kill(old_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and Path(f"/proc/{old_pid}").exists():
                    time.sleep(0.1)
                self.pid_path.unlink(missing_ok=True)
        self._start_gui()
        self._start_arcade()
        desktop = self._desktop("start")
        result = self.status()
        result["desktop_start"] = desktop
        return result

    @staticmethod
    def _stop_owned(pid_path: Path, owner_check, timeout: float = 5.0) -> None:
        pid = GuiRuntime._read_pid(pid_path)
        if not pid:
            return
        if not owner_check(pid):
            pid_path.unlink(missing_ok=True)
            raise GuiRuntimeError("refusing to signal an unrecognized process")
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and owner_check(pid):
            time.sleep(0.1)
        pid_path.unlink(missing_ok=True)

    def stop(self) -> dict[str, Any]:
        desktop = self._desktop("stop")
        self._stop_owned(self.arcade_pid_path, self._owned_arcade)
        try:
            self._stop_owned(self.pid_path, self._owned_gui)
        except GuiRuntimeError:
            self._clear_stale_gui_listener()
        result = self.status()
        result["desktop_stop"] = desktop
        return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Installed Aurum GUI + physical desktop runtime manager")
    parser.add_argument("command", choices=("status", "start", "stop"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    runtime = GuiRuntime()
    try:
        if args.command == "start":
            result = runtime.start()
        elif args.command == "stop":
            result = runtime.stop()
        else:
            result = runtime.status()
    except GuiRuntimeError as exc:
        print(json.dumps({"schema": SCHEMA, "status": "failed", "detail": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
