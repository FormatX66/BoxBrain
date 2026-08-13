from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from field_native_batch import NativeBatchItem
from field_native_vm import compile_native
from native_batch_cost import estimate_native_batch_cost
from native_work_cost import estimate_native_work


PARTITION_REVISION = "aurum-native-batch-partition-v0"


@dataclass(frozen=True)
class NativeBatchLane:
    index: int
    items: tuple[str, ...]
    total_units: int


@dataclass(frozen=True)
class NativeBatchPartition:
    lanes: tuple[NativeBatchLane, ...]
    total_units: int
    max_lane_units: int
    min_lane_units: int
    requested_parallelism: int


def partition_native_batch(
    items: Iterable[NativeBatchItem],
    *,
    parallelism: int | None = None,
    max_parallelism: int = 8,
    target_units_per_worker: int = 256,
) -> NativeBatchPartition:
    """Balance native candidate work into deterministic pre-claim lanes.

    This is only a work partition. It does not choose nodes, grant authority, or
    execute candidates. Largest-cost items are placed first into the lightest lane.
    """
    ordered = tuple(sorted(items, key=lambda item: item.name))
    if not ordered:
        raise ValueError("native batch partition requires at least one item")

    estimate = estimate_native_batch_cost(
        ordered,
        max_parallelism=max_parallelism,
        target_units_per_worker=target_units_per_worker,
    )
    lane_count = estimate.recommended_parallelism if parallelism is None else parallelism
    if lane_count <= 0:
        raise ValueError("parallelism must be positive")
    lane_count = min(lane_count, len(ordered), max_parallelism)

    weighted: list[tuple[int, str]] = []
    for item in ordered:
        program = compile_native(item.parameters, item.expression)
        cost = estimate_native_work(program, item.examples)
        weighted.append((cost.total_units, item.name))
    weighted.sort(key=lambda pair: (-pair[0], pair[1]))

    lane_items: list[list[str]] = [[] for _ in range(lane_count)]
    lane_units = [0 for _ in range(lane_count)]
    for units, name in weighted:
        index = min(range(lane_count), key=lambda lane: (lane_units[lane], lane))
        lane_items[index].append(name)
        lane_units[index] += units

    lanes = tuple(
        NativeBatchLane(
            index=index,
            items=tuple(lane_items[index]),
            total_units=lane_units[index],
        )
        for index in range(lane_count)
    )
    return NativeBatchPartition(
        lanes=lanes,
        total_units=sum(lane_units),
        max_lane_units=max(lane_units),
        min_lane_units=min(lane_units),
        requested_parallelism=lane_count,
    )


__all__ = [
    "PARTITION_REVISION",
    "NativeBatchLane",
    "NativeBatchPartition",
    "partition_native_batch",
]
