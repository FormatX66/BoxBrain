from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from field_native_batch import NativeBatchItem, NativeBatchResult, batch_identity
from field_native_bundle import NativeProgramBundle, make_native_bundle
from field_native_vm import compile_native, execute_native, verify_native


BATCH_BUNDLE_REVISION = "aurum-field-native-batch-bundle-v0"


@dataclass(frozen=True)
class NativeBatchBundleProof:
    batch_identity: str
    bundle_sha256: str
    bundle_field_id: str
    results: tuple[NativeBatchResult, ...]
    bundle: NativeProgramBundle
    verified: bool
    source_generation_required: bool = False
    filesystem_build_required: bool = False
    subprocess_test_required: bool = False
    model_reasoning_required: bool = False


def run_native_batch_bundle(items: Iterable[NativeBatchItem]) -> NativeBatchBundleProof:
    """Build several specified pure capabilities and persist one native carrier."""
    ordered = tuple(sorted(items, key=lambda candidate: candidate.name))
    if not ordered:
        raise ValueError("native batch bundle requires at least one item")
    if len({item.name for item in ordered}) != len(ordered):
        raise ValueError("native batch bundle names must be unique")

    programs = {}
    results: list[NativeBatchResult] = []
    for item in ordered:
        program = compile_native(item.parameters, item.expression)
        verification = verify_native(program, item.examples)
        if not verification.verified:
            raise ValueError(
                f"native batch bundle verification failed for {item.name}: "
                f"{verification.passed}/{verification.examples}"
            )
        output = execute_native(program, item.invocation_arguments)
        programs[item.name] = program
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

    bundle = make_native_bundle(programs)
    return NativeBatchBundleProof(
        batch_identity=batch_identity(ordered),
        bundle_sha256=bundle.carrier_sha256,
        bundle_field_id=bundle.field_id,
        results=tuple(results),
        bundle=bundle,
        verified=True,
    )


__all__ = [
    "BATCH_BUNDLE_REVISION",
    "NativeBatchBundleProof",
    "run_native_batch_bundle",
]
