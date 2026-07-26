"""Read-only system telemetry for BoxBrain."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from typing import Any


def _read_text(path: str, default: str = "unavailable") -> str:
    try:
        return Path(path).read_text(encoding="utf-8").replace("\x00", "").strip()
    except (OSError, UnicodeError):
        return default


def _memory() -> dict[str, int | None]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            values[key] = int(raw.strip().split()[0]) * 1024
    except (OSError, ValueError):
        return {"total_bytes": None, "used_bytes": None, "available_bytes": None}

    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    used = total - available if total is not None and available is not None else None
    return {"total_bytes": total, "used_bytes": used, "available_bytes": available}


def _temperature_c() -> float | None:
    raw = _read_text("/sys/class/thermal/thermal_zone0/temp", "")
    try:
        return round(float(raw) / 1000.0, 1)
    except ValueError:
        return None


def _run_json(command: list[str]) -> Any:
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return []


def _network() -> dict[str, Any]:
    interfaces: list[dict[str, Any]] = []
    for item in _run_json(["ip", "-json", "-4", "address", "show"]):
        addresses = [
            address.get("local")
            for address in item.get("addr_info", [])
            if address.get("family") == "inet" and address.get("local")
        ]
        interfaces.append(
            {
                "name": item.get("ifname", "unknown"),
                "state": item.get("operstate", "UNKNOWN"),
                "addresses": addresses,
            }
        )

    default_route = None
    routes = _run_json(["ip", "-json", "-4", "route", "show", "default"])
    if routes:
        route = routes[0]
        default_route = {
            "gateway": route.get("gateway"),
            "interface": route.get("dev"),
        }

    return {"interfaces": interfaces, "default_route": default_route}


def collect_status(started_monotonic: float) -> dict[str, Any]:
    try:
        disk = shutil.disk_usage("/")
        storage: dict[str, int | None] = {
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "free_bytes": disk.free,
        }
    except OSError:
        storage = {"total_bytes": None, "used_bytes": None, "free_bytes": None}

    try:
        load = [round(value, 2) for value in os.getloadavg()]
    except (AttributeError, OSError):
        load = []

    return {
        "status": "ok",
        "hostname": socket.gethostname(),
        "model": _read_text("/proc/device-tree/model"),
        "kernel": os.uname().release if hasattr(os, "uname") else "unavailable",
        "architecture": os.uname().machine if hasattr(os, "uname") else "unavailable",
        "service_uptime_seconds": round(time.monotonic() - started_monotonic),
        "system_uptime_seconds": _system_uptime(),
        "load_average": load,
        "temperature_c": _temperature_c(),
        "memory": _memory(),
        "storage": storage,
        "network": _network(),
        "state_directory": os.environ.get("BOXBRAIN_STATE_DIR", "/var/lib/boxbrain"),
    }


def _system_uptime() -> int | None:
    raw = _read_text("/proc/uptime", "")
    try:
        return round(float(raw.split()[0]))
    except (ValueError, IndexError):
        return None
