from __future__ import annotations
from dataclasses import dataclass
import hashlib
from typing import Any,Mapping,Sequence
from aurum_field import encode
from builder_capability_catalog import find_builder_capability_candidates
from field_native_vm import NativeExample

DIAGNOSIS_REVISION="aurum-native-failure-diagnosis-v9"
@dataclass(frozen=True)
class NativeFailureDiagnosis:
    target_type:str;categories:tuple[str,...];observations:tuple[str,...];builder_learning:tuple[str,...];local_capability_candidates:tuple[Mapping[str,Any],...];diagnosis_identity:str

def _value_type(v:Any)->str:
    if isinstance(v,str):return "text"
    if isinstance(v,(int,float)) and not isinstance(v,bool):return "number"
    if isinstance(v,(list,tuple,set,frozenset)):return "tokens"
    return type(v).__name__
def _tokens(v:Any)->set[str]:
    if isinstance(v,str):return set(v.split())
    if isinstance(v,(list,tuple,set,frozenset)):return {str(x) for x in v}
    return set()
def _labeled(p:Sequence[str],e:NativeExample)->bool:return str(e.expected)==";".join(f"{n}={str(e.arguments.get(n) or 'none')}" for n in p)
def _reason(n:str)->str:return (n[:-8] if n.endswith("_present") else n).replace("_","-")
def _required(p:Sequence[str],es:Sequence[NativeExample])->bool:
    ok=[e for e in es if not str(e.expected).startswith("blocked-")]
    if len(ok)!=1:return False
    b=ok[0]
    if len({str(b.arguments.get(n)) for n in p})!=1:return False
    return all(e is b or (lambda c:len(c)==1 and str(e.expected)==f"blocked-{_reason(c[0])}")([n for n in p if e.arguments.get(n)!=b.arguments.get(n)]) for e in es)
def _thresholded(p:Sequence[str],es:Sequence[NativeExample])->bool:
    if "threshold" not in p:return False
    names=[n for n in p if n!="threshold"];valid={n.replace("_","-") for n in names};fb=set()
    for e in es:
        t=e.arguments.get("threshold");scores={n:e.arguments.get(n) for n in names}
        if isinstance(t,bool) or not isinstance(t,(int,float)) or any(isinstance(v,bool) or not isinstance(v,(int,float)) for v in scores.values()):return False
        best=max(map(float,scores.values()));w=[n for n,v in scores.items() if float(v)==best]
        if best<float(t) or len(w)!=1:fb.add(str(e.expected))
        elif str(e.expected)!=w[0].replace("_","-"):return False
    return len(fb)==1 and not fb&valid
def _protected(p:Sequence[str],es:Sequence[NativeExample])->bool:
    if "candidate" not in p:return False
    other=[n for n in p if n!="candidate"]
    return bool(other) and all((lambda want,cand,prot:want==cand-prot and str(e.expected)==" ".join(sorted(want)))(_tokens(e.expected),_tokens(e.arguments.get("candidate")),set().union(*(_tokens(e.arguments.get(n)) for n in other))) for e in es)
def _reversible(p:Sequence[str],es:Sequence[NativeExample])->bool:
    if not {"current","target","evidence"}.issubset(p):return False
    for e in es:
        c=_tokens(e.arguments.get("current"));t=_tokens(e.arguments.get("target"));ev=str(e.arguments.get("evidence") or "none");a=" ".join(sorted(t-c)) or "none";r=" ".join(sorted(c-t)) or "none"
        if str(e.expected)!=f"add={a};remove={r};evidence={ev}":return False
    return True
def _preference(p:Sequence[str],es:Sequence[NativeExample])->bool:
    if not {"accepted","reverted","pinned","ignored","disabled"}.issubset(p):return False
    R=lambda s:" ".join(sorted(s)) or "none"
    for e in es:
        a=_tokens(e.arguments.get("accepted"));r=_tokens(e.arguments.get("reverted"));pin=_tokens(e.arguments.get("pinned"));i=_tokens(e.arguments.get("ignored"));d=_tokens(e.arguments.get("disabled"));avoid=r|d;lock=pin-d;prefer=(a|pin)-avoid;neutral=i-avoid-prefer
        if str(e.expected)!=f"prefer={R(prefer)};avoid={R(avoid)};lock={R(lock)};neutral={R(neutral)}":return False
    return True
def _categorical(p:Sequence[str],es:Sequence[NativeExample])->bool:
    if not {"mode","available"}.issubset(p) or len({str(e.arguments.get("mode")) for e in es})<3:return False
    for e in es:
        wanted=_tokens(e.expected);available=_tokens(e.arguments.get("available"))
        if not wanted.issubset(available) or str(e.expected)!=" ".join(sorted(wanted)):return False
    return True

def diagnose_native_synthesis_failure(parameters:Sequence[str],examples:Sequence[NativeExample])->NativeFailureDiagnosis:
    p=tuple(parameters);es=tuple(examples)
    if not p or not es:raise ValueError("failure diagnosis requires parameters and examples")
    types={_value_type(e.expected) for e in es};target=next(iter(types)) if len(types)==1 else "mixed";cats:set[str]=set();obs:set[str]=set();learn:set[str]=set()
    if target=="text":
        flags={"labeled":all(_labeled(p,e) for e in es),"required":_required(p,es),"thresholded":_thresholded(p,es),"protected":_protected(p,es),"reversible":_reversible(p,es),"preference":_preference(p,es),"categorical":_categorical(p,es)};specific=any(flags.values())
        rules={
            "labeled":("labeled-parameter-projection","expected text is a stable parameter-labeled projection",{"deterministic-labeled-text-projection"}),
            "required":("ordered-required-condition-classification","single failed requirements map to explicit blocked reasons",{"ordered-required-condition-classification","explicit-failure-reason-projection","fail-closed-condition-classification"}),
            "thresholded":("thresholded-unique-best-selection","unique highest scores above threshold win; ties/sub-threshold fall back",{"numeric-threshold-comparison","unique-maximum-selection","deterministic-fallback-selection"}),
            "protected":("multi-source-protected-set-difference","candidate tokens are filtered by the union of protected inputs",{"multi-source-protected-set-difference","deterministic-token-canonicalization","constraint-preserving-filter"}),
            "reversible":("reversible-set-delta-projection","target/current sets become canonical reversible deltas with evidence",{"reversible-set-delta","evidence-preserving-projection","deterministic-delta-canonicalization"}),
            "preference":("bounded-preference-evidence-projection","explicit feedback maps to prefer/avoid/lock/neutral with precedence",{"explicit-feedback-precedence","bounded-preference-evidence-projection","neutral-feedback-preservation"}),
            "categorical":("categorical-available-token-policy","categories map to canonical token policies bounded by available tokens",{"declarative-category-policy","available-token-bounding","deterministic-policy-filtering"}),}
        for k,on in flags.items():
            if on:
                c,o,l=rules[k];cats.add(c);obs.add(o);learn.update(l)
        nonempty=[str(e.expected) for e in es if str(e.expected)]
        if not specific and nonempty and any(str(e.expected)=="" for e in es):cats.add("conditional-empty-or-choice");obs.add("examples require empty/non-empty choice");learn.add("deterministic-conditional-selection")
        if not specific and "required" in p:
            req=set().union(*(_tokens(e.arguments.get("required")) for e in es));out=set(nonempty);carriers=[n for n in p if n!="required" and out and all((not str(e.expected)) or str(e.expected) in _tokens(e.arguments.get(n)) for e in es)]
            if carriers and out.isdisjoint(req):cats.add("cross-vocabulary-fact-binding");obs.add("requested semantics and output identifiers occupy different vocabularies");learn.add("declarative-fact-binding")
    found=find_builder_capability_candidates(learn);local=[]
    for c in found:
        local.append({"name":c.name,"module":c.module,"callable":c.callable_name,"matched":list(c.matched),"missing":list(c.missing),"coverage":c.coverage,"authority":c.authority,"verification_adapter":c.verification_adapter,"routed":False,"executed":False})
        if not c.missing:cats.add("local-capability-candidate-covers-builder-learning");obs.add(f"local capability candidate '{c.name}' covers all diagnosed builder-learning requirements but has not been routed or executed")
    ident=[{"name":c.name,"module":c.module,"callable":c.callable_name,"matched":list(c.matched),"missing":list(c.missing),"coverage_ratio":[len(c.matched),max(1,len(learn))],"authority":c.authority,"verification_adapter":c.verification_adapter} for c in found]
    payload:Mapping[str,Any]={"revision":DIAGNOSIS_REVISION,"parameters":list(p),"target_type":target,"categories":sorted(cats),"observations":sorted(obs),"builder_learning":sorted(learn),"local_capability_candidates":ident};identity=hashlib.blake2s(b"AURUM-NATIVE-FAILURE-DIAGNOSIS-0\x00"+encode(payload)).hexdigest()
    return NativeFailureDiagnosis(target,tuple(sorted(cats)),tuple(sorted(obs)),tuple(sorted(learn)),tuple(local),identity)

__all__=["DIAGNOSIS_REVISION","NativeFailureDiagnosis","diagnose_native_synthesis_failure"]
