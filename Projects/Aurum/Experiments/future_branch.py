"""Experimental Future Branch decision model.

This is non-production orchestration logic. It ranks likely next machine/user states
and decides whether the operator should answer now, execute now, prepare now, or
wait at a real boundary. It does not itself perform external/destructive actions.
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

    def validate(self) -> None:
        if not self.name:
            raise ValueError("branch name required")
        if not 0 <= self.probability <= 1:
            raise ValueError("probability must be between 0 and 1")
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
            "disposition": disposition(item).value,
            "dependencies_satisfied": item.dependencies_satisfied,
            "real_boundary": item.has_real_boundary,
        }
        for item in ranked
    ]
