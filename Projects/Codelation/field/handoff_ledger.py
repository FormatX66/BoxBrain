from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Mapping, Sequence

from aurum_field import Field
from capacity_mesh import Node, WorkItem
from event_handoff import Handoff, HandoffPlan


OPEN = "open"
CLAIMED = "claimed"
COMPLETED = "completed"
REJECTED = "rejected"
_VALID_STATES = frozenset({OPEN, CLAIMED, COMPLETED, REJECTED})


@dataclass(frozen=True)
class LedgerEntry:
    handoff_id: str
    cause: str
    work: WorkItem
    reward_score: int
    state: str = OPEN
    claimant: str | None = None
    result_event_id: str | None = None

    def __post_init__(self) -> None:
        if self.state not in _VALID_STATES:
            raise ValueError("invalid handoff ledger state")
        if self.state == OPEN and (self.claimant is not None or self.result_event_id is not None):
            raise ValueError("open handoff cannot already have claim/result state")
        if self.state == CLAIMED and not self.claimant:
            raise ValueError("claimed handoff requires claimant")
        if self.state == COMPLETED and (not self.claimant or not self.result_event_id):
            raise ValueError("completed handoff requires claimant and result event")


class HandoffLedger:
    """Deterministic claim lifecycle for event-derived work; clocks are not semantic."""

    def __init__(self, entries: Iterable[LedgerEntry] = ()) -> None:
        self._entries: dict[str, LedgerEntry] = {}
        for entry in entries:
            existing = self._entries.get(entry.handoff_id)
            if existing is not None and existing != entry:
                raise ValueError("conflicting state for one handoff identity")
            self._entries[entry.handoff_id] = entry

    @classmethod
    def from_plan(cls, plan: HandoffPlan) -> "HandoffLedger":
        return cls(
            LedgerEntry(
                handoff_id=handoff.event_id,
                cause=handoff.cause,
                work=handoff.work,
                reward_score=handoff.reward_score,
            )
            for handoff in plan.emitted
        )

    def entries(self) -> tuple[LedgerEntry, ...]:
        return tuple(self._entries[key] for key in sorted(self._entries))

    def open_entries(self) -> tuple[LedgerEntry, ...]:
        return tuple(
            sorted(
                (entry for entry in self._entries.values() if entry.state == OPEN),
                key=lambda entry: (-entry.work.weight, entry.work.name, entry.handoff_id),
            )
        )

    def claim(self, worker: Node) -> LedgerEntry | None:
        """Claim the highest-value open work the worker can satisfy."""
        candidates = [
            entry
            for entry in self.open_entries()
            if entry.work.requires.issubset(worker.capabilities)
        ]
        if not candidates:
            return None
        selected = candidates[0]
        claimed = replace(selected, state=CLAIMED, claimant=worker.name)
        self._entries[selected.handoff_id] = claimed
        return claimed

    def complete(self, handoff_id: str, *, worker: str, result_event_id: str) -> LedgerEntry:
        current = self._entries[handoff_id]
        if current.state == COMPLETED:
            if current.claimant == worker and current.result_event_id == result_event_id:
                return current
            raise ValueError("handoff already completed with different evidence")
        if current.state != CLAIMED:
            raise ValueError("handoff must be claimed before completion")
        if current.claimant != worker:
            raise ValueError("only the recorded claimant may complete a handoff")
        if not result_event_id:
            raise ValueError("completion requires result event identity")
        completed = replace(current, state=COMPLETED, result_event_id=result_event_id)
        self._entries[handoff_id] = completed
        return completed

    def reject(self, handoff_id: str, *, worker: str) -> LedgerEntry:
        current = self._entries[handoff_id]
        if current.state != CLAIMED or current.claimant != worker:
            raise ValueError("only the recorded claimant may reject claimed work")
        rejected = replace(current, state=REJECTED)
        self._entries[handoff_id] = rejected
        return rejected

    def merge(self, other: "HandoffLedger") -> "HandoffLedger":
        """Converge identical lifecycle state; conflicting mutable histories stay explicit."""
        merged = HandoffLedger(self.entries())
        for entry in other.entries():
            existing = merged._entries.get(entry.handoff_id)
            if existing is None:
                merged._entries[entry.handoff_id] = entry
            elif existing != entry:
                raise ValueError("handoff lifecycle conflict requires evidence review")
        return merged


def ledger_field(ledger: HandoffLedger) -> Field:
    """Persist claim lifecycle as machine-oriented Field state with provenance."""
    field = Field()
    refs = []
    for entry in ledger.entries():
        refs.append(
            field.add(
                "relation",
                {
                    "handoff_id": entry.handoff_id,
                    "cause": entry.cause,
                    "work": entry.work.name,
                    "requires": sorted(entry.work.requires),
                    "weight": entry.work.weight,
                    "reward_score": entry.reward_score,
                    "state": entry.state,
                    "claimant": entry.claimant,
                    "result_event_id": entry.result_event_id,
                },
            )
        )
    field.add("view", {"name": "claimable-handoff-ledger", "entries": refs})
    return field


def restore_ledger(field: Field) -> HandoffLedger:
    """Reconstruct ledger semantics from its Field projection."""
    entries: list[LedgerEntry] = []
    for identity in field.identities():
        grain = field.get(identity)
        value = grain.value
        if grain.kind != 2 or not isinstance(value, Mapping) or "handoff_id" not in value:
            continue
        entries.append(
            LedgerEntry(
                handoff_id=str(value["handoff_id"]),
                cause=str(value["cause"]),
                work=WorkItem(
                    name=str(value["work"]),
                    requires=frozenset(str(item) for item in value["requires"]),
                    weight=int(value["weight"]),
                ),
                reward_score=int(value["reward_score"]),
                state=str(value["state"]),
                claimant=None if value["claimant"] is None else str(value["claimant"]),
                result_event_id=(
                    None
                    if value["result_event_id"] is None
                    else str(value["result_event_id"])
                ),
            )
        )
    return HandoffLedger(entries)


__all__ = [
    "CLAIMED",
    "COMPLETED",
    "HandoffLedger",
    "LedgerEntry",
    "OPEN",
    "REJECTED",
    "ledger_field",
    "restore_ledger",
]
