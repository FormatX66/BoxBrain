from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Metrics:
    """Evidence collected from one implementation of the same capability."""

    success: bool
    invariant_preserved: bool
    attempts: int
    rollback_count: int
    duration_ms: float
    resource_cost: float
    regressions: int = 0
    learned_avoidance: bool = False


@dataclass(frozen=True)
class Decision:
    promotable: bool
    score: float
    reasons: tuple[str, ...]


def _positive(value: float, floor: float = 1e-9) -> float:
    return max(float(value), floor)


def evaluate(
    baseline: Metrics,
    candidate: Metrics,
    *,
    max_runtime_regression: float = 1.10,
    max_resource_regression: float = 1.10,
) -> Decision:
    """Compare a candidate against a known-good baseline.

    Safety and verified outcome are hard gates. Efficiency is deliberately a
    secondary concern so Aurum cannot promote a faster implementation that is
    less recoverable or less correct.
    """

    reasons: list[str] = []

    if not candidate.success:
        reasons.append("candidate did not reach the desired state")
    if not candidate.invariant_preserved:
        reasons.append("candidate violated a safety invariant")
    if candidate.regressions > baseline.regressions:
        reasons.append("candidate introduced additional regressions")
    if candidate.rollback_count > baseline.rollback_count:
        reasons.append("candidate required more rollbacks")
    if candidate.duration_ms > _positive(baseline.duration_ms) * max_runtime_regression:
        reasons.append("runtime regression exceeded budget")
    if candidate.resource_cost > _positive(baseline.resource_cost) * max_resource_regression:
        reasons.append("resource regression exceeded budget")

    attempt_gain = (baseline.attempts - candidate.attempts) / _positive(baseline.attempts)
    runtime_gain = (baseline.duration_ms - candidate.duration_ms) / _positive(baseline.duration_ms)
    resource_gain = (baseline.resource_cost - candidate.resource_cost) / _positive(baseline.resource_cost)
    rollback_gain = (baseline.rollback_count - candidate.rollback_count) / _positive(
        max(baseline.rollback_count, 1)
    )
    learning_bonus = 0.10 if candidate.learned_avoidance else 0.0

    score = (
        0.35 * attempt_gain
        + 0.25 * runtime_gain
        + 0.20 * resource_gain
        + 0.20 * rollback_gain
        + learning_bonus
    )

    hard_ok = not reasons
    # A candidate that merely matches the baseline is acceptable evidence, but
    # promotion requires a measurable improvement or newly demonstrated learning.
    improved = score > 0.0 or candidate.learned_avoidance
    if hard_ok and not improved:
        reasons.append("candidate is safe but has not demonstrated an improvement")

    return Decision(promotable=hard_ok and improved, score=score, reasons=tuple(reasons))


def choose_best(baseline: Metrics, candidates: Iterable[Metrics]) -> tuple[int | None, Decision | None]:
    """Return the best promotable candidate without mutating the baseline."""

    winner_index: int | None = None
    winner: Decision | None = None
    for index, candidate in enumerate(candidates):
        decision = evaluate(baseline, candidate)
        if decision.promotable and (winner is None or decision.score > winner.score):
            winner_index = index
            winner = decision
    return winner_index, winner
