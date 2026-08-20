#!/usr/bin/env python3
"""Read-only Hopper proof surface for physical Echo Rally readiness.

The server exposes only a minimal, machine-bound readiness document. It does not
accept POST requests, execute commands, expose logs, or provide host-control.
Readiness is re-derived on every request from Hopper's current receipts, live
process state, physical input nodes, and open input-device handles.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

SCHEMA = "aurum.hopper.proof.v1"
DEFAULT_POLICY = Path(__file__).with_name("pc01_autonomy_policy.json")
DEFAULT_RECEIPT = Path("/etc/aurum-installed.json")
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
DEFAULT_RUN = Path("/run/aurum")
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8767
EVENT_RE = re.compile(r"\bevent\d+\b")


def _json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _authorized(policy: Mapping[str, Any], receipt: Mapping[str, Any]) -> tuple[bool, str]:
    if policy.get("schema") != "aurum-pc-autonomy-policy-v1" or policy.get("enabled") is not True:
        return False, "policy-disabled-or-invalid"
    if str(policy.get("machine_display_name") or "") != "Hopper":
        return False, "machine-name-not-hopper"
    match = policy.get("machine_match") if isinstance(policy.get("machine_match"), dict) else {}
    target = receipt.get("target") if isinstance(receipt.get("target"), dict) else {}
    expected_serial = str(match.get("installed_target_serial") or "")
    expected_size = int(match.get("installed_target_size_bytes") or 0)
    if not expected_serial or expected_size <= 0:
        return False, "machine-match-incomplete"
    if str(target.get("serial") or "") != expected_serial:
        return False, "installed-target-serial-mismatch"
    if int(target.get("size_bytes") or 0) != expected_size:
        return False, "installed-target-size-mismatch"
    return True, "authorized-hopper"


def _positive_resolution(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(item, int) and not isinstance(item, bool) and item > 0 for item in value)
    )


def _cmdline(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
    except OSError:
        return ""


def _process_alive(pid: object, marker: str) -> bool:
    return isinstance(pid, int) and not isinstance(pid, bool) and pid > 1 and marker in _cmdline(pid)


def _input_nodes() -> dict[str, list[str]]:
    keyboard: set[str] = set()
    pointer: set[str] = set()
    try:
        text = Path("/proc/bus/input/devices").read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    for block in text.split("\n\n"):
        handlers = ""
        for line in block.splitlines():
            if line.startswith("H: Handlers="):
                handlers = line.partition("=")[2]
                break
        if not handlers:
            continue
        events = EVENT_RE.findall(handlers)
        tokens = handlers.split()
        if "kbd" in tokens:
            keyboard.update(f"/dev/input/{name}" for name in events)
        if any(token.startswith("mouse") for token in tokens):
            pointer.update(f"/dev/input/{name}" for name in events)
    return {"keyboard": sorted(keyboard), "pointer": sorted(pointer)}


def _open_device_targets(pid: int) -> set[str]:
    targets: set[str] = set()
    fd_dir = Path(f"/proc/{pid}/fd")
    try:
        entries = list(fd_dir.iterdir())
    except OSError:
        return targets
    for entry in entries:
        try:
            target = os.readlink(entry)
        except OSError:
            continue
        if target.startswith("/dev/input/event"):
            targets.add(target)
    return targets


def _x_server_pids() -> list[int]:
    found: list[int] = []
    try:
        entries = list(Path("/proc").iterdir())
    except OSError:
        return found
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        cmdline = _cmdline(pid)
        if "Xorg" in cmdline or cmdline.startswith("/usr/lib/xorg/Xorg ") or cmdline.startswith("Xorg "):
            found.append(pid)
    return found


def _input_proof(echo: Mapping[str, Any], display: Mapping[str, Any]) -> dict[str, Any]:
    nodes = _input_nodes()
    keyboard_nodes = set(nodes["keyboard"])
    pointer_nodes = set(nodes["pointer"])
    game_pid = echo.get("pid")
    game_open: set[str] = set()
    if isinstance(game_pid, int) and not isinstance(game_pid, bool) and game_pid > 1:
        game_open = _open_device_targets(game_pid)

    mode = str(display.get("mode") or "")
    x_pids = _x_server_pids() if mode == "x11-vt2" else []
    x_open: set[str] = set()
    for pid in x_pids:
        x_open.update(_open_device_targets(pid))

    if mode == "kmsdrm-vt2":
        keyboard_open = sorted(keyboard_nodes & game_open)
        pointer_open = sorted(pointer_nodes & game_open)
    elif mode == "x11-vt2":
        keyboard_open = sorted(keyboard_nodes & x_open)
        pointer_open = sorted(pointer_nodes & x_open)
    else:
        keyboard_open = sorted(keyboard_nodes & (game_open | x_open))
        pointer_open = sorted(pointer_nodes & (game_open | x_open))

    return {
        "mode": mode or None,
        "keyboard_device_count": len(keyboard_nodes),
        "pointer_device_count": len(pointer_nodes),
        "keyboard_path_available": bool(keyboard_open),
        "pointer_path_available": bool(pointer_open),
        "keyboard_open_nodes": keyboard_open,
        "pointer_open_nodes": pointer_open,
        "game_open_input_node_count": len(game_open),
        "x_server_pids": x_pids,
        "x_open_input_node_count": len(x_open),
    }


def collect_proof(
    state_dir: Path = DEFAULT_STATE,
    *,
    policy_path: Path = DEFAULT_POLICY,
    receipt_path: Path = DEFAULT_RECEIPT,
) -> dict[str, Any]:
    now = time.time()
    policy = _json_file(policy_path)
    install = _json_file(receipt_path)
    identity = _json_file(state_dir / "machine-identity.json")
    display = _json_file(state_dir / "hopper-display.json")
    echo = _json_file(state_dir / "echo-native.json")
    authorized, authorization_reason = _authorized(policy, install)

    echo_process_running = _process_alive(echo.get("pid"), "aurum_echo_native.py")
    input_proof = _input_proof(echo, display)
    display_ready = bool(
        display.get("physical_display") is True
        and display.get("status") == "running"
        and str(display.get("machine") or "") == "Hopper"
    )
    echo_ready = bool(
        echo.get("status") == "running"
        and echo_process_running
        and str(echo.get("machine") or "") == "Hopper"
        and str(echo.get("game") or "") == "Echo Rally"
        and echo.get("fullscreen") is True
        and isinstance(echo.get("video_driver"), str)
        and bool(str(echo.get("video_driver") or "").strip())
        and _positive_resolution(echo.get("physical_resolution"))
    )
    identity_ready = bool(
        identity.get("status") == "named"
        and identity.get("display_name") == "Hopper"
        and identity.get("hostname") == "hopper"
    )
    ready = bool(
        authorized
        and identity_ready
        and display_ready
        and echo_ready
        and input_proof["keyboard_path_available"]
        and input_proof["pointer_path_available"]
    )

    return {
        "schema": SCHEMA,
        "ready": ready,
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "machine": {
            "authorized": authorized,
            "authorization_reason": authorization_reason,
            "display_name": identity.get("display_name"),
            "configured_hostname": identity.get("hostname"),
            "runtime_hostname": socket.gethostname(),
            "identity_receipt_ready": identity_ready,
        },
        "display": {
            "ready": display_ready,
            "mode": display.get("mode"),
            "physical_display": display.get("physical_display") is True,
            "status": display.get("status"),
        },
        "echo": {
            "ready": echo_ready,
            "status": echo.get("status"),
            "game": echo.get("game"),
            "pid": echo.get("pid"),
            "process_running": echo_process_running,
            "fullscreen": echo.get("fullscreen") is True,
            "video_driver": echo.get("video_driver"),
            "physical_resolution": echo.get("physical_resolution"),
            "started_at": echo.get("started_at"),
        },
        "input": input_proof,
        "boundary": {
            "read_only": True,
            "post_supported": False,
            "host_actuation": False,
            "logs_exposed": False,
            "credential_data_exposed": False,
        },
    }


class ProofServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(
        self,
        address: tuple[str, int],
        state_dir: Path,
        policy_path: Path,
        receipt_path: Path,
    ) -> None:
        super().__init__(address, ProofHandler)
        self.state_dir = state_dir
        self.policy_path = policy_path
        self.receipt_path = receipt_path


class ProofHandler(BaseHTTPRequestHandler):
    server: ProofServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def _headers(self, length: int) -> None:
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self._headers(len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path not in {"/", "/proof"}:
            self._json(HTTPStatus.NOT_FOUND, {"schema": SCHEMA, "error": "not-found"})
            return
        self._json(
            HTTPStatus.OK,
            collect_proof(
                self.server.state_dir,
                policy_path=self.server.policy_path,
                receipt_path=self.server.receipt_path,
            ),
        )

    def do_POST(self) -> None:  # noqa: N802
        self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"schema": SCHEMA, "error": "read-only"})


def _owned_pid(pid_path: Path) -> int | None:
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
        cmdline = _cmdline(pid)
    except (OSError, ValueError):
        return None
    return pid if pid > 1 and "aurum_proof_server.py" in cmdline else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Hopper read-only Echo proof server")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    policy = _json_file(args.policy)
    install = _json_file(args.receipt)
    authorized, reason = _authorized(policy, install)
    if not authorized:
        print(json.dumps({"schema": SCHEMA, "status": "refused", "reason": reason}, sort_keys=True))
        return 1
    if args.host not in {"0.0.0.0", "127.0.0.1", "::"}:
        print(json.dumps({"schema": SCHEMA, "status": "refused", "reason": "bind-host-not-allowed"}, sort_keys=True))
        return 1
    if not 1024 <= args.port <= 65535:
        print(json.dumps({"schema": SCHEMA, "status": "refused", "reason": "port-out-of-range"}, sort_keys=True))
        return 1

    args.run_dir.mkdir(parents=True, exist_ok=True)
    pid_path = args.run_dir / "hopper-proof.pid"
    existing = _owned_pid(pid_path)
    if existing:
        print(json.dumps({"schema": SCHEMA, "status": "already-running", "pid": existing}, sort_keys=True))
        return 0

    server = ProofServer((args.host, args.port), args.state_dir, args.policy, args.receipt)
    pid_path.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "schema": SCHEMA,
                "status": "running",
                "pid": os.getpid(),
                "host": args.host,
                "port": server.server_address[1],
                "read_only": True,
                "host_actuation": False,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        try:
            if pid_path.read_text(encoding="utf-8").strip() == str(os.getpid()):
                pid_path.unlink(missing_ok=True)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
