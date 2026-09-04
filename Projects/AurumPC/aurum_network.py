#!/usr/bin/env python3
"""Bounded Wi-Fi bring-up for the Aurum PC live seed.

Aurum owns the operator flow; Linux networking tools are used only as the
hardware compatibility substrate.  Wi-Fi credentials are converted to a
wpa_supplicant configuration with the plaintext comment removed and are kept
under Aurum's state directory with mode 0600.  This module never writes an
internal disk directly.
"""
from __future__ import annotations

import argparse
import errno
from contextlib import contextmanager
from functools import wraps
import getpass
import ipaddress
import json
import os
import re
import select
import signal
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
SAVED_WIFI = STATE_DIR / "wifi.conf"
RUN_DIR = Path("/run/aurum")
PROC_ROOT = Path("/proc")
CONTROL_DIR = Path("/run/wpa_supplicant")


class NetworkError(RuntimeError):
    pass


class NetworkBusy(NetworkError):
    pass


@contextmanager
def _operation_lock():
    # File locking also covers separate GUI, console and boot processes.
    import fcntl
    RUN_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(RUN_DIR / "wifi-operation.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
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
            return {"status": "wifi-operation-busy", "online": False}
        except (NetworkError, OSError) as exc:
            return {"status": "wifi-service-unavailable", "online": False, "error_type": type(exc).__name__}
    return wrapped


def _usable_ipv4(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
        return address.version == 4 and not (
            address.is_loopback or address.is_link_local or address.is_unspecified or address.is_multicast
        )
    except ValueError:
        return False


def _internet_probe(interface: str, source_ip: str) -> dict[str, Any]:
    # Resolver calls can block beyond socket timeouts. An owned child bounds
    # DNS AND TCP together; subprocess.run kills/reaps it on timeout. No shell.
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
            return {key: payload.get(key) for key in ("dns_github", "github_tcp_443", "probe_status")}
    except (NetworkError, ValueError):
        pass
    return {"dns_github": False, "github_tcp_443": False, "probe_status": "timeout-or-unavailable"}


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
    result = _run(arguments, timeout=2)
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
        route_result = _run([ip, "route", "show", "default"], timeout=2)
        default_routes = [line.strip() for line in route_result.stdout.splitlines() if line.strip()]
        route_arguments = [ip, "route", "get", "1.1.1.1"]
        if interface:
            route_arguments.extend(["oif", interface])
        route_probe = _run(route_arguments, timeout=2)
        if route_probe.returncode == 0:
            route = route_probe.stdout.strip().splitlines()[0] if route_probe.stdout.strip() else ""

    route_fields = route.split()
    route_interface = None
    if "dev" in route_fields and route_fields.index("dev") + 1 < len(route_fields):
        route_interface = route_fields[route_fields.index("dev") + 1]
    active_interface = interface or route_interface
    addresses = _addresses(interface)
    active_addresses = [
        value.split(":", 1)[1]
        for value in addresses
        if active_interface and value.startswith(f"{active_interface}:")
    ]
    active_ip = next((value for value in active_addresses if _usable_ipv4(value)), None)
    route_matches = bool(active_interface and active_interface == route_interface)
    probe = {"dns_github": False, "github_tcp_443": False, "probe_status": "not-run"}
    if active_ip and route_matches:
        probe = _internet_probe(active_interface, active_ip)
    return {
        "wireless_interfaces": wireless_interfaces(),
        "interface": active_interface,
        "ip": active_ip,
        "addresses": addresses,
        "default_routes": default_routes,
        "route_probe": route,
        "route_matches_interface": route_matches,
        **probe,
        "online": bool(active_ip and route_matches and probe["dns_github"] and probe["github_tcp_443"]),
    }


@_serialized
def scan_networks(interface: str | None = None) -> dict[str, Any]:
    interfaces = wireless_interfaces()
    selected = interface or (interfaces[0] if interfaces else None)
    if not selected or selected not in interfaces:
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


def _write_config(path: Path, config: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(config)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if hasattr(os, "O_DIRECTORY"):
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def _write_saved_config(config: str) -> None:
    if SAVED_WIFI.is_file():
        previous = SAVED_WIFI.read_text(encoding="utf-8")
        if previous != config:
            _write_config(SAVED_WIFI.with_name("wifi.previous.conf"), previous)
    _write_config(SAVED_WIFI, config)


def _aurum_supplicant_arguments(arguments: list[str], interface: str) -> bool:
    def option(name: str):
        if arguments.count(name) != 1:
            return None
        index = arguments.index(name) + 1
        return arguments[index] if index < len(arguments) else None
    configs = {str(SAVED_WIFI), str(RUN_DIR / f"wifi-{interface}.conf")}
    return bool(arguments and Path(arguments[0]).name == "wpa_supplicant"
                and "-N" not in arguments and option("-i") == interface
                and option("-P") == str(RUN_DIR / f"wpa-{interface}.pid")
                and option("-c") in configs)


def _orphan_identity_matches(pid: int, interface: str, inode: str) -> bool:
    """A lost PID file is recoverable only with executable AND socket ownership."""
    process = PROC_ROOT / str(pid)
    try:
        arguments = (process / "cmdline").read_bytes().decode("utf-8", "strict").strip("\0").split("\0")
        if not _aurum_supplicant_arguments(arguments, interface) or process.stat().st_uid != 0:
            return False
        if (process / "exe").resolve(strict=True) != Path(_command("wpa_supplicant")).resolve(strict=True):
            return False
        deadline = time.monotonic() + 1
        for index, descriptor in enumerate((process / "fd").iterdir()):
            if index >= 256 or time.monotonic() > deadline:
                raise NetworkError("Wi-Fi descriptor ownership inspection incomplete")
            try:
                if os.readlink(descriptor) == f"socket:[{inode}]":
                    return True
            except FileNotFoundError:
                continue  # A descriptor may close during a read-only snapshot.
    except (FileNotFoundError, ProcessLookupError, UnicodeError):
        return False
    return False


def _find_owned_orphan_supplicant(interface: str) -> tuple[int, str] | None:
    path = str(CONTROL_DIR / interface)
    inodes = set()
    for line in (PROC_ROOT / "net" / "unix").read_text(encoding="utf-8").splitlines():
        fields = line.split(maxsplit=7)
        if len(fields) == 8 and fields[7] == path and fields[4] == "0002":
            inodes.add(fields[6])
    if not inodes:
        return None
    matches = []
    deadline = time.monotonic() + 2
    for index, process in enumerate(PROC_ROOT.iterdir()):
        if index >= 4096 or time.monotonic() > deadline:
            raise NetworkError("Wi-Fi socket ownership inspection incomplete")
        if not process.name.isdecimal() or int(process.name) <= 1:
            continue
        for inode in inodes:
            if _orphan_identity_matches(int(process.name), interface, inode):
                matches.append((int(process.name), inode))
    if len(matches) > 1:
        raise NetworkError("Wi-Fi socket ownership is ambiguous")
    return matches[0] if matches else None


def _control_socket_is_bound(interface: str) -> bool:
    # No unlink: even an unresponsive bound socket belongs to a live process.
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as probe:
        probe.settimeout(0.2)
        try:
            probe.connect(str(CONTROL_DIR / interface))
            return True
        except OSError as exc:
            if exc.errno in {errno.ENOENT, errno.ECONNREFUSED}:
                return False
            raise NetworkError("Wi-Fi control socket could not be inspected safely") from exc


def _managed_supplicant_unit(pid: int) -> str | None:
    try:
        groups = (PROC_ROOT / str(pid) / "cgroup").read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    for group in groups:
        unit = group.rsplit("/", 1)[-1]
        if re.fullmatch(r"aurum-wifi-[0-9a-f]{32}\.service", unit):
            return unit
    return None


def _wait_owned_unit_cleanup(unit: str) -> None:
    # PIDFile cleanup can lag process exit. Never launch a new PID into that race.
    deadline = time.monotonic() + 3
    while True:
        result = _run([_command("systemctl"), "show", unit, "--property=LoadState", "--property=ActiveState"], timeout=2)
        fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        if fields.get("LoadState") == "not-found" or (
            result.returncode == 0 and fields.get("ActiveState") in {"inactive", "failed"}
        ):
            return
        if time.monotonic() >= deadline:
            raise NetworkError("Wi-Fi service cleanup incomplete; no replacement started")
        time.sleep(.1)


def _start_owned_supplicant(interface: str, config_path: Path, manager: str) -> subprocess.CompletedProcess[str]:
    pid_path = RUN_DIR / f"wpa-{interface}.pid"
    unit = f"aurum-wifi-{uuid.uuid4().hex}.service"
    _write_config(RUN_DIR / f"wpa-{interface}.unit", unit + "\n")
    # The system manager, not the requesting GUI/console, owns this process.
    # No Restart loop: explicit locked transactions own reconnection/recovery.
    return _run([
        manager, "--quiet", "--no-ask-password", "--collect", f"--unit={unit}",
        "--service-type=forking", f"--property=PIDFile={pid_path}",
        "--property=Restart=no", "--property=KillMode=control-group",
        "--property=TimeoutStartSec=8", "--property=TimeoutStopSec=5", "--property=UMask=0077",
        "--", _command("wpa_supplicant"), "-B", "-D", "nl80211,wext", "-i", interface,
        "-c", str(config_path), "-P", str(pid_path),
    ], timeout=15)


def _stop_owned_supplicant(interface: str) -> None:
    pid_path = RUN_DIR / f"wpa-{interface}.pid"
    unit_path = RUN_DIR / f"wpa-{interface}.unit"
    try:
        tracked_unit = unit_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        tracked_unit = None
    if tracked_unit is not None and not re.fullmatch(r"aurum-wifi-[0-9a-f]{32}\.service", tracked_unit):
        raise NetworkError("invalid Wi-Fi service ownership record")

    def finish_unit_cleanup(managed=None):
        for unit in sorted({value for value in (managed, tracked_unit) if value}):
            _wait_owned_unit_cleanup(unit)
        try:
            if tracked_unit is not None and unit_path.read_text(encoding="utf-8").strip() == tracked_unit:
                unit_path.unlink()
        except FileNotFoundError:
            pass

    managed_unit = None
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pid = None
    if (pid is not None and pid <= 1) or not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise NetworkError("safe Wi-Fi process ownership check unavailable")
    fd = None
    if pid is not None:
        try:
            fd = os.pidfd_open(pid)
        except ProcessLookupError:
            pid = None
    orphan = None
    if fd is None:
        orphan = _find_owned_orphan_supplicant(interface)
        if orphan is None:
            finish_unit_cleanup()
            return
        pid, _ = orphan
        try:
            fd = os.pidfd_open(pid)
        except ProcessLookupError:
            finish_unit_cleanup()
            return
    try:
        try:
            arguments = (PROC_ROOT / str(pid) / "cmdline").read_bytes().decode("utf-8", "strict").strip("\0").split("\0")
        except FileNotFoundError:
            arguments = []
        owned = _aurum_supplicant_arguments(arguments, interface)
        if orphan is not None:
            owned = owned and _orphan_identity_matches(pid, interface, orphan[1])
        if not owned and not select.select([fd], [], [], 0)[0]:
            raise NetworkError("refusing to terminate an unrecognized Wi-Fi process")
        if owned:
            managed_unit = _managed_supplicant_unit(pid)
            try:
                signal.pidfd_send_signal(fd, signal.SIGTERM)
            except ProcessLookupError:
                pass
        if not select.select([fd], [], [], 5)[0]:
            raise NetworkError("Wi-Fi service did not stop; no replacement was started")
    finally:
        os.close(fd)
    finish_unit_cleanup(managed_unit)
    try:
        if pid_path.read_text(encoding="utf-8").strip() == str(pid):
            pid_path.unlink()
    except FileNotFoundError:
        pass


def _supplicant_status(interface: str) -> dict[str, str]:
    helper = _command("wpa_cli")
    result = _run([helper, "-p", str(CONTROL_DIR), "-i", interface, "status"], timeout=2)
    fields = {}
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            key, separator, value = line.partition("=")
            if separator and key in {"wpa_state", "ssid"}:
                fields[key] = value
    return fields


def _connection_state(interface: str) -> dict[str, Any]:
    association = _supplicant_status(interface)
    status = network_status(interface)
    associated = association.get("wpa_state") == "COMPLETED"
    reason = "online"
    if not associated:
        reason = "wifi-association-pending"
    elif not status.get("ip"):
        reason = "wifi-address-pending"
    elif not status.get("route_matches_interface"):
        reason = "wifi-route-pending"
    elif status.get("probe_status") == "timeout-or-unavailable":
        reason = "wifi-probe-unavailable"
    elif not status.get("dns_github"):
        reason = "wifi-dns-unavailable"
    elif not status.get("github_tcp_443"):
        reason = "wifi-internet-unreachable"
    return {**status, "associated": associated, "ssid": association.get("ssid"),
            "wpa_state": association.get("wpa_state", "UNKNOWN"), "status": reason,
            "online": bool(associated and status.get("online"))}


def _connect_config(selected: str, config_path: Path, *, timeout_seconds: int) -> dict[str, Any]:
    if selected not in wireless_interfaces():
        return {"status": "no-wifi-interface", "online": False, "started": False}
    # Resolve dependencies before stopping a usable existing connection.
    manager = _command("systemd-run")
    _command("systemctl")
    _command("wpa_supplicant")
    deadline = time.monotonic() + max(0, timeout_seconds)
    rfkill = shutil.which("rfkill")
    if rfkill:
        _run([rfkill, "unblock", "wifi"], timeout=2)
    _run([_command("ip"), "link", "set", "dev", selected, "up"], timeout=2)
    _stop_owned_supplicant(selected)
    # A remaining responsive manager or bound socket is not ours. Never kill it, unlink its
    # socket or start a competing daemon on its interface.
    if _supplicant_status(selected).get("wpa_state") or _control_socket_is_bound(selected):
        return {"status": "wifi-manager-conflict", "online": False, "started": False}
    result = _start_owned_supplicant(selected, config_path, manager)
    if result.returncode != 0:
        reason = "wifi-manager-conflict" if "ctrl_iface exists and seems to be in use" in result.stdout else "association-start-failed"
        return {"status": reason, "online": False, "started": True}
    networkctl = shutil.which("networkctl")
    # Reconfiguring on every poll needlessly churns DHCP while it is acquiring
    # a lease. Request it once; networkd reacts to association/carrier changes.
    if networkctl:
        _run([networkctl, "reconfigure", selected], timeout=2)
    status = {"status": "wifi-connection-unverified", "online": False}
    while time.monotonic() < deadline:
        status = _connection_state(selected)
        if status["online"]:
            break
        if time.monotonic() < deadline:
            time.sleep(min(1, max(0, deadline - time.monotonic())))
    return {**status, "started": True}


@_serialized
def connect_saved(interface: str | None = None, *, timeout_seconds: int = 50) -> dict[str, Any]:
    interfaces = wireless_interfaces()
    selected = interface or (interfaces[0] if interfaces else None)
    if not selected or selected not in interfaces:
        return {"status": "no-wifi-interface", **network_status()}
    if not SAVED_WIFI.is_file():
        return {"status": "credentials-required", **network_status(selected)}

    return _connect_config(selected, SAVED_WIFI, timeout_seconds=timeout_seconds)


@_serialized
def connect_wifi(
    ssid: str,
    password: str,
    interface: str | None = None,
    *,
    timeout_seconds: int = 50,
) -> dict[str, Any]:
    """Connect from a graphical client without exposing a text-console workflow."""
    interfaces = wireless_interfaces()
    selected = interface or (interfaces[0] if interfaces else None)
    if not selected or selected not in interfaces:
        return {"status": "no-wifi-interface", **network_status()}
    config = _make_config(ssid.strip(), password)
    password = ""
    candidate = RUN_DIR / f"wifi-{selected}.conf"
    _write_config(candidate, config)
    result = _connect_config(selected, candidate, timeout_seconds=timeout_seconds)
    verified = bool(result.get("online") and result.get("associated") and result.get("ssid") == ssid.strip())
    if verified:
        _write_saved_config(config)
        return {**result, "saved": True}
    result = {**result, "online": False, "saved": False}
    if result.get("status") == "online":
        result["status"] = "wifi-network-mismatch"
    if result.get("started"):
        try:
            _stop_owned_supplicant(selected)
            if SAVED_WIFI.is_file():
                recovery = _connect_config(selected, SAVED_WIFI, timeout_seconds=15)
                result["recovery"] = {"status": recovery["status"], "online": recovery.get("online", False)}
        except NetworkError:
            result["recovery"] = {"status": "recovery-not-verified", "online": False}
    return result


@_serialized
def disconnect_wifi(*, forget: bool = False) -> dict[str, Any]:
    interfaces = wireless_interfaces()
    selected = interfaces[0] if interfaces else None
    if selected:
        _stop_owned_supplicant(selected)
        if _supplicant_status(selected).get("wpa_state") or _control_socket_is_bound(selected):
            return {"status": "wifi-manager-conflict", "online": False}
    if forget:
        SAVED_WIFI.unlink(missing_ok=True)
        SAVED_WIFI.with_name("wifi.previous.conf").unlink(missing_ok=True)
        if selected:
            (RUN_DIR / f"wifi-{selected}.conf").unlink(missing_ok=True)
    return {"status": "saved-network-forgotten" if forget else "disconnected", "online": False}


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
    return connect_wifi(ssid, password, selected)


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


def _write_receipt(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bounded Aurum Wi-Fi recovery")
    parser.add_argument("--reconnect-saved", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=50)
    parser.add_argument("--write-state", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.reconnect_saved:
        result = network_status()
    else:
        timeout_seconds = max(5, min(args.timeout_seconds, 120))
        current = network_status()
        result = (
            {"status": "already-online", **current}
            if current.get("online")
            else connect_saved(timeout_seconds=timeout_seconds)
        )
    if args.write_state:
        _write_receipt(args.write_state, result)
    print(json.dumps(result, sort_keys=True))
    # Wi-Fi is a recoverable boot dependency. The receipt carries degraded
    # state while boot and the local recovery console remain available.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
