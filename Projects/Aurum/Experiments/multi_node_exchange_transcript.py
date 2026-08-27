"""Software-only receipt chain for Aurum Gen3 multi-node exchange preparation.

The transcript preserves deterministic provenance, sequencing, quarantine outcomes,
and LKG non-mutation while Future Branch prepares the live multi-node lane.  It is
not transport evidence and it does not authenticate a peer, prove liveness, mutate
LKG, widen trust, or grant promotion/mutation authority.
"""
from __future__ import annotations

import hashlib
import json
from typing import Iterable, Mapping

from multi_node_exchange_preflight import replay_exchange_envelope


_SCHEMA = "aurum-gen3-exchange-receipt-v1"


def _stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _token(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _digest(value: object, name: str) -> str:
    digest = _token(value, name).lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return digest


def _sequence(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("sequence must be a non-negative integer")
    return value


def _decision(preflight_result: Mapping[str, object]) -> tuple[str, bool]:
    state = preflight_result.get("state")
    accepted = preflight_result.get("software_exchange_preflight")
    if state == "software-preflight-accepted" and accepted is True:
        return state, True
    if state == "software-preflight-quarantined" and accepted is False:
        return state, False
    raise ValueError("preflight result has inconsistent state")


def _require_zero_authority(preflight_result: Mapping[str, object]) -> None:
    must_be_false = (
        "sender_identity_authenticated",
        "network_delivery_proven",
        "peer_liveness_proven",
        "live_multi_node_exchange_proven",
        "independent_node_recovery_proven",
        "trust_widened",
        "grants_mutation_authority",
        "grants_promotion_authority",
        "infers_physical_proof",
    )
    if any(preflight_result.get(field) is not False for field in must_be_false):
        raise ValueError("preflight result attempted to widen proof or authority")


def build_exchange_receipt(
    envelope: Mapping[str, object],
    preflight_result: Mapping[str, object],
    *,
    previous_receipt_digest: str | None = None,
) -> dict:
    """Bind one replay-verified envelope to a receiver decision without authority."""
    replayed = replay_exchange_envelope(_stable_json(dict(envelope)))
    state, accepted = _decision(preflight_result)
    _require_zero_authority(preflight_result)

    envelope_digest = _digest(preflight_result.get("envelope_digest"), "preflight envelope digest")
    candidate_digest = _digest(preflight_result.get("candidate_digest"), "preflight candidate digest")
    if envelope_digest != replayed["envelope_digest"]:
        raise ValueError("preflight/envelope digest mismatch")
    if candidate_digest != replayed["candidate_digest"]:
        raise ValueError("preflight/candidate digest mismatch")

    lkg_before = _digest(preflight_result.get("receiver_lkg_digest_before"), "receiver LKG before")
    lkg_after = _digest(preflight_result.get("receiver_lkg_digest_after"), "receiver LKG after")
    if lkg_before != lkg_after:
        raise ValueError("software receipt cannot record LKG mutation")

    previous = None if previous_receipt_digest is None else _digest(
        previous_receipt_digest, "previous receipt digest"
    )
    body = {
        "schema": _SCHEMA,
        "exchange_id": _token(replayed.get("exchange_id"), "exchange id"),
        "sequence": _sequence(replayed.get("sequence")),
        "claimed_sender_node": _token(replayed.get("claimed_sender_node"), "claimed sender node"),
        "receiver_node": _token(replayed.get("receiver_node"), "receiver node"),
        "envelope_digest": replayed["envelope_digest"],
        "candidate_digest": replayed["candidate_digest"],
        "decision_state": state,
        "accepted_as_software_evidence": accepted,
        "quarantine_reasons": list(preflight_result.get("quarantine_reasons", [])),
        "receiver_lkg_digest_before": lkg_before,
        "receiver_lkg_digest_after": lkg_after,
        "previous_receipt_digest": previous,
        "sender_identity_authenticated": False,
        "network_delivery_proven": False,
        "peer_liveness_proven": False,
        "live_multi_node_exchange_proven": False,
        "independent_node_recovery_proven": False,
        "trust_widened": False,
        "grants_mutation_authority": False,
        "grants_promotion_authority": False,
        "infers_physical_proof": False,
    }
    return {**body, "receipt_digest": _sha256(body)}


def verify_exchange_transcript(receipts: Iterable[Mapping[str, object]]) -> dict:
    """Verify receipt integrity, chain continuity, and strict per-session sequencing."""
    items = [dict(item) for item in receipts]
    if not items:
        raise ValueError("exchange transcript requires at least one receipt")

    exchange_id: str | None = None
    sender: str | None = None
    receiver: str | None = None
    previous_digest: str | None = None
    previous_sequence: int | None = None
    accepted = 0
    quarantined = 0

    zero_authority_fields = (
        "sender_identity_authenticated",
        "network_delivery_proven",
        "peer_liveness_proven",
        "live_multi_node_exchange_proven",
        "independent_node_recovery_proven",
        "trust_widened",
        "grants_mutation_authority",
        "grants_promotion_authority",
        "infers_physical_proof",
    )

    for item in items:
        if item.get("schema") != _SCHEMA:
            raise ValueError("unsupported exchange receipt schema")
        claimed_digest = _digest(item.get("receipt_digest"), "receipt digest")
        body = dict(item)
        body.pop("receipt_digest", None)
        if _sha256(body) != claimed_digest:
            raise ValueError("exchange receipt digest mismatch")
        if any(item.get(field) is not False for field in zero_authority_fields):
            raise ValueError("exchange receipt attempted to widen proof or authority")

        item_exchange_id = _token(item.get("exchange_id"), "exchange id")
        item_sender = _token(item.get("claimed_sender_node"), "claimed sender node")
        item_receiver = _token(item.get("receiver_node"), "receiver node")
        sequence = _sequence(item.get("sequence"))
        _digest(item.get("envelope_digest"), "envelope digest")
        _digest(item.get("candidate_digest"), "candidate digest")
        lkg_before = _digest(item.get("receiver_lkg_digest_before"), "receiver LKG before")
        lkg_after = _digest(item.get("receiver_lkg_digest_after"), "receiver LKG after")
        if lkg_before != lkg_after:
            raise ValueError("exchange receipt records LKG mutation")

        if exchange_id is None:
            exchange_id, sender, receiver = item_exchange_id, item_sender, item_receiver
        elif (item_exchange_id, item_sender, item_receiver) != (exchange_id, sender, receiver):
            raise ValueError("exchange transcript mixed session or node identity")

        recorded_previous = item.get("previous_receipt_digest")
        if previous_digest is None:
            if recorded_previous is not None:
                raise ValueError("first receipt must not claim a previous receipt")
        elif _digest(recorded_previous, "previous receipt digest") != previous_digest:
            raise ValueError("exchange receipt chain mismatch")

        if previous_sequence is not None and sequence != previous_sequence + 1:
            raise ValueError("exchange transcript sequence must be contiguous")

        decision_state = item.get("decision_state")
        accepted_flag = item.get("accepted_as_software_evidence")
        if decision_state == "software-preflight-accepted" and accepted_flag is True:
            accepted += 1
        elif decision_state == "software-preflight-quarantined" and accepted_flag is False:
            quarantined += 1
        else:
            raise ValueError("exchange receipt has inconsistent decision state")

        previous_digest = claimed_digest
        previous_sequence = sequence

    return {
        "state": "software-transcript-verified",
        "exchange_id": exchange_id,
        "claimed_sender_node": sender,
        "receiver_node": receiver,
        "receipt_count": len(items),
        "accepted_receipts": accepted,
        "quarantined_receipts": quarantined,
        "first_sequence": _sequence(items[0]["sequence"]),
        "last_sequence": _sequence(items[-1]["sequence"]),
        "terminal_receipt_digest": previous_digest,
        "transcript_integrity_verified": True,
        "sequence_continuity_verified": True,
        "lkg_preserved": True,
        "sender_identity_authenticated": False,
        "network_delivery_proven": False,
        "peer_liveness_proven": False,
        "live_multi_node_exchange_proven": False,
        "independent_node_recovery_proven": False,
        "trust_widened": False,
        "grants_mutation_authority": False,
        "grants_promotion_authority": False,
        "infers_physical_proof": False,
    }


def append_exchange_receipt(
    receipts: Iterable[Mapping[str, object]],
    envelope: Mapping[str, object],
    preflight_result: Mapping[str, object],
) -> list[dict]:
    """Append only if the new receipt continues the same session and sequence."""
    items = [dict(item) for item in receipts]
    previous_digest: str | None = None
    expected_sequence: int | None = None
    expected_identity: tuple[str, str, str] | None = None

    if items:
        summary = verify_exchange_transcript(items)
        previous_digest = _digest(summary["terminal_receipt_digest"], "terminal receipt digest")
        expected_sequence = int(summary["last_sequence"]) + 1
        expected_identity = (
            _token(summary["exchange_id"], "exchange id"),
            _token(summary["claimed_sender_node"], "claimed sender node"),
            _token(summary["receiver_node"], "receiver node"),
        )

    receipt = build_exchange_receipt(
        envelope,
        preflight_result,
        previous_receipt_digest=previous_digest,
    )

    if expected_sequence is not None and receipt["sequence"] != expected_sequence:
        raise ValueError("new exchange receipt is duplicate, stale, or out of sequence")
    if expected_identity is not None:
        identity = (
            receipt["exchange_id"],
            receipt["claimed_sender_node"],
            receipt["receiver_node"],
        )
        if identity != expected_identity:
            raise ValueError("new exchange receipt belongs to a different session or node pair")

    result = items + [receipt]
    verify_exchange_transcript(result)
    return result


def gen3_live_exchange_transcript_gate(summary: Mapping[str, object]) -> dict:
    """Expose useful software preparation while holding all external Gen3 proof gates."""
    return {
        "exchange_transcript_software_preflight": (
            summary.get("transcript_integrity_verified") is True
            and summary.get("sequence_continuity_verified") is True
            and summary.get("lkg_preserved") is True
            and int(summary.get("receipt_count", 0)) > 0
        ),
        "live_multi_node_exchange": False,
        "authenticated_peer_identity": False,
        "network_delivery_proof": False,
        "peer_liveness_proof": False,
        "independent_node_recovery": False,
        "lkg_mutated": False,
        "trust_widened": False,
        "grants_mutation_authority": False,
        "grants_promotion_authority": False,
        "infers_physical_proof": False,
    }
