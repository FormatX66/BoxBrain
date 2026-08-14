from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib
import inspect
from typing import Any, Mapping, Sequence

from aurum_field import encode
from builder_capability_catalog import get_builder_capability
from native_gap_catalog import NativeSemanticGap


LOCAL_VERIFICATION_REVISION = "aurum-local-capability-verification-v6"


@dataclass(frozen=True)
class LocalCapabilityVerification:
    capability: str
    module: str
    callable_name: str
    adapter: str
    implementation_sha256: str
    examples: int
    passed: int
    verified: bool
    invocation_output: Any
    verification_identity: str
    authority_granted: bool = False
    routed_to_host: bool = False


def _tokens(value: object) -> tuple[str, ...]:
    if isinstance(value, str): return tuple(item for item in value.split() if item)
    if isinstance(value, (list, tuple, set, frozenset)): return tuple(str(item) for item in value if str(item))
    raise ValueError("verification adapter requires text/list token inputs")


def _condition_config(gap: NativeSemanticGap) -> Mapping[str, str]:
    success_examples=[e for e in gap.examples if not str(e.expected).startswith("blocked-")]
    if len(success_examples)!=1: raise ValueError("required-condition adapter needs one success example")
    success_example=success_examples[0]; positive_values={str(success_example.arguments[name]) for name in gap.parameters}
    if len(positive_values)!=1: raise ValueError("required-condition adapter needs one shared positive token")
    return {"positive":next(iter(positive_values)),"success":str(success_example.expected),"blocked_prefix":"blocked-"}


def _score_config(gap: NativeSemanticGap) -> Mapping[str, str]:
    if "threshold" not in gap.parameters: raise ValueError("thresholded selector adapter requires threshold parameter")
    score_names=tuple(name for name in gap.parameters if name!="threshold"); valid_labels={name.replace("_","-") for name in score_names}
    fallbacks={str(e.expected) for e in gap.examples if str(e.expected) not in valid_labels}
    if len(fallbacks)!=1: raise ValueError("thresholded selector adapter requires one stable fallback label")
    return {"fallback":next(iter(fallbacks))}


def _invoke(adapter: str, callable_obj: Any, arguments: Mapping[str, object], parameters: Sequence[str], config: Mapping[str, str]) -> Any:
    if adapter=="semantic-port-plan-v0":
        plan=callable_obj(_tokens(arguments["required"]),available_ports=_tokens(arguments["available"]),permissions=_tokens(arguments["permissions"]))
        if getattr(plan,"missing",()) or len(getattr(plan,"selected",()))!=1:return ""
        return str(plan.selected[0])
    if adapter=="labeled-text-projection-v0": return callable_obj(arguments,order=parameters,empty_value="none",separator=";")
    if adapter=="required-condition-classification-v0": return callable_obj(arguments,order=parameters,positive=config["positive"],success=config["success"],blocked_prefix=config["blocked_prefix"])
    if adapter=="thresholded-unique-best-v0":
        threshold=arguments.get("threshold")
        if isinstance(threshold,bool) or not isinstance(threshold,(int,float)): raise ValueError("thresholded selector requires numeric threshold")
        return callable_obj({name:arguments[name] for name in parameters if name!="threshold"},threshold=float(threshold),fallback=config["fallback"])
    if adapter=="protected-token-filter-v0":
        if "candidate" not in parameters: raise ValueError("protected token filter requires candidate parameter")
        return " ".join(callable_obj(_tokens(arguments["candidate"]),*(_tokens(arguments[name]) for name in parameters if name!="candidate")))
    if adapter=="reversible-state-delta-v0": return callable_obj(_tokens(arguments["current"]),_tokens(arguments["target"]),evidence=str(arguments["evidence"]),empty_value="none")
    if adapter=="preference-evidence-v0":
        required=("accepted","reverted","pinned","ignored","disabled")
        if not all(name in arguments for name in required): raise ValueError("preference evidence adapter requires explicit feedback inputs")
        return callable_obj(*(_tokens(arguments[name]) for name in required),empty_value="none")
    raise ValueError(f"unsupported local verification adapter: {adapter}")


def verify_local_capability_for_gap(gap: NativeSemanticGap, capability_name: str) -> LocalCapabilityVerification:
    descriptor=get_builder_capability(capability_name)
    if descriptor is None: raise ValueError("unknown local builder capability")
    if descriptor.authority!="none": raise ValueError("local capability verification requires authority-free candidate")
    if not {"pure-decision","deterministic","no-host-authority"}.issubset(descriptor.constraints): raise ValueError("local capability is not eligible for authority-free verification")
    if not descriptor.verification_adapter: raise ValueError("local capability has no bounded verification adapter")
    module=importlib.import_module(descriptor.module); callable_obj=getattr(module,descriptor.callable_name)
    implementation_sha256=hashlib.sha256(inspect.getsource(callable_obj).encode("utf-8")).hexdigest(); config:Mapping[str,str]={}
    if descriptor.verification_adapter=="required-condition-classification-v0": config=_condition_config(gap)
    elif descriptor.verification_adapter=="thresholded-unique-best-v0": config=_score_config(gap)
    outputs=[]; passed=0
    for example in gap.examples:
        observed=_invoke(descriptor.verification_adapter,callable_obj,example.arguments,gap.parameters,config); outputs.append(observed); passed+=observed==example.expected
    verified=passed==len(gap.examples); invocation_output=_invoke(descriptor.verification_adapter,callable_obj,gap.invocation_arguments,gap.parameters,config)
    payload={"revision":LOCAL_VERIFICATION_REVISION,"gap":gap.name,"capability":descriptor.name,"module":descriptor.module,"callable":descriptor.callable_name,"adapter":descriptor.verification_adapter,"adapter_config":dict(config),"implementation_sha256":implementation_sha256,"examples":len(gap.examples),"passed":passed,"outputs":outputs,"verified":verified,"authority_granted":False,"routed_to_host":False}
    verification_identity=hashlib.sha256(encode(payload)).hexdigest()
    return LocalCapabilityVerification(descriptor.name,descriptor.module,descriptor.callable_name,descriptor.verification_adapter,implementation_sha256,len(gap.examples),passed,verified,invocation_output,verification_identity)


__all__=["LOCAL_VERIFICATION_REVISION","LocalCapabilityVerification","verify_local_capability_for_gap"]
