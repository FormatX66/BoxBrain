from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Iterable, Mapping, Sequence

from aurum_field import Field, encode
from field_native_vm import NativeExample, compile_native, execute_native, verify_native


BATCH_REVISION = "aurum-field-native-batch-v0"


@dataclass(frozen=True)
class NativeBatchItem:
    name: str
    parameters: tuple[str, ...]
    expression: Mapping[str, Any]
    examples: tuple[NativeExample, ...]
    invocation_arguments: Mapping[str, Any]


@dataclass(frozen=True)
class NativeBatchResult:
    name: str
    program_identity: str
    tape_identity: str
    examples: int
    passed: int
    output: Any


@dataclass(frozen=True)
class NativeBatchProof:
    batch_identity: str
    results: tuple[NativeBatchResult, ...]
    verified: bool
    source_generation_required: bool = False
    filesystem_build_required: bool = False
    subprocess_test_required: bool = False
    model_reasoning_required: bool = False


def batch_identity(items: Sequence[NativeBatchItem]) -> str:
    payload = [
        {
            "name": item.name,
            "parameters": list(item.parameters),
            "expression": dict(item.expression),
            "examples": [
                {"arguments": dict(example.arguments), "expected": example.expected}
                for example in item.examples
            ],
        }
        for item in sorted(items, key=lambda candidate: candidate.name)
    ]
    return hashlib.blake2s(
        b"AURUM-NATIVE-BATCH-0\x00"
        + encode({"revision": BATCH_REVISION, "items": payload})
    ).hexdigest()


def run_native_batch(items: Iterable[NativeBatchItem]) -> NativeBatchProof:
    """Compile, verify and invoke already-specified pure capabilities in one memory lane.

    This intentionally does not call a model, generate source, touch the filesystem,
    or launch subprocesses. Items are independent and sorted for deterministic proof.
    """
    ordered = tuple(sorted(items, key=lambda candidate: candidate.name))
    if not ordered:
        raise ValueError("native batch requires at least one item")
    if len({item.name for item in ordered}) != len(ordered):
        raise ValueError("native batch item names must be unique")

    results: list[NativeBatchResult] = []
    for item in ordered:
        program = compile_native(item.parameters, item.expression)
        verification = verify_native(program, item.examples)
        if not verification.verified:
            raise ValueError(
                f"native batch verification failed for {item.name}: "
                f"{verification.passed}/{verification.examples}"
            )
        output = execute_native(program, item.invocation_arguments)
        results.append(
            NativeBatchResult(
                name=item.name,
                program_identity=program.identity,
                tape_identity=program.tape_identity,
                examples=verification.examples,
                passed=verification.passed,
                output=output,
            )
        )

    return NativeBatchProof(
        batch_identity=batch_identity(ordered),
        results=tuple(results),
        verified=True,
    )


def native_batch_field(proof: NativeBatchProof) -> Field:
    field = Field()
    refs = []
    for result in proof.results:
        refs.append(
            field.add(
                "capability",
                {
                    "name": result.name,
                    "representation": BATCH_REVISION,
                    "program_identity": result.program_identity,
                    "tape_identity": result.tape_identity,
                    "examples": result.examples,
                    "passed": result.passed,
                    "verified": result.examples == result.passed,
                },
            )
        )
    field.add(
        "view",
        {
            "name": "aurum-field-native-batch-proof",
            "batch_identity": proof.batch_identity,
            "capabilities": refs,
            "verified": proof.verified,
            "model_reasoning_required": proof.model_reasoning_required,
            "source_generation_required": proof.source_generation_required,
            "filesystem_build_required": proof.filesystem_build_required,
            "subprocess_test_required": proof.subprocess_test_required,
        },
    )
    return field


__all__ = [
    "BATCH_REVISION",
    "NativeBatchItem",
    "NativeBatchProof",
    "NativeBatchResult",
    "batch_identity",
    "native_batch_field",
    "run_native_batch",
]
