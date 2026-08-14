from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .hardware_profile import DeviceObservation, MachineProfile


@dataclass(frozen=True)
class DriverWorkItem:
    bus: str
    address: str
    modalias: str | None
    observed_driver: str | None
    action: str
    trust_state: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def classify_device(device: DeviceObservation) -> DriverWorkItem:
    if device.driver:
        return DriverWorkItem(
            bus=device.bus,
            address=device.address,
            modalias=device.modalias,
            observed_driver=device.driver,
            action="reuse-bound-driver",
            trust_state="observed-existing-driver",
            reason="The generic seed already bound a driver to this device.",
        )
    if device.modalias:
        return DriverWorkItem(
            bus=device.bus,
            address=device.address,
            modalias=device.modalias,
            observed_driver=None,
            action="resolve-modalias",
            trust_state="needs-existing-driver-resolution",
            reason="Resolve this modalias against installed modules and the selected kernel source tree before generating anything new.",
        )
    return DriverWorkItem(
        bus=device.bus,
        address=device.address,
        modalias=None,
        observed_driver=None,
        action="research-hardware-contract",
        trust_state="unknown-hardware-contract",
        reason="No bound driver or modalias evidence exists. Aurum must identify the controller/protocol before proposing a driver.",
    )


def build_driver_plan(profile: MachineProfile) -> tuple[DriverWorkItem, ...]:
    return tuple(classify_device(device) for device in profile.devices)


def required_bound_drivers(items: Iterable[DriverWorkItem]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                item.observed_driver
                for item in items
                if item.action == "reuse-bound-driver" and item.observed_driver
            }
        )
    )


__all__ = [
    "DriverWorkItem",
    "build_driver_plan",
    "classify_device",
    "required_bound_drivers",
]
