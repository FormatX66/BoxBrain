#!/usr/bin/env python3
"""Thin, graphical NetworkManager adapter for Aurum PC.

NetworkManager is the only connection owner. Aurum never starts, stops, or
signals wpa_supplicant and never runs a second DHCP client. The adapter only
creates root-only NetworkManager keyfiles, asks NetworkManager to activate
them, verifies the selected wireless path, and restores the prior profile when
a candidate fails. No credential is placed in argv, JSON, logs, or receipts.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from functools import wraps
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any


STATE_DIR = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
RUN_DIR = Path(os.environ.get("AURUM_RUN_DIR", "/run/aurum"))
SYSTEM_CONNECTIONS = Path(
    os.environ.get("AURUM_NM_SYSTEM_CONNECTIONS", "/etc/NetworkManager/system-connections")
)
RUNTIME_CONNECTIONS = Path(
    os.environ.get("AURUM_NM_RUNTIME_CONNECTIONS", "/run/NetworkManager/system-connections")
)
PROFILE_PREFIX = "aurum-wifi-"
MANAGER = "NetworkManager"
WIFI_TYPES = {"wifi", "802-11-wireless"}


class NetworkError(RuntimeError):
    pass


class NetworkBusy(NetworkError):
    pass


@contextmanager
def _operation_lock():
    """Serialize GUI, boot, recovery, and console requests across processes."""
    import fcntl

    RUN_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(
        RUN_DIR / "wifi-operation.lock",
        os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
        0o600,
    )
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise NetworkBusy("another Wi-Fi operation is active") from exc
        yield
    finally:
        os.close(fd)


def _serialized(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            with _operation_lock():
                return function(*args, **kwargs)
        except NetworkBusy:
            return {"status": "wifi-operation-busy", "online": False, "manager": MANAGER}
        except (NetworkError, OSError) as exc:
            return {
                "status": "wifi-service-unavailable",
                "online": False,
                "manager": MANAGER,
                "error_type": type(exc).__name__,
            }

    return wrapped


def _run(
    arguments: list[str],
    *,
    input_text: str | None = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["LC_ALL"] = "C"
    try:
        return subprocess.run(
            arguments,
            input=input_text,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise NetworkError(f"NetworkManager request failed to start: {exc}") from exc


def _command(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise NetworkError(f"required network helper is unavailable: {name}")
    return path


def _nmcli(arguments: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return _run([_command("nmcli"), "--colors", "no", *arguments], timeout=timeout)


def _split_nmcli(line: str) -> list[str]:
    """Split nmcli terse output without losing escaped colons/backslashes."""
    values: list[str] = []
    current: list[str] = []
    escaped = False
    for character in line:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == ":":
            values.append("".join(current))
            current = []
        else:
            current.append(character)
    if escaped:
        current.append("\\")
    values.append("".join(current))
    return values


def _rows(fields: list[str], arguments: list[str], *, timeout: int = 10) -> list[dict[str, str]]:
    result = _nmcli(
        ["--terse", "--escape", "yes", "--fields", ",".join(fields), *arguments],
        timeout=timeout,
    )
    if result.returncode != 0:
        return []
    parsed: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        values = _split_nmcli(line)
        if len(values) == len(fields):
            parsed.append(dict(zip(fields, values, strict=True)))
    return parsed


def _manager_ready() -> bool:
    if not shutil.which("nmcli"):
        return False
    result = _nmcli(["--terse", "--fields", "RUNNING", "general"], timeout=3)
    return result.returncode == 0 and result.stdout.strip().lower() == "running"


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


def _wireless_driver(interface: str, sys_root: Path = Path("/sys")) -> str | None:
    try:
        return (sys_root / "class" / "net" / interface / "device" / "driver").resolve(
            strict=True
        ).name
    except OSError:
        return None


def _unbound_pci_wifi_count(sys_root: Path = Path("/sys")) -> int:
    count = 0
    root = sys_root / "bus" / "pci" / "devices"
    try:
        devices = list(root.iterdir())
    except OSError:
        return 0
    for device in devices:
        try:
            device_class = (device / "class").read_text(encoding="ascii").strip().lower()
        except OSError:
            continue
        if device_class.startswith("0x0280") and not (device / "driver").exists():
            count += 1
    return count


def _device_rows() -> list[dict[str, str]]:
    if not _manager_ready():
        return []
    return _rows(
        ["DEVICE", "TYPE", "STATE", "CONNECTION"],
        ["device", "status"],
        timeout=5,
    )


def wireless_hardware(sys_root: Path = Path("/sys")) -> dict[str, Any]:
    interfaces = wireless_interfaces(sys_root)
    managed = {row["DEVICE"]: row["STATE"] for row in _device_rows()}
    adapters = []
    for interface in interfaces:
        driver = _wireless_driver(interface, sys_root)
        adapters.append(
            {
                "interface": interface,
                "driver": driver,
                "driver_ready": driver is not None,
                "manager_state": managed.get(interface, "unavailable"),
            }
        )
    return {
        "adapters": adapters,
        "adapter_count": len(adapters),
        "unbound_pci_wifi_count": _unbound_pci_wifi_count(sys_root),
        "driver_ready": bool(adapters and all(item["driver_ready"] for item in adapters)),
    }


def _usable_ipv4(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
        return address.version == 4 and not (
            address.is_loopback
            or address.is_link_local
            or address.is_unspecified
            or address.is_multicast
        )
    except ValueError:
        return False


def _internet_probe(interface: str, source_ip: str) -> dict[str, Any]:
    # DNS and TCP run together in an owned child so resolver stalls are bounded.
    program = """import json, socket, sys
result = {'dns_github': False, 'github_tcp_443': False, 'probe_status': 'complete'}
try:
    addresses = socket.getaddrinfo('github.com', 443, socket.AF_INET, socket.SOCK_STREAM)
    result['dns_github'] = bool(addresses)
    for family, kind, protocol, _, target in addresses[:4]:
        try:
            with socket.socket(family, kind, protocol) as connection:
                connection.settimeout(1)
                connection.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, (sys.argv[1] + '\\0').encode())
                connection.bind((sys.argv[2], 0))
                connection.connect(target)
                result['github_tcp_443'] = True
                break
        except OSError:
            continue
except OSError:
    pass
print(json.dumps(result))
"""
    try:
        result = _run([sys.executable, "-c", program, interface, source_ip], timeout=5)
        payload = json.loads(result.stdout)
        if result.returncode == 0 and isinstance(payload, dict):
            return {
                key: payload.get(key)
                for key in ("dns_github", "github_tcp_443", "probe_status")
            }
    except (NetworkError, ValueError):
        pass
    return {
        "dns_github": False,
        "github_tcp_443": False,
        "probe_status": "timeout-or-unavailable",
    }


def _device_properties(interface: str) -> dict[str, list[str]]:
    result = _nmcli(
        [
            "--terse",
            "--escape",
            "yes",
            "--fields",
            "GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS,IP4.GATEWAY",
            "device",
            "show",
            interface,
        ],
        timeout=5,
    )
    if result.returncode != 0:
        return {}
    properties: dict[str, list[str]] = {}
    for line in result.stdout.splitlines():
        values = _split_nmcli(line)
        if len(values) != 2:
            continue
        key = values[0].split("[", 1)[0]
        properties.setdefault(key, []).append(values[1])
    return properties


def _active_connections() -> list[dict[str, str]]:
    return _rows(
        ["NAME", "UUID", "TYPE", "DEVICE"],
        ["connection", "show", "--active"],
        timeout=5,
    )


def _active_for(interface: str) -> dict[str, str] | None:
    return next(
        (row for row in _active_connections() if row.get("DEVICE") == interface),
        None,
    )


def _profile_ssid(profile_uuid: str) -> str | None:
    result = _nmcli(
        [
            "--escape",
            "yes",
            "--get-values",
            "802-11-wireless.ssid",
            "connection",
            "show",
            "uuid",
            profile_uuid,
        ],
        timeout=5,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return _split_nmcli(value)[0] if value else None


def _status_for(interface: str, rows: list[dict[str, str]]) -> dict[str, Any]:
    row = next((item for item in rows if item.get("DEVICE") == interface), {})
    properties = _device_properties(interface)
    state_value = next(iter(properties.get("GENERAL.STATE", [])), "0")
    match = re.match(r"(\d+)", state_value)
    state_code = int(match.group(1)) if match else 0
    connected = state_code == 100 or row.get("STATE") == "connected"
    addresses = [
        value.split("/", 1)[0]
        for value in properties.get("IP4.ADDRESS", [])
        if value
    ]
    active_ip = next((value for value in addresses if _usable_ipv4(value)), None)
    gateway = next((value for value in properties.get("IP4.GATEWAY", []) if value), None)
    active = _active_for(interface) if connected else None
    is_wifi = row.get("TYPE") in WIFI_TYPES or interface in wireless_interfaces()
    associated = bool(
        is_wifi and connected and active and active.get("TYPE") in WIFI_TYPES
    )
    profile_uuid = active.get("UUID") if active else None
    ssid = _profile_ssid(profile_uuid) if associated and profile_uuid else None
    probe = {"dns_github": False, "github_tcp_443": False, "probe_status": "not-run"}
    route_matches = bool(connected and active_ip and gateway)
    if route_matches:
        probe = _internet_probe(interface, active_ip)
    online = bool(
        route_matches and probe.get("dns_github") and probe.get("github_tcp_443")
    )
    if not connected:
        status = "wifi-disconnected" if is_wifi else "network-disconnected"
    elif is_wifi and not associated:
        status = "wifi-association-pending"
    elif not active_ip:
        status = "wifi-address-pending" if is_wifi else "network-address-pending"
    elif not gateway:
        status = "wifi-route-pending" if is_wifi else "network-route-pending"
    elif probe.get("probe_status") == "timeout-or-unavailable":
        status = "wifi-probe-unavailable" if is_wifi else "network-probe-unavailable"
    elif not probe.get("dns_github"):
        status = "wifi-dns-unavailable" if is_wifi else "network-dns-unavailable"
    elif not probe.get("github_tcp_443"):
        status = "wifi-internet-unreachable" if is_wifi else "network-internet-unreachable"
    else:
        status = "online"
    return {
        "status": status,
        "manager": MANAGER,
        "manager_ready": True,
        "exclusive_owner": True,
        "interface": interface,
        "connection_uuid": profile_uuid,
        "ip": active_ip,
        "addresses": [f"{interface}:{value}" for value in addresses],
        "gateway": gateway,
        "default_routes": [f"default via {gateway} dev {interface}"] if gateway else [],
        "route_probe": f"dev {interface} src {active_ip}" if active_ip else "",
        "route_matches_interface": route_matches,
        "associated": associated,
        "ssid": ssid,
        **probe,
        "online": online,
    }


def network_status(interface: str | None = None) -> dict[str, Any]:
    interfaces = wireless_interfaces()
    hardware = wireless_hardware()
    if not _manager_ready():
        status = (
            "wifi-driver-unavailable"
            if not interfaces and hardware["unbound_pci_wifi_count"]
            else "network-manager-unavailable"
        )
        return {
            "status": status,
            "manager": MANAGER,
            "manager_ready": False,
            "exclusive_owner": False,
            "wireless_interfaces": interfaces,
            "wireless_hardware": hardware,
            "interface": interface,
            "online": False,
        }
    rows = _device_rows()
    if interface:
        if not any(row.get("DEVICE") == interface for row in rows):
            return {
                "status": "network-interface-unavailable",
                "manager": MANAGER,
                "manager_ready": True,
                "exclusive_owner": True,
                "wireless_interfaces": interfaces,
                "wireless_hardware": hardware,
                "interface": interface,
                "online": False,
            }
        selected = interface
    else:
        connected = [row for row in rows if row.get("STATE") == "connected"]
        selected = next(
            (row["DEVICE"] for row in connected if row.get("TYPE") not in WIFI_TYPES),
            None,
        ) or next((row["DEVICE"] for row in connected), None)
        selected = selected or (interfaces[0] if interfaces else None)
    if not selected:
        return {
            "status": "no-network-interface",
            "manager": MANAGER,
            "manager_ready": True,
            "exclusive_owner": True,
            "wireless_interfaces": interfaces,
            "wireless_hardware": hardware,
            "interface": None,
            "online": False,
        }
    return {
        **_status_for(selected, rows),
        "wireless_interfaces": interfaces,
        "wireless_hardware": hardware,
    }


def _connection_state(interface: str) -> dict[str, Any]:
    status = network_status(interface)
    if interface not in status.get("wireless_interfaces", []):
        return {**status, "status": "no-wifi-interface", "online": False}
    return status


@_serialized
def scan_networks(interface: str | None = None) -> dict[str, Any]:
    interfaces = wireless_interfaces()
    selected = interface or (interfaces[0] if interfaces else None)
    if not selected or selected not in interfaces:
        return {
            "status": "no-wifi-interface",
            "manager": MANAGER,
            "interface": None,
            "ssids": [],
        }
    if not _manager_ready():
        return {
            "status": "network-manager-unavailable",
            "manager": MANAGER,
            "interface": selected,
            "ssids": [],
        }
    _nmcli(["radio", "wifi", "on"], timeout=5)
    managed = _nmcli(["device", "set", selected, "managed", "yes"], timeout=5)
    if managed.returncode != 0:
        return {
            "status": "wifi-manager-unavailable",
            "manager": MANAGER,
            "interface": selected,
            "ssids": [],
        }
    _nmcli(["--wait", "15", "device", "wifi", "rescan", "ifname", selected], timeout=20)
    rows = _rows(
        ["SSID", "SIGNAL", "SECURITY", "IN-USE"],
        ["device", "wifi", "list", "ifname", selected, "--rescan", "no"],
        timeout=20,
    )
    ssids: list[str] = []
    for row in rows:
        ssid = row.get("SSID", "")
        if ssid and ssid not in ssids:
            ssids.append(ssid)
    return {
        "status": "ready",
        "manager": MANAGER,
        "interface": selected,
        "ssids": ssids,
        "networks": [
            {
                "ssid": row.get("SSID"),
                "signal": int(row["SIGNAL"]) if row.get("SIGNAL", "").isdigit() else None,
                "secured": bool(row.get("SECURITY") and row.get("SECURITY") != "--"),
                "active": row.get("IN-USE") in {"yes", "*"},
            }
            for row in rows
            if row.get("SSID")
        ],
    }


def _keyfile_escape(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    leading = len(escaped) - len(escaped.lstrip(" "))
    trailing = len(escaped) - len(escaped.rstrip(" "))
    if leading:
        escaped = "\\s" * leading + escaped[leading:]
    if trailing:
        escaped = escaped[:-trailing] + "\\s" * trailing
    return escaped


def _validate_credentials(ssid: str, password: str) -> tuple[str, str] | None:
    normalized = ssid.strip()
    if not normalized or len(normalized.encode("utf-8")) > 32:
        return None
    if any(ord(character) < 32 for character in normalized):
        return None
    if password and not (
        8 <= len(password) <= 63 or re.fullmatch(r"[0-9a-fA-F]{64}", password)
    ):
        return None
    if any(character in "\0\n\r" for character in password):
        return None
    return normalized, password


def _profile_content(ssid: str, password: str, profile_uuid: str) -> str:
    sections = [
        "[connection]",
        "id=Aurum Wi-Fi",
        f"uuid={profile_uuid}",
        "type=wifi",
        "autoconnect=true",
        "autoconnect-priority=100",
        "",
        "[wifi]",
        "mode=infrastructure",
        f"ssid={_keyfile_escape(ssid)}",
        "hidden=true",
    ]
    if password:
        sections.extend(
            [
                "security=wifi-security",
                "",
                "[wifi-security]",
                "key-mgmt=wpa-psk",
                f"psk={_keyfile_escape(password)}",
                "psk-flags=0",
            ]
        )
    sections.extend(
        [
            "",
            "[ipv4]",
            "method=auto",
            "",
            "[ipv6]",
            "method=auto",
            "addr-gen-mode=stable-privacy",
            "",
        ]
    )
    return "\n".join(sections)


def _write_private(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            if hasattr(os, "fchmod"):
                os.fchmod(stream.fileno(), 0o600)
            else:
                os.chmod(temporary, 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        if hasattr(os, "O_DIRECTORY"):
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def _profile_uuid(path: Path) -> str | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("uuid="):
                value = line.split("=", 1)[1].strip()
                return str(uuid.UUID(value))
    except (OSError, UnicodeError, ValueError):
        return None
    return None


def _owned_profiles(*roots: Path) -> list[tuple[Path, str]]:
    profiles: list[tuple[Path, str]] = []
    for root in roots:
        try:
            candidates = sorted(root.glob(f"{PROFILE_PREFIX}*.nmconnection"))
        except OSError:
            continue
        for path in candidates:
            value = _profile_uuid(path)
            if value:
                profiles.append((path, value))
    return profiles


def _load_profile(path: Path) -> None:
    result = _nmcli(["connection", "load", str(path)], timeout=10)
    if result.returncode != 0:
        raise NetworkError("NetworkManager rejected the private Wi-Fi profile")


def _activate_profile(
    profile_uuid: str,
    interface: str,
    ssid: str,
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    result = _nmcli(
        [
            "--wait",
            str(max(5, min(timeout_seconds, 120))),
            "connection",
            "up",
            "uuid",
            profile_uuid,
            "ifname",
            interface,
        ],
        timeout=max(10, min(timeout_seconds, 120) + 5),
    )
    if result.returncode != 0:
        output = result.stdout.lower()
        if "secrets were required" in output or "password" in output or "encryption key" in output:
            reason = "wifi-credentials-rejected"
        elif "not found" in output or "no network" in output:
            reason = "wifi-network-not-found"
        else:
            reason = "wifi-association-failed"
        return {"status": reason, "online": False, "activated": False}
    deadline = time.monotonic() + max(0, timeout_seconds)
    status = {"status": "wifi-connection-unverified", "online": False}
    while True:
        status = _connection_state(interface)
        exact_profile = status.get("connection_uuid") == profile_uuid
        exact_ssid = status.get("ssid") == ssid
        if status.get("online") and status.get("associated") and exact_profile and exact_ssid:
            return {**status, "activated": True}
        if time.monotonic() >= deadline:
            break
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    if status.get("online"):
        status = {**status, "status": "wifi-network-mismatch", "online": False}
    return {**status, "activated": True}


def _remove_candidate(path: Path, profile_uuid: str) -> None:
    _nmcli(["--wait", "5", "connection", "down", "uuid", profile_uuid], timeout=8)
    _nmcli(["--wait", "5", "connection", "delete", "uuid", profile_uuid], timeout=8)
    path.unlink(missing_ok=True)
    _nmcli(["connection", "reload"], timeout=8)


def _restore_profile(profile_uuid: str | None, interface: str) -> dict[str, Any] | None:
    if not profile_uuid:
        return None
    result = _nmcli(
        ["--wait", "15", "connection", "up", "uuid", profile_uuid, "ifname", interface],
        timeout=20,
    )
    state = _connection_state(interface)
    return {
        "status": state.get("status") if result.returncode == 0 else "recovery-not-verified",
        "online": bool(result.returncode == 0 and state.get("online")),
    }


def _commit_profile(candidate: Path, profile_uuid: str) -> Path:
    persistent = SYSTEM_CONNECTIONS / f"{PROFILE_PREFIX}{profile_uuid}.nmconnection"
    _write_private(persistent, candidate.read_text(encoding="utf-8"))
    try:
        _load_profile(persistent)
    except Exception:
        persistent.unlink(missing_ok=True)
        raise
    candidate.unlink(missing_ok=True)
    return persistent


def _remove_superseded_profiles(keep_uuid: str) -> bool:
    clean = True
    for path, profile_uuid in _owned_profiles(SYSTEM_CONNECTIONS, RUNTIME_CONNECTIONS):
        if profile_uuid == keep_uuid:
            continue
        result = _nmcli(
            ["--wait", "5", "connection", "delete", "uuid", profile_uuid],
            timeout=8,
        )
        if result.returncode == 0:
            path.unlink(missing_ok=True)
        else:
            clean = False
    _nmcli(["connection", "reload"], timeout=8)
    return clean


@_serialized
def connect_wifi(
    ssid: str,
    password: str,
    interface: str | None = None,
    *,
    timeout_seconds: int = 50,
) -> dict[str, Any]:
    """Connect from the GUI without exposing credentials outside a keyfile."""
    validated = _validate_credentials(ssid, password)
    if validated is None:
        return {
            "status": "invalid-wifi-credentials",
            "online": False,
            "saved": False,
            "manager": MANAGER,
        }
    normalized_ssid, password_value = validated
    interfaces = wireless_interfaces()
    selected = interface or (interfaces[0] if interfaces else None)
    if not selected or selected not in interfaces:
        return {
            "status": "no-wifi-interface",
            "online": False,
            "saved": False,
            "manager": MANAGER,
            **network_status(),
        }
    if not _manager_ready():
        return {
            "status": "network-manager-unavailable",
            "online": False,
            "saved": False,
            "manager": MANAGER,
            "interface": selected,
        }
    active = _active_for(selected)
    previous_uuid = active.get("UUID") if active else None
    profile_uuid = str(uuid.uuid4())
    candidate = RUNTIME_CONNECTIONS / f"{PROFILE_PREFIX}{profile_uuid}.nmconnection"
    content = _profile_content(normalized_ssid, password_value, profile_uuid)
    password_value = ""
    _write_private(candidate, content)
    content = ""
    try:
        _load_profile(candidate)
        result = _activate_profile(
            profile_uuid,
            selected,
            normalized_ssid,
            timeout_seconds=timeout_seconds,
        )
        verified = bool(
            result.get("online")
            and result.get("associated")
            and result.get("ssid") == normalized_ssid
            and result.get("connection_uuid") == profile_uuid
        )
        if not verified:
            _remove_candidate(candidate, profile_uuid)
            recovery = _restore_profile(previous_uuid, selected)
            return {**result, "online": False, "saved": False, "recovery": recovery}
        persistent = _commit_profile(candidate, profile_uuid)
        cleanup_complete = _remove_superseded_profiles(profile_uuid)
        return {
            **result,
            "status": "online" if cleanup_complete else "online-cleanup-pending",
            "saved": True,
            "profile_persistent": persistent.is_file(),
            "legacy_profile_used": False,
        }
    except (NetworkError, OSError):
        try:
            _remove_candidate(candidate, profile_uuid)
        except (NetworkError, OSError):
            candidate.unlink(missing_ok=True)
        recovery = _restore_profile(previous_uuid, selected)
        return {
            "status": "wifi-service-unavailable",
            "online": False,
            "saved": False,
            "manager": MANAGER,
            "interface": selected,
            "recovery": recovery,
        }


@_serialized
def connect_saved(interface: str | None = None, *, timeout_seconds: int = 50) -> dict[str, Any]:
    interfaces = wireless_interfaces()
    selected = interface or (interfaces[0] if interfaces else None)
    if not selected or selected not in interfaces:
        return {"status": "no-wifi-interface", **network_status()}
    if not _manager_ready():
        return {
            "status": "network-manager-unavailable",
            "online": False,
            "manager": MANAGER,
            "interface": selected,
        }
    current = _connection_state(selected)
    if current.get("online") and current.get("associated"):
        return {"status": "already-online", **current}
    profiles = _owned_profiles(SYSTEM_CONNECTIONS)
    if not profiles:
        return {"status": "credentials-required", **current}
    path, profile_uuid = max(profiles, key=lambda item: item[0].stat().st_mtime_ns)
    ssid = _profile_ssid(profile_uuid)
    if not ssid:
        return {"status": "saved-profile-invalid", **current, "online": False}
    return _activate_profile(
        profile_uuid,
        selected,
        ssid,
        timeout_seconds=timeout_seconds,
    )


@_serialized
def disconnect_wifi(*, forget: bool = False) -> dict[str, Any]:
    interfaces = wireless_interfaces()
    selected = interfaces[0] if interfaces else None
    if not selected:
        return {"status": "no-wifi-interface", "online": False, "manager": MANAGER}
    if not _manager_ready():
        return {
            "status": "network-manager-unavailable",
            "online": False,
            "manager": MANAGER,
        }
    result = _nmcli(["--wait", "10", "device", "disconnect", selected], timeout=15)
    if result.returncode != 0:
        return {"status": "wifi-disconnect-failed", "online": False, "manager": MANAGER}
    if forget:
        for path, profile_uuid in _owned_profiles(SYSTEM_CONNECTIONS, RUNTIME_CONNECTIONS):
            _nmcli(
                ["--wait", "5", "connection", "delete", "uuid", profile_uuid],
                timeout=8,
            )
            path.unlink(missing_ok=True)
        _nmcli(["connection", "reload"], timeout=8)
    return {
        "status": "saved-network-forgotten" if forget else "disconnected",
        "online": False,
        "manager": MANAGER,
    }


def interactive_wifi_setup(interface: str | None = None) -> dict[str, Any]:
    """The recovery console routes operators to the graphical setup surface."""
    return {
        "status": "use-gui-wifi-setup",
        "online": False,
        "manager": MANAGER,
        "interface": interface,
    }


def ensure_online(*, interactive: bool) -> dict[str, Any]:
    current = network_status()
    if current.get("online"):
        return {"status": "already-online", **current}
    interfaces = wireless_interfaces()
    if not interfaces:
        return {"status": "no-wifi-interface", **current}
    saved = connect_saved(interfaces[0])
    if saved.get("online"):
        return saved
    if interactive:
        return interactive_wifi_setup(interfaces[0])
    return saved


def _write_receipt(path: Path, payload: dict[str, Any]) -> None:
    safe = dict(payload)
    safe.pop("ssid", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(safe, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bounded Aurum network observer")
    parser.add_argument("--boot-status", action="store_true")
    parser.add_argument("--reconnect-saved", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=50)
    parser.add_argument("--write-state", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.reconnect_saved:
        result = connect_saved(timeout_seconds=max(5, min(args.timeout_seconds, 120)))
    else:
        result = network_status()
    if args.write_state:
        _write_receipt(args.write_state, result)
    print(json.dumps(result, sort_keys=True))
    # Network loss is recoverable; boot and the graphical setup remain usable.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
