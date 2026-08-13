from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping

from aurum_field import Field

GIB = 1024 ** 3
MIB = 1024 ** 2
SLUSH_EXTENT_SCHEMA = "aurum-slush-extent-v0"
ANCHOR_BYTES = 4096


class SlushExtentError(ValueError):
    pass


@dataclass(frozen=True)
class HostStorageObservation:
    node: str
    volume: str
    filesystem: str
    total_bytes: int
    free_bytes: int
    sparse_supported: bool


@dataclass(frozen=True)
class SlushExtentPlan:
    node: str
    path: str
    capacity_bytes: int
    reserve_bytes: int
    source_free_bytes: int
    sparse_required: bool
    anchor_bytes: int
    primary_anchor_offset: int
    mirror_anchor_offset: int
    identity: str


def _align_down(value: int, alignment: int) -> int:
    return value - (value % alignment)


def plan_morris_slush_extent(
    observation: HostStorageObservation,
    *,
    path: str = r"%USERPROFILE%\.aurum\slush\Morris.prototype.slush",
    desired_bytes: int = 64 * GIB,
    minimum_bytes: int = 32 * GIB,
    reserve_bytes: int = 32 * GIB,
    alignment: int = GIB,
) -> SlushExtentPlan:
    """Plan a reversible sparse Slush file without repartitioning the host disk."""
    if observation.node != "Aurum-Morris":
        raise SlushExtentError("planner is pinned to Aurum-Morris")
    if observation.total_bytes <= 0 or observation.free_bytes <= 0:
        raise SlushExtentError("storage observation is incomplete")
    if observation.free_bytes > observation.total_bytes:
        raise SlushExtentError("free space exceeds total capacity")
    if not observation.sparse_supported:
        raise SlushExtentError("host filesystem does not support sparse files")
    if alignment < MIB or alignment & (alignment - 1):
        raise SlushExtentError("alignment must be a power of two of at least 1 MiB")
    if reserve_bytes < 16 * GIB:
        raise SlushExtentError("host reserve is below the prototype safety floor")

    usable = _align_down(max(0, observation.free_bytes - reserve_bytes), alignment)
    capacity = min(desired_bytes, usable)
    capacity = _align_down(capacity, alignment)
    if capacity < minimum_bytes:
        raise SlushExtentError("not enough verified free space for a safe prototype extent")
    if capacity < ANCHOR_BYTES * 2:
        raise SlushExtentError("extent is too small for mirrored anchors")

    payload = {
        "schema": SLUSH_EXTENT_SCHEMA,
        "node": observation.node,
        "volume": observation.volume,
        "filesystem": observation.filesystem,
        "path": path,
        "capacity_bytes": capacity,
        "reserve_bytes": reserve_bytes,
        "source_free_bytes": observation.free_bytes,
        "sparse_required": True,
        "anchor_bytes": ANCHOR_BYTES,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    identity = hashlib.sha256(b"AURUM-MORRIS-SLUSH-0\x00" + raw).hexdigest()
    return SlushExtentPlan(
        node=observation.node,
        path=path,
        capacity_bytes=capacity,
        reserve_bytes=reserve_bytes,
        source_free_bytes=observation.free_bytes,
        sparse_required=True,
        anchor_bytes=ANCHOR_BYTES,
        primary_anchor_offset=0,
        mirror_anchor_offset=capacity - ANCHOR_BYTES,
        identity=identity,
    )


def slush_extent_field(plan: SlushExtentPlan, observation: HostStorageObservation) -> Field:
    field = Field()
    observation_ref = field.add(
        "fact",
        {
            "node": observation.node,
            "volume": observation.volume,
            "filesystem": observation.filesystem,
            "total_bytes": observation.total_bytes,
            "free_bytes": observation.free_bytes,
            "sparse_supported": observation.sparse_supported,
        },
    )
    extent_ref = field.add(
        "fact",
        {
            "identity": plan.identity,
            "node": plan.node,
            "path": plan.path,
            "capacity_bytes": plan.capacity_bytes,
            "reserve_bytes": plan.reserve_bytes,
            "sparse_required": plan.sparse_required,
            "primary_anchor_offset": plan.primary_anchor_offset,
            "mirror_anchor_offset": plan.mirror_anchor_offset,
            "carrier": "windows-sparse-file",
            "host_partition_changed": False,
        },
    )
    field.add(
        "relation",
        {
            "kind": "materialize-slush-from-storage-observation",
            "observation": observation_ref,
            "extent": extent_ref,
        },
    )
    field.add(
        "view",
        {
            "name": "aurum-morris-prototype-slush",
            "identity": plan.identity,
            "extent": extent_ref,
        },
    )
    return field


def provisioning_contract(plan: SlushExtentPlan) -> Mapping[str, object]:
    return {
        "schema": SLUSH_EXTENT_SCHEMA,
        "identity": plan.identity,
        "host_partition_change_allowed": False,
        "host_partition_shrink_allowed": False,
        "raw_physical_disk_write_allowed": False,
        "existing_file_overwrite_allowed": False,
        "fixed_path_only": True,
        "sparse_file_required": True,
        "mirror_anchor_required": True,
        "delete_is_rollback": True,
        "boot_configuration_change_allowed": False,
    }


__all__ = [
    "ANCHOR_BYTES",
    "GIB",
    "HostStorageObservation",
    "SlushExtentError",
    "SlushExtentPlan",
    "plan_morris_slush_extent",
    "provisioning_contract",
    "slush_extent_field",
]
