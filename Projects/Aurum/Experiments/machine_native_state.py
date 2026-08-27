"""Gen2 machine-native state substrate for Aurum.

The canonical representation is a deterministic graph of semantic entities and
relationships. Human file/tree views are compatibility projections only. This
module is intentionally pure and zero-authority: it performs no filesystem,
device, network, promotion, or LKG mutation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Iterable, Mapping


_ALLOWED_PERSISTENCE = {"ephemeral", "slush", "durable", "protected"}


def _stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _token(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _ratio(value: float, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{field_name} must be within [0, 1]")
    return value


@dataclass(frozen=True)
class EvidenceRef:
    source: str
    digest: str
    confidence: float = 1.0

    def canonical(self) -> dict:
        source = _token(self.source, field_name="evidence source")
        digest = _token(self.digest, field_name="evidence digest").lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError("evidence digest must be a 64-character lowercase hex SHA-256")
        return {
            "source": source,
            "digest": digest,
            "confidence": _ratio(self.confidence, field_name="evidence confidence"),
        }


@dataclass(frozen=True)
class NativeEntity:
    entity_id: str
    kind: str
    attributes: Mapping[str, object] = field(default_factory=dict)
    persistence: str = "slush"
    reachability: float = 1.0
    usefulness: float = 0.5
    evidence: tuple[EvidenceRef, ...] = ()

    def canonical(self) -> dict:
        entity_id = _token(self.entity_id, field_name="entity_id")
        kind = _token(self.kind, field_name="entity kind")
        persistence = _token(self.persistence, field_name="persistence")
        if persistence not in _ALLOWED_PERSISTENCE:
            raise ValueError(f"unsupported persistence class: {persistence}")
        evidence = sorted((item.canonical() for item in self.evidence), key=_stable_json)
        return {
            "entity_id": entity_id,
            "kind": kind,
            "attributes": dict(self.attributes),
            "persistence": persistence,
            "reachability": _ratio(self.reachability, field_name="reachability"),
            "usefulness": _ratio(self.usefulness, field_name="usefulness"),
            "evidence": evidence,
        }


@dataclass(frozen=True)
class NativeRelation:
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    evidence: tuple[EvidenceRef, ...] = ()

    def canonical(self) -> dict:
        return {
            "subject": _token(self.subject, field_name="relation subject"),
            "predicate": _token(self.predicate, field_name="relation predicate"),
            "object": _token(self.object, field_name="relation object"),
            "confidence": _ratio(self.confidence, field_name="relation confidence"),
            "evidence": sorted((item.canonical() for item in self.evidence), key=_stable_json),
        }


class NativeState:
    """Deterministic semantic graph with replay and compatibility projection."""

    schema = "aurum-machine-native-state-v1"

    def __init__(self, entities: Iterable[NativeEntity] = (), relations: Iterable[NativeRelation] = ()):
        self._entities: dict[str, dict] = {}
        self._relations: dict[tuple[str, str, str], dict] = {}
        for entity in entities:
            self.add_entity(entity)
        for relation in relations:
            self.add_relation(relation)
        self._validate_relations()

    def add_entity(self, entity: NativeEntity) -> None:
        canonical = entity.canonical()
        key = canonical["entity_id"]
        previous = self._entities.get(key)
        if previous is not None and previous != canonical:
            raise ValueError(f"contradictory entity definition: {key}")
        self._entities[key] = canonical

    def add_relation(self, relation: NativeRelation) -> None:
        canonical = relation.canonical()
        key = (canonical["subject"], canonical["predicate"], canonical["object"])
        previous = self._relations.get(key)
        if previous is not None and previous != canonical:
            raise ValueError(f"contradictory relation definition: {key}")
        self._relations[key] = canonical

    def _validate_relations(self) -> None:
        for relation in self._relations.values():
            if relation["subject"] not in self._entities:
                raise ValueError(f"unknown relation subject: {relation['subject']}")
            if relation["object"] not in self._entities:
                raise ValueError(f"unknown relation object: {relation['object']}")

    def canonical(self) -> dict:
        self._validate_relations()
        return {
            "schema": self.schema,
            "entities": [self._entities[key] for key in sorted(self._entities)],
            "relations": [self._relations[key] for key in sorted(self._relations)],
        }

    def digest(self) -> str:
        return _sha256(self.canonical())

    def serialize(self) -> str:
        return _stable_json(self.canonical())

    @classmethod
    def replay(cls, serialized: str, *, expected_digest: str | None = None) -> "NativeState":
        try:
            payload = json.loads(serialized)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("malformed native-state snapshot") from exc
        if not isinstance(payload, dict) or payload.get("schema") != cls.schema:
            raise ValueError("unsupported native-state schema")
        entities = []
        for item in payload.get("entities", []):
            if not isinstance(item, dict):
                raise ValueError("malformed entity")
            evidence = tuple(EvidenceRef(**e) for e in item.get("evidence", []))
            entities.append(NativeEntity(
                entity_id=item.get("entity_id"),
                kind=item.get("kind"),
                attributes=item.get("attributes", {}),
                persistence=item.get("persistence", "slush"),
                reachability=item.get("reachability", 1.0),
                usefulness=item.get("usefulness", 0.5),
                evidence=evidence,
            ))
        relations = []
        for item in payload.get("relations", []):
            if not isinstance(item, dict):
                raise ValueError("malformed relation")
            evidence = tuple(EvidenceRef(**e) for e in item.get("evidence", []))
            relations.append(NativeRelation(
                subject=item.get("subject"),
                predicate=item.get("predicate"),
                object=item.get("object"),
                confidence=item.get("confidence", 1.0),
                evidence=evidence,
            ))
        state = cls(entities=entities, relations=relations)
        if state.serialize() != _stable_json(payload):
            raise ValueError("snapshot is not canonical")
        if expected_digest is not None and state.digest() != expected_digest:
            raise ValueError("native-state digest mismatch")
        return state

    def compatibility_projection(self) -> dict:
        """Return a deterministic human-facing view that is never canonical authority."""
        entries = []
        for entity_id in sorted(self._entities):
            entity = self._entities[entity_id]
            links = [
                {
                    "predicate": r["predicate"],
                    "target": r["object"],
                    "confidence": r["confidence"],
                }
                for r in self._relations.values()
                if r["subject"] == entity_id
            ]
            entries.append({
                "path": f"/{entity['kind']}/{entity_id}.json",
                "entity": entity_id,
                "links": sorted(links, key=_stable_json),
            })
        return {
            "schema": "aurum-human-compatibility-projection-v1",
            "canonical": False,
            "source_native_digest": self.digest(),
            "entries": entries,
            "grants_authority": False,
        }


def stateweave_basis_is_current(native_state: NativeState, branch_basis_digest: str) -> bool:
    """Bind speculative StateWeave work to the exact native-state basis."""
    return native_state.digest() == _token(branch_basis_digest, field_name="branch basis digest")


def gen2_state_gate(native_state: NativeState, *, replayed_digest: str, compatibility_source_digest: str) -> dict:
    """Emit evidence for the Gen2 ladder without granting promotion or mutation."""
    digest = native_state.digest()
    replay_ok = digest == replayed_digest
    projection_ok = digest == compatibility_source_digest
    ready = replay_ok and projection_ok
    return {
        "machine_native_state_projection": ready,
        "slush_relationship_model": ready,
        "canonical_digest": digest,
        "replay_verified": replay_ok,
        "compatibility_projection_bound": projection_ok,
        "compatibility_projection_is_canonical": False,
        "grants_mutation_authority": False,
        "may_promote_candidate": False,
        "infers_physical_recovery": False,
    }
