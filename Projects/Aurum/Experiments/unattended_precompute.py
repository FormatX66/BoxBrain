"""Unattended precompute planning for Future Branch.

When the human is unavailable but a likely future physical action is known, Aurum
should spend safe/reversible compute reducing uncertainty until it reaches a true
physical or authority boundary. The result is a compact physical-session packet.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PendingPhysicalAction:
    name: str
    probability: float
    hours_until_likely_human_action: float
    reality_gap: float
    stacked_gap: float
    reversible_compute_available: bool = True

    def validate(self) -> None:
        if not self.name:
            raise ValueError("name required")
        for field, value in (
            ("probability", self.probability),
            ("reality_gap", self.reality_gap),
            ("stacked_gap", self.stacked_gap),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field} must be between 0 and 1")
        if self.hours_until_likely_human_action < 0:
            raise ValueError("hours_until_likely_human_action must be non-negative")


def unattended_value(action: PendingPhysicalAction) -> float:
    """Estimate how aggressively to precompute before the human returns."""
    action.validate()
    if not action.reversible_compute_available:
        return 0.0
    uncertainty = max(action.reality_gap, action.stacked_gap)
    lead_time = min(1.0, action.hours_until_likely_human_action / 8.0)
    return action.probability * (0.45 + 0.55 * uncertainty) * (0.5 + 0.5 * lead_time)


def physical_session_packet(action: PendingPhysicalAction) -> dict:
    """Describe the preparation that should be ready before a likely physical step."""
    value = unattended_value(action)
    aggressive = value >= 0.45
    return {
        "action": action.name,
        "unattended_precompute_value": round(value, 4),
        "prepare_latest_verified_artifact": True,
        "prepare_target_identity_contract": True,
        "prepare_runner_and_service_probe": True,
        "prepare_runtime_semantics_probe": True,
        "prepare_dry_run": True,
        "prepare_success_path": True,
        "prepare_failure_tree": True,
        "prepare_recovery_path": True,
        "prepare_evidence_contract": True,
        "simulate_failure_families": aggressive,
        "test_alternate_execution_routes": aggressive,
        "lookahead_to_next_boundary": aggressive,
        "physical_effect_allowed": False,
        "authority_granted": False,
    }
