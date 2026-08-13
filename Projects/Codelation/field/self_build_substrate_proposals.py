from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from aurum_field import Field
from self_build_gap_spec import GapSupportAnalysis


@dataclass(frozen=True)
class SubstrateProposal:
    capability: str
    operation: str
    arity: int
    semantic_contract: str
    validation_contract: tuple[str, ...]
    rendering_contract: str
    examples: tuple[tuple[Mapping[str, Any], Any], ...]
    reasoner: str = "gpt-reasoning"
    executable: bool = False
    promoted: bool = False


def reason_substrate_proposals(analysis: GapSupportAnalysis) -> tuple[SubstrateProposal, ...]:
    """Return bounded reasoner output for currently known missing safe primitives.

    These are design contracts only. They do not modify the self-build kernel and
    cannot be promoted without an isolated implementation/test result.
    """
    proposals: list[SubstrateProposal] = []
    for operation in sorted(analysis.missing_operations):
        capability = f"self-build-op:{operation}"
        if operation == "length":
            proposals.append(
                SubstrateProposal(
                    capability=capability,
                    operation=operation,
                    arity=1,
                    semantic_contract="Return the number of members in the evaluated child value.",
                    validation_contract=(
                        "exactly one mapping child named value",
                        "child expression must itself be valid",
                        "result must be a non-negative integer",
                    ),
                    rendering_contract="Apply the host language's bounded length primitive to the child value.",
                    examples=(
                        ({"value": []}, 0),
                        ({"value": ["a", "b"]}, 2),
                        ({"value": {"a", "b", "c"}}, 3),
                    ),
                )
            )
        elif operation == "symmetric_difference":
            proposals.append(
                SubstrateProposal(
                    capability=capability,
                    operation=operation,
                    arity=2,
                    semantic_contract=(
                        "Return members present in exactly one of the evaluated left/right collections; "
                        "input order and duplicate multiplicity must not affect membership."
                    ),
                    validation_contract=(
                        "exactly two mapping children named left and right",
                        "both child expressions must themselves be valid",
                        "comparison is set-semantic rather than sequence-semantic",
                    ),
                    rendering_contract=(
                        "Convert both evaluated collections to set semantics and compute symmetric difference."
                    ),
                    examples=(
                        ({"left": ["a", "b"], "right": ["b", "c"]}, {"a", "c"}),
                        ({"left": ["a", "a"], "right": ["a"]}, set()),
                    ),
                )
            )
        else:
            proposals.append(
                SubstrateProposal(
                    capability=capability,
                    operation=operation,
                    arity=0,
                    semantic_contract="Unspecified operation requires additional reasoning before implementation.",
                    validation_contract=("do not implement without a bounded semantic contract",),
                    rendering_contract="none",
                    examples=(),
                )
            )
    return tuple(proposals)


def substrate_proposal_field(
    analysis: GapSupportAnalysis,
    proposals: Sequence[SubstrateProposal],
) -> Field:
    field = Field()
    refs = []
    for proposal in proposals:
        refs.append(
            field.add(
                "fact",
                {
                    "kind": "self-build-substrate-proposal",
                    "parent_gap": analysis.gap,
                    "capability": proposal.capability,
                    "operation": proposal.operation,
                    "arity": proposal.arity,
                    "semantic_contract": proposal.semantic_contract,
                    "validation_contract": list(proposal.validation_contract),
                    "rendering_contract": proposal.rendering_contract,
                    "reasoner": proposal.reasoner,
                    "executable": proposal.executable,
                    "promoted": proposal.promoted,
                },
            )
        )
    field.add(
        "view",
        {
            "name": "aurum-self-build-substrate-proposals",
            "parent_gap": analysis.gap,
            "proposals": refs,
            "all_non_executable": all(not proposal.executable for proposal in proposals),
            "all_unpromoted": all(not proposal.promoted for proposal in proposals),
            "next_stage": "isolated-build-test",
        },
    )
    return field


__all__ = [
    "SubstrateProposal",
    "reason_substrate_proposals",
    "substrate_proposal_field",
]
