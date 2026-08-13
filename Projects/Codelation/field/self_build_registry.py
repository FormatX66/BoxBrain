from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from typing import Iterable, Mapping

from aurum_field import Field


CANDIDATE = "candidate"
VERIFIED = "verified"
PROMOTED = "promoted"
REJECTED = "rejected"
_STATES = frozenset({CANDIDATE, VERIFIED, PROMOTED, REJECTED})


@dataclass(frozen=True)
class CapabilityArtifact:
    capability: str
    local_variant_identity: str
    carrier_sha256: str
    node: str
    semantic_contract: str
    evidence: tuple[str, ...] = ()
    state: str = CANDIDATE
    test_sha256: str | None = None
    learning_packet_identity: str | None = None

    def __post_init__(self) -> None:
        if self.state not in _STATES:
            raise ValueError("invalid capability artifact state")
        if not self.capability or not self.local_variant_identity or not self.carrier_sha256:
            raise ValueError("capability, local variant identity, and carrier digest are required")
        if self.state in {VERIFIED, PROMOTED} and (not self.test_sha256 or not self.evidence):
            raise ValueError("verified/promoted artifact requires test digest and evidence")


def artifact_identity(artifact: CapabilityArtifact) -> str:
    payload = {
        "capability": artifact.capability,
        "local_variant_identity": artifact.local_variant_identity,
        "carrier_sha256": artifact.carrier_sha256,
        "node": artifact.node,
        "semantic_contract": artifact.semantic_contract,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.blake2s(b"AURUM-SELF-BUILD-ARTIFACT-0\x00" + raw).hexdigest()


class CapabilityRegistry:
    """Durable metadata registry for locally built Aurum capability variants.

    The registry deliberately stores identities, evidence, and carrier digests—not
    executable source. Another node learns from the semantic/evidence record and
    derives its own local variant rather than copying this carrier.
    """

    def __init__(self, artifacts: Iterable[CapabilityArtifact] = ()) -> None:
        self._artifacts: dict[str, CapabilityArtifact] = {}
        for artifact in artifacts:
            self.add(artifact)

    def add(self, artifact: CapabilityArtifact) -> str:
        identity = artifact_identity(artifact)
        existing = self._artifacts.get(identity)
        if existing is not None and existing != artifact:
            raise ValueError("conflicting state for capability artifact")
        self._artifacts[identity] = artifact
        return identity

    def artifacts(self) -> tuple[CapabilityArtifact, ...]:
        return tuple(self._artifacts[key] for key in sorted(self._artifacts))

    def verify(
        self,
        identity: str,
        *,
        test_sha256: str,
        evidence: Iterable[str],
    ) -> CapabilityArtifact:
        current = self._artifacts[identity]
        if current.state not in {CANDIDATE, VERIFIED}:
            raise ValueError("only candidate/verified artifacts can enter verified state")
        items = tuple(sorted(set(str(item) for item in evidence if str(item))))
        if not test_sha256 or not items:
            raise ValueError("verification requires test digest and evidence")
        verified = replace(
            current,
            state=VERIFIED,
            test_sha256=test_sha256,
            evidence=items,
        )
        self._artifacts[identity] = verified
        return verified

    def promote(
        self,
        identity: str,
        *,
        observed_carrier_sha256: str,
        learning_packet_identity: str,
    ) -> CapabilityArtifact:
        current = self._artifacts[identity]
        if current.state != VERIFIED:
            raise ValueError("promotion requires verified artifact")
        if observed_carrier_sha256 != current.carrier_sha256:
            raise ValueError("carrier digest changed after verification")
        if not learning_packet_identity:
            raise ValueError("promotion requires learning packet identity")
        promoted = replace(
            current,
            state=PROMOTED,
            learning_packet_identity=learning_packet_identity,
        )
        self._artifacts[identity] = promoted
        return promoted

    def reject(self, identity: str) -> CapabilityArtifact:
        current = self._artifacts[identity]
        if current.state == PROMOTED:
            raise ValueError("promoted artifact cannot be silently rejected")
        rejected = replace(current, state=REJECTED)
        self._artifacts[identity] = rejected
        return rejected


def registry_field(registry: CapabilityRegistry) -> Field:
    field = Field()
    refs = []
    for artifact in registry.artifacts():
        refs.append(
            field.add(
                "capability",
                {
                    "artifact_identity": artifact_identity(artifact),
                    "capability": artifact.capability,
                    "local_variant_identity": artifact.local_variant_identity,
                    "carrier_sha256": artifact.carrier_sha256,
                    "node": artifact.node,
                    "semantic_contract": artifact.semantic_contract,
                    "state": artifact.state,
                    "test_sha256": artifact.test_sha256,
                    "evidence": list(artifact.evidence),
                    "learning_packet_identity": artifact.learning_packet_identity,
                    "executable_source_stored": False,
                    "copy_to_other_nodes": False,
                },
            )
        )
    field.add(
        "view",
        {
            "name": "aurum-self-build-capability-registry",
            "artifacts": refs,
            "shared_learning_not_shared_binary": True,
        },
    )
    return field


__all__ = [
    "CANDIDATE",
    "PROMOTED",
    "REJECTED",
    "VERIFIED",
    "CapabilityArtifact",
    "CapabilityRegistry",
    "artifact_identity",
    "registry_field",
]
