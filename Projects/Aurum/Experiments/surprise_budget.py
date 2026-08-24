"""Future Branch surprise-budget experiment.

Aurum should not assign all probability mass to named branches. Repeated
unpredicted failures increase a reserved unknown-unknown branch and reduce
confidence in the current leading prediction until new evidence closes the gap.
"""
from __future__ import annotations

from enum import Enum


class FailureFamily(str, Enum):
    TARGET_IDENTITY = "target-identity"
    ORCHESTRATION_TRIGGER = "orchestration-trigger"
    ENVIRONMENT_SEMANTICS = "environment-semantics"
    RUNNER_AVAILABILITY = "runner-availability"
    DEVICE_READINESS = "device-readiness"
    BOOT_PRESENTATION = "boot-presentation"
    UNKNOWN = "unknown-unknown"


CORE_FAILURE_FAMILIES = tuple(f for f in FailureFamily if f is not FailureFamily.UNKNOWN)


def surprise_reserve(
    *,
    unpredicted_failures: int,
    total_failures: int,
    base_reserve: float = 0.10,
    cap: float = 0.35,
) -> float:
    """Return probability mass reserved for causes outside named branches."""
    if unpredicted_failures < 0 or total_failures < 0:
        raise ValueError("failure counts must be non-negative")
    if unpredicted_failures > total_failures:
        raise ValueError("unpredicted_failures cannot exceed total_failures")
    if not 0 <= base_reserve <= cap <= 1:
        raise ValueError("invalid reserve bounds")
    if total_failures == 0:
        return base_reserve
    miss_rate = unpredicted_failures / total_failures
    return min(cap, base_reserve + 0.25 * miss_rate)


def calibrated_leader_confidence(*, leader_probability: float, reserve: float) -> float:
    """Discount named-branch confidence by the current surprise reserve."""
    if not 0 <= leader_probability <= 1 or not 0 <= reserve <= 1:
        raise ValueError("probabilities must be between 0 and 1")
    return leader_probability * (1 - reserve)


def failure_family_coverage(modeled: set[FailureFamily]) -> dict:
    """Expose broad failure-family gaps before a consequential boundary."""
    missing = [family.value for family in CORE_FAILURE_FAMILIES if family not in modeled]
    return {
        "modeled": sorted(f.value for f in modeled),
        "missing": missing,
        "unknown_branch_required": True,
        "coverage_complete": not missing,
    }


def boundary_expansion_required(*, reserve: float, missing_families: int) -> bool:
    """Keep expanding diagnostics before a boundary when uncertainty is material."""
    if not 0 <= reserve <= 1 or missing_families < 0:
        raise ValueError("invalid inputs")
    return reserve >= 0.15 or missing_families > 0
