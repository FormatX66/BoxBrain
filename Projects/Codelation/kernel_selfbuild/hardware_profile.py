from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import platform
from typing import Iterable


@dataclass(frozen=True)
class DeviceObservation:
    bus: str
    address: str
    vendor: str | None
    device: str | None
    class_code: str | None
    modalias: str | None
    driver: str | None


@dataclass(frozen=True)
class MachineProfile:
    architecture: str
    machine: str
    kernel_release: str
    firmware: str
    cpu_model: str | None
    devices: tuple[DeviceObservation, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip() or None
    except (FileNotFoundError, PermissionError, OSError):
        return None


def _read_hexish(path: Path) -> str | None:
    value = _read_text(path)
    return value.lower() if value else None


def _driver_name(device_dir: Path) -> str | None:
    try:
        return device_dir.joinpath("driver").resolve(strict=True).name
    except (FileNotFoundError, RuntimeError, OSError):
        return None


def _iter_bus_devices(sys_root: Path, bus: str) -> Iterable[DeviceObservation]:
    root = sys_root / "bus" / bus / "devices"
    if not root.is_dir():
        return ()
    out: list[DeviceObservation] = []
    for item in sorted(root.iterdir(), key=lambda p: p.name):
        out.append(
            DeviceObservation(
                bus=bus,
                address=item.name,
                vendor=_read_hexish(item / "vendor"),
                device=_read_hexish(item / "device"),
                class_code=_read_hexish(item / "class"),
                modalias=_read_text(item / "modalias"),
                driver=_driver_name(item),
            )
        )
    return tuple(out)


def _iter_platform_devices(sys_root: Path) -> Iterable[DeviceObservation]:
    root = sys_root / "bus" / "platform" / "devices"
    if not root.is_dir():
        return ()
    out: list[DeviceObservation] = []
    for item in sorted(root.iterdir(), key=lambda p: p.name):
        alias = _read_text(item / "modalias")
        driver = _driver_name(item)
        if alias or driver:
            out.append(
                DeviceObservation(
                    bus="platform",
                    address=item.name,
                    vendor=None,
                    device=None,
                    class_code=None,
                    modalias=alias,
                    driver=driver,
                )
            )
    return tuple(out)


def _cpu_model(proc_root: Path) -> str | None:
    cpuinfo = _read_text(proc_root / "cpuinfo")
    if not cpuinfo:
        return None
    preferred = ("model name", "hardware", "processor")
    lines = cpuinfo.splitlines()
    for key in preferred:
        for line in lines:
            if ":" not in line:
                continue
            left, right = line.split(":", 1)
            if left.strip().casefold() == key:
                value = right.strip()
                if value:
                    return value
    return None


def normalize_arch(machine: str) -> str:
    value = machine.casefold()
    if value in {"x86_64", "amd64"}:
        return "x86_64"
    if value in {"aarch64", "arm64"}:
        return "arm64"
    if value.startswith("arm"):
        return "arm"
    return value or "unknown"


def collect_machine_profile(
    *,
    sys_root: Path = Path("/sys"),
    proc_root: Path = Path("/proc"),
    machine: str | None = None,
    kernel_release: str | None = None,
) -> MachineProfile:
    machine_value = machine or platform.machine()
    devices = tuple(
        sorted(
            (
                *tuple(_iter_bus_devices(sys_root, "pci")),
                *tuple(_iter_bus_devices(sys_root, "usb")),
                *tuple(_iter_platform_devices(sys_root)),
            ),
            key=lambda item: (item.bus, item.address),
        )
    )
    firmware = "uefi" if (sys_root / "firmware" / "efi").exists() else (
        "device-tree" if (sys_root / "firmware" / "devicetree").exists() else "legacy-or-unknown"
    )
    return MachineProfile(
        architecture=normalize_arch(machine_value),
        machine=machine_value,
        kernel_release=kernel_release or platform.release(),
        firmware=firmware,
        cpu_model=_cpu_model(proc_root),
        devices=devices,
    )


__all__ = [
    "DeviceObservation",
    "MachineProfile",
    "collect_machine_profile",
    "normalize_arch",
]
