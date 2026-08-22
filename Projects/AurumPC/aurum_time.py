#!/usr/bin/env python3
"""Bounded network time synchronization and evidence for Aurum PC.

Aurum does not present local wall-clock time as authoritative unless the host
reports NTP synchronization.  This module asks systemd-timesyncd to synchronize,
reads the active time-server identity when available, and returns an evidence
object that GUI/runtime consumers can display without inventing clock state.
"""
from __future__ import annotations

import datetime as dt
import shutil
import subprocess
import time
from typing import Any


def _run(arguments: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )


def _property(name: str) -> str:
    timedatectl = shutil.which("timedatectl")
    if not timedatectl:
        return ""
    try:
        result = _run([timedatectl, "show", f"--property={name}", "--value"], timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _ntp_synchronized() -> bool:
    return _property("NTPSynchronized").lower() == "yes"


def _timesync_value(name: str) -> str:
    timedatectl = shutil.which("timedatectl")
    if not timedatectl:
        return ""
    try:
        result = _run([timedatectl, "show-timesync", f"--property={name}", "--value"], timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _server_identity() -> tuple[str | None, str | None]:
    name = _timesync_value("ServerName") or None
    address = _timesync_value("ServerAddress") or None
    if name or address:
        return name, address

    timedatectl = shutil.which("timedatectl")
    if not timedatectl:
        return None, None
    try:
        result = _run([timedatectl, "timesync-status"], timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None, None
    if result.returncode != 0:
        return None, None
    parsed_name = None
    parsed_address = None
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if line.lower().startswith("server:"):
            value = line.split(":", 1)[1].strip()
            if "(" in value and value.endswith(")"):
                parsed_name = value.split("(", 1)[0].strip() or None
                parsed_address = value.rsplit("(", 1)[1][:-1].strip() or None
            elif value:
                parsed_name = value
    return parsed_name, parsed_address


def time_status() -> dict[str, Any]:
    """Return current clock evidence without claiming authority when unsynchronized."""
    epoch = time.time()
    synchronized = _ntp_synchronized()
    server_name, server_address = _server_identity() if synchronized else (None, None)
    timezone = _property("Timezone") or None
    local = dt.datetime.fromtimestamp(epoch).astimezone()
    utc = dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc)
    return {
        "schema": "aurum.time-status.v1",
        "epoch": epoch,
        "local_iso": local.isoformat(timespec="seconds"),
        "utc_iso": utc.isoformat(timespec="seconds"),
        "timezone": timezone or str(local.tzinfo or "local"),
        "ntp_enabled": _property("NTP").lower() == "yes",
        "synchronized": synchronized,
        "source": "ntp-server" if synchronized else "local-unsynchronized",
        "server_name": server_name,
        "server_address": server_address,
        "authoritative": synchronized,
    }


def synchronize_clock(*, timeout_seconds: int = 35) -> dict[str, Any]:
    """Ask systemd-timesyncd for network time and return the resulting evidence."""
    before_epoch = int(time.time())
    timedatectl = shutil.which("timedatectl")
    systemctl = shutil.which("systemctl")
    if not timedatectl or not systemctl:
        status = time_status()
        return {
            "status": "helper-unavailable",
            "before_epoch": before_epoch,
            "after_epoch": int(time.time()),
            **status,
        }

    try:
        _run([timedatectl, "set-ntp", "true"], timeout=5)
        _run([systemctl, "start", "systemd-timesyncd.service"], timeout=10)
    except (OSError, subprocess.SubprocessError):
        status = time_status()
        return {
            "status": "start-failed",
            "before_epoch": before_epoch,
            "after_epoch": int(time.time()),
            **status,
        }

    deadline = time.monotonic() + max(0, timeout_seconds)
    while time.monotonic() < deadline:
        if _ntp_synchronized():
            status = time_status()
            return {
                "status": "synchronized",
                "before_epoch": before_epoch,
                "after_epoch": int(time.time()),
                **status,
            }
        time.sleep(1)

    status = time_status()
    return {
        "status": "timeout",
        "before_epoch": before_epoch,
        "after_epoch": int(time.time()),
        **status,
    }
