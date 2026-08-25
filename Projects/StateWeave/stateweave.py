"""StateWeave generation-0 prototype.

A deterministic machine-state representation and transition engine. This lane is
standalone on purpose: it does not import or depend on the Adaptive Kernel lane.

Future Branch integration is deliberately *recording only*: StateWeave preserves
candidate/proven branch facts, evidence references, rollback lineage, verified
outcomes, and the verified-state basis a speculative branch was built against. It
does not rank branches or execute their actions. The safety/policy engine remains
outside this state representation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Iterable, Mapping

Scalar = bool | int | float | str | None
_BRANCH_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
_BRANCH_STATUSES = {"warm", "promoted", "rejected", "quarantined", "expired", "verified"}
_REVERSIBILITY = {"full", "partial", "none"}


def _canonical(mapping: Mapping[str, Scalar]) -> tuple[tuple[str, Scalar], ...]:
    return tuple(sorted(mapping.items(), key=lambda item: item[0]))


@dataclass(frozen=True)
class State:
    values: tuple[tuple[str, Scalar], ...]

    @classmethod
    def from_mapping(cls, values: Mapping[str, Scalar]) -> "State":
        return cls(_canonical(values))

    def as_dict(self) -> dict[str, Scalar]:
        return dict(self.values)

    def digest(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Transition:
    name: str
    requires: tuple[tuple[str, Scalar], ...]
    writes: tuple[tuple[str, Scalar], ...]

    @classmethod
    def build(
        cls,
        name: str,
        *,
        requires: Mapping[str, Scalar] | None = None,
        writes: Mapping[str, Scalar] | None = None,
    ) -> "Transition":
        return cls(name, _canonical(requires or {}), _canonical(writes or {}))

    def enabled(self, state: State) -> bool:
        current = state.as_dict()
        return all(current.get(key) == value for key, value in self.requires)

    def apply(self, state: State) -> State:
        if not self.enabled(state):
            raise ValueError(f"transition {self.name!r} requirements are not satisfied")
        updated = state.as_dict()
        updated.update(dict(self.writes))
        return State.from_mapping(updated)


@dataclass(frozen=True)
class TraceStep:
    transition: str
    before: str
    after: str


@dataclass(frozen=True)
class BranchEvidenceRecord:
    """Auditable evidence metadata for a Future Branch.

    Only references and bounded scoring facts are stored. Hidden reasoning and raw
    private context are intentionally outside the StateWeave record.
    """

    ref: str
    weight: float = 1.0
    quality: float = 1.0
    supports: bool = True

    def validate(self) -> None:
        if not self.ref:
            raise ValueError("evidence ref required")
        for name, value in (("weight", self.weight), ("quality", self.quality)):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"evidence {name} must be between 0 and 1")


@dataclass(frozen=True)
class BranchRecord:
    """Serializable decision facts for one Future Branch."""

    branch_id: str
    proposed_state: str
    confidence: float
    risk: float
    reversibility: str = "full"
    status: str = "warm"
    evidence: tuple[BranchEvidenceRecord, ...] = ()
    rollback_target: str | None = None
    is_last_known_good: bool = False
    verified_result: str | None = None
    basis_state_digest: str | None = None

    def validate(self) -> None:
        if not self.branch_id or not _BRANCH_ID.fullmatch(self.branch_id):
            raise ValueError("branch_id must use letters, numbers, dot, dash, or underscore")
        if not self.proposed_state:
            raise ValueError("proposed_state required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not 0.0 <= self.risk <= 1.0:
            raise ValueError("risk must be between 0 and 1")
        if self.reversibility not in _REVERSIBILITY:
            raise ValueError("invalid reversibility")
        if self.status not in _BRANCH_STATUSES:
            raise ValueError("invalid branch status")
        if self.basis_state_digest is not None and not re.fullmatch(r"[0-9a-f]{64}", self.basis_state_digest):
            raise ValueError("basis_state_digest must be a sha256 hex digest")
        for item in self.evidence:
            item.validate()


def branch_writes(record: BranchRecord) -> dict[str, Scalar]:
    """Encode a Future Branch record as deterministic StateWeave scalar keys."""

    record.validate()
    prefix = f"future.branch.{record.branch_id}."
    writes: dict[str, Scalar] = {
        f"{prefix}proposed_state": record.proposed_state,
        f"{prefix}confidence": record.confidence,
        f"{prefix}risk": record.risk,
        f"{prefix}reversibility": record.reversibility,
        f"{prefix}status": record.status,
        f"{prefix}evidence_count": len(record.evidence),
        f"{prefix}is_last_known_good": record.is_last_known_good,
    }
    if record.rollback_target is not None:
        writes[f"{prefix}rollback_target"] = record.rollback_target
    if record.verified_result is not None:
        writes[f"{prefix}verified_result"] = record.verified_result
    if record.basis_state_digest is not None:
        writes[f"{prefix}basis_state_digest"] = record.basis_state_digest

    for index, item in enumerate(record.evidence):
        evidence_prefix = f"{prefix}evidence.{index}."
        writes[f"{evidence_prefix}ref"] = item.ref
        writes[f"{evidence_prefix}weight"] = item.weight
        writes[f"{evidence_prefix}quality"] = item.quality
        writes[f"{evidence_prefix}supports"] = item.supports
    return writes


def record_branch(state: State, record: BranchRecord) -> State:
    """Preserve one externally evaluated Future Branch in the state graph."""

    transition = Transition.build(
        f"future-branch-record:{record.branch_id}",
        writes=branch_writes(record),
    )
    return transition.apply(state)


def record_branch_set(state: State, records: Iterable[BranchRecord]) -> State:
    """Record a bounded branch field without choosing a winner."""

    result = state
    count = 0
    for record in records:
        result = record_branch(result, record)
        count += 1
    return Transition.build("future-branch-field", writes={"future.branch.count": count}).apply(result)


def expire_stale_branches(state: State, *, current_verified_state_digest: str) -> State:
    """Mark warm/promoted speculative branches expired when their basis changed.

    The old decision facts/evidence stay in StateWeave for auditability; only the
    branch status changes to ``expired``. Verified/LKG records are not rewritten by
    this helper. A branch with no recorded basis remains untouched because its
    staleness cannot be established from evidence.
    """

    if not re.fullmatch(r"[0-9a-f]{64}", current_verified_state_digest):
        raise ValueError("current_verified_state_digest must be a sha256 hex digest")
    values = state.as_dict()
    suffix = ".basis_state_digest"
    writes: dict[str, Scalar] = {}
    for key, basis in values.items():
        if not key.startswith("future.branch.") or not key.endswith(suffix):
            continue
        branch_id = key[len("future.branch.") : -len(suffix)]
        status_key = f"future.branch.{branch_id}.status"
        status = values.get(status_key)
        if basis != current_verified_state_digest and status in {"warm", "promoted"}:
            writes[status_key] = "expired"
            writes[f"future.branch.{branch_id}.expired_against_state_digest"] = current_verified_state_digest
    if not writes:
        return state
    return Transition.build("future-branch-expire-stale", writes=writes).apply(state)


def run(initial: State, transitions: Iterable[Transition]) -> tuple[State, tuple[TraceStep, ...]]:
    state = initial
    trace: list[TraceStep] = []
    for transition in transitions:
        before = state.digest()
        state = transition.apply(state)
        trace.append(TraceStep(transition.name, before, state.digest()))
    return state, tuple(trace)
