from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from aurum_field import Field, encode


EVENT_TAG = b"AURUM-IO-EVENT-0\x00"
MAX_TRANSIENT_PAYLOAD = 16 * 1024 * 1024
MAX_INLINE_PAYLOAD = 64 * 1024


class IOEventError(ValueError):
    pass


@dataclass(frozen=True)
class PayloadDescriptor:
    digest: bytes
    size: int
    inline: bytes | None = None
    carrier: str | None = None


@dataclass(frozen=True)
class IOEvent:
    channel: str
    direction: str
    sequence: int
    monotonic_ns: int
    semantics: frozenset[str]
    permission: str
    provenance: tuple[str, ...]
    payload: PayloadDescriptor

    @property
    def identity(self) -> bytes:
        return event_identity(self)

    @property
    def hex_id(self) -> str:
        return self.identity.hex()


def describe_payload(
    payload: bytes,
    *,
    retain_inline: bool = False,
    carrier: str | None = None,
) -> PayloadDescriptor:
    raw = bytes(payload)
    if len(raw) > MAX_TRANSIENT_PAYLOAD:
        raise IOEventError("transient I/O payload exceeds the bounded event limit")
    inline = raw if retain_inline and len(raw) <= MAX_INLINE_PAYLOAD else None
    return PayloadDescriptor(
        digest=hashlib.blake2s(raw, digest_size=32).digest(),
        size=len(raw),
        inline=inline,
        carrier=carrier,
    )


def make_event(
    channel: str,
    direction: str,
    payload: bytes,
    *,
    sequence: int,
    monotonic_ns: int,
    semantics: Iterable[str] = (),
    permission: str = "none",
    provenance: Iterable[str] = (),
    retain_inline: bool = False,
    carrier: str | None = None,
) -> IOEvent:
    if not channel:
        raise IOEventError("channel must be non-empty")
    if direction not in {"in", "out", "duplex-observation"}:
        raise IOEventError("direction is not a supported I/O event direction")
    if sequence < 0 or monotonic_ns < 0:
        raise IOEventError("sequence and monotonic time must be non-negative")
    return IOEvent(
        channel=channel,
        direction=direction,
        sequence=sequence,
        monotonic_ns=monotonic_ns,
        semantics=frozenset(semantics),
        permission=permission,
        provenance=tuple(sorted(set(provenance))),
        payload=describe_payload(
            payload,
            retain_inline=retain_inline,
            carrier=carrier,
        ),
    )


def _semantic_value(event: IOEvent) -> dict[str, object]:
    return {
        "channel": event.channel,
        "direction": event.direction,
        "sequence": event.sequence,
        "monotonic_ns": event.monotonic_ns,
        "semantics": sorted(event.semantics),
        "permission": event.permission,
        "provenance": list(event.provenance),
        "payload_digest": event.payload.digest,
        "payload_size": event.payload.size,
    }


def event_identity(event: IOEvent) -> bytes:
    """Identity is independent of the carrier and of whether raw bytes were retained."""
    return hashlib.blake2s(
        EVENT_TAG + encode(_semantic_value(event)),
        digest_size=32,
    ).digest()


def event_field(events: Iterable[IOEvent]) -> Field:
    """Persist event meaning/provenance without durably embedding raw sensory bytes."""
    field = Field()
    refs = []
    for event in sorted(events, key=lambda item: (item.monotonic_ns, item.channel, item.sequence, item.identity)):
        refs.append(
            field.add(
                "fact",
                {
                    "io_event_id": event.identity,
                    **_semantic_value(event),
                    "payload_carrier": event.payload.carrier,
                    "raw_payload_persisted": False,
                },
            )
        )
    field.add("view", {"name": "aurum-io-events", "events": refs})
    return field


__all__ = [
    "EVENT_TAG",
    "IOEvent",
    "IOEventError",
    "MAX_INLINE_PAYLOAD",
    "MAX_TRANSIENT_PAYLOAD",
    "PayloadDescriptor",
    "describe_payload",
    "event_field",
    "event_identity",
    "make_event",
]
