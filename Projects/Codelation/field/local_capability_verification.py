from __future__ import annotations
from dataclasses import dataclass
import hashlib, importlib, inspect
from typing import Any, Mapping, Sequence
from aurum_field import encode
from builder_capability_catalog import get_builder_capability
from native_gap_catalog import NativeSemanticGap

LOCAL_VERIFICATION_REVISION="aurum-local-capability-verification-v7"
@dataclass(frozen=True)
class LocalCapabilityVerification:
    capability:str; module:str; callable_name:str; adapter:str; implementation_sha256:str; examples:int; passed:int; verified:bool; invocation_output:Any; verification_identity:str; authority_granted:bool=False; routed_to_host:bool=False

def _tokens(v:object)->tuple[str,...]:
    if isinstance(v,str):return tuple(x for x in v.split() if x)
    if isinstance(v,(list,tuple,set,frozenset)):return tuple(str(x) for x in v if str(x))
    raise ValueError("token input required")

def _condition_config(gap:NativeSemanticGap)->dict[str,Any]:
    success=[e for e in gap.examples if not str(e.expected).startswith("blocked-")]
    if len(success)!=1:raise ValueError("one success example required")
    vals={str(success[0].arguments[n]) for n in gap.parameters}
    if len(vals)!=1:raise ValueError("one positive token required")
    return {"positive":next(iter(vals)),"success":str(success[0].expected),"blocked_prefix":"blocked-"}

def _score_config(gap:NativeSemanticGap)->dict[str,Any]:
    names=[n for n in gap.parameters if n!="threshold"]; valid={n.replace("_","-") for n in names}; fb={str(e.expected) for e in gap.examples if str(e.expected) not in valid}
    if "threshold" not in gap.parameters or len(fb)!=1:raise ValueError("stable threshold fallback required")
    return {"fallback":next(iter(fb))}

def _categorical_config(gap:NativeSemanticGap)->dict[str,Any]:
    if not {"mode","available"}.issubset(gap.parameters):raise ValueError("categorical policy requires mode and available")
    profiles:dict[str,tuple[str,...]]={}
    for e in gap.examples:
        mode=str(e.arguments["mode"]); expected=tuple(sorted(_tokens(e.expected)))
        if mode in profiles and profiles[mode]!=expected:raise ValueError("conflicting category profile examples")
        profiles[mode]=expected
    return {"profiles":profiles}

def _invoke(adapter:str,fn:Any,args:Mapping[str,object],params:Sequence[str],cfg:Mapping[str,Any])->Any:
    if adapter=="semantic-port-plan-v0":
        p=fn(_tokens(args["required"]),available_ports=_tokens(args["available"]),permissions=_tokens(args["permissions"]));return "" if getattr(p,"missing",()) or len(getattr(p,"selected",()))!=1 else str(p.selected[0])
    if adapter=="labeled-text-projection-v0":return fn(args,order=params,empty_value="none",separator=";")
    if adapter=="required-condition-classification-v0":return fn(args,order=params,positive=cfg["positive"],success=cfg["success"],blocked_prefix=cfg["blocked_prefix"])
    if adapter=="thresholded-unique-best-v0":return fn({n:args[n] for n in params if n!="threshold"},threshold=float(args["threshold"]),fallback=cfg["fallback"])
    if adapter=="protected-token-filter-v0":return " ".join(fn(_tokens(args["candidate"]),*(_tokens(args[n]) for n in params if n!="candidate")))
    if adapter=="reversible-state-delta-v0":return fn(_tokens(args["current"]),_tokens(args["target"]),evidence=str(args["evidence"]),empty_value="none")
    if adapter=="preference-evidence-v0":return fn(*(_tokens(args[n]) for n in ("accepted","reverted","pinned","ignored","disabled")),empty_value="none")
    if adapter=="categorical-policy-v0":return " ".join(fn(str(args["mode"]),_tokens(args["available"]),cfg["profiles"]))
    raise ValueError(f"unsupported local verification adapter: {adapter}")

def verify_local_capability_for_gap(gap:NativeSemanticGap,capability_name:str)->LocalCapabilityVerification:
    d=get_builder_capability(capability_name)
    if d is None or d.authority!="none" or not {"pure-decision","deterministic","no-host-authority"}.issubset(d.constraints) or not d.verification_adapter:raise ValueError("local capability not eligible")
    fn=getattr(importlib.import_module(d.module),d.callable_name); impl=hashlib.sha256(inspect.getsource(fn).encode()).hexdigest();cfg:dict[str,Any]={}
    if d.verification_adapter=="required-condition-classification-v0":cfg=_condition_config(gap)
    elif d.verification_adapter=="thresholded-unique-best-v0":cfg=_score_config(gap)
    elif d.verification_adapter=="categorical-policy-v0":cfg=_categorical_config(gap)
    outputs=[];passed=0
    for e in gap.examples:
        observed=_invoke(d.verification_adapter,fn,e.arguments,gap.parameters,cfg);outputs.append(observed);passed+=observed==e.expected
    invocation=_invoke(d.verification_adapter,fn,gap.invocation_arguments,gap.parameters,cfg);verified=passed==len(gap.examples)
    identity=hashlib.sha256(encode({"revision":LOCAL_VERIFICATION_REVISION,"gap":gap.name,"capability":d.name,"module":d.module,"callable":d.callable_name,"adapter":d.verification_adapter,"adapter_config":cfg,"implementation_sha256":impl,"outputs":outputs,"passed":passed,"verified":verified,"authority_granted":False,"routed_to_host":False})).hexdigest()
    return LocalCapabilityVerification(d.name,d.module,d.callable_name,d.verification_adapter,impl,len(gap.examples),passed,verified,invocation,identity)

__all__=["LOCAL_VERIFICATION_REVISION","LocalCapabilityVerification","verify_local_capability_for_gap"]
