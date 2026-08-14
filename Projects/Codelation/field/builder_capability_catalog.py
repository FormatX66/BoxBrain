from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

CATALOG_REVISION="aurum-builder-capability-catalog-v8"

@dataclass(frozen=True)
class BuilderCapabilityDescriptor:
    name:str; module:str; callable_name:str; provides:frozenset[str]; constraints:frozenset[str]; authority:str="none"; verification_adapter:str|None=None

@dataclass(frozen=True)
class BuilderCapabilityCandidate:
    name:str; module:str; callable_name:str; matched:tuple[str,...]; missing:tuple[str,...]; coverage:float; authority:str; verification_adapter:str|None

def default_builder_capabilities()->tuple[BuilderCapabilityDescriptor,...]:
    pure=frozenset({"pure-decision","deterministic","no-host-authority"})
    D=BuilderCapabilityDescriptor
    return (
        D("io-plan","io_fabric","plan_io",frozenset({"bounded-token-selection","declarative-fact-binding","deterministic-conditional-selection","least-privilege-ranking","permission-aware-selection","semantic-port-selection"}),pure|frozenset({"permission-does-not-equal-authority"}),"none","semantic-port-plan-v0"),
        D("labeled-text-projection","structured_projection","project_labeled_state",frozenset({"deterministic-labeled-text-projection","empty-value-normalization","human-readable-state-projection"}),pure|frozenset({"view-only","field-remains-authoritative"}),"none","labeled-text-projection-v0"),
        D("required-condition-classifier","constraint_classification","classify_required_conditions",frozenset({"ordered-required-condition-classification","explicit-failure-reason-projection","fail-closed-condition-classification"}),pure|frozenset({"classification-only","no-implicit-authority"}),"none","required-condition-classification-v0"),
        D("thresholded-unique-best-selector","score_selection","select_thresholded_unique_max",frozenset({"numeric-threshold-comparison","unique-maximum-selection","deterministic-fallback-selection"}),pure|frozenset({"recommendation-only","no-actuation"}),"none","thresholded-unique-best-v0"),
        D("protected-token-filter","set_constraints","subtract_protected_tokens",frozenset({"multi-source-protected-set-difference","deterministic-token-canonicalization","constraint-preserving-filter"}),pure|frozenset({"simulation-only","no-actuation"}),"none","protected-token-filter-v0"),
        D("reversible-state-delta-projection","reversible_state_delta","project_reversible_set_delta",frozenset({"reversible-set-delta","evidence-preserving-projection","deterministic-delta-canonicalization"}),pure|frozenset({"proposal-only","no-actuation","reversible"}),"none","reversible-state-delta-v0"),
        D("bounded-preference-evidence","preference_evidence","project_preference_evidence",frozenset({"explicit-feedback-precedence","bounded-preference-evidence-projection","neutral-feedback-preservation"}),pure|frozenset({"local-learning-only","no-trait-inference","no-actuation"}),"none","preference-evidence-v0"),
        D("categorical-token-policy","categorical_policy","select_categorical_policy_tokens",frozenset({"declarative-category-policy","available-token-bounding","deterministic-policy-filtering"}),pure|frozenset({"proposal-only","no-actuation"}),"none","categorical-policy-v0"),
    )

def get_builder_capability(name:str)->BuilderCapabilityDescriptor|None:return next((d for d in default_builder_capabilities() if d.name==name),None)

def find_builder_capability_candidates(requirements:Iterable[str],*,catalog:Iterable[BuilderCapabilityDescriptor]|None=None)->tuple[BuilderCapabilityCandidate,...]:
    required=frozenset(str(x) for x in requirements if str(x))
    if not required:return ()
    out=[]
    for d in catalog or default_builder_capabilities():
        matched=tuple(sorted(required&d.provides))
        if matched:
            missing=tuple(sorted(required-d.provides));out.append(BuilderCapabilityCandidate(d.name,d.module,d.callable_name,matched,missing,len(matched)/len(required),d.authority,d.verification_adapter))
    return tuple(sorted(out,key=lambda x:(-x.coverage,len(x.missing),x.authority!="none",x.name)))

__all__=["CATALOG_REVISION","BuilderCapabilityCandidate","BuilderCapabilityDescriptor","default_builder_capabilities","find_builder_capability_candidates","get_builder_capability"]
