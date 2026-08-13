from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from aurum_field import Field


@dataclass(frozen=True)
class BuilderResource:
    name: str
    capabilities: frozenset[str]
    parallel_slots: int = 1
    persistence: int = 0
    isolation: int = 0
    locality: int = 0
    cost: int = 0
    available: bool = True


@dataclass(frozen=True)
class SelfBuildNeed:
    execution_requires: frozenset[str]
    reasoning_requires: frozenset[str] = frozenset()
    promotion_requires: frozenset[str] = frozenset()


@dataclass(frozen=True)
class SelfBuildPlacement:
    executor: str | None
    reasoner: str | None
    promoter: str | None
    missing: frozenset[str]


def _rank(resource: BuilderResource) -> tuple[int, int, int, int, int, str]:
    return (
        -max(0, resource.parallel_slots),
        -resource.isolation,
        -resource.persistence,
        -resource.locality,
        resource.cost,
        resource.name,
    )


def _select(resources: Sequence[BuilderResource], required: frozenset[str]) -> BuilderResource | None:
    if not required:
        return None
    candidates = [
        resource
        for resource in resources
        if resource.available
        and resource.parallel_slots > 0
        and required.issubset(resource.capabilities)
    ]
    if not candidates:
        return None
    return sorted(candidates, key=_rank)[0]


def plan_self_build(
    need: SelfBuildNeed,
    resources: Iterable[BuilderResource],
) -> SelfBuildPlacement:
    """Place self-build stages on the strongest currently verified resources.

    Execution, reasoning, and promotion are selected independently. This keeps
    model intelligence optional and prevents the reasoning resource from
    implicitly gaining repository or host authority.
    """
    pool = tuple(resources)
    executor = _select(pool, need.execution_requires)
    reasoner = _select(pool, need.reasoning_requires)
    promoter = _select(pool, need.promotion_requires)

    missing: set[str] = set()
    union = set().union(*(item.capabilities for item in pool if item.available)) if pool else set()
    for required in (
        need.execution_requires,
        need.reasoning_requires,
        need.promotion_requires,
    ):
        missing.update(required - union)

    return SelfBuildPlacement(
        executor=executor.name if executor else None,
        reasoner=reasoner.name if reasoner else None,
        promoter=promoter.name if promoter else None,
        missing=frozenset(missing),
    )


def default_self_build_resources() -> tuple[BuilderResource, ...]:
    """Current known resource roles; availability is evidence, not a promise."""
    return (
        BuilderResource(
            "github-actions",
            frozenset({
                "deterministic-execution",
                "repository-read",
                "isolated-build",
                "parallel-test",
                "artifact-output",
            }),
            parallel_slots=8,
            persistence=1,
            isolation=5,
            locality=2,
            cost=0,
        ),
        BuilderResource(
            "gpt-reasoning",
            frozenset({
                "model-reasoning",
                "candidate-generation",
                "semantic-analysis",
            }),
            parallel_slots=1,
            persistence=0,
            isolation=2,
            locality=0,
            cost=1,
        ),
        BuilderResource(
            "github-control-plane",
            frozenset({"verified-repository-promotion"}),
            parallel_slots=1,
            persistence=5,
            isolation=4,
            locality=2,
            cost=0,
        ),
    )


def self_build_resource_field(resources: Iterable[BuilderResource]) -> Field:
    field = Field()
    refs = []
    for resource in sorted(resources, key=lambda item: item.name):
        refs.append(
            field.add(
                "capability",
                {
                    "name": resource.name,
                    "provides": sorted(resource.capabilities),
                    "parallel_slots": resource.parallel_slots,
                    "persistence": resource.persistence,
                    "isolation": resource.isolation,
                    "locality": resource.locality,
                    "cost": resource.cost,
                    "available": resource.available,
                },
            )
        )
    field.add("view", {"name": "aurum-self-build-resources", "resources": refs})
    return field


__all__ = [
    "BuilderResource",
    "SelfBuildNeed",
    "SelfBuildPlacement",
    "default_self_build_resources",
    "plan_self_build",
    "self_build_resource_field",
]
