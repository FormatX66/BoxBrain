from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from field_native_vm import NativeExample


CATALOG_REVISION = "aurum-native-gap-catalog-v0"


@dataclass(frozen=True)
class NativeSemanticGap:
    name: str
    parameters: tuple[str, ...]
    examples: tuple[NativeExample, ...]
    invocation_arguments: Mapping[str, object]
    next_gap: str
    purpose: str
    principles: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ("pure", "deterministic", "no-io", "no-host-authority")
    max_synthesis_cost: int = 12


def _gaps() -> tuple[NativeSemanticGap, ...]:
    return (
        NativeSemanticGap(
            name="learning_delta_score",
            parameters=("before", "after"),
            examples=(
                NativeExample({"before": "field slush", "after": "field aurum slush"}, 1),
                NativeExample({"before": "a b", "after": "a c"}, 2),
                NativeExample({"before": "x y", "after": "x y"}, 0),
            ),
            invocation_arguments={"before": "field slush", "after": "field aurum slush"},
            next_gap="learning_overlap_score",
            purpose="Measure how many unique learning tokens changed between observations.",
            principles=("token order is not semantic", "duplicate tokens do not amplify change"),
            max_synthesis_cost=8,
        ),
        NativeSemanticGap(
            name="learning_overlap_score",
            parameters=("before", "after"),
            examples=(
                NativeExample({"before": "a b", "after": "a b c"}, 2),
                NativeExample({"before": "field slush", "after": "field aurum"}, 1),
                NativeExample({"before": "x", "after": "y"}, 0),
            ),
            invocation_arguments={"before": "field slush", "after": "field aurum slush"},
            next_gap="learning_union_size",
            purpose="Measure shared unique learning tokens between observations.",
            principles=("shared meaning is set-like",),
            max_synthesis_cost=8,
        ),
        NativeSemanticGap(
            name="learning_union_size",
            parameters=("before", "after"),
            examples=(
                NativeExample({"before": "a b", "after": "a b c"}, 3),
                NativeExample({"before": "field slush", "after": "field aurum"}, 3),
                NativeExample({"before": "x", "after": "x"}, 1),
            ),
            invocation_arguments={"before": "field slush", "after": "field aurum slush"},
            next_gap="learning_retention_ratio",
            purpose="Measure total unique learning vocabulary across two observations.",
            max_synthesis_cost=8,
        ),
        NativeSemanticGap(
            name="learning_retention_ratio",
            parameters=("before", "after"),
            examples=(
                NativeExample({"before": "a b", "after": "a b c"}, 2 / 3),
                NativeExample({"before": "field slush", "after": "field"}, 1 / 2),
                NativeExample({"before": "", "after": ""}, 0),
            ),
            invocation_arguments={"before": "a b", "after": "a b c"},
            next_gap="learning_novelty_ratio",
            purpose="Normalize retained shared learning by total observed vocabulary.",
            principles=("zero vocabulary yields zero ratio",),
            max_synthesis_cost=12,
        ),
        NativeSemanticGap(
            name="learning_novelty_ratio",
            parameters=("before", "after"),
            examples=(
                NativeExample({"before": "a b", "after": "a b c"}, 1 / 3),
                NativeExample({"before": "field slush", "after": "field"}, 1 / 2),
                NativeExample({"before": "x", "after": "x"}, 0),
                NativeExample({"before": "", "after": ""}, 0),
            ),
            invocation_arguments={"before": "a b", "after": "a b c"},
            next_gap="learning_stability_index",
            purpose="Normalize changed unique learning by total observed vocabulary.",
            principles=("zero vocabulary yields zero ratio",),
            max_synthesis_cost=12,
        ),
    )


_CATALOG = {gap.name: gap for gap in _gaps()}


def get_native_semantic_gap(name: str) -> NativeSemanticGap | None:
    return _CATALOG.get(name)


def native_semantic_gap_names() -> tuple[str, ...]:
    return tuple(sorted(_CATALOG))


__all__ = [
    "CATALOG_REVISION",
    "NativeSemanticGap",
    "get_native_semantic_gap",
    "native_semantic_gap_names",
]
