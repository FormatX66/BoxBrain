#!/usr/bin/env python3
"""OpenSSH forced-command adapter for Hopper's restricted remote identity."""
from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time

SCHEMA = "aurum.remote-command.v1"
MAX_TUNNEL_SECONDS = 4 * 60 * 60
BROKER = "/opt/aurum/aurum_remote_control.py"
PYTHON = "/usr/bin/python3"
SUDO = "/usr/bin/sudo"
EXACT_COMMANDS = frozenset({"status", "seed-sync", "desktop-start", "desktop-stop", "desktop-tunnel"})


def _broker(action: str) -> int:
    completed = subprocess.run(
        [SUDO, "-n", PYTHON, BROKER, action],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=sys.stdout,
        stderr=sys.stderr,
        timeout=1200 if action == "seed-sync" else 60,
    )
    return int(completed.returncode)


def _tunnel() -> int:
    if _broker("desktop-start") != 0:
        return 1
    print(json.dumps({
        "schema": SCHEMA,
        "status": "ready",
        "transport": "vnc-over-ssh-loopback-tunnel",
        "remote_target": "127.0.0.1:6080",
        "viewer_path": "/vnc.html",
        "raw_shell": False,
        "max_session_seconds": MAX_TUNNEL_SECONDS,
    }, sort_keys=True), flush=True)
    deadline = time.monotonic() + MAX_TUNNEL_SECONDS
    try:
        while time.monotonic() < deadline:
            ready, _write, _error = select.select([sys.stdin], [], [], 1.0)
            if ready and sys.stdin.buffer.read(1) == b"":
                break
    finally:
        _broker("desktop-stop")
    return 0


def main() -> int:
    command = " ".join(os.environ.get("SSH_ORIGINAL_COMMAND", "").strip().split())
    if command not in EXACT_COMMANDS:
        print(json.dumps({
            "schema": SCHEMA,
            "status": "refused",
            "reason": "named-command-required",
            "allowed": sorted(EXACT_COMMANDS),
            "raw_shell": False,
        }, sort_keys=True))
        return 64
    if command == "desktop-tunnel":
        return _tunnel()
    return _broker(command)


if __name__ == "__main__":
    raise SystemExit(main())
