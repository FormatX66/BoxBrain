from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from aurum_field import Field
from capacity_mesh import RewardSignal
from capability_wave import (
    CapabilityCompletion,
    CapabilityWave,
    UpgradeNode,
    capability_wave_field,
    emit_capability_wave,
)
from self_build_registry import PROMOTED, CapabilityArtifact, artifact_identity


@dataclass(frozen=True)
class RegistryLearningWave:
    artifact_identity: str
    completion: CapabilityCompletion
    wave: CapabilityWave


def promoted_artifact_completion(artifact: CapabilityArtifact) -> CapabilityCompletion:
    """Convert one promoted local variant into transferable cluster learning."""
    if artifact.state != PROMOTED:
        raise ValueError("only promoted artifacts may emit cluster learning waves")
    if not artifact.learning_packet_identity:
        raise ValueError("promoted artifact is missing learning packet identity")
    return CapabilityCompletion(
        capability=artifact.capability,
        source_node=artifact.node,
        source_variant_identity=artifact.local_variant_identity,
        requires=frozenset(),
        reward=RewardSignal(verified=True, reusable=True, generalized=True),
        evidence=tuple(sorted(set(artifact.evidence + (
            f"artifact:{artifact_identity(artifact)}",
            f"carrier:{artifact.carrier_sha256}",
            f"tests:{artifact.test_sha256}",
        )))),
        learned_principles=(artifact.semantic_contract,),
        constraints=(
            "derive-own-local-variant",
            "do-not-copy-source-carrier",
            "local-verification-before-promotion",
        ),
        success_conditions=(
            "same-semantic-capability-goal",
            "local-variant-independently-verified",
        ),
        failed_approaches=(),
    )


def emit_registry_learning_wave(
    artifact: CapabilityArtifact,
    nodes: Iterable[UpgradeNode],
) -> RegistryLearningWave:
    completion = promoted_artifact_completion(artifact)
    wave = emit_capability_wave(completion, nodes)
    return RegistryLearningWave(
        artifact_identity=artifact_identity(artifact),
        completion=completion,
        wave=wave,
    )


def registry_learning_wave_field(item: RegistryLearningWave) -> Field:
    field = capability_wave_field(item.completion, item.wave)
    field.add(
        "view",
        {
            "name": "aurum-registry-learning-wave",
            "artifact_identity": item.artifact_identity,
            "learning_packet_identity": item.wave.learning_packet_identity,
            "source_variant_identity": item.wave.source_variant_identity,
            "target_nodes": list(item.wave.target_nodes),
            "shared_carrier": False,
            "shared_learning": True,
        },
    )
    return field


__all__ = [
    "RegistryLearningWave",
    "emit_registry_learning_wave",
    "promoted_artifact_completion",
    "registry_learning_wave_field",
]
