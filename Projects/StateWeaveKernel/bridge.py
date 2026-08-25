"""Generation-0 bridge between StateWeave and Adaptive Kernel.

The bridge consumes StateWeave state and returns an in-memory StateWeave result
that describes an Adaptive Kernel plan. It has no authority to alter a real OS.

Future Branch integration keeps the experiment boundaries explicit: Adaptive
Kernel emits candidate proposals, StateWeave records them, and this bridge only
translates between the two. It does not rank/promote candidates. Each translated
branch is bound to the StateWeave digest it was derived from so a later verified
state change can expire stale speculative futures without erasing their evidence.
"""

from __future__ import annotations

from typing import Iterable

from Projects.AdaptiveKernel.adaptive_kernel import (
    CapabilityRule,
    KernelPlan,
    future_branch_proposals,
    plan,
)
from Projects.StateWeave.stateweave import (
    BranchEvidenceRecord,
    BranchRecord,
    State,
    Transition,
    record_branch_set,
)

FACT_PREFIX = "fact."
CAPABILITY_PREFIX = "kernel.capability."


def facts_from_state(state: State) -> dict[str, bool]:
    facts: dict[str, bool] = {}
    for key, value in state.values:
        if key.startswith(FACT_PREFIX) and isinstance(value, bool):
            facts[key[len(FACT_PREFIX):]] = value
    return facts


def plan_from_state(
    state: State,
    rules: Iterable[CapabilityRule],
    *,
    threshold: float = 1.0,
) -> KernelPlan:
    return plan(facts_from_state(state), rules, threshold=threshold)


def future_branches_from_state(
    state: State,
    rules: Iterable[CapabilityRule],
    *,
    rollback_target: str = "current-proven-kernel",
) -> tuple[dict, ...]:
    """Translate StateWeave facts into warm kernel Future Branch proposals."""

    return future_branch_proposals(
        facts_from_state(state),
        rules,
        rollback_target=rollback_target,
    )


def _record_from_proposal(proposal: dict, *, basis_state_digest: str | None = None) -> BranchRecord:
    evidence = tuple(
        BranchEvidenceRecord(
            ref=item["ref"],
            weight=float(item.get("weight", 1.0)),
            quality=float(item.get("quality", 1.0)),
            supports=bool(item.get("supports", True)),
        )
        for item in proposal.get("evidence", ())
    )
    return BranchRecord(
        branch_id=str(proposal["branch_id"]),
        proposed_state=str(proposal["proposed_state"]),
        confidence=float(proposal["confidence"]),
        risk=float(proposal["risk"]),
        reversibility=str(proposal.get("reversibility", "full")),
        status=str(proposal.get("status", "warm")),
        evidence=evidence,
        rollback_target=proposal.get("rollback_target"),
        is_last_known_good=bool(proposal.get("is_last_known_good", False)),
        basis_state_digest=basis_state_digest,
    )


def describe_future_branches_in_state(
    state: State,
    proposals: Iterable[dict],
) -> State:
    """Persist the auditable candidate field without declaring a winner."""

    basis = state.digest()
    return record_branch_set(
        state,
        (_record_from_proposal(item, basis_state_digest=basis) for item in proposals),
    )


def describe_plan_in_state(state: State, kernel_plan: KernelPlan) -> State:
    writes: dict[str, bool | int | float | str | None] = {}
    for candidate in kernel_plan.selected:
        for capability in candidate.rule.provides:
            writes[f"{CAPABILITY_PREFIX}{capability}"] = True
    writes["kernel.plan.selected_count"] = len(kernel_plan.selected)
    writes["kernel.plan.rejected_count"] = len(kernel_plan.rejected)
    transition = Transition.build("adaptive-kernel-plan", writes=writes)
    return transition.apply(state)
