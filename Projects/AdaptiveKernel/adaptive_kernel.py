"""Adaptive Kernel generation-0 prototype.

This lane produces *plans only*. It does not bind drivers, write firmware, change
boot state, or perform privileged hardware operations.

Future Branch integration emits auditable candidate proposals only. It does not
rank or promote them, so this standalone experiment remains independent of
StateWeave and of the external policy/safety evaluator.
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
    """Emit safety-evaluator-ready Future Branch proposals.

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
