from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from aurum_field import Field
from capacity_mesh import Node, RewardSignal, WorkItem
from event_handoff import CompletionEvent, completion_id, continue_from_events
from handoff_ledger import HandoffLedger, ledger_field
from self_build_federation import (
    FederatedSelfBuildPlan,
    SelfBuildLane,
    federation_field,
    plan_federated_self_build,
)
from self_build_proof import SelfBuildProof
from self_build_resources import BuilderResource, default_self_build_resources


SELF_BUILD_ORCHESTRATOR = Node(
    "aurum-self-build-orchestrator",
    frozenset({"self-build-orchestrate"}),
    capacity=1,
)


@dataclass(frozen=True)
class RecurrenceStage:
    name: str
    requires: frozenset[str]
    after: frozenset[str] = frozenset()
    redundancy: int = 1
    weight: int = 1


@dataclass(frozen=True)
class SelfBuildContinuation:
    next_gap: str
    source_completion_id: str
    continuation_handoff_id: str
    stages: tuple[RecurrenceStage, ...]
    completed_stages: frozenset[str]
    ready_stages: tuple[str, ...]
    federation: FederatedSelfBuildPlan
    ledger: HandoffLedger


_PIPELINE = (
    RecurrenceStage(
        "specify-gap",
        frozenset({"model-reasoning"}),
        weight=100,
    ),
    RecurrenceStage(
        "derive-candidates",
        frozenset({"candidate-generation"}),
        after=frozenset({"specify-gap"}),
        redundancy=2,
        weight=90,
    ),
    RecurrenceStage(
        "isolated-build-test",
        frozenset({"isolated-build", "parallel-test"}),
        after=frozenset({"derive-candidates"}),
        redundancy=2,
        weight=80,
    ),
    RecurrenceStage(
        "semantic-review",
        frozenset({"semantic-analysis"}),
        after=frozenset({"isolated-build-test"}),
        weight=70,
    ),
    RecurrenceStage(
        "verified-promotion",
        frozenset({"verified-repository-promotion"}),
        after=frozenset({"semantic-review"}),
        weight=60,
    ),
    RecurrenceStage(
        "emit-learning-next-gap",
        frozenset({"deterministic-execution"}),
        after=frozenset({"verified-promotion"}),
        weight=50,
    ),
)


def recurrence_pipeline() -> tuple[RecurrenceStage, ...]:
    return _PIPELINE


def ready_recurrence_stages(
    completed: Iterable[str],
    *,
    stages: Sequence[RecurrenceStage] = _PIPELINE,
) -> tuple[RecurrenceStage, ...]:
    done = frozenset(completed)
    known = {stage.name for stage in stages}
    unknown = done - known
    if unknown:
        raise ValueError(f"unknown recurrence stages: {sorted(unknown)}")
    return tuple(
        stage
        for stage in stages
        if stage.name not in done and stage.after.issubset(done)
    )


def _proof_completion(proof: SelfBuildProof) -> CompletionEvent:
    verified = (
        proof.candidate_sha256 == proof.promoted_sha256
        and bool(proof.stages)
        and proof.stages[-1] == "next-gap-emitted"
        and bool(proof.next_gap)
    )
    return CompletionEvent(
        name=f"self-build-complete:{proof.gap_name}",
        node="aurum-self-build",
        reward=RewardSignal(
            verified=verified,
            reusable=verified,
            generalized=verified,
            false_claim=not verified,
        ),
        followups=(
            WorkItem(
                name=f"self-build-continuation:{proof.next_gap}",
                requires=frozenset({"self-build-orchestrate"}),
                weight=100,
            ),
        ),
        evidence=(
            f"candidate:{proof.candidate_sha256}",
            f"promoted:{proof.promoted_sha256}",
            f"learning:{proof.learning_packet_identity}",
            f"wave:{proof.wave_id}",
            f"next-gap:{proof.next_gap}",
        ),
    )


def continue_self_build(
    proof: SelfBuildProof,
    *,
    completed_stages: Iterable[str] = (),
    resources: Sequence[BuilderResource] | None = None,
) -> SelfBuildContinuation:
    """Turn a verified self-build result into the next event-driven build cycle.

    There is no timer input. A verified proof emits exactly one durable continuation
    handoff. The orchestrator claims that handoff, then only dependency-ready stages
    are federated to currently available resources. Promotion is therefore never
    scheduled before build/test and semantic review evidence exist.
    """
    completion = _proof_completion(proof)
    event_plan = continue_from_events([completion], [SELF_BUILD_ORCHESTRATOR])
    if len(event_plan.emitted) != 1:
        raise ValueError("verified self-build must emit exactly one continuation")

    ledger = HandoffLedger.from_plan(event_plan)
    claimed = ledger.claim(SELF_BUILD_ORCHESTRATOR)
    if claimed is None:
        raise ValueError("self-build continuation could not be claimed")

    done = frozenset(completed_stages)
    ready = ready_recurrence_stages(done)
    lanes = tuple(
        SelfBuildLane(
            name=f"{stage.name}:{proof.next_gap}",
            requires=stage.requires,
            weight=stage.weight,
            redundancy=stage.redundancy,
        )
        for stage in ready
    )
    pool = tuple(default_self_build_resources() if resources is None else resources)
    federation = plan_federated_self_build(lanes, pool)

    return SelfBuildContinuation(
        next_gap=proof.next_gap,
        source_completion_id=completion_id(completion),
        continuation_handoff_id=claimed.handoff_id,
        stages=tuple(_PIPELINE),
        completed_stages=done,
        ready_stages=tuple(stage.name for stage in ready),
        federation=federation,
        ledger=ledger,
    )


def advance_self_build(
    continuation: SelfBuildContinuation,
    newly_completed: Iterable[str],
    *,
    resources: Sequence[BuilderResource] | None = None,
) -> SelfBuildContinuation:
    """Advance recurrence only from explicit stage-completion evidence."""
    completed = continuation.completed_stages | frozenset(newly_completed)
    ready = ready_recurrence_stages(completed, stages=continuation.stages)
    lanes = tuple(
        SelfBuildLane(
            name=f"{stage.name}:{continuation.next_gap}",
            requires=stage.requires,
            weight=stage.weight,
            redundancy=stage.redundancy,
        )
        for stage in ready
    )
    pool = tuple(default_self_build_resources() if resources is None else resources)
    federation = plan_federated_self_build(lanes, pool)
    return SelfBuildContinuation(
        next_gap=continuation.next_gap,
        source_completion_id=continuation.source_completion_id,
        continuation_handoff_id=continuation.continuation_handoff_id,
        stages=continuation.stages,
        completed_stages=completed,
        ready_stages=tuple(stage.name for stage in ready),
        federation=federation,
        ledger=continuation.ledger,
    )


def recurrence_field(continuation: SelfBuildContinuation) -> Field:
    """Merge recurrence, durable handoff, and resource-federation state into Field."""
    field = ledger_field(continuation.ledger)
    resource_pool = default_self_build_resources()
    ready = [stage for stage in continuation.stages if stage.name in continuation.ready_stages]
    lanes = tuple(
        SelfBuildLane(
            name=f"{stage.name}:{continuation.next_gap}",
            requires=stage.requires,
            weight=stage.weight,
            redundancy=stage.redundancy,
        )
        for stage in ready
    )
    field = field.merge(federation_field(lanes, resource_pool, continuation.federation))
    field.add(
        "view",
        {
            "name": "aurum-self-build-recurrence",
            "next_gap": continuation.next_gap,
            "source_completion_id": continuation.source_completion_id,
            "continuation_handoff_id": continuation.continuation_handoff_id,
            "completed_stages": sorted(continuation.completed_stages),
            "ready_stages": list(continuation.ready_stages),
            "active_resources": list(continuation.federation.active_resources),
            "timer_dependency": False,
            "promotion_before_verification": False,
        },
    )
    return field


__all__ = [
    "RecurrenceStage",
    "SELF_BUILD_ORCHESTRATOR",
    "SelfBuildContinuation",
    "advance_self_build",
    "continue_self_build",
    "ready_recurrence_stages",
    "recurrence_field",
    "recurrence_pipeline",
]
