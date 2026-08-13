from __future__ import annotations

from dataclasses import dataclass

from capacity_mesh import Node
from windows_node_growth import WindowsResourceObservation, advertised_worker_capabilities, derive_morris_growth

GIB = 1024 ** 3


@dataclass(frozen=True)
class CapacityMapping:
    worker_slots: int
    memory_slot_bytes: int
    storage_headroom_bytes: int
    node: Node


def derive_capacity_mapping(
    observation: WindowsResourceObservation,
    *,
    memory_per_slot_bytes: int = 4 * GIB,
    maximum_slots: int = 8,
) -> CapacityMapping:
    observation.validate()
    if memory_per_slot_bytes <= 0 or maximum_slots <= 0:
        raise ValueError("slot constraints must be positive")
    growth = derive_morris_growth(observation)
    cpu_slots = max(1, observation.logical_processors // 2)
    memory_slots = max(1, observation.memory_available_bytes // memory_per_slot_bytes)
    worker_slots = max(1, min(cpu_slots, memory_slots, maximum_slots))
    names = frozenset(advertised_worker_capabilities(growth))
    node = Node(
        name=observation.node_name,
        capabilities=names,
        capacity=worker_slots,
        cost=0,
    )
    reserve = growth.slush_plan.reserve_bytes if growth.slush_plan is not None else 0
    headroom = max(0, observation.storage_free_bytes - reserve)
    return CapacityMapping(
        worker_slots=worker_slots,
        memory_slot_bytes=memory_per_slot_bytes,
        storage_headroom_bytes=headroom,
        node=node,
    )


__all__ = ["CapacityMapping", "derive_capacity_mapping"]
