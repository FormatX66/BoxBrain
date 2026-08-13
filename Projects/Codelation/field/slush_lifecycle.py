from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from aurum_field import Field
from capacity_mesh import WorkItem

PLANNED = "planned"
MATERIALIZED = "materialized"
SEEDED = "seeded"
RUNTIME_READY = "runtime-ready"


@dataclass(frozen=True)
class SlushState:
    identity: str
    node_id: str
    carrier: str
    capacity_bytes: int
    state: str = PLANNED
    evidence: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.identity or not self.node_id or not self.carrier:
            raise ValueError("Slush identity, node, and carrier are required")
        if self.capacity_bytes <= 0:
            raise ValueError("Slush capacity must be positive")
        if self.state not in {PLANNED, MATERIALIZED, SEEDED, RUNTIME_READY}:
            raise ValueError("invalid Slush lifecycle state")


_REQUIRED = {
    (PLANNED, MATERIALIZED): frozenset(
        {"storage-capacity-verified", "write-scope-approved", "no-partition-change"}
    ),
    (MATERIALIZED, SEEDED): frozenset(
        {"extent-verified", "seed-digest-verified", "mirrored-anchor-verified"}
    ),
    (SEEDED, RUNTIME_READY): frozenset(
        {"isolation-carrier-verified", "runtime-artifact-verified", "runtime-selftest-pass"}
    ),
}


def advance_slush(
    current: SlushState,
    target_state: str,
    evidence: Iterable[str],
) -> SlushState:
    current.validate()
    key = (current.state, target_state)
    if key not in _REQUIRED:
        raise ValueError("invalid or non-adjacent Slush transition")
    merged = frozenset(current.evidence) | frozenset(evidence)
    missing = _REQUIRED[key] - merged
    if missing:
        raise ValueError("missing transition evidence: " + ",".join(sorted(missing)))
    return replace(current, state=target_state, evidence=tuple(sorted(merged)))


def next_slush_work(current: SlushState) -> tuple[WorkItem, ...]:
    current.validate()
    if current.state == PLANNED:
        return (
            WorkItem(
                "materialize-slush:" + current.identity,
                frozenset({"slush-extent-provision"}),
                weight=5,
            ),
        )
    if current.state == MATERIALIZED:
        return (
            WorkItem(
                "seed-slush:" + current.identity,
                frozenset({"slush-seed"}),
                weight=5,
            ),
        )
    if current.state == SEEDED:
        return (
            WorkItem(
                "materialize-runtime:" + current.identity,
                frozenset({"prototype-runtime-materialize"}),
                weight=6,
            ),
        )
    return ()


def slush_lifecycle_field(current: SlushState) -> Field:
    current.validate()
    field = Field()
    state_ref = field.add(
        "fact",
        {
            "identity": current.identity,
            "node_id": current.node_id,
            "carrier": current.carrier,
            "capacity_bytes": current.capacity_bytes,
            "state": current.state,
            "evidence": list(sorted(current.evidence)),
        },
    )
    work_refs = []
    for work in next_slush_work(current):
        work_refs.append(
            field.add(
                "capability",
                {
                    "kind": "claimable-next-work",
                    "name": work.name,
                    "requires": sorted(work.requires),
                    "weight": work.weight,
                    "executable": False,
                },
            )
        )
    field.add(
        "view",
        {
            "name": "aurum-slush-lifecycle",
            "state": state_ref,
            "next_work": work_refs,
        },
    )
    return field


__all__ = [
    "MATERIALIZED",
    "PLANNED",
    "RUNTIME_READY",
    "SEEDED",
    "SlushState",
    "advance_slush",
    "next_slush_work",
    "slush_lifecycle_field",
]
