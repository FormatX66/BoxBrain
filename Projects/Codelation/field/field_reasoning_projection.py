from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from aurum_field import Field, Ref


PROJECTION_REVISION = "aurum-field-reasoning-projection-v0"


@dataclass(frozen=True)
class ReasoningProjection:
    identity: str
    source_field_id: str
    grains: int
    utf8_bytes: int
    text: str


def _project_value(value: Any, indexes: Mapping[bytes, int]) -> Any:
    if isinstance(value, Ref):
        if value.identity not in indexes:
            raise ValueError("reasoning projection requires reference-closed Field")
        return ["@", indexes[value.identity]]
    if isinstance(value, bytes):
        return ["b", value.hex()]
    if isinstance(value, list):
        return [_project_value(item, indexes) for item in value]
    if isinstance(value, tuple):
        return [_project_value(item, indexes) for item in value]
    if isinstance(value, Mapping):
        return {
            str(key): _project_value(item, indexes)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    return value


def project_for_reasoning(field: Field) -> ReasoningProjection:
    """Create a compact deterministic GPT-facing view of a closed Field.

    Full grain identities are not repeated in the model projection. Canonical
    Field order defines stable local integer indexes for this one projection;
    references become ["@", index]. Field remains the authoritative identity map.
    """
    if field.missing_refs():
        raise ValueError("reasoning projection requires reference-closed Field")
    identities = field.identities()
    indexes = {identity: index for index, identity in enumerate(identities)}
    records = []
    for identity in identities:
        grain = field.get(identity)
        records.append([grain.kind, _project_value(grain.value, indexes)])

    payload = {
        "v": PROJECTION_REVISION,
        "f": field.hex_id,
        "g": records,
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    raw = text.encode("utf-8")
    identity = hashlib.blake2s(
        b"AURUM-FIELD-REASONING-PROJECTION-0\x00" + raw
    ).hexdigest()
    return ReasoningProjection(
        identity=identity,
        source_field_id=field.hex_id,
        grains=len(records),
        utf8_bytes=len(raw),
        text=text,
    )


__all__ = [
    "PROJECTION_REVISION",
    "ReasoningProjection",
    "project_for_reasoning",
]
