from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from aurum_field import Field
from capacity_mesh import Capability
from morris_slush_extent import (
    HostStorageObservation,
    SlushExtentPlan,
    plan_morris_slush_extent,
)

MORRIS_NODE_ID = "825e5a7b7d4a7aed"
MORRIS_NODE_NAME = "Aurum-Morris"


@dataclass(frozen=True)
class WindowsResourceObservation:
    node_id: str
    node_name: str
    logical_processors: int
    memory_total_bytes: int
    memory_available_bytes: int
    system_volume: str
    filesystem: str
    storage_total_bytes: int
    storage_free_bytes: int
    sparse_supported: bool
    gpu_names: tuple[str, ...] = ()
    hypervisor_present: bool = False
    new_vhd_available: bool = False

    def validate(self) -> None:
        if self.node_id != MORRIS_NODE_ID or self.node_name != MORRIS_NODE_NAME:
            raise ValueError("resource observation is not for the pinned Morris node")
        if self.logical_processors <= 0:
            raise ValueError("logical processor count is missing")
        if self.memory_total_bytes <= 0 or self.memory_available_bytes < 0:
            raise ValueError("memory observation is incomplete")
        if self.memory_available_bytes > self.memory_total_bytes:
            raise ValueError("available memory exceeds total memory")
        if self.storage_total_bytes <= 0 or self.storage_free_bytes < 0:
            raise ValueError("storage observation is incomplete")
        if self.storage_free_bytes > self.storage_total_bytes:
            raise ValueError("free storage exceeds total storage")
        if not self.system_volume:
            raise ValueError("system volume is missing")


@dataclass(frozen=True)
class NodeGrowthState:
    capabilities: tuple[Capability, ...]
    slush_plan: SlushExtentPlan | None
    blocked: Mapping[str, str]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.capabilities)


def base_windows_capabilities() -> tuple[Capability, ...]:
    return (
        Capability(
            "connectivity-observation",
            frozenset({"authorized-private-network"}),
            frozenset({"connectivity-evidence"}),
            frozenset({"read-only", "bounded"}),
        ),
        Capability(
            "bbpi4-bootstrap",
            frozenset({"authorized-bbpi4-seed-route"}),
            frozenset({"bbpi4-bootstrap-result"}),
            frozenset({"bounded", "seed-route-only"}),
        ),
        Capability(
            "resource-observation",
            frozenset({"local-windows-node"}),
            frozenset({"cpu-capacity", "memory-capacity", "storage-capacity", "carrier-capacity"}),
            frozenset({"read-only", "local", "reversible"}),
        ),
    )


def derive_morris_growth(observation: WindowsResourceObservation) -> NodeGrowthState:
    """Turn verified host evidence into the next safely claimable Morris capabilities."""
    observation.validate()
    capabilities = list(base_windows_capabilities())
    blocked: dict[str, str] = {}
    plan: SlushExtentPlan | None = None

    if not observation.sparse_supported:
        blocked["slush-extent-plan"] = "host-filesystem-does-not-support-sparse-extents"
        blocked["slush-extent-provision"] = "host-filesystem-does-not-support-sparse-extents"
    else:
        host = HostStorageObservation(
            node=MORRIS_NODE_NAME,
            volume=observation.system_volume,
            filesystem=observation.filesystem,
            total_bytes=observation.storage_total_bytes,
            free_bytes=observation.storage_free_bytes,
            sparse_supported=True,
        )
        try:
            plan = plan_morris_slush_extent(host)
        except ValueError as exc:
            blocked["slush-extent-plan"] = str(exc)
            blocked["slush-extent-provision"] = str(exc)
        else:
            capabilities.extend(
                (
                    Capability(
                        "slush-extent-plan",
                        frozenset({"storage-capacity"}),
                        frozenset({"slush-extent-plan"}),
                        frozenset({"deterministic", "no-write"}),
                    ),
                    Capability(
                        "slush-extent-provision",
                        frozenset({"slush-extent-plan", "local-write-approval"}),
                        frozenset({"slush-extent"}),
                        frozenset({"fixed-path", "sparse-only", "no-partition-change", "no-overwrite"}),
                    ),
                    Capability(
                        "slush-seed",
                        frozenset({"slush-extent", "verified-aurum-seed"}),
                        frozenset({"seeded-slush"}),
                        frozenset({"content-addressed", "mirrored-anchor", "reversible"}),
                    ),
                )
            )

    if observation.hypervisor_present or observation.new_vhd_available:
        capabilities.append(
            Capability(
                "prototype-runtime-materialize",
                frozenset({"seeded-slush", "verified-runtime-artifact"}),
                frozenset({"isolated-prototype-runtime"}),
                frozenset({"isolated", "rollback-required", "host-boot-unchanged"}),
            )
        )
    else:
        blocked["prototype-runtime-materialize"] = "no-verified-isolated-runtime-carrier"

    return NodeGrowthState(
        capabilities=tuple(sorted(capabilities, key=lambda item: item.name)),
        slush_plan=plan,
        blocked=dict(sorted(blocked.items())),
    )


def resource_observation_field(observation: WindowsResourceObservation) -> Field:
    observation.validate()
    field = Field()
    fact = field.add(
        "fact",
        {
            "node_id": observation.node_id,
            "node": observation.node_name,
            "logical_processors": observation.logical_processors,
            "memory_total_bytes": observation.memory_total_bytes,
            "memory_available_bytes": observation.memory_available_bytes,
            "system_volume": observation.system_volume,
            "filesystem": observation.filesystem,
            "storage_total_bytes": observation.storage_total_bytes,
            "storage_free_bytes": observation.storage_free_bytes,
            "sparse_supported": observation.sparse_supported,
            "gpu_names": list(observation.gpu_names),
            "hypervisor_present": observation.hypervisor_present,
            "new_vhd_available": observation.new_vhd_available,
            "read_only_observation": True,
        },
    )
    field.add(
        "view",
        {
            "name": "aurum-windows-node-capacity",
            "node_id": observation.node_id,
            "observation": fact,
        },
    )
    return field


def growth_field(observation: WindowsResourceObservation, state: NodeGrowthState) -> Field:
    field = resource_observation_field(observation)
    capability_refs = []
    for item in state.capabilities:
        capability_refs.append(
            field.add(
                "capability",
                {
                    "node_id": observation.node_id,
                    "name": item.name,
                    "accepts": sorted(item.accepts),
                    "provides": sorted(item.provides),
                    "traits": sorted(item.traits),
                },
            )
        )
    plan_ref = None
    if state.slush_plan is not None:
        plan_ref = field.add(
            "fact",
            {
                "node_id": observation.node_id,
                "kind": "slush-extent-plan",
                "identity": state.slush_plan.identity,
                "path": state.slush_plan.path,
                "capacity_bytes": state.slush_plan.capacity_bytes,
                "reserve_bytes": state.slush_plan.reserve_bytes,
                "host_partition_change": False,
            },
        )
    field.add(
        "view",
        {
            "name": "aurum-morris-growth-state",
            "node_id": observation.node_id,
            "capabilities": capability_refs,
            "slush_plan": plan_ref,
            "blocked": dict(state.blocked),
        },
    )
    return field


def advertised_worker_capabilities(state: NodeGrowthState) -> tuple[str, ...]:
    """Return executable worker names only; declarative traits never become authority."""
    executable = {
        "bbpi4-bootstrap",
        "connectivity-observation",
        "resource-observation",
        "slush-extent-plan",
        "slush-extent-provision",
        "slush-seed",
        "prototype-runtime-materialize",
    }
    return tuple(name for name in state.names if name in executable)


__all__ = [
    "MORRIS_NODE_ID",
    "MORRIS_NODE_NAME",
    "NodeGrowthState",
    "WindowsResourceObservation",
    "advertised_worker_capabilities",
    "base_windows_capabilities",
    "derive_morris_growth",
    "growth_field",
    "resource_observation_field",
]
