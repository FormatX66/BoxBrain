#!/usr/bin/env python3
"""Bounded continuous self-diagnosis and safe local recovery for Hopper."""
from __future__ import annotations

import json
import os
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from aurum_gui_runtime import GuiRuntime, GuiRuntimeError
from aurum_input import status as input_status
from aurum_network import network_status
from aurum_runtime_update import RuntimeUpdater, RuntimeUpdateError

SCHEMA = "aurum.self-debug.v2"
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
DEFAULT_WORKSPACE = Path(os.environ.get("AURUM_GIT_WORKSPACE", "/var/lib/aurum/workspace/BoxBrain"))
DEFAULT_PORT = 8768


def _json(path: Path) -> dict[str, Any]:
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


class HopperSelfDebugger:
    def __init__(self, *, state_dir: Path = DEFAULT_STATE, workspace: Path = DEFAULT_WORKSPACE) -> None:
        self.state_dir = state_dir
        self.workspace = workspace
        self.receipt = state_dir / "self-debug.json"
        self.gui = GuiRuntime(workspace=workspace, state_dir=state_dir)
        self.runtime = RuntimeUpdater(workspace=workspace, state_dir=state_dir)

    def _collect(self) -> dict[str, Any]:
        inp = input_status(apply_wake=False)
        try:
            gui = self.gui.status()
        except (GuiRuntimeError, OSError) as exc:
            gui = {"status": "failed", "detail": f"{type(exc).__name__}:{exc}"}
        try:
            runtime = self.runtime.plan()
        except (RuntimeUpdateError, OSError) as exc:
            runtime = {"status": "failed", "detail": f"{type(exc).__name__}:{exc}"}
        return {
            "input": inp,
            "gui": gui,
            "runtime": runtime,
            "network": network_status(),
            "self_build": _json(self.state_dir / "self-build-progress.json"),
        }

    @staticmethod
    def _issues(state: dict[str, Any]) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        inp = state["input"]
        if not inp.get("pointers"):
            issues.append({"code": "INPUT_NO_POINTER", "severity": "red", "plain": "No pointer device is visible to Aurum."})
        elif not bool((inp.get("libinput") or {}).get("xorg_driver")):
            issues.append({"code": "INPUT_LIBINPUT_MISSING", "severity": "red", "plain": "Trackpad is visible but Xorg libinput translation is missing."})
        elif inp.get("status") != "ready":
            issues.append({"code": "INPUT_DEGRADED", "severity": "amber", "plain": "Pointer path is present but degraded."})

        gui = state["gui"]
        if gui.get("status") != "running":
            issues.append({"code": "GUI_NOT_RUNNING", "severity": "red", "plain": "Aurum GUI service is not running."})
        elif not gui.get("physical_desktop"):
            issues.append({"code": "DESKTOP_NOT_PRESENTING", "severity": "red", "plain": "GUI service is alive but the physical Hopper desktop is not presenting."})

        runtime = state["runtime"]
        if runtime.get("status") == "failed":
            issues.append({"code": "RUNTIME_STATUS_FAILED", "severity": "red", "plain": "Aurum could not inspect the installed runtime."})
        elif runtime.get("changes") or runtime.get("system_changed"):
            issues.append({"code": "RUNTIME_UPDATE_PENDING", "severity": "amber", "plain": "A newer workspace state is ready to install."})

        if not state["network"].get("online"):
            issues.append({"code": "NETWORK_OFFLINE", "severity": "amber", "plain": "Hopper is offline; local operation remains available."})
        if state["self_build"] and state["self_build"].get("status") == "failed":
            issues.append({"code": "SELF_BUILD_FAILED", "severity": "amber", "plain": "The latest bounded self-build reported a failure."})
        return issues

    def status(self) -> dict[str, Any]:
        state = self._collect()
        issues = self._issues(state)
        payload = {
            "schema": SCHEMA,
            "machine": "Hopper",
            "status": "healthy" if not issues else "degraded",
            "issue_count": len(issues),
            "issues": issues,
            "input": {
                "status": state["input"].get("status"),
                "pointers": len(state["input"].get("pointers") or []),
                "touchpads": len(state["input"].get("touchpads") or []),
                "libinput": state["input"].get("libinput"),
            },
            "gui": {
                "status": state["gui"].get("status"),
                "physical_desktop": bool(state["gui"].get("physical_desktop")),
                "desktop_status": (state["gui"].get("desktop") or {}).get("status"),
            },
            "runtime": {
                "schema": state["runtime"].get("schema"),
                "status": state["runtime"].get("status"),
                "changes": bool(state["runtime"].get("changes") or state["runtime"].get("system_changed")),
            },
            "network": {"online": bool(state["network"].get("online"))},
            "boundary": {
                "read_only_endpoint": True,
                "arbitrary_shell": False,
                "physical_driver_swap": False,
                "firmware_write": False,
            },
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _atomic_json(self.receipt, payload)
        return payload

    def cycle(self) -> dict[str, Any]:
        before = self.status()
        actions: list[dict[str, Any]] = []
        codes = {item.get("code") for item in before.get("issues") or []}

        if "INPUT_LIBINPUT_MISSING" in codes or "INPUT_DEGRADED" in codes:
            repaired = input_status(apply_wake=True)
            actions.append({"action": "input-recover", "status": repaired.get("status"), "repair": repaired.get("repair")})
            if repaired.get("gui_restart_required"):
                try:
                    self.gui.stop()
                    restarted = self.gui.start()
                    actions.append({"action": "gui-restart-after-input", "status": restarted.get("status")})
                except (GuiRuntimeError, OSError) as exc:
                    actions.append({"action": "gui-restart-after-input", "status": "failed", "detail": type(exc).__name__})

        if "GUI_NOT_RUNNING" in codes or "DESKTOP_NOT_PRESENTING" in codes:
            try:
                started = self.gui.start()
                actions.append({"action": "gui-start", "status": started.get("status")})
            except (GuiRuntimeError, OSError) as exc:
                actions.append({"action": "gui-start", "status": "failed", "detail": type(exc).__name__})

        after = self.status()
        result = {
            **after,
            "cycle": {
                "before_issue_count": before.get("issue_count", 0),
                "after_issue_count": after.get("issue_count", 0),
                "actions": actions,
                "bounded": True,
            },
        }
        _atomic_json(self.receipt, result)
        return result


class _StatusServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], debugger: HopperSelfDebugger) -> None:
        super().__init__(address, _StatusHandler)
        self.debugger = debugger


class _StatusHandler(BaseHTTPRequestHandler):
    server: _StatusServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if urlsplit(self.path).path not in {"/", "/status"}:
            self._send(HTTPStatus.NOT_FOUND, {"schema": SCHEMA, "error": "not-found"})
            return
        payload = _json(self.server.debugger.receipt)
        if not payload:
            payload = self.server.debugger.status()
        self._send(HTTPStatus.OK, payload)

    def do_POST(self) -> None:  # noqa: N802
        self._send(HTTPStatus.METHOD_NOT_ALLOWED, {"schema": SCHEMA, "error": "read-only"})


def watch(interval: int = 60, port: int = DEFAULT_PORT) -> int:
    debugger = HopperSelfDebugger()
    debugger.status()
    server = _StatusServer(("0.0.0.0", port), debugger)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True)
    thread.start()
    time.sleep(min(30, interval))
    try:
        while True:
            debugger.cycle()
            time.sleep(max(30, interval))
    except KeyboardInterrupt:
        server.shutdown()
        return 0


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Bounded Hopper self-debugger")
    parser.add_argument("command", choices=("status", "cycle", "watch"))
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    if args.command == "watch":
        return watch(interval=args.interval, port=args.port)
    debugger = HopperSelfDebugger()
    payload = debugger.cycle() if args.command == "cycle" else debugger.status()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("status") == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
