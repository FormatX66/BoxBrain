"""Expected-value gate for speculative Future Branch execution.

This module answers a different question from branch ranking: not "which future is
most likely?" but "is it worth running this bounded process now to learn whether the
future is feasible?"

A high expected failure rate is not automatically a reason to avoid a run. If an
early failure would produce useful evidence or prevent expensive downstream work,
the information value of failing early can make a heavy process worth pre-running.

This gate never authorizes physical, destructive, credentialed, irreversible, or
otherwise consequential work. Those remain real boundaries even when the computed
information value is large.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PreRunDecision(str, Enum):
    PRE_RUN = "pre-run"
    SKIP_LOW_VALUE = "skip-low-value"
    HOLD_RESOURCES = "hold-resources"
    WAIT_BOUNDARY = "wait-boundary"


@dataclass(frozen=True)
class FeasibilityProbe:
    name: str
    success_probability: float
    success_value: float
    failure_learning_value: float
    downstream_cost_avoided_if_failure: float
    run_cost: float
    risk_exposure: float
    resource_headroom: float
    minimum_resource_headroom: float = 0.15
    reversible: bool = True
    external_side_effects: bool = False
    requires_authorization: bool = False
    authorized: bool = False

    def validate(self) -> None:
        if not self.name:
            raise ValueError("probe name required")
        for name, value in (
            ("success_probability", self.success_probability),
            ("resource_headroom", self.resource_headroom),
            ("minimum_resource_headroom", self.minimum_resource_headroom),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        for name, value in (
            ("success_value", self.success_value),
            ("failure_learning_value", self.failure_learning_value),
            ("downstream_cost_avoided_if_failure", self.downstream_cost_avoided_if_failure),
            ("run_cost", self.run_cost),
            ("risk_exposure", self.risk_exposure),
        ):
            if value < 0.0:
                raise ValueError(f"{name} must be non-negative")

    @property
    def has_real_boundary(self) -> bool:
        return (
            not self.reversible
            or self.external_side_effects
            or (self.requires_authorization and not self.authorized)
        )


def expected_information_value(probe: FeasibilityProbe) -> dict[str, float]:
    """Return expected success value, failure-information value, and net value.

    Values are normalized utility units chosen by the caller. Failure value includes
    both what is learned from the failure and downstream work avoided because the
    infeasible path was discovered early.
    """

    probe.validate()
    failure_probability = 1.0 - probe.success_probability
    success_component = probe.success_probability * probe.success_value
    failure_component = failure_probability * (
        probe.failure_learning_value + probe.downstream_cost_avoided_if_failure
    )
    gross_value = success_component + failure_component
    net_value = gross_value - probe.run_cost - probe.risk_exposure
    return {
        "success_probability": probe.success_probability,
        "failure_probability": failure_probability,
        "success_component": success_component,
        "failure_information_component": failure_component,
        "gross_value": gross_value,
        "net_value": net_value,
    }


def decide_prerun(probe: FeasibilityProbe) -> PreRunDecision:
    """Decide whether to speculatively run a bounded feasibility process now."""

    probe.validate()
    if probe.has_real_boundary:
        return PreRunDecision.WAIT_BOUNDARY
    if probe.resource_headroom < probe.minimum_resource_headroom:
        return PreRunDecision.HOLD_RESOURCES
    if expected_information_value(probe)["net_value"] > 0.0:
        return PreRunDecision.PRE_RUN
    return PreRunDecision.SKIP_LOW_VALUE
