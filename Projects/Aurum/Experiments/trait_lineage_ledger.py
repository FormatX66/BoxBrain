"""Immutable, replay-verifiable Gen3 trait lineage ledger.

The ledger records why candidate traits were accepted as evidence, quarantined,
rejected, or reverted.  It is deliberately pure and zero-authority: appending a
record cannot mutate LKG, install a trait, widen trust, or grant promotion.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable, Mapping


_SCHEMA = "aurum-trait-lineage-ledger-v1"
_DECISIONS = {"candidate-evidence", "quarantined", "rejected", "reverted"}


def _stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _token(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _digest(value: str, name: str) -> str:
    value = _token(value, name).lower()
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


@dataclass(frozen=True)
class LineageInput:
    generation: int
    trait_digest: str
    source_node: str
    decision: str
    evidence_digests: tuple[str, ...]
    lkg_digest: str
    parent_record_digest: str | None = None
    reason: str = ""

    def canonical(self) -> dict:
        if isinstance(self.generation, bool) or not isinstance(self.generation, int) or self.generation < 1:
            raise ValueError("generation must be a positive integer")
        decision = _token(self.decision, "decision")
        if decision not in _DECISIONS:
            raise ValueError(f"unsupported lineage decision: {decision}")
        evidence = sorted({_digest(item, "evidence digest") for item in self.evidence_digests})
        if not evidence:
            raise ValueError("at least one evidence digest is required")
        parent = (
            None
            if self.parent_record_digest is None
            else _digest(self.parent_record_digest, "parent record digest")
        )
        return {
            "generation": self.generation,
            "trait_digest": _digest(self.trait_digest, "trait digest"),
            "source_node": _token(self.source_node, "source node"),
            "decision": decision,
            "evidence_digests": evidence,
            "lkg_digest": _digest(self.lkg_digest, "LKG digest"),
            "parent_record_digest": parent,
            "reason": self.reason.strip() if isinstance(self.reason, str) else "",
        }


class TraitLineageLedger:
    schema = _SCHEMA

    def __init__(self, records: Iterable[Mapping[str, object]] = ()):
        self._records: list[dict] = []
        for record in records:
            self._append_verified_record(dict(record))

    @property
    def tip_digest(self) -> str | None:
        return self._records[-1]["record_digest"] if self._records else None

    @property
    def records(self) -> tuple[dict, ...]:
        return tuple(dict(item) for item in self._records)

    def append(self, item: LineageInput) -> dict:
        canonical = item.canonical()
        expected_parent = self.tip_digest
        if canonical["parent_record_digest"] != expected_parent:
            raise ValueError("lineage parent does not match current ledger tip")
        body = {"schema": self.schema, **canonical}
        record = {**body, "record_digest": _sha256(body)}
        self._append_verified_record(record)
        return dict(record)

    def _append_verified_record(self, record: dict) -> None:
        if record.get("schema") != self.schema:
            raise ValueError("unsupported lineage ledger schema")
        claimed = record.get("record_digest")
        if not isinstance(claimed, str):
            raise ValueError("lineage record digest missing")
        claimed = _digest(claimed, "record digest")
        body = dict(record)
        body.pop("record_digest", None)
        if _sha256(body) != claimed:
            raise ValueError("lineage record digest mismatch")

        item = LineageInput(
            generation=body.get("generation"),
            trait_digest=body.get("trait_digest"),
            source_node=body.get("source_node"),
            decision=body.get("decision"),
            evidence_digests=tuple(body.get("evidence_digests", ())),
            lkg_digest=body.get("lkg_digest"),
            parent_record_digest=body.get("parent_record_digest"),
            reason=body.get("reason", ""),
        )
        canonical = item.canonical()
        canonical_body = {"schema": self.schema, **canonical}
        if canonical_body != body:
            raise ValueError("lineage record is not canonical")

        expected_parent = self.tip_digest
        if canonical["parent_record_digest"] != expected_parent:
            raise ValueError("lineage chain parent mismatch")
        self._records.append({**canonical_body, "record_digest": claimed})

    def serialize(self) -> str:
        return _stable_json({"schema": self.schema, "records": self._records})

    def digest(self) -> str:
        return _sha256({"schema": self.schema, "records": self._records})

    @classmethod
    def replay(cls, serialized: str, *, expected_ledger_digest: str | None = None) -> "TraitLineageLedger":
        try:
            payload = json.loads(serialized)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("malformed lineage ledger") from exc
        if not isinstance(payload, dict) or payload.get("schema") != cls.schema:
            raise ValueError("unsupported lineage ledger schema")
        records = payload.get("records")
        if not isinstance(records, list):
            raise ValueError("lineage records must be a list")
        ledger = cls(records)
        if ledger.serialize() != _stable_json(payload):
            raise ValueError("lineage ledger is not canonical")
        if expected_ledger_digest is not None:
            expected = _digest(expected_ledger_digest, "expected ledger digest")
            if ledger.digest() != expected:
                raise ValueError("lineage ledger digest mismatch")
        return ledger

    def trait_history(self, trait_digest: str) -> tuple[dict, ...]:
        target = _digest(trait_digest, "trait digest")
        return tuple(dict(item) for item in self._records if item["trait_digest"] == target)

    def software_gate(self) -> dict:
        """Expose lineage proof without turning recorded decisions into authority."""
        replayed = TraitLineageLedger.replay(self.serialize(), expected_ledger_digest=self.digest())
        return {
            "lineage_ledger": replayed.digest() == self.digest(),
            "ledger_digest": self.digest(),
            "record_count": len(self._records),
            "tip_digest": self.tip_digest,
            "quarantined_records_retained": any(
                item["decision"] in {"quarantined", "rejected", "reverted"}
                for item in self._records
            ),
            "lkg_mutated": False,
            "trust_widened": False,
            "grants_mutation_authority": False,
            "grants_promotion_authority": False,
            "infers_physical_exchange": False,
        }
