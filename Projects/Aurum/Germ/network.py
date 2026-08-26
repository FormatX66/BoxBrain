#!/usr/bin/env python3
"""Minimal wired/Wi-Fi onboarding for the Aurum Tiny Seed.

The module prefers NetworkManager/nmcli because it provides one small bounded
surface for wired DHCP and interactive Wi-Fi. Secrets are passed directly to
nmcli and are never written by this module.
"""
from __future__ import annotations

import ipaddress
import json
import os
import socket
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPOSITORY_HOST = "github.com"
REPOSITORY_URL = "https://github.com/FormatX66/BoxBrain.git"
REPOSITORY_REF = "refs/heads/main"


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


def _networkmanager_connected() -> bool:
    nmcli = shutil.which("nmcli")
    if not nmcli:
        return False
    result = _run([nmcli, "-t", "-f", "STATE", "general"], timeout=10, check=False)
    # NetworkManager's wording varies by version and can report site/local
    # connectivity even when the exact Aurum repository path is usable. Treat
    # any connected state as a link hint; DNS, TLS and git still have to prove
    # the real sync route below.
    return result.returncode == 0 and result.stdout.strip().lower().startswith("connected")


def _repository_addresses() -> list[str]:
    """Resolve the allowlisted genetics host through the system resolver."""
    try:
        records = socket.getaddrinfo(REPOSITORY_HOST, 443, type=socket.SOCK_STREAM)
    except OSError:
        return []
    addresses: list[str] = []
    for _family, _socktype, _proto, _canonname, sockaddr in records:
        value = str(sockaddr[0]) if sockaddr else ""
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            continue
        if not address.is_unspecified and value not in addresses:
            addresses.append(value)
    return addresses


def _repository_tcp_ready(addresses: list[str]) -> bool:
    """Prove a route to the HTTPS endpoint without trusting link state alone."""
    for address in addresses[:4]:
        try:
            with socket.create_connection((address, 443), timeout=4):
                return True
        except OSError:
            continue
    return False


def _repository_https_ready() -> bool:
    """Prove the TLS/HTTP path used before asking git to synchronize."""
    request = urllib.request.Request(
        "https://github.com/FormatX66/BoxBrain",
        method="HEAD",
        headers={"User-Agent": "Aurum-TinySeed/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return 200 <= int(response.status) < 400
    except (OSError, urllib.error.URLError, ValueError):
        return False


def _repository_sync_ready() -> bool:
    """Exercise the exact public git path Tiny Seed uses for current genetics."""
    git = shutil.which("git")
    if not git:
        return False
    result = _run(
        [git, "ls-remote", "--exit-code", REPOSITORY_URL, REPOSITORY_REF],
        timeout=20,
        check=False,
    )
    return result.returncode == 0 and REPOSITORY_REF in result.stdout


def failure_reason(observed: dict[str, Any]) -> str:
    if not observed.get("link_connected"):
        return "no connected Ethernet or Wi-Fi link"
    if not observed.get("resolver_ready"):
        return "the link is up but DNS resolution is unavailable"
    if not observed.get("repository_tcp_443"):
        return "DNS works but GitHub TCP/443 is unreachable"
    if not observed.get("repository_https"):
        return "TCP/443 works but the trusted HTTPS path is unavailable"
    if not observed.get("repository_sync"):
        return "HTTPS works but the exact BoxBrain git sync probe failed"
    return "network state is still settling"


def connectivity() -> dict[str, Any]:
    """Return end-to-end readiness for fetching Aurum's allowlisted genetics."""
    link_connected = _networkmanager_connected()
    addresses = _repository_addresses() if link_connected else []
    repository_tcp_443 = _repository_tcp_ready(addresses) if addresses else False
    repository_https = _repository_https_ready() if repository_tcp_443 else False
    repository_sync = _repository_sync_ready() if repository_https else False
    return {
        "link_connected": link_connected,
        "resolver_ready": bool(addresses),
        "repository_tcp_443": repository_tcp_443,
        "repository_https": repository_https,
        "repository_sync": repository_sync,
        "online": bool(link_connected and addresses and repository_tcp_443 and repository_https and repository_sync),
    }


def repair() -> dict[str, Any]:
    """Run bounded, reversible repairs for the live network/sync substrate."""
    actions: list[dict[str, Any]] = []

    def attempt(args: list[str], timeout: int = 20) -> None:
        executable = shutil.which(args[0])
        if not executable:
            actions.append({"command": args[0], "ok": False, "reason": "unavailable"})
            return
        try:
            result = _run([executable, *args[1:]], timeout=timeout, check=False)
            actions.append({"command": " ".join(args), "ok": result.returncode == 0})
        except NetworkError as exc:
            actions.append({"command": " ".join(args), "ok": False, "reason": str(exc)[:200]})

    attempt(["rfkill", "unblock", "wifi"], timeout=10)
    attempt(["nmcli", "networking", "on"], timeout=10)
    attempt(["nmcli", "radio", "wifi", "on"], timeout=10)
    attempt(["nmcli", "connection", "reload"], timeout=10)
    attempt(["systemctl", "restart", "systemd-resolved.service"], timeout=20)

    resolver_target = Path("/run/systemd/resolve/stub-resolv.conf")
    resolver_link = Path("/etc/resolv.conf")
    if resolver_target.exists():
        try:
            if resolver_link.is_symlink() and os.readlink(resolver_link) == str(resolver_target):
                actions.append({"command": "restore-resolver-link", "ok": True, "changed": False})
            else:
                resolver_link.unlink(missing_ok=True)
                resolver_link.symlink_to(resolver_target)
                actions.append({"command": "restore-resolver-link", "ok": True, "changed": True})
        except OSError as exc:
            actions.append({"command": "restore-resolver-link", "ok": False, "reason": str(exc)[:200]})

    try:
        observed = connectivity()
    except NetworkError as exc:
        observed = {
            "link_connected": False,
            "resolver_ready": False,
            "repository_tcp_443": False,
            "repository_https": False,
            "repository_sync": False,
            "online": False,
        }
        actions.append({"command": "connectivity-proof", "ok": False, "reason": str(exc)[:200]})
    return {
        "schema": "aurum-tinyseed-network-repair-v1",
        "actions": actions,
        "connectivity": observed,
        "reason": None if observed["online"] else failure_reason(observed),
    }


def online() -> bool:
    return bool(connectivity()["online"])


def wait_online(timeout: float = 20.0, interval: float = 0.5) -> bool:
    """Allow NetworkManager's connectivity state to settle after association."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if online():
            return True
        time.sleep(interval)
    return online()


def status() -> dict[str, Any]:
    nmcli = _nmcli()
    result = _run([nmcli, "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"], timeout=10)
    devices = []
    for line in result.stdout.splitlines():
        parts = line.split(":", 3)
        if len(parts) == 4:
            devices.append({"device": parts[0], "type": parts[1], "state": parts[2], "connection": parts[3]})
    return {"schema": "aurum-tinyseed-network-v1", **connectivity(), "devices": devices}


def wifi_scan() -> list[dict[str, Any]]:
    nmcli = _nmcli()
    _run([nmcli, "radio", "wifi", "on"], timeout=10, check=False)
    result = _run([nmcli, "-t", "--escape", "no", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes"], timeout=30)
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
    args = [nmcli, "--wait", "45", "device", "wifi", "connect", ssid]
    if password:
        args.extend(["password", password])
    result = _run(args, timeout=45)
    observed = connectivity()
    return {
        "status": "connected-and-sync-ready" if observed["online"] else "associated-sync-not-ready",
        "ssid": ssid,
        "detail": result.stdout.strip()[-500:],
        "connectivity": observed,
        "reason": None if observed["online"] else failure_reason(observed),
    }


def main() -> int:
    print(json.dumps(status(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
