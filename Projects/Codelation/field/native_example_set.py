from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable, Mapping, Any

from aurum_field import encode
from field_native_vm import NativeExample


EXAMPLE_SET_REVISION = "aurum-native-example-set-v0"


@dataclass(frozen=True)
class CanonicalExampleSet:
    identity: str
    examples: tuple[NativeExample, ...]
    input_examples: int
    duplicate_examples_removed: int


def _arguments_identity(arguments: Mapping[str, Any]) -> bytes:
    return encode({"arguments": dict(arguments)})


def _example_identity(example: NativeExample) -> bytes:
    return encode({"arguments": dict(example.arguments), "expected": example.expected})


def canonicalize_examples(examples: Iterable[NativeExample]) -> CanonicalExampleSet:
    """Deduplicate exact native examples and reject conflicting expectations.

    Equal argument mappings with different expected outputs are not silently merged;
    they represent a specification conflict that requires review.
    """
    by_arguments: dict[bytes, NativeExample] = {}
    seen_exact: set[bytes] = set()
    input_count = 0

    for example in examples:
        input_count += 1
        args_id = _arguments_identity(example.arguments)
        exact_id = _example_identity(example)
        current = by_arguments.get(args_id)
        if current is not None and current.expected != example.expected:
            raise ValueError("conflicting expected outputs for identical native arguments")
        by_arguments.setdefault(args_id, example)
        seen_exact.add(exact_id)

    ordered = tuple(
        by_arguments[key]
        for key in sorted(by_arguments)
    )
    payload = {
        "revision": EXAMPLE_SET_REVISION,
        "examples": [
            {"arguments": dict(example.arguments), "expected": example.expected}
            for example in ordered
        ],
    }
    identity = hashlib.blake2s(
        b"AURUM-NATIVE-EXAMPLE-SET-0\x00" + encode(payload)
    ).hexdigest()
    return CanonicalExampleSet(
        identity=identity,
        examples=ordered,
        input_examples=input_count,
        duplicate_examples_removed=max(0, input_count - len(ordered)),
    )


__all__ = [
    "EXAMPLE_SET_REVISION",
    "CanonicalExampleSet",
    "canonicalize_examples",
]
