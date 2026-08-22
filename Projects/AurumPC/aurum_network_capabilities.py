#!/usr/bin/env python3
"""Read-only network-wide capability discovery for Aurum.

Aurum treats every reachable networked device as a potential capability node.
This module discovers local peers without logging in to them or changing their
state, infers conservative capability hypotheses from observed roles/services,
and emits nodes compatible with aurum_capability_graph.py.

Discovery is intentionally bounded to the local machine's existing neighbor
state plus optional local-link mDNS/SSDP service discovery. No port sweep,
credential attempt, configuration change, or remote command is performed.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "aurum.network-capability-discovery.v1"
DEFAULT_OUT = Path(os.environ.get("AURUM_NETWORK_CAPABILITIES", "/run/aurum/network-capabilities.json"))


def _run(arguments: list[str], *, timeout: int = 5) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            arguments,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _read(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return default


def _gateway(proc_root: Path = Path("/proc")) -> tuple[str | None, str | None]:
    text = _read(proc_root / "net" / "route")
    for line in text.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 4 or fields[1] != "00000000":
            continue
        try:
            flags = int(fields[3], 16)
            raw = bytes.fromhex(fields[2])
            address = str(ipaddress.IPv4Address(raw[::-1]))
        except (ValueError, ipaddress.AddressValueError):
            continue
        if flags & 0x2:
            return address, fields[0]
    return None, None


def neighbor_rows() -> list[dict[str, Any]]:
    ip = shutil.which("ip")
    if not ip:
        return []
    result = _run([ip, "-j", "neigh", "show"], timeout=5)
    if result is None or result.returncode != 0:
        return []
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    rows: list[dict[str, Any]] = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        dst = str(item.get("dst") or "").strip()
        if not dst:
            continue
        try:
            parsed = ipaddress.ip_address(dst)
        except ValueError:
            continue
        if parsed.is_loopback or parsed.is_multicast:
            continue
        rows.append(
            {
                "address": dst,
                "mac": item.get("lladdr"),
                "interface": item.get("dev"),
                "state": list(item.get("state") or []),
                "source": "ip-neigh",
            }
        )
    return rows


def _mdns_rows() -> list[dict[str, Any]]:
    avahi = shutil.which("avahi-browse")
    if not avahi:
        return []
    result = _run([avahi, "-artp"], timeout=8)
    if result is None:
        return []
    rows: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        if not line.startswith("="):
            continue
        fields = line.split(";")
        if len(fields) < 9:
            continue
        # avahi-browse parseable resolved line:
        # =;iface;proto;name;type;domain;host;address;port;txt
        try:
            port = int(fields[8])
        except ValueError:
            port = None
        rows.append(
            {
                "name": fields[3],
                "service": fields[4],
                "host": fields[6],
                "address": fields[7],
                "port": port,
                "txt": fields[9] if len(fields) > 9 else "",
                "source": "mdns",
            }
        )
    return rows


def _ssdp_rows(timeout_seconds: float = 1.2) -> list[dict[str, Any]]:
    request = (
        "M-SEARCH * HTTP/1.1\r\n"
        "HOST: 239.255.255.250:1900\r\n"
        'MAN: "ssdp:discover"\r\n'
        "MX: 1\r\n"
        "ST: ssdp:all\r\n\r\n"
    ).encode("ascii")
    rows: list[dict[str, Any]] = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.settimeout(timeout_seconds)
        sock.sendto(request, ("239.255.255.250", 1900))
        deadline = time.monotonic() + timeout_seconds
        seen: set[tuple[str, str, str]] = set()
        while time.monotonic() < deadline:
            try:
                data, peer = sock.recvfrom(65535)
            except socket.timeout:
                break
            text = data.decode("utf-8", "replace")
            headers: dict[str, str] = {}
            for line in text.splitlines()[1:]:
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
            key = (peer[0], headers.get("st", ""), headers.get("usn", ""))
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "address": peer[0],
                    "service": headers.get("st"),
                    "server": headers.get("server"),
                    "location": headers.get("location"),
                    "usn": headers.get("usn"),
                    "source": "ssdp",
                }
            )
    except OSError:
        return rows
    finally:
        sock.close()
    return rows


def _tokens(*values: object) -> str:
    return " ".join(str(value or "").lower() for value in values)


def _infer_role(text: str, *, is_gateway: bool = False) -> tuple[str, set[str], float]:
    caps: set[str] = {"transport"}
    role = "network-peer"
    confidence = 0.45

    if is_gateway or any(token in text for token in ("router", "gateway", "openwrt", "routeros", "unifi", "eero")):
        return "router", {"transport", "route", "relay", "sense", "recover"}, 0.9 if is_gateway else 0.75

    if any(token in text for token in ("camera", "cam", "onvif", "rtsp", "nvr", "doorbell")):
        role = "camera"
        caps |= {"sense", "optical-receive", "store"}
        confidence = 0.82
    elif any(token in text for token in ("light", "bulb", "lamp", "hue", "nanoleaf", "lifx")):
        role = "light"
        caps |= {"actuate", "light-emit"}
        confidence = 0.82
    elif any(token in text for token in ("speaker", "sonos", "airplay", "audio", "homepod")):
        role = "speaker"
        caps |= {"actuate", "acoustic-emit"}
        confidence = 0.8
    elif any(token in text for token in ("headset", "earbud", "headphone")):
        role = "headset"
        caps |= {"sense", "actuate", "acoustic-emit", "acoustic-receive"}
        confidence = 0.78
    elif any(token in text for token in ("tv", "television", "chromecast", "roku", "airplay", "dlna", "mediarenderer")):
        role = "display"
        caps |= {"actuate", "light-emit", "acoustic-emit"}
        confidence = 0.76
    elif any(token in text for token in ("iphone", "android", "phone", "pixel", "galaxy")):
        role = "phone"
        caps |= {"sense", "actuate", "compute", "store", "radio", "light-emit", "optical-receive", "acoustic-emit", "acoustic-receive"}
        confidence = 0.7
    elif any(token in text for token in ("printer", "ipp", "airprint")):
        role = "printer"
        caps |= {"actuate", "store"}
        confidence = 0.8
    elif any(token in text for token in ("nas", "synology", "qnap", "smb", "nfs", "storage")):
        role = "storage"
        caps |= {"store", "relay"}
        confidence = 0.8
    elif any(token in text for token in ("switch", "bridge", "access point", "access-point", "wireless ap")):
        role = "network-infrastructure"
        caps |= {"relay", "sense"}
        confidence = 0.72
    elif any(token in text for token in ("laptop", "desktop", "computer", "raspberry", "linux", "windows", "macbook", "aurum", "boxbrain", "hopper")):
        role = "computer"
        caps |= {"sense", "actuate", "compute", "store", "recover"}
        confidence = 0.68

    return role, caps, confidence


def _node_id(address: str, mac: str | None) -> str:
    stable = (mac or address).lower().replace(":", "-").replace("%", "-")
    return f"network:{stable}"


def build_discovery(
    *,
    neighbors: Iterable[dict[str, Any]] | None = None,
    services: Iterable[dict[str, Any]] | None = None,
    gateway: tuple[str | None, str | None] | None = None,
    active_local_discovery: bool = False,
    proc_root: Path = Path("/proc"),
) -> dict[str, Any]:
    neighbors = list(neighbor_rows() if neighbors is None else neighbors)
    service_rows = list(services or [])
    if active_local_discovery and services is None:
        service_rows.extend(_mdns_rows())
        service_rows.extend(_ssdp_rows())
    gateway_address, gateway_interface = gateway if gateway is not None else _gateway(proc_root)

    devices: dict[str, dict[str, Any]] = {}
    for row in neighbors:
        address = str(row.get("address") or "").strip()
        if not address:
            continue
        key = address
        devices.setdefault(
            key,
            {
                "address": address,
                "mac": row.get("mac"),
                "interface": row.get("interface"),
                "neighbor_state": row.get("state") or [],
                "names": [],
                "services": [],
                "evidence": [row.get("source") or "neighbor"],
            },
        )

    for row in service_rows:
        address = str(row.get("address") or "").strip()
        if not address:
            continue
        device = devices.setdefault(
            address,
            {
                "address": address,
                "mac": None,
                "interface": None,
                "neighbor_state": [],
                "names": [],
                "services": [],
                "evidence": [],
            },
        )
        for name in (row.get("name"), row.get("host"), row.get("server")):
            if name and str(name) not in device["names"]:
                device["names"].append(str(name))
        service = {key: value for key, value in row.items() if key not in {"address", "name", "host", "server", "source"} and value not in (None, "")}
        if service and service not in device["services"]:
            device["services"].append(service)
        source = str(row.get("source") or "service")
        if source not in device["evidence"]:
            device["evidence"].append(source)

    nodes: list[dict[str, Any]] = []
    for address, device in sorted(devices.items()):
        service_text = " ".join(json.dumps(item, sort_keys=True) for item in device["services"])
        evidence_text = _tokens(address, device.get("mac"), *device["names"], service_text)
        is_gateway = bool(gateway_address and address == gateway_address)
        role, caps, confidence = _infer_role(evidence_text, is_gateway=is_gateway)
        if is_gateway:
            device["interface"] = device.get("interface") or gateway_interface
        label = device["names"][0] if device["names"] else ("Default gateway" if is_gateway else address)
        nodes.append(
            {
                "id": _node_id(address, device.get("mac")),
                "label": label,
                "source": "network-discovery",
                "capabilities": sorted(caps),
                "properties": {
                    "address": address,
                    "mac": device.get("mac"),
                    "interface": device.get("interface"),
                    "neighbor_state": device.get("neighbor_state"),
                    "role_hypothesis": role,
                    "gateway": is_gateway,
                    "names": device["names"],
                    "services": device["services"],
                    "evidence": sorted(set(device["evidence"])),
                    "authorization": "unverified",
                },
                "safety": "observe-only",
                "confidence": round(confidence, 3),
            }
        )

    return {
        "schema": SCHEMA,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "read_only": True,
        "local_link_only": True,
        "active_local_discovery": bool(active_local_discovery),
        "device_count": len(nodes),
        "nodes": nodes,
        "boundary": {
            "port_sweep": False,
            "credential_attempt": False,
            "remote_command": False,
            "remote_configuration": False,
            "execution_authorized": False,
        },
        "principle": "every reachable device is a potential capability node; capabilities remain hypotheses until measured",
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Aurum network capability discovery")
    parser.add_argument("capture", nargs="?")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--active-local-discovery", action="store_true")
    args = parser.parse_args()
    payload = build_discovery(active_local_discovery=args.active_local_discovery)
    _atomic_json(args.out, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
