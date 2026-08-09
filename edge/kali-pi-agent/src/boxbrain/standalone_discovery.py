"""Bounded discovery for BoxBrain's standalone trusted-LAN mode.

Discovery is deliberately separated from enrollment.  It inventories a directly
connected private WLAN, identifies BoxBrain health endpoints and WinRM listeners,
and refreshes diagnostics only for targets that were already enrolled with the
BoxBrain SSH key.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import http.client
import ipaddress
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import tempfile
from typing import Any, Callable

from boxbrain import __version__
from boxbrain.diagnostics import DIAGNOSTIC_AUTHORIZATION, DiagnosticError, TargetDiagnostics
from boxbrain.links import load_links
from boxbrain import link_monitor


LOG = logging.getLogger("boxbrain.standalone-discovery")
STATE_DIRECTORY = Path(os.environ.get("BOXBRAIN_STATE_DIR", "/var/lib/boxbrain"))
MODE_FILE = Path(os.environ.get("BOXBRAIN_NETWORK_MODE_FILE", "/run/boxbrain/network-mode"))
ALLOWLIST_FILE = Path(
    os.environ.get(
        "BOXBRAIN_STANDALONE_NETWORK_ALLOWLIST",
        "/etc/boxbrain/standalone-networks.allow",
    )
)
WIFI_INTERFACE = os.environ.get("BOXBRAIN_STANDALONE_WIFI_INTERFACE", "wlan0")
DISCOVERY_PORTS = (22, 5985, 5986, 8787, 8788)
MAX_HOSTS = 254
MAX_WORKERS = 48
SOCKET_TIMEOUT = 0.3


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run(command: list[str], timeout: int = 5) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}-",
        dir=path.parent,
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, separators=(",", ":"), sort_keys=True)
            stream.write("\n")
        os.chmod(temporary_name, 0o640)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _read_allowlist(path: Path | None = None) -> set[str]:
    if path is None:
        path = ALLOWLIST_FILE
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return set()
    return {
        line.strip()
        for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    }


def _nmcli_field(value: str) -> str:
    """Unescape the small subset used by nmcli's terse output."""
    return value.replace(r"\:", ":").replace(r"\\", "\\")


def wifi_context(interface: str = WIFI_INTERFACE) -> dict[str, Any]:
    active = _run(["nmcli", "-t", "-f", "ACTIVE,SSID", "device", "wifi", "list", "ifname", interface])
    ssid = ""
    if active is not None and active.returncode == 0:
        for line in active.stdout.splitlines():
            if line.startswith("yes:"):
                ssid = _nmcli_field(line[4:]).strip()
                break

    known = _run(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"])
    known_names: list[str] = []
    if known is not None and known.returncode == 0:
        for line in known.stdout.splitlines():
            name, separator, connection_type = line.rpartition(":")
            if separator and connection_type == "802-11-wireless" and name:
                known_names.append(_nmcli_field(name))

    addresses = _run(["ip", "-j", "-4", "address", "show", "dev", interface])
    address = ""
    prefix = 0
    if addresses is not None and addresses.returncode == 0:
        try:
            payload = json.loads(addresses.stdout)
        except json.JSONDecodeError:
            payload = []
        for item in payload:
            for info in item.get("addr_info", []):
                try:
                    candidate = ipaddress.ip_address(str(info.get("local", "")))
                except ValueError:
                    continue
                if candidate.version == 4 and candidate.is_private and not candidate.is_link_local:
                    address = str(candidate)
                    prefix = int(info.get("prefixlen", 0))
                    break
            if address:
                break

    return {
        "interface": interface,
        "ssid": ssid,
        "known_wifi_profiles": sorted(set(known_names), key=str.casefold),
        "address": address,
        "prefix_length": prefix,
    }


def bounded_network(address: str, prefix_length: int) -> ipaddress.IPv4Network:
    parsed = ipaddress.ip_address(address)
    if parsed.version != 4 or not parsed.is_private or parsed.is_link_local:
        raise ValueError("Standalone discovery requires a private, non-link-local IPv4 address.")
    network = ipaddress.ip_network(f"{address}/{prefix_length}", strict=False)
    if network.num_addresses > 256:
        network = ipaddress.ip_network(f"{address}/24", strict=False)
    if max(0, network.num_addresses - 2) > MAX_HOSTS:
        raise ValueError("Standalone discovery scope exceeds the host limit.")
    return network


def _open_ports(address: str, ports: tuple[int, ...] = DISCOVERY_PORTS) -> list[int]:
    open_ports: list[int] = []
    for port in ports:
        try:
            with socket.create_connection((address, port), timeout=SOCKET_TIMEOUT):
                open_ports.append(port)
        except OSError:
            continue
    return open_ports


def _boxbrain_health(address: str, port: int) -> dict[str, Any] | None:
    connection = http.client.HTTPConnection(address, port, timeout=1.0)
    try:
        connection.request("GET", "/health", headers={"Accept": "application/json"})
        response = connection.getresponse()
        body = response.read(65537)
        if response.status != 200 or len(body) > 65536:
            return None
        payload = json.loads(body.decode("utf-8"))
    except (OSError, http.client.HTTPException, UnicodeError, json.JSONDecodeError):
        return None
    finally:
        connection.close()
    if not isinstance(payload, dict) or not str(payload.get("service", "")).startswith("boxbrain"):
        return None
    return {
        "service": str(payload.get("service")),
        "status": str(payload.get("status", "unknown")),
        "version": str(payload.get("version", "unknown")),
        "port": port,
    }


def _version_tuple(value: str) -> tuple[int, ...] | None:
    parts = value.strip().split(".")
    if not parts or any(not part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def _version_review(remote_version: str) -> dict[str, Any]:
    local = _version_tuple(__version__)
    remote = _version_tuple(remote_version)
    if local is None or remote is None:
        return {"status": "review", "local_version": __version__}
    width = max(len(local), len(remote))
    local = (*local, *(0 for _ in range(width - len(local))))
    remote = (*remote, *(0 for _ in range(width - len(remote))))
    if remote < local:
        status = "update_recommended"
    elif remote > local:
        status = "local_update_recommended"
    else:
        status = "current"
    return {"status": status, "local_version": __version__}


def discover_hosts(
    network: ipaddress.IPv4Network,
    own_address: str,
    *,
    port_probe: Callable[[str], list[int]] = _open_ports,
) -> list[dict[str, Any]]:
    candidates = [str(item) for item in network.hosts() if str(item) != own_address]
    discovered: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, max(1, len(candidates)))) as executor:
        futures = {executor.submit(port_probe, address): address for address in candidates}
        for future in as_completed(futures):
            address = futures[future]
            try:
                ports = sorted(set(future.result()))
            except Exception as error:  # isolate a failed host probe
                LOG.debug("Probe failed for %s: %s", address, error)
                continue
            if ports:
                discovered.append({"address": address, "open_ports": ports})
    return sorted(discovered, key=lambda item: ipaddress.ip_address(item["address"]))


def _refresh_enrolled_hosts(hosts: list[dict[str, Any]], interface: str) -> None:
    registered = {
        str(item.get("address")): item
        for item in load_links(str(STATE_DIRECTORY))
        if isinstance(item.get("address"), str)
    }
    if not registered or not link_monitor.IDENTITY_FILE.is_file():
        return
    diagnostics = TargetDiagnostics(str(STATE_DIRECTORY), str(link_monitor.IDENTITY_FILE))
    for host in hosts:
        address = host["address"]
        if address not in registered or 22 not in host["open_ports"]:
            continue
        verified = link_monitor.probe(address, transport="network-ssh", interface=interface)
        if verified is None:
            host["enrollment"] = "key_verification_failed"
            continue
        saved = link_monitor.save_link(verified)
        host["enrollment"] = "verified"
        host["hostname"] = saved.get("hostname")
        if link_monitor._diagnostic_due(saved):
            try:
                report = diagnostics.diagnose(address, DIAGNOSTIC_AUTHORIZATION)
                host["quick_check"] = {
                    "status": "completed",
                    "overall": report.get("summary", {}).get("overall"),
                }
            except DiagnosticError as error:
                host["quick_check"] = {"status": "failed", "error": str(error)[:300]}


def run_once() -> dict[str, Any]:
    try:
        mode = MODE_FILE.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        mode = "unknown"
    if mode != "standalone-local":
        return {"schema_version": 1, "changed": False, "skipped": "not_standalone_local", "mode": mode}

    context = wifi_context()
    if not context["ssid"] or not context["address"]:
        return {"schema_version": 1, "changed": False, "skipped": "wifi_not_ready", "mode": mode}

    network = bounded_network(context["address"], context["prefix_length"])
    allowlist = _read_allowlist()
    context["scan_authorization"] = (
        "current_private_lan" if context["ssid"] not in allowlist else "explicit_allowlist"
    )
    context["allowlisted"] = context["ssid"] in allowlist
    context["network"] = str(network)
    hosts = discover_hosts(network, context["address"])

    for host in hosts:
        services: list[str] = []
        if 22 in host["open_ports"]:
            services.append("ssh")
        if 5985 in host["open_ports"]:
            services.append("winrm-http")
        if 5986 in host["open_ports"]:
            services.append("winrm-https")
        for port in (8787, 8788):
            if port not in host["open_ports"]:
                continue
            health = _boxbrain_health(host["address"], port)
            if health is not None:
                host["boxbrain"] = health
                host["version_review"] = _version_review(health["version"])
                services.append(health["service"])
                break
        host["services"] = sorted(set(services))
        host["winrm_detected"] = any(port in host["open_ports"] for port in (5985, 5986))
        host["observation_only"] = True

    _refresh_enrolled_hosts(hosts, context["interface"])
    result = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "changed": True,
        "mode": mode,
        "scope": "directly-connected-private-wlan",
        "policy": {
            "unknown_hosts": "inventory_only",
            "enrolled_hosts": "key_verified_read_only_check",
            "automatic_remote_updates": False,
            "ports": list(DISCOVERY_PORTS),
            "host_limit": MAX_HOSTS,
        },
        "wifi": context,
        "host_count": len(hosts),
        "hosts": hosts,
    }
    discovery_directory = STATE_DIRECTORY / "discovery"
    _atomic_json(discovery_directory / "latest.json", result)
    for host in hosts:
        _atomic_json(discovery_directory / "hosts" / f"{host['address'].replace('.', '-')}.json", host)
    return result


def main() -> None:
    logging.basicConfig(level=os.environ.get("BOXBRAIN_LOG_LEVEL", "INFO"))
    result = run_once()
    if result.get("changed"):
        LOG.info(
            "Standalone discovery found %s endpoint(s) on %s",
            result.get("host_count", 0),
            result.get("wifi", {}).get("network", "unknown"),
        )
    else:
        LOG.info("Standalone discovery skipped: %s", result.get("skipped", "unknown"))


if __name__ == "__main__":
    main()
