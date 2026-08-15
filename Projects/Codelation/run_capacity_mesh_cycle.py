from __future__ import annotations

import argparse
import json
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
        modules = suite_test_modules(path.suite)
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
        maximum_duplicate_work_fraction=float(
            limits.get("maximum_duplicate_work_fraction", 0.05)
        ),
    )
    return {
        "schema": "aurum-capacity-mesh-audit-v1",
        "candidate_paths": [path.name for path in paths],
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
        "target_met": snapshot.target_met,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--github-matrix", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    policy = load_policy(args.policy)
    if args.github_matrix:
        print(json.dumps(github_matrix_from_policy(policy), separators=(",", ":")))
        return 0
    audit = policy_audit(policy)
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0 if audit["target_met"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
