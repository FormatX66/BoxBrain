from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Evidence:
    source: str
    behavior: str
    confidence: float
    independent_group: str


@dataclass(frozen=True)
class BehavioralFact:
    behavior: str
    confidence: float
    source_count: int
    independent_groups: int
    safe_for_read_only_probe: bool


def build_behavioral_fact(evidence: Iterable[Evidence]) -> BehavioralFact:
    """Fuse agreeing sources without trusting any single source blindly."""

    items = tuple(evidence)
    if not items:
        raise ValueError("at least one evidence item is required")

    behavior = items[0].behavior
    if any(item.behavior != behavior for item in items):
        raise ValueError("conflicting behaviors must be modeled as separate hypotheses")

    for item in items:
        if not 0.0 <= item.confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")

    groups = {item.independent_group for item in items}
    # Independent corroboration raises confidence, but never to absolute certainty.
    miss_probability = 1.0
    group_best: dict[str, float] = {}
    for item in items:
        group_best[item.independent_group] = max(group_best.get(item.independent_group, 0.0), item.confidence)
    for confidence in group_best.values():
        miss_probability *= 1.0 - confidence
    fused = min(0.999, 1.0 - miss_probability)

    safe_probe = len(groups) >= 2 and fused >= 0.90
    return BehavioralFact(
        behavior=behavior,
        confidence=fused,
        source_count=len(items),
        independent_groups=len(groups),
        safe_for_read_only_probe=safe_probe,
    )


def select_probe(fact: BehavioralFact) -> dict[str, object]:
    """Return only a reversible/read-only experiment from model evidence."""

    if not fact.safe_for_read_only_probe:
        return {"action": "defer", "reason": "insufficient independent confidence"}
    return {
        "action": "read-only-observe",
        "behavior": fact.behavior,
        "reversible": True,
        "writes_allowed": False,
        "confidence": fact.confidence,
    }
