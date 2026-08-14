from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping, Sequence

from aurum_field import encode
from builder_capability_catalog import find_builder_capability_candidates
from field_native_vm import NativeExample


DIAGNOSIS_REVISION = "aurum-native-failure-diagnosis-v8"


@dataclass(frozen=True)
class NativeFailureDiagnosis:
    target_type: str
    categories: tuple[str, ...]
    observations: tuple[str, ...]
    builder_learning: tuple[str, ...]
    local_capability_candidates: tuple[Mapping[str, Any], ...]
    diagnosis_identity: str


def _value_type(value: Any) -> str:
    if isinstance(value, str): return "text"
    if isinstance(value, (int, float)) and not isinstance(value, bool): return "number"
    if isinstance(value, (list, tuple, set, frozenset)): return "tokens"
    return type(value).__name__


def _tokens(value: Any) -> set[str]:
    if isinstance(value, str): return set(value.split())
    if isinstance(value, (list, tuple, set, frozenset)): return {str(item) for item in value}
    return set()


def _labeled_projection_matches(parameters: Sequence[str], example: NativeExample) -> bool:
    return str(example.expected)==";".join(f"{name}={str(example.arguments.get(name) or 'none')}" for name in parameters)


def _reason_label(name: str) -> str:
    normalized=name[:-8] if name.endswith("_present") else name
    return normalized.replace("_","-")


def _required_condition_pattern(parameters: Sequence[str], examples: Sequence[NativeExample]) -> bool:
    success=[e for e in examples if not str(e.expected).startswith("blocked-")]
    if len(success)!=1:return False
    baseline=success[0]
    if len({str(baseline.arguments.get(n)) for n in parameters})!=1:return False
    for e in examples:
        if e is baseline:continue
        changed=[n for n in parameters if e.arguments.get(n)!=baseline.arguments.get(n)]
        if len(changed)!=1 or str(e.expected)!=f"blocked-{_reason_label(changed[0])}":return False
    return True


def _thresholded_unique_best_pattern(parameters: Sequence[str], examples: Sequence[NativeExample]) -> bool:
    if "threshold" not in parameters:return False
    score_names=[n for n in parameters if n!="threshold"]; valid_labels={n.replace("_","-") for n in score_names}; fallbacks=set()
    for e in examples:
        threshold=e.arguments.get("threshold")
        if isinstance(threshold,bool) or not isinstance(threshold,(int,float)):return False
        scores={n:e.arguments.get(n) for n in score_names}
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) for v in scores.values()):return False
        best=max(float(v) for v in scores.values()); winners=[n for n,v in scores.items() if float(v)==best]
        if best<float(threshold) or len(winners)!=1:fallbacks.add(str(e.expected))
        elif str(e.expected)!=winners[0].replace("_","-"):return False
    return len(fallbacks)==1 and not fallbacks.intersection(valid_labels)


def _protected_set_difference_pattern(parameters: Sequence[str], examples: Sequence[NativeExample]) -> bool:
    if "candidate" not in parameters:return False
    protected=[n for n in parameters if n!="candidate"]
    if not protected:return False
    for e in examples:
        wanted=_tokens(e.expected); candidate=_tokens(e.arguments.get("candidate")); protected_tokens=set().union(*(_tokens(e.arguments.get(n)) for n in protected))
        if wanted!=candidate-protected_tokens or str(e.expected)!=" ".join(sorted(wanted)):return False
    return True


def _reversible_delta_pattern(parameters: Sequence[str], examples: Sequence[NativeExample]) -> bool:
    if not {"current","target","evidence"}.issubset(parameters):return False
    for e in examples:
        current=_tokens(e.arguments.get("current")); target=_tokens(e.arguments.get("target")); evidence=str(e.arguments.get("evidence") or "none")
        added=" ".join(sorted(target-current)) or "none"; removed=" ".join(sorted(current-target)) or "none"
        if str(e.expected)!=f"add={added};remove={removed};evidence={evidence}":return False
    return True


def _preference_evidence_pattern(parameters: Sequence[str], examples: Sequence[NativeExample]) -> bool:
    required={"accepted","reverted","pinned","ignored","disabled"}
    if not required.issubset(parameters):return False
    def render(values:set[str])->str:return " ".join(sorted(values)) or "none"
    for e in examples:
        accepted=_tokens(e.arguments.get("accepted")); reverted=_tokens(e.arguments.get("reverted")); pinned=_tokens(e.arguments.get("pinned")); ignored=_tokens(e.arguments.get("ignored")); disabled=_tokens(e.arguments.get("disabled"))
        avoid=reverted|disabled; lock=pinned-disabled; prefer=(accepted|pinned)-avoid; neutral=ignored-avoid-prefer
        expected=f"prefer={render(prefer)};avoid={render(avoid)};lock={render(lock)};neutral={render(neutral)}"
        if str(e.expected)!=expected:return False
    return True


def diagnose_native_synthesis_failure(parameters: Sequence[str], examples: Sequence[NativeExample]) -> NativeFailureDiagnosis:
    parameters=tuple(parameters); examples=tuple(examples)
    if not parameters or not examples:raise ValueError("failure diagnosis requires parameters and examples")
    expected=tuple(e.expected for e in examples); types={_value_type(v) for v in expected}; target_type=next(iter(types)) if len(types)==1 else "mixed"
    categories:set[str]=set(); observations:set[str]=set(); learning:set[str]=set()
    if target_type=="text":
        labeled=all(_labeled_projection_matches(parameters,e) for e in examples); required_conditions=_required_condition_pattern(parameters,examples); thresholded=_thresholded_unique_best_pattern(parameters,examples); protected=_protected_set_difference_pattern(parameters,examples); reversible=_reversible_delta_pattern(parameters,examples); preference=_preference_evidence_pattern(parameters,examples)
        specific=labeled or required_conditions or thresholded or protected or reversible or preference
        if labeled:
            categories.add("labeled-parameter-projection"); observations.add("expected text is a stable parameter-labeled projection in declared parameter order"); learning.add("deterministic-labeled-text-projection")
            if any(any(not str(e.arguments.get(n) or "") for n in parameters) for e in examples):categories.add("explicit-empty-normalization"); observations.add("empty values are represented explicitly as 'none'"); learning.add("empty-value-normalization")
        if required_conditions:categories.add("ordered-required-condition-classification"); observations.add("one baseline success state is preserved while each single failed condition maps to its explicit blocked reason"); learning.update({"ordered-required-condition-classification","explicit-failure-reason-projection","fail-closed-condition-classification"})
        if thresholded:categories.add("thresholded-unique-best-selection"); observations.add("examples choose one unique highest score only above threshold and otherwise use one stable fallback"); learning.update({"numeric-threshold-comparison","unique-maximum-selection","deterministic-fallback-selection"})
        if protected:categories.add("multi-source-protected-set-difference"); observations.add("expected tokens are exactly candidate tokens minus the union of every protected input, with canonical ordering"); learning.update({"multi-source-protected-set-difference","deterministic-token-canonicalization","constraint-preserving-filter"})
        if reversible:categories.add("reversible-set-delta-projection"); observations.add("expected text preserves evidence and canonically represents target-current additions plus current-target removals"); learning.update({"reversible-set-delta","evidence-preserving-projection","deterministic-delta-canonicalization"})
        if preference:categories.add("bounded-preference-evidence-projection"); observations.add("explicit feedback classes map to prefer, avoid, lock, and neutral sets with disable/revert precedence"); learning.update({"explicit-feedback-precedence","bounded-preference-evidence-projection","neutral-feedback-preservation"})
        nonempty=[str(v) for v in expected if str(v)]
        if not specific and nonempty and any(str(v)=="" for v in expected):categories.add("conditional-empty-or-choice"); observations.add("examples require both an empty result and a non-empty text result"); learning.add("deterministic-conditional-selection")
        drawn={n:0 for n in parameters}
        for e in examples:
            wanted=str(e.expected)
            if not wanted:continue
            for n in parameters:
                if wanted in _tokens(e.arguments.get(n)):drawn[n]+=1
        for n,count in sorted(drawn.items()):
            if not specific and nonempty and count==len(nonempty):categories.add("select-token-from-input"); observations.add(f"every non-empty expected result is a token drawn from input '{n}'"); learning.add("bounded-token-selection")
        if not specific and "required" in parameters:
            req=set().union(*(_tokens(e.arguments.get("required")) for e in examples)); out=set(nonempty); carriers=[n for n in parameters if n!="required" and out and all((not str(e.expected)) or str(e.expected) in _tokens(e.arguments.get(n)) for e in examples)]
            if carriers and out.isdisjoint(req):categories.add("cross-vocabulary-fact-binding"); observations.add("requested semantic tokens and selected identifier tokens occupy different vocabularies"); learning.add("declarative-fact-binding")
    discovered=find_builder_capability_candidates(learning); local=[]
    for c in discovered:
        local.append({"name":c.name,"module":c.module,"callable":c.callable_name,"matched":list(c.matched),"missing":list(c.missing),"coverage":c.coverage,"authority":c.authority,"verification_adapter":c.verification_adapter,"routed":False,"executed":False})
        if not c.missing:categories.add("local-capability-candidate-covers-builder-learning"); observations.add(f"local capability candidate '{c.name}' covers all diagnosed builder-learning requirements but has not been routed or executed")
    identity_candidates=[{"name":c.name,"module":c.module,"callable":c.callable_name,"matched":list(c.matched),"missing":list(c.missing),"coverage_ratio":[len(c.matched),max(1,len(learning))],"authority":c.authority,"verification_adapter":c.verification_adapter} for c in discovered]
    payload:Mapping[str,Any]={"revision":DIAGNOSIS_REVISION,"parameters":list(parameters),"target_type":target_type,"categories":sorted(categories),"observations":sorted(observations),"builder_learning":sorted(learning),"local_capability_candidates":identity_candidates}
    identity=hashlib.blake2s(b"AURUM-NATIVE-FAILURE-DIAGNOSIS-0\x00"+encode(payload)).hexdigest()
    return NativeFailureDiagnosis(target_type,tuple(sorted(categories)),tuple(sorted(observations)),tuple(sorted(learning)),tuple(local),identity)


__all__=["DIAGNOSIS_REVISION","NativeFailureDiagnosis","diagnose_native_synthesis_failure"]
