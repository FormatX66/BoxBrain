from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .driver_plan import DriverWorkItem, required_bound_drivers
from .hardware_profile import MachineProfile


SUPPORTED_ARCHES = frozenset({"x86_64", "arm64"})


@dataclass(frozen=True)
class KernelBuildPlan:
    architecture: str
    firmware: str
    source_strategy: str
    config_strategy: tuple[str, ...]
    required_modules: tuple[str, ...]
    unresolved_modaliases: tuple[str, ...]
    unknown_devices: tuple[str, ...]
    boot_critical_preservation: tuple[str, ...]
    verification_gates: tuple[str, ...]
    deployment_strategy: str
    ready_for_compile: bool

    def to_dict(self) -> dict:
        return asdict(self)


def make_kernel_build_plan(
    profile: MachineProfile,
    driver_items: Iterable[DriverWorkItem],
) -> KernelBuildPlan:
    items = tuple(driver_items)
    required_modules = required_bound_drivers(items)
    unresolved_modaliases = tuple(
        sorted({item.modalias for item in items if item.action == "resolve-modalias" and item.modalias})
    )
    unknown_devices = tuple(
        sorted(f"{item.bus}:{item.address}" for item in items if item.action == "research-hardware-contract")
    )
    arch_supported = profile.architecture in SUPPORTED_ARCHES
    return KernelBuildPlan(
        architecture=profile.architecture,
        firmware=profile.firmware,
        source_strategy=(
            "pin-known-good-linux-source-and-apply-machine-profile"
            if arch_supported
            else "unsupported-architecture-requires-new-seed"
        ),
        config_strategy=(
            "start-from-running-seed-config",
            "resolve-observed-device-modaliases",
            "preserve-boot-critical-subsystems",
            "reduce-unused-features-conservatively",
            "prefer-hotplug-peripherals-as-modules",
            "run-olddefconfig-equivalent-finalization",
        ),
        required_modules=required_modules,
        unresolved_modaliases=unresolved_modaliases,
        unknown_devices=unknown_devices,
        boot_critical_preservation=(
            "root-storage-controller",
            "root-filesystem",
            "partition-and-block-layer",
            "firmware-loader",
            "console",
            "keyboard-input",
            "usb-host-controllers",
            "boot-network-path-when-required",
            "architecture-timer-interrupt-and-iommu-baseline",
        ),
        verification_gates=(
            "kernel-config-resolves",
            "kernel-and-modules-build",
            "module-dependency-closure",
            "initramfs-contains-boot-critical-modules",
            "machine-profile-required-drivers-present",
            "vm-or-emulated-boot-when-hardware-model-is-available",
            "signed-artifact-manifest",
            "a-b-fallback-preserved",
        ),
        deployment_strategy="trial-slot-next-to-generic-seed-never-overwrite-only-known-good-kernel",
        ready_for_compile=arch_supported and not unknown_devices,
    )


__all__ = ["KernelBuildPlan", "SUPPORTED_ARCHES", "make_kernel_build_plan"]
