from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Iterable, Mapping, Sequence

from aurum_field import encode
from field_native_vm import NativeExample, compile_native, execute_native


SYNTHESIS_REVISION = "aurum-native-synthesis-v1"


@dataclass(frozen=True)
class SynthesisCandidate:
    expression: Mapping[str, Any]
    cost: int
    output_type: str
    signature_identity: str


@dataclass(frozen=True)
class SynthesisResult:
    found: bool
    expression: Mapping[str, Any] | None
    cost: int | None
    candidates_evaluated: int
    signatures_retained: int
    proof_identity: str


_TYPE_TEXT = "text"
_TYPE_TOKENS = "tokens"
_TYPE_NUMBER = "number"


def _value_type(value: Any) -> str | None:
    if isinstance(value, str):
        return _TYPE_TEXT
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _TYPE_NUMBER
    if isinstance(value, (list, tuple, set, frozenset)):
        return _TYPE_TOKENS
    return None


def _identity_value(value: Any) -> Any:
    """Project runtime values into Field's canonical scalar vocabulary for identity only."""
    if isinstance(value, float):
        return {"float_hex": value.hex()}
    if isinstance(value, (str, int, bytes)) or value is None or isinstance(value, bool):
        return value
    if isinstance(value, (list, tuple)):
        return [_identity_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        projected = [_identity_value(item) for item in value]
        return sorted(projected, key=encode)
    if isinstance(value, Mapping):
        return {str(key): _identity_value(item) for key, item in value.items()}
    raise ValueError(f"unsupported synthesis identity value: {type(value).__name__}")


def _signature(values: Sequence[Any]) -> tuple[str, str]:
    out_type = _value_type(values[0]) if values else None
    if out_type is None or any(_value_type(value) != out_type for value in values):
        raise ValueError("synthesis signature values must have one supported type")
    identity = hashlib.blake2s(
        b"AURUM-NATIVE-SYNTHESIS-SIGNATURE-0\x00"
        + encode([_identity_value(value) for value in values])
    ).hexdigest()
    return out_type, identity


def _expression_key(expression: Mapping[str, Any]) -> bytes:
    return encode(dict(expression))


def _evaluate(parameters: Sequence[str], expression: Mapping[str, Any], examples: Sequence[NativeExample]) -> tuple[Any, ...] | None:
    try:
        program = compile_native(parameters, expression)
        return tuple(execute_native(program, example.arguments) for example in examples)
    except (ValueError, TypeError, KeyError):
        return None


def _input_type(name: str, examples: Sequence[NativeExample]) -> str | None:
    values = [example.arguments.get(name) for example in examples]
    if not values:
        return None
    first = _value_type(values[0])
    if first is None or any(_value_type(value) != first for value in values):
        return None
    return first


def synthesize_native_expression(
    parameters: Sequence[str],
    examples: Iterable[NativeExample],
    *,
    max_cost: int = 8,
    max_signatures: int = 10000,
) -> SynthesisResult:
    """Find a small bounded native expression matching all examples.

    Search is deterministic and pure. It never generates source code, touches the
    filesystem, launches subprocesses, calls a model, or gains host authority.
    Observationally equivalent expressions are collapsed by their output signatures.
    """
    examples = tuple(examples)
    parameters = tuple(parameters)
    if not parameters or len(set(parameters)) != len(parameters):
        raise ValueError("parameters must be non-empty and unique")
    if not examples:
        raise ValueError("synthesis requires examples")
    if max_cost < 1 or max_signatures < 1:
        raise ValueError("synthesis bounds must be positive")
    required = set(parameters)
    for example in examples:
        if set(example.arguments) != required:
            raise ValueError("example arguments must exactly match parameters")

    expected = tuple(example.expected for example in examples)
    target_type, target_signature = _signature(expected)

    by_cost: dict[int, list[SynthesisCandidate]] = {}
    retained: dict[tuple[str, str], SynthesisCandidate] = {}
    evaluated = 0

    def admit(expression: Mapping[str, Any], cost: int) -> SynthesisCandidate | None:
        nonlocal evaluated
        values = _evaluate(parameters, expression, examples)
        evaluated += 1
        if values is None:
            return None
        try:
            out_type, signature = _signature(values)
        except ValueError:
            return None
        key = (out_type, signature)
        candidate = SynthesisCandidate(dict(expression), cost, out_type, signature)
        current = retained.get(key)
        if current is None or (cost, _expression_key(expression)) < (current.cost, _expression_key(current.expression)):
            retained[key] = candidate
            by_cost.setdefault(cost, []).append(candidate)
        return candidate

    for name in sorted(parameters):
        kind = _input_type(name, examples)
        if kind is None:
            continue
        candidate = admit({"op": "input", "name": name}, 1)
        if candidate and candidate.output_type == target_type and candidate.signature_identity == target_signature:
            proof = hashlib.blake2s(b"AURUM-NATIVE-SYNTHESIS-PROOF-0\x00" + _expression_key(candidate.expression)).hexdigest()
            return SynthesisResult(True, candidate.expression, candidate.cost, evaluated, len(retained), proof)

    unary_ops: tuple[tuple[str, str, str], ...] = (
        ("strip", _TYPE_TEXT, _TYPE_TEXT),
        ("casefold", _TYPE_TEXT, _TYPE_TEXT),
        ("split", _TYPE_TEXT, _TYPE_TOKENS),
        ("unique", _TYPE_TOKENS, _TYPE_TOKENS),
        ("sort", _TYPE_TOKENS, _TYPE_TOKENS),
        ("length", _TYPE_TOKENS, _TYPE_NUMBER),
    )
    binary_ops: tuple[tuple[str, str, str, str], ...] = (
        ("symmetric_difference", _TYPE_TOKENS, _TYPE_TOKENS, _TYPE_TOKENS),
        ("intersection", _TYPE_TOKENS, _TYPE_TOKENS, _TYPE_TOKENS),
        ("union", _TYPE_TOKENS, _TYPE_TOKENS, _TYPE_TOKENS),
        ("safe_divide", _TYPE_NUMBER, _TYPE_NUMBER, _TYPE_NUMBER),
    )

    def check(candidate: SynthesisCandidate | None) -> SynthesisResult | None:
        if candidate and candidate.output_type == target_type and candidate.signature_identity == target_signature:
            proof = hashlib.blake2s(
                b"AURUM-NATIVE-SYNTHESIS-PROOF-0\x00"
                + encode({"revision": SYNTHESIS_REVISION, "expression": dict(candidate.expression), "target": target_signature})
            ).hexdigest()
            return SynthesisResult(True, candidate.expression, candidate.cost, evaluated, len(retained), proof)
        return None

    for cost in range(2, max_cost + 1):
        prior = tuple(
            sorted(
                (candidate for c in range(1, cost) for candidate in by_cost.get(c, ())),
                key=lambda item: (item.cost, _expression_key(item.expression)),
            )
        )
        for op, source_type, _ in unary_ops:
            for source in prior:
                if source.cost + 1 != cost or source.output_type != source_type:
                    continue
                result = check(admit({"op": op, "value": dict(source.expression)}, cost))
                if result:
                    return result
                if len(retained) >= max_signatures:
                    break
            if len(retained) >= max_signatures:
                break
        if len(retained) >= max_signatures:
            break

        for op, left_type, right_type, _ in binary_ops:
            lefts = [candidate for candidate in prior if candidate.output_type == left_type]
            rights = [candidate for candidate in prior if candidate.output_type == right_type]
            for left in lefts:
                for right in rights:
                    if left.cost + right.cost + 1 != cost:
                        continue
                    result = check(
                        admit(
                            {"op": op, "left": dict(left.expression), "right": dict(right.expression)},
                            cost,
                        )
                    )
                    if result:
                        return result
                    if len(retained) >= max_signatures:
                        break
                if len(retained) >= max_signatures:
                    break
            if len(retained) >= max_signatures:
                break
        if len(retained) >= max_signatures:
            break

    proof = hashlib.blake2s(
        b"AURUM-NATIVE-SYNTHESIS-NOT-FOUND-0\x00"
        + encode({"revision": SYNTHESIS_REVISION, "parameters": list(parameters), "target": target_signature, "max_cost": max_cost})
    ).hexdigest()
    return SynthesisResult(False, None, None, evaluated, len(retained), proof)


__all__ = [
    "SYNTHESIS_REVISION",
    "SynthesisCandidate",
    "SynthesisResult",
    "synthesize_native_expression",
]
