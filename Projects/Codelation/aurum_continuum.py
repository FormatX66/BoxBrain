"""Aurum Continuum v0: carrier-independent, relation-first durable state.

The continuum is not organized as files, folders, tables, disks, or programs.
It is a set of immutable *impressions*.  Each impression contains meaning,
facets, and links to other impressions.  Identity is derived from canonical
content, so independently formed identical impressions converge naturally.

Files or network messages may carry an exported byte stream, but carrier
boundaries are not part of the logical model.  An exported stream can be split
at arbitrary byte positions, reordered at the impression level, merged with
another stream, or salvaged after localized corruption.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import struct
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from types import MappingProxyType
from typing import Any, Final

STREAM_MAGIC: Final[bytes] = b"AURUM-CONTINUUM\x00\x00"
FRAME_SYNC: Final[bytes] = b"\xa7AURC0\x1e\x9d"
IDENTITY_BYTES: Final[int] = 32
MAX_FRAME_BYTES: Final[int] = 16 * 1024 * 1024
MAX_U64: Final[int] = (1 << 64) - 1
_PERSON: Final[bytes] = b"AurumContinuum0"


class ContinuumError(ValueError):
    """Base error for invalid continuum state or carrier data."""


class CanonicalValueError(ContinuumError):
    """Raised when a value has no canonical v0 representation."""


class CarrierCorruption(ContinuumError):
    """Raised when strict carrier decoding encounters damaged data."""


class IdentityCollision(ContinuumError):
    """Raised if one identity is associated with different canonical bodies."""


@dataclass(frozen=True, slots=True)
class Impression:
    """One immutable meaning-bearing unit in a continuum."""

    identity: bytes
    kind: str
    essence: Any
    facets: Mapping[str, Any]
    links: tuple[bytes, ...]

    @property
    def token(self) -> str:
        """Return a stable compact human projection of the binary identity."""
        return "ac0:" + self.identity.hex()


@dataclass(frozen=True, slots=True)
class ImportReport:
    """Evidence produced while reconstructing a continuum from a carrier."""

    accepted: int
    duplicates: int
    rejected: int
    skipped_bytes: int
    trailing_bytes: int

    @property
    def clean(self) -> bool:
        return self.rejected == 0 and self.skipped_bytes == 0 and self.trailing_bytes == 0


def _normal_text(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _encode_uvarint(value: int) -> bytes:
    if value < 0:
        raise CanonicalValueError("unsigned varint cannot encode a negative value")
    if value > MAX_U64:
        raise CanonicalValueError("unsigned varint exceeds the v0 64-bit bound")
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _read_uvarint(data: bytes, offset: int, *, limit: int | None = None) -> tuple[int, int]:
    end = len(data) if limit is None else min(len(data), limit)
    value = 0
    cursor = offset
    for group in range(10):
        if cursor >= end:
            raise CarrierCorruption("truncated varint")
        byte = data[cursor]
        cursor += 1
        if group == 9 and byte > 1:
            raise CarrierCorruption("varint exceeds the v0 64-bit bound")
        value |= (byte & 0x7F) << (group * 7)
        if byte < 0x80:
            if group > 0 and byte == 0:
                raise CarrierCorruption("varint is not minimally encoded")
            return value, cursor
    raise CarrierCorruption("oversized varint")


def _encode_text(value: str) -> bytes:
    raw = _normal_text(value).encode("utf-8")
    return _encode_uvarint(len(raw)) + raw


def _read_text(data: bytes, offset: int, limit: int) -> tuple[str, int]:
    size, cursor = _read_uvarint(data, offset, limit=limit)
    end = cursor + size
    if end > limit:
        raise CarrierCorruption("truncated text")
    try:
        value = data[cursor:end].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CarrierCorruption("invalid UTF-8") from exc
    normalized = _normal_text(value)
    if value != normalized:
        raise CarrierCorruption("non-canonical Unicode")
    return value, end


def encode_value(value: Any) -> bytes:
    """Encode a supported Python value into the canonical ACV0 value form."""
    if value is None:
        return b"\x00"
    if value is False:
        return b"\x01"
    if value is True:
        return b"\x02"
    if isinstance(value, int):
        if value < -(1 << 63) or value > (1 << 63) - 1:
            raise CanonicalValueError("integer exceeds the v0 signed 64-bit bound")
        zigzag = value * 2 if value >= 0 else (-value * 2) - 1
        return b"\x10" + _encode_uvarint(zigzag)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalValueError("NaN and infinity are not canonical values")
        if value == 0.0:
            value = 0.0
        return b"\x11" + struct.pack(">d", value)
    if isinstance(value, bytes):
        return b"\x20" + _encode_uvarint(len(value)) + value
    if isinstance(value, str):
        return b"\x21" + _encode_text(value)
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                raise CanonicalValueError("continuum map keys must be text")
            key = _normal_text(raw_key)
            if key in normalized:
                raise CanonicalValueError("map keys collide after Unicode normalization")
            normalized[key] = item
        out = bytearray(b"\x31")
        keys = sorted(normalized, key=lambda item: item.encode("utf-8"))
        out += _encode_uvarint(len(keys))
        for key in keys:
            out += _encode_text(key)
            out += encode_value(normalized[key])
        return bytes(out)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        out = bytearray(b"\x30")
        out += _encode_uvarint(len(value))
        for item in value:
            out += encode_value(item)
        return bytes(out)
    raise CanonicalValueError(f"unsupported canonical value: {type(value).__name__}")


def _decode_value(data: bytes, offset: int, limit: int) -> tuple[Any, int]:
    if offset >= limit:
        raise CarrierCorruption("truncated value")
    tag = data[offset]
    cursor = offset + 1
    if tag == 0x00:
        return None, cursor
    if tag == 0x01:
        return False, cursor
    if tag == 0x02:
        return True, cursor
    if tag == 0x10:
        zigzag, cursor = _read_uvarint(data, cursor, limit=limit)
        value = zigzag // 2 if zigzag % 2 == 0 else -((zigzag // 2) + 1)
        return value, cursor
    if tag == 0x11:
        end = cursor + 8
        if end > limit:
            raise CarrierCorruption("truncated float")
        value = struct.unpack(">d", data[cursor:end])[0]
        if not math.isfinite(value) or struct.pack(">d", 0.0 if value == 0.0 else value) != data[cursor:end]:
            raise CarrierCorruption("non-canonical float")
        return value, end
    if tag == 0x20:
        size, cursor = _read_uvarint(data, cursor, limit=limit)
        end = cursor + size
        if end > limit:
            raise CarrierCorruption("truncated bytes")
        return data[cursor:end], end
    if tag == 0x21:
        return _read_text(data, cursor, limit)
    if tag == 0x30:
        count, cursor = _read_uvarint(data, cursor, limit=limit)
        if count > limit - cursor:
            raise CarrierCorruption("sequence count exceeds available canonical values")
        values: list[Any] = []
        for _ in range(count):
            item, cursor = _decode_value(data, cursor, limit)
            values.append(item)
        return tuple(values), cursor
    if tag == 0x31:
        count, cursor = _read_uvarint(data, cursor, limit=limit)
        if count > (limit - cursor) // 2:
            raise CarrierCorruption("map count exceeds available key-value pairs")
        result: dict[str, Any] = {}
        previous_key: bytes | None = None
        for _ in range(count):
            key, cursor = _read_text(data, cursor, limit)
            key_bytes = key.encode("utf-8")
            if previous_key is not None and key_bytes <= previous_key:
                raise CarrierCorruption("map keys are not in canonical order")
            previous_key = key_bytes
            item, cursor = _decode_value(data, cursor, limit)
            result[key] = item
        return result, cursor
    raise CarrierCorruption(f"unknown canonical value tag 0x{tag:02x}")


def _canonical_body(kind: str, essence: Any, facets: Mapping[str, Any], links: Iterable[bytes]) -> bytes:
    normalized_kind = _normal_text(kind)
    if not normalized_kind:
        raise CanonicalValueError("impression kind cannot be empty")
    canonical_links = sorted(set(links))
    for link in canonical_links:
        if not isinstance(link, bytes) or len(link) != IDENTITY_BYTES:
            raise CanonicalValueError("links must be 32-byte continuum identities")
    out = bytearray()
    out += _encode_uvarint(0)
    out += _encode_text(normalized_kind)
    out += encode_value(essence)
    out += encode_value(dict(facets))
    out += _encode_uvarint(len(canonical_links))
    for link in canonical_links:
        out += link
    return bytes(out)


def _identity(body: bytes) -> bytes:
    return hashlib.blake2b(body, digest_size=IDENTITY_BYTES, person=_PERSON).digest()


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _decode_body(body: bytes, identity: bytes) -> Impression:
    version, cursor = _read_uvarint(body, 0, limit=len(body))
    if version != 0:
        raise CarrierCorruption(f"unsupported impression version {version}")
    kind, cursor = _read_text(body, cursor, len(body))
    essence, cursor = _decode_value(body, cursor, len(body))
    facets, cursor = _decode_value(body, cursor, len(body))
    if not isinstance(facets, dict):
        raise CarrierCorruption("impression facets are not a map")
    link_count, cursor = _read_uvarint(body, cursor, limit=len(body))
    if link_count > (len(body) - cursor) // IDENTITY_BYTES:
        raise CarrierCorruption("link count exceeds available identities")
    links: list[bytes] = []
    previous: bytes | None = None
    for _ in range(link_count):
        end = cursor + IDENTITY_BYTES
        if end > len(body):
            raise CarrierCorruption("truncated link identity")
        link = body[cursor:end]
        if previous is not None and link <= previous:
            raise CarrierCorruption("links are not in canonical order")
        links.append(link)
        previous = link
        cursor = end
    if cursor != len(body):
        raise CarrierCorruption("trailing bytes inside impression")
    return Impression(
        identity=identity,
        kind=kind,
        essence=_freeze(essence),
        facets=_freeze(facets),
        links=tuple(links),
    )


class Continuum:
    """A convergent collection of immutable impressions.

    The internal dictionary is only a runtime acceleration structure.  The
    identity and relation model does not expose paths, sectors, partitions,
    tables, or ownership by a compartmental program.
    """

    def __init__(self) -> None:
        self._bodies: dict[bytes, bytes] = {}

    def __len__(self) -> int:
        return len(self._bodies)

    def __contains__(self, identity: bytes) -> bool:
        return identity in self._bodies

    @property
    def identities(self) -> tuple[bytes, ...]:
        return tuple(sorted(self._bodies))

    @property
    def root_digest(self) -> bytes:
        """Return an order-independent identity for the complete continuum."""
        digest = hashlib.blake2b(digest_size=IDENTITY_BYTES, person=b"AurumContinuumR")
        for identity in sorted(self._bodies):
            digest.update(identity)
        return digest.digest()

    @property
    def root_token(self) -> str:
        return "acr0:" + self.root_digest.hex()

    def remember(
        self,
        kind: str,
        essence: Any,
        *,
        facets: Mapping[str, Any] | None = None,
        links: Iterable[bytes] = (),
    ) -> Impression:
        """Converge an impression into the continuum and return it."""
        body = _canonical_body(kind, essence, facets or {}, links)
        identity = _identity(body)
        existing = self._bodies.get(identity)
        if existing is not None and existing != body:
            raise IdentityCollision("one identity resolved to different canonical bodies")
        self._bodies[identity] = body
        return _decode_body(body, identity)

    def resolve(self, identity: bytes) -> Impression:
        try:
            body = self._bodies[identity]
        except KeyError as exc:
            raise KeyError("continuum identity is not present") from exc
        return _decode_body(body, identity)

    def select(
        self,
        *,
        kind: str | None = None,
        facets: Mapping[str, Any] | None = None,
        linked_to: bytes | None = None,
    ) -> tuple[Impression, ...]:
        """Project impressions matching meaning, facets, or a relation."""
        normalized_kind = _normal_text(kind) if kind is not None else None
        expected_facets = dict(facets or {})
        found: list[Impression] = []
        for identity in sorted(self._bodies):
            impression = self.resolve(identity)
            if normalized_kind is not None and impression.kind != normalized_kind:
                continue
            if linked_to is not None and linked_to not in impression.links:
                continue
            if any(impression.facets.get(key) != value for key, value in expected_facets.items()):
                continue
            found.append(impression)
        return tuple(found)

    def closure(self, roots: Iterable[bytes]) -> tuple[Impression, ...]:
        """Project the reachable meaning from roots through their links."""
        pending = list(roots)
        seen: set[bytes] = set()
        while pending:
            identity = pending.pop()
            if identity in seen or identity not in self._bodies:
                continue
            seen.add(identity)
            pending.extend(self.resolve(identity).links)
        return tuple(self.resolve(identity) for identity in sorted(seen))

    def merge(self, other: "Continuum") -> int:
        """Converge another continuum by set union; return new impressions."""
        added = 0
        for identity, body in other._bodies.items():
            existing = self._bodies.get(identity)
            if existing is not None:
                if existing != body:
                    raise IdentityCollision("merge found one identity with different bodies")
                continue
            self._bodies[identity] = body
            added += 1
        return added

    def export(self, *, reverse: bool = False) -> bytes:
        """Project the continuum into a deterministic independent-frame carrier."""
        output = bytearray(STREAM_MAGIC)
        for identity in sorted(self._bodies, reverse=reverse):
            body = self._bodies[identity]
            output += FRAME_SYNC
            output += _encode_uvarint(len(body))
            output += body
            output += identity
        return bytes(output)

    @classmethod
    def import_chunks(
        cls,
        chunks: Iterable[bytes],
        *,
        salvage: bool = False,
    ) -> tuple["Continuum", ImportReport]:
        """Reconstruct from arbitrary carrier chunks.

        Chunk boundaries may occur anywhere.  In salvage mode, invalid frames
        are rejected and scanning resumes at the next independently verifiable
        frame.  Strict mode fails on the first inconsistency.
        """
        carrier = b"".join(bytes(chunk) for chunk in chunks)
        continuum = cls()
        accepted = duplicates = rejected = skipped = 0
        if not carrier.startswith(STREAM_MAGIC):
            if not salvage:
                raise CarrierCorruption("continuum stream magic is absent")
            first = carrier.find(FRAME_SYNC)
            if first < 0:
                return continuum, ImportReport(0, 0, 1, len(carrier), 0)
            skipped += first
            cursor = first
        else:
            cursor = len(STREAM_MAGIC)

        while cursor < len(carrier):
            if not carrier.startswith(FRAME_SYNC, cursor):
                next_sync = carrier.find(FRAME_SYNC, cursor + 1)
                if next_sync < 0:
                    trailing = len(carrier) - cursor
                    if not salvage and trailing:
                        raise CarrierCorruption("trailing carrier bytes")
                    return continuum, ImportReport(accepted, duplicates, rejected, skipped, trailing)
                if not salvage:
                    raise CarrierCorruption("unexpected bytes between frames")
                skipped += next_sync - cursor
                rejected += 1
                cursor = next_sync
                continue

            frame_start = cursor
            cursor += len(FRAME_SYNC)
            try:
                body_size, body_start = _read_uvarint(carrier, cursor)
                if body_size > MAX_FRAME_BYTES:
                    raise CarrierCorruption("frame exceeds the v0 safety bound")
                body_end = body_start + body_size
                identity_end = body_end + IDENTITY_BYTES
                if identity_end > len(carrier):
                    raise CarrierCorruption("truncated frame")
                body = carrier[body_start:body_end]
                identity = carrier[body_end:identity_end]
                if _identity(body) != identity:
                    raise CarrierCorruption("impression identity does not match its body")
                _decode_body(body, identity)
                existing = continuum._bodies.get(identity)
                if existing is None:
                    continuum._bodies[identity] = body
                    accepted += 1
                elif existing == body:
                    duplicates += 1
                else:
                    raise IdentityCollision("carrier contains an identity collision")
                cursor = identity_end
            except (ContinuumError, OverflowError) as exc:
                if not salvage:
                    if isinstance(exc, CarrierCorruption):
                        raise
                    raise CarrierCorruption(str(exc)) from exc
                rejected += 1
                next_sync = carrier.find(FRAME_SYNC, frame_start + 1)
                if next_sync < 0:
                    trailing = len(carrier) - frame_start
                    return continuum, ImportReport(accepted, duplicates, rejected, skipped, trailing)
                skipped += next_sync - frame_start
                cursor = next_sync

        return continuum, ImportReport(accepted, duplicates, rejected, skipped, 0)


__all__ = [
    "CanonicalValueError",
    "CarrierCorruption",
    "Continuum",
    "ContinuumError",
    "IdentityCollision",
    "ImportReport",
    "Impression",
    "encode_value",
]
