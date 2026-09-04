"""Typed contracts and state-machine rules for Aurum Farmer."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Iterable, Mapping


class JobState(str, Enum):
    RECEIVED = "RECEIVED"
    PLANNED = "PLANNED"
    READY = "READY"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    RETRYING = "RETRYING"
    RECOVERING = "RECOVERING"
    WAITING = "WAITING"
    BLOCKED_HUMAN = "BLOCKED_HUMAN"
    SUCCEEDED = "SUCCEEDED"
    FAILED_FINAL = "FAILED_FINAL"
    CANCELLED = "CANCELLED"


TERMINAL_STATES = {JobState.SUCCEEDED, JobState.FAILED_FINAL, JobState.CANCELLED}


ALLOWED_TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.RECEIVED: {JobState.PLANNED, JobState.CANCELLED},
    JobState.PLANNED: {JobState.READY, JobState.WAITING, JobState.BLOCKED_HUMAN, JobState.CANCELLED},
    JobState.READY: {JobState.RUNNING, JobState.WAITING, JobState.BLOCKED_HUMAN, JobState.CANCELLED},
    JobState.RUNNING: {
        JobState.VERIFYING,
        JobState.RETRYING,
        JobState.RECOVERING,
        JobState.WAITING,
        JobState.BLOCKED_HUMAN,
        JobState.FAILED_FINAL,
        JobState.CANCELLED,
    },
    JobState.VERIFYING: {
        JobState.SUCCEEDED,
        JobState.RETRYING,
        JobState.RECOVERING,
        JobState.FAILED_FINAL,
        JobState.CANCELLED,
    },
    JobState.RETRYING: {JobState.READY, JobState.FAILED_FINAL, JobState.CANCELLED},
    JobState.RECOVERING: {JobState.READY, JobState.BLOCKED_HUMAN, JobState.FAILED_FINAL, JobState.CANCELLED},
    JobState.WAITING: {JobState.READY, JobState.BLOCKED_HUMAN, JobState.FAILED_FINAL, JobState.CANCELLED},
    JobState.BLOCKED_HUMAN: {JobState.READY, JobState.CANCELLED, JobState.FAILED_FINAL},
    JobState.SUCCEEDED: set(),
    JobState.FAILED_FINAL: set(),
    JobState.CANCELLED: set(),
}


class BranchState(str, Enum):
    CANDIDATE = "CANDIDATE"
    RUNNING = "RUNNING"
    RETRYABLE = "RETRYABLE"
    WAITING = "WAITING"
    BLOCKED_HUMAN = "BLOCKED_HUMAN"
    SUCCEEDED = "SUCCEEDED"
    QUARANTINED = "QUARANTINED"


class Outcome(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    WAITING = "waiting"
    HUMAN_REQUIRED = "human_required"
    REFUSED = "refused"
    NO_CHANGE = "no_change"


HUMAN_BOUNDARY_KINDS = {
    "credential",
    "destructive_authorization",
    "irreversible_authorization",
    "physical_action",
    "subjective_decision",
    "identity_confirmation",
}


RETRY_CHANGE_DIMENSIONS = {
    "input",
    "state",
    "evidence",
    "implementation",
    "environment",
    "dependency",
    "hypothesis",
    "authority",
}


TRANSIENT_FAILURE_CLASSES = {
    "rate_limit",
    "transport",
    "dependency_unavailable",
    "runner_lost",
    "timeout",
}


@dataclass(frozen=True)
class EvidenceRequirement:
    kind: str
    minimum: int = 1

    @classmethod
    def from_value(cls, value: str | Mapping[str, Any]) -> "EvidenceRequirement":
        if isinstance(value, str):
            return cls(value)
        return cls(str(value["kind"]), int(value.get("minimum", 1)))

    def validate(self) -> None:
        if not self.kind or len(self.kind) > 100:
            raise ValueError("evidence requirement kind is invalid")
        if self.minimum < 1 or self.minimum > 100:
            raise ValueError("evidence requirement minimum must be from 1 to 100")


@dataclass(frozen=True)
class EvidenceItem:
    kind: str
    source: str
    data: Mapping[str, Any]
    verified: bool = True

    def validate(self) -> None:
        if not self.kind or len(self.kind) > 100:
            raise ValueError("evidence kind is invalid")
        if not self.source or len(self.source) > 500:
            raise ValueError("evidence source is invalid")
        if not isinstance(self.data, Mapping):
            raise ValueError("evidence data must be an object")


@dataclass(frozen=True)
class HumanBoundary:
    kind: str
    summary: str
    requested_action: str

    @classmethod
    def from_value(cls, value: Mapping[str, Any] | None) -> "HumanBoundary | None":
        if value is None:
            return None
        return cls(
            kind=str(value["kind"]),
            summary=str(value["summary"]),
            requested_action=str(value["requested_action"]),
        )

    def validate(self) -> None:
        if self.kind not in HUMAN_BOUNDARY_KINDS:
            raise ValueError(f"unsupported human boundary kind: {self.kind}")
        if not self.summary or not self.requested_action:
            raise ValueError("human boundary summary and requested_action are required")


@dataclass(frozen=True)
class BranchSpec:
    id: str
    label: str
    executor: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    expected_evidence: tuple[EvidenceRequirement, ...] = ()
    priority: int = 50
    confidence: float = 0.5
    impact: float = 0.5
    evidence_quality: float = 0.5
    risk: float = 0.0
    cost: float = 0.1
    reversibility: float = 1.0
    authority_ready: bool = True
    dependencies_satisfied: bool = True
    human_boundary: HumanBoundary | None = None
    max_attempts: int = 3
    lkg_scope: str | None = None
    decision: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "BranchSpec":
        return cls(
            id=str(value["id"]),
            label=str(value.get("label", value["id"])),
            executor=str(value["executor"]),
            payload=dict(value.get("payload", {})),
            expected_evidence=tuple(
                EvidenceRequirement.from_value(item)
                for item in value.get("expected_evidence", ())
            ),
            priority=int(value.get("priority", 50)),
            confidence=float(value.get("confidence", 0.5)),
            impact=float(value.get("impact", 0.5)),
            evidence_quality=float(value.get("evidence_quality", 0.5)),
            risk=float(value.get("risk", 0.0)),
            cost=float(value.get("cost", 0.1)),
            reversibility=float(value.get("reversibility", 1.0)),
            authority_ready=bool(value.get("authority_ready", True)),
            dependencies_satisfied=bool(value.get("dependencies_satisfied", True)),
            human_boundary=HumanBoundary.from_value(value.get("human_boundary")),
            max_attempts=int(value.get("max_attempts", 3)),
            lkg_scope=value.get("lkg_scope"),
            decision=dict(value.get("decision", {})),
        )

    def validate(self) -> None:
        if not self.id or len(self.id) > 100:
            raise ValueError("branch id is invalid")
        if not self.label or len(self.label) > 500:
            raise ValueError("branch label is invalid")
        if not self.executor or len(self.executor) > 100:
            raise ValueError("executor is invalid")
        if not 0 <= self.priority <= 100:
            raise ValueError("branch priority must be from 0 to 100")
        for name, item in (
            ("confidence", self.confidence),
            ("impact", self.impact),
            ("evidence_quality", self.evidence_quality),
            ("risk", self.risk),
            ("reversibility", self.reversibility),
        ):
            if not 0 <= item <= 1:
                raise ValueError(f"{name} must be from 0 to 1")
        if not math.isfinite(self.cost) or self.cost < 0:
            raise ValueError("branch cost must be non-negative")
        allowed = {"parents", "required_tier", "effect", "rollback_ref", "expires_at",
                   "uncertainty", "irreversible_cost", "impossible", "implementation_ref"}
        if set(self.decision) - allowed:
            raise ValueError("unknown decision fields; proposals cannot override authority or evidence")
        for key in ("uncertainty", "irreversible_cost"):
            if not 0 <= float(self.decision.get(key, 0)) <= 1:
                raise ValueError(f"{key} must be from 0 to 1")
        if self.decision.get("effect", "read_only") not in {"read_only", "reversible", "protected"}:
            raise ValueError("invalid effect")
        if not isinstance(self.decision.get("parents", []), list):
            raise ValueError("parents must be a list")
        if self.max_attempts < 1 or self.max_attempts > 20:
            raise ValueError("max_attempts must be from 1 to 20")
        for requirement in self.expected_evidence:
            requirement.validate()
        if self.human_boundary:
            self.human_boundary.validate()


@dataclass(frozen=True)
class JobSpec:
    goal: str
    branches: tuple[BranchSpec, ...]
    id: str | None = None
    priority: int = 50
    dedupe_key: str | None = None
    context: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "JobSpec":
        return cls(
            id=value.get("id"),
            goal=str(value["goal"]),
            priority=int(value.get("priority", 50)),
            dedupe_key=value.get("dedupe_key"),
            context=dict(value.get("context", {})),
            branches=tuple(BranchSpec.from_dict(item) for item in value.get("branches", ())),
        )

    def validate(self) -> None:
        if not self.goal or len(self.goal) > 4000:
            raise ValueError("job goal is invalid")
        if not 0 <= self.priority <= 100:
            raise ValueError("job priority must be from 0 to 100")
        if not self.branches:
            raise ValueError("at least one Future Branch is required")
        if len(self.branches) > 128:
            raise ValueError("a job may contain at most 128 action branches")
        ids = set()
        for branch in self.branches:
            branch.validate()
            if branch.id in ids:
                raise ValueError(f"duplicate branch id: {branch.id}")
            ids.add(branch.id)


@dataclass(frozen=True)
class ExecutionResult:
    outcome: Outcome
    summary: str
    evidence: tuple[EvidenceItem, ...] = ()
    failure_class: str | None = None
    retryable: bool = False
    retry_after_seconds: float = 0.0
    changed_dimensions: frozenset[str] = frozenset()
    failure_fingerprint: str | None = None
    human_boundary: HumanBoundary | None = None
    lkg_ref: str | None = None
    next_action: str | None = None

    def validate(self) -> None:
        if not self.summary:
            raise ValueError("execution result summary is required")
        for item in self.evidence:
            item.validate()
        invalid = set(self.changed_dimensions) - RETRY_CHANGE_DIMENSIONS
        if invalid:
            raise ValueError(f"invalid retry change dimensions: {sorted(invalid)}")
        if self.retry_after_seconds < 0:
            raise ValueError("retry_after_seconds must be non-negative")
        if self.outcome == Outcome.HUMAN_REQUIRED:
            if self.human_boundary is None:
                raise ValueError("human_required outcome must include a boundary")
            self.human_boundary.validate()

    @property
    def permits_retry(self) -> bool:
        return self.retryable and (
            bool(self.changed_dimensions)
            or (self.failure_class or "") in TRANSIENT_FAILURE_CLASSES
        )


def transition_allowed(current: str | JobState, target: str | JobState) -> bool:
    return JobState(target) in ALLOWED_TRANSITIONS[JobState(current)]


def evidence_kinds(items: Iterable[EvidenceItem]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if item.verified:
            counts[item.kind] = counts.get(item.kind, 0) + 1
    return counts
