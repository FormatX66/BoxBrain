from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .driver_plan import DriverWorkItem, classify_device
from .hardware_profile import DeviceObservation, MachineProfile


@dataclass(frozen=True)
class HardwareDelta:
    added: tuple[DeviceObservation, ...]
    removed: tuple[DeviceObservation, ...]
    driver_work: tuple[DriverWorkItem, ...]
    full_kernel_rebuild_required: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _identity(device: DeviceObservation) -> tuple[str, str, str | None, str | None, str | None]:
    return (device.bus, device.address, device.vendor, device.device, device.modalias)


def diff_hardware(previous: MachineProfile, current: MachineProfile) -> HardwareDelta:
    before = {_identity(device): device for device in previous.devices}
    after = {_identity(device): device for device in current.devices}
    added = tuple(after[key] for key in sorted(set(after) - set(before)))
    removed = tuple(before[key] for key in sorted(set(before) - set(after)))
    work = tuple(classify_device(device) for device in added)
    return HardwareDelta(added=added, removed=removed, driver_work=work)


__all__ = ["HardwareDelta", "diff_hardware"]
