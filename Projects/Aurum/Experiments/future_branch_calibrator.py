"""Natural-interaction calibration helpers for the experimental Future Branch model.

Prediction quality and preparation/execution quality are scored separately so the
system cannot claim success merely because it named a likely future.  Calibration
questions are derived from the current uncertainty shape rather than a fixed
quota.  Immediate human wait saved is kept separate from durable/compounding
value, and speculative work distinguishes gross work from net waste after useful
reusable state is retained.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


PREDICTION_SCORES = {"exact": 1.0, "partial": 0.5, "miss": 0.0}
EXECUTION_SCORES = {
    "complete": 1.0,
    "prepared": 0.75,
    "partial": 0.5,
    "miss": 0.0,
    "boundary-correct": 1.0,
}
PREDICTION_BASES = {"semantic", "surface-only"}


def _non_negative(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    value = float(value)
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _unit_interval(value: float, name: str) -> float:
    value = _non_negative(value, name)
    if value > 1:
        raise ValueError(f"{name} must be within [0, 1]")
    return value


@dataclass(frozen=True)
class CalibrationEvent:
    family: str
    prediction: str
    execution: str
    user_turns_avoided: int = 0
    estimated_wait_seconds_saved: float = 0.0
    assumption_corrections: int = 0
    prediction_basis: str = "semantic"
    reusable_partial_state_units: float = 0.0
    cached_artifact_units: float = 0.0
    calibration_learning_units: float = 0.0
    avoided_future_error_units: float = 0.0
    branch_shared_work_units: float = 0.0
    gross_speculative_work_units: float = 0.0

    def validate(self) -> None:
        if not self.family:
            raise ValueError("family required")
        if self.prediction not in PREDICTION_SCORES:
            raise ValueError("invalid prediction score")
        if self.execution not in EXECUTION_SCORES:
            raise ValueError("invalid execution score")
        if self.prediction_basis not in PREDICTION_BASES:
            raise ValueError("invalid prediction basis")
        if self.user_turns_avoided < 0:
            raise ValueError("user_turns_avoided must be non-negative")
        if self.assumption_corrections < 0:
            raise ValueError("assumption_corrections must be non-negative")
        _non_negative(self.estimated_wait_seconds_saved, "estimated_wait_seconds_saved")
        _non_negative(self.reusable_partial_state_units, "reusable_partial_state_units")
        _non_negative(self.cached_artifact_units, "cached_artifact_units")
        _non_negative(self.calibration_learning_units, "calibration_learning_units")
        _non_negative(self.avoided_future_error_units, "avoided_future_error_units")
        _non_negative(self.branch_shared_work_units, "branch_shared_work_units")
        _non_negative(self.gross_speculative_work_units, "gross_speculative_work_units")

    @property
    def prediction_value(self) -> float:
        self.validate()
        # A spelling/typing/punctuation-only coincidence is not a prediction win.
        if self.prediction_basis == "surface-only":
            return 0.0
        return PREDICTION_SCORES[self.prediction]

    @property
    def execution_value(self) -> float:
        self.validate()
        return EXECUTION_SCORES[self.execution]

    @property
    def useful_hit_value(self) -> float:
        """Require both semantic prediction and execution/preparation for full credit."""
        return self.prediction_value * self.execution_value

    @property
    def compounding_value_units(self) -> float:
        """Durable value that can reduce future cost after this immediate turn."""
        self.validate()
        return round(
            self.reusable_partial_state_units
            + self.cached_artifact_units
            + self.calibration_learning_units
            + self.avoided_future_error_units
            + self.branch_shared_work_units,
            6,
        )

    @property
    def net_speculative_waste_units(self) -> float:
        """Gross speculative work minus durable value, floored at zero.

        Durable value is deliberately not called a prediction hit: useful state may
        survive even when the selected future branch is not the one later chosen.
        """
        self.validate()
        return round(max(0.0, self.gross_speculative_work_units - self.compounding_value_units), 6)


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
            "compounding_value_units": 0.0,
            "gross_speculative_work_units": 0.0,
            "net_speculative_waste_units": 0.0,
        }
    count = len(values)
    return {
        "events": count,
        "prediction_accuracy": round(sum(x.prediction_value for x in values) / count, 6),
        "execution_completeness": round(sum(x.execution_value for x in values) / count, 6),
        "useful_hit_rate": round(sum(x.useful_hit_value for x in values) / count, 6),
        "user_turns_avoided": sum(x.user_turns_avoided for x in values),
        # Immediate human latency stays separate from long-horizon durable value.
        "estimated_wait_seconds_saved": round(sum(x.estimated_wait_seconds_saved for x in values), 3),
        "assumption_corrections": sum(x.assumption_corrections for x in values),
        "compounding_value_units": round(sum(x.compounding_value_units for x in values), 6),
        "gross_speculative_work_units": round(sum(x.gross_speculative_work_units for x in values), 6),
        "net_speculative_waste_units": round(sum(x.net_speculative_waste_units for x in values), 6),
    }


def probability_adjustment(*, prediction: str, execution: str, learning_rate: float = 0.12,
                           prediction_basis: str = "semantic") -> float:
    """Return a conservative multiplicative adjustment for a branch-family prior."""
    if prediction not in PREDICTION_SCORES or execution not in EXECUTION_SCORES:
        raise ValueError("invalid calibration labels")
    if prediction_basis not in PREDICTION_BASES:
        raise ValueError("invalid prediction basis")
    if not 0 < learning_rate <= 0.5:
        raise ValueError("learning_rate must be in (0, 0.5]")
    prediction_value = 0.0 if prediction_basis == "surface-only" else PREDICTION_SCORES[prediction]
    useful = prediction_value * EXECUTION_SCORES[execution]
    centered = useful - 0.5
    return round(1.0 + (2.0 * learning_rate * centered), 6)


def calibration_question_budget(
    probabilities: Sequence[float], *, path_clear: bool = False, safe: bool = False,
    cheap: bool = False, linear: bool = False
) -> dict:
    """Derive a short calibration-question budget from uncertainty shape.

    The thresholds intentionally mirror natural interaction rather than enforce a
    fixed questionnaire: a clear safe/cheap/linear route asks nothing; one dominant
    branch normally permits one discriminating question; two competitive branches
    permit about two; a broad cluster around 20-35% can justify up to three.
    """
    if not probabilities:
        return {"max_questions": 0, "shape": "no-branch", "goal": "none"}
    probs = [_unit_interval(value, "branch probability") for value in probabilities]
    total = sum(probs)
    if total <= 0:
        return {"max_questions": 0, "shape": "no-probability-mass", "goal": "none"}
    normalized = sorted((value / total for value in probs), reverse=True)

    if path_clear and safe and cheap and linear:
        return {"max_questions": 0, "shape": "clear-safe-linear", "goal": "proceed"}

    leader = normalized[0]
    runner_up = normalized[1] if len(normalized) > 1 else 0.0
    clustered = [value for value in normalized if 0.20 <= value <= 0.35]

    if leader >= 0.70:
        return {
            "max_questions": 1,
            "shape": "dominant-leader",
            "goal": "confirm-or-disprove-leader",
        }
    if len(normalized) >= 2 and 0.35 <= leader <= 0.65 and 0.30 <= runner_up <= 0.60:
        return {
            "max_questions": 2,
            "shape": "two-competitive-branches",
            "goal": "separate-top-two",
        }
    if len(clustered) >= 3:
        return {
            "max_questions": 3,
            "shape": "several-plausible-branches",
            "goal": "collapse-cluster",
        }
    if leader >= 0.55:
        return {"max_questions": 1, "shape": "soft-leader", "goal": "test-leader"}
    return {"max_questions": min(2, len(normalized) - 1), "shape": "diffuse", "goal": "reduce-uncertainty"}


def branch_priority(*, probability: float, impact: float, user_time_saved: float,
                    preparation_leverage: float, cost: float) -> float:
    """Rank work by probability × impact × time saved × leverage / cost."""
    probability = _unit_interval(probability, "probability")
    impact = _non_negative(impact, "impact")
    user_time_saved = _non_negative(user_time_saved, "user_time_saved")
    preparation_leverage = _non_negative(preparation_leverage, "preparation_leverage")
    cost = _non_negative(cost, "cost")
    if cost == 0:
        cost = 1e-9
    return round(probability * impact * user_time_saved * preparation_leverage / cost, 9)


def prediction_debt(*, probability: float, impact: float, user_time_saved: float,
                    preparation_leverage: float, cost: float, prepared_fraction: float) -> float:
    """Score high-value predicted work that remains unprepared."""
    prepared_fraction = _unit_interval(prepared_fraction, "prepared_fraction")
    return round(
        branch_priority(
            probability=probability,
            impact=impact,
            user_time_saved=user_time_saved,
            preparation_leverage=preparation_leverage,
            cost=cost,
        ) * (1.0 - prepared_fraction),
        9,
    )


def speculation_decision(*, expected_long_horizon_benefit: float, compute_cost: float = 0.0,
                         energy_cost: float = 0.0, ram_cost: float = 0.0,
                         storage_cost: float = 0.0, network_cost: float = 0.0,
                         privacy_cost: float = 0.0, foreground_cost: float = 0.0,
                         foreground_headroom_healthy: bool = True,
                         privacy_allowed: bool = True,
                         storage_endurance_healthy: bool = True) -> dict:
    """Continue speculation only when plausible long-horizon benefit exceeds total cost."""
    benefit = _non_negative(expected_long_horizon_benefit, "expected_long_horizon_benefit")
    costs = {
        "compute": _non_negative(compute_cost, "compute_cost"),
        "energy": _non_negative(energy_cost, "energy_cost"),
        "ram": _non_negative(ram_cost, "ram_cost"),
        "storage": _non_negative(storage_cost, "storage_cost"),
        "network": _non_negative(network_cost, "network_cost"),
        "privacy": _non_negative(privacy_cost, "privacy_cost"),
        "foreground": _non_negative(foreground_cost, "foreground_cost"),
    }
    total_cost = sum(costs.values())
    hard_gate = foreground_headroom_healthy and privacy_allowed and storage_endurance_healthy
    continue_speculation = hard_gate and benefit > total_cost
    return {
        "continue": continue_speculation,
        "expected_long_horizon_benefit": round(benefit, 6),
        "total_cost": round(total_cost, 6),
        "net_expected_value": round(benefit - total_cost, 6),
        "hard_gate_passed": hard_gate,
        "costs": costs,
    }


def feedback_cue_mode(sample_index: int, *, meaningful_turn: bool = True) -> str:
    """Vary early calibration feedback and deliberately leave some turns uncued."""
    if isinstance(sample_index, bool) or not isinstance(sample_index, int) or sample_index < 0:
        raise ValueError("sample_index must be a non-negative integer")
    if not meaningful_turn:
        return "none"
    # Deliberately irregular enough to collect broad natural-interaction samples.
    pattern = ("brief", "none", "detailed", "brief", "none", "compact-metric", "none")
    return pattern[sample_index % len(pattern)]
