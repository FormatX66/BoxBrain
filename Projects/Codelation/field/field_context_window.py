from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from aurum_field import Field
from capacity_mesh import semantic_recall


CONTEXT_REVISION = "aurum-field-context-window-v0"


@dataclass(frozen=True)
class FieldContextWindow:
    identity: str
    query: str
    source_field_id: str
    context_field_id: str
    selected_grains: int
    source_grains: int
    carrier_bytes: int
    full_carrier_bytes: int
    carrier: bytes

    @property
    def saved_bytes(self) -> int:
        return max(0, self.full_carrier_bytes - self.carrier_bytes)

    @property
    def saved_ratio(self) -> float:
        if self.full_carrier_bytes == 0:
            return 0.0
        return self.saved_bytes / self.full_carrier_bytes


def _closure(source: Field, identities: Iterable[bytes]) -> tuple[bytes, ...]:
    needed = set(identities)
    pending = list(identities)
    while pending:
        identity = pending.pop()
        grain = source.get(identity)
        for ref in source.refs_in(grain):
            if ref.identity not in needed:
                needed.add(ref.identity)
                pending.append(ref.identity)
    return tuple(sorted(needed))


def _subset(source: Field, identities: Iterable[bytes]) -> Field:
    return Field(source.get(identity) for identity in identities)


def select_field_context(
    source: Field,
    query: str,
    *,
    recall_limit: int = 32,
    max_bytes: int = 64 * 1024,
) -> FieldContextWindow:
    """Project only gap-relevant Field grains plus reference closure.

    Selection is deterministic and read-only. Candidates are admitted in semantic
    recall order only while the closed projection remains inside max_bytes.
    """
    if recall_limit <= 0:
        raise ValueError("recall_limit must be positive")
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if source.missing_refs():
        raise ValueError("source Field must be reference-closed")

    recalled = semantic_recall(source, query, limit=recall_limit)
    chosen: set[bytes] = set()

    for grain in recalled:
        proposed = _closure(source, tuple(chosen | {grain.identity}))
        candidate = _subset(source, proposed)
        if len(candidate.project()) <= max_bytes:
            chosen = set(proposed)

    context = _subset(source, sorted(chosen))
    carrier = context.project() if chosen else b""
    full_bytes = len(source.project())
    h = hashlib.blake2s(digest_size=32)
    h.update(b"AURUM-FIELD-CONTEXT-0\x00")
    h.update(source.hex_id.encode("ascii"))
    h.update(query.casefold().encode("utf-8"))
    h.update(str(recall_limit).encode("ascii"))
    h.update(str(max_bytes).encode("ascii"))
    h.update(context.hex_id.encode("ascii"))

    return FieldContextWindow(
        identity=h.hexdigest(),
        query=query,
        source_field_id=source.hex_id,
        context_field_id=context.hex_id,
        selected_grains=len(context),
        source_grains=len(source),
        carrier_bytes=len(carrier),
        full_carrier_bytes=full_bytes,
        carrier=carrier,
    )


__all__ = [
    "CONTEXT_REVISION",
    "FieldContextWindow",
    "select_field_context",
]
