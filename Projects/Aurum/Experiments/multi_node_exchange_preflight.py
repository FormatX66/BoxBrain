"""Gen3 software-only multi-node exchange preflight for Aurum Future Branch.

This module prepares and replays deterministic trait-exchange envelopes before a
real transport or physical peer is available.  It deliberately does not provide
sender authentication, network delivery proof, peer liveness, recovery proof,
LKG mutation, or promotion authority.  Those remain external/physical gates.
"""
from __future__ import annotations

import hashlib
import json
from typing import Mapping

from scoped_trait_inheritance import (
    ReceivingContext,
    TraitCandidate,
    TraitEvidence,
    TraitScope,
    evaluate_trait,
)


_SCHEMA = "aurum-gen3-trait-exchange-envelope-v1"


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
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _sequence(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("sequence must be a non-negative integer")
    return value


def _candidate_from_canonical(payload: Mapping[str, object]) -> TraitCandidate:
    if not isinstance(payload, Mapping):
        raise ValueError("candidate must be an object")
    scope = payload.get("scope")
    evidence = payload.get("evidence")
    if not isinstance(scope, Mapping) or not isinstance(evidence, list):
        raise ValueError("candidate scope/evidence malformed")

    def tuple_field(name: str) -> tuple[str, ...]:
        values = scope.get(name, [])
        if not isinstance(values, list):
            raise ValueError(f"candidate scope {name} malformed")
        return tuple(values)

    evidence_items: list[TraitEvidence] = []
    for item in evidence:
        if not isinstance(item, Mapping):
            raise ValueError("candidate evidence malformed")
        evidence_items.append(
            TraitEvidence(
                evidence_id=item.get("evidence_id"),
                digest=item.get("digest"),
                confidence=item.get("confidence"),
                safety_veto=item.get("safety_veto", False),
            )
        )

    candidate = TraitCandidate(
        trait_id=payload.get("trait_id"),
        version=payload.get("version"),
        source_node=payload.get("source_node"),
        lineage_digest=payload.get("lineage_digest"),
        payload_digest=payload.get("payload_digest"),
        parent_trait_digest=payload.get("parent_trait_digest"),
        scope=TraitScope(
            hardware=tuple_field("hardware"),
            workload=tuple_field("workload"),
            environment=tuple_field("environment"),
            phenotype=tuple_field("phenotype"),
        ),
        evidence=tuple(evidence_items),
    )
    if candidate.canonical() != dict(payload):
        raise ValueError("candidate is not canonical")
    return candidate


def build_exchange_envelope(
    candidate: TraitCandidate,
    *,
    claimed_sender_node: str,
    receiver_node: str,
    exchange_id: str,
    sequence: int,
    source_lkg_digest: str,
) -> dict:
    """Prepare a deterministic envelope without claiming it crossed a network."""
    canonical = candidate.canonical()
    sender = _token(claimed_sender_node, "claimed_sender_node")
    if sender != canonical["source_node"]:
        raise ValueError("claimed sender must match candidate source node")
    body = {
        "schema": _SCHEMA,
        "exchange_id": _token(exchange_id, "exchange_id"),
        "sequence": _sequence(sequence),
        "claimed_sender_node": sender,
        "receiver_node": _token(receiver_node, "receiver_node"),
        "source_lkg_digest": _digest(source_lkg_digest, "source LKG digest"),
        "candidate_digest": candidate.digest(),
        "candidate": canonical,
        "sender_identity_authenticated": False,
        "network_delivery_proven": False,
        "peer_liveness_proven": False,
        "live_multi_node_exchange_proven": False,
        "independent_node_recovery_proven": False,
        "grants_mutation_authority": False,
        "grants_promotion_authority": False,
        "infers_physical_proof": False,
    }
    return {**body, "envelope_digest": _sha256(body)}


def replay_exchange_envelope(serialized: str, *, expected_digest: str | None = None) -> dict:
    """Authenticate envelope structure/digest and reconstruct its trait candidate."""
    try:
        payload = json.loads(serialized)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("malformed exchange envelope") from exc
    if not isinstance(payload, dict) or payload.get("schema") != _SCHEMA:
        raise ValueError("unsupported exchange envelope schema")

    claimed = _digest(payload.get("envelope_digest"), "envelope digest")
    body = dict(payload)
    body.pop("envelope_digest", None)
    if _sha256(body) != claimed:
        raise ValueError("exchange envelope digest mismatch")
    if expected_digest is not None and claimed != _digest(expected_digest, "expected envelope digest"):
        raise ValueError("exchange envelope expected digest mismatch")

    candidate = _candidate_from_canonical(payload.get("candidate"))
    if candidate.digest() != _digest(payload.get("candidate_digest"), "candidate digest"):
        raise ValueError("exchange candidate digest mismatch")
    if _token(payload.get("claimed_sender_node"), "claimed sender") != candidate.canonical()["source_node"]:
        raise ValueError("exchange sender/source mismatch")
    _token(payload.get("receiver_node"), "receiver node")
    _token(payload.get("exchange_id"), "exchange id")
    _sequence(payload.get("sequence"))
    _digest(payload.get("source_lkg_digest"), "source LKG digest")

    zero_authority_fields = (
        "sender_identity_authenticated",
        "network_delivery_proven",
        "peer_liveness_proven",
        "live_multi_node_exchange_proven",
        "independent_node_recovery_proven",
        "grants_mutation_authority",
        "grants_promotion_authority",
        "infers_physical_proof",
    )
    if any(payload.get(field) is not False for field in zero_authority_fields):
        raise ValueError("software exchange envelope attempted to widen proof or authority")
    return payload


def serialize_exchange_envelope(envelope: Mapping[str, object]) -> str:
    replayed = replay_exchange_envelope(_stable_json(dict(envelope)))
    return _stable_json(replayed)


def evaluate_exchange_preflight(
    envelope: Mapping[str, object],
    *,
    expected_receiver_node: str,
    trusted_claimed_senders: frozenset[str],
    target_scope: TraitScope,
    receiver_lkg_digest: str,
    expected_parent_lineage: str | None = None,
) -> dict:
    """Evaluate what a receiver *could* accept if an authenticated transport later delivers it."""
    replayed = replay_exchange_envelope(_stable_json(dict(envelope)))
    candidate = _candidate_from_canonical(replayed["candidate"])
    receiver = _token(expected_receiver_node, "expected_receiver_node")
    reasons: list[str] = []

    if replayed["receiver_node"] != receiver:
        reasons.append("receiver-mismatch")
    if replayed["claimed_sender_node"] not in trusted_claimed_senders:
        reasons.append("untrusted-claimed-sender")

    context = ReceivingContext(
        node_id=receiver,
        trusted_nodes=trusted_claimed_senders,
        target_scope=target_scope,
        current_lkg_digest=receiver_lkg_digest,
        expected_parent_lineage=expected_parent_lineage,
    )
    trait_result = evaluate_trait(candidate, context)
    reasons.extend(reason for reason in trait_result["quarantine_reasons"] if reason not in reasons)
    accepted = not reasons and trait_result["accepted_as_evidence"] is True

    return {
        "state": "software-preflight-accepted" if accepted else "software-preflight-quarantined",
        "software_exchange_preflight": accepted,
        "quarantine_reasons": reasons,
        "envelope_digest": replayed["envelope_digest"],
        "candidate_digest": replayed["candidate_digest"],
        "trait_evaluation": trait_result,
        "sender_identity_authenticated": False,
        "network_delivery_proven": False,
        "peer_liveness_proven": False,
        "live_multi_node_exchange_proven": False,
        "independent_node_recovery_proven": False,
        "receiver_lkg_digest_before": _digest(receiver_lkg_digest, "receiver LKG digest"),
        "receiver_lkg_digest_after": _digest(receiver_lkg_digest, "receiver LKG digest"),
        "trust_widened": False,
        "grants_mutation_authority": False,
        "grants_promotion_authority": False,
        "infers_physical_proof": False,
    }


def gen3_live_exchange_preflight_gate(result: Mapping[str, object]) -> dict:
    """Expose software readiness while keeping the real live-exchange gate held."""
    return {
        "multi_node_exchange_software_preflight": result.get("software_exchange_preflight") is True,
        "live_multi_node_exchange": False,
        "authenticated_peer_identity": False,
        "network_delivery_proof": False,
        "independent_node_recovery": False,
        "lkg_mutated": False,
        "trust_widened": False,
        "grants_mutation_authority": False,
        "grants_promotion_authority": False,
        "infers_physical_proof": False,
    }
