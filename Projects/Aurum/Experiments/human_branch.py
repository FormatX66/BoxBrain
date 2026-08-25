"""Human-facing Future Branch adaptation primitives.

This module models short-lived intent, repeated preference evidence, identity/session
confidence, and status projection. It is deliberately advisory: inferred intent,
GUI preference, or identity likelihood never grants destructive authority or
lowers an authentication/privilege threshold.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class IntentDisposition(str, Enum):
    PRESTAGE = "prestage"
    WARM = "warm"
    EXPIRE = "expire"
    WAIT_BOUNDARY = "wait-boundary"


class PreferenceDisposition(str, Enum):
    ADAPT_REVERSIBLY = "adapt-reversibly"
    KEEP_WARM = "keep-warm"
    KEEP_CURRENT = "keep-current"


class IdentityDisposition(str, Enum):
    KEEP_PRIVILEGE = "keep-privilege"
    REDUCE_PRIVILEGE = "reduce-privilege"
    REQUIRE_AUTH = "require-auth"


@dataclass(frozen=True)
class IntentCandidate:
    name: str
    probability: float
    freshness: float
    human_value: float
    reversible_prestage: bool = False
    high_impact_boundary: bool = False

    def validate(self) -> None:
        if not self.name:
            raise ValueError("intent name required")
        for label, value in (
            ("probability", self.probability),
            ("freshness", self.freshness),
            ("human_value", self.human_value),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{label} must be between 0 and 1")

    @property
    def score(self) -> float:
        self.validate()
        return self.probability * self.freshness * (0.5 + 0.5 * self.human_value)


@dataclass(frozen=True)
class PreferenceCandidate:
    name: str
    positive_observations: int
    negative_observations: int
    familiarity: float
    rollback_available: bool

    def validate(self) -> None:
        if not self.name:
            raise ValueError("preference name required")
        if self.positive_observations < 0 or self.negative_observations < 0:
            raise ValueError("observation counts must be non-negative")
        if not 0.0 <= self.familiarity <= 1.0:
            raise ValueError("familiarity must be between 0 and 1")


@dataclass(frozen=True)
class IdentityHypothesis:
    name: str
    confidence: float
    signal_quality: float

    def validate(self) -> None:
        if not self.name:
            raise ValueError("identity hypothesis name required")
        for label, value in (("confidence", self.confidence), ("signal_quality", self.signal_quality)):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{label} must be between 0 and 1")


def rank_intents(
    candidates: Iterable[IntentCandidate],
    *,
    limit: int = 5,
    expire_freshness_below: float = 0.25,
) -> list[dict]:
    """Rank short-lived intent hypotheses without turning likelihood into authority."""
    if limit < 1:
        raise ValueError("limit must be positive")
    values = list(candidates)
    for item in values:
        item.validate()
    ordered = sorted(values, key=lambda item: (-item.score, item.name))[:limit]
    output: list[dict] = []
    for item in ordered:
        if item.freshness < expire_freshness_below:
            disposition = IntentDisposition.EXPIRE
        elif item.high_impact_boundary:
            disposition = IntentDisposition.WAIT_BOUNDARY
        elif item.reversible_prestage and item.probability >= 0.45:
            disposition = IntentDisposition.PRESTAGE
        else:
            disposition = IntentDisposition.WARM
        output.append(
            {
                "name": item.name,
                "score": round(item.score, 6),
                "probability": item.probability,
                "freshness": item.freshness,
                "disposition": disposition.value,
                "grants_authority": False,
            }
        )
    return output


def preference_decision(
    candidate: PreferenceCandidate,
    *,
    current_preference: str,
    minimum_repeated_evidence: int = 3,
) -> dict:
    """Require repeated behavior and easy rollback before adapting presentation."""
    candidate.validate()
    if minimum_repeated_evidence < 2:
        raise ValueError("minimum_repeated_evidence must be at least 2")
    net = candidate.positive_observations - candidate.negative_observations

    if candidate.name == current_preference:
        disposition = PreferenceDisposition.KEEP_CURRENT
    elif (
        candidate.positive_observations >= minimum_repeated_evidence
        and net >= 2
        and candidate.rollback_available
    ):
        disposition = PreferenceDisposition.ADAPT_REVERSIBLY
    else:
        disposition = PreferenceDisposition.KEEP_WARM

    return {
        "candidate": candidate.name,
        "current": current_preference,
        "net_evidence": net,
        "disposition": disposition.value,
        "rollback_required": disposition == PreferenceDisposition.ADAPT_REVERSIBLY,
        "single_observation_can_switch": False,
        "grants_authority": False,
    }


def identity_session_decision(
    hypotheses: Iterable[IdentityHypothesis],
    *,
    current_privilege: int,
    requested_privilege: int,
    authentication_threshold: float,
    ambiguity_margin: float = 0.12,
) -> dict:
    """Never elevate privilege from prediction; ambiguity waits or reduces privilege."""
    if current_privilege < 0 or requested_privilege < 0:
        raise ValueError("privilege levels must be non-negative")
    if not 0.0 <= authentication_threshold <= 1.0:
        raise ValueError("authentication_threshold must be between 0 and 1")
    if not 0.0 <= ambiguity_margin <= 1.0:
        raise ValueError("ambiguity_margin must be between 0 and 1")

    values = list(hypotheses)
    for item in values:
        item.validate()
    ordered = sorted(
        values,
        key=lambda item: (-(item.confidence * item.signal_quality), item.name),
    )
    top = ordered[0] if ordered else None
    runner = ordered[1] if len(ordered) > 1 else None
    top_score = 0.0 if top is None else top.confidence * top.signal_quality
    runner_score = 0.0 if runner is None else runner.confidence * runner.signal_quality
    ambiguous = top is None or (top_score - runner_score) < ambiguity_margin
    sufficient = top_score >= authentication_threshold and not ambiguous

    if requested_privilege > current_privilege:
        disposition = IdentityDisposition.REQUIRE_AUTH
        effective_privilege = current_privilege
    elif not sufficient:
        disposition = IdentityDisposition.REDUCE_PRIVILEGE
        effective_privilege = min(current_privilege, requested_privilege)
    else:
        disposition = IdentityDisposition.KEEP_PRIVILEGE
        effective_privilege = min(current_privilege, requested_privilege)

    return {
        "top_identity": None if top is None else top.name,
        "top_score": round(top_score, 6),
        "runner_up_score": round(runner_score, 6),
        "ambiguous": ambiguous,
        "threshold_met": sufficient,
        "disposition": disposition.value,
        "current_privilege": current_privilege,
        "requested_privilege": requested_privilege,
        "effective_privilege": effective_privilege,
        "prediction_can_raise_privilege": False,
        "authentication_threshold_lowered": False,
    }


def status_projection(
    *,
    verified_state: str,
    likely_next: Iterable[tuple[str, float]],
    lkg: str | None,
    blockers: Iterable[str] = (),
) -> dict:
    """Keep verified truth visibly separate from likely futures."""
    futures = sorted(
        ((str(name), float(probability)) for name, probability in likely_next),
        key=lambda pair: (-pair[1], pair[0]),
    )
    for _, probability in futures:
        if not 0.0 <= probability <= 1.0:
            raise ValueError("future probabilities must be between 0 and 1")
    return {
        "schema": "aurum-human-future-branch-status-v1",
        "verified": {"state": verified_state, "lkg": lkg},
        "likely_next": [
            {"state": name, "probability": probability, "verified": False}
            for name, probability in futures
        ],
        "blockers": list(blockers),
        "speculation_rendered_as_verified": False,
        "authority_from_projection": False,
    }
