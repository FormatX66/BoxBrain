"""Experimental Future Branch decision model.

This is non-production orchestration logic. It ranks likely next machine/user states,
decides whether the operator should answer now, execute now, prepare now, or wait at
a real boundary, and exposes calibration/depth helpers. It does not itself perform
external or destructive actions.
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
    """Backward-compatible bounded depth estimate for callers that need an integer.

    This is only an estimate. `lookahead_mode(...)=TO_BOUNDARY` overrides the idea of
    an arbitrary numeric ceiling when resources are healthy and the path is highly
    probable/linear.
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


def lookahead_mode(
    branch: FutureBranch,
    *,
    resource_headroom: float,
) -> LookaheadMode:
    """Choose preparation depth class from probability, linearity, and resources.

    `resource_headroom` summarizes reclaimable CPU/RAM/Slush/storage after foreground
    reserves. A very strong, highly linear path is prepared until a real boundary or
    resource reserve is reached rather than stopping at an arbitrary step count.
    """
    branch.validate()
    if not 0 <= resource_headroom <= 1:
        raise ValueError("resource_headroom must be between 0 and 1")
    pressure = branch.probability * branch.linearity * resource_headroom
    if branch.probability >= 0.85 and branch.linearity >= 0.85 and resource_headroom >= 0.60:
        return LookaheadMode.TO_BOUNDARY
    if pressure >= 0.45:
        return LookaheadMode.DEEP
    if pressure >= 0.20:
        return LookaheadMode.MODERATE
    return LookaheadMode.SHALLOW


def calibration_question_budget(probabilities: Iterable[float]) -> int:
    """Recommend how many targeted questions are worth asking early in training.

    Heuristic:
    * several ~30% branches -> up to three questions;
    * two competitive ~50% branches -> around two;
    * one dominant branch -> usually one discriminating question, preferably aimed
      at confirming/disproving the leader rather than asking the obvious thing.
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


def should_ask_calibration(
    *,
    top_probability: float,
    runner_up_probability: float,
    wrong_branch_cost: float,
    early_training: bool = True,
) -> bool:
    """Ask when the information gain is worth the interruption."""
    for value in (top_probability, runner_up_probability):
        if not 0 <= value <= 1:
            raise ValueError("probabilities must be between 0 and 1")
    if wrong_branch_cost < 0:
        raise ValueError("wrong_branch_cost must be non-negative")
    if not early_training:
        return False
    spread = top_probability - runner_up_probability
    return top_probability < 0.72 or spread < 0.18 or wrong_branch_cost >= 2.0


def confidence_band(probability: float, *, was_leading: bool) -> str:
    """Return a neutral confidence class for varied human feedback."""
    if not 0 <= probability <= 1:
        raise ValueError("probability must be between 0 and 1")
    if was_leading and probability >= 0.80:
        return "warm"
    if probability >= 0.50:
        return "expected"
    if probability >= 0.20:
        return "plausible"
    return "outside-leading-field"


def human_confidence_feedback(branch: FutureBranch, *, variant: int = 0) -> str:
    """Return varied natural feedback so training samples do not use one fixed cue."""
    branch.validate()
    band = confidence_band(branch.probability, was_leading=branch.probability >= 0.70)
    variants = {
        "warm": (
            "I had that path warm already.",
            "That was already one of my hottest branches.",
            "I was leaning hard in that direction, so most of that path was warm.",
        ),
        "expected": (
            "That was one of the directions I was expecting.",
            "That fit one of my stronger branches.",
            "I had that in the active field, though not as a lock.",
        ),
        "plausible": (
            "That was plausible, but it wasn't one of my leading branches.",
            "I had that as a live possibility, but it was running cooler.",
            "That was in the field, just not near the top.",
        ),
        "outside-leading-field": (
            "That came from outside my leading branches, so I'm recalculating around it.",
            "That was out of my warm field; I need to fan out from here.",
            "I didn't have that path meaningfully warmed, so this one needs fresh compute.",
        ),
    }
    choices = variants[band]
    return choices[variant % len(choices)]


def rank_branches(branches: Iterable[FutureBranch], *, limit: int = 6) -> list[dict]:
    """Return a compact ranked Future Branch field."""
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
