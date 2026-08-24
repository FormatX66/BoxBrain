"""Experimental Future Branch decision model.

This is non-production orchestration logic. It ranks likely next machine/user states,
decides whether the operator should answer now, execute now, prepare now, or wait at
a real boundary, and exposes small calibration helpers for question count and
lookahead depth. It does not itself perform external/destructive actions.
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


class LookaheadMode(str, Enum):
    SHALLOW = "shallow"
    MODERATE = "moderate"
    DEEP = "deep"
    TO_BOUNDARY = "to-boundary"


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


def calibration_question_budget(probabilities: Iterable[float]) -> int:
    """Recommend a small question count from branch uncertainty.

    This intentionally follows a human-calibration heuristic rather than pretending
    the initial probabilities are perfectly calibrated:
    * several roughly-even low/moderate branches can justify up to three questions;
    * two competitive medium branches usually justify two;
    * one dominant branch usually justifies one discriminating confirmation question.
    """
    values = sorted((float(p) for p in probabilities), reverse=True)
    if any(p < 0 or p > 1 for p in values):
        raise ValueError("probabilities must be between 0 and 1")
    meaningful = [p for p in values if p >= 0.15]
    if not meaningful:
        return 0
    if meaningful[0] >= 0.70:
        return 1
    if len(meaningful) >= 3 and meaningful[0] < 0.50 and meaningful[2] >= 0.20:
        return 3
    if len(meaningful) >= 2 and meaningful[0] >= 0.40 and meaningful[1] >= 0.30:
        return 2
    return min(2, len(meaningful))


def lookahead_mode(
    *,
    probability: float,
    linearity: float,
    resource_headroom: float,
) -> LookaheadMode:
    """Choose how deeply to prepare a branch before a real boundary.

    `resource_headroom` is a normalized summary of reclaimable compute/RAM/Slush/
    storage budget after foreground reserves. Very high-confidence, highly linear
    branches with healthy resources are not assigned an arbitrary step count: they
    are prepared until the first real dependency/safety/authority/resource boundary.
    """
    for name, value in {
        "probability": probability,
        "linearity": linearity,
        "resource_headroom": resource_headroom,
    }.items():
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
    pressure = probability * linearity * resource_headroom
    if probability >= 0.85 and linearity >= 0.85 and resource_headroom >= 0.60:
        return LookaheadMode.TO_BOUNDARY
    if pressure >= 0.45:
        return LookaheadMode.DEEP
    if pressure >= 0.20:
        return LookaheadMode.MODERATE
    return LookaheadMode.SHALLOW


def confidence_band(probability: float, *, was_leading: bool) -> str:
    """Return a neutral human-feedback band, not a bragging score."""
    if not 0 <= probability <= 1:
        raise ValueError("probability must be between 0 and 1")
    if was_leading and probability >= 0.80:
        return "warm"
    if probability >= 0.50:
        return "expected"
    if probability >= 0.20:
        return "plausible"
    return "outside-leading-field"


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
