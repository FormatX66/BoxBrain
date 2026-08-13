from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable, Mapping

from aurum_field import Field

MIB = 1024 * 1024
GIB = 1024 * MIB
SLUSH_MEDIA_SCHEMA = "aurum-slush-media-v0"


class SlushMediaError(ValueError):
    pass


@dataclass(frozen=True)
class MediaRegion:
    name: str
    offset: int
    size: int
    carrier: str
    semantic_owner: str
    writable_after_boot: bool


@dataclass(frozen=True)
class SlushMediaPlan:
    target: str
    capacity: int
    alignment: int
    regions: tuple[MediaRegion, ...]
    stages: tuple[str, ...]
    bootstrap_only: bool
    identity: str

    @property
    def slush_bytes(self) -> int:
        return sum(region.size for region in self.regions if region.semantic_owner == "aurum-slush")


@dataclass(frozen=True)
class MediaWriteGate:
    allowed: bool
    reasons: tuple[str, ...]


def _align_up(value: int, alignment: int) -> int:
    return ((value + alignment - 1) // alignment) * alignment


def _canonical_plan_payload(
    *,
    target: str,
    capacity: int,
    alignment: int,
    regions: Iterable[MediaRegion],
    stages: Iterable[str],
) -> bytes:
    payload = {
        "schema": SLUSH_MEDIA_SCHEMA,
        "target": target,
        "capacity": capacity,
        "alignment": alignment,
        "regions": [
            {
                "name": region.name,
                "offset": region.offset,
                "size": region.size,
                "carrier": region.carrier,
                "semantic_owner": region.semantic_owner,
                "writable_after_boot": region.writable_after_boot,
            }
            for region in regions
        ],
        "stages": list(stages),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def plan_pi3_slush_media(
    capacity: int,
    *,
    boot_shim_bytes: int = 256 * MIB,
    alignment: int = 4 * MIB,
) -> SlushMediaPlan:
    """Plan a Pi 3 microSD as a tiny compatibility boot shim plus raw Aurum Slush.

    This function never writes a block device.  It only produces deterministic
    machine state describing how a separately authorised media writer should
    lay out the card.
    """
    if capacity < 2 * GIB:
        raise SlushMediaError("Pi 3 Slush media requires at least 2 GiB")
    if alignment < MIB or alignment & (alignment - 1):
        raise SlushMediaError("alignment must be a power of two of at least 1 MiB")
    if boot_shim_bytes < 64 * MIB:
        raise SlushMediaError("boot shim is too small for a bounded firmware/kernel/initramfs carrier")

    boot_offset = alignment
    boot_size = _align_up(boot_shim_bytes, alignment)
    slush_offset = _align_up(boot_offset + boot_size, alignment)
    if slush_offset >= capacity:
        raise SlushMediaError("no room remains for Aurum Slush")
    slush_size = capacity - slush_offset

    regions = (
        MediaRegion(
            name="aurum-boot-shim",
            offset=boot_offset,
            size=boot_size,
            carrier="fat-compatible-pi-boot",
            semantic_owner="compatibility-shim",
            writable_after_boot=False,
        ),
        MediaRegion(
            name="aurum-slush",
            offset=slush_offset,
            size=slush_size,
            carrier="raw-block-region",
            semantic_owner="aurum-slush",
            writable_after_boot=True,
        ),
    )
    stages = (
        "boot-compatible-shim",
        "open-slush-region",
        "observe-hardware",
        "record-observation-field",
        "derive-required-capabilities",
        "materialize-local-runtime",
        "verify-local-runtime",
        "checkpoint-recovery-state",
        "enter-aurum-runtime",
    )
    raw = _canonical_plan_payload(
        target="raspberry-pi-3",
        capacity=capacity,
        alignment=alignment,
        regions=regions,
        stages=stages,
    )
    identity = hashlib.blake2s(b"AURUM-SLUSH-MEDIA-0\x00" + raw, digest_size=32).hexdigest()
    return SlushMediaPlan(
        target="raspberry-pi-3",
        capacity=capacity,
        alignment=alignment,
        regions=regions,
        stages=stages,
        bootstrap_only=True,
        identity=identity,
    )


def check_media_write_gate(
    *,
    explicit_media_selected: bool,
    exact_capacity_verified: bool,
    removable_media_verified: bool,
    system_disk: bool,
    mounted_or_in_use: bool,
    operator_authorized_write: bool,
) -> MediaWriteGate:
    """Fail closed before any destructive physical-media operation."""
    reasons: list[str] = []
    if not explicit_media_selected:
        reasons.append("no-explicit-media-selection")
    if not exact_capacity_verified:
        reasons.append("capacity-not-verified")
    if not removable_media_verified:
        reasons.append("removable-media-not-verified")
    if system_disk:
        reasons.append("system-disk-rejected")
    if mounted_or_in_use:
        reasons.append("media-in-use")
    if not operator_authorized_write:
        reasons.append("physical-write-not-authorized")
    return MediaWriteGate(not reasons, tuple(reasons))


def slush_boot_field(
    plan: SlushMediaPlan,
    *,
    source_node: str,
    boot_assets: Mapping[str, str] | None = None,
) -> Field:
    """Represent a Slush-card bootstrap as declarative Field state.

    Boot assets are content digests only.  Firmware/kernel bytes remain external
    carrier material and are not treated as Aurum's semantic identity.
    """
    field = Field()
    region_refs = []
    for region in plan.regions:
        region_refs.append(
            field.add(
                "fact",
                {
                    "media_plan": plan.identity,
                    "region": region.name,
                    "offset": region.offset,
                    "size": region.size,
                    "carrier": region.carrier,
                    "semantic_owner": region.semantic_owner,
                    "writable_after_boot": region.writable_after_boot,
                },
            )
        )
    source_ref = field.add(
        "fact",
        {
            "media_plan": plan.identity,
            "source_node": source_node,
            "target": plan.target,
            "capacity": plan.capacity,
            "bootstrap_only": plan.bootstrap_only,
            "boot_assets": dict(sorted((boot_assets or {}).items())),
        },
    )
    stage_ref = field.add(
        "relation",
        {
            "media_plan": plan.identity,
            "stages": list(plan.stages),
            "source": source_ref,
            "regions": region_refs,
        },
    )
    field.add(
        "view",
        {
            "name": "aurum-slush-self-build-media",
            "plan": plan.identity,
            "bootstrap": stage_ref,
        },
    )
    return field


def first_boot_contract(plan: SlushMediaPlan) -> Mapping[str, object]:
    """Return the invariant contract the target must satisfy before entering Aurum."""
    return {
        "schema": SLUSH_MEDIA_SCHEMA,
        "plan": plan.identity,
        "target": plan.target,
        "must_observe_before_materialize": True,
        "hardware_profile_prebaked": False,
        "slush_is_authoritative_during_first_boot": True,
        "compatibility_shim_is_os_owner": False,
        "runtime_must_verify_before_promotion": True,
        "rollback_checkpoint_required": True,
        "raw_media_write_requires_external_gate": True,
    }


__all__ = [
    "GIB",
    "MIB",
    "MediaRegion",
    "MediaWriteGate",
    "SlushMediaError",
    "SlushMediaPlan",
    "check_media_write_gate",
    "first_boot_contract",
    "plan_pi3_slush_media",
    "slush_boot_field",
]
