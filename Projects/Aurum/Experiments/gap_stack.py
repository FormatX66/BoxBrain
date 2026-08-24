"""Stacked-gap model for Future Branch preparation.

Reality Gap is one source of uncertainty. This module models other predictable
mismatches between what Aurum thinks it knows and what execution actually depends
on. Multiple moderate gaps can combine into a high-risk transition even when no
single gap is extreme.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import prod


class GapKind(str, Enum):
    REALITY = "reality-gap"
    CONTEXT = "context-gap"
    TOPOLOGY = "topology-gap"
    CAPABILITY = "capability-gap"
    RUNTIME = "runtime-gap"
    EVIDENCE = "evidence-gap"
    FRESHNESS = "freshness-gap"
    CONCURRENCY = "concurrency-gap"
    RESOURCE = "resource-gap"
    RECOVERY_PROOF = "recovery-proof-gap"
    HUMAN_INTERPRETATION = "human-interpretation-gap"


@dataclass(frozen=True)
class GapExposure:
    kind: GapKind
    severity: float
    evidence_quality: float = 0.5
    mitigated: bool = False

    def validate(self) -> None:
        for name, value in (("severity", self.severity), ("evidence_quality", self.evidence_quality)):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")

    @property
    def effective(self) -> float:
        self.validate()
        evidence_discount = 0.55 + 0.45 * (1.0 - self.evidence_quality)
        mitigation_discount = 0.45 if self.mitigated else 1.0
        return min(1.0, self.severity * evidence_discount * mitigation_discount)


def stacked_gap_score(gaps: list[GapExposure]) -> float:
    """Combine independent-ish gap exposures without simply summing past 1.0."""
    if not gaps:
        return 0.0
    effective = [g.effective for g in gaps]
    return 1.0 - prod(1.0 - value for value in effective)


def gap_preparation_profile(gaps: list[GapExposure]) -> dict:
    """Translate stacked uncertainty into preparation behavior only."""
    score = stacked_gap_score(gaps)
    active = sorted(g.kind.value for g in gaps if g.effective >= 0.15)
    if score >= 0.80:
        lookahead = "to-boundary"
    elif score >= 0.60:
        lookahead = "deep"
    elif score >= 0.35:
        lookahead = "moderate"
    else:
        lookahead = "normal"
    return {
        "stacked_gap_score": round(score, 4),
        "processing_multiplier": round(1.0 + 2.0 * score, 3),
        "lookahead": lookahead,
        "active_gaps": active,
        "cross_check_context_and_topology": any(g.kind in {GapKind.CONTEXT, GapKind.TOPOLOGY} and g.effective >= 0.15 for g in gaps),
        "require_capability_probe": any(g.kind == GapKind.CAPABILITY and g.effective >= 0.15 for g in gaps),
        "require_runtime_probe": any(g.kind == GapKind.RUNTIME and g.effective >= 0.15 for g in gaps),
        "require_independent_verification": any(g.kind in {GapKind.EVIDENCE, GapKind.RECOVERY_PROOF} and g.effective >= 0.15 for g in gaps),
        "revalidate_before_effect": any(g.kind in {GapKind.FRESHNESS, GapKind.CONCURRENCY} and g.effective >= 0.15 for g in gaps),
        "authority_granted": False,
    }
