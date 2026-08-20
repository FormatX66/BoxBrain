from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIELD = ROOT / "field"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(FIELD) not in sys.path:
    sys.path.insert(0, str(FIELD))

from mesh_efficiency import (  # noqa: E402
    assess_efficiency,
    candidate_paths_from_policy,
    github_matrix_from_policy,
    nodes_from_policy,
    plan_candidate_paths,
)
from run_capacity_mesh_lane import suite_test_modules  # noqa: E402


DEFAULT_POLICY = ROOT / "autobuild" / "capacity_mesh_policy.json"


def load_policy(path: Path) -> dict:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("schema") != "aurum-capacity-mesh-policy-v1":
        raise ValueError("unsupported capacity mesh policy schema")
    return policy


def duplicate_test_work(paths) -> tuple[int, int]:
    seen_by_runner: dict[str, set[str]] = {}
    duplicate_work_items = 0
    total_work_items = 0
    for path in paths:
        modules = suite_test_modules(
            path.suite,
            shard_index=path.shard_index,
            shard_count=path.shard_count,
        )
        total_work_items += len(modules)
        seen = seen_by_runner.setdefault(path.runner, set())
        duplicate_work_items += sum(module in seen for module in modules)
        seen.update(modules)
    return duplicate_work_items, total_work_items


def policy_audit(policy: dict) -> dict:
    paths = candidate_paths_from_policy(policy)
    available = [
        node["name"]
        for node in policy.get("nodes", ())
        if node.get("availability") != "fresh-heartbeat-required"
    ]
    nodes = nodes_from_policy(policy, available=available)
    plan = plan_candidate_paths(paths, nodes)
    duplicate_work_items, duplicate_work_total = duplicate_test_work(paths)
    limits = policy.get("limits", {})
    snapshot = assess_efficiency(
        plan,
        nodes,
        work_count=len(paths),
        duplicate_work_items=duplicate_work_items,
        duplicate_work_total=duplicate_work_total,
        target_slot_utilization=float(limits.get("target_slot_utilization", 0.85)),
        maximum_duplicate_work_fraction=float(limits.get("maximum_duplicate_work_fraction", 0.05)),
    )
    matrix = github_matrix_from_policy(policy)
    work_type_counts: dict[str, int] = {}
    architecture_counts: dict[str, int] = {}
    for path in paths:
        work_type_counts[path.work_type] = work_type_counts.get(path.work_type, 0) + 1
        architecture_counts[path.architecture] = architecture_counts.get(path.architecture, 0) + 1
    return {
        "schema": "aurum-capacity-mesh-audit-v2",
        "candidate_paths": [path.name for path in paths],
        "matrix_lane_count": len(matrix.get("include", ())),
        "available_nodes": [node.name for node in nodes],
        "assignments": {name: list(items) for name, items in plan.assignments.items()},
        "unassigned": list(plan.unassigned),
        "missing_capabilities": sorted(plan.missing_capabilities),
        "total_capacity": snapshot.total_capacity,
        "assigned_slots": snapshot.assigned_slots,
        "useful_parallelism": snapshot.useful_parallelism,
        "slot_utilization": snapshot.slot_utilization,
        "idle_capacity": snapshot.idle_capacity,
        "duplicate_work_items": duplicate_work_items,
        "duplicate_work_total": duplicate_work_total,
        "duplicate_work_fraction": snapshot.duplicate_work_fraction,
        "work_type_counts": work_type_counts,
        "architecture_counts": architecture_counts,
        "target_met": snapshot.target_met,
    }


def converge_lane_results(policy: dict, results: list[dict], *, source_sha: str) -> dict:
    """Fail closed unless every planned lane returns identity-bound evidence."""
    if not re.fullmatch(r"[0-9a-f]{40,64}", source_sha):
        raise ValueError("capacity mesh source_sha must be a full Git object identity")
    expected = {path.name: path for path in candidate_paths_from_policy(policy)}
    observed: dict[str, dict] = {}
    for result in results:
        name = str(result.get("name", ""))
        if name not in expected:
            raise ValueError(f"unexpected capacity mesh lane result: {name}")
        if name in observed:
            raise ValueError(f"duplicate capacity mesh lane result: {name}")
        if result.get("schema") != "aurum-capacity-mesh-lane-result-v3":
            raise ValueError(f"unsupported lane evidence schema: {name}")
        path = expected[name]
        comparisons = {
            "posture": path.posture,
            "suite": path.suite,
            "shard_index": path.shard_index,
            "shard_count": path.shard_count,
            "work_type": path.work_type,
            "architecture": path.architecture,
            "execution_environment": path.execution_environment,
            "artifact_role": path.artifact_role,
            "source_sha": source_sha,
        }
        for field, value in comparisons.items():
            if result.get(field) != value:
                raise ValueError(f"lane evidence mismatch for {name}: {field}")
        if result.get("state_authority") != "ephemeral-github-runner":
            raise ValueError(f"lane escaped ephemeral authority: {name}")
        if result.get("physical_state_mutated"):
            raise ValueError(f"speculative lane mutated trusted physical state: {name}")
        if bool(result.get("verified")) != (result.get("returncode") == 0):
            raise ValueError(f"lane verification and return code disagree: {name}")
        if "command" in result or "remote_command" in result:
            raise ValueError(f"arbitrary command evidence is forbidden: {name}")
        observed[name] = result

    missing = sorted(set(expected) - set(observed))
    if missing:
        raise ValueError(f"capacity mesh evidence is incomplete: {missing}")
    failed_mandatory = sorted(
        name
        for name, path in expected.items()
        if path.posture in {"safe", "verify"} and not observed[name].get("verified")
    )
    if failed_mandatory:
        raise ValueError(f"mandatory capacity mesh lanes failed: {failed_mandatory}")

    verified = [result for result in observed.values() if result.get("verified")]
    architectures = {str(result["architecture"]) for result in verified}
    if policy.get("fan_in", {}).get("require_cross_architecture_evidence") and not {
        "x86_64",
        "arm64",
    }.issubset(architectures):
        raise ValueError("verified fan-in lacks distinct x86_64 and ARM64 evidence")
    return {
        "schema": "aurum-capacity-mesh-convergence-v1",
        "source_sha": source_sha,
        "planned_lane_count": len(expected),
        "evidence_lane_count": len(observed),
        "verified_lane_count": len(verified),
        "excluded_failed_adventurous_lanes": sorted(
            name
            for name, path in expected.items()
            if path.posture == "adventurous" and not observed[name].get("verified")
        ),
        "architectures": sorted(architectures),
        "work_types": sorted({str(result["work_type"]) for result in verified}),
        "physical_state_mutated": False,
        "promotion": "single-verified-evidence-path",
        "verified": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--github-matrix", action="store_true")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--converge-results", type=Path)
    parser.add_argument("--source-sha")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    policy = load_policy(args.policy)
    if args.github_matrix:
        print(json.dumps(github_matrix_from_policy(policy), separators=(",", ":")))
        return 0
    if args.converge_results is not None:
        if not args.source_sha:
            parser.error("--source-sha is required with --converge-results")
        results = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(args.converge_results.rglob("*.json"))
        ]
        convergence = converge_lane_results(policy, results, source_sha=args.source_sha)
        rendered = json.dumps(convergence, indent=2, sort_keys=True) + "\n"
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        print(rendered, end="")
        return 0
    audit = policy_audit(policy)
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0 if audit["target_met"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
