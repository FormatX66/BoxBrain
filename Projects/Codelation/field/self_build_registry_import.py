from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from self_build_registry import CapabilityArtifact, CapabilityRegistry, artifact_identity
from self_build_substrate_proposals import SubstrateProposal


@dataclass(frozen=True)
class CandidateTestEvidence:
    capability: str
    candidate_sha256: str
    test_sha256: str
    tests_passed: bool
    evidence: tuple[str, ...]
    node: str


def register_verified_candidates(
    proposals: Sequence[SubstrateProposal],
    evidence: Sequence[CandidateTestEvidence],
    *,
    registry: CapabilityRegistry | None = None,
) -> CapabilityRegistry:
    """Import verified candidate evidence without granting promotion authority."""
    target = CapabilityRegistry() if registry is None else registry
    proposal_by_capability = {item.capability: item for item in proposals}

    for item in evidence:
        proposal = proposal_by_capability.get(item.capability)
        if proposal is None:
            raise ValueError(f"missing semantic proposal for {item.capability}")
        if not item.tests_passed:
            continue
        if not item.candidate_sha256 or not item.test_sha256 or not item.evidence:
            raise ValueError("passing candidate evidence is incomplete")

        artifact = CapabilityArtifact(
            capability=item.capability,
            local_variant_identity=item.candidate_sha256,
            carrier_sha256=item.candidate_sha256,
            node=item.node,
            semantic_contract=proposal.semantic_contract,
        )
        identity = target.add(artifact)
        target.verify(
            identity,
            test_sha256=item.test_sha256,
            evidence=item.evidence,
        )
    return target


def substrate_test_evidence_records(
    payload: Mapping[str, object],
    *,
    node: str = "gpt-python-sandbox",
) -> tuple[CandidateTestEvidence, ...]:
    """Normalize persisted substrate evidence into registry-import records."""
    candidates = payload.get("candidates")
    if not isinstance(candidates, Mapping):
        raise ValueError("substrate evidence has no candidates mapping")
    records: list[CandidateTestEvidence] = []
    for capability in sorted(candidates):
        raw = candidates[capability]
        if not isinstance(raw, Mapping):
            raise ValueError("candidate evidence entry must be a mapping")
        passed = bool(raw.get("tests_passed"))
        evidence = []
        if passed:
            evidence.append("isolated-generated-tests-pass")
        if raw.get("stderr_empty") is True:
            evidence.append("isolated-stderr-empty")
        marker = raw.get("stdout_marker")
        if isinstance(marker, str) and marker:
            evidence.append(f"stdout:{marker}")
        records.append(
            CandidateTestEvidence(
                capability=str(capability),
                candidate_sha256=str(raw.get("candidate_sha256") or ""),
                test_sha256=str(raw.get("test_sha256") or ""),
                tests_passed=passed,
                evidence=tuple(evidence),
                node=node,
            )
        )
    return tuple(records)


__all__ = [
    "CandidateTestEvidence",
    "register_verified_candidates",
    "substrate_test_evidence_records",
]
