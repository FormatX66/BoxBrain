from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class BootMediaPlan:
    architecture: str
    removable_media: bool
    seed_role: str
    custom_slot_role: str
    state_role: str
    fallback_required: bool
    uefi_fallback_path: str | None
    arm_board_bootstrap_note: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def make_boot_media_plan(architecture: str) -> BootMediaPlan:
    if architecture == "x86_64":
        return BootMediaPlan(
            architecture=architecture,
            removable_media=True,
            seed_role="known-good broad x86_64 Linux observation/recovery kernel",
            custom_slot_role="machine-specific trial kernel plus initramfs and modules",
            state_role="persistent profiles, manifests, source pins and rollback state",
            fallback_required=True,
            uefi_fallback_path="EFI/BOOT/BOOTX64.EFI",
            arm_board_bootstrap_note=None,
        )
    if architecture == "arm64":
        return BootMediaPlan(
            architecture=architecture,
            removable_media=True,
            seed_role="known-good ARM64 Linux observation/recovery kernel compatible with the board firmware",
            custom_slot_role="machine-specific trial kernel, DT/ACPI assets as required, initramfs and modules",
            state_role="persistent profiles, manifests, source pins and rollback state",
            fallback_required=True,
            uefi_fallback_path="EFI/BOOT/BOOTAA64.EFI",
            arm_board_bootstrap_note="ARM64 removable boot is not universally firmware-generic; the initial seed may need board-specific firmware or device-tree support before Aurum can self-specialize.",
        )
    raise ValueError(f"unsupported boot-media architecture: {architecture}")


__all__ = ["BootMediaPlan", "make_boot_media_plan"]
