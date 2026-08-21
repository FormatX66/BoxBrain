"""Generation-0 bridge between StateWeave and Adaptive Kernel.

The bridge consumes StateWeave state and returns an in-memory StateWeave result
that describes an Adaptive Kernel plan. It has no authority to alter a real OS.
"""

from __future__ import annotations

from typing import Iterable

from Projects.AdaptiveKernel.adaptive_kernel import CapabilityRule, KernelPlan, plan
from Projects.StateWeave.stateweave import State, Transition

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


def describe_plan_in_state(state: State, kernel_plan: KernelPlan) -> State:
    writes: dict[str, bool | int | float | str | None] = {}
    for candidate in kernel_plan.selected:
        for capability in candidate.rule.provides:
            writes[f"{CAPABILITY_PREFIX}{capability}"] = True
    writes["kernel.plan.selected_count"] = len(kernel_plan.selected)
    writes["kernel.plan.rejected_count"] = len(kernel_plan.rejected)
    transition = Transition.build("adaptive-kernel-plan", writes=writes)
    return transition.apply(state)
