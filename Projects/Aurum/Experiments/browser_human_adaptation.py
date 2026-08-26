"""Browser-facing Future Branch preference adaptation contract.

This is an experimental, presentation-only consumer of the human-facing Future
Branch primitives. It may adapt a local browser view after repeated evidence, but
it cannot mutate server state, infer identity, lower authentication, grant
privilege, or authorize external/destructive actions.
"""
from __future__ import annotations

from dataclasses import dataclass

from human_branch import PreferenceCandidate, preference_decision


@dataclass(frozen=True)
class BrowserPreferenceEvidence:
    name: str
    positive_sessions: int
    negative_sessions: int
    age_days: float
    rollback_available: bool = True

    def validate(self) -> None:
        if not self.name:
            raise ValueError("preference name required")
        if self.positive_sessions < 0 or self.negative_sessions < 0:
            raise ValueError("session counts must be non-negative")
        if self.age_days < 0:
            raise ValueError("age_days must be non-negative")


def browser_preference_decision(
    evidence: BrowserPreferenceEvidence,
    *,
    current_preference: str,
    stale_after_days: float = 30.0,
    minimum_repeated_evidence: int = 3,
) -> dict:
    """Return a fail-closed, reversible local-browser adaptation decision.

    Evidence is intentionally counted by distinct browser sessions so repeated
    clicks in one session cannot manufacture confidence. Stale evidence expires.
    The resulting recommendation is presentation-only and local-only.
    """
    evidence.validate()
    if stale_after_days <= 0:
        raise ValueError("stale_after_days must be positive")
    if minimum_repeated_evidence < 2:
        raise ValueError("minimum_repeated_evidence must be at least 2")

    if evidence.age_days > stale_after_days:
        result = {
            "candidate": evidence.name,
            "current": current_preference,
            "net_evidence": 0,
            "disposition": "keep-current",
            "rollback_required": False,
            "single_observation_can_switch": False,
            "grants_authority": False,
            "expired": True,
        }
    else:
        result = preference_decision(
            PreferenceCandidate(
                name=evidence.name,
                positive_observations=evidence.positive_sessions,
                negative_observations=evidence.negative_sessions,
                familiarity=1.0,
                rollback_available=evidence.rollback_available,
            ),
            current_preference=current_preference,
            minimum_repeated_evidence=minimum_repeated_evidence,
        )
        result["expired"] = False

    return {
        **result,
        "schema": "aurum-browser-human-adaptation-v1",
        "evidence_unit": "distinct-browser-session",
        "storage_scope": "local-browser-only",
        "presentation_only": True,
        "reset_available": True,
        "server_state_mutation_allowed": False,
        "external_action_allowed": False,
        "destructive_action_allowed": False,
        "identity_inference_allowed": False,
        "authentication_threshold_change_allowed": False,
        "privilege_change_allowed": False,
    }
