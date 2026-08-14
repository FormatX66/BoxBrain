from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib
import inspect
from typing import Any, Mapping, Sequence

from aurum_field import encode
from builder_capability_catalog import get_builder_capability
from native_gap_catalog import NativeSemanticGap


LOCAL_VERIFICATION_REVISION = "aurum-local-capability-verification-v1"


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
    if isinstance(value, str):
        return tuple(item for item in value.split() if item)
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(str(item) for item in value if str(item))
    raise ValueError("verification adapter requires text/list token inputs")


def _invoke(
    adapter: str,
    callable_obj: Any,
    arguments: Mapping[str, object],
    parameters: Sequence[str],
) -> Any:
    if adapter == "semantic-port-plan-v0":
        required = _tokens(arguments["required"])
        available = _tokens(arguments["available"])
        permissions = _tokens(arguments["permissions"])
        plan = callable_obj(
            required,
            available_ports=available,
            permissions=permissions,
        )
        if getattr(plan, "missing", ()) or len(getattr(plan, "selected", ())) != 1:
            return ""
        return str(plan.selected[0])
    if adapter == "labeled-text-projection-v0":
        return callable_obj(arguments, order=parameters, empty_value="none", separator=";")
    raise ValueError(f"unsupported local verification adapter: {adapter}")


def verify_local_capability_for_gap(
    gap: NativeSemanticGap,
    capability_name: str,
) -> LocalCapabilityVerification:
    """Verify an already-present authority-free local capability against a gap.

    This executes only bounded pure decision/view code on semantic examples. It does
    not touch host I/O, grant authority, promote the implementation, or route work to
    a machine. Exact implementation source is hashed so verification is tied to the
    locally observed callable variant.
    """
    descriptor = get_builder_capability(capability_name)
    if descriptor is None:
        raise ValueError("unknown local builder capability")
    if descriptor.authority != "none":
        raise ValueError("local capability verification requires authority-free candidate")
    required_constraints = {"pure-decision", "deterministic", "no-host-authority"}
    if not required_constraints.issubset(descriptor.constraints):
        raise ValueError("local capability is not eligible for authority-free verification")
    if not descriptor.verification_adapter:
        raise ValueError("local capability has no bounded verification adapter")

    module = importlib.import_module(descriptor.module)
    callable_obj = getattr(module, descriptor.callable_name)
    source = inspect.getsource(callable_obj).encode("utf-8")
    implementation_sha256 = hashlib.sha256(source).hexdigest()

    outputs: list[Any] = []
    passed = 0
    for example in gap.examples:
        observed = _invoke(
            descriptor.verification_adapter,
            callable_obj,
            example.arguments,
            gap.parameters,
        )
        outputs.append(observed)
        if observed == example.expected:
            passed += 1
    verified = passed == len(gap.examples)
    invocation_output = _invoke(
        descriptor.verification_adapter,
        callable_obj,
        gap.invocation_arguments,
        gap.parameters,
    )

    payload = {
        "revision": LOCAL_VERIFICATION_REVISION,
        "gap": gap.name,
        "capability": descriptor.name,
        "module": descriptor.module,
        "callable": descriptor.callable_name,
        "adapter": descriptor.verification_adapter,
        "implementation_sha256": implementation_sha256,
        "examples": len(gap.examples),
        "passed": passed,
        "outputs": outputs,
        "verified": verified,
        "authority_granted": False,
        "routed_to_host": False,
    }
    verification_identity = hashlib.sha256(encode(payload)).hexdigest()
    return LocalCapabilityVerification(
        capability=descriptor.name,
        module=descriptor.module,
        callable_name=descriptor.callable_name,
        adapter=descriptor.verification_adapter,
        implementation_sha256=implementation_sha256,
        examples=len(gap.examples),
        passed=passed,
        verified=verified,
        invocation_output=invocation_output,
        verification_identity=verification_identity,
    )


__all__ = [
    "LOCAL_VERIFICATION_REVISION",
    "LocalCapabilityVerification",
    "verify_local_capability_for_gap",
]
