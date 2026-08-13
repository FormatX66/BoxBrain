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
    """One node's verified local solution and the learning extracted from it.

    source_variant_identity identifies only the source node's implementation.
    It is evidence, never an install target for another node.
    """

    capability: str
    source_node: str
    source_variant_identity: str
    requires: frozenset[str]
    reward: RewardSignal
    evidence: tuple[str, ...] = ()
    learned_principles: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    success_conditions: tuple[str, ...] = ()
    failed_approaches: tuple[str, ...] = ()


@dataclass(frozen=True)
class UpgradeLane:
    node: str
    capability: str
    learning_packet_identity: str
    source_variant_identity: str
    missing_prerequisites: frozenset[str]
    mode: str
    stages: tuple[str, ...] = (
        "ingest-cluster-learning",
        "observe-local-state",
        "derive-local-capability-design",
        "adapt-or-build-local-prerequisites",
        "build-isolated-local-variant",
        "verify-local-variant",
        "promote-local-variant",
        "publish-new-learning",
        "emit-local-completion",
    )


@dataclass(frozen=True)
class CapabilityWave:
    wave_id: str
    learning_packet_identity: str
    source_node: str
    capability: str
    source_variant_identity: str
    lanes: tuple[UpgradeLane, ...]
    unavailable_nodes: tuple[str, ...]
    source_current_nodes: tuple[str, ...]
    blocked_reason: str | None = None

    @property
    def target_nodes(self) -> tuple[str, ...]:
        return tuple(lane.node for lane in self.lanes)


def _completion_payload(completion: CapabilityCompletion) -> Mapping[str, object]:
    return {
        "capability": completion.capability,
        "source_node": completion.source_node,
        "source_variant_identity": completion.source_variant_identity,
        "requires": sorted(completion.requires),
        "evidence": sorted(set(completion.evidence)),
        "learned_principles": sorted(set(completion.learned_principles)),
        "constraints": sorted(set(completion.constraints)),
        "success_conditions": sorted(set(completion.success_conditions)),
        "failed_approaches": sorted(set(completion.failed_approaches)),
        "reward_score": score_reward(completion.reward),
    }


def learning_packet_identity(completion: CapabilityCompletion) -> str:
    """Identify the transferable learning, not a cluster-wide implementation."""
    payload = {
        "capability": completion.capability,
        "source_variant_identity": completion.source_variant_identity,
        "requires": sorted(completion.requires),
        "evidence": sorted(set(completion.evidence)),
        "learned_principles": sorted(set(completion.learned_principles)),
        "constraints": sorted(set(completion.constraints)),
        "success_conditions": sorted(set(completion.success_conditions)),
        "failed_approaches": sorted(set(completion.failed_approaches)),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.blake2s(b"AURUM-CAPABILITY-LEARNING-0\x00" + raw).hexdigest()


def wave_identity(completion: CapabilityCompletion) -> str:
    raw = json.dumps(
        _completion_payload(completion),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.blake2s(b"AURUM-CAPABILITY-LEARNING-WAVE-0\x00" + raw).hexdigest()


def emit_capability_wave(
    completion: CapabilityCompletion,
    nodes: Iterable[UpgradeNode],
) -> CapabilityWave:
    """Broadcast learning so every verified available node invents its own variant.

    The source implementation is never copied or treated as the target identity.
    Every other node receives the same learned evidence, inspects its own state,
    and independently derives a local implementation. Nodes missing prerequisites
    enter an adaptation lane instead of being excluded.
    """
    blocked_reason = None
    if completion.reward.unsafe_or_unauthorized:
        blocked_reason = "unsafe-or-unauthorized-completion"
    elif completion.reward.false_claim:
        blocked_reason = "false-claim-completion"
    elif not completion.reward.verified:
        blocked_reason = "completion-not-verified"

    packet_id = learning_packet_identity(completion)
    wave_id = wave_identity(completion)
    if blocked_reason is not None:
        return CapabilityWave(
            wave_id=wave_id,
            learning_packet_identity=packet_id,
            source_node=completion.source_node,
            capability=completion.capability,
            source_variant_identity=completion.source_variant_identity,
            lanes=(),
            unavailable_nodes=(),
            source_current_nodes=(),
            blocked_reason=blocked_reason,
        )

    lanes: list[UpgradeLane] = []
    unavailable: list[str] = []
    source_current: list[str] = []

    for node in sorted(nodes, key=lambda item: item.name):
        if node.name == completion.source_node:
            source_current.append(node.name)
            continue
        if not node.available or not node.verified:
            unavailable.append(node.name)
            continue

        missing = completion.requires - node.capabilities
        mode = "derive-local-variant" if not missing else "adapt-prerequisites-then-derive"
        lanes.append(
            UpgradeLane(
                node=node.name,
                capability=completion.capability,
                learning_packet_identity=packet_id,
                source_variant_identity=completion.source_variant_identity,
                missing_prerequisites=frozenset(missing),
                mode=mode,
            )
        )

    return CapabilityWave(
        wave_id=wave_id,
        learning_packet_identity=packet_id,
        source_node=completion.source_node,
        capability=completion.capability,
        source_variant_identity=completion.source_variant_identity,
        lanes=tuple(lanes),
        unavailable_nodes=tuple(unavailable),
        source_current_nodes=tuple(source_current),
        blocked_reason=None,
    )


def capability_wave_field(completion: CapabilityCompletion, wave: CapabilityWave) -> Field:
    field = Field()
    learning_ref = field.add(
        "fact",
        {
            "kind": "verified-capability-learning",
            "learning_packet_identity": wave.learning_packet_identity,
            **_completion_payload(completion),
            "source_variant_is_evidence_not-template": True,
        },
    )
    lane_refs = []
    for lane in wave.lanes:
        lane_refs.append(
            field.add(
                "relation",
                {
                    "kind": "parallel-capability-learning-lane",
                    "wave_id": wave.wave_id,
                    "learns_from": learning_ref,
                    "node": lane.node,
                    "capability_goal": lane.capability,
                    "learning_packet_identity": lane.learning_packet_identity,
                    "source_variant_identity": lane.source_variant_identity,
                    "copy_source_variant": False,
                    "derive_own_variant": True,
                    "missing_prerequisites": sorted(lane.missing_prerequisites),
                    "mode": lane.mode,
                    "stages": list(lane.stages),
                    "local_verification_before_promotion": True,
                    "publish_new_learning_after_local_result": True,
                },
            )
        )
    field.add(
        "view",
        {
            "name": "aurum-capability-learning-wave",
            "wave_id": wave.wave_id,
            "learning_packet_identity": wave.learning_packet_identity,
            "source_node": wave.source_node,
            "capability_goal": wave.capability,
            "source_variant_identity": wave.source_variant_identity,
            "lanes": lane_refs,
            "target_nodes": list(wave.target_nodes),
            "unavailable_nodes": list(wave.unavailable_nodes),
            "source_current_nodes": list(wave.source_current_nodes),
            "blocked_reason": wave.blocked_reason,
            "shared_implementation": False,
            "shared_learning": True,
            "local_variants_expected_to_differ": True,
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
    "learning_packet_identity",
    "wave_identity",
]
