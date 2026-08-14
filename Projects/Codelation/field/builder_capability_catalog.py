from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


CATALOG_REVISION = "aurum-builder-capability-catalog-v4"


@dataclass(frozen=True)
class BuilderCapabilityDescriptor:
    name: str
    module: str
    callable_name: str
    provides: frozenset[str]
    constraints: frozenset[str]
    authority: str = "none"
    verification_adapter: str | None = None


@dataclass(frozen=True)
class BuilderCapabilityCandidate:
    name: str
    module: str
    callable_name: str
    matched: tuple[str, ...]
    missing: tuple[str, ...]
    coverage: float
    authority: str
    verification_adapter: str | None


def default_builder_capabilities() -> tuple[BuilderCapabilityDescriptor, ...]:
    pure = frozenset({"pure-decision", "deterministic", "no-host-authority"})
    return (
        BuilderCapabilityDescriptor(
            name="io-plan",
            module="io_fabric",
            callable_name="plan_io",
            provides=frozenset({
                "bounded-token-selection",
                "declarative-fact-binding",
                "deterministic-conditional-selection",
                "least-privilege-ranking",
                "permission-aware-selection",
                "semantic-port-selection",
            }),
            constraints=pure | frozenset({"permission-does-not-equal-authority"}),
            authority="none",
            verification_adapter="semantic-port-plan-v0",
        ),
        BuilderCapabilityDescriptor(
            name="labeled-text-projection",
            module="structured_projection",
            callable_name="project_labeled_state",
            provides=frozenset({
                "deterministic-labeled-text-projection",
                "empty-value-normalization",
                "human-readable-state-projection",
            }),
            constraints=pure | frozenset({"view-only", "field-remains-authoritative"}),
            authority="none",
            verification_adapter="labeled-text-projection-v0",
        ),
        BuilderCapabilityDescriptor(
            name="required-condition-classifier",
            module="constraint_classification",
            callable_name="classify_required_conditions",
            provides=frozenset({
                "ordered-required-condition-classification",
                "explicit-failure-reason-projection",
                "fail-closed-condition-classification",
            }),
            constraints=pure | frozenset({"classification-only", "no-implicit-authority"}),
            authority="none",
            verification_adapter="required-condition-classification-v0",
        ),
        BuilderCapabilityDescriptor(
            name="thresholded-unique-best-selector",
            module="score_selection",
            callable_name="select_thresholded_unique_max",
            provides=frozenset({
                "numeric-threshold-comparison",
                "unique-maximum-selection",
                "deterministic-fallback-selection",
            }),
            constraints=pure | frozenset({"recommendation-only", "no-actuation"}),
            authority="none",
            verification_adapter="thresholded-unique-best-v0",
        ),
    )


def get_builder_capability(name: str) -> BuilderCapabilityDescriptor | None:
    for descriptor in default_builder_capabilities():
        if descriptor.name == name:
            return descriptor
    return None


def find_builder_capability_candidates(
    requirements: Iterable[str],
    *,
    catalog: Iterable[BuilderCapabilityDescriptor] | None = None,
) -> tuple[BuilderCapabilityCandidate, ...]:
    required = frozenset(str(item) for item in requirements if str(item))
    if not required:
        return ()
    candidates: list[BuilderCapabilityCandidate] = []
    for descriptor in catalog or default_builder_capabilities():
        matched = tuple(sorted(required & descriptor.provides))
        if not matched:
            continue
        missing = tuple(sorted(required - descriptor.provides))
        candidates.append(
            BuilderCapabilityCandidate(
                name=descriptor.name,
                module=descriptor.module,
                callable_name=descriptor.callable_name,
                matched=matched,
                missing=missing,
                coverage=len(matched) / len(required),
                authority=descriptor.authority,
                verification_adapter=descriptor.verification_adapter,
            )
        )
    return tuple(sorted(candidates, key=lambda item: (-item.coverage, len(item.missing), item.authority != "none", item.name)))


__all__ = [
    "CATALOG_REVISION",
    "BuilderCapabilityCandidate",
    "BuilderCapabilityDescriptor",
    "default_builder_capabilities",
    "find_builder_capability_candidates",
    "get_builder_capability",
]
