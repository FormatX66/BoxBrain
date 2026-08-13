from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from capacity_mesh import RewardSignal
from capability_wave import CapabilityCompletion, UpgradeNode, emit_capability_wave
from field_native_vm import (
    NativeExample,
    NativeVMError,
    compile_native,
    execute_native,
    verify_native,
)


@dataclass(frozen=True)
class NativeSelfBuildProof:
    gap_name: str
    program_identity: str
    tape_identity: str
    examples: int
    passed: int
    invocation_output: Any
    learning_packet_identity: str
    wave_id: str
    wave_targets: tuple[str, ...]
    next_gap: str
    stages: tuple[str, ...]
    source_generation_required: bool = False
    filesystem_build_required: bool = False
    subprocess_test_required: bool = False


@dataclass(frozen=True)
class NativeGap:
    name: str
    parameters: tuple[str, ...]
    expression: Mapping[str, Any]
    examples: tuple[NativeExample, ...]
    purpose: str
    learned_principles: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()


def can_build_native(gap: NativeGap) -> bool:
    try:
        compile_native(gap.parameters, gap.expression)
        return True
    except (NativeVMError, ValueError, TypeError):
        return False


def run_native_self_build(
    gap: NativeGap,
    *,
    invocation_arguments: Mapping[str, Any],
    nodes: Sequence[UpgradeNode],
    next_gap: str,
) -> NativeSelfBuildProof:
    """Build/verify one bounded capability without source/files/subprocesses."""
    stages = ["gap-observed"]
    program = compile_native(gap.parameters, gap.expression)
    stages.append("native-program-compiled")

    verification = verify_native(program, gap.examples)
    if not verification.verified:
        raise NativeVMError(
            f"native verification failed: {verification.passed}/{verification.examples}"
        )
    stages.append("native-program-verified")

    output = execute_native(program, invocation_arguments)
    stages.append("native-program-invoked")

    completion = CapabilityCompletion(
        capability=gap.name,
        source_node="aurum-field-native-vm",
        source_variant_identity=program.tape_identity,
        requires=frozenset({"aurum-field-native-vm"}),
        reward=RewardSignal(verified=True, reusable=True, generalized=True),
        evidence=(
            "native-example-verification-pass",
            "native-program-invoked",
            "no-source-generation",
            "no-filesystem-build",
            "no-subprocess-test",
        ),
        learned_principles=gap.learned_principles,
        constraints=gap.constraints,
        success_conditions=(
            "all native examples pass",
            "native invocation succeeds",
        ),
        failed_approaches=(),
    )
    wave = emit_capability_wave(completion, nodes)
    stages.extend(("learning-wave-emitted", "next-gap-emitted"))

    return NativeSelfBuildProof(
        gap_name=gap.name,
        program_identity=program.identity,
        tape_identity=program.tape_identity,
        examples=verification.examples,
        passed=verification.passed,
        invocation_output=output,
        learning_packet_identity=wave.learning_packet_identity,
        wave_id=wave.wave_id,
        wave_targets=wave.target_nodes,
        next_gap=next_gap,
        stages=tuple(stages),
    )


def first_native_gap() -> NativeGap:
    return NativeGap(
        name="canonical_learning_tokens",
        parameters=("text",),
        expression={
            "op": "join",
            "separator": " ",
            "value": {
                "op": "sort",
                "value": {
                    "op": "unique",
                    "value": {
                        "op": "split",
                        "value": {
                            "op": "casefold",
                            "value": {
                                "op": "strip",
                                "value": {"op": "input", "name": "text"},
                            },
                        },
                    },
                },
            },
        },
        examples=(
            NativeExample({"text": "  Field field SLUSH  "}, "field slush"),
            NativeExample({"text": "Pi3 Morris GitHub Pi3"}, "github morris pi3"),
        ),
        purpose="Canonicalize learning vocabulary before semantic comparison.",
        learned_principles=(
            "canonical meaning should not depend on token order",
            "duplicate vocabulary should not amplify learning identity",
        ),
        constraints=("pure function", "no I/O", "no host authority"),
    )


__all__ = [
    "NativeGap",
    "NativeSelfBuildProof",
    "can_build_native",
    "first_native_gap",
    "run_native_self_build",
]
