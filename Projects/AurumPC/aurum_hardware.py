#!/usr/bin/env python3
"""Read-only hardware evidence collection for the Aurum PC live seed.

The live seed uses Linux only as a hardware compatibility substrate.  This
module deliberately learns from procfs/sysfs and writes evidence only beneath
/run (tmpfs) by default, so inventory never requires network access or writes
to an internal disk.
"""
from __future__ import annotations

import json
import os
import platform
import time
from pathlib import Path
from typing import Any, Iterable

PROFILE_SCHEMA = "aurum-x86-machine-profile-v1"
PLAN_SCHEMA = "aurum-x86-kernel-driver-plan-v1"
DEFAULT_PROFILE = Path("/run/aurum/machine-profile.json")
DEFAULT_PLAN = Path("/run/aurum/kernel-driver-plan.json")


def _read(path: Path, default: str | None = None) -> str | None:
    try:
        value = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return default
    return value or default


def _integer(path: Path) -> int | None:
    value = _read(path)
    if value is None:
        return None
    try:
        return int(value, 0)
    except ValueError:
        return None


def _driver_name(device: Path) -> str | None:
    link = device / "driver"
    try:
        return link.resolve(strict=True).name
    except OSError:
        return None


def _sorted_dirs(path: Path) -> list[Path]:
    try:
        return sorted((entry for entry in path.iterdir() if entry.is_dir()), key=lambda entry: entry.name)
    except OSError:
        return []


def _cpu(proc_root: Path) -> dict[str, Any]:
    processors = 0
    first: dict[str, str] = {}
    text = _read(proc_root / "cpuinfo", "") or ""
    for stanza in text.split("\n\n"):
        fields: dict[str, str] = {}
        for line in stanza.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
        if not fields:
            continue
        processors += 1
        if not first:
            first = fields
    flags = (first.get("flags") or first.get("Features") or "").split()
    return {
        "logical_processors": processors or None,
        "vendor": first.get("vendor_id") or first.get("CPU implementer"),
        "model_name": first.get("model name") or first.get("Processor"),
        "family": first.get("cpu family"),
        "model": first.get("model"),
        "stepping": first.get("stepping"),
        "flags": sorted(set(flags)),
    }


def _memory(proc_root: Path) -> dict[str, Any]:
    total_kib: int | None = None
    text = _read(proc_root / "meminfo", "") or ""
    for line in text.splitlines():
        if line.startswith("MemTotal:"):
            fields = line.split()
            if len(fields) >= 2 and fields[1].isdigit():
                total_kib = int(fields[1])
            break
    return {"total_kib": total_kib}


def _firmware(sys_root: Path) -> dict[str, Any]:
    dmi = sys_root / "class" / "dmi" / "id"
    return {
        "mode": "uefi" if (sys_root / "firmware" / "efi").exists() else "bios-or-unknown",
        "sys_vendor": _read(dmi / "sys_vendor"),
        "product_name": _read(dmi / "product_name"),
        "product_version": _read(dmi / "product_version"),
        "board_vendor": _read(dmi / "board_vendor"),
        "board_name": _read(dmi / "board_name"),
        "bios_vendor": _read(dmi / "bios_vendor"),
        "bios_version": _read(dmi / "bios_version"),
    }


def _pci(sys_root: Path) -> list[dict[str, Any]]:
    devices = []
    for device in _sorted_dirs(sys_root / "bus" / "pci" / "devices"):
        devices.append(
            {
                "address": device.name,
                "vendor": _read(device / "vendor"),
                "device": _read(device / "device"),
                "class": _read(device / "class"),
                "subsystem_vendor": _read(device / "subsystem_vendor"),
                "subsystem_device": _read(device / "subsystem_device"),
                "modalias": _read(device / "modalias"),
                "driver": _driver_name(device),
            }
        )
    return devices


def _usb(sys_root: Path) -> list[dict[str, Any]]:
    devices = []
    for device in _sorted_dirs(sys_root / "bus" / "usb" / "devices"):
        vendor = _read(device / "idVendor")
        product = _read(device / "idProduct")
        if vendor is None or product is None:
            continue
        devices.append(
            {
                "address": device.name,
                "vendor": vendor,
                "product": product,
                "manufacturer": _read(device / "manufacturer"),
                "product_name": _read(device / "product"),
                "serial": _read(device / "serial"),
                "device_class": _read(device / "bDeviceClass"),
                "modalias": _read(device / "modalias"),
                "driver": _driver_name(device),
            }
        )
    return devices


def _block(sys_root: Path) -> list[dict[str, Any]]:
    devices = []
    for entry in _sorted_dirs(sys_root / "class" / "block"):
        # Partitions carry a partition marker; inventory them, but distinguish
        # them from the controller-backed whole device.
        is_partition = (entry / "partition").exists()
        devices.append(
            {
                "name": entry.name,
                "partition": is_partition,
                "removable": _integer(entry / "removable"),
                "size_sectors": _integer(entry / "size"),
                "logical_block_size": _integer(entry / "queue" / "logical_block_size"),
                "vendor": _read(entry / "device" / "vendor"),
                "model": _read(entry / "device" / "model"),
                "revision": _read(entry / "device" / "rev"),
                "modalias": _read(entry / "device" / "modalias"),
                "driver": _driver_name(entry / "device"),
            }
        )
    return devices


def _input(sys_root: Path) -> list[dict[str, Any]]:
    devices = []
    for entry in _sorted_dirs(sys_root / "class" / "input"):
        if not entry.name.startswith("event"):
            continue
        device = entry / "device"
        devices.append(
            {
                "event": entry.name,
                "name": _read(device / "name"),
                "phys": _read(device / "phys"),
                "modalias": _read(device / "modalias"),
                "driver": _driver_name(device),
            }
        )
    return devices


def _graphics(sys_root: Path) -> list[dict[str, Any]]:
    devices = []
    for entry in _sorted_dirs(sys_root / "class" / "drm"):
        if not entry.name.startswith("card") or "-" in entry.name:
            continue
        device = entry / "device"
        devices.append(
            {
                "card": entry.name,
                "vendor": _read(device / "vendor"),
                "device": _read(device / "device"),
                "class": _read(device / "class"),
                "modalias": _read(device / "modalias"),
                "driver": _driver_name(device),
            }
        )
    return devices


def _network(sys_root: Path) -> list[dict[str, Any]]:
    interfaces = []
    for entry in _sorted_dirs(sys_root / "class" / "net"):
        if entry.name == "lo":
            continue
        device = entry / "device"
        interfaces.append(
            {
                "name": entry.name,
                "mac": _read(entry / "address"),
                "carrier": _integer(entry / "carrier"),
                "operstate": _read(entry / "operstate"),
                "mtu": _integer(entry / "mtu"),
                "modalias": _read(device / "modalias"),
                "driver": _driver_name(device),
            }
        )
    return interfaces


def _modules(proc_root: Path) -> list[str]:
    text = _read(proc_root / "modules", "") or ""
    return sorted({line.split()[0] for line in text.splitlines() if line.split()})


def _mounts(proc_root: Path) -> list[dict[str, str]]:
    evidence = []
    text = _read(proc_root / "mounts", "") or ""
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        source, target, fs_type, options = fields[:4]
        if target == "/" or "live" in target or source.startswith("/dev/"):
            evidence.append(
                {"source": source, "target": target, "filesystem": fs_type, "options": options}
            )
    return evidence


def collect_hardware_profile(
    *, sys_root: Path = Path("/sys"), proc_root: Path = Path("/proc")
) -> dict[str, Any]:
    """Capture exact observed hardware without mutating hardware or disks."""
    return {
        "schema": PROFILE_SCHEMA,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "observation_policy": {
            "read_only": True,
            "network_required": False,
            "internal_disk_writes": False,
            "evidence_default_location": "/run/aurum",
        },
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "cmdline": _read(proc_root / "cmdline", ""),
        "cpu": _cpu(proc_root),
        "memory": _memory(proc_root),
        "firmware": _firmware(sys_root),
        "pci_devices": _pci(sys_root),
        "usb_devices": _usb(sys_root),
        "block_devices": _block(sys_root),
        "input_devices": _input(sys_root),
        "graphics_devices": _graphics(sys_root),
        "network_interfaces": _network(sys_root),
        "loaded_modules": _modules(proc_root),
        "boot_mount_evidence": _mounts(proc_root),
    }


def _bound_drivers(profile: dict[str, Any], collections: Iterable[str]) -> list[str]:
    drivers: set[str] = set()
    for collection in collections:
        for device in profile.get(collection, []):
            driver = device.get("driver")
            if driver:
                drivers.add(driver)
    return sorted(drivers)


def derive_kernel_driver_plan(profile: dict[str, Any]) -> dict[str, Any]:
    """Derive a conservative exact-machine plan from observed bound devices."""
    collections = (
        "pci_devices",
        "usb_devices",
        "block_devices",
        "input_devices",
        "graphics_devices",
        "network_interfaces",
    )
    unresolved = []
    for collection in collections:
        for device in profile.get(collection, []):
            if device.get("modalias") and not device.get("driver"):
                unresolved.append(
                    {
                        "collection": collection,
                        "identity": device.get("address") or device.get("name") or device.get("event") or device.get("card"),
                        "modalias": device.get("modalias"),
                        "action": "resolve-existing-driver-before-synthesis",
                    }
                )
    return {
        "schema": PLAN_SCHEMA,
        "source_profile_schema": profile.get("schema"),
        "architecture": profile.get("architecture"),
        "observed_kernel": profile.get("kernel"),
        "seed_recovery": {
            "preserve_current_removable_boot": True,
            "overwrite_only_known_good_boot": False,
            "first_generated_boot": "a-b-removable-media-trial",
            "automatic_fallback_required": True,
        },
        "required_existing_drivers": _bound_drivers(profile, collections),
        "loaded_modules_observed": profile.get("loaded_modules", []),
        "unresolved_devices": unresolved,
        "compile_policy": {
            "preserve_boot_storage_filesystem_console_input_network_firmware_bus_support": True,
            "optional_hotplug_as_modules": True,
            "compile_before_physical_load": True,
            "static_or_vm_verify_before_physical_boot": True,
        },
        "physical_driver_policy": {
            "one_target_at_a_time": True,
            "persistent_backup_before_swap": True,
            "behavior_comparison_required": True,
            "automatic_restore_required": True,
        },
        "separate_explicit_gate_required": [
            "storage-or-boot-critical-replacement",
            "firmware-nvram-otp-fuse-write",
            "power-clock-voltage-thermal-reset-control",
            "unbounded-raw-mmio-pio",
        ],
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def capture_hardware_evidence(
    *,
    profile_path: Path = DEFAULT_PROFILE,
    plan_path: Path = DEFAULT_PLAN,
    sys_root: Path = Path("/sys"),
    proc_root: Path = Path("/proc"),
) -> tuple[dict[str, Any], dict[str, Any]]:
    profile = collect_hardware_profile(sys_root=sys_root, proc_root=proc_root)
    plan = derive_kernel_driver_plan(profile)
    _atomic_json(profile_path, profile)
    _atomic_json(plan_path, plan)
    return profile, plan
