from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable, Mapping, Sequence

from aurum_field import Field


@dataclass(frozen=True)
class SwarmCell:
    name: str
    role: str
    capabilities: frozenset[str]
    slots: int = 1
    available: bool = True
    verified: bool = True


@dataclass(frozen=True)
class LearningPacket:
    gap: str
    principles: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    success_conditions: tuple[str, ...] = ()
    failed_approaches: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class PingPongLane:
    lane: str
    cells: tuple[str, ...]
    produces: str


@dataclass(frozen=True)
class PingPongRound:
    round_id: str
    gap: str
    lanes: tuple[PingPongLane, ...]
    unavailable_cells: tuple[str, ...]
    missing_roles: tuple[str, ...]


ROLE_NEEDS: Mapping[str, frozenset[str]] = {
    "reason": frozenset({"reason"}),
    "derive": frozenset({"derive-local-variant"}),
    "build": frozenset({"isolated-build"}),
    "test": frozenset({"isolated-test"}),
    "review": frozenset({"semantic-review"}),
    "promote": frozenset({"verified-promotion"}),
}


def packet_identity(packet: LearningPacket) -> str:
    payload = {
        "gap": packet.gap,
        "principles": sorted(set(packet.principles)),
        "constraints": sorted(set(packet.constraints)),
        "success_conditions": sorted(set(packet.success_conditions)),
        "failed_approaches": sorted(set(packet.failed_approaches)),
        "evidence": sorted(set(packet.evidence)),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.blake2s(b"AURUM-PINGPONG-LEARNING-0\x00" + raw).hexdigest()


def _eligible(cells: Sequence[SwarmCell], required: frozenset[str]) -> tuple[SwarmCell, ...]:
    return tuple(
        cell
        for cell in sorted(cells, key=lambda item: (-max(0, item.slots), item.name))
        if cell.available and cell.verified and cell.slots > 0 and required.issubset(cell.capabilities)
    )


def plan_pingpong_round(packet: LearningPacket, cells: Iterable[SwarmCell]) -> PingPongRound:
    """Fan one self-build learning round across all verified useful cells.

    Git cells are independent workshops. GPT-like cells are reasoning resources.
    Cells exchange learning/evidence, never an implementation that other nodes
    must copy. Promotion is a separate role from reasoning and building.
    """
    pool = tuple(cells)
    lanes: list[PingPongLane] = []
    missing: list[str] = []

    lane_specs = (
        ("reason", "candidate-specifications"),
        ("derive", "local-variant-designs"),
        ("build", "isolated-candidates"),
        ("test", "verification-evidence"),
        ("review", "semantic-review-evidence"),
        ("promote", "promoted-local-variants"),
    )
    for role, produces in lane_specs:
        selected = _eligible(pool, ROLE_NEEDS[role])
        if selected:
            lanes.append(PingPongLane(role, tuple(cell.name for cell in selected), produces))
        else:
            missing.append(role)

    unavailable = tuple(sorted(cell.name for cell in pool if not cell.available or not cell.verified))
    raw = json.dumps(
        {
            "packet": packet_identity(packet),
            "lanes": [(lane.lane, lane.cells, lane.produces) for lane in lanes],
            "missing": missing,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    round_id = hashlib.blake2s(b"AURUM-PINGPONG-ROUND-0\x00" + raw).hexdigest()
    return PingPongRound(round_id, packet.gap, tuple(lanes), unavailable, tuple(missing))


def default_pingpong_cells() -> tuple[SwarmCell, ...]:
    """Logical cells; these may map to branches, worktrees, runners, or remote nodes."""
    return (
        SwarmCell(
            "git-linux-a",
            "git",
            frozenset({"derive-local-variant", "isolated-build", "isolated-test"}),
            slots=4,
        ),
        SwarmCell(
            "git-linux-b",
            "git",
            frozenset({"derive-local-variant", "isolated-build", "isolated-test"}),
            slots=4,
        ),
        SwarmCell(
            "gpt-reasoner-a",
            "gpt",
            frozenset({"reason", "semantic-review"}),
            slots=1,
        ),
        SwarmCell(
            "git-promoter",
            "git-control",
            frozenset({"verified-promotion"}),
            slots=1,
        ),
    )


def pingpong_field(packet: LearningPacket, round_: PingPongRound) -> Field:
    field = Field()
    packet_ref = field.add(
        "fact",
        {
            "kind": "self-build-learning-packet",
            "identity": packet_identity(packet),
            "gap": packet.gap,
            "principles": list(packet.principles),
            "constraints": list(packet.constraints),
            "success_conditions": list(packet.success_conditions),
            "failed_approaches": list(packet.failed_approaches),
            "evidence": list(packet.evidence),
        },
    )
    lane_refs = []
    for lane in round_.lanes:
        lane_refs.append(
            field.add(
                "relation",
                {
                    "kind": "self-build-pingpong-lane",
                    "round_id": round_.round_id,
                    "learns_from": packet_ref,
                    "lane": lane.lane,
                    "cells": list(lane.cells),
                    "produces": lane.produces,
                    "shared_implementation": False,
                },
            )
        )
    field.add(
        "view",
        {
            "name": "aurum-self-build-pingpong-round",
            "round_id": round_.round_id,
            "gap": round_.gap,
            "lanes": lane_refs,
            "unavailable_cells": list(round_.unavailable_cells),
            "missing_roles": list(round_.missing_roles),
            "event_driven": True,
            "timer_dependency": False,
            "shared_learning_only": True,
        },
    )
    return field


__all__ = [
    "LearningPacket",
    "PingPongLane",
    "PingPongRound",
    "SwarmCell",
    "default_pingpong_cells",
    "packet_identity",
    "pingpong_field",
    "plan_pingpong_round",
]
