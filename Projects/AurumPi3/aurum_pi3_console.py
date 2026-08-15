#!/usr/bin/env python3
"""Bounded, local-first Aurum console for Raspberry Pi 3.

The console intentionally exposes semantic operations rather than a shell. All
machine probes are read-only and individually isolated so an unavailable kernel
interface or command is a local capability barrier, never a console-wide stop.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

TARGET = "raspberry-pi-3"
STATE_SCHEMA = "aurum-pi3-capability-state-v1"
ROOT = Path(os.environ.get("AURUM_ROOT", "/opt/aurum/current"))
CODELATION = ROOT / "codelation"
CHAIN_STATE = CODELATION / "autobuild" / "native_chain_state.json"
RELEASE = ROOT / "RELEASE.json"
PACKAGED_UPDATER = ROOT / "aurum_updater.py"
UPDATER = Path(
    os.environ.get(
        "AURUM_UPDATER",
        str(PACKAGED_UPDATER if PACKAGED_UPDATER.is_file() else "/opt/aurum/updater/aurum_updater.py"),
    )
)
READINESS_FILE = os.environ.get("AURUM_READINESS_FILE")
DEFAULT_CAPABILITY_STATE = (
    "/var/lib/aurum-pi3/capability-state.json"
    if os.name != "nt"
    else str(Path(os.environ.get("TEMP", ".")) / "aurum-pi3" / "capability-state.json")
)
CAPABILITY_STATE = Path(os.environ.get("AURUM_CAPABILITY_STATE", DEFAULT_CAPABILITY_STATE))
PROC = Path(os.environ.get("AURUM_PROC_ROOT", "/proc"))
SYS = Path(os.environ.get("AURUM_SYS_ROOT", "/sys"))


def _release() -> dict[str, Any]:
    try:
        value = json.loads(RELEASE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


VERSION = str(_release().get("version", "0.01"))
RELEASE_ID = str(_release().get("release_id", f"{VERSION}-unversioned"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_text(path: Path, default: str = "unknown", limit: int = 262_144) -> str:
    try:
        value = path.read_bytes()[:limit].decode("utf-8", errors="replace")
        value = value.replace("\x00", "").strip()
        return value or default
    except OSError:
        return default


def _read_int(path: Path, default: int | None = None) -> int | None:
    try:
        return int(_read_text(path, ""))
    except ValueError:
        return default


def _chain_state() -> dict[str, Any]:
    try:
        value = json.loads(CHAIN_STATE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


CAPABILITY_DEFINITIONS: dict[str, dict[str, Any]] = {
    "capabilities": {
        "description": "Inventory implemented and machine-discovered capabilities.",
        "kind": "semantic",
        "authorization": "read-only",
    },
    "hardware": {
        "description": "Observe architecture, board identity, memory, and kernel.",
        "kind": "probe",
        "authorization": "read-only",
    },
    "network": {
        "description": "Observe local interfaces, routes, and configured DNS.",
        "kind": "probe",
        "authorization": "read-only",
    },
    "storage": {
        "description": "Observe block devices, mounts, and root filesystem capacity.",
        "kind": "probe",
        "authorization": "read-only",
    },
    "usb": {
        "description": "Observe USB devices exposed by Linux sysfs.",
        "kind": "probe",
        "authorization": "read-only",
    },
    "processes": {
        "description": "Observe process counts, load, memory, temperature, and pressure.",
        "kind": "probe",
        "authorization": "read-only",
    },
    "health": {
        "description": "Read-only alias for process, load, memory, temperature, and pressure health.",
        "kind": "semantic",
        "authorization": "read-only",
    },
    "services": {
        "description": "Observe systemd service health without changing service state.",
        "kind": "probe",
        "authorization": "read-only",
    },
    "frontier": {
        "description": "Choose the next local verification gap without blocking other work.",
        "kind": "semantic",
        "authorization": "read-only",
    },
    "observe": {
        "description": "Read the last persisted observation without probing again.",
        "kind": "semantic",
        "authorization": "read-only",
    },
    "rescan": {
        "description": "Run one or all bounded read-only probes and persist their state.",
        "kind": "semantic",
        "authorization": "read-only",
    },
    "json": {
        "description": "Emit a command result as one machine-readable JSON document.",
        "kind": "semantic",
        "authorization": "read-only",
    },
    "update-check": {
        "description": "Verify a pinned application release without activating it.",
        "kind": "semantic",
        "authorization": "read-only-with-explicit-source",
    },
    "update": {
        "description": "Stage and activate a verified application release without reflashing.",
        "kind": "action",
        "authorization": "explicit-manifest-sha256-and-network-authorization",
    },
    "update-status": {
        "description": "Read active, previous, pending, and update history state.",
        "kind": "semantic",
        "authorization": "read-only",
    },
    "rollback": {
        "description": "Atomically reactivate the previous healthy application release.",
        "kind": "action",
        "authorization": "explicit-confirmation",
    },
    "reboot": {
        "description": "Reboot only after an explicit confirmation token.",
        "kind": "action",
        "authorization": "explicit-confirmation",
    },
    "poweroff": {
        "description": "Power off only after an explicit confirmation token.",
        "kind": "action",
        "authorization": "explicit-confirmation",
    },
}

PROBE_ORDER = ("hardware", "network", "storage", "usb", "processes", "services")
PROBE_ALIASES = {"health": "processes", "system-health": "processes"}


class LocalBarrier(RuntimeError):
    """A failure scoped to one capability."""


class StateStore:
    def __init__(self, path: Path = CAPABILITY_STATE):
        self.path = path

    def _fresh(self) -> dict[str, Any]:
        capabilities: dict[str, Any] = {}
        for name, definition in CAPABILITY_DEFINITIONS.items():
            semantic = definition["kind"] == "semantic"
            read_only = definition["authorization"].startswith("read-only")
            capabilities[name] = {
                "implemented": True,
                "discovered": semantic,
                "verified": semantic,
                "authorized": read_only,
                "authorization": definition["authorization"],
                "status": "available" if semantic else "unverified",
                "last_observed_at": None,
                "barrier": None,
                "summary": {},
            }
        return {
            "schema": STATE_SCHEMA,
            "aurum_pi3_version": VERSION,
            "target": TARGET,
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "observation_generation": 0,
            "capabilities": capabilities,
            "frontier": None,
        }

    def load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("schema") != STATE_SCHEMA:
                raise ValueError("unsupported-state-schema")
            capabilities = value.setdefault("capabilities", {})
            capabilities.pop("upgrade.inspect", None)
            capabilities.pop("upgrade.apply", None)
            for name, initial in self._fresh()["capabilities"].items():
                capabilities.setdefault(name, initial)
            return value
        except FileNotFoundError:
            return self._fresh()
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            value = self._fresh()
            value["state_barrier"] = {
                "scope": "capability-state",
                "reason": f"{type(exc).__name__}:{exc}",
                "observed_at": _utc_now(),
            }
            return value

    def _acquire_lock(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_name(self.path.name + ".lock")
        for _ in range(20):
            try:
                lock.mkdir(mode=0o700)
                return lock
            except FileExistsError:
                try:
                    if time.time() - lock.stat().st_mtime > 30:
                        lock.rmdir()
                        continue
                except OSError:
                    pass
                time.sleep(0.05)
        raise LocalBarrier("capability-state-busy")

    def _write_unlocked(self, value: dict[str, Any]) -> None:
        value["updated_at"] = _utc_now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        try:
            temporary.write_text(
                json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            try:
                temporary.chmod(0o600)
            except OSError:
                pass
            os.replace(temporary, self.path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def mutate(self, change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        lock = self._acquire_lock()
        try:
            value = self.load()
            change(value)
            self._write_unlocked(value)
            return value
        finally:
            try:
                lock.rmdir()
            except OSError:
                pass

    def ensure_initialized(self) -> None:
        if self.path.exists():
            return
        self.mutate(lambda _state: None)

    def record_probe(
        self,
        name: str,
        *,
        discovered: bool,
        verified: bool,
        summary: dict[str, Any],
        barrier: str | None,
    ) -> dict[str, Any]:
        observed_at = _utc_now()

        def change(state: dict[str, Any]) -> None:
            state["observation_generation"] = int(state.get("observation_generation", 0)) + 1
            entry = state["capabilities"][name]
            entry.update(
                {
                    "discovered": discovered,
                    "verified": verified,
                    "authorized": True,
                    "status": "verified" if verified else "barrier",
                    "last_observed_at": observed_at,
                    "barrier": (
                        None
                        if barrier is None
                        else {"scope": name, "reason": barrier, "observed_at": observed_at}
                    ),
                    "summary": summary,
                }
            )

        return self.mutate(change)


@dataclass
class ProbeResult:
    capability: str
    ok: bool
    discovered: bool
    verified: bool
    data: dict[str, Any]
    barrier: dict[str, Any] | None
    state_persisted: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "capability": self.capability,
            "discovered": self.discovered,
            "verified": self.verified,
            "authorized": True,
            "data": self.data,
            "barrier": self.barrier,
            "state_persisted": self.state_persisted,
        }


def _memory_info() -> dict[str, int]:
    result: dict[str, int] = {}
    text = _read_text(PROC / "meminfo", "")
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z_()]+):\s+(\d+)", line)
        if match:
            result[match.group(1).lower() + "_kib"] = int(match.group(2))
    return result


def probe_hardware() -> tuple[dict[str, Any], dict[str, Any]]:
    serial = "unknown"
    cpuinfo = _read_text(PROC / "cpuinfo", "")
    for line in cpuinfo.splitlines():
        if line.lower().startswith("serial") and ":" in line:
            serial = line.split(":", 1)[1].strip()
            break
    data = {
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "model": _read_text(
            PROC / "device-tree" / "model", _read_text(SYS / "firmware/devicetree/base/model")
        ),
        "serial": serial,
        "memory": _memory_info(),
    }
    if not data["architecture"]:
        raise LocalBarrier("architecture-unavailable")
    return data, {"architecture": data["architecture"], "model": data["model"]}


def _ipv4_routes() -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    text = _read_text(PROC / "net" / "route", "")
    for line in text.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 8:
            continue
        routes.append(
            {
                "interface": fields[0],
                "destination_hex": fields[1],
                "gateway_hex": fields[2],
                "flags_hex": fields[3],
                "metric": int(fields[6]) if fields[6].isdigit() else None,
                "mask_hex": fields[7],
                "default": fields[1] == "00000000",
            }
        )
    return routes


def _ip_addresses() -> tuple[dict[str, Any], str | None]:
    executable = shutil.which("ip")
    if not executable:
        return {}, "ip-command-unavailable-addresses-limited-to-sysfs"
    try:
        completed = subprocess.run(
            [executable, "-j", "address", "show"],
            check=False,
            capture_output=True,
            text=True,
            timeout=4,
        )
        if completed.returncode != 0:
            return {}, f"ip-address-returned-{completed.returncode}"
        values = json.loads(completed.stdout)
        result: dict[str, Any] = {}
        for item in values if isinstance(values, list) else []:
            name = item.get("ifname")
            if not name:
                continue
            result[name] = [
                {
                    "family": address.get("family"),
                    "local": address.get("local"),
                    "prefixlen": address.get("prefixlen"),
                    "scope": address.get("scope"),
                }
                for address in item.get("addr_info", [])
            ]
        return result, None
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return {}, f"ip-address-limited:{type(exc).__name__}"


def probe_network() -> tuple[dict[str, Any], dict[str, Any]]:
    root = SYS / "class" / "net"
    if not root.is_dir():
        raise LocalBarrier("sysfs-network-interface-unavailable")
    addresses, limitation = _ip_addresses()
    interfaces = []
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        interfaces.append(
            {
                "name": path.name,
                "state": _read_text(path / "operstate"),
                "mac": _read_text(path / "address"),
                "mtu": _read_int(path / "mtu"),
                "carrier": _read_int(path / "carrier"),
                "addresses": addresses.get(path.name, []),
            }
        )
    dns = []
    for line in _read_text(Path("/etc/resolv.conf"), "").splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] == "nameserver":
            dns.append(fields[1])
    routes = _ipv4_routes()
    data = {
        "interfaces": interfaces,
        "default_routes": [route for route in routes if route["default"]],
        "routes": routes,
        "dns_servers": dns,
        "limitations": [limitation] if limitation else [],
    }
    return data, {
        "interfaces": len(interfaces),
        "interfaces_up": sum(item["state"] == "up" for item in interfaces),
        "default_routes": len(data["default_routes"]),
    }


def probe_storage() -> tuple[dict[str, Any], dict[str, Any]]:
    root = SYS / "class" / "block"
    if not root.is_dir():
        raise LocalBarrier("sysfs-block-interface-unavailable")
    devices = []
    for path in sorted(root.iterdir(), key=lambda item: item.name)[:256]:
        sectors = _read_int(path / "size", 0) or 0
        devices.append(
            {
                "name": path.name,
                "bytes": sectors * 512,
                "read_only": bool(_read_int(path / "ro", 0)),
                "removable": bool(_read_int(path / "removable", 0)),
                "model": _read_text(path / "device" / "model", "unknown"),
                "partition": (path / "partition").exists(),
            }
        )
    root_usage: dict[str, int] | None = None
    try:
        usage = shutil.disk_usage("/")
        root_usage = {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
        }
    except OSError:
        pass
    mounts = []
    for line in _read_text(PROC / "mounts", "").splitlines()[:512]:
        fields = line.split()
        if len(fields) >= 4:
            mounts.append(
                {
                    "source": fields[0],
                    "mountpoint": fields[1],
                    "filesystem": fields[2],
                    "read_only": "ro" in fields[3].split(","),
                }
            )
    data = {"block_devices": devices, "mounts": mounts, "root_filesystem": root_usage}
    return data, {
        "block_devices": len(devices),
        "removable_devices": sum(item["removable"] for item in devices),
        "root_free_bytes": root_usage["free_bytes"] if root_usage else None,
    }


def probe_usb() -> tuple[dict[str, Any], dict[str, Any]]:
    root = SYS / "bus" / "usb" / "devices"
    if not root.is_dir():
        raise LocalBarrier("sysfs-usb-interface-unavailable")
    devices = []
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        vendor = _read_text(path / "idVendor", "")
        product_id = _read_text(path / "idProduct", "")
        if not vendor or not product_id:
            continue
        devices.append(
            {
                "sysfs_name": path.name,
                "vendor_id": vendor,
                "product_id": product_id,
                "manufacturer": _read_text(path / "manufacturer", "unknown"),
                "product": _read_text(path / "product", "unknown"),
                "serial": _read_text(path / "serial", "unknown"),
                "authorized_by_kernel": bool(_read_int(path / "authorized", 0)),
            }
        )
    return {"devices": devices}, {"devices": len(devices)}


def _pressure() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in ("cpu", "io", "memory"):
        text = _read_text(PROC / "pressure" / name, "")
        if text:
            result[name] = text.splitlines()
    return result


def probe_processes() -> tuple[dict[str, Any], dict[str, Any]]:
    if not PROC.is_dir():
        raise LocalBarrier("procfs-unavailable")
    processes = []
    for path in sorted(
        (item for item in PROC.iterdir() if item.name.isdigit()),
        key=lambda item: int(item.name),
    )[:8192]:
        comm = _read_text(path / "comm", "unknown")
        statm = _read_text(path / "statm", "").split()
        rss_pages = int(statm[1]) if len(statm) > 1 and statm[1].isdigit() else 0
        processes.append({"pid": int(path.name), "name": comm, "rss_pages": rss_pages})
    page_size = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
    top = sorted(processes, key=lambda item: item["rss_pages"], reverse=True)[:10]
    for item in top:
        item["rss_bytes"] = item.pop("rss_pages") * page_size
    load_fields = _read_text(PROC / "loadavg", "").split()
    temperature_millic = _read_int(SYS / "class" / "thermal" / "thermal_zone0" / "temp")
    uptime_fields = _read_text(PROC / "uptime", "").split()
    data = {
        "process_count": len(processes),
        "top_memory_processes": top,
        "load_1m_5m_15m": load_fields[:3],
        "uptime_seconds": float(uptime_fields[0]) if uptime_fields else None,
        "temperature_celsius": temperature_millic / 1000 if temperature_millic is not None else None,
        "memory": _memory_info(),
        "pressure": _pressure(),
    }
    return data, {
        "process_count": len(processes),
        "load_1m": load_fields[0] if load_fields else None,
        "temperature_celsius": data["temperature_celsius"],
    }


def probe_services() -> tuple[dict[str, Any], dict[str, Any]]:
    executable = shutil.which("systemctl")
    if not executable:
        raise LocalBarrier("systemctl-unavailable")
    command = [
        executable,
        "list-units",
        "--type=service",
        "--all",
        "--no-legend",
        "--no-pager",
        "--plain",
    ]
    try:
        completed = subprocess.run(
            command, check=False, capture_output=True, text=True, timeout=8
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LocalBarrier(f"systemctl-failed:{type(exc).__name__}") from exc
    if completed.returncode not in (0, 1):
        detail = completed.stderr.strip().replace("\n", " ")[:160]
        raise LocalBarrier(f"systemctl-returned-{completed.returncode}:{detail}")
    services = []
    for line in completed.stdout.splitlines()[:512]:
        fields = line.strip().lstrip("●").split(None, 4)
        if len(fields) < 4 or not fields[0].endswith(".service"):
            continue
        services.append(
            {
                "unit": fields[0],
                "load": fields[1],
                "active": fields[2],
                "sub": fields[3],
                "description": fields[4] if len(fields) > 4 else "",
            }
        )
    failed = [item for item in services if item["active"] == "failed"]
    data = {"services": services, "failed": failed}
    return data, {
        "services": len(services),
        "active": sum(item["active"] == "active" for item in services),
        "failed": len(failed),
    }


PROBES: dict[str, Callable[[], tuple[dict[str, Any], dict[str, Any]]]] = {
    "hardware": probe_hardware,
    "network": probe_network,
    "storage": probe_storage,
    "usb": probe_usb,
    "processes": probe_processes,
    "services": probe_services,
}


def run_probe(name: str, store: StateStore) -> ProbeResult:
    if name not in PROBES:
        return ProbeResult(
            capability=name,
            ok=False,
            discovered=False,
            verified=False,
            data={},
            barrier={"scope": name, "reason": "unknown-probe", "observed_at": _utc_now()},
            state_persisted=False,
        )
    try:
        data, summary = PROBES[name]()
        discovered = True
        verified = True
        barrier = None
    except Exception as exc:  # every probe is an independent failure boundary
        data = {}
        summary = {}
        discovered = not isinstance(exc, LocalBarrier) or "unavailable" not in str(exc)
        verified = False
        barrier = {
            "scope": name,
            "reason": f"{type(exc).__name__}:{exc}",
            "observed_at": _utc_now(),
        }
    persisted = True
    try:
        store.record_probe(
            name,
            discovered=discovered,
            verified=verified,
            summary=summary,
            barrier=barrier["reason"] if barrier else None,
        )
    except (OSError, LocalBarrier) as exc:
        persisted = False
        persistence = f"capability-state-not-persisted:{type(exc).__name__}:{exc}"
        if barrier:
            barrier["persistence"] = persistence
        else:
            data["local_state_barrier"] = persistence
    return ProbeResult(name, verified, discovered, verified, data, barrier, persisted)


def capability_inventory(store: StateStore) -> dict[str, Any]:
    state = store.load()
    inventory = []
    stored = state.get("capabilities", {})
    for name, definition in CAPABILITY_DEFINITIONS.items():
        current = stored.get(name, {})
        inventory.append(
            {
                "name": name,
                "description": definition["description"],
                "kind": definition["kind"],
                "implemented": True,
                "discovered": bool(current.get("discovered")),
                "verified": bool(current.get("verified")),
                "authorized": bool(current.get("authorized")),
                "authorization": definition["authorization"],
                "status": current.get("status", "unknown"),
                "last_observed_at": current.get("last_observed_at"),
                "barrier": current.get("barrier"),
            }
        )
    return {
        "ok": True,
        "capability": "capabilities",
        "state_file": str(store.path),
        "observation_generation": state.get("observation_generation", 0),
        "inventory": inventory,
        "state_barrier": state.get("state_barrier"),
    }


def frontier(store: StateStore) -> dict[str, Any]:
    state = store.load()
    capabilities = state.get("capabilities", {})
    next_name = None
    reason = "all-read-only-probes-verified"
    for name in PROBE_ORDER:
        entry = capabilities.get(name, {})
        if entry.get("barrier"):
            next_name = name
            reason = "retry-local-barrier"
            break
        if not entry.get("verified"):
            next_name = name
            reason = (
                "verify-discovered-capability"
                if entry.get("discovered")
                else "discover-local-capability"
            )
            break
    codelation = _chain_state()
    result = {
        "ok": True,
        "capability": "frontier",
        "next_gap": next_name,
        "reason": reason,
        "suggested_command": f"rescan {next_name}" if next_name else None,
        "local_barriers": [
            entry["barrier"]
            for name in PROBE_ORDER
            if (entry := capabilities.get(name, {})).get("barrier")
        ],
        "codelation_frontier": {
            "next_gap": codelation.get("next_gap"),
            "blocked_reason": codelation.get("blocked_reason"),
        },
    }

    def change(current: dict[str, Any]) -> None:
        current["frontier"] = {
            "next_gap": next_name,
            "reason": reason,
            "evaluated_at": _utc_now(),
        }

    try:
        store.mutate(change)
    except (OSError, LocalBarrier) as exc:
        result["state_persisted"] = False
        result["state_barrier"] = f"{type(exc).__name__}:{exc}"
    else:
        result["state_persisted"] = True
    return result


def observe(store: StateStore, name: str | None = None) -> dict[str, Any]:
    state = store.load()
    if name:
        name = PROBE_ALIASES.get(name, name)
        entry = state.get("capabilities", {}).get(name)
        if entry is None:
            return {
                "ok": False,
                "capability": "observe",
                "barrier": {
                    "scope": name,
                    "reason": "unknown-capability",
                    "observed_at": _utc_now(),
                },
            }
        return {
            "ok": True,
            "capability": "observe",
            "observed_capability": name,
            "state": entry,
        }
    return {"ok": True, "capability": "observe", "state": state}


def rescan(store: StateStore, name: str = "all") -> dict[str, Any]:
    normalized_name = PROBE_ALIASES.get(name, name)
    names = list(PROBE_ORDER) if normalized_name == "all" else [normalized_name]
    results = [run_probe(item, store).as_dict() for item in names]
    return {
        "ok": all(item["ok"] for item in results),
        "capability": "rescan",
        "scope": name,
        "results": results,
        "verified": sum(item["verified"] for item in results),
        "barriers": [item["barrier"] for item in results if item["barrier"]],
        "continuation_allowed": True,
    }


def selftest() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.append(
        {
            "name": "bounded-probe-registry",
            "ok": set(PROBE_ORDER) == set(PROBES),
            "detail": ",".join(PROBE_ORDER),
        }
    )
    field_dir = CODELATION / "field"
    if not field_dir.is_dir():
        checks.append(
            {"name": "codelation-field", "ok": False, "detail": "codelation-field-missing"}
        )
    else:
        sys.path.insert(0, str(field_dir))
        try:
            from local_capability_verification import verify_local_capability_for_gap
            from native_gap_catalog import get_native_semantic_gap

            gap = get_native_semantic_gap("io_safe_port_choice")
            if gap is None:
                raise LocalBarrier("io-safe-port-gap-missing")
            verification = verify_local_capability_for_gap(gap, "io-plan")
            checks.append(
                {
                    "name": "codelation-field",
                    "ok": bool(verification.verified),
                    "detail": f"io-plan={verification.invocation_output}",
                }
            )
        except Exception as exc:
            checks.append(
                {
                    "name": "codelation-field",
                    "ok": False,
                    "detail": f"{type(exc).__name__}:{exc}",
                }
            )
    return {
        "ok": all(check["ok"] for check in checks),
        "capability": "selftest",
        "checks": checks,
        "continuation_allowed": True,
    }


def status(store: StateStore) -> dict[str, Any]:
    state = _chain_state()
    return {
        "ok": True,
        "capability": "status",
        "aurum_pi3_version": VERSION,
        "release_id": RELEASE_ID,
        "target": TARGET,
        "substrate": "raspberry-pi-os-hardware-compatibility-layer",
        "hardware": run_probe("hardware", store).as_dict(),
        "capability_state": {
            "path": str(store.path),
            "observation_generation": store.load().get("observation_generation", 0),
        },
        "aurum": {
            "completed_generations": state.get("completed_generations"),
            "latest_completed_gap": state.get("latest_completed_gap"),
            "next_gap": state.get("next_gap"),
            "blocked_reason": state.get("blocked_reason"),
            "blocked_output": state.get("blocked_output"),
            "trusted_for_continuation": (state.get("workflow_verification") or {}).get(
                "trusted_for_continuation"
            ),
        },
    }


def show_field() -> dict[str, Any]:
    state = _chain_state()
    return {
        "ok": True,
        "capability": "field",
        "native": state.get("reusable_native_capabilities") or [],
        "local": state.get("reusable_local_capabilities") or [],
    }


def explicit_power(action: str, confirmation: str | None) -> dict[str, Any]:
    if action not in {"reboot", "poweroff"}:
        return {
            "ok": False,
            "capability": action,
            "barrier": {"scope": action, "reason": "action-not-allowlisted"},
        }
    if confirmation != "confirm":
        return {
            "ok": False,
            "capability": action,
            "authorized": False,
            "performed": False,
            "barrier": {
                "scope": action,
                "reason": f"explicit-confirmation-required: use '{action} confirm'",
            },
        }
    executable = f"/sbin/{action}"
    if not Path(executable).exists():
        return {
            "ok": False,
            "capability": action,
            "authorized": True,
            "performed": False,
            "barrier": {"scope": action, "reason": f"executable-unavailable:{executable}"},
        }
    completed = subprocess.run([executable], check=False)
    return {
        "ok": completed.returncode == 0,
        "capability": action,
        "authorized": True,
        "performed": True,
        "returncode": completed.returncode,
    }


def _run_updater(arguments: list[str], capability: str) -> dict[str, Any]:
    if not UPDATER.is_file():
        return {
            "ok": False,
            "capability": capability,
            "barrier": {"scope": capability, "reason": "updater-bootstrap-required"},
            "continuation_allowed": True,
        }
    try:
        completed = subprocess.run(
            [sys.executable, str(UPDATER), *arguments],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "ok": False,
            "capability": capability,
            "barrier": {
                "scope": capability,
                "reason": f"{type(exc).__name__}:{exc}",
            },
            "continuation_allowed": True,
        }
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {
            "status": "error",
            "code": "updater-output-invalid",
            "message": completed.stdout.strip()[-1000:],
        }
    payload["ok"] = completed.returncode == 0 and payload.get("status") != "error"
    payload["capability"] = capability
    payload["continuation_allowed"] = True
    if not payload["ok"] and "barrier" not in payload:
        payload["barrier"] = {
            "scope": capability,
            "reason": f"{payload.get('code', 'updater-failed')}:{payload.get('message', '')}",
        }
    return payload


def update_command(command: str, arguments: list[str]) -> dict[str, Any]:
    if command in {"update-check", "update"}:
        usage = f"{command} <manifest-source> <manifest-sha256> [authorize-network]"
        if len(arguments) not in {2, 3}:
            return {"ok": False, "capability": command, "barrier": {"scope": command, "reason": usage}}
        authorize_network = len(arguments) == 3 and arguments[2].lower() == "authorize-network"
        if len(arguments) == 3 and not authorize_network:
            return {
                "ok": False,
                "capability": command,
                "barrier": {"scope": command, "reason": "network-authorization-token-invalid"},
            }
        updater_arguments = [
            "check" if command == "update-check" else "request",
            "--manifest",
            arguments[0],
            "--manifest-sha256",
            arguments[1].lower(),
        ]
        if authorize_network:
            updater_arguments.append("--authorize-network")
        return _run_updater(updater_arguments, command)
    if command == "update-status" and not arguments:
        return _run_updater(["status"], command)
    if command == "rollback" and len(arguments) == 1 and arguments[0].lower() == "confirm":
        return _run_updater(["request-rollback"], command)
    usage = "update-status | rollback confirm"
    return {"ok": False, "capability": command, "barrier": {"scope": command, "reason": usage}}


HELP = {
    "ok": True,
    "capability": "help",
    "commands": [
        "status",
        "capabilities",
        "hardware",
        "network",
        "storage",
        "usb",
        "processes | health | system-health",
        "services",
        "observe [capability]",
        "rescan [capability|all]",
        "frontier | next-gap",
        "field",
        "selftest",
        "json <command>",
        "update-check <manifest-source> <manifest-sha256> [authorize-network]",
        "update <manifest-source> <manifest-sha256> [authorize-network]",
        "update-status",
        "rollback confirm",
        "reboot confirm",
        "poweroff confirm",
        "help",
    ],
    "arbitrary_shell": False,
}


def execute(tokens: list[str], store: StateStore) -> dict[str, Any]:
    if not tokens or tokens[0] in {"help", "?"}:
        return HELP
    command = tokens[0].lower()
    arguments = tokens[1:]
    if command == "json":
        return execute(arguments, store)
    if command == "status":
        return status(store)
    if command == "capabilities":
        return capability_inventory(store)
    if command in PROBES:
        return run_probe(command, store).as_dict()
    if command in PROBE_ALIASES:
        result = run_probe(PROBE_ALIASES[command], store).as_dict()
        result["capability"] = command
        result["observed_capability"] = PROBE_ALIASES[command]
        return result
    if command == "observe":
        return observe(store, arguments[0] if arguments else None)
    if command == "rescan":
        return rescan(store, arguments[0] if arguments else "all")
    if command in {"frontier", "next-gap"}:
        return frontier(store)
    if command == "field":
        return show_field()
    if command == "selftest":
        return selftest()
    if command in {"update-check", "update", "update-status", "rollback"}:
        return update_command(command, arguments)
    if command in {"reboot", "poweroff"}:
        return explicit_power(command, arguments[0].lower() if len(arguments) == 1 else None)
    return {
        "ok": False,
        "capability": "command-routing",
        "barrier": {"scope": command, "reason": "unknown-command"},
        "continuation_allowed": True,
        "suggested_command": "capabilities",
    }


def _emit(payload: dict[str, Any], compact: bool) -> None:
    print(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":") if compact else None,
            indent=None if compact else 2,
        ),
        flush=True,
    )


def _selftest_detail(result: dict[str, Any]) -> str:
    return ";".join(
        f"{check.get('name')}={check.get('detail')}"
        for check in result.get("checks", [])
        if isinstance(check, dict)
    )


def _write_readiness(result: dict[str, Any], hardware_data: dict[str, Any]) -> None:
    if not READINESS_FILE:
        return
    path = Path(READINESS_FILE)
    payload = {
        "schema": "aurum-pi3-readiness-v1",
        "version": VERSION,
        "release_id": RELEASE_ID,
        "target": TARGET,
        "architecture": hardware_data.get("architecture", "unknown"),
        "selftest": "ok" if result.get("ok") else "failed",
        "detail": _selftest_detail(result),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ["--selftest-json"]:
        result = selftest()
        print(
            json.dumps(
                {
                    "version": VERSION,
                    "release_id": RELEASE_ID,
                    "target": TARGET,
                    "selftest": "ok" if result.get("ok") else "failed",
                    "detail": _selftest_detail(result),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return 0 if result.get("ok") else 1
    compact = False
    if arguments and arguments[0] == "--json":
        compact = True
        arguments.pop(0)
    store = StateStore()
    try:
        store.ensure_initialized()
    except (OSError, LocalBarrier):
        pass

    if arguments:
        _emit(execute(arguments, store), compact=compact)
        return 0

    startup_test = selftest()
    hardware_result = run_probe("hardware", store)
    data = hardware_result.data
    _write_readiness(startup_test, data)
    print(
        "AURUM_PI3_READY "
        f"version={VERSION} release={RELEASE_ID} target={TARGET} "
        f"arch={data.get('architecture', 'unknown')} "
        f"kernel={data.get('kernel', 'unknown')} "
        f"selftest={'ok' if startup_test['ok'] else 'partial'}",
        flush=True,
    )
    print(
        "Type 'help'. Semantic probes are read-only; network updates, rollback, reboot, and poweroff require explicit authorization.",
        flush=True,
    )

    while True:
        try:
            line = input("aurum-pi3> ").strip()
        except EOFError:
            return 0
        except KeyboardInterrupt:
            print("", flush=True)
            continue
        try:
            tokens = shlex.split(line)
        except ValueError as exc:
            _emit(
                {"ok": False, "barrier": {"scope": "command-parse", "reason": str(exc)}},
                compact=True,
            )
            continue
        json_requested = bool(tokens and tokens[0].lower() == "json")
        _emit(execute(tokens, store), compact=json_requested)


if __name__ == "__main__":
    raise SystemExit(main())
