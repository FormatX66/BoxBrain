"""Calibration helpers for the experimental Future Branch model.

Prediction quality and preparation/execution quality are scored separately so the
system cannot claim success merely because it named a likely future. A useful
Future Branch hit should both anticipate the state and prepare or execute the
allowed work that state implies.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


PREDICTION_SCORES = {"exact": 1.0, "partial": 0.5, "miss": 0.0}
EXECUTION_SCORES = {
    "complete": 1.0,
    "prepared": 0.75,
    "partial": 0.5,
    "miss": 0.0,
    "boundary-correct": 1.0,
}


@dataclass(frozen=True)
class CalibrationEvent:
    family: str
    prediction: str
    execution: str
    user_turns_avoided: int = 0
    estimated_wait_seconds_saved: float = 0.0
    assumption_corrections: int = 0

    def validate(self) -> None:
        if not self.family:
            raise ValueError("family required")
        if self.prediction not in PREDICTION_SCORES:
            raise ValueError("invalid prediction score")
        if self.execution not in EXECUTION_SCORES:
            raise ValueError("invalid execution score")
        if self.user_turns_avoided < 0:
            raise ValueError("user_turns_avoided must be non-negative")
        if self.estimated_wait_seconds_saved < 0:
            raise ValueError("estimated_wait_seconds_saved must be non-negative")
        if self.assumption_corrections < 0:
            raise ValueError("assumption_corrections must be non-negative")

    @property
    def prediction_value(self) -> float:
        self.validate()
        return PREDICTION_SCORES[self.prediction]

    @property
    def execution_value(self) -> float:
        self.validate()
        return EXECUTION_SCORES[self.execution]

    @property
    def useful_hit_value(self) -> float:
        """Require both prediction and execution/preparation to earn full credit."""
        return self.prediction_value * self.execution_value


def summarize(events: Iterable[CalibrationEvent]) -> dict:
    values = list(events)
    for item in values:
        item.validate()
    if not values:
        return {
            "events": 0,
            "prediction_accuracy": 0.0,
            "execution_completeness": 0.0,
            "useful_hit_rate": 0.0,
            "user_turns_avoided": 0,
            "estimated_wait_seconds_saved": 0.0,
            "assumption_corrections": 0,
        }
    count = len(values)
    return {
        "events": count,
        "prediction_accuracy": round(sum(x.prediction_value for x in values) / count, 6),
        "execution_completeness": round(sum(x.execution_value for x in values) / count, 6),
        "useful_hit_rate": round(sum(x.useful_hit_value for x in values) / count, 6),
        "user_turns_avoided": sum(x.user_turns_avoided for x in values),
        "estimated_wait_seconds_saved": round(sum(x.estimated_wait_seconds_saved for x in values), 3),
        "assumption_corrections": sum(x.assumption_corrections for x in values),
    }


def probability_adjustment(*, prediction: str, execution: str, learning_rate: float = 0.12) -> float:
    """Return a bounded multiplicative adjustment for a branch-family prior.

    Exact + complete/prepared branches strengthen. Misses weaken. Correct waits at
    real boundaries are not punished. This is intentionally conservative because
    a few conversational samples should not dominate long-lived priors.
    """
    if prediction not in PREDICTION_SCORES or execution not in EXECUTION_SCORES:
        raise ValueError("invalid calibration labels")
    if not 0 < learning_rate <= 0.5:
        raise ValueError("learning_rate must be in (0, 0.5]")
    useful = PREDICTION_SCORES[prediction] * EXECUTION_SCORES[execution]
    centered = useful - 0.5
    return round(1.0 + (2.0 * learning_rate * centered), 6)
