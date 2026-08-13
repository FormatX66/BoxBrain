from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from aurum_field import Field
from self_build_federation import (
    FederatedSelfBuildPlan,
    SelfBuildLane,
    federation_field,
    plan_federated_self_build,
)
from self_build_gap_spec import GapSupportAnalysis
from self_build_resources import BuilderResource, default_self_build_resources


@dataclass(frozen=True)
class SubstrateGrowthPlan:
    parent_gap: str
    substrate_gaps: tuple[str, ...]
    ready_stage: str
    federation: FederatedSelfBuildPlan


def plan_substrate_growth(
    analysis: GapSupportAnalysis,
    *,
    resources: Sequence[BuilderResource] | None = None,
) -> SubstrateGrowthPlan:
    """Start every missing self-build primitive in parallel at candidate derivation.

    The gap specification has already established what semantic primitives are
    required, so the first ready work is candidate generation for each missing
    primitive. No kernel promotion is scheduled here; each candidate must later
    pass isolated build/test and review gates before any promotion authority is
    eligible.
    """
    gaps = tuple(need.name for need in analysis.substrate_needs)
    lanes = tuple(
        SelfBuildLane(
            name=f"derive-substrate-candidate:{gap}",
            requires=frozenset({"candidate-generation"}),
            weight=100,
            redundancy=2,
        )
        for gap in gaps
    )
    pool = tuple(default_self_build_resources() if resources is None else resources)
    federation = plan_federated_self_build(lanes, pool)
    return SubstrateGrowthPlan(
        parent_gap=analysis.gap,
        substrate_gaps=gaps,
        ready_stage="derive-substrate-candidate",
        federation=federation,
    )


def substrate_growth_field(
    analysis: GapSupportAnalysis,
    plan: SubstrateGrowthPlan,
    *,
    resources: Sequence[BuilderResource] | None = None,
) -> Field:
    pool = tuple(default_self_build_resources() if resources is None else resources)
    lanes = tuple(
        SelfBuildLane(
            name=f"derive-substrate-candidate:{gap}",
            requires=frozenset({"candidate-generation"}),
            weight=100,
            redundancy=2,
        )
        for gap in plan.substrate_gaps
    )
    field = federation_field(lanes, pool, plan.federation)
    field.add(
        "view",
        {
            "name": "aurum-self-build-substrate-growth",
            "parent_gap": plan.parent_gap,
            "substrate_gaps": list(plan.substrate_gaps),
            "ready_stage": plan.ready_stage,
            "active_resources": list(plan.federation.active_resources),
            "unassigned": list(plan.federation.unassigned_lanes),
            "missing_capabilities": sorted(plan.federation.missing_capabilities),
            "parallel": True,
            "promotion_scheduled": False,
        },
    )
    return field


__all__ = [
    "SubstrateGrowthPlan",
    "plan_substrate_growth",
    "substrate_growth_field",
]
