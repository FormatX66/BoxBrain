from __future__ import annotations

from dataclasses import dataclass, fields
import hashlib
import json
from typing import Mapping, Sequence

from aurum_field import Field
from capacity_mesh import (
    Node,
    RewardSignal,
    WorkItem,
    assign_parallel,
    score_reward,
)


@dataclass(frozen=True)
class CompletionEvent:
    """Verified-or-evaluated completion that may cause more capability work."""

    name: str
    node: str
    reward: RewardSignal
    followups: tuple[WorkItem, ...] = ()
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class Handoff:
    """One claimable unit caused by a completion event rather than by a clock."""

    event_id: str
    cause: str
    work: WorkItem
    reward_score: int


@dataclass(frozen=True)
class HandoffPlan:
    emitted: tuple[Handoff, ...]
    assignments: Mapping[str, tuple[str, ...]]
    unassigned: tuple[str, ...]
    missing_capabilities: frozenset[str]


def _reward_payload(reward: RewardSignal) -> dict[str, bool]:
    return {item.name: bool(getattr(reward, item.name)) for item in fields(RewardSignal)}


def completion_id(event: CompletionEvent) -> str:
    """Return a deterministic identity for a completion independent of set ordering."""

    payload = {
        "name": event.name,
        "node": event.node,
        "reward": _reward_payload(event.reward),
        "evidence": sorted(set(event.evidence)),
        "followups": [
            {
                "name": item.name,
                "requires": sorted(item.requires),
                "weight": item.weight,
            }
            for item in sorted(
                event.followups,
                key=lambda candidate: (
                    candidate.name,
                    tuple(sorted(candidate.requires)),
                    candidate.weight,
                ),
            )
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.blake2s(b"AURUM-EVENT-HANDOFF-0\x00" + canonical, digest_size=32).hexdigest()


def _adjust_weight(work: WorkItem, reward_score: int) -> int:
    # Reward influences selection pressure but can never make work disappear by arithmetic.
    # Unsafe/false completions are filtered separately and cannot emit follow-ups at all.
    bonus = max(-10, min(50, reward_score // 5))
    return max(1, work.weight + bonus)


def emit_handoffs(completions: Sequence[CompletionEvent]) -> tuple[Handoff, ...]:
    """Derive all safe next work from completion events; no event means no continuation."""

    deduped: dict[tuple[str, tuple[str, ...]], Handoff] = {}
    for completion in sorted(completions, key=completion_id):
        # Bad evidence must not create selection pressure toward more actions.
        if completion.reward.unsafe_or_unauthorized or completion.reward.false_claim:
            continue
        source_id = completion_id(completion)
        reward_score = score_reward(completion.reward)
        for work in completion.followups:
            adjusted = WorkItem(
                name=work.name,
                requires=work.requires,
                weight=_adjust_weight(work, reward_score),
            )
            key = (adjusted.name, tuple(sorted(adjusted.requires)))
            candidate = Handoff(
                event_id=hashlib.blake2s(
                    (
                        "AURUM-HANDOFF-0\x00"
                        + source_id
                        + "\x00"
                        + adjusted.name
                        + "\x00"
                        + ",".join(sorted(adjusted.requires))
                    ).encode("utf-8"),
                    digest_size=32,
                ).hexdigest(),
                cause=source_id,
                work=adjusted,
                reward_score=reward_score,
            )
            current = deduped.get(key)
            if current is None or (
                candidate.work.weight,
                candidate.reward_score,
                candidate.event_id,
            ) > (
                current.work.weight,
                current.reward_score,
                current.event_id,
            ):
                deduped[key] = candidate

    return tuple(
        sorted(
            deduped.values(),
            key=lambda handoff: (-handoff.work.weight, handoff.work.name, handoff.event_id),
        )
    )


def claim_handoffs(handoffs: Sequence[Handoff], nodes: Sequence[Node]) -> HandoffPlan:
    """Let suitable nodes claim emitted work while keeping capability gaps explicit."""

    if not handoffs:
        return HandoffPlan((), {}, (), frozenset())

    assignment = assign_parallel([handoff.work for handoff in handoffs], nodes)
    return HandoffPlan(
        emitted=tuple(handoffs),
        assignments=assignment.assignments,
        unassigned=assignment.unassigned,
        missing_capabilities=assignment.missing_capabilities,
    )


def continue_from_events(
    completions: Sequence[CompletionEvent],
    nodes: Sequence[Node],
) -> HandoffPlan:
    """Event-driven continuation: completion -> handoffs -> claims, with no timer input."""

    return claim_handoffs(emit_handoffs(completions), nodes)


def handoff_field(completions: Sequence[CompletionEvent], plan: HandoffPlan) -> Field:
    """Represent completion and handoff evidence in Aurum Field without executable payloads."""

    field = Field()
    completion_refs = []
    for completion in sorted(completions, key=completion_id):
        completion_refs.append(
            field.add(
                "fact",
                {
                    "event_id": completion_id(completion),
                    "name": completion.name,
                    "node": completion.node,
                    "reward": _reward_payload(completion.reward),
                    "evidence": sorted(set(completion.evidence)),
                },
            )
        )

    handoff_refs = []
    for handoff in plan.emitted:
        handoff_refs.append(
            field.add(
                "relation",
                {
                    "event_id": handoff.event_id,
                    "caused_by": handoff.cause,
                    "work": handoff.work.name,
                    "requires": sorted(handoff.work.requires),
                    "weight": handoff.work.weight,
                    "reward_score": handoff.reward_score,
                },
            )
        )

    field.add(
        "view",
        {
            "name": "event-driven-capability-handoff",
            "completions": completion_refs,
            "handoffs": handoff_refs,
            "assignments": {
                node: list(items) for node, items in sorted(plan.assignments.items())
            },
            "unassigned": list(plan.unassigned),
            "missing_capabilities": sorted(plan.missing_capabilities),
        },
    )
    return field


__all__ = [
    "CompletionEvent",
    "Handoff",
    "HandoffPlan",
    "claim_handoffs",
    "completion_id",
    "continue_from_events",
    "emit_handoffs",
    "handoff_field",
]
