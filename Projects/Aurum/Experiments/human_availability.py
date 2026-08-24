"""Experimental human-availability context for Future Branch.

Human availability is a soft scheduling prior, not authority. A physical or human
boundary can stop an effect while Future Branch continues preparing success,
failure, diagnostic, recovery, and next-step branches behind it.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HumanMode(str, Enum):
    MORNING_UPDATE = "morning-update"
    DAYTIME_MACHINE_HEAVY = "daytime-machine-heavy"
    EVENING_HARDWARE = "evening-hardware"
    LATE_NIGHT_LOGIC = "late-night-logic"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class HumanAvailability:
    mode: HumanMode
    likely_near_hardware: bool
    likely_wants_summary: bool
    suitable_for_long_human_procedure: bool
    machine_preparation_bias: float
    notes: str = ""

    def validate(self) -> None:
        if not 0 <= self.machine_preparation_bias <= 1:
            raise ValueError("machine_preparation_bias must be between 0 and 1")


def default_profile_for_hour(local_hour: int) -> HumanAvailability:
    """Return a conservative inferred operating mode for an hour of day.

    Fresh explicit context overrides this prior. The current default profile reflects
    an observed rhythm: update-ready around 06:00, machine-heavy daytime preparation,
    stronger physical-hardware availability in the evening, and logic/driver/training
    work late at night.
    """
    if not 0 <= local_hour <= 23:
        raise ValueError("local_hour must be 0..23")
    if 5 <= local_hour < 9:
        return HumanAvailability(
            HumanMode.MORNING_UPDATE, False, True, False, 0.85,
            "Prepare the update before it is requested; keep physical work queued behind presence evidence.",
        )
    if 9 <= local_hour < 17:
        return HumanAvailability(
            HumanMode.DAYTIME_MACHINE_HEAVY, False, False, False, 1.0,
            "Favor autonomous builds, CI, diagnostics, simulations, evidence collection, and branch preparation.",
        )
    if 17 <= local_hour < 21:
        return HumanAvailability(
            HumanMode.EVENING_HARDWARE, True, False, True, 0.65,
            "Surface the highest-value physical action with pass/fail branches already prepared.",
        )
    if 21 <= local_hour or local_hour < 2:
        return HumanAvailability(
            HumanMode.LATE_NIGHT_LOGIC, True, False, True, 0.8,
            "Favor architecture, logic, drivers, experiments, and training concepts; keep hardware steps concise.",
        )
    return HumanAvailability(
        HumanMode.UNKNOWN, False, False, False, 0.9,
        "Do not assume human availability; continue safe machine preparation until fresh evidence arrives.",
    )


def boundary_policy(*, human_required: bool, physical_required: bool, profile: HumanAvailability) -> dict:
    """Separate effect blocking from analysis/preparation blocking."""
    profile.validate()
    real_boundary = human_required or physical_required
    return {
        "execution_blocked": bool(real_boundary),
        "future_branch_analysis_continues": True,
        "prepare_success_path": True,
        "prepare_failure_paths": True,
        "prepare_diagnostics": True,
        "prepare_recovery": True,
        "surface_human_action_now": bool(real_boundary and profile.likely_near_hardware),
        "machine_preparation_bias": profile.machine_preparation_bias,
    }
