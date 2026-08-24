"""Future Branch Reality Gap model.

The farther a candidate moves from where it was proven into the physical world,
the more uncertainty, surprise reserve, diagnostic breadth, and preparation
compute it should receive before a consequential boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class ProofLevel(IntEnum):
    CONCEPT = 0
    UNIT_TESTED = 1
    SIMULATED = 2
    VM_EMULATED = 3
    CONTROLLED_INTEGRATION = 4
    KNOWN_HARDWARE = 5
    NEW_HARDWARE = 6
    FIELD_ENVIRONMENT = 7


@dataclass(frozen=True)
class RealityTransition:
    proven_at: ProofLevel
    target: ProofLevel
    hardware_novelty: float = 0.0
    firmware_dependency: float = 0.0
    driver_dependency: float = 0.0
    external_state_dependency: float = 0.0
    prior_physical_proof: bool = False

    def validate(self) -> None:
        for name, value in (
            ("hardware_novelty", self.hardware_novelty),
            ("firmware_dependency", self.firmware_dependency),
            ("driver_dependency", self.driver_dependency),
            ("external_state_dependency", self.external_state_dependency),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")


def reality_gap_score(transition: RealityTransition) -> float:
    """Return normalized 0..1 exposure to reality-specific surprise."""
    transition.validate()
    level_gap = max(0, int(transition.target) - int(transition.proven_at)) / 7.0
    physicality = max(0.0, (int(transition.target) - int(ProofLevel.VM_EMULATED)) / 4.0)
    dependency_novelty = (
        0.30 * transition.hardware_novelty
        + 0.20 * transition.firmware_dependency
        + 0.20 * transition.driver_dependency
        + 0.15 * transition.external_state_dependency
    )
    score = 0.45 * level_gap + 0.25 * physicality + dependency_novelty
    if transition.prior_physical_proof:
        score *= 0.70
    return min(1.0, max(0.0, score))


def preparation_profile(transition: RealityTransition) -> dict:
    """Translate Reality Gap into extra Future Branch preparation effort.

    This increases analysis/preparation only. It grants no authority to perform
    physical or destructive work.
    """
    gap = reality_gap_score(transition)
    target_is_physical = transition.target >= ProofLevel.KNOWN_HARDWARE
    surprise_floor = min(0.35, 0.10 + 0.22 * gap)
    processing_multiplier = 1.0 + 1.5 * gap
    if gap >= 0.75:
        depth = "to-boundary"
    elif gap >= 0.50:
        depth = "deep"
    elif gap >= 0.25:
        depth = "moderate"
    else:
        depth = "normal"
    return {
        "reality_gap_score": round(gap, 4),
        "processing_multiplier": round(processing_multiplier, 3),
        "surprise_reserve_floor": round(surprise_floor, 3),
        "lookahead": depth,
        "broaden_failure_families": bool(gap >= 0.25),
        "require_physical_identity_checks": target_is_physical,
        "require_pass_and_fail_paths": True,
        "authority_granted": False,
    }
