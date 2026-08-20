from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from capacity_mesh import AssignmentPlan, Node, WorkItem, assign_parallel


MESH_EFFICIENCY_REVISION = "aurum-mesh-efficiency-v3"
_ALLOWED_POSTURES = frozenset({"safe", "adventurous", "verify"})
_ALLOWED_RUNNERS = frozenset({"ubuntu-latest", "ubuntu-24.04-arm", "windows-latest"})
_ALLOWED_SUITES = frozenset({"core", "broad", "verification", "portability"})
_REQUIRED_WORK_TYPES = frozenset(
    {
        "container-build",
        "cached-build",
        "unit-test-shard",
        "verification-shard",
        "vm-topology-verification",
        "artifact-convergence",
    }
)
_ALLOWED_ARCHITECTURES = frozenset({"x86_64", "arm64", "multi-architecture"})


@dataclass(frozen=True)
class CandidatePath:
    name: str
    posture: str
    requires: frozenset[str]
    weight: int = 1
    runner: str = "ubuntu-latest"
    suite: str = "core"
    shard_index: int = 0
    shard_count: int = 1
    work_type: str = "unit-test-shard"
    architecture: str = "x86_64"
    execution_environment: str = "github-hosted-runner"
    artifact_role: str = "test-evidence"
    may_mutate_physical_state: bool = False


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
    validate_work_classes(policy)
    limits = policy.get("limits", {})
    maximum = max(1, int(limits.get("max_speculative_paths_per_gap", 4)))
    raw = policy.get("candidate_paths", ())
    paths: list[CandidatePath] = []
    seen_names: set[str] = set()
    seen_shards: set[tuple[str, str, int, int]] = set()
    safe_count = 0
    verifier_count = 0
    for item in raw:
        name = str(item["name"])
        posture = str(item["posture"])
        runner = str(item["runner"])
        suite = str(item["suite"])
        shard_index = int(item.get("shard_index", 0))
        shard_count = int(item.get("shard_count", 1))
        work_type = str(item.get("work_type", ""))
        architecture = str(item.get("architecture", ""))
        execution_environment = str(item.get("execution_environment", ""))
        artifact_role = str(item.get("artifact_role", ""))
        may_mutate_physical_state = bool(item.get("may_mutate_physical_state", False))
        if name in seen_names:
            raise ValueError(f"duplicate candidate path: {name}")
        if posture not in _ALLOWED_POSTURES:
            raise ValueError(f"unsupported posture: {posture}")
        if runner not in _ALLOWED_RUNNERS:
            raise ValueError(f"unsupported runner: {runner}")
        if suite not in _ALLOWED_SUITES:
            raise ValueError(f"unsupported suite: {suite}")
        if work_type not in _REQUIRED_WORK_TYPES:
            raise ValueError(f"unsupported work type: {work_type}")
        if architecture not in _ALLOWED_ARCHITECTURES:
            raise ValueError(f"unsupported architecture: {architecture}")
        if not execution_environment or not artifact_role:
            raise ValueError(f"incomplete work metadata for {name}")
        if runner == "ubuntu-24.04-arm" and architecture != "arm64":
            raise ValueError(f"ARM runner has non-ARM evidence: {name}")
        if runner != "ubuntu-24.04-arm" and architecture == "arm64":
            raise ValueError(f"ARM evidence is assigned to a non-ARM runner: {name}")
        if may_mutate_physical_state:
            raise ValueError(f"hosted candidate may not mutate physical state: {name}")
        if shard_count < 1 or shard_index < 0 or shard_index >= shard_count:
            raise ValueError(f"invalid shard contract for {name}: {shard_index}/{shard_count}")
        shard_key = (runner, suite, shard_index, shard_count)
        if shard_key in seen_shards:
            raise ValueError(f"duplicate shard contract: {runner}:{suite}:{shard_index}/{shard_count}")
        path = CandidatePath(
            name=name,
            posture=posture,
            requires=frozenset(str(value) for value in item.get("requires", ())),
            weight=int(item.get("weight", 1)),
            runner=runner,
            suite=suite,
            shard_index=shard_index,
            shard_count=shard_count,
            work_type=work_type,
            architecture=architecture,
            execution_environment=execution_environment,
            artifact_role=artifact_role,
            may_mutate_physical_state=may_mutate_physical_state,
        )
        paths.append(path)
        seen_names.add(name)
        seen_shards.add(shard_key)
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


def validate_work_classes(policy: Mapping[str, Any]) -> None:
    work_classes = policy.get("work_classes", {})
    if not isinstance(work_classes, Mapping):
        raise ValueError("mesh work_classes must be a mapping")
    missing = _REQUIRED_WORK_TYPES - set(str(name) for name in work_classes)
    if missing:
        raise ValueError(f"mesh work classes are missing: {sorted(missing)}")
    for name in sorted(_REQUIRED_WORK_TYPES):
        definition = work_classes[name]
        if not isinstance(definition, Mapping):
            raise ValueError(f"invalid work class: {name}")
        architectures = {str(value) for value in definition.get("architectures", ())}
        if not architectures or not architectures.issubset(_ALLOWED_ARCHITECTURES):
            raise ValueError(f"invalid architecture metadata for work class: {name}")
        if not definition.get("execution_environment") or not definition.get("artifact_role"):
            raise ValueError(f"incomplete work class metadata: {name}")


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
                provider=str(item.get("kind", name)),
                architecture=str(item.get("architecture", "any")),
                available=(
                    name in available_names
                    if available_names is not None
                    else item.get("availability", "available") == "available"
                ),
                expected_queue_seconds=max(0, int(item.get("expected_queue_seconds", 0))),
                estimated_runtime_seconds=max(0, int(item.get("estimated_runtime_seconds", 0))),
                cache_locality=float(item.get("cache_locality", 0.0)),
                external_cost_class=str(item.get("external_cost_class", "free")),
                verification_strength=max(0, int(item.get("verification_strength", 0))),
                authority_level=str(item.get("authority_level", "BUILD-ONLY")),
                authority_levels=frozenset(str(value) for value in item.get("authority_levels", ())),
                trust_level=max(0, int(item.get("trust_level", 0))),
                safe=bool(item.get("safe", True)),
                intent_compatible=bool(item.get("intent_compatible", True)),
                optional=bool(item.get("optional", False)),
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
    duplicate_work_total: int | None = None,
    target_slot_utilization: float = 0.85,
    maximum_duplicate_work_fraction: float = 0.05,
) -> MeshEfficiencySnapshot:
    total_capacity = sum(max(0, node.capacity) for node in nodes)
    assigned_slots = sum(len(items) for items in plan.assignments.values())
    useful_parallelism = min(max(0, work_count), total_capacity)
    denominator = useful_parallelism or 1
    utilization = min(1.0, assigned_slots / denominator)
    duplicate_denominator = work_count if duplicate_work_total is None else duplicate_work_total
    duplicate_fraction = duplicate_work_items / max(1, duplicate_denominator)
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
                "shard_index": path.shard_index,
                "shard_count": path.shard_count,
                "work_type": path.work_type,
                "architecture": path.architecture,
                "execution_environment": path.execution_environment,
                "artifact_role": path.artifact_role,
                "may_mutate_physical_state": path.may_mutate_physical_state,
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
    "validate_work_classes",
]
