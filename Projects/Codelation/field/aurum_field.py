from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Iterable


SCHEMA_TAG = b"AURUM-FIELD-0\x00"
FIELD_TAG = b"AURUM-FIELD-ID-0\x00"
RECORD_MAGIC = b"AFG0"
RECORD_VERSION = 0
MAX_DEPTH = 64
MAX_VALUE_BYTES = 16 * 1024 * 1024
MAX_INTEGER_VARINT_BYTES = 512


class FieldError(ValueError):
    pass


@dataclass(frozen=True, order=True)
class Ref:
    identity: bytes

    def __post_init__(self) -> None:
        if len(self.identity) != 32:
            raise FieldError("reference identity must be 32 bytes")

    @classmethod
    def hex(cls, value: str) -> "Ref":
        raw = bytes.fromhex(value)
        return cls(raw)

    def __str__(self) -> str:
        return self.identity.hex()


@dataclass(frozen=True)
class Grain:
    kind: int
    value: Any
    body: bytes
    identity: bytes

    @property
    def hex_id(self) -> str:
        return self.identity.hex()


_KIND = {
    "fact": 1,
    "relation": 2,
    "capability": 3,
    "view": 4,
}
_KIND_NAME = {v: k for k, v in _KIND.items()}


def _uvarint(n: int) -> bytes:
    if n < 0:
        raise FieldError("uvarint cannot encode negative values")
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _read_uvarint(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    shift = 0
    for index in range(MAX_INTEGER_VARINT_BYTES):
        if pos >= len(data):
            raise FieldError("truncated varint")
        b = data[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        if not (b & 0x80):
            if index > 0 and b == 0:
                raise FieldError("non-canonical varint")
            return value, pos
        shift += 7
    raise FieldError("varint too long")


def _zigzag(n: int) -> int:
    return n * 2 if n >= 0 else (-n * 2) - 1


def _unzigzag(n: int) -> int:
    return n // 2 if n % 2 == 0 else -(n // 2) - 1


def encode(value: Any, _depth: int = 0) -> bytes:
    if _depth > MAX_DEPTH:
        raise FieldError("value nesting too deep")
    if value is None:
        return b"\x00"
    if value is False:
        return b"\x01"
    if value is True:
        return b"\x02"
    if isinstance(value, int) and not isinstance(value, bool):
        return b"\x03" + _uvarint(_zigzag(value))
    if isinstance(value, bytes):
        if len(value) > MAX_VALUE_BYTES:
            raise FieldError("byte value too large")
        return b"\x04" + _uvarint(len(value)) + value
    if isinstance(value, str):
        raw = value.encode("utf-8")
        if len(raw) > MAX_VALUE_BYTES:
            raise FieldError("text value too large")
        return b"\x05" + _uvarint(len(raw)) + raw
    if isinstance(value, Ref):
        return b"\x06" + value.identity
    if isinstance(value, (list, tuple)):
        parts = [b"\x07", _uvarint(len(value))]
        parts.extend(encode(item, _depth + 1) for item in value)
        return b"".join(parts)
    if isinstance(value, dict):
        encoded_items = []
        for key, item in value.items():
            key_bytes = encode(key, _depth + 1)
            val_bytes = encode(item, _depth + 1)
            encoded_items.append((key_bytes, val_bytes))
        encoded_items.sort(key=lambda pair: pair[0])
        for i in range(1, len(encoded_items)):
            if encoded_items[i - 1][0] == encoded_items[i][0]:
                raise FieldError("map contains canonically duplicate keys")
        parts = [b"\x08", _uvarint(len(encoded_items))]
        for key_bytes, val_bytes in encoded_items:
            parts.extend((key_bytes, val_bytes))
        return b"".join(parts)
    raise FieldError(f"unsupported field value type: {type(value).__name__}")


def _decode(data: bytes, pos: int = 0, depth: int = 0) -> tuple[Any, int]:
    if depth > MAX_DEPTH:
        raise FieldError("value nesting too deep")
    if pos >= len(data):
        raise FieldError("truncated value")
    tag = data[pos]
    pos += 1
    if tag == 0x00:
        return None, pos
    if tag == 0x01:
        return False, pos
    if tag == 0x02:
        return True, pos
    if tag == 0x03:
        raw, pos = _read_uvarint(data, pos)
        return _unzigzag(raw), pos
    if tag in (0x04, 0x05):
        size, pos = _read_uvarint(data, pos)
        if size > MAX_VALUE_BYTES or pos + size > len(data):
            raise FieldError("truncated or oversized scalar")
        raw = data[pos : pos + size]
        pos += size
        return (raw if tag == 0x04 else raw.decode("utf-8")), pos
    if tag == 0x06:
        if pos + 32 > len(data):
            raise FieldError("truncated reference")
        return Ref(data[pos : pos + 32]), pos + 32
    if tag == 0x07:
        count, pos = _read_uvarint(data, pos)
        out = []
        for _ in range(count):
            item, pos = _decode(data, pos, depth + 1)
            out.append(item)
        return out, pos
    if tag == 0x08:
        count, pos = _read_uvarint(data, pos)
        out = {}
        last_key_bytes = None
        for _ in range(count):
            key_start = pos
            key, pos = _decode(data, pos, depth + 1)
            key_bytes = data[key_start:pos]
            if last_key_bytes is not None and key_bytes <= last_key_bytes:
                raise FieldError("non-canonical map key order")
            last_key_bytes = key_bytes
            try:
                hash(key)
            except TypeError as exc:
                raise FieldError("decoded map key is not hashable") from exc
            val, pos = _decode(data, pos, depth + 1)
            out[key] = val
        return out, pos
    raise FieldError(f"unknown field value tag: {tag}")


def decode(data: bytes) -> Any:
    value, pos = _decode(data, 0, 0)
    if pos != len(data):
        raise FieldError("trailing bytes after canonical value")
    return value


def kind_code(kind: str | int) -> int:
    if isinstance(kind, int):
        if kind not in _KIND_NAME:
            raise FieldError("unknown grain kind")
        return kind
    try:
        return _KIND[kind]
    except KeyError as exc:
        raise FieldError(f"unknown grain kind: {kind}") from exc


def make_grain(kind: str | int, value: Any) -> Grain:
    code = kind_code(kind)
    body = encode(value)
    identity = hashlib.blake2s(SCHEMA_TAG + bytes([code]) + body, digest_size=32).digest()
    return Grain(code, value, body, identity)


def make_capability(name: str, *, accepts: Iterable[str] = (), provides: Iterable[str] = (), traits: dict[str, Any] | None = None) -> Grain:
    if not name or len(name.encode("utf-8")) > 256:
        raise FieldError("capability name must be non-empty and bounded")
    value = {
        "name": name,
        "accepts": sorted(set(accepts)),
        "provides": sorted(set(provides)),
        "traits": traits or {},
    }
    return make_grain("capability", value)


def _record_bytes(grain: Grain) -> bytes:
    return (
        RECORD_MAGIC
        + bytes([RECORD_VERSION, grain.kind])
        + _uvarint(len(grain.body))
        + grain.identity
        + grain.body
    )


class Field:
    """Location-free logical set of immutable self-addressed grains."""

    def __init__(self, grains: Iterable[Grain] = ()) -> None:
        self._grains: dict[bytes, Grain] = {}
        for grain in grains:
            self.add_grain(grain)

    def __len__(self) -> int:
        return len(self._grains)

    def __contains__(self, identity: bytes | Ref) -> bool:
        raw = identity.identity if isinstance(identity, Ref) else identity
        return raw in self._grains

    def add(self, kind: str | int, value: Any) -> Ref:
        grain = make_grain(kind, value)
        self.add_grain(grain)
        return Ref(grain.identity)

    def add_grain(self, grain: Grain) -> Ref:
        expected = make_grain(grain.kind, grain.value)
        if expected.body != grain.body or expected.identity != grain.identity:
            raise FieldError("grain does not match its canonical identity")
        existing = self._grains.get(grain.identity)
        if existing is not None and existing.body != grain.body:
            raise FieldError("identity collision")
        self._grains[grain.identity] = grain
        return Ref(grain.identity)

    def get(self, ref: Ref | bytes) -> Grain:
        identity = ref.identity if isinstance(ref, Ref) else ref
        return self._grains[identity]

    def identities(self) -> tuple[bytes, ...]:
        return tuple(sorted(self._grains))

    @property
    def identity(self) -> bytes:
        h = hashlib.blake2s(digest_size=32)
        h.update(FIELD_TAG)
        for identity in self.identities():
            h.update(identity)
        return h.digest()

    @property
    def hex_id(self) -> str:
        return self.identity.hex()

    def refs_in(self, grain: Grain) -> set[Ref]:
        found: set[Ref] = set()

        def walk(value: Any) -> None:
            if isinstance(value, Ref):
                found.add(value)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
            elif isinstance(value, dict):
                for key, item in value.items():
                    walk(key)
                    walk(item)

        walk(grain.value)
        return found

    def missing_refs(self) -> set[Ref]:
        missing: set[Ref] = set()
        for grain in self._grains.values():
            for ref in self.refs_in(grain):
                if ref.identity not in self._grains:
                    missing.add(ref)
        return missing

    def merge(self, other: "Field") -> "Field":
        merged = Field(self._grains.values())
        for grain in other._grains.values():
            merged.add_grain(grain)
        return merged

    def project(self, order: Iterable[bytes] | None = None) -> bytes:
        ids = list(self.identities() if order is None else order)
        if set(ids) != set(self._grains) or len(ids) != len(self._grains):
            raise FieldError("projection order must contain every grain exactly once")
        return b"".join(_record_bytes(self._grains[identity]) for identity in ids)

    @classmethod
    def absorb(cls, carrier: bytes, *, recover: bool = False) -> "Field":
        field = cls()
        pos = 0
        while pos < len(carrier):
            if carrier[pos : pos + 4] != RECORD_MAGIC:
                if not recover:
                    raise FieldError(f"record magic missing at byte {pos}")
                next_pos = carrier.find(RECORD_MAGIC, pos + 1)
                if next_pos < 0:
                    break
                pos = next_pos
                continue
            record_start = pos
            try:
                pos += 4
                if pos + 2 > len(carrier):
                    raise FieldError("truncated record header")
                version = carrier[pos]
                kind = carrier[pos + 1]
                pos += 2
                if version != RECORD_VERSION:
                    raise FieldError("unsupported record version")
                kind_code(kind)
                body_size, pos = _read_uvarint(carrier, pos)
                if body_size > MAX_VALUE_BYTES or pos + 32 + body_size > len(carrier):
                    raise FieldError("truncated or oversized record")
                identity = carrier[pos : pos + 32]
                pos += 32
                body = carrier[pos : pos + body_size]
                pos += body_size
                value = decode(body)
                grain = make_grain(kind, value)
                if grain.identity != identity or grain.body != body:
                    raise FieldError("record identity mismatch")
                field.add_grain(grain)
            except (FieldError, UnicodeDecodeError):
                if not recover:
                    raise
                next_pos = carrier.find(RECORD_MAGIC, record_start + 1)
                if next_pos < 0:
                    break
                pos = next_pos
        return field


__all__ = [
    "Field",
    "FieldError",
    "Grain",
    "Ref",
    "decode",
    "encode",
    "make_capability",
    "make_grain",
]
