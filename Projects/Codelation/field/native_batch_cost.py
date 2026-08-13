from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Iterable

from field_native_batch import NativeBatchItem
from field_native_vm import compile_native
from native_work_cost import estimate_native_work


BATCH_COST_REVISION = "aurum-native-batch-cost-v0"


@dataclass(frozen=True)
class NativeBatchItemCost:
    name: str
    total_units: int
    scheduling_class: str
    unique_examples: int


@dataclass(frozen=True)
class NativeBatchCost:
    items: tuple[NativeBatchItemCost, ...]
    total_units: int
    max_item_units: int
    recommended_parallelism: int
    max_parallelism: int
    target_units_per_worker: int


def estimate_native_batch_cost(
    items: Iterable[NativeBatchItem],
    *,
    max_parallelism: int = 8,
    target_units_per_worker: int = 256,
) -> NativeBatchCost:
    """Estimate bounded parallelism for a native batch without launching workers."""
    if max_parallelism <= 0:
        raise ValueError("max_parallelism must be positive")
    if target_units_per_worker <= 0:
        raise ValueError("target_units_per_worker must be positive")
    ordered = tuple(sorted(items, key=lambda item: item.name))
    if not ordered:
        raise ValueError("native batch cost requires at least one item")

    costs: list[NativeBatchItemCost] = []
    total = 0
    maximum = 0
    for item in ordered:
        program = compile_native(item.parameters, item.expression)
        cost = estimate_native_work(program, item.examples)
        costs.append(
            NativeBatchItemCost(
                name=item.name,
                total_units=cost.total_units,
                scheduling_class=cost.scheduling_class,
                unique_examples=cost.unique_examples,
            )
        )
        total += cost.total_units
        maximum = max(maximum, cost.total_units)

    desired = max(1, ceil(total / target_units_per_worker))
    recommended = min(max_parallelism, len(ordered), desired)
    return NativeBatchCost(
        items=tuple(costs),
        total_units=total,
        max_item_units=maximum,
        recommended_parallelism=recommended,
        max_parallelism=max_parallelism,
        target_units_per_worker=target_units_per_worker,
    )


__all__ = [
    "BATCH_COST_REVISION",
    "NativeBatchCost",
    "NativeBatchItemCost",
    "estimate_native_batch_cost",
]
