"""Deterministic Gen3 cross-node evidence receipts for Aurum Future Branch.

This module closes the software-only evidence-merge gap without claiming that
any network exchange, physical node, recovery path, promotion, or LKG mutation
has been proven.  It consumes already-scoped trait candidates, applies the
existing fail-closed cross-node merge rules, and emits a tamper-evident receipt
that can be replayed by CI and downstream preparation lanes.
"""
from __future__ import annotations

import hashlib
import json
from typing import Iterable, Mapping

from scoped_trait_inheritance import TraitCandidate, merge_cross_node_evidence


_SCHEMA = "aurum-cross-node-evidence-receipt-v1"


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


def build_cross_node_evidence_receipt(
    candidates: Iterable[TraitCandidate], *, trusted_nodes: frozenset[str]
) -> dict:
    """Merge scoped trait evidence and emit a zero-authority software receipt.

    A successful receipt requires at least two distinct trusted source nodes,
    an identity-compatible merge, and no safety veto.  Anything else is retained
    as explicit quarantine evidence rather than silently discarded.
    """
    items = list(candidates)
    if not items:
        raise ValueError("at least one trait candidate is required")

    canonical = [item.canonical() for item in items]
    source_nodes = sorted({item["source_node"] for item in canonical})
    trusted = sorted({_token(node, "trusted node") for node in trusted_nodes})
    untrusted = sorted(set(source_nodes) - set(trusted))
    candidate_digests = sorted(item.digest() for item in items)
    merge = merge_cross_node_evidence(items)

    if untrusted:
        state = "quarantined-untrusted-source"
        cross_node_verified = False
    elif not merge.get("merged", False):
        state = str(merge.get("state", "quarantined-merge-failure"))
        cross_node_verified = False
    elif merge.get("safety_veto", False):
        state = "merged-evidence-vetoed"
        cross_node_verified = False
    elif len(source_nodes) < 2:
        state = "single-node-evidence"
        cross_node_verified = False
    else:
        state = "verified-cross-node-evidence"
        cross_node_verified = True

    merged_evidence = merge.get("evidence", []) if isinstance(merge, dict) else []
    body = {
        "schema": _SCHEMA,
        "state": state,
        "candidate_digests": candidate_digests,
        "source_nodes": source_nodes,
        "trusted_nodes": trusted,
        "untrusted_sources": untrusted,
        "merge_result": merge,
        "merged_evidence_digests": sorted(
            {
                _digest(item["digest"], "merged evidence digest")
                for item in merged_evidence
                if isinstance(item, dict) and "digest" in item
            }
        ),
        "cross_node_evidence_merge": cross_node_verified,
        "multi_node_live_exchange_proven": False,
        "independent_node_recovery_proven": False,
        "lkg_mutated": False,
        "trust_widened": False,
        "grants_mutation_authority": False,
        "grants_promotion_authority": False,
        "infers_physical_proof": False,
    }
    return {**body, "receipt_digest": _sha256(body)}


def replay_cross_node_evidence_receipt(
    serialized: str, *, expected_digest: str | None = None
) -> dict:
    """Replay and authenticate a receipt without turning it into authority."""
    try:
        payload = json.loads(serialized)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("malformed cross-node evidence receipt") from exc
    if not isinstance(payload, dict) or payload.get("schema") != _SCHEMA:
        raise ValueError("unsupported cross-node evidence receipt schema")

    required = {
        "schema",
        "state",
        "candidate_digests",
        "source_nodes",
        "trusted_nodes",
        "untrusted_sources",
        "merge_result",
        "merged_evidence_digests",
        "cross_node_evidence_merge",
        "multi_node_live_exchange_proven",
        "independent_node_recovery_proven",
        "lkg_mutated",
        "trust_widened",
        "grants_mutation_authority",
        "grants_promotion_authority",
        "infers_physical_proof",
        "receipt_digest",
    }
    if set(payload) != required:
        raise ValueError("cross-node evidence receipt fields mismatch")

    claimed = _digest(payload["receipt_digest"], "receipt digest")
    body = dict(payload)
    body.pop("receipt_digest")
    if _sha256(body) != claimed:
        raise ValueError("cross-node evidence receipt digest mismatch")
    if expected_digest is not None and claimed != _digest(expected_digest, "expected receipt digest"):
        raise ValueError("cross-node evidence receipt expected digest mismatch")

    for field in ("candidate_digests", "merged_evidence_digests"):
        values = payload[field]
        if not isinstance(values, list):
            raise ValueError(f"{field} must be a list")
        normalized = sorted({_digest(item, field) for item in values})
        if values != normalized:
            raise ValueError(f"{field} must be canonical")
    for field in ("source_nodes", "trusted_nodes", "untrusted_sources"):
        values = payload[field]
        if not isinstance(values, list):
            raise ValueError(f"{field} must be a list")
        normalized = sorted({_token(item, field) for item in values})
        if values != normalized:
            raise ValueError(f"{field} must be canonical")

    zero_authority = (
        payload["lkg_mutated"] is False
        and payload["trust_widened"] is False
        and payload["grants_mutation_authority"] is False
        and payload["grants_promotion_authority"] is False
        and payload["infers_physical_proof"] is False
    )
    if not zero_authority:
        raise ValueError("cross-node evidence receipt attempted to widen authority")
    if payload["multi_node_live_exchange_proven"] is not False:
        raise ValueError("software receipt cannot prove live multi-node exchange")
    if payload["independent_node_recovery_proven"] is not False:
        raise ValueError("software receipt cannot prove independent-node recovery")
    if payload["cross_node_evidence_merge"] is True:
        if payload["state"] != "verified-cross-node-evidence":
            raise ValueError("verified merge state mismatch")
        if len(payload["source_nodes"]) < 2 or payload["untrusted_sources"]:
            raise ValueError("verified merge requires two trusted source nodes")
        if not isinstance(payload["merge_result"], Mapping) or not payload["merge_result"].get("merged"):
            raise ValueError("verified merge lacks merge evidence")
        if payload["merge_result"].get("safety_veto"):
            raise ValueError("verified merge cannot contain a safety veto")

    return payload


def serialize_cross_node_evidence_receipt(receipt: Mapping[str, object]) -> str:
    replayed = replay_cross_node_evidence_receipt(_stable_json(dict(receipt)))
    return _stable_json(replayed)


def gen3_cross_node_evidence_gate(receipt: Mapping[str, object]) -> dict:
    """Project the receipt into the Gen3 ladder while keeping physical gates held."""
    replayed = replay_cross_node_evidence_receipt(_stable_json(dict(receipt)))
    verified = replayed["cross_node_evidence_merge"] is True
    return {
        "cross_node_evidence_merge": verified,
        "receipt_replay_verified": True,
        "multi_node_live_exchange": False,
        "independent_node_recovery": False,
        "lkg_mutated": False,
        "trust_widened": False,
        "grants_mutation_authority": False,
        "grants_promotion_authority": False,
        "infers_physical_proof": False,
    }
