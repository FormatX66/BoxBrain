"""Experimental Future Branch decision model.

This is non-production orchestration logic. It ranks likely next machine/user states,
decides whether the operator should answer now, execute now, prepare now, or wait at
a real boundary, and exposes bounded lookahead/confidence feedback. It does not
itself perform external/destructive actions.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class Disposition(str, Enum):
    ANSWER_NOW = "answer-now"
    EXECUTE_NOW = "execute-now"
    PREPARE_NOW = "prepare-now"
    WAIT_BOUNDARY = "wait-boundary"


@dataclass(frozen=True)
class FutureBranch:
    name: str
    probability: float
    impact: float
    user_time_saved: float
    preparation_leverage: float
    cost: float
    informational: bool = False
    safe_reversible_action: bool = False
    dependencies_satisfied: bool = False
    physical_boundary: bool = False
    destructive_boundary: bool = False
    credential_boundary: bool = False
    preference_boundary: bool = False
    irreversible_boundary: bool = False
    linearity: float = 0.5

    def validate(self) -> None:
        if not self.name:
            raise ValueError("branch name required")
        if not 0 <= self.probability <= 1:
            raise ValueError("probability must be between 0 and 1")
        if not 0 <= self.linearity <= 1:
            raise ValueError("linearity must be between 0 and 1")
        for value in (self.impact, self.user_time_saved, self.preparation_leverage, self.cost):
            if value < 0:
                raise ValueError("branch scoring values must be non-negative")

    @property
    def has_real_boundary(self) -> bool:
        return any(
            (
                self.physical_boundary,
                self.destructive_boundary,
                self.credential_boundary,
                self.preference_boundary,
                self.irreversible_boundary,
            )
        )


def priority(branch: FutureBranch) -> float:
    branch.validate()
    return (
        branch.probability
        * branch.impact
        * branch.user_time_saved
        * branch.preparation_leverage
        / max(branch.cost, 0.01)
    )


def disposition(branch: FutureBranch) -> Disposition:
    """Choose the strongest action allowed by evidence and boundaries."""
    branch.validate()
    if branch.has_real_boundary:
        return Disposition.WAIT_BOUNDARY
    if branch.informational:
        return Disposition.ANSWER_NOW
    if branch.safe_reversible_action and branch.dependencies_satisfied:
        return Disposition.EXECUTE_NOW
    return Disposition.PREPARE_NOW


def lookahead_depth(branch: FutureBranch, *, base_depth: int = 2, max_depth: int = 6) -> int:
    """Choose bounded speculative depth from probability and path linearity.

    High-confidence linear chains deserve deeper preparation because each additional
    step is less likely to be wasted. Forky or uncertain branches stay shallow. A
    real authority/physical boundary still stops execution regardless of depth.
    """
    branch.validate()
    if base_depth < 1 or max_depth < base_depth:
        raise ValueError("invalid lookahead bounds")
    confidence = branch.probability * branch.linearity
    if confidence >= 0.90:
        extra = 4
    elif confidence >= 0.78:
        extra = 3
    elif confidence >= 0.64:
        extra = 2
    elif confidence >= 0.48:
        extra = 1
    else:
        extra = 0
    return min(max_depth, base_depth + extra)


def human_confidence_feedback(branch: FutureBranch) -> str:
    """Return a short natural signal of how expected the resolved branch was."""
    branch.validate()
    if branch.probability >= 0.90:
        return "I had that path warm already."
    if branch.probability >= 0.70:
        return "That was one of the directions I was expecting."
    if branch.probability >= 0.45:
        return "That was plausible, but it wasn't one of my leading branches."
    return "That came from outside my leading branches, so I'm recalculating around it."


def should_ask_calibration(
    *,
    top_probability: float,
    runner_up_probability: float,
    wrong_branch_cost: float,
    early_training: bool = True,
) -> bool:
    """Ask a useful training question when uncertainty is worth resolving.

    Questions are favored early when the leading branch is weak, the top branches
    are close together, or preparing the wrong path would be relatively expensive.
    Strong linear futures should normally be prepared rather than interrupted by a
    question.
    """
    for value in (top_probability, runner_up_probability):
        if not 0 <= value <= 1:
            raise ValueError("probabilities must be between 0 and 1")
    if wrong_branch_cost < 0:
        raise ValueError("wrong_branch_cost must be non-negative")
    if not early_training:
        return False
    spread = top_probability - runner_up_probability
    return top_probability < 0.72 or spread < 0.18 or wrong_branch_cost >= 2.0


def rank_branches(branches: Iterable[FutureBranch], *, limit: int = 6) -> list[dict]:
    """Return a compact ranked Future Branch field.

    This intentionally includes more than pass/fail: callers may supply likely user
    questions, partial outcomes, stalls, adjacent opportunities, recovery paths, and
    next-capability branches.
    """
    if limit < 1:
        raise ValueError("limit must be positive")
    values = list(branches)
    for item in values:
        item.validate()
    ranked = sorted(values, key=lambda item: (-priority(item), item.name))[:limit]
    return [
        {
            "name": item.name,
            "priority": round(priority(item), 6),
            "probability": item.probability,
            "linearity": item.linearity,
            "lookahead_depth": lookahead_depth(item),
            "feedback": human_confidence_feedback(item),
            "disposition": disposition(item).value,
            "dependencies_satisfied": item.dependencies_satisfied,
            "real_boundary": item.has_real_boundary,
        }
        for item in ranked
    ]
