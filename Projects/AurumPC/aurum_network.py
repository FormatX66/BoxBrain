#!/usr/bin/env python3
"""Bounded Wi-Fi bring-up for the Aurum PC live seed.

Aurum owns the operator flow; Linux networking tools are used only as the
hardware compatibility substrate.  Wi-Fi credentials are converted to a
wpa_supplicant configuration with the plaintext comment removed and are kept
under Aurum's state directory with mode 0600.  This module never writes an
internal disk directly.
"""
from __future__ import annotations

import getpass
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

STATE_DIR = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
SAVED_WIFI = STATE_DIR / "wifi.conf"
RUN_DIR = Path("/run/aurum")


class NetworkError(RuntimeError):
    pass


def _run(arguments: list[str], *, input_text: str | None = None, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            arguments,
            input=input_text,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise NetworkError(f"network operation failed to start: {exc}") from exc


def _command(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise NetworkError(f"required Wi-Fi helper is unavailable: {name}")
    return path


def wireless_interfaces(sys_root: Path = Path("/sys")) -> list[str]:
    interfaces: list[str] = []
    root = sys_root / "class" / "net"
    try:
        entries = sorted(root.iterdir(), key=lambda path: path.name)
    except OSError:
        return []
    for entry in entries:
        if (entry / "wireless").exists() or entry.name.startswith("wl"):
            interfaces.append(entry.name)
    return interfaces


def _addresses(interface: str | None = None) -> list[str]:
    ip = shutil.which("ip")
    if not ip:
        return []
    arguments = [ip, "-j", "address", "show"]
    if interface:
        arguments.extend(["dev", interface])
    result = _run(arguments, timeout=10)
    if result.returncode != 0:
        return []
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    addresses: list[str] = []
    for item in payload:
        name = item.get("ifname")
        for address in item.get("addr_info") or []:
            local = address.get("local")
            if local and not str(local).startswith("127.") and local != "::1":
                addresses.append(f"{name}:{local}")
    return addresses


def network_status(interface: str | None = None) -> dict[str, Any]:
    ip = shutil.which("ip")
    route = ""
    default_routes: list[str] = []
    if ip:
        route_result = _run([ip, "route", "show", "default"], timeout=10)
        default_routes = [line.strip() for line in route_result.stdout.splitlines() if line.strip()]
        route_probe = _run([ip, "route", "get", "1.1.1.1"], timeout=10)
        if route_probe.returncode == 0:
            route = route_probe.stdout.strip().splitlines()[0] if route_probe.stdout.strip() else ""

    dns_ok = False
    try:
        socket.getaddrinfo("github.com", 443, type=socket.SOCK_STREAM)
        dns_ok = True
    except OSError:
        pass

    github_tcp = False
    if dns_ok and route:
        try:
            with socket.create_connection(("github.com", 443), timeout=4):
                github_tcp = True
        except OSError:
            pass

    addresses = _addresses(interface)
    return {
        "wireless_interfaces": wireless_interfaces(),
        "interface": interface,
        "addresses": addresses,
        "default_routes": default_routes,
        "route_probe": route,
        "dns_github": dns_ok,
        "github_tcp_443": github_tcp,
        "online": bool(addresses and route and dns_ok and github_tcp),
    }


def scan_networks(interface: str | None = None) -> dict[str, Any]:
    interfaces = wireless_interfaces()
    selected = interface or (interfaces[0] if interfaces else None)
    if not selected:
        return {"status": "no-wifi-interface", "interface": None, "ssids": []}

    rfkill = shutil.which("rfkill")
    if rfkill:
        _run([rfkill, "unblock", "wifi"], timeout=10)
    ip = _command("ip")
    _run([ip, "link", "set", "dev", selected, "up"], timeout=10)
    iw = _command("iw")
    result = _run([iw, "dev", selected, "scan"], timeout=20)
    ssids: list[str] = []
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if not stripped.startswith("SSID:"):
                continue
            ssid = stripped.split(":", 1)[1].strip()
            if ssid and ssid not in ssids:
                ssids.append(ssid)
    return {
        "status": "ready" if result.returncode == 0 else "scan-failed",
        "interface": selected,
        "ssids": ssids,
        "detail": "" if result.returncode == 0 else result.stdout.strip()[-800:],
    }


def _escaped_ssid(ssid: str) -> str:
    return ssid.replace("\\", "\\\\").replace('"', '\\"')


def _make_config(ssid: str, password: str) -> str:
    if not ssid or len(ssid.encode("utf-8")) > 32:
        raise NetworkError("Wi-Fi SSID must contain 1-32 bytes")
    if password:
        helper = _command("wpa_passphrase")
        result = _run([helper, ssid], input_text=password + "\n", timeout=10)
        if result.returncode != 0:
            raise NetworkError(result.stdout.strip()[-800:] or "wpa_passphrase rejected the credentials")
        lines = [line for line in result.stdout.splitlines() if not line.lstrip().startswith("#psk=")]
        config = "\n".join(lines).strip() + "\n"
        config = config.replace("network={\n", "network={\n\tscan_ssid=1\n", 1)
    else:
        config = (
            "network={\n"
            f'\tssid="{_escaped_ssid(ssid)}"\n'
            "\tscan_ssid=1\n"
            "\tkey_mgmt=NONE\n"
            "}\n"
        )
    return "ctrl_interface=/run/wpa_supplicant\nupdate_config=0\n" + config


def _write_saved_config(config: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = SAVED_WIFI.with_name(f".{SAVED_WIFI.name}.{os.getpid()}.tmp")
    temporary.write_text(config, encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, SAVED_WIFI)


def _stop_owned_supplicant(interface: str) -> None:
    pid_path = RUN_DIR / f"wpa-{interface}.pid"
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
    except OSError:
        pid_path.unlink(missing_ok=True)
        return
    if "wpa_supplicant" not in cmdline or interface not in cmdline:
        raise NetworkError("refusing to terminate an unrecognized process from the Wi-Fi pid file")
    try:
        os.kill(pid, 15)
    except ProcessLookupError:
        pass
    pid_path.unlink(missing_ok=True)


def connect_saved(interface: str | None = None, *, timeout_seconds: int = 50) -> dict[str, Any]:
    interfaces = wireless_interfaces()
    selected = interface or (interfaces[0] if interfaces else None)
    if not selected:
        return {"status": "no-wifi-interface", **network_status()}
    if not SAVED_WIFI.is_file():
        return {"status": "credentials-required", **network_status(selected)}

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    rfkill = shutil.which("rfkill")
    if rfkill:
        _run([rfkill, "unblock", "wifi"], timeout=10)
    ip = _command("ip")
    _run([ip, "link", "set", "dev", selected, "up"], timeout=10)
    _stop_owned_supplicant(selected)

    supplicant = _command("wpa_supplicant")
    pid_path = RUN_DIR / f"wpa-{selected}.pid"
    result = _run(
        [supplicant, "-B", "-D", "nl80211,wext", "-i", selected, "-c", str(SAVED_WIFI), "-P", str(pid_path)],
        timeout=15,
    )
    if result.returncode != 0:
        return {"status": "association-start-failed", "detail": result.stdout.strip()[-800:], **network_status(selected)}

    networkctl = shutil.which("networkctl")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if networkctl:
            _run([networkctl, "reconfigure", selected], timeout=10)
        status = network_status(selected)
        if status["online"]:
            return {"status": "online", **status}
        time.sleep(2)
    return {"status": "wifi-connected-no-internet", **network_status(selected)}


def interactive_wifi_setup(interface: str | None = None) -> dict[str, Any]:
    scan = scan_networks(interface)
    selected = scan.get("interface")
    if not selected:
        return scan
    ssids = scan.get("ssids") or []
    print(f"AURUM_WIFI_SCAN interface={selected} networks={len(ssids)}", flush=True)
    for index, ssid in enumerate(ssids[:20], start=1):
        print(f"  {index:2d}. {ssid}", flush=True)
    try:
        ssid = input("Wi-Fi SSID (blank keeps Aurum offline): ").strip()
    except (EOFError, KeyboardInterrupt):
        return {"status": "credentials-skipped", **network_status(selected)}
    if not ssid:
        return {"status": "credentials-skipped", **network_status(selected)}
    try:
        password = getpass.getpass("Wi-Fi password (blank for open network): ")
    except (EOFError, KeyboardInterrupt):
        return {"status": "credentials-skipped", **network_status(selected)}
    config = _make_config(ssid, password)
    password = ""
    _write_saved_config(config)
    return connect_saved(selected)


def ensure_online(*, interactive: bool) -> dict[str, Any]:
    current = network_status()
    if current["online"]:
        return {"status": "already-online", **current}
    interfaces = wireless_interfaces()
    if not interfaces:
        return {"status": "no-wifi-interface", **current}
    if SAVED_WIFI.is_file():
        saved = connect_saved(interfaces[0])
        if saved.get("online") or not interactive:
            return saved
    if not interactive:
        return {"status": "credentials-required", **network_status(interfaces[0])}
    return interactive_wifi_setup(interfaces[0])
