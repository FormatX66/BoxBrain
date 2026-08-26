"""Future Branch operational workflow planning.

This module turns CI/build, website/deployment, and external-content alternatives
into a ranked preparation field. It is deliberately side-effect free: cached
validation, rollback preparation, and reversible drafts may be prepared, but
deployment, publishing, messaging, or other external effects remain behind their
normal authority boundary. Unchanged failed retries and trust broadening are
quarantined instead of becoming retry storms.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class WorkflowDomain(str, Enum):
    CI_BUILD = "ci-build"
    WEBSITE_DEPLOYMENT = "website-deployment"
    EXTERNAL_CONTENT = "external-content"


class WorkflowDisposition(str, Enum):
    PREPARE = "prepare"
    WARM = "warm"
    WAIT = "wait"
    HOLD = "hold"
    QUARANTINE = "quarantine"
    WAIT_BOUNDARY = "wait-boundary"


@dataclass(frozen=True)
class WorkflowCandidate:
    name: str
    domain: WorkflowDomain
    probability: float
    impact: float
    human_time_saved: float
    preparation_leverage: float
    cost: float
    evidence_freshness: float = 1.0
    read_only: bool = False
    reversible: bool = False
    external_side_effect: bool = False
    authorization_required: bool = False
    rollback_prepared: bool = False
    preserves_verified_state: bool = True
    unchanged_retry: bool = False
    retry_after_seconds: int = 0
    trust_broadening: bool = False
    alternate_authorized_route: bool = False

    def validate(self) -> None:
        if not self.name:
            raise ValueError("candidate name required")
        for label, value in (
            ("probability", self.probability),
            ("impact", self.impact),
            ("evidence_freshness", self.evidence_freshness),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{label} must be between 0 and 1")
        for label, value in (
            ("human_time_saved", self.human_time_saved),
            ("preparation_leverage", self.preparation_leverage),
            ("cost", self.cost),
        ):
            if value < 0:
                raise ValueError(f"{label} must be non-negative")
        if self.retry_after_seconds < 0:
            raise ValueError("retry_after_seconds must be non-negative")


def candidate_score(candidate: WorkflowCandidate) -> float:
    """Rank expected long-horizon utility per cost without rewarding stale loops."""
    candidate.validate()
    if candidate.unchanged_retry or candidate.trust_broadening:
        return float("-inf")
    time_value = max(candidate.human_time_saved, 0.01)
    leverage = max(candidate.preparation_leverage, 0.01)
    return (
        candidate.probability
        * candidate.impact
        * time_value
        * leverage
        * candidate.evidence_freshness
        / max(candidate.cost, 0.01)
    )


def candidate_disposition(candidate: WorkflowCandidate) -> tuple[WorkflowDisposition, str]:
    """Select only a preparation state; never authorize an external effect."""
    candidate.validate()
    if candidate.unchanged_retry:
        return WorkflowDisposition.QUARANTINE, "unchanged-failed-retry"
    if candidate.trust_broadening:
        return WorkflowDisposition.QUARANTINE, "trust-or-target-broadening"
    if candidate.retry_after_seconds > 0:
        return WorkflowDisposition.WAIT, "explicit-retry-after"
    if not candidate.preserves_verified_state:
        return WorkflowDisposition.HOLD, "would-displace-verified-state"
    if candidate.domain == WorkflowDomain.WEBSITE_DEPLOYMENT and not candidate.read_only:
        if not candidate.rollback_prepared:
            return WorkflowDisposition.HOLD, "rollback-not-prepared"
    if candidate.external_side_effect or candidate.authorization_required:
        return WorkflowDisposition.WAIT_BOUNDARY, "external-authority-boundary"
    if candidate.read_only or candidate.reversible:
        return WorkflowDisposition.PREPARE, "safe-preparation"
    return WorkflowDisposition.WARM, "plausible-nonexecuting-alternative"


def operational_plan(
    candidates: Iterable[WorkflowCandidate],
    *,
    verified_state: str,
    limit: int = 8,
) -> dict:
    """Return a ranked cross-workflow Future Branch field with zero authority."""
    if limit < 1:
        raise ValueError("limit must be positive")
    values = list(candidates)
    for item in values:
        item.validate()
    ordered = sorted(values, key=lambda item: (-candidate_score(item), item.name))[:limit]
    branches = []
    for item in ordered:
        disposition, reason = candidate_disposition(item)
        score = candidate_score(item)
        branches.append(
            {
                "name": item.name,
                "domain": item.domain.value,
                "probability": item.probability,
                "score": None if score == float("-inf") else round(score, 6),
                "disposition": disposition.value,
                "reason": reason,
                "read_only": item.read_only,
                "reversible": item.reversible,
                "rollback_prepared": item.rollback_prepared,
                "alternate_authorized_route": item.alternate_authorized_route,
                "grants_authority": False,
            }
        )
    return {
        "schema": "aurum-future-branch-operational-plan-v1",
        "verified_state": verified_state,
        "branches": branches,
        "verified_state_preserved": True,
        "external_action_allowed": False,
        "publish_allowed": False,
        "deployment_promotion_allowed": False,
        "trust_broadening_allowed": False,
        "unchanged_retry_allowed": False,
    }
