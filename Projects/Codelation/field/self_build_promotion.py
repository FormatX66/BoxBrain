from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable

from aurum_field import Field
from self_build_registry import (
    PROMOTED,
    VERIFIED,
    CapabilityArtifact,
    CapabilityRegistry,
    artifact_identity,
)


@dataclass(frozen=True)
class PromotionReview:
    artifact_identity: str
    permitted: bool
    reason: str
    semantic_review_identity: str
    learning_packet_identity: str | None


def verified_learning_identity(
    artifact: CapabilityArtifact,
    *,
    semantic_review_identity: str,
) -> str:
    """Address transferable learning before local promotion occurs."""
    if artifact.state != VERIFIED:
        raise ValueError("learning identity requires verified artifact")
    if not semantic_review_identity:
        raise ValueError("semantic review identity is required")
    payload = {
        "capability": artifact.capability,
        "source_node": artifact.node,
        "source_variant_identity": artifact.local_variant_identity,
        "semantic_contract": artifact.semantic_contract,
        "carrier_sha256": artifact.carrier_sha256,
        "test_sha256": artifact.test_sha256,
        "evidence": sorted(set(artifact.evidence)),
        "semantic_review_identity": semantic_review_identity,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.blake2s(b"AURUM-VERIFIED-LEARNING-0\x00" + raw).hexdigest()


def review_promotion(
    artifact: CapabilityArtifact,
    *,
    observed_carrier_sha256: str,
    semantic_review_identity: str,
    required_evidence: Iterable[str] = ("isolated-generated-tests-pass",),
) -> PromotionReview:
    identity = artifact_identity(artifact)
    if artifact.state != VERIFIED:
        return PromotionReview(identity, False, "artifact-not-verified", semantic_review_identity, None)
    if observed_carrier_sha256 != artifact.carrier_sha256:
        return PromotionReview(identity, False, "carrier-digest-mismatch", semantic_review_identity, None)
    if not semantic_review_identity:
        return PromotionReview(identity, False, "semantic-review-missing", semantic_review_identity, None)
    required = frozenset(str(item) for item in required_evidence)
    present = frozenset(artifact.evidence)
    if not required.issubset(present):
        return PromotionReview(identity, False, "required-evidence-missing", semantic_review_identity, None)
    learning = verified_learning_identity(
        artifact,
        semantic_review_identity=semantic_review_identity,
    )
    return PromotionReview(identity, True, "verified-evidence-satisfied", semantic_review_identity, learning)


def promote_reviewed_artifact(
    registry: CapabilityRegistry,
    review: PromotionReview,
    *,
    observed_carrier_sha256: str,
) -> CapabilityArtifact:
    if not review.permitted or not review.learning_packet_identity:
        raise ValueError("promotion review does not permit promotion")
    promoted = registry.promote(
        review.artifact_identity,
        observed_carrier_sha256=observed_carrier_sha256,
        learning_packet_identity=review.learning_packet_identity,
    )
    if promoted.state != PROMOTED:
        raise ValueError("registry did not enter promoted state")
    return promoted


def promotion_review_field(review: PromotionReview) -> Field:
    field = Field()
    ref = field.add(
        "fact",
        {
            "kind": "self-build-promotion-review",
            "artifact_identity": review.artifact_identity,
            "permitted": review.permitted,
            "reason": review.reason,
            "semantic_review_identity": review.semantic_review_identity,
            "learning_packet_identity": review.learning_packet_identity,
        },
    )
    field.add(
        "view",
        {
            "name": "aurum-self-build-promotion-review",
            "review": ref,
            "promotion_requires_verified_evidence": True,
            "promotion_requires_carrier_digest_match": True,
            "promotion_requires_semantic_review": True,
        },
    )
    return field


__all__ = [
    "PromotionReview",
    "promote_reviewed_artifact",
    "promotion_review_field",
    "review_promotion",
    "verified_learning_identity",
]
