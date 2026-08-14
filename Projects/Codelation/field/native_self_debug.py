from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Any, Callable, Mapping, Sequence

from aurum_field import encode
from field_native_vm import NativeExample, compile_native, verify_native
from native_program_synthesis import _identity_value


SELF_DEBUG_REVISION = "aurum-native-self-debug-v0"


@dataclass(frozen=True)
class SelfDebugIssue:
    code: str
    domain: str
    blocking: bool
    detail: str


@dataclass(frozen=True)
class SelfDebugCounterexample:
    invariant: str
    observed: str
    expected: str
    detail: str


@dataclass(frozen=True)
class NativeSelfDebugReport:
    stage: str
    status: str
    invariants_checked: tuple[str, ...]
    issues: tuple[SelfDebugIssue, ...]
    counterexamples: tuple[SelfDebugCounterexample, ...]
    probable_failure_domains: tuple[str, ...]
    recommended_action: str
    model_escalation_advised: bool
    internal_next_action: str | None
    report_identity: str


def _runtime_argument_key(value: Any) -> Any:
    """Freeze bounded example arguments using runtime equality, not synthesis identity."""
    if value is None or isinstance(value, (str, bytes, bool, int, float)):
        return value
    if isinstance(value, list):
        return ("list", tuple(_runtime_argument_key(item) for item in value))
    if isinstance(value, tuple):
        return ("tuple", tuple(_runtime_argument_key(item) for item in value))
    if isinstance(value, Mapping):
        return (
            "mapping",
            tuple(sorted((str(key), _runtime_argument_key(item)) for key, item in value.items())),
        )
    if isinstance(value, (set, frozenset)):
        return (type(value).__name__, tuple(sorted(repr(item) for item in value)))
    return (type(value).__name__, repr(value))


def _numeric_variant(value: Any) -> Any | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        candidate = float(value)
        if math.isfinite(candidate) and candidate == value:
            return candidate
        return None
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        if value.is_integer():
            candidate = int(value)
            if candidate == value:
                return candidate
    return None


def _equivalent_variants(value: Any) -> tuple[Any, ...]:
    """Generate tiny verifier-equivalent counterexample candidates, bounded by structure."""
    variants: list[Any] = []
    numeric = _numeric_variant(value)
    if numeric is not None and type(numeric) is not type(value):
        variants.append(numeric)

    if isinstance(value, list):
        for index, item in enumerate(value[:8]):
            nested = _numeric_variant(item)
            if nested is None or type(nested) is type(item):
                continue
            clone = list(value)
            clone[index] = nested
            variants.append(clone)
    elif isinstance(value, tuple):
        for index, item in enumerate(value[:8]):
            nested = _numeric_variant(item)
            if nested is None or type(nested) is type(item):
                continue
            clone = list(value)
            clone[index] = nested
            variants.append(tuple(clone))
    return tuple(variants[:8])


def _target_type(value: Any) -> str:
    if isinstance(value, str):
        return "text"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, (list, tuple, set, frozenset)):
        return "tokens"
    return "unsupported"


def _identity_payload(value: Any) -> str:
    return repr(value)


def audit_native_self_build(
    parameters: Sequence[str],
    examples: Sequence[NativeExample],
    *,
    stage: str = "preflight",
    synthesis: Mapping[str, Any] | None = None,
    diagnosis: Mapping[str, Any] | None = None,
    identity_projector: Callable[[Any], Any] = _identity_value,
) -> NativeSelfDebugReport:
    """Audit Aurum's own builder before model escalation.

    The audit is deterministic and non-authoritative. It checks the semantic examples,
    probes verifier/synthesis equivalence with generated counterexamples, and classifies
    a failed search into bounded failure domains. It never edits the builder, routes a
    capability, executes discovered local capabilities, or grants host authority.
    """
    parameters = tuple(parameters)
    examples = tuple(examples)
    if stage not in {"preflight", "post-failure"}:
        raise ValueError("self-debug stage must be preflight or post-failure")
    if not parameters or not examples:
        raise ValueError("self-debug requires parameters and examples")

    invariants = [
        "example-arguments-match-parameters",
        "duplicate-example-consistency",
        "target-representation-supported",
        "verifier-synthesis-equivalence-agreement",
    ]
    issues: list[SelfDebugIssue] = []
    counterexamples: list[SelfDebugCounterexample] = []
    domains: set[str] = set()
    required = set(parameters)

    seen: dict[Any, Any] = {}
    values_to_probe: list[Any] = []
    for index, example in enumerate(examples):
        if set(example.arguments) != required:
            issues.append(
                SelfDebugIssue(
                    "example-argument-mismatch",
                    "semantic-spec",
                    True,
                    f"example {index} arguments do not exactly match declared parameters",
                )
            )
            domains.add("semantic-spec")
        frozen = _runtime_argument_key(example.arguments)
        prior = seen.get(frozen, object())
        if frozen in seen and prior != example.expected:
            issues.append(
                SelfDebugIssue(
                    "conflicting-duplicate-example",
                    "semantic-spec",
                    True,
                    f"equivalent example arguments have conflicting expected outputs at example {index}",
                )
            )
            domains.add("semantic-spec")
        else:
            seen[frozen] = example.expected

        if _target_type(example.expected) == "unsupported":
            issues.append(
                SelfDebugIssue(
                    "unsupported-target-representation",
                    "representation",
                    True,
                    f"example {index} expected value type is not representable by the native synthesizer",
                )
            )
            domains.add("representation")
        values_to_probe.append(example.expected)
        values_to_probe.extend(example.arguments.values())

    # Probe the actual verifier with pass-through programs rather than assuming its
    # equality semantics. If the verifier accepts two values as equivalent, synthesis
    # identity must collapse them too. This would have caught the historical 0 vs 0.0 bug.
    pass_through = compile_native(("probe",), {"op": "input", "name": "probe"})
    probed_pairs: set[tuple[str, str]] = set()
    for observed in values_to_probe[:128]:
        for expected in _equivalent_variants(observed):
            pair_key = (repr(observed), repr(expected))
            if pair_key in probed_pairs:
                continue
            probed_pairs.add(pair_key)
            verification = verify_native(
                pass_through,
                (NativeExample({"probe": observed}, expected),),
            )
            if not verification.verified:
                continue
            try:
                observed_identity = identity_projector(observed)
                expected_identity = identity_projector(expected)
            except (TypeError, ValueError, OverflowError) as exc:
                issues.append(
                    SelfDebugIssue(
                        "identity-projection-error",
                        "builder-equivalence",
                        True,
                        f"synthesis identity could not represent verifier-accepted values: {exc}",
                    )
                )
                domains.add("builder-equivalence")
                counterexamples.append(
                    SelfDebugCounterexample(
                        "verifier-synthesis-equivalence-agreement",
                        _identity_payload(observed),
                        _identity_payload(expected),
                        "verifier accepted the pair but synthesis identity projection raised",
                    )
                )
                continue
            if observed_identity != expected_identity:
                issues.append(
                    SelfDebugIssue(
                        "verification-synthesis-equivalence-mismatch",
                        "builder-equivalence",
                        True,
                        "verifier-equivalent values have different synthesis identities",
                    )
                )
                domains.add("builder-equivalence")
                counterexamples.append(
                    SelfDebugCounterexample(
                        "verifier-synthesis-equivalence-agreement",
                        _identity_payload(observed),
                        _identity_payload(expected),
                        "the verifier treats these as equal while synthesis identity distinguishes them",
                    )
                )

    recommended_action = "continue-native-synthesis"
    model_escalation = False
    internal_next_action: str | None = None

    blocking_domains = {issue.domain for issue in issues if issue.blocking}
    if "semantic-spec" in blocking_domains:
        recommended_action = "repair-semantic-spec"
        model_escalation = True
    elif "builder-equivalence" in blocking_domains:
        recommended_action = "repair-builder-equivalence"
        internal_next_action = "repair-builder-equivalence"
    elif "representation" in blocking_domains:
        recommended_action = "grow-or-change-representation"
        model_escalation = True

    if stage == "post-failure":
        invariants.append("post-failure-domain-triage")
        synthesis = dict(synthesis or {})
        diagnosis = dict(diagnosis or {})
        builder_learning = tuple(str(item) for item in diagnosis.get("builder_learning", ()) if str(item))
        local_candidates = diagnosis.get("local_capability_candidates", ())
        complete_local = []
        if isinstance(local_candidates, (list, tuple)):
            complete_local = [
                candidate
                for candidate in local_candidates
                if isinstance(candidate, Mapping)
                and not candidate.get("missing")
                and candidate.get("authority") == "none"
            ]

        if complete_local:
            domains.add("local-capability-reuse")
            recommended_action = "verify-existing-local-capability"
            internal_next_action = "verify-existing-local-capability"
            model_escalation = False
        elif builder_learning:
            domains.add("builder-vocabulary")
            recommended_action = "grow-builder-vocabulary"
            internal_next_action = "grow-builder-vocabulary"
            model_escalation = True
        elif int(synthesis.get("signatures_retained") or 0) >= 9000:
            domains.add("search-bound")
            recommended_action = "review-search-bound"
            internal_next_action = "review-search-bound"
            model_escalation = True
        elif not any(issue.blocking for issue in issues):
            domains.add("unclassified-builder-failure")
            recommended_action = "bounded-model-diagnosis"
            model_escalation = True

    blocking = any(issue.blocking for issue in issues)
    if blocking:
        status = "blocked"
    elif stage == "post-failure":
        status = "actionable"
    else:
        status = "clean"

    identity_payload: Mapping[str, Any] = {
        "revision": SELF_DEBUG_REVISION,
        "stage": stage,
        "status": status,
        "invariants": sorted(set(invariants)),
        "issues": [
            [issue.code, issue.domain, issue.blocking, issue.detail]
            for issue in issues
        ],
        "counterexamples": [
            [item.invariant, item.observed, item.expected, item.detail]
            for item in counterexamples
        ],
        "domains": sorted(domains),
        "recommended_action": recommended_action,
        "model_escalation_advised": model_escalation,
        "internal_next_action": internal_next_action,
    }
    report_identity = hashlib.blake2s(
        b"AURUM-NATIVE-SELF-DEBUG-0\x00" + encode(identity_payload)
    ).hexdigest()

    return NativeSelfDebugReport(
        stage=stage,
        status=status,
        invariants_checked=tuple(sorted(set(invariants))),
        issues=tuple(issues),
        counterexamples=tuple(counterexamples),
        probable_failure_domains=tuple(sorted(domains)),
        recommended_action=recommended_action,
        model_escalation_advised=model_escalation,
        internal_next_action=internal_next_action,
        report_identity=report_identity,
    )


__all__ = [
    "SELF_DEBUG_REVISION",
    "NativeSelfDebugReport",
    "SelfDebugCounterexample",
    "SelfDebugIssue",
    "audit_native_self_build",
]
