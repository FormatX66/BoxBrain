from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Iterable, Mapping, Sequence

from aurum_field import Field, Grain, Ref


MESH_REVISION = "event-ledger-v0"


@dataclass(frozen=True)
class RewardSignal:
    verified: bool = False
    reusable: bool = False
    generalized: bool = False
    uncertainty_reduced: bool = False
    assumption_corrected: bool = False
    false_claim: bool = False
    repeated_without_gain: bool = False
    unsafe_or_unauthorized: bool = False


def score_reward(signal: RewardSignal) -> int:
    """Evidence-first selection pressure for capability outcomes."""
    score = 0
    score += 40 if signal.verified else 0
    score += 20 if signal.reusable else 0
    score += 25 if signal.generalized else 0
    score += 10 if signal.uncertainty_reduced else 0
    score += 15 if signal.assumption_corrected else 0
    score -= 80 if signal.false_claim else 0
    score -= 15 if signal.repeated_without_gain else 0
    score -= 200 if signal.unsafe_or_unauthorized else 0
    return score


@dataclass(frozen=True)
class Capability:
    name: str
    accepts: frozenset[str] = frozenset()
    provides: frozenset[str] = frozenset()
    traits: Mapping[str, Any] = dc_field(default_factory=dict)


@dataclass(frozen=True)
class Composition:
    capabilities: tuple[str, ...]
    available: frozenset[str]
    complete: bool
    missing: frozenset[str]


def compose_capabilities(
    capabilities: Sequence[Capability],
    *,
    initial: Iterable[str] = (),
    required: Iterable[str] = (),
) -> Composition:
    """Reach a deterministic capability fixed point by meaning, not program ownership."""
    available = set(initial)
    chosen: list[str] = []
    remaining = sorted(capabilities, key=lambda capability: capability.name)
    progressed = True
    while progressed:
        progressed = False
        next_remaining: list[Capability] = []
        for capability in remaining:
            if capability.accepts.issubset(available):
                new = set(capability.provides) - available
                if new:
                    available.update(new)
                    chosen.append(capability.name)
                    progressed = True
            else:
                next_remaining.append(capability)
        remaining = next_remaining
    required_set = set(required)
    missing = required_set - available
    return Composition(
        tuple(chosen),
        frozenset(available),
        not missing,
        frozenset(missing),
    )


def _tokens(value: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(value, Ref):
        out.add(value.identity.hex())
    elif isinstance(value, str):
        normalized = value.casefold()
        out.add(normalized)
        out.update(
            part
            for part in normalized.replace("_", " ").replace("-", " ").split()
            if part
        )
    elif isinstance(value, bytes):
        out.add(value.hex())
    elif isinstance(value, Mapping):
        for key, item in value.items():
            out.update(_tokens(key))
            out.update(_tokens(item))
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            out.update(_tokens(item))
    elif value is not None:
        out.add(str(value).casefold())
    return out


def semantic_recall(field: Field, query: str, *, limit: int = 20) -> tuple[Grain, ...]:
    """Recall grains by meaning-bearing tokens without paths or table ownership."""
    wanted = {
        part
        for part in query.casefold().replace("_", " ").replace("-", " ").split()
        if part
    }
    if not wanted or limit <= 0:
        return ()
    ranked: list[tuple[int, bytes, Grain]] = []
    for identity in field.identities():
        grain = field.get(identity)
        tokens = _tokens(grain.value)
        tokens.add(str(grain.kind))
        score = sum(
            2 if word in tokens else 1
            for word in wanted
            if any(word in token for token in tokens)
        )
        if score:
            ranked.append((-score, identity, grain))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return tuple(item[2] for item in ranked[:limit])


@dataclass(frozen=True)
class Node:
    name: str
    capabilities: frozenset[str]
    capacity: int = 1
    cost: int = 0
    provider: str = "local"
    architecture: str = "any"
    available: bool = True
    expected_queue_seconds: int = 0
    estimated_runtime_seconds: int = 0
    cache_locality: float = 0.0
    external_cost_class: str = "free"
    verification_strength: int = 0
    authority_level: str = "BUILD-ONLY"
    authority_levels: frozenset[str] = frozenset()
    trust_level: int = 0
    safe: bool = True
    intent_compatible: bool = True
    optional: bool = False


@dataclass(frozen=True)
class WorkItem:
    name: str
    requires: frozenset[str]
    weight: int = 1
    architecture: str = "any"
    allowed_cost_classes: frozenset[str] = frozenset({"free", "controlled"})
    minimum_verification_strength: int = 0
    required_authority: str | None = None
    preserve_user_intent: bool = True


@dataclass(frozen=True)
class AssignmentPlan:
    assignments: Mapping[str, tuple[str, ...]]
    unassigned: tuple[str, ...]
    missing_capabilities: frozenset[str]


def assign_parallel(work: Sequence[WorkItem], nodes: Sequence[Node]) -> AssignmentPlan:
    """Assign independent work across suitable nodes without inventing capacity."""
    slots = {node.name: max(0, node.capacity) for node in nodes}
    assignments: dict[str, list[str]] = {node.name: [] for node in nodes}
    unassigned: list[str] = []
    missing: set[str] = set()

    for item in sorted(work, key=lambda candidate: (-candidate.weight, candidate.name)):
        candidates = [
            node
            for node in nodes
            if slots[node.name] > 0
            and node.available
            and node.safe
            and (node.intent_compatible or not item.preserve_user_intent)
            and item.requires.issubset(node.capabilities)
            and (item.architecture == "any" or node.architecture in {"any", item.architecture})
            and node.external_cost_class in item.allowed_cost_classes
            and node.verification_strength >= item.minimum_verification_strength
            and (
                item.required_authority is None
                or item.required_authority
                in (node.authority_levels or frozenset({node.authority_level}))
            )
        ]
        if not candidates:
            unassigned.append(item.name)
            union = set().union(*(node.capabilities for node in nodes)) if nodes else set()
            missing.update(item.requires - union)
            continue
        candidates.sort(
            key=lambda node: (
                -node.verification_strength,
                node.expected_queue_seconds + node.estimated_runtime_seconds,
                len(assignments[node.name]) / max(1, node.capacity),
                -node.cache_locality,
                node.cost,
                -node.capacity,
                -node.trust_level,
                node.name,
            )
        )
        selected = candidates[0]
        assignments[selected.name].append(item.name)
        slots[selected.name] -= 1

    return AssignmentPlan(
        assignments={
            name: tuple(items) for name, items in assignments.items() if items
        },
        unassigned=tuple(unassigned),
        missing_capabilities=frozenset(missing),
    )


def shadow_state(state: Mapping[str, Any]) -> tuple[Field, Mapping[str, Any]]:
    """Project conventional state into Field grains and rebuild the same human view."""
    field = Field()
    refs: dict[str, Ref] = {}
    for key in sorted(state):
        refs[key] = field.add("fact", {"key": key, "value": state[key]})
    field.add(
        "view",
        {"name": "shadow-state", "members": [refs[key] for key in sorted(refs)]},
    )

    rebuilt: dict[str, Any] = {}
    for identity in field.identities():
        grain = field.get(identity)
        if (
            grain.kind == 1
            and isinstance(grain.value, dict)
            and set(grain.value) == {"key", "value"}
        ):
            rebuilt[str(grain.value["key"])] = grain.value["value"]
    return field, rebuilt


__all__ = [
    "AssignmentPlan",
    "Capability",
    "Composition",
    "MESH_REVISION",
    "Node",
    "RewardSignal",
    "WorkItem",
    "assign_parallel",
    "compose_capabilities",
    "score_reward",
    "semantic_recall",
    "shadow_state",
]
