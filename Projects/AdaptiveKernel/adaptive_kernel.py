"""Adaptive Kernel generation-0 prototype.

This lane produces *plans only*. It does not bind drivers, write firmware, change
boot state, or perform privileged hardware operations.
"""

from __future__ import annotations

from dataclasses import dataclass
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
