"""Deterministic benchmark for Future Branch latency reduction.

This experiment compares a purely reactive computer with a Future Branch system
that spends only an idle/speculation window preparing likely futures before the
actual branch is known. It measures human wait saved plus both gross speculative
work and modeled long-horizon value that survives a near-term branch miss.

It is deliberately non-production: no external actions, state mutation, or LKG
promotion occurs here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CandidateFuture:
    name: str
    probability: float
    work_ms: int
    human_value: float = 1.0
    reusable_fraction: float = 0.0
    learning_credit_ms: int = 0
    avoided_error_credit_ms: int = 0

    def validate(self) -> None:
        if not self.name:
            raise ValueError("future name required")
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError("probability must be between 0 and 1")
        if not 0.0 <= self.reusable_fraction <= 1.0:
            raise ValueError("reusable_fraction must be between 0 and 1")
        if self.work_ms < 0:
            raise ValueError("work_ms must be non-negative")
        if self.human_value < 0:
            raise ValueError("human_value must be non-negative")
        if self.learning_credit_ms < 0 or self.avoided_error_credit_ms < 0:
            raise ValueError("long-horizon credits must be non-negative")


def preparation_priority(future: CandidateFuture) -> float:
    """Expected human-facing and compounding value of speculative preparation."""
    future.validate()
    if future.work_ms == 0:
        return float("inf")
    direct = future.probability * future.human_value
    compound = future.reusable_fraction + (
        future.learning_credit_ms + future.avoided_error_credit_ms
    ) / max(future.work_ms, 1)
    return direct + compound


def prepare_futures(
    futures: Iterable[CandidateFuture],
    *,
    idle_window_ms: int,
    breadth_limit: int | None = None,
) -> dict[str, int]:
    """Spend the idle window on the highest-value likely futures.

    The model is intentionally single-normalized-worker. Parallel hardware can be
    represented by increasing the idle window or running independent pools. Work
    is preemptible and may be partially prepared.
    """
    if idle_window_ms < 0:
        raise ValueError("idle_window_ms must be non-negative")
    values = list(futures)
    for item in values:
        item.validate()
    if breadth_limit is not None and breadth_limit < 1:
        raise ValueError("breadth_limit must be positive")

    ranked = sorted(values, key=lambda item: (-preparation_priority(item), item.name))
    if breadth_limit is not None:
        ranked = ranked[:breadth_limit]

    remaining = idle_window_ms
    prepared: dict[str, int] = {item.name: 0 for item in values}
    for item in ranked:
        if remaining <= 0:
            break
        amount = min(item.work_ms, remaining)
        prepared[item.name] = amount
        remaining -= amount
    return prepared


def _long_horizon_credit_ms(
    values: list[CandidateFuture],
    prepared: dict[str, int],
    *,
    actual: str,
) -> dict[str, int]:
    reusable = 0
    learning = 0
    avoided_errors = 0
    for item in values:
        amount = prepared[item.name]
        if amount <= 0:
            continue
        fraction_prepared = 0.0 if item.work_ms == 0 else amount / item.work_ms
        if item.name != actual:
            reusable += round(amount * item.reusable_fraction)
        learning += round(item.learning_credit_ms * fraction_prepared)
        avoided_errors += round(item.avoided_error_credit_ms * fraction_prepared)
    return {
        "reusable_nonactual_ms": reusable,
        "learning_credit_ms": learning,
        "avoided_error_credit_ms": avoided_errors,
        "total_long_horizon_credit_ms": reusable + learning + avoided_errors,
    }


def benchmark_decision(
    futures: Iterable[CandidateFuture],
    *,
    actual: str,
    idle_window_ms: int,
    breadth_limit: int | None = None,
) -> dict:
    """Compare reactive wait with Future Branch wait for one resolved decision."""
    values = list(futures)
    by_name = {item.name: item for item in values}
    if len(by_name) != len(values):
        raise ValueError("future names must be unique")
    if actual not in by_name:
        raise ValueError("actual branch must exist in futures")

    prepared = prepare_futures(values, idle_window_ms=idle_window_ms, breadth_limit=breadth_limit)
    actual_future = by_name[actual]
    reactive_wait_ms = actual_future.work_ms
    useful_prepared_ms = prepared[actual]
    future_branch_wait_ms = max(0, actual_future.work_ms - useful_prepared_ms)
    total_speculative_ms = sum(prepared.values())
    gross_nonactual_ms = total_speculative_ms - useful_prepared_ms
    wait_saved_ms = reactive_wait_ms - future_branch_wait_ms
    credits = _long_horizon_credit_ms(values, prepared, actual=actual)
    net_waste_ms = max(0, gross_nonactual_ms - credits["total_long_horizon_credit_ms"])

    return {
        "schema": "aurum-future-branch-benchmark-v2",
        "actual": actual,
        "reactive_wait_ms": reactive_wait_ms,
        "future_branch_wait_ms": future_branch_wait_ms,
        "wait_saved_ms": wait_saved_ms,
        "wait_saved_fraction": 0.0 if reactive_wait_ms == 0 else round(wait_saved_ms / reactive_wait_ms, 6),
        "speculative_work_ms": total_speculative_ms,
        "useful_speculative_ms": useful_prepared_ms,
        "gross_nonactual_speculative_ms": gross_nonactual_ms,
        **credits,
        "net_speculative_waste_ms": net_waste_ms,
        "immediate_speculation_efficiency": 0.0 if total_speculative_ms == 0 else round(useful_prepared_ms / total_speculative_ms, 6),
        "long_horizon_value_fraction": 0.0 if total_speculative_ms == 0 else round(min(total_speculative_ms, useful_prepared_ms + credits["total_long_horizon_credit_ms"]) / total_speculative_ms, 6),
        "prepared": prepared,
        "foreground_regression_ms": 0,
        "active_state_mutation_allowed": False,
        "lkg_mutation_allowed": False,
    }


def benchmark_suite(cases: Iterable[dict]) -> dict:
    """Aggregate deterministic decision cases into a human-latency report."""
    results = [benchmark_decision(**case) for case in cases]
    reactive = sum(item["reactive_wait_ms"] for item in results)
    anticipated = sum(item["future_branch_wait_ms"] for item in results)
    saved = sum(item["wait_saved_ms"] for item in results)
    speculative = sum(item["speculative_work_ms"] for item in results)
    gross_nonactual = sum(item["gross_nonactual_speculative_ms"] for item in results)
    long_credit = sum(item["total_long_horizon_credit_ms"] for item in results)
    net_waste = sum(item["net_speculative_waste_ms"] for item in results)
    return {
        "schema": "aurum-future-branch-benchmark-suite-v2",
        "cases": len(results),
        "reactive_wait_ms": reactive,
        "future_branch_wait_ms": anticipated,
        "wait_saved_ms": saved,
        "wait_saved_fraction": 0.0 if reactive == 0 else round(saved / reactive, 6),
        "speculative_work_ms": speculative,
        "gross_nonactual_speculative_ms": gross_nonactual,
        "total_long_horizon_credit_ms": long_credit,
        "net_speculative_waste_ms": net_waste,
        "foreground_regression_ms": sum(item["foreground_regression_ms"] for item in results),
        "results": results,
    }
