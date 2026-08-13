from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from aurum_field import Field
from self_build_resources import BuilderResource


@dataclass(frozen=True)
class SelfBuildLane:
    name: str
    requires: frozenset[str]
    weight: int = 1
    redundancy: int = 1


@dataclass(frozen=True)
class FederatedAssignment:
    lane: str
    resources: tuple[str, ...]


@dataclass(frozen=True)
class FederatedSelfBuildPlan:
    assignments: tuple[FederatedAssignment, ...]
    unused_available_resources: tuple[str, ...]
    unavailable_resources: tuple[str, ...]
    unassigned_lanes: tuple[str, ...]
    missing_capabilities: frozenset[str]

    @property
    def active_resources(self) -> tuple[str, ...]:
        names = {
            resource
            for assignment in self.assignments
            for resource in assignment.resources
        }
        return tuple(sorted(names))


def _resource_rank(resource: BuilderResource) -> tuple[int, int, int, int, int, str]:
    return (
        -max(0, resource.parallel_slots),
        -resource.isolation,
        -resource.persistence,
        -resource.locality,
        resource.cost,
        resource.name,
    )


def plan_federated_self_build(
    lanes: Sequence[SelfBuildLane],
    resources: Iterable[BuilderResource],
) -> FederatedSelfBuildPlan:
    """Fan independent self-build work across all verified useful resources.

    This is federation, not winner-take-all placement. Every available resource
    that can satisfy at least one lane may participate. A lane can request
    redundant execution for independent verification. Per-resource slot limits
    remain explicit, and unavailable resources never receive work.
    """
    pool = tuple(resources)
    available = tuple(
        resource
        for resource in pool
        if resource.available and resource.parallel_slots > 0
    )
    unavailable = tuple(sorted(resource.name for resource in pool if not resource.available))
    slots = {resource.name: max(0, resource.parallel_slots) for resource in available}
    used: set[str] = set()
    assignments: list[FederatedAssignment] = []
    unassigned: list[str] = []
    missing: set[str] = set()

    union = set().union(*(resource.capabilities for resource in available)) if available else set()

    for lane in sorted(lanes, key=lambda item: (-item.weight, item.name)):
        candidates = [
            resource
            for resource in available
            if slots[resource.name] > 0
            and lane.requires.issubset(resource.capabilities)
        ]
        if not candidates:
            unassigned.append(lane.name)
            missing.update(lane.requires - union)
            continue

        candidates.sort(key=_resource_rank)
        desired = max(1, lane.redundancy)
        selected = candidates[:desired]
        for resource in selected:
            slots[resource.name] -= 1
            used.add(resource.name)
        assignments.append(
            FederatedAssignment(
                lane=lane.name,
                resources=tuple(resource.name for resource in selected),
            )
        )

    # If a verified resource is useful for some lane but remained idle because a
    # stronger resource took all work, spread eligible single-owner lanes onto it
    # when this does not violate slot limits. This preserves the user's desired
    # all-resource federation without assigning irrelevant work.
    for resource in sorted(available, key=_resource_rank):
        if resource.name in used or slots[resource.name] <= 0:
            continue
        eligible_indexes = [
            index
            for index, assignment in enumerate(assignments)
            if resource.name not in assignment.resources
            and next(lane for lane in lanes if lane.name == assignment.lane).requires.issubset(resource.capabilities)
        ]
        if not eligible_indexes:
            continue
        index = eligible_indexes[0]
        assignment = assignments[index]
        assignments[index] = FederatedAssignment(
            lane=assignment.lane,
            resources=tuple(sorted(assignment.resources + (resource.name,))),
        )
        slots[resource.name] -= 1
        used.add(resource.name)

    unused = tuple(sorted(resource.name for resource in available if resource.name not in used))
    return FederatedSelfBuildPlan(
        assignments=tuple(assignments),
        unused_available_resources=unused,
        unavailable_resources=unavailable,
        unassigned_lanes=tuple(unassigned),
        missing_capabilities=frozenset(missing),
    )


def federation_field(
    lanes: Sequence[SelfBuildLane],
    resources: Iterable[BuilderResource],
    plan: FederatedSelfBuildPlan,
) -> Field:
    field = Field()
    resource_refs: dict[str, object] = {}
    for resource in sorted(resources, key=lambda item: item.name):
        resource_refs[resource.name] = field.add(
            "capability",
            {
                "name": resource.name,
                "provides": sorted(resource.capabilities),
                "parallel_slots": resource.parallel_slots,
                "available": resource.available,
            },
        )
    lane_refs: dict[str, object] = {}
    for lane in sorted(lanes, key=lambda item: item.name):
        lane_refs[lane.name] = field.add(
            "fact",
            {
                "kind": "self-build-lane",
                "name": lane.name,
                "requires": sorted(lane.requires),
                "weight": lane.weight,
                "redundancy": lane.redundancy,
            },
        )
    assignment_refs = []
    for assignment in plan.assignments:
        assignment_refs.append(
            field.add(
                "relation",
                {
                    "kind": "self-build-federated-assignment",
                    "lane": lane_refs[assignment.lane],
                    "resources": [resource_refs[name] for name in assignment.resources],
                },
            )
        )
    field.add(
        "view",
        {
            "name": "aurum-federated-self-build-plan",
            "assignments": assignment_refs,
            "active_resources": list(plan.active_resources),
            "unused_available_resources": list(plan.unused_available_resources),
            "unavailable_resources": list(plan.unavailable_resources),
            "unassigned_lanes": list(plan.unassigned_lanes),
            "missing_capabilities": sorted(plan.missing_capabilities),
        },
    )
    return field


__all__ = [
    "FederatedAssignment",
    "FederatedSelfBuildPlan",
    "SelfBuildLane",
    "federation_field",
    "plan_federated_self_build",
]
