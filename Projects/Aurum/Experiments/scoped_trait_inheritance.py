"""Gen3 scoped multi-node trait inheritance for Aurum.

Traits are evidence-bearing candidate information, never remote authority. Scope,
lineage, provenance, safety vetoes, and trusted node identity are explicit. The
module is pure: no transport, device mutation, promotion, trust-store changes,
or LKG mutation are performed here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Iterable, Mapping


def _stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _token(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _digest(value: str, name: str) -> str:
    value = _token(value, name).lower()
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
    return value


def _confidence(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("confidence must be numeric")
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError("confidence must be within [0, 1]")
    return value


@dataclass(frozen=True)
class TraitScope:
    hardware: tuple[str, ...] = ()
    workload: tuple[str, ...] = ()
    environment: tuple[str, ...] = ()
    phenotype: tuple[str, ...] = ()

    def canonical(self) -> dict:
        def normalize(values: tuple[str, ...], name: str) -> list[str]:
            return sorted({_token(item, name) for item in values})
        return {
            "hardware": normalize(self.hardware, "hardware scope"),
            "workload": normalize(self.workload, "workload scope"),
            "environment": normalize(self.environment, "environment scope"),
            "phenotype": normalize(self.phenotype, "phenotype scope"),
        }

    def covers(self, target: "TraitScope") -> bool:
        """A trait covers a target only when every constrained dimension contains it."""
        source = self.canonical()
        wanted = target.canonical()
        for dimension in source:
            allowed = set(source[dimension])
            requested = set(wanted[dimension])
            if allowed and not requested.issubset(allowed):
                return False
        return True


@dataclass(frozen=True)
class TraitEvidence:
    evidence_id: str
    digest: str
    confidence: float
    safety_veto: bool = False

    def canonical(self) -> dict:
        if not isinstance(self.safety_veto, bool):
            raise ValueError("safety_veto must be boolean")
        return {
            "evidence_id": _token(self.evidence_id, "evidence_id"),
            "digest": _digest(self.digest, "evidence digest"),
            "confidence": _confidence(self.confidence),
            "safety_veto": self.safety_veto,
        }


@dataclass(frozen=True)
class TraitCandidate:
    trait_id: str
    version: str
    source_node: str
    lineage_digest: str
    payload_digest: str
    scope: TraitScope
    evidence: tuple[TraitEvidence, ...]
    parent_trait_digest: str | None = None

    def canonical(self) -> dict:
        parent = None if self.parent_trait_digest is None else _digest(
            self.parent_trait_digest, "parent trait digest"
        )
        evidence = sorted((item.canonical() for item in self.evidence), key=_stable_json)
        if not evidence:
            raise ValueError("trait requires at least one evidence item")
        return {
            "trait_id": _token(self.trait_id, "trait_id"),
            "version": _token(self.version, "version"),
            "source_node": _token(self.source_node, "source_node"),
            "lineage_digest": _digest(self.lineage_digest, "lineage digest"),
            "payload_digest": _digest(self.payload_digest, "payload digest"),
            "parent_trait_digest": parent,
            "scope": self.scope.canonical(),
            "evidence": evidence,
        }

    def digest(self) -> str:
        return _sha256(self.canonical())


@dataclass(frozen=True)
class ReceivingContext:
    node_id: str
    trusted_nodes: frozenset[str]
    target_scope: TraitScope
    current_lkg_digest: str
    expected_parent_lineage: str | None = None

    def canonical(self) -> dict:
        return {
            "node_id": _token(self.node_id, "node_id"),
            "trusted_nodes": sorted(_token(node, "trusted node") for node in self.trusted_nodes),
            "target_scope": self.target_scope.canonical(),
            "current_lkg_digest": _digest(self.current_lkg_digest, "LKG digest"),
            "expected_parent_lineage": (
                None
                if self.expected_parent_lineage is None
                else _digest(self.expected_parent_lineage, "expected parent lineage")
            ),
        }


def evaluate_trait(candidate: TraitCandidate, context: ReceivingContext) -> dict:
    trait = candidate.canonical()
    receiver = context.canonical()
    reasons: list[str] = []

    if trait["source_node"] not in set(receiver["trusted_nodes"]):
        reasons.append("untrusted-source-node")
    if not candidate.scope.covers(context.target_scope):
        reasons.append("out-of-scope")
    if receiver["expected_parent_lineage"] is not None and (
        trait["lineage_digest"] != receiver["expected_parent_lineage"]
    ):
        reasons.append("lineage-mismatch")
    if any(item["safety_veto"] for item in trait["evidence"]):
        reasons.append("safety-veto")

    mean_confidence = sum(item["confidence"] for item in trait["evidence"]) / len(trait["evidence"])
    accepted_as_evidence = not reasons
    state = "candidate-evidence-accepted" if accepted_as_evidence else "quarantined"

    return {
        "trait_digest": candidate.digest(),
        "state": state,
        "accepted_as_evidence": accepted_as_evidence,
        "quarantine_reasons": reasons,
        "mean_confidence": mean_confidence,
        "lkg_digest_before": receiver["current_lkg_digest"],
        "lkg_digest_after": receiver["current_lkg_digest"],
        "scope_widened": False,
        "trust_widened": False,
        "grants_mutation_authority": False,
        "grants_promotion_authority": False,
        "may_bind_driver": False,
        "may_replace_kernel": False,
    }


def merge_cross_node_evidence(candidates: Iterable[TraitCandidate]) -> dict:
    """Merge identical scoped traits deterministically without vote-based authority."""
    items = list(candidates)
    if not items:
        raise ValueError("at least one candidate is required")
    canonical = [item.canonical() for item in items]
    identity = {
        (
            item["trait_id"],
            item["version"],
            item["payload_digest"],
            _stable_json(item["scope"]),
            item["lineage_digest"],
        )
        for item in canonical
    }
    if len(identity) != 1:
        return {
            "state": "quarantined-conflict",
            "merged": False,
            "source_nodes": sorted({item["source_node"] for item in canonical}),
            "grants_authority": False,
        }

    evidence_by_key: dict[tuple[str, str], dict] = {}
    for item in canonical:
        for evidence in item["evidence"]:
            key = (evidence["evidence_id"], evidence["digest"])
            previous = evidence_by_key.get(key)
            if previous is not None and previous != evidence:
                return {
                    "state": "quarantined-evidence-conflict",
                    "merged": False,
                    "source_nodes": sorted({item["source_node"] for item in canonical}),
                    "grants_authority": False,
                }
            evidence_by_key[key] = evidence

    merged_evidence = [evidence_by_key[key] for key in sorted(evidence_by_key)]
    safety_veto = any(item["safety_veto"] for item in merged_evidence)
    return {
        "state": "merged-evidence" if not safety_veto else "merged-evidence-vetoed",
        "merged": True,
        "source_nodes": sorted({item["source_node"] for item in canonical}),
        "evidence": merged_evidence,
        "safety_veto": safety_veto,
        "scope_widened": False,
        "trust_widened": False,
        "grants_authority": False,
    }


def provenance_replay(candidate: TraitCandidate, *, expected_trait_digest: str) -> dict:
    expected = _digest(expected_trait_digest, "expected trait digest")
    actual = candidate.digest()
    if actual != expected:
        raise ValueError("trait provenance replay digest mismatch")
    canonical = candidate.canonical()
    return {
        "trait_digest": actual,
        "source_node": canonical["source_node"],
        "lineage_digest": canonical["lineage_digest"],
        "parent_trait_digest": canonical["parent_trait_digest"],
        "scope": canonical["scope"],
        "evidence_digests": [item["digest"] for item in canonical["evidence"]],
        "replay_verified": True,
        "grants_authority": False,
    }


def gen3_inheritance_gate(*, lineage_verified: bool, scoped_inheritance_verified: bool,
                          cross_node_merge_verified: bool, phenotype_scope_verified: bool,
                          provenance_replay_verified: bool, non_widening_trust_verified: bool) -> Mapping[str, bool]:
    """Project software-only evidence into the shared generation ladder."""
    return {
        "lineage_ledger": lineage_verified is True,
        "scoped_trait_inheritance": scoped_inheritance_verified is True,
        "cross_node_evidence_merge": cross_node_merge_verified is True,
        "phenotype_scope_guard": phenotype_scope_verified is True,
        "provenance_replay": provenance_replay_verified is True,
        "non_widening_trust_guard": non_widening_trust_verified is True,
        "grants_mutation_authority": False,
        "infers_multi_node_physical_proof": False,
    }
