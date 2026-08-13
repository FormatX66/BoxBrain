from __future__ import annotations

from dataclasses import dataclass
import hashlib

from aurum_field import Field
from field_context_window import FieldContextWindow, select_field_context
from field_reasoning_projection import ReasoningProjection, project_for_reasoning


PACKET_REVISION = "aurum-field-reasoning-packet-v0"


@dataclass(frozen=True)
class FieldReasoningPacket:
    identity: str
    query: str
    source_field_id: str
    context_field_id: str
    context_grains: int
    source_grains: int
    binary_context_bytes: int
    full_binary_bytes: int
    reasoning_utf8_bytes: int
    reasoning_projection_identity: str
    reasoning_text: str

    @property
    def binary_reduction_ratio(self) -> float:
        if self.full_binary_bytes == 0:
            return 0.0
        return 1.0 - (self.binary_context_bytes / self.full_binary_bytes)


def build_reasoning_packet(
    source: Field,
    query: str,
    *,
    recall_limit: int = 32,
    max_context_bytes: int = 64 * 1024,
) -> FieldReasoningPacket:
    """Select bounded semantic context and create its compact GPT-facing view."""
    window = select_field_context(
        source,
        query,
        recall_limit=recall_limit,
        max_bytes=max_context_bytes,
    )
    context = Field.absorb(window.carrier) if window.carrier else Field()
    projection = project_for_reasoning(context)

    h = hashlib.blake2s(digest_size=32)
    h.update(b"AURUM-FIELD-REASONING-PACKET-0\x00")
    h.update(window.identity.encode("ascii"))
    h.update(projection.identity.encode("ascii"))

    return FieldReasoningPacket(
        identity=h.hexdigest(),
        query=query,
        source_field_id=window.source_field_id,
        context_field_id=window.context_field_id,
        context_grains=window.selected_grains,
        source_grains=window.source_grains,
        binary_context_bytes=window.carrier_bytes,
        full_binary_bytes=window.full_carrier_bytes,
        reasoning_utf8_bytes=projection.utf8_bytes,
        reasoning_projection_identity=projection.identity,
        reasoning_text=projection.text,
    )


__all__ = [
    "FieldReasoningPacket",
    "PACKET_REVISION",
    "build_reasoning_packet",
]
