from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping

from aurum_field import Field
from slush_media import SlushMediaError, SlushMediaPlan

BOOT_SHIM_SCHEMA = "aurum-pi3-boot-shim-v0"


class BootShimError(ValueError):
    pass


@dataclass(frozen=True)
class BootAsset:
    name: str
    role: str
    size: int
    sha256: str
    source: str


@dataclass(frozen=True)
class Pi3BootShim:
    media_plan: str
    source_revision: str
    assets: tuple[BootAsset, ...]
    config_txt: str
    cmdline_txt: str
    identity: str
    rootfs_prebuilt: bool = False


_REQUIRED_EXTERNAL = {
    "bootcode.bin": "soc-second-stage-bootloader",
    "start.elf": "videocore-firmware",
    "fixup.dat": "videocore-firmware-fixup",
    "kernel8.img": "arm64-bootstrap-kernel",
    "initramfs": "aurum-first-boot-initramfs",
    "bcm2710-rpi-3-b.dtb": "pi3b-device-tree",
    "bcm2710-rpi-3-b-plus.dtb": "pi3b-plus-device-tree",
    "LICENCE.broadcom": "firmware-license",
    "COPYING.linux": "kernel-license",
}


def required_external_assets() -> Mapping[str, str]:
    return dict(_REQUIRED_EXTERNAL)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _asset(path: Path, *, role: str, source: str) -> BootAsset:
    if not path.is_file():
        raise BootShimError(f"missing boot asset: {path.name}")
    return BootAsset(
        name=path.name,
        role=role,
        size=path.stat().st_size,
        sha256=_sha256(path),
        source=source,
    )


def build_config_txt() -> str:
    """Minimal Pi 3 carrier configuration for the Aurum first-boot initramfs."""
    return "\n".join(
        (
            "arm_64bit=1",
            "kernel=kernel8.img",
            "initramfs initramfs followkernel",
            "enable_uart=1",
            "disable_splash=1",
            "",
        )
    )


def build_cmdline_txt(media_plan: str) -> str:
    if len(media_plan) != 64:
        raise BootShimError("media plan identity must be a 32-byte hexadecimal digest")
    try:
        bytes.fromhex(media_plan)
    except ValueError as exc:
        raise BootShimError("media plan identity is not hexadecimal") from exc
    # Unknown aurum.* arguments are intentionally passed through by Linux for
    # the initramfs bootstrap to read.  There is no root= filesystem here.
    return (
        "console=serial0,115200 console=tty1 rdinit=/aurum-init "
        f"aurum.bootstrap=1 aurum.slush_plan={media_plan}\n"
    )


def _canonical_payload(
    *,
    media_plan: str,
    source_revision: str,
    assets: Iterable[BootAsset],
    config_txt: str,
    cmdline_txt: str,
) -> bytes:
    payload = {
        "schema": BOOT_SHIM_SCHEMA,
        "media_plan": media_plan,
        "source_revision": source_revision,
        "assets": [
            {
                "name": item.name,
                "role": item.role,
                "size": item.size,
                "sha256": item.sha256,
                "source": item.source,
            }
            for item in sorted(assets, key=lambda candidate: candidate.name)
        ],
        "config_txt": config_txt,
        "cmdline_txt": cmdline_txt,
        "rootfs_prebuilt": False,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def inspect_boot_asset_directory(
    directory: str | Path,
    *,
    source_revision: str,
    source_name: str = "raspberrypi/firmware+pinned-kernel-initramfs",
) -> tuple[BootAsset, ...]:
    root = Path(directory)
    if not root.is_dir():
        raise BootShimError("boot asset directory does not exist")
    if not source_revision or any(character.isspace() for character in source_revision):
        raise BootShimError("source revision must be a non-empty single token")
    assets = []
    for name, role in sorted(_REQUIRED_EXTERNAL.items()):
        assets.append(
            _asset(
                root / name,
                role=role,
                source=f"{source_name}@{source_revision}",
            )
        )
    return tuple(assets)


def build_pi3_boot_shim(
    plan: SlushMediaPlan,
    *,
    source_revision: str,
    assets: Iterable[BootAsset],
) -> Pi3BootShim:
    if plan.target != "raspberry-pi-3":
        raise BootShimError("Pi 3 boot shim requires a Raspberry Pi 3 media plan")
    by_name = {asset.name: asset for asset in assets}
    missing = sorted(set(_REQUIRED_EXTERNAL) - set(by_name))
    if missing:
        raise BootShimError("missing required assets: " + ", ".join(missing))
    for name, expected_role in _REQUIRED_EXTERNAL.items():
        asset = by_name[name]
        if asset.role != expected_role:
            raise BootShimError(f"asset role mismatch: {name}")
        if asset.size <= 0:
            raise BootShimError(f"empty boot asset: {name}")
        if len(asset.sha256) != 64:
            raise BootShimError(f"invalid asset digest: {name}")
        try:
            bytes.fromhex(asset.sha256)
        except ValueError as exc:
            raise BootShimError(f"invalid asset digest: {name}") from exc

    config_txt = build_config_txt()
    cmdline_txt = build_cmdline_txt(plan.identity)
    canonical = _canonical_payload(
        media_plan=plan.identity,
        source_revision=source_revision,
        assets=by_name.values(),
        config_txt=config_txt,
        cmdline_txt=cmdline_txt,
    )
    identity = hashlib.blake2s(b"AURUM-PI3-BOOT-SHIM-0\x00" + canonical, digest_size=32).hexdigest()
    return Pi3BootShim(
        media_plan=plan.identity,
        source_revision=source_revision,
        assets=tuple(sorted(by_name.values(), key=lambda candidate: candidate.name)),
        config_txt=config_txt,
        cmdline_txt=cmdline_txt,
        identity=identity,
        rootfs_prebuilt=False,
    )


def verify_boot_shim(shim: Pi3BootShim, plan: SlushMediaPlan) -> None:
    if shim.media_plan != plan.identity:
        raise BootShimError("boot shim is bound to a different Slush media plan")
    if shim.rootfs_prebuilt:
        raise BootShimError("v0 boot shim must not contain a prebuilt root filesystem")
    expected_config = build_config_txt()
    expected_cmdline = build_cmdline_txt(plan.identity)
    if shim.config_txt != expected_config or shim.cmdline_txt != expected_cmdline:
        raise BootShimError("boot shim configuration changed from the v0 first-boot contract")
    rebuilt = build_pi3_boot_shim(
        plan,
        source_revision=shim.source_revision,
        assets=shim.assets,
    )
    if rebuilt.identity != shim.identity:
        raise BootShimError("boot shim identity mismatch")


def boot_shim_field(shim: Pi3BootShim) -> Field:
    """Project carrier evidence without making the firmware/kernel Aurum's owner."""
    field = Field()
    asset_refs = []
    for asset in shim.assets:
        asset_refs.append(
            field.add(
                "fact",
                {
                    "boot_shim": shim.identity,
                    "name": asset.name,
                    "role": asset.role,
                    "size": asset.size,
                    "sha256": asset.sha256,
                    "source": asset.source,
                    "semantic_owner": "compatibility-carrier",
                },
            )
        )
    config_ref = field.add(
        "fact",
        {
            "boot_shim": shim.identity,
            "media_plan": shim.media_plan,
            "source_revision": shim.source_revision,
            "config_txt": shim.config_txt,
            "cmdline_txt": shim.cmdline_txt,
            "rootfs_prebuilt": shim.rootfs_prebuilt,
        },
    )
    field.add(
        "view",
        {
            "name": "aurum-pi3-boot-shim",
            "identity": shim.identity,
            "configuration": config_ref,
            "assets": asset_refs,
        },
    )
    return field


def first_boot_os_build_contract(shim: Pi3BootShim) -> Mapping[str, object]:
    return {
        "schema": BOOT_SHIM_SCHEMA,
        "boot_shim": shim.identity,
        "media_plan": shim.media_plan,
        "rootfs_prebuilt": False,
        "first_process": "/aurum-init",
        "slush_plan_from_kernel_command_line": True,
        "observe_device_tree": True,
        "observe_cpu_memory": True,
        "observe_storage_capacity": True,
        "observe_available_io": True,
        "record_observations_before_materialization": True,
        "derive_runtime_from_observed_capabilities": True,
        "verify_runtime_before_promotion": True,
        "retain_boot_shim_as_recovery_carrier": True,
    }


__all__ = [
    "BOOT_SHIM_SCHEMA",
    "BootAsset",
    "BootShimError",
    "Pi3BootShim",
    "boot_shim_field",
    "build_cmdline_txt",
    "build_config_txt",
    "build_pi3_boot_shim",
    "first_boot_os_build_contract",
    "inspect_boot_asset_directory",
    "required_external_assets",
    "verify_boot_shim",
]
