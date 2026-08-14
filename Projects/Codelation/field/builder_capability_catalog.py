from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


CATALOG_REVISION = "aurum-builder-capability-catalog-v6"


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
        BuilderCapabilityDescriptor("io-plan","io_fabric","plan_io",frozenset({"bounded-token-selection","declarative-fact-binding","deterministic-conditional-selection","least-privilege-ranking","permission-aware-selection","semantic-port-selection"}),pure|frozenset({"permission-does-not-equal-authority"}),"none","semantic-port-plan-v0"),
        BuilderCapabilityDescriptor("labeled-text-projection","structured_projection","project_labeled_state",frozenset({"deterministic-labeled-text-projection","empty-value-normalization","human-readable-state-projection"}),pure|frozenset({"view-only","field-remains-authoritative"}),"none","labeled-text-projection-v0"),
        BuilderCapabilityDescriptor("required-condition-classifier","constraint_classification","classify_required_conditions",frozenset({"ordered-required-condition-classification","explicit-failure-reason-projection","fail-closed-condition-classification"}),pure|frozenset({"classification-only","no-implicit-authority"}),"none","required-condition-classification-v0"),
        BuilderCapabilityDescriptor("thresholded-unique-best-selector","score_selection","select_thresholded_unique_max",frozenset({"numeric-threshold-comparison","unique-maximum-selection","deterministic-fallback-selection"}),pure|frozenset({"recommendation-only","no-actuation"}),"none","thresholded-unique-best-v0"),
        BuilderCapabilityDescriptor("protected-token-filter","set_constraints","subtract_protected_tokens",frozenset({"multi-source-protected-set-difference","deterministic-token-canonicalization","constraint-preserving-filter"}),pure|frozenset({"simulation-only","no-actuation"}),"none","protected-token-filter-v0"),
        BuilderCapabilityDescriptor("reversible-state-delta-projection","reversible_state_delta","project_reversible_set_delta",frozenset({"reversible-set-delta","evidence-preserving-projection","deterministic-delta-canonicalization"}),pure|frozenset({"proposal-only","no-actuation","reversible"}),"none","reversible-state-delta-v0"),
    )


def get_builder_capability(name: str) -> BuilderCapabilityDescriptor | None:
    for descriptor in default_builder_capabilities():
        if descriptor.name == name:
            return descriptor
    return None


def find_builder_capability_candidates(requirements: Iterable[str], *, catalog: Iterable[BuilderCapabilityDescriptor] | None = None) -> tuple[BuilderCapabilityCandidate, ...]:
    required=frozenset(str(item) for item in requirements if str(item))
    if not required: return ()
    candidates=[]
    for descriptor in catalog or default_builder_capabilities():
        matched=tuple(sorted(required & descriptor.provides))
        if not matched: continue
        missing=tuple(sorted(required-descriptor.provides))
        candidates.append(BuilderCapabilityCandidate(descriptor.name,descriptor.module,descriptor.callable_name,matched,missing,len(matched)/len(required),descriptor.authority,descriptor.verification_adapter))
    return tuple(sorted(candidates,key=lambda item:(-item.coverage,len(item.missing),item.authority!="none",item.name)))


__all__=["CATALOG_REVISION","BuilderCapabilityCandidate","BuilderCapabilityDescriptor","default_builder_capabilities","find_builder_capability_candidates","get_builder_capability"]
