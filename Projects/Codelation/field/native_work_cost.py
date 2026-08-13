from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from field_native_vm import NativeExample, NativeProgram
from native_example_set import canonicalize_examples


COST_REVISION = "aurum-native-work-cost-v0"


@dataclass(frozen=True)
class NativeWorkCost:
    tape_instructions: int
    input_examples: int
    unique_examples: int
    duplicate_examples_removed: int
    compile_units: int
    verification_units: int
    invocation_units: int
    total_units: int
    scheduling_class: str


def estimate_native_work(
    program: NativeProgram,
    examples: Iterable[NativeExample],
) -> NativeWorkCost:
    """Estimate deterministic native work without executing the candidate.

    Units are deliberately relative rather than wall-clock predictions. They let
    the scheduler compare candidates consistently and push larger verification
    sets into parallel cells while keeping tiny work local.
    """
    canonical = canonicalize_examples(examples)
    tape = len(program.tape)
    compile_units = max(1, tape)
    verification_units = tape * len(canonical.examples)
    invocation_units = max(1, tape)
    total = compile_units + verification_units + invocation_units
    if total <= 32:
        scheduling_class = "tiny-local"
    elif total <= 256:
        scheduling_class = "small-local-or-parallel"
    else:
        scheduling_class = "parallel-preferred"
    return NativeWorkCost(
        tape_instructions=tape,
        input_examples=canonical.input_examples,
        unique_examples=len(canonical.examples),
        duplicate_examples_removed=canonical.duplicate_examples_removed,
        compile_units=compile_units,
        verification_units=verification_units,
        invocation_units=invocation_units,
        total_units=total,
        scheduling_class=scheduling_class,
    )


__all__ = [
    "COST_REVISION",
    "NativeWorkCost",
    "estimate_native_work",
]
