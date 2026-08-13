from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable, Mapping

from aurum_field import Field
from capacity_mesh import RewardSignal, score_reward


@dataclass(frozen=True)
class UpgradeNode:
    name: str
    capabilities: frozenset[str]
    available: bool = True
    verified: bool = True


@dataclass(frozen=True)
class CapabilityCompletion:
    capability: str
    source_node: str
    semantic_identity: str
    requires: frozenset[str]
    reward: RewardSignal
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class UpgradeLane:
    node: str
    capability: str
    semantic_identity: str
    requires: frozenset[str]
    stages: tuple[str, ...] = (
        "adapt-local-carrier",
        "build-isolated-candidate",
        "verify-local-candidate",
        "promote-local-capability",
        "emit-local-completion",
    )


@dataclass(frozen=True)
class CapabilityWave:
    wave_id: str
    source_node: str
    capability: str
    semantic_identity: str
    lanes: tuple[UpgradeLane, ...]
    unavailable_nodes: tuple[str, ...]
    incompatible_nodes: tuple[str, ...]
    already_current_nodes: tuple[str, ...]
    blocked_reason: str | None = None

    @property
    def target_nodes(self) -> tuple[str, ...]:
        return tuple(lane.node for lane in self.lanes)


def _completion_payload(completion: CapabilityCompletion) -> Mapping[str, object]:
    return {
        "capability": completion.capability,
        "source_node": completion.source_node,
        "semantic_identity": completion.semantic_identity,
        "requires": sorted(completion.requires),
        "evidence": sorted(set(completion.evidence)),
        "reward_score": score_reward(completion.reward),
    }


def wave_identity(completion: CapabilityCompletion) -> str:
    raw = json.dumps(
        _completion_payload(completion),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.blake2s(b"AURUM-CAPABILITY-WAVE-0\x00" + raw).hexdigest()


def emit_capability_wave(
    completion: CapabilityCompletion,
    nodes: Iterable[UpgradeNode],
    *,
    current_semantic_identities: Mapping[str, frozenset[str]] | None = None,
) -> CapabilityWave:
    """Fan one verified capability completion to every eligible node at once.

    The wave carries semantic capability identity, not a shared binary. Each node
    receives an independent local materialization lane and may promote only after
    its own local verification succeeds.
    """
    current = current_semantic_identities or {}
    blocked_reason = None
    if completion.reward.unsafe_or_unauthorized:
        blocked_reason = "unsafe-or-unauthorized-completion"
    elif completion.reward.false_claim:
        blocked_reason = "false-claim-completion"
    elif not completion.reward.verified:
        blocked_reason = "completion-not-verified"

    wave_id = wave_identity(completion)
    if blocked_reason is not None:
        return CapabilityWave(
            wave_id=wave_id,
            source_node=completion.source_node,
            capability=completion.capability,
            semantic_identity=completion.semantic_identity,
            lanes=(),
            unavailable_nodes=(),
            incompatible_nodes=(),
            already_current_nodes=(),
            blocked_reason=blocked_reason,
        )

    lanes: list[UpgradeLane] = []
    unavailable: list[str] = []
    incompatible: list[str] = []
    already_current: list[str] = []

    for node in sorted(nodes, key=lambda item: item.name):
        if node.name == completion.source_node:
            already_current.append(node.name)
            continue
        if not node.available or not node.verified:
            unavailable.append(node.name)
            continue
        if completion.semantic_identity in current.get(node.name, frozenset()):
            already_current.append(node.name)
            continue
        if not completion.requires.issubset(node.capabilities):
            incompatible.append(node.name)
            continue
        lanes.append(
            UpgradeLane(
                node=node.name,
                capability=completion.capability,
                semantic_identity=completion.semantic_identity,
                requires=completion.requires,
            )
        )

    return CapabilityWave(
        wave_id=wave_id,
        source_node=completion.source_node,
        capability=completion.capability,
        semantic_identity=completion.semantic_identity,
        lanes=tuple(lanes),
        unavailable_nodes=tuple(unavailable),
        incompatible_nodes=tuple(incompatible),
        already_current_nodes=tuple(already_current),
        blocked_reason=None,
    )


def capability_wave_field(completion: CapabilityCompletion, wave: CapabilityWave) -> Field:
    field = Field()
    completion_ref = field.add(
        "fact",
        {
            "kind": "verified-capability-completion",
            **_completion_payload(completion),
        },
    )
    lane_refs = []
    for lane in wave.lanes:
        lane_refs.append(
            field.add(
                "relation",
                {
                    "kind": "parallel-capability-upgrade-lane",
                    "wave_id": wave.wave_id,
                    "caused_by": completion_ref,
                    "node": lane.node,
                    "capability": lane.capability,
                    "semantic_identity": lane.semantic_identity,
                    "requires": sorted(lane.requires),
                    "stages": list(lane.stages),
                    "local_verification_before_promotion": True,
                },
            )
        )
    field.add(
        "view",
        {
            "name": "aurum-capability-wave",
            "wave_id": wave.wave_id,
            "source_node": wave.source_node,
            "capability": wave.capability,
            "semantic_identity": wave.semantic_identity,
            "lanes": lane_refs,
            "target_nodes": list(wave.target_nodes),
            "unavailable_nodes": list(wave.unavailable_nodes),
            "incompatible_nodes": list(wave.incompatible_nodes),
            "already_current_nodes": list(wave.already_current_nodes),
            "blocked_reason": wave.blocked_reason,
            "timer_dependency": False,
            "global_barrier_before_start": False,
        },
    )
    return field


__all__ = [
    "CapabilityCompletion",
    "CapabilityWave",
    "UpgradeLane",
    "UpgradeNode",
    "capability_wave_field",
    "emit_capability_wave",
    "wave_identity",
]
