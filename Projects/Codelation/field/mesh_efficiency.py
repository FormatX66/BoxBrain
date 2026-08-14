from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from capacity_mesh import AssignmentPlan, Node, WorkItem, assign_parallel


MESH_EFFICIENCY_REVISION = "aurum-mesh-efficiency-v1"
_ALLOWED_POSTURES = frozenset({"safe", "adventurous", "verify"})
_ALLOWED_RUNNERS = frozenset({"ubuntu-latest", "ubuntu-24.04-arm", "windows-latest"})
_ALLOWED_SUITES = frozenset({"core", "broad", "verification", "portability"})


@dataclass(frozen=True)
class CandidatePath:
    name: str
    posture: str
    requires: frozenset[str]
    weight: int = 1
    runner: str = "ubuntu-latest"
    suite: str = "core"


@dataclass(frozen=True)
class MeshEfficiencySnapshot:
    total_capacity: int
    assigned_slots: int
    useful_parallelism: int
    slot_utilization: float
    idle_capacity: int
    unassigned_work: int
    missing_capabilities: frozenset[str]
    duplicate_work_fraction: float
    target_met: bool


def candidate_paths_from_policy(policy: Mapping[str, Any]) -> tuple[CandidatePath, ...]:
    limits = policy.get("limits", {})
    maximum = max(1, int(limits.get("max_speculative_paths_per_gap", 4)))
    raw = policy.get("candidate_paths", ())
    paths: list[CandidatePath] = []
    seen_names: set[str] = set()
    safe_count = 0
    verifier_count = 0
    for item in raw:
        name = str(item["name"])
        posture = str(item["posture"])
        runner = str(item["runner"])
        suite = str(item["suite"])
        if name in seen_names:
            raise ValueError(f"duplicate candidate path: {name}")
        if posture not in _ALLOWED_POSTURES:
            raise ValueError(f"unsupported posture: {posture}")
        if runner not in _ALLOWED_RUNNERS:
            raise ValueError(f"unsupported runner: {runner}")
        if suite not in _ALLOWED_SUITES:
            raise ValueError(f"unsupported suite: {suite}")
        path = CandidatePath(
            name=name,
            posture=posture,
            requires=frozenset(str(value) for value in item.get("requires", ())),
            weight=int(item.get("weight", 1)),
            runner=runner,
            suite=suite,
        )
        paths.append(path)
        seen_names.add(name)
        safe_count += posture == "safe"
        verifier_count += posture == "verify"
    if len(paths) > maximum:
        raise ValueError("candidate path count exceeds policy limit")
    if not safe_count:
        raise ValueError("mesh policy must retain at least one safe path")
    minimum_verifiers = int(limits.get("minimum_verifier_lanes", 1))
    if verifier_count < minimum_verifiers:
        raise ValueError("mesh policy does not provide enough verifier lanes")
    return tuple(paths)


def nodes_from_policy(policy: Mapping[str, Any], *, available: Iterable[str] | None = None) -> tuple[Node, ...]:
    available_names = set(available) if available is not None else None
    nodes: list[Node] = []
    for item in policy.get("nodes", ()):
        name = str(item["name"])
        if available_names is not None and name not in available_names:
            continue
        nodes.append(
            Node(
                name=name,
                capabilities=frozenset(str(value) for value in item.get("capabilities", ())),
                capacity=max(0, int(item.get("capacity", 0))),
                cost=int(item.get("cost", 0)),
            )
        )
    return tuple(nodes)


def plan_candidate_paths(paths: Sequence[CandidatePath], nodes: Sequence[Node]) -> AssignmentPlan:
    return assign_parallel(
        [WorkItem(path.name, path.requires, weight=path.weight) for path in paths],
        nodes,
    )


def assess_efficiency(
    plan: AssignmentPlan,
    nodes: Sequence[Node],
    *,
    work_count: int,
    duplicate_work_items: int = 0,
    target_slot_utilization: float = 0.85,
    maximum_duplicate_work_fraction: float = 0.05,
) -> MeshEfficiencySnapshot:
    total_capacity = sum(max(0, node.capacity) for node in nodes)
    assigned_slots = sum(len(items) for items in plan.assignments.values())
    useful_parallelism = min(max(0, work_count), total_capacity)
    denominator = useful_parallelism or 1
    utilization = min(1.0, assigned_slots / denominator)
    duplicate_fraction = duplicate_work_items / max(1, work_count)
    idle_capacity = max(0, total_capacity - assigned_slots)
    target_met = (
        not plan.unassigned
        and utilization >= target_slot_utilization
        and duplicate_fraction <= maximum_duplicate_work_fraction
    )
    return MeshEfficiencySnapshot(
        total_capacity=total_capacity,
        assigned_slots=assigned_slots,
        useful_parallelism=useful_parallelism,
        slot_utilization=utilization,
        idle_capacity=idle_capacity,
        unassigned_work=len(plan.unassigned),
        missing_capabilities=plan.missing_capabilities,
        duplicate_work_fraction=duplicate_fraction,
        target_met=target_met,
    )


def github_matrix_from_policy(policy: Mapping[str, Any]) -> Mapping[str, list[Mapping[str, Any]]]:
    limits = policy.get("limits", {})
    max_parallel = max(1, int(limits.get("max_parallel_hosted_lanes", 8)))
    paths = candidate_paths_from_policy(policy)
    hosted = [path for path in paths if path.runner in _ALLOWED_RUNNERS]
    if len(hosted) > max_parallel:
        hosted = sorted(hosted, key=lambda path: (-path.weight, path.name))[:max_parallel]
    return {
        "include": [
            {
                "name": path.name,
                "posture": path.posture,
                "runner": path.runner,
                "suite": path.suite,
            }
            for path in hosted
        ]
    }


__all__ = [
    "CandidatePath",
    "MESH_EFFICIENCY_REVISION",
    "MeshEfficiencySnapshot",
    "assess_efficiency",
    "candidate_paths_from_policy",
    "github_matrix_from_policy",
    "nodes_from_policy",
    "plan_candidate_paths",
]
