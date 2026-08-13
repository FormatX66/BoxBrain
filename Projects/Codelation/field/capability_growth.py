from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from aurum_field import Field
from capacity_mesh import Node, WorkItem, assign_parallel
from event_handoff import HandoffPlan


@dataclass(frozen=True)
class CapabilityNeed:
    name: str
    demanded_by: tuple[str, ...]
    occurrences: int


@dataclass(frozen=True)
class GrowthPlan:
    needs: tuple[CapabilityNeed, ...]
    build_work: tuple[WorkItem, ...]
    assignments: dict[str, tuple[str, ...]]
    unassigned: tuple[str, ...]
    missing_builder_capabilities: frozenset[str]


def derive_needs(plans: Sequence[HandoffPlan]) -> tuple[CapabilityNeed, ...]:
    """Converge repeated capability gaps into deterministic demand signals."""

    demand: dict[str, list[str]] = {}
    for plan in plans:
        for capability in sorted(plan.missing_capabilities):
            demand.setdefault(capability, []).extend(plan.unassigned)

    return tuple(
        CapabilityNeed(
            name=name,
            demanded_by=tuple(sorted(set(items))),
            occurrences=len(items),
        )
        for name, items in sorted(demand.items())
    )


def build_candidates(
    needs: Sequence[CapabilityNeed],
    *,
    builder_capability: str = "capability-build",
) -> tuple[WorkItem, ...]:
    """Turn missing capabilities into claimable build work without executable payloads."""

    return tuple(
        WorkItem(
            name=f"build-capability:{need.name}",
            requires=frozenset({builder_capability}),
            weight=max(1, 10 + need.occurrences),
        )
        for need in sorted(needs, key=lambda item: (-item.occurrences, item.name))
    )


def plan_growth(
    plans: Sequence[HandoffPlan],
    builders: Sequence[Node],
    *,
    builder_capability: str = "capability-build",
) -> GrowthPlan:
    """Derive missing abilities, create build candidates, and distribute them by fit."""

    needs = derive_needs(plans)
    work = build_candidates(needs, builder_capability=builder_capability)
    assignment = assign_parallel(work, builders)
    return GrowthPlan(
        needs=needs,
        build_work=work,
        assignments=dict(assignment.assignments),
        unassigned=assignment.unassigned,
        missing_builder_capabilities=assignment.missing_capabilities,
    )


def growth_field(plan: GrowthPlan) -> Field:
    """Project capability demand and build intent into Field as declarative evidence."""

    field = Field()
    need_refs = []
    for need in plan.needs:
        need_refs.append(
            field.add(
                "fact",
                {
                    "type": "capability-need",
                    "name": need.name,
                    "demanded_by": list(need.demanded_by),
                    "occurrences": need.occurrences,
                },
            )
        )

    candidate_refs = []
    for work in plan.build_work:
        candidate_refs.append(
            field.add(
                "capability",
                {
                    "name": work.name,
                    "accepts": sorted(work.requires),
                    "provides": [work.name.removeprefix("build-capability:")],
                    "traits": {
                        "declarative_candidate": True,
                        "weight": work.weight,
                    },
                },
            )
        )

    field.add(
        "view",
        {
            "name": "capability-growth",
            "needs": need_refs,
            "candidates": candidate_refs,
            "assignments": {
                worker: list(items) for worker, items in sorted(plan.assignments.items())
            },
            "unassigned": list(plan.unassigned),
            "missing_builder_capabilities": sorted(plan.missing_builder_capabilities),
        },
    )
    return field


__all__ = [
    "CapabilityNeed",
    "GrowthPlan",
    "build_candidates",
    "derive_needs",
    "growth_field",
    "plan_growth",
]
