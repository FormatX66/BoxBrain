from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping, Sequence

from aurum_field import encode
from builder_capability_catalog import find_builder_capability_candidates
from field_native_vm import NativeExample


DIAGNOSIS_REVISION = "aurum-native-failure-diagnosis-v4"


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
    parts=[]
    for name in parameters:
        raw=example.arguments.get(name); text="" if raw is None else str(raw)
        parts.append(f"{name}={text if text else 'none'}")
    return str(example.expected)==";".join(parts)


def _reason_label(name: str) -> str:
    normalized=name[:-8] if name.endswith("_present") else name
    return normalized.replace("_","-")


def _required_condition_pattern(parameters: Sequence[str], examples: Sequence[NativeExample]) -> bool:
    success=[e for e in examples if not str(e.expected).startswith("blocked-")]
    if len(success)!=1: return False
    baseline=success[0]
    if len({str(baseline.arguments.get(n)) for n in parameters})!=1: return False
    for e in examples:
        if e is baseline: continue
        changed=[n for n in parameters if e.arguments.get(n)!=baseline.arguments.get(n)]
        if len(changed)!=1 or str(e.expected)!=f"blocked-{_reason_label(changed[0])}": return False
    return True


def _thresholded_unique_best_pattern(parameters: Sequence[str], examples: Sequence[NativeExample]) -> bool:
    if "threshold" not in parameters: return False
    score_names=[n for n in parameters if n!="threshold"]
    valid_labels={n.replace("_","-") for n in score_names}
    fallback_labels=set()
    for e in examples:
        threshold=e.arguments.get("threshold")
        if isinstance(threshold,bool) or not isinstance(threshold,(int,float)): return False
        scores={n:e.arguments.get(n) for n in score_names}
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) for v in scores.values()): return False
        best=max(float(v) for v in scores.values())
        winners=[n for n,v in scores.items() if float(v)==best]
        expected=str(e.expected)
        if best < float(threshold) or len(winners)!=1:
            fallback_labels.add(expected)
        elif expected != winners[0].replace("_","-"):
            return False
    return len(fallback_labels)==1 and not fallback_labels.intersection(valid_labels)


def diagnose_native_synthesis_failure(parameters: Sequence[str], examples: Sequence[NativeExample]) -> NativeFailureDiagnosis:
    parameters=tuple(parameters); examples=tuple(examples)
    if not parameters or not examples: raise ValueError("failure diagnosis requires parameters and examples")
    expected=tuple(e.expected for e in examples)
    target_types={_value_type(v) for v in expected}; target_type=next(iter(target_types)) if len(target_types)==1 else "mixed"
    categories:set[str]=set(); observations:set[str]=set(); learning:set[str]=set()

    if target_type=="text":
        nonempty=[str(v) for v in expected if str(v)]
        if nonempty and any(str(v)=="" for v in expected):
            categories.add("conditional-empty-or-choice"); observations.add("examples require both an empty result and a non-empty text result"); learning.add("deterministic-conditional-selection")
        if all(_labeled_projection_matches(parameters,e) for e in examples):
            categories.add("labeled-parameter-projection"); observations.add("expected text is a stable parameter-labeled projection in declared parameter order"); learning.add("deterministic-labeled-text-projection")
            if any(any(not str(e.arguments.get(n) or "") for n in parameters) for e in examples):
                categories.add("explicit-empty-normalization"); observations.add("empty values are represented explicitly as 'none'"); learning.add("empty-value-normalization")
        if _required_condition_pattern(parameters,examples):
            categories.add("ordered-required-condition-classification"); observations.add("one baseline success state is preserved while each single failed condition maps to its explicit blocked reason")
            learning.update({"ordered-required-condition-classification","explicit-failure-reason-projection","fail-closed-condition-classification"})
        if _thresholded_unique_best_pattern(parameters,examples):
            categories.add("thresholded-unique-best-selection"); observations.add("examples choose one unique highest score only above threshold and otherwise use one stable fallback")
            learning.update({"numeric-threshold-comparison","unique-maximum-selection","deterministic-fallback-selection"})
        drawn_from={n:0 for n in parameters}
        for e in examples:
            wanted=str(e.expected)
            if not wanted: continue
            for n in parameters:
                if wanted in _tokens(e.arguments.get(n)): drawn_from[n]+=1
        for n,count in sorted(drawn_from.items()):
            if nonempty and count==len(nonempty): categories.add("select-token-from-input"); observations.add(f"every non-empty expected result is a token drawn from input '{n}'"); learning.add("bounded-token-selection")
        if "required" in parameters:
            required_vocab=set().union(*(_tokens(e.arguments.get("required")) for e in examples)); output_vocab=set(nonempty)
            carrier_params=[n for n in parameters if n!="required" and output_vocab and all((not str(e.expected)) or str(e.expected) in _tokens(e.arguments.get(n)) for e in examples)]
            if carrier_params and output_vocab.isdisjoint(required_vocab): categories.add("cross-vocabulary-fact-binding"); observations.add("requested semantic tokens and selected identifier tokens occupy different vocabularies"); learning.add("declarative-fact-binding")

    discovered=find_builder_capability_candidates(learning); local_candidates=[]
    for c in discovered:
        local_candidates.append({"name":c.name,"module":c.module,"callable":c.callable_name,"matched":list(c.matched),"missing":list(c.missing),"coverage":c.coverage,"authority":c.authority,"verification_adapter":c.verification_adapter,"routed":False,"executed":False})
        if not c.missing: categories.add("local-capability-candidate-covers-builder-learning"); observations.add(f"local capability candidate '{c.name}' covers all diagnosed builder-learning requirements but has not been routed or executed")
    identity_candidates=[{"name":c.name,"module":c.module,"callable":c.callable_name,"matched":list(c.matched),"missing":list(c.missing),"coverage_ratio":[len(c.matched),max(1,len(learning))],"authority":c.authority,"verification_adapter":c.verification_adapter} for c in discovered]
    payload:Mapping[str,Any]={"revision":DIAGNOSIS_REVISION,"parameters":list(parameters),"target_type":target_type,"categories":sorted(categories),"observations":sorted(observations),"builder_learning":sorted(learning),"local_capability_candidates":identity_candidates}
    identity=hashlib.blake2s(b"AURUM-NATIVE-FAILURE-DIAGNOSIS-0\x00"+encode(payload)).hexdigest()
    return NativeFailureDiagnosis(target_type,tuple(sorted(categories)),tuple(sorted(observations)),tuple(sorted(learning)),tuple(local_candidates),identity)


__all__=["DIAGNOSIS_REVISION","NativeFailureDiagnosis","diagnose_native_synthesis_failure"]
