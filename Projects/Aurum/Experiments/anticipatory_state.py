"""Non-production experiment for Aurum anticipatory next-state preparation.

The experiment ranks plausible next human intents and allocates only reclaimable
idle capacity. It may recommend speculative preparation, but it never authorizes
an external action or mutates the active/LKG state.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CandidateIntent:
    name: str
    probability: float
    human_value: float
    latency_saved_ms: int
    cpu_cost: float
    ram_mb: int
    storage_write_mb: int = 0
    privacy_cost: float = 0.0

    def validate(self) -> None:
        if not self.name:
            raise ValueError("intent name required")
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError("probability must be between 0 and 1")
        if self.human_value < 0 or self.latency_saved_ms < 0:
            raise ValueError("value and latency saved must be non-negative")
        if self.cpu_cost < 0 or self.ram_mb < 0 or self.storage_write_mb < 0 or self.privacy_cost < 0:
            raise ValueError("resource/privacy costs must be non-negative")


@dataclass(frozen=True)
class ResourceBudget:
    idle_cpu_capacity: float
    free_ram_mb: int
    foreground_ram_reserve_mb: int
    storage_write_budget_mb: int
    max_privacy_cost: float

    def validate(self) -> None:
        if not 0.0 <= self.idle_cpu_capacity <= 1.0:
            raise ValueError("idle_cpu_capacity must be between 0 and 1")
        if min(self.free_ram_mb, self.foreground_ram_reserve_mb, self.storage_write_budget_mb) < 0:
            raise ValueError("resource budgets must be non-negative")
        if self.max_privacy_cost < 0:
            raise ValueError("privacy budget must be non-negative")


@dataclass(frozen=True)
class SpeculationPolicy:
    """How aggressively to fill otherwise-idle resources with useful futures."""

    idle_cpu_target: float = 0.95
    reclaimable_ram_target: float = 0.90
    minimum_score: float = 0.05

    def validate(self) -> None:
        if not 0.0 <= self.idle_cpu_target <= 1.0:
            raise ValueError("idle_cpu_target must be between 0 and 1")
        if not 0.0 <= self.reclaimable_ram_target <= 1.0:
            raise ValueError("reclaimable_ram_target must be between 0 and 1")
        if self.minimum_score < 0:
            raise ValueError("minimum_score must be non-negative")


def expected_preparation_value(intent: CandidateIntent) -> float:
    intent.validate()
    benefit = intent.probability * intent.human_value * (1.0 + intent.latency_saved_ms / 1000.0)
    cost = 1.0 + intent.cpu_cost + intent.ram_mb / 1024.0 + intent.storage_write_mb / 512.0 + intent.privacy_cost
    return benefit / cost


def build_speculative_plan(
    intents: Iterable[CandidateIntent],
    budget: ResourceBudget,
    policy: SpeculationPolicy | None = None,
) -> dict:
    """Rank branches and fill reclaimable idle resources with useful futures.

    CPU cost is modeled as a fraction of one normalized idle-capacity pool. RAM
    may use only free RAM above the foreground reserve. The policy intentionally
    targets most-but-not-all idle CPU and reclaimable RAM/Slush while retaining
    immediate foreground headroom. Low-value work is not admitted merely to make
    utilization appear high. Storage writes remain separately budgeted to avoid
    speculative SSD churn.
    """
    budget.validate()
    policy = policy or SpeculationPolicy()
    policy.validate()
    candidates = list(intents)
    for intent in candidates:
        intent.validate()

    ranked = sorted(
        candidates,
        key=lambda item: (-expected_preparation_value(item), item.name),
    )
    total_reclaimable_ram = max(0, budget.free_ram_mb - budget.foreground_ram_reserve_mb)
    cpu_budget = budget.idle_cpu_capacity * policy.idle_cpu_target
    ram_budget = int(total_reclaimable_ram * policy.reclaimable_ram_target)
    cpu_left = cpu_budget
    ram_left = ram_budget
    storage_left = budget.storage_write_budget_mb
    prepared: list[dict] = []
    held: list[dict] = []

    for intent in ranked:
        score = expected_preparation_value(intent)
        reason = None
        if score < policy.minimum_score:
            reason = "insufficient-future-value"
        elif intent.privacy_cost > budget.max_privacy_cost:
            reason = "privacy-budget"
        elif intent.cpu_cost > cpu_left:
            reason = "foreground-cpu-reserve"
        elif intent.ram_mb > ram_left:
            reason = "foreground-ram-reserve"
        elif intent.storage_write_mb > storage_left:
            reason = "storage-write-budget"

        record = {
            "intent": intent.name,
            "score": round(score, 6),
            "probability": intent.probability,
            "prepare_only": True,
            "action_allowed": False,
        }
        if reason:
            record["held_reason"] = reason
            held.append(record)
            continue

        cpu_left -= intent.cpu_cost
        ram_left -= intent.ram_mb
        storage_left -= intent.storage_write_mb
        if score >= 2.0:
            depth = "deep"
        elif score >= 0.5:
            depth = "medium"
        else:
            depth = "shallow"
        record["preparation_depth"] = depth
        prepared.append(record)

    cpu_used = cpu_budget - cpu_left
    ram_used = ram_budget - ram_left
    return {
        "schema": "aurum-anticipatory-state-plan-v1",
        "mode": "anticipating-not-interfering",
        "policy": {
            "idle_cpu_target": policy.idle_cpu_target,
            "reclaimable_ram_target": policy.reclaimable_ram_target,
            "minimum_score": policy.minimum_score,
        },
        "prepared": prepared,
        "held": held,
        "utilization": {
            "speculative_cpu_budget": round(cpu_budget, 6),
            "speculative_cpu_used": round(cpu_used, 6),
            "speculative_cpu_fill": 0.0 if cpu_budget == 0 else round(cpu_used / cpu_budget, 6),
            "reclaimable_ram_budget_mb": ram_budget,
            "reclaimable_ram_used_mb": ram_used,
            "reclaimable_ram_fill": 0.0 if ram_budget == 0 else round(ram_used / ram_budget, 6),
        },
        "remaining": {
            "idle_cpu_capacity": round(cpu_left, 6),
            "reclaimable_ram_mb": ram_left,
            "storage_write_budget_mb": storage_left,
        },
        "external_action_allowed": False,
        "active_state_mutation_allowed": False,
        "lkg_mutation_allowed": False,
    }
