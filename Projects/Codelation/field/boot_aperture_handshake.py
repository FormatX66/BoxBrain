from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable

from aurum_field import Field
from boot_aperture import BootAperturePlan

HANDSHAKE_SCHEMA = "aurum.boot.handshake.v0"


@dataclass(frozen=True)
class BootRequest:
    target_identity: str
    observed_boot_tokens: tuple[str, ...]
    request_id: str


@dataclass(frozen=True)
class BootOffer:
    request_id: str
    aperture_identity: str
    carrier: str
    payload_digests: tuple[str, ...]
    offer_id: str


@dataclass(frozen=True)
class BootReceipt:
    offer_id: str
    target_identity: str
    observed_payload_digest: str
    accepted: bool
    receipt_id: str


def _digest(prefix: bytes, payload: dict[str, object], size: int = 32) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.blake2s(prefix + raw, digest_size=size).hexdigest()


def make_boot_request(target_identity: str, observed_boot_tokens: Iterable[str]) -> BootRequest:
    if not target_identity:
        raise ValueError("target identity is required")
    tokens = tuple(sorted(set(observed_boot_tokens)))
    payload = {
        "schema": HANDSHAKE_SCHEMA,
        "target_identity": target_identity,
        "observed_boot_tokens": list(tokens),
    }
    request_id = _digest(b"AURUM-BOOT-REQUEST-0\x00", payload)
    return BootRequest(target_identity, tokens, request_id)


def make_boot_offer(
    request: BootRequest,
    aperture: BootAperturePlan,
    payload_digests: Iterable[str],
) -> BootOffer:
    if request.target_identity != aperture.target_identity:
        raise ValueError("boot offer target does not match request")
    digests = tuple(sorted(set(payload_digests)))
    if not digests:
        raise ValueError("at least one content digest is required")
    for digest in digests:
        if len(digest) != 64:
            raise ValueError("boot payload digest must be 32-byte hex")
        bytes.fromhex(digest)
    payload = {
        "schema": HANDSHAKE_SCHEMA,
        "request_id": request.request_id,
        "aperture_identity": aperture.identity,
        "carrier": aperture.carrier,
        "payload_digests": list(digests),
    }
    offer_id = _digest(b"AURUM-BOOT-OFFER-0\x00", payload)
    return BootOffer(request.request_id, aperture.identity, aperture.carrier, digests, offer_id)


def make_boot_receipt(
    offer: BootOffer,
    target_identity: str,
    observed_payload_digest: str,
) -> BootReceipt:
    if observed_payload_digest not in offer.payload_digests:
        accepted = False
    else:
        accepted = True
    payload = {
        "schema": HANDSHAKE_SCHEMA,
        "offer_id": offer.offer_id,
        "target_identity": target_identity,
        "observed_payload_digest": observed_payload_digest,
        "accepted": accepted,
    }
    receipt_id = _digest(b"AURUM-BOOT-RECEIPT-0\x00", payload)
    return BootReceipt(
        offer_id=offer.offer_id,
        target_identity=target_identity,
        observed_payload_digest=observed_payload_digest,
        accepted=accepted,
        receipt_id=receipt_id,
    )


def boot_handshake_field(
    request: BootRequest,
    offer: BootOffer,
    receipt: BootReceipt | None = None,
) -> Field:
    field = Field()
    request_ref = field.add("fact", request.__dict__)
    offer_ref = field.add("relation", {"request": request_ref, **offer.__dict__})
    receipt_ref = None
    if receipt is not None:
        receipt_ref = field.add("relation", {"offer": offer_ref, **receipt.__dict__})
    field.add(
        "view",
        {
            "name": "aurum-boot-aperture-handshake",
            "request": request_ref,
            "offer": offer_ref,
            "receipt": receipt_ref,
            "protocol_is_not_os_owner": True,
        },
    )
    return field


__all__ = [
    "BootOffer",
    "BootReceipt",
    "BootRequest",
    "boot_handshake_field",
    "make_boot_offer",
    "make_boot_receipt",
    "make_boot_request",
]
