from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aurum_field import Field
from capacity_mesh import Node, WorkItem
from capability_growth import CapabilityNeed, build_candidates
import self_build_proof


@dataclass(frozen=True)
class GapSpecification:
    name: str
    purpose: str
    parameters: tuple[str, ...]
    expression: Mapping[str, Any]
    examples: tuple[tuple[Mapping[str, Any], Any], ...]
    constraints: tuple[str, ...] = ()
    learned_principles: tuple[str, ...] = ()


@dataclass(frozen=True)
class GapSupportAnalysis:
    gap: str
    required_operations: frozenset[str]
    supported_operations: frozenset[str]
    missing_operations: frozenset[str]
    substrate_needs: tuple[CapabilityNeed, ...]
    build_candidates: tuple[WorkItem, ...]

    @property
    def directly_buildable(self) -> bool:
        return not self.missing_operations


def expression_operations(expression: Mapping[str, Any]) -> frozenset[str]:
    found: set[str] = set()

    def walk(value: Any) -> None:
        if not isinstance(value, Mapping):
            return
        op = value.get("op")
        if isinstance(op, str) and op:
            found.add(op)
        for key in ("value", "left", "right"):
            child = value.get(key)
            if isinstance(child, Mapping):
                walk(child)

    walk(expression)
    return frozenset(found)


def current_self_build_operations() -> frozenset[str]:
    """Observe the kernel's actual bounded operation vocabulary rather than guessing it."""
    return frozenset(str(item) for item in getattr(self_build_proof, "_ALLOWED_OPS", ()))


def analyze_gap_support(spec: GapSpecification) -> GapSupportAnalysis:
    required = expression_operations(spec.expression)
    supported = current_self_build_operations()
    missing = required - supported
    needs = tuple(
        CapabilityNeed(
            name=f"self-build-op:{name}",
            demanded_by=(f"gap:{spec.name}",),
            occurrences=1,
        )
        for name in sorted(missing)
    )
    return GapSupportAnalysis(
        gap=spec.name,
        required_operations=required,
        supported_operations=supported,
        missing_operations=missing,
        substrate_needs=needs,
        build_candidates=build_candidates(needs),
    )


def learning_delta_score_spec() -> GapSpecification:
    """Bounded reasoning result for the first automatically emitted next gap."""

    def tokens(name: str) -> Mapping[str, Any]:
        return {
            "op": "unique",
            "value": {
                "op": "split",
                "value": {
                    "op": "casefold",
                    "value": {
                        "op": "strip",
                        "value": {"op": "input", "name": name},
                    },
                },
            },
        }

    return GapSpecification(
        name="learning_delta_score",
        purpose=(
            "Measure vocabulary change between two learning states so Aurum can "
            "prefer revisions that add or remove meaningful information."
        ),
        parameters=("before", "after"),
        expression={
            "op": "length",
            "value": {
                "op": "symmetric_difference",
                "left": tokens("before"),
                "right": tokens("after"),
            },
        },
        examples=(
            ({"before": "field slush", "after": "field slush aurum"}, 1),
            ({"before": "Pi3 Morris", "after": "morris pi3"}, 0),
            ({"before": "alpha beta", "after": "beta gamma"}, 2),
        ),
        constraints=("pure function", "no I/O", "no host authority"),
        learned_principles=(
            "learning change should be insensitive to token order and duplicates",
            "both additions and removals are meaningful deltas",
        ),
    )


def gap_analysis_field(spec: GapSpecification, analysis: GapSupportAnalysis) -> Field:
    field = Field()
    spec_ref = field.add(
        "fact",
        {
            "kind": "self-build-gap-specification",
            "name": spec.name,
            "purpose": spec.purpose,
            "parameters": list(spec.parameters),
            "required_operations": sorted(analysis.required_operations),
            "constraints": list(spec.constraints),
            "learned_principles": list(spec.learned_principles),
        },
    )
    need_refs = []
    for need in analysis.substrate_needs:
        need_refs.append(
            field.add(
                "fact",
                {
                    "kind": "self-build-substrate-need",
                    "name": need.name,
                    "demanded_by": list(need.demanded_by),
                    "occurrences": need.occurrences,
                },
            )
        )
    candidate_refs = []
    for work in analysis.build_candidates:
        candidate_refs.append(
            field.add(
                "capability",
                {
                    "name": work.name,
                    "accepts": sorted(work.requires),
                    "provides": [work.name.removeprefix("build-capability:")],
                    "traits": {"weight": work.weight, "declarative_candidate": True},
                },
            )
        )
    field.add(
        "view",
        {
            "name": "aurum-self-build-gap-support",
            "specification": spec_ref,
            "directly_buildable": analysis.directly_buildable,
            "supported_operations": sorted(analysis.supported_operations),
            "missing_operations": sorted(analysis.missing_operations),
            "substrate_needs": need_refs,
            "build_candidates": candidate_refs,
        },
    )
    return field


__all__ = [
    "GapSpecification",
    "GapSupportAnalysis",
    "analyze_gap_support",
    "current_self_build_operations",
    "expression_operations",
    "gap_analysis_field",
    "learning_delta_score_spec",
]
