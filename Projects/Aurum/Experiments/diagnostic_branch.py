"""Future Branch diagnostic/operational hypothesis ranking.

This module is intentionally side-effect free. It turns fresh evidence into a small
ranked field of competing causes and cheap evidence-producing next probes. It
never grants authority, broadens identity/trust, or turns an alternate route into
permission to mutate a target.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class DiagnosticDomain(str, Enum):
    POWER = "power"
    CABLE = "cable"
    STORAGE = "storage"
    TRANSPORT = "transport"
    DRIVER = "driver"
    FIRMWARE = "firmware"
    DNS = "dns"
    TLS = "tls"
    ROUTING = "routing"
    SERVICE = "service"
    HARDWARE = "hardware"
    CONFIGURATION = "configuration"
    DEPENDENCY = "dependency"
    QUOTA = "quota"
    AUTHORIZATION = "authorization"
    ENVIRONMENT = "environment"
    TEST_REGRESSION = "test-regression"
    DEPLOYMENT_DRIFT = "deployment-drift"


class ProbeDisposition(str, Enum):
    PROBE = "probe"
    HOLD = "hold"
    QUARANTINE = "quarantine"
    WAIT = "wait"


@dataclass(frozen=True)
class DiagnosticHypothesis:
    name: str
    domain: DiagnosticDomain
    prior_probability: float
    impact: float
    evidence_support: float = 0.0
    evidence_conflict: float = 0.0
    freshness: float = 1.0
    stable_failed_attempts: int = 0

    def validate(self) -> None:
        if not self.name:
            raise ValueError("hypothesis name required")
        for label, value in (
            ("prior_probability", self.prior_probability),
            ("impact", self.impact),
            ("evidence_support", self.evidence_support),
            ("evidence_conflict", self.evidence_conflict),
            ("freshness", self.freshness),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{label} must be between 0 and 1")
        if self.stable_failed_attempts < 0:
            raise ValueError("stable_failed_attempts must be non-negative")

    @property
    def probability(self) -> float:
        """Evidence-adjusted comparative probability, bounded to [0, 1]."""
        self.validate()
        positive = self.prior_probability + (1.0 - self.prior_probability) * 0.70 * self.evidence_support
        negative = positive * 0.85 * self.evidence_conflict
        return max(0.0, min(1.0, (positive - negative) * (0.65 + 0.35 * self.freshness)))


@dataclass(frozen=True)
class DiagnosticProbe:
    name: str
    domains: tuple[DiagnosticDomain, ...]
    read_only: bool
    evidence_gain: float
    human_time_saved: float
    compute_cost: float
    network_cost: float = 0.0
    privacy_cost: float = 0.0
    risk: float = 0.0
    available: bool = True
    unchanged_retry: bool = False
    identity_broadening: bool = False
    authority_required: bool = False

    def validate(self) -> None:
        if not self.name:
            raise ValueError("probe name required")
        if not self.domains:
            raise ValueError("probe must cover at least one domain")
        for label, value in (
            ("evidence_gain", self.evidence_gain),
            ("human_time_saved", self.human_time_saved),
            ("compute_cost", self.compute_cost),
            ("network_cost", self.network_cost),
            ("privacy_cost", self.privacy_cost),
            ("risk", self.risk),
        ):
            if value < 0:
                raise ValueError(f"{label} must be non-negative")


def hypothesis_score(item: DiagnosticHypothesis) -> float:
    item.validate()
    repeat_discount = 1.0 / (1.0 + 0.8 * item.stable_failed_attempts)
    return item.probability * (0.5 + 0.5 * item.impact) * repeat_discount


def rank_hypotheses(
    hypotheses: Iterable[DiagnosticHypothesis],
    *,
    limit: int = 6,
    quarantine_below: float = 0.035,
) -> list[dict]:
    """Rank a small competing cause field without preserving disproven loops."""
    if limit < 1:
        raise ValueError("limit must be positive")
    values = list(hypotheses)
    for item in values:
        item.validate()
    ranked = sorted(values, key=lambda item: (-hypothesis_score(item), item.name))
    result: list[dict] = []
    for item in ranked[:limit]:
        score = hypothesis_score(item)
        if score < quarantine_below or (item.evidence_conflict >= 0.85 and item.evidence_support <= 0.15):
            disposition = ProbeDisposition.QUARANTINE.value
        elif item.freshness < 0.25:
            disposition = ProbeDisposition.WAIT.value
        else:
            disposition = ProbeDisposition.PROBE.value
        result.append(
            {
                "name": item.name,
                "domain": item.domain.value,
                "probability": round(item.probability, 6),
                "score": round(score, 6),
                "disposition": disposition,
                "stable_failed_attempts": item.stable_failed_attempts,
            }
        )
    return result


def probe_score(
    probe: DiagnosticProbe,
    hypotheses: Iterable[DiagnosticHypothesis],
) -> float:
    """Expected information/time value per cost for a side-effect-free probe."""
    probe.validate()
    values = list(hypotheses)
    for item in values:
        item.validate()
    if not probe.available:
        return float("-inf")
    if probe.unchanged_retry:
        return float("-inf")
    if probe.identity_broadening:
        return float("-inf")

    covered_domains = set(probe.domains)
    covered = sum(
        hypothesis_score(item)
        for item in values
        if item.domain in covered_domains
    )
    benefit = covered * probe.evidence_gain * (1.0 + probe.human_time_saved)
    cost = (
        0.05
        + probe.compute_cost
        + probe.network_cost
        + probe.privacy_cost
        + 2.0 * probe.risk
        + (1.0 if probe.authority_required else 0.0)
        + (0.5 if not probe.read_only else 0.0)
    )
    return benefit / cost


def rank_probes(
    probes: Iterable[DiagnosticProbe],
    hypotheses: Iterable[DiagnosticHypothesis],
    *,
    limit: int = 5,
) -> list[dict]:
    """Prefer cheap read-only evidence and reject retry/trust-expansion loops."""
    if limit < 1:
        raise ValueError("limit must be positive")
    probe_values = list(probes)
    hypothesis_values = list(hypotheses)
    for probe in probe_values:
        probe.validate()
    for item in hypothesis_values:
        item.validate()

    ordered = sorted(
        probe_values,
        key=lambda probe: (-probe_score(probe, hypothesis_values), probe.name),
    )
    output: list[dict] = []
    for probe in ordered[:limit]:
        score = probe_score(probe, hypothesis_values)
        if not probe.available:
            disposition = ProbeDisposition.WAIT.value
            reason = "unavailable"
        elif probe.unchanged_retry:
            disposition = ProbeDisposition.QUARANTINE.value
            reason = "unchanged-retry"
        elif probe.identity_broadening:
            disposition = ProbeDisposition.QUARANTINE.value
            reason = "identity-trust-broadening"
        elif probe.authority_required or not probe.read_only:
            disposition = ProbeDisposition.HOLD.value
            reason = "authority-or-side-effect-boundary"
        else:
            disposition = ProbeDisposition.PROBE.value
            reason = "read-only-evidence"
        output.append(
            {
                "name": probe.name,
                "score": None if score == float("-inf") else round(score, 6),
                "disposition": disposition,
                "reason": reason,
                "read_only": probe.read_only,
                "authority_required": probe.authority_required,
            }
        )
    return output


def diagnostic_plan(
    hypotheses: Iterable[DiagnosticHypothesis],
    probes: Iterable[DiagnosticProbe],
    *,
    hypothesis_limit: int = 6,
    probe_limit: int = 5,
) -> dict:
    """Return a diagnostic Future Branch field with explicit zero authority."""
    hypothesis_values = list(hypotheses)
    probe_values = list(probes)
    ranked_hypotheses = rank_hypotheses(hypothesis_values, limit=hypothesis_limit)
    ranked_probes = rank_probes(probe_values, hypothesis_values, limit=probe_limit)
    return {
        "schema": "aurum-future-branch-diagnostic-plan-v1",
        "hypotheses": ranked_hypotheses,
        "probes": ranked_probes,
        "external_action_allowed": False,
        "identity_trust_broadening_allowed": False,
        "destructive_authority": False,
        "retry_unchanged_failure_allowed": False,
    }
