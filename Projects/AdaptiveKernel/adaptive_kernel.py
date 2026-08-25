"""Adaptive Kernel generation-0 prototype.

This module's generation-0 layer produces *plans only*. The bounded generation-1
simulator lives in ``runtime.py``. Neither layer binds drivers, writes firmware,
changes boot state, or performs privileged hardware operations.

Future Branch integration emits auditable candidate proposals and a bounded
canary decision field. It never mutates the proven implementation itself: the
current proven state, rollback, and gather-more-evidence remain explicit competing
branches, and a candidate can become promotion-eligible only after independent
boot/resume/hardware/performance/regression evidence is positive and a separate
Guardian approval is present.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Mapping


@dataclass(frozen=True)
class CapabilityRule:
    name: str
    requires: tuple[str, ...]
    provides: tuple[str, ...]
    risk: str = "low"


@dataclass(frozen=True)
class Candidate:
    rule: CapabilityRule
    matched: tuple[str, ...]
    missing: tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class KernelPlan:
    selected: tuple[Candidate, ...]
    rejected: tuple[Candidate, ...]


@dataclass(frozen=True)
class CanaryEvidence:
    """Independent canary dimensions used before a kernel/driver promotion."""

    boot: bool | None = None
    resume: bool | None = None
    hardware: bool | None = None
    performance: bool | None = None
    regression: bool | None = None

    def as_mapping(self) -> dict[str, bool | None]:
        return {
            "boot": self.boot,
            "resume": self.resume,
            "hardware": self.hardware,
            "performance": self.performance,
            "regression": self.regression,
        }

    @property
    def complete(self) -> bool:
        return all(value is not None for value in self.as_mapping().values())

    @property
    def all_positive(self) -> bool:
        return self.complete and all(bool(value) for value in self.as_mapping().values())

    @property
    def strong_regression(self) -> bool:
        return self.regression is False


_RISK_SCORE = {"low": 0.10, "medium": 0.45, "high": 0.85}


def evaluate(rule: CapabilityRule, facts: Mapping[str, bool]) -> Candidate:
    matched = tuple(key for key in rule.requires if facts.get(key, False))
    missing = tuple(key for key in rule.requires if not facts.get(key, False))
    confidence = 1.0 if not rule.requires else len(matched) / len(rule.requires)
    return Candidate(rule, matched, missing, confidence)


def plan(
    facts: Mapping[str, bool],
    rules: Iterable[CapabilityRule],
    *,
    threshold: float = 1.0,
) -> KernelPlan:
    """Build a reversible phenotype proposal from observed facts."""
    selected: list[Candidate] = []
    rejected: list[Candidate] = []
    for rule in rules:
        candidate = evaluate(rule, facts)
        if candidate.confidence >= threshold and rule.risk == "low":
            selected.append(candidate)
        else:
            rejected.append(candidate)
    return KernelPlan(tuple(selected), tuple(rejected))


def _safe_branch_id(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-.")
    if not slug:
        raise ValueError("capability rule name must contain an auditable identifier")
    return f"kernel-{slug}"


def future_branch_proposals(
    facts: Mapping[str, bool],
    rules: Iterable[CapabilityRule],
    *,
    rollback_target: str = "current-proven-kernel",
) -> tuple[dict, ...]:
    """Emit safety-evaluator-ready Future Branch candidate proposals.

    The output intentionally mirrors the shared Future Branch contract but does
    not choose a winner. Every observed requirement becomes an evidence record;
    missing requirements are explicit contradictory evidence. Medium/high-risk
    candidates require authorization even when their evidence is otherwise strong.
    """

    proposals: list[dict] = []
    for rule in rules:
        if rule.risk not in _RISK_SCORE:
            raise ValueError(f"unknown kernel risk class: {rule.risk!r}")
        candidate = evaluate(rule, facts)
        evidence = [
            {
                "ref": f"fact.{name}",
                "weight": 1.0,
                "quality": 1.0,
                "supports": name in candidate.matched,
            }
            for name in rule.requires
        ]
        proposed_state = "+".join(rule.provides) if rule.provides else rule.name
        proposals.append(
            {
                "branch_id": _safe_branch_id(rule.name),
                "proposed_state": f"kernel:{proposed_state}",
                "confidence": candidate.confidence,
                "risk": _RISK_SCORE[rule.risk],
                "cost": 0.20,
                "reversibility": "full",
                "evidence": evidence,
                "status": "warm",
                "requires_authorization": rule.risk != "low",
                "authorized": False,
                "rollback_target": rollback_target,
                "is_last_known_good": False,
            }
        )
    return tuple(proposals)


def kernel_canary_branch_field(
    proposals: Iterable[dict],
    evidence_by_branch: Mapping[str, CanaryEvidence],
    *,
    proven_state: str = "current-proven-kernel",
    guardian_approved_branches: Iterable[str] = (),
) -> dict:
    """Create the bounded Future Branch field for kernel/driver canaries.

    This is still proposal/decision evidence only. ``promotion_performed`` is
    always false. A Guardian approval can make a fully verified candidate
    *promotion eligible*, but this function cannot replace the proven state.

    Regression evidence is a hard veto: ``regression=False`` rejects the
    candidate regardless of positive boot/resume/hardware/performance evidence.
    Missing evidence leaves the candidate warm and keeps gather-more-evidence
    explicit.
    """

    guardian_approved = set(guardian_approved_branches)
    candidate_branches: list[dict] = []
    for raw in proposals:
        proposal = dict(raw)
        branch_id = str(proposal["branch_id"])
        canary = evidence_by_branch.get(branch_id, CanaryEvidence())
        dimensions = canary.as_mapping()
        independent = [
            {
                "ref": f"canary.{branch_id}.{name}",
                "dimension": name,
                "supports": value,
                "observed": value is not None,
                "quality": 1.0,
                "weight": 1.0,
            }
            for name, value in dimensions.items()
        ]
        proposal["evidence"] = list(proposal.get("evidence", ())) + independent
        proposal["canary_evidence"] = dimensions
        proposal["guardian_approved"] = branch_id in guardian_approved
        proposal["promotion_eligible"] = False

        if canary.strong_regression:
            proposal["status"] = "rejected"
            proposal["hold_reason"] = "strong-regression-evidence"
        elif not canary.complete:
            proposal["status"] = "warm"
            proposal["hold_reason"] = "gather-independent-canary-evidence"
        elif not canary.all_positive:
            proposal["status"] = "rejected"
            proposal["hold_reason"] = "negative-canary-evidence"
        elif branch_id not in guardian_approved:
            proposal["status"] = "verified"
            proposal["hold_reason"] = "guardian-approval-required"
        else:
            proposal["status"] = "verified"
            proposal["promotion_eligible"] = True
            proposal["hold_reason"] = None
        candidate_branches.append(proposal)

    field = [
        {
            "branch_id": "kernel-proven-lkg",
            "proposed_state": proven_state,
            "confidence": 1.0,
            "risk": 0.0,
            "cost": 0.0,
            "reversibility": "full",
            "evidence": [{"ref": "kernel.current-proven-state", "supports": True, "quality": 1.0, "weight": 1.0}],
            "status": "verified",
            "requires_authorization": False,
            "authorized": True,
            "rollback_target": None,
            "is_last_known_good": True,
            "promotion_eligible": False,
        },
        *candidate_branches,
        {
            "branch_id": "kernel-rollback",
            "proposed_state": proven_state,
            "confidence": 0.98,
            "risk": 0.02,
            "cost": 0.05,
            "reversibility": "full",
            "evidence": [{"ref": "kernel.rollback-target", "supports": True, "quality": 1.0, "weight": 1.0}],
            "status": "warm",
            "requires_authorization": False,
            "authorized": True,
            "rollback_target": proven_state,
            "is_last_known_good": False,
            "promotion_eligible": False,
        },
        {
            "branch_id": "kernel-gather-evidence",
            "proposed_state": "gather-independent-kernel-canary-evidence",
            "confidence": 0.90,
            "risk": 0.0,
            "cost": 0.10,
            "reversibility": "full",
            "evidence": [],
            "status": "warm",
            "requires_authorization": False,
            "authorized": True,
            "rollback_target": proven_state,
            "is_last_known_good": False,
            "promotion_eligible": False,
        },
    ]
    return {
        "schema": "aurum-adaptive-kernel-future-branch-canary-v1",
        "decision_authority": "StateGuardian",
        "promotion_performed": False,
        "proven_state": proven_state,
        "branches": field,
        "invariants": {
            "proven_state_destroy_allowed": False,
            "strong_regression_is_veto": True,
            "independent_canary_dimensions": ["boot", "resume", "hardware", "performance", "regression"],
            "guardian_approval_required_for_promotion_eligibility": True,
            "promotion_requires_separate_guardian_action": True,
        },
    }
