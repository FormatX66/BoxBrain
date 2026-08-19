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

SCHEMA = "aurum-pc-gui-runtime-v1"
DEFAULT_WORKSPACE = Path(os.environ.get("AURUM_GIT_WORKSPACE", "/var/lib/aurum/workspace/BoxBrain"))
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
DEFAULT_RUN = Path("/run/aurum")
DEFAULT_PORT = 8765


class GuiRuntimeError(RuntimeError):
    pass


class GuiRuntime:
    def __init__(
        self,
        *,
        workspace: Path = DEFAULT_WORKSPACE,
        state_dir: Path = DEFAULT_STATE,
        run_dir: Path = DEFAULT_RUN,
        port: int = DEFAULT_PORT,
    ) -> None:
        self.workspace = workspace
        self.state_dir = state_dir
        self.root = state_dir / "gui"
        self.run_dir = run_dir
        self.port = port
        self.seed_dir = workspace / "Projects" / "Codelation" / "seed"
        self.gui_script = self.seed_dir / "aurum_gui.py"
        self.bootstrap_mind = workspace / "Projects" / "Codelation" / "mind" / "bootstrap_mind.json"
        self.pid_path = run_dir / "aurum-gui.pid"
        self.log_path = run_dir / "aurum-gui.log"

    def _pid(self) -> int | None:
        try:
            pid = int(self.pid_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None
        return pid if pid > 1 else None

    def _owned_process(self, pid: int) -> bool:
        try:
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            return False
        return "aurum_gui.py" in cmdline and str(self.gui_script) in cmdline

    def _probe(self) -> dict[str, Any]:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/status",
            headers={"Host": f"127.0.0.1:{self.port}", "User-Agent": "Aurum-PC-GUI-Probe/1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                raw = response.read(65536)
                payload = json.loads(raw.decode("utf-8"))
                return {
                    "reachable": response.status == 200,
                    "http_status": response.status,
                    "gui_schema": payload.get("schema"),
                    "loopback_only": bool((payload.get("transport") or {}).get("loopback_only")),
                    "dialogue_only": bool((payload.get("authority") or {}).get("dialogue_only")),
                    "host_actuation": bool((payload.get("authority") or {}).get("host_actuation")),
                }
        except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
            return {"reachable": False}

    def prepare(self) -> None:
        if not (self.workspace / ".git").is_dir():
            raise GuiRuntimeError("Git workspace is not initialized")
        if not self.gui_script.is_file() or not self.bootstrap_mind.is_file():
            raise GuiRuntimeError("Aurum GUI source is incomplete")
        self.root.mkdir(parents=True, exist_ok=True)
        mind_dir = self.root / "mind"
        mind_dir.mkdir(parents=True, exist_ok=True)
        bootstrap_target = mind_dir / "bootstrap_mind.json"
        if not bootstrap_target.is_file():
            shutil.copy2(self.bootstrap_mind, bootstrap_target)
            os.chmod(bootstrap_target, 0o600)
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def status(self) -> dict[str, Any]:
        pid = self._pid()
        owned = bool(pid and self._owned_process(pid))
        probe = self._probe() if owned else {"reachable": False}
        if pid and not owned:
            self.pid_path.unlink(missing_ok=True)
            pid = None
        return {
            "schema": SCHEMA,
            "status": "running" if owned and probe.get("reachable") else "stopped",
            "pid": pid if owned else None,
            "address": "127.0.0.1",
            "port": self.port,
            "loopback_only": True,
            "probe": probe,
            "root": str(self.root),
        }

    def start(self) -> dict[str, Any]:
        self.prepare()
        current = self.status()
        if current["status"] == "running":
            return current
        log = self.log_path.open("ab", buffering=0)
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(self.gui_script),
                    "--root",
                    str(self.root),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(self.port),
                ],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                close_fds=True,
                start_new_session=True,
            )
        finally:
            log.close()
        self.pid_path.write_text(str(process.pid) + "\n", encoding="utf-8")
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            result = self.status()
            if result["status"] == "running":
                return result
            if process.poll() is not None:
                break
            time.sleep(0.25)
        detail = ""
        try:
            detail = self.log_path.read_text(encoding="utf-8", errors="replace")[-1000:]
        except OSError:
            pass
        self.pid_path.unlink(missing_ok=True)
        raise GuiRuntimeError("GUI did not become ready" + (f": {detail}" if detail else ""))

    def stop(self) -> dict[str, Any]:
        pid = self._pid()
        if not pid:
            return self.status()
        if not self._owned_process(pid):
            self.pid_path.unlink(missing_ok=True)
            raise GuiRuntimeError("refusing to signal an unrecognized process")
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and self._owned_process(pid):
            time.sleep(0.1)
        self.pid_path.unlink(missing_ok=True)
        return self.status()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Installed Aurum loopback GUI runtime manager")
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
