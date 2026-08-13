from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping

from aurum_field import Field


PRESENCE_REVISION = "aurum-durable-carrier-presence-v0"


@dataclass(frozen=True)
class CarrierPresence:
    node: str
    carrier_sha256: str
    locator_kind: str
    locator_identity: str
    readback_sha256: str
    immutable: bool
    locally_owned_variant: bool = True
    shared_as_learning_only: bool = True


@dataclass(frozen=True)
class PresenceProof:
    identity: str
    valid: bool
    reason: str
    carrier_sha256: str
    locator_kind: str
    locator_identity: str


def presence_identity(presence: CarrierPresence) -> str:
    payload = {
        "revision": PRESENCE_REVISION,
        "node": presence.node,
        "carrier_sha256": presence.carrier_sha256,
        "locator_kind": presence.locator_kind,
        "locator_identity": presence.locator_identity,
        "readback_sha256": presence.readback_sha256,
        "immutable": presence.immutable,
        "locally_owned_variant": presence.locally_owned_variant,
        "shared_as_learning_only": presence.shared_as_learning_only,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.blake2s(b"AURUM-DURABLE-CARRIER-PRESENCE-0\x00" + raw).hexdigest()


def verify_presence(presence: CarrierPresence) -> PresenceProof:
    identity = presence_identity(presence)
    if not presence.node:
        return PresenceProof(identity, False, "node-missing", presence.carrier_sha256, presence.locator_kind, presence.locator_identity)
    if not presence.carrier_sha256 or len(presence.carrier_sha256) != 64:
        return PresenceProof(identity, False, "carrier-digest-invalid", presence.carrier_sha256, presence.locator_kind, presence.locator_identity)
    if not presence.locator_kind or not presence.locator_identity:
        return PresenceProof(identity, False, "durable-locator-missing", presence.carrier_sha256, presence.locator_kind, presence.locator_identity)
    if not presence.immutable:
        return PresenceProof(identity, False, "carrier-not-immutable", presence.carrier_sha256, presence.locator_kind, presence.locator_identity)
    if presence.readback_sha256 != presence.carrier_sha256:
        return PresenceProof(identity, False, "readback-digest-mismatch", presence.carrier_sha256, presence.locator_kind, presence.locator_identity)
    if not presence.locally_owned_variant:
        return PresenceProof(identity, False, "variant-not-locally-owned", presence.carrier_sha256, presence.locator_kind, presence.locator_identity)
    if not presence.shared_as_learning_only:
        return PresenceProof(identity, False, "implementation-sharing-not-allowed", presence.carrier_sha256, presence.locator_kind, presence.locator_identity)
    return PresenceProof(identity, True, "durable-carrier-readback-verified", presence.carrier_sha256, presence.locator_kind, presence.locator_identity)


def presence_field(presence: CarrierPresence, proof: PresenceProof) -> Field:
    field = Field()
    presence_ref = field.add(
        "fact",
        {
            "kind": "durable-local-carrier-presence",
            "revision": PRESENCE_REVISION,
            "node": presence.node,
            "carrier_sha256": presence.carrier_sha256,
            "locator_kind": presence.locator_kind,
            "locator_identity": presence.locator_identity,
            "readback_sha256": presence.readback_sha256,
            "immutable": presence.immutable,
            "locally_owned_variant": presence.locally_owned_variant,
            "shared_as_learning_only": presence.shared_as_learning_only,
        },
    )
    proof_ref = field.add(
        "fact",
        {
            "kind": "durable-local-carrier-presence-proof",
            "identity": proof.identity,
            "valid": proof.valid,
            "reason": proof.reason,
            "carrier_sha256": proof.carrier_sha256,
            "locator_kind": proof.locator_kind,
            "locator_identity": proof.locator_identity,
        },
    )
    field.add(
        "view",
        {
            "name": "aurum-durable-carrier-presence",
            "presence": presence_ref,
            "proof": proof_ref,
            "promotion_may_consume_only_valid_proof": True,
            "carrier_bytes_shared_to_other_nodes": False,
        },
    )
    return field


__all__ = [
    "CarrierPresence",
    "PRESENCE_REVISION",
    "PresenceProof",
    "presence_field",
    "presence_identity",
    "verify_presence",
]
