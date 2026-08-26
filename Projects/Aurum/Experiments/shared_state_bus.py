"""Evidence-backed shared state/event bus for Aurum/BoxBrain.

The bus is deliberately boring: append-only JSONL events plus a deterministic
projection. Chats, Future Branch, runners, devices, and dashboards can therefore
cross-talk through durable facts instead of relying on one conversation's memory.

The bus does not grant authority. Verified runtime states require evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Iterable, Mapping
from uuid import uuid4


SCHEMA = "aurum-shared-state-event-v1"
PROJECTION_SCHEMA = "aurum-shared-state-v1"

STATUSES = frozenset(
    {
        "planned",
        "queued",
        "running_unverified",
        "running_verified",
        "waiting",
        "blocked",
        "succeeded",
        "failed",
        "no_change",
        "refused",
    }
)
VERIFIED_STATUSES = frozenset({"running_verified", "succeeded"})
TERMINAL_STATUSES = frozenset({"succeeded", "failed", "no_change", "refused"})


class SharedStateError(ValueError):
    """Raised when shared state would violate evidence/provenance invariants."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _nonempty(value: object, name: str) -> str:
    text = str(value).strip()
    if not text:
        raise SharedStateError(f"{name} must be non-empty")
    return text


def _unique_strings(values: Iterable[object]) -> tuple[str, ...]:
    result = tuple(_nonempty(value, "reference") for value in values)
    return tuple(dict.fromkeys(result))


@dataclass(frozen=True)
class StateEvent:
    subject_id: str
    subject_kind: str
    status: str
    actor: str
    source: str
    event_id: str = field(default_factory=lambda: f"evt-{uuid4().hex}")
    timestamp: str = field(default_factory=utc_now)
    node_id: str | None = None
    summary: str = ""
    evidence_refs: tuple[str, ...] = ()
    dependency_ids: tuple[str, ...] = ()
    confidence: float | None = None
    payload: Mapping[str, object] = field(default_factory=dict)
    authority_ref: str | None = None

    def validate(self) -> None:
        _nonempty(self.event_id, "event_id")
        _nonempty(self.subject_id, "subject_id")
        _nonempty(self.subject_kind, "subject_kind")
        _nonempty(self.actor, "actor")
        _nonempty(self.source, "source")
        _nonempty(self.timestamp, "timestamp")
        if self.status not in STATUSES:
            raise SharedStateError(f"unknown status: {self.status}")
        evidence = _unique_strings(self.evidence_refs)
        _unique_strings(self.dependency_ids)
        if self.status in VERIFIED_STATUSES and not evidence:
            raise SharedStateError(f"{self.status} requires at least one evidence reference")
        if self.confidence is not None and not 0.0 <= float(self.confidence) <= 1.0:
            raise SharedStateError("confidence must be between 0 and 1")
        if self.authority_ref is not None:
            _nonempty(self.authority_ref, "authority_ref")
        if self.node_id is not None:
            _nonempty(self.node_id, "node_id")
        if not isinstance(self.payload, Mapping):
            raise SharedStateError("payload must be a mapping")

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "schema": SCHEMA,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "subject_id": self.subject_id,
            "subject_kind": self.subject_kind,
            "node_id": self.node_id,
            "status": self.status,
            "actor": self.actor,
            "source": self.source,
            "summary": self.summary,
            "evidence_refs": list(_unique_strings(self.evidence_refs)),
            "dependency_ids": list(_unique_strings(self.dependency_ids)),
            "confidence": self.confidence,
            "authority_ref": self.authority_ref,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "StateEvent":
        if raw.get("schema") != SCHEMA:
            raise SharedStateError("unexpected shared-state event schema")
        event = cls(
            event_id=str(raw["event_id"]),
            timestamp=str(raw["timestamp"]),
            subject_id=str(raw["subject_id"]),
            subject_kind=str(raw["subject_kind"]),
            node_id=None if raw.get("node_id") is None else str(raw["node_id"]),
            status=str(raw["status"]),
            actor=str(raw["actor"]),
            source=str(raw["source"]),
            summary=str(raw.get("summary", "")),
            evidence_refs=tuple(str(item) for item in raw.get("evidence_refs", ()) or ()),
            dependency_ids=tuple(str(item) for item in raw.get("dependency_ids", ()) or ()),
            confidence=None if raw.get("confidence") is None else float(raw["confidence"]),
            authority_ref=None if raw.get("authority_ref") is None else str(raw["authority_ref"]),
            payload=dict(raw.get("payload", {}) or {}),
        )
        event.validate()
        return event


@dataclass(frozen=True)
class SubjectState:
    subject_id: str
    subject_kind: str
    status: str
    actor: str
    source: str
    event_id: str
    timestamp: str
    node_id: str | None
    summary: str
    evidence_refs: tuple[str, ...]
    dependency_ids: tuple[str, ...]
    confidence: float | None
    authority_ref: str | None
    payload: Mapping[str, object]

    @classmethod
    def from_event(cls, event: StateEvent) -> "SubjectState":
        event.validate()
        return cls(
            subject_id=event.subject_id,
            subject_kind=event.subject_kind,
            status=event.status,
            actor=event.actor,
            source=event.source,
            event_id=event.event_id,
            timestamp=event.timestamp,
            node_id=event.node_id,
            summary=event.summary,
            evidence_refs=_unique_strings(event.evidence_refs),
            dependency_ids=_unique_strings(event.dependency_ids),
            confidence=event.confidence,
            authority_ref=event.authority_ref,
            payload=dict(event.payload),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "subject_id": self.subject_id,
            "subject_kind": self.subject_kind,
            "status": self.status,
            "actor": self.actor,
            "source": self.source,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "node_id": self.node_id,
            "summary": self.summary,
            "evidence_refs": list(self.evidence_refs),
            "dependency_ids": list(self.dependency_ids),
            "confidence": self.confidence,
            "authority_ref": self.authority_ref,
            "payload": dict(self.payload),
        }


class SharedStateBus:
    """Append-only journal with a latest-state projection per subject."""

    def __init__(self, events: Iterable[StateEvent] = ()) -> None:
        self._events: list[StateEvent] = []
        self._ids: set[str] = set()
        self._projection: dict[str, SubjectState] = {}
        for event in events:
            self.apply(event)

    @property
    def events(self) -> tuple[StateEvent, ...]:
        return tuple(self._events)

    def apply(self, event: StateEvent) -> None:
        event.validate()
        if event.event_id in self._ids:
            raise SharedStateError(f"duplicate event id: {event.event_id}")
        prior = self._projection.get(event.subject_id)
        if prior is not None and event.timestamp < prior.timestamp:
            raise SharedStateError("events for a subject must not move backward in time")
        self._events.append(event)
        self._ids.add(event.event_id)
        self._projection[event.subject_id] = SubjectState.from_event(event)

    def latest(self, subject_id: str) -> SubjectState | None:
        return self._projection.get(str(subject_id))

    def projection(self) -> dict[str, SubjectState]:
        return dict(self._projection)

    def unresolved(self) -> tuple[SubjectState, ...]:
        return tuple(
            state
            for _, state in sorted(self._projection.items())
            if state.status not in TERMINAL_STATUSES
        )

    def to_projection_dict(self) -> dict[str, object]:
        return {
            "schema": PROJECTION_SCHEMA,
            "subjects": {
                key: value.to_dict() for key, value in sorted(self._projection.items())
            },
            "event_count": len(self._events),
            "invariants": {
                "verified_runtime_state_requires_evidence": True,
                "state_bus_grants_execution_authority": False,
                "append_only_events": True,
                "chat_memory_is_source_of_truth": False,
            },
        }

    def to_projection_json(self) -> str:
        return json.dumps(self.to_projection_dict(), indent=2, sort_keys=True) + "\n"

    def to_jsonl(self) -> str:
        return "".join(json.dumps(event.to_dict(), sort_keys=True) + "\n" for event in self._events)

    @classmethod
    def from_jsonl(cls, text: str) -> "SharedStateBus":
        events: list[StateEvent] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            raw = json.loads(line)
            if not isinstance(raw, dict):
                raise SharedStateError(f"line {line_number} must contain an object")
            events.append(StateEvent.from_dict(raw))
        return cls(events)

    @classmethod
    def load(cls, path: str | Path) -> "SharedStateBus":
        file_path = Path(path)
        if not file_path.exists():
            return cls()
        return cls.from_jsonl(file_path.read_text(encoding="utf-8"))

    def append_file(self, path: str | Path, event: StateEvent) -> None:
        """Validate, append, flush, then update the in-memory projection.

        This intentionally writes one complete JSON object per line so interrupted
        producers cannot rewrite prior evidence. Callers needing multi-writer
        coordination should add their platform's lock around this method.
        """

        event.validate()
        if event.event_id in self._ids:
            raise SharedStateError(f"duplicate event id: {event.event_id}")
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(event.to_dict(), sort_keys=True) + "\n"
        with file_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        self.apply(event)
