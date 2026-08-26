"""Fail-closed contract for the Pi3 kernel-canary out-of-band recovery gate.

This module does not actuate hardware.  It evaluates whether collected evidence is
strong enough to say that a kernel canary has an *independent* automatic recovery
path.  A local timer, SSH session, same-kernel watchdog, or rollback image alone
is useful evidence but is not out-of-band recovery because all can disappear if
the target kernel wedges.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class WatchdogState(str, Enum):
    PROVEN = "out-of-band-watchdog-proven"
    HELD_IDENTITY = "held-controller-or-target-identity-unproven"
    HELD_OBSERVER = "held-independent-observer-unproven"
    HELD_ACTUATOR = "held-independent-recovery-actuator-unproven"
    HELD_RECOVERY = "held-recovery-cycle-unproven"
    HELD_LKG = "held-lkg-restoration-unproven"


@dataclass(frozen=True)
class WatchdogEvidence:
    """Evidence required before a Pi3 kernel mutation can rely on OOB recovery.

    The observer and actuator must both remain usable when the target OS/kernel is
    unavailable.  Examples of acceptable actuators include independently
    controlled power plus a proven bootable LKG medium, or another physically
    independent mechanism with equivalent recovery capability.
    """

    pinned_target_identity: bool
    independent_controller_identity: bool
    observer_independent_of_target_kernel: bool
    recovery_actuator_independent_of_target_kernel: bool
    automatic_failure_detection_proven: bool
    automatic_recovery_actuation_proven: bool
    post_recovery_target_identity_proven: bool
    lkg_restored_and_healthy_proven: bool
    local_target_timer_only: bool = False
    network_only_actuation: bool = False
    mutation_authority_granted: bool = False


@dataclass(frozen=True)
class WatchdogDecision:
    state: WatchdogState
    watchdog_proven: bool
    mutation_authority_granted: bool
    next_gate: str


def evaluate_watchdog(evidence: WatchdogEvidence) -> WatchdogDecision:
    """Evaluate OOB recovery evidence without ever granting mutation authority."""

    # Authority is deliberately not inherited from evidence.  This evaluator can
    # establish a prerequisite only; a separate fresh mutation gate is required.
    authority = False

    if not (evidence.pinned_target_identity and evidence.independent_controller_identity):
        return WatchdogDecision(
            WatchdogState.HELD_IDENTITY,
            False,
            authority,
            "prove-pinned-target-and-independent-controller-identity",
        )

    if evidence.local_target_timer_only or not evidence.observer_independent_of_target_kernel:
        return WatchdogDecision(
            WatchdogState.HELD_OBSERVER,
            False,
            authority,
            "prove-failure-observation-independent-of-target-kernel",
        )

    # SSH/network reachability alone cannot recover a kernel that has wedged the
    # network stack.  The actuator must survive loss of target-kernel service.
    if evidence.network_only_actuation or not evidence.recovery_actuator_independent_of_target_kernel:
        return WatchdogDecision(
            WatchdogState.HELD_ACTUATOR,
            False,
            authority,
            "prove-independent-recovery-actuator",
        )

    if not (evidence.automatic_failure_detection_proven and evidence.automatic_recovery_actuation_proven):
        return WatchdogDecision(
            WatchdogState.HELD_RECOVERY,
            False,
            authority,
            "exercise-automatic-failure-detection-and-recovery-cycle",
        )

    if not (evidence.post_recovery_target_identity_proven and evidence.lkg_restored_and_healthy_proven):
        return WatchdogDecision(
            WatchdogState.HELD_LKG,
            False,
            authority,
            "prove-post-recovery-identity-and-lkg-health",
        )

    return WatchdogDecision(
        WatchdogState.PROVEN,
        True,
        authority,
        "fresh-explicit-kernel-mutation-authority",
    )
