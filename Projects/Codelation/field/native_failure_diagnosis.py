from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping, Sequence

from aurum_field import encode
from builder_capability_catalog import find_builder_capability_candidates
from field_native_vm import NativeExample


DIAGNOSIS_REVISION = "aurum-native-failure-diagnosis-v2"


@dataclass(frozen=True)
class NativeFailureDiagnosis:
    target_type: str
    categories: tuple[str, ...]
    observations: tuple[str, ...]
    builder_learning: tuple[str, ...]
    local_capability_candidates: tuple[Mapping[str, Any], ...]
    diagnosis_identity: str


def _value_type(value: Any) -> str:
    if isinstance(value, str):
        return "text"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, (list, tuple, set, frozenset)):
        return "tokens"
    return type(value).__name__


def _tokens(value: Any) -> set[str]:
    if isinstance(value, str):
        return set(value.split())
    if isinstance(value, (list, tuple, set, frozenset)):
        return {str(item) for item in value}
    return set()


def _labeled_projection_matches(parameters: Sequence[str], example: NativeExample) -> bool:
    expected = str(example.expected)
    parts: list[str] = []
    for name in parameters:
        raw = example.arguments.get(name)
        text = "" if raw is None else str(raw)
        parts.append(f"{name}={text if text else 'none'}")
    return expected == ";".join(parts)


def diagnose_native_synthesis_failure(
    parameters: Sequence[str],
    examples: Sequence[NativeExample],
) -> NativeFailureDiagnosis:
    parameters = tuple(parameters)
    examples = tuple(examples)
    if not parameters or not examples:
        raise ValueError("failure diagnosis requires parameters and examples")

    expected = tuple(example.expected for example in examples)
    target_types = {_value_type(value) for value in expected}
    target_type = next(iter(target_types)) if len(target_types) == 1 else "mixed"
    categories: set[str] = set()
    observations: set[str] = set()
    learning: set[str] = set()

    if target_type == "text":
        nonempty = [str(value) for value in expected if str(value)]
        if nonempty and any(str(value) == "" for value in expected):
            categories.add("conditional-empty-or-choice")
            observations.add("examples require both an empty result and a non-empty text result")
            learning.add("deterministic-conditional-selection")

        if all(_labeled_projection_matches(parameters, example) for example in examples):
            categories.add("labeled-parameter-projection")
            observations.add("expected text is a stable parameter-labeled projection in declared parameter order")
            learning.add("deterministic-labeled-text-projection")
            if any(any(not str(example.arguments.get(name) or "") for name in parameters) for example in examples):
                categories.add("explicit-empty-normalization")
                observations.add("empty values are represented explicitly as 'none'")
                learning.add("empty-value-normalization")

        drawn_from: dict[str, int] = {name: 0 for name in parameters}
        for example in examples:
            wanted = str(example.expected)
            if not wanted:
                continue
            for name in parameters:
                if wanted in _tokens(example.arguments.get(name)):
                    drawn_from[name] += 1
        for name, count in sorted(drawn_from.items()):
            if nonempty and count == len(nonempty):
                categories.add("select-token-from-input")
                observations.add(f"every non-empty expected result is a token drawn from input '{name}'")
                learning.add("bounded-token-selection")

        if "required" in parameters:
            required_vocab = set().union(*(_tokens(example.arguments.get("required")) for example in examples))
            output_vocab = set(nonempty)
            carrier_params = [
                name
                for name in parameters
                if name != "required"
                and output_vocab
                and all(
                    (not str(example.expected))
                    or str(example.expected) in _tokens(example.arguments.get(name))
                    for example in examples
                )
            ]
            if carrier_params and output_vocab.isdisjoint(required_vocab):
                categories.add("cross-vocabulary-fact-binding")
                observations.add("requested semantic tokens and selected identifier tokens occupy different vocabularies")
                learning.add("declarative-fact-binding")

    discovered = find_builder_capability_candidates(learning)
    local_candidates: list[Mapping[str, Any]] = []
    for candidate in discovered:
        local_candidates.append(
            {
                "name": candidate.name,
                "module": candidate.module,
                "callable": candidate.callable_name,
                "matched": list(candidate.matched),
                "missing": list(candidate.missing),
                "coverage": candidate.coverage,
                "authority": candidate.authority,
                "verification_adapter": candidate.verification_adapter,
                "routed": False,
                "executed": False,
            }
        )
        if not candidate.missing:
            categories.add("local-capability-candidate-covers-builder-learning")
            observations.add(
                f"local capability candidate '{candidate.name}' covers all diagnosed builder-learning requirements but has not been routed or executed"
            )

    identity_candidates = [
        {
            "name": candidate.name,
            "module": candidate.module,
            "callable": candidate.callable_name,
            "matched": list(candidate.matched),
            "missing": list(candidate.missing),
            "coverage_ratio": [len(candidate.matched), max(1, len(learning))],
            "authority": candidate.authority,
            "verification_adapter": candidate.verification_adapter,
        }
        for candidate in discovered
    ]
    payload: Mapping[str, Any] = {
        "revision": DIAGNOSIS_REVISION,
        "parameters": list(parameters),
        "target_type": target_type,
        "categories": sorted(categories),
        "observations": sorted(observations),
        "builder_learning": sorted(learning),
        "local_capability_candidates": identity_candidates,
    }
    identity = hashlib.blake2s(b"AURUM-NATIVE-FAILURE-DIAGNOSIS-0\x00" + encode(payload)).hexdigest()
    return NativeFailureDiagnosis(
        target_type=target_type,
        categories=tuple(sorted(categories)),
        observations=tuple(sorted(observations)),
        builder_learning=tuple(sorted(learning)),
        local_capability_candidates=tuple(local_candidates),
        diagnosis_identity=identity,
    )


__all__ = [
    "DIAGNOSIS_REVISION",
    "NativeFailureDiagnosis",
    "diagnose_native_synthesis_failure",
]
