#!/usr/bin/env python3
"""Minimal wired/Wi-Fi onboarding for the Aurum Tiny Seed.

The module prefers NetworkManager/nmcli because it provides one small bounded
surface for wired DHCP and interactive Wi-Fi. Secrets are passed directly to
nmcli and are never written by this module.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any


class NetworkError(RuntimeError):
    pass


def _run(args: list[str], *, timeout: int = 30, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise NetworkError(f"network command failed to start: {exc}") from exc
    if check and result.returncode != 0:
        raise NetworkError((result.stdout or "network command failed").strip()[-1000:])
    return result


def _nmcli() -> str:
    path = shutil.which("nmcli")
    if not path:
        raise NetworkError("NetworkManager/nmcli is unavailable")
    return path


def online() -> bool:
    nmcli = shutil.which("nmcli")
    if nmcli:
        result = _run([nmcli, "-t", "-f", "STATE", "general"], timeout=10, check=False)
        return result.returncode == 0 and result.stdout.strip().lower() in {"connected", "connected (global)", "connected (site)"}
    return False


def status() -> dict[str, Any]:
    nmcli = _nmcli()
    result = _run([nmcli, "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"], timeout=10)
    devices = []
    for line in result.stdout.splitlines():
        parts = line.split(":", 3)
        if len(parts) == 4:
            devices.append({"device": parts[0], "type": parts[1], "state": parts[2], "connection": parts[3]})
    return {"schema": "aurum-tinyseed-network-v1", "online": online(), "devices": devices}


def wifi_scan() -> list[dict[str, Any]]:
    nmcli = _nmcli()
    _run([nmcli, "radio", "wifi", "on"], timeout=10, check=False)
    result = _run([nmcli, "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes"], timeout=30)
    best: dict[str, dict[str, Any]] = {}
    for line in result.stdout.splitlines():
        parts = line.rsplit(":", 2)
        if len(parts) != 3:
            continue
        ssid, signal, security = parts
        if not ssid:
            continue
        try:
            strength = int(signal)
        except ValueError:
            strength = 0
        candidate = {"ssid": ssid, "signal": strength, "security": security or "open"}
        if ssid not in best or strength > int(best[ssid]["signal"]):
            best[ssid] = candidate
    return sorted(best.values(), key=lambda item: (-int(item["signal"]), str(item["ssid"]).lower()))


def wifi_connect(ssid: str, password: str | None = None) -> dict[str, Any]:
    if not ssid or len(ssid) > 64:
        raise NetworkError("Wi-Fi SSID is invalid")
    nmcli = _nmcli()
    args = [nmcli, "device", "wifi", "connect", ssid]
    if password:
        args.extend(["password", password])
    result = _run(args, timeout=45)
    return {"status": "connected" if online() else "connection-command-finished", "ssid": ssid, "detail": result.stdout.strip()[-500:]}


def main() -> int:
    print(json.dumps(status(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
