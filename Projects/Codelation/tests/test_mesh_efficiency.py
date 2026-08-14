from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "field"))

from capacity_mesh import AssignmentPlan, Node  # noqa: E402
from mesh_efficiency import (  # noqa: E402
    CandidatePath,
    assess_efficiency,
    candidate_paths_from_policy,
    github_matrix_from_policy,
    nodes_from_policy,
    plan_candidate_paths,
)


POLICY = ROOT / "autobuild" / "capacity_mesh_policy.json"


class MeshEfficiencyTests(unittest.TestCase):
    def _policy(self):
        return json.loads(POLICY.read_text(encoding="utf-8"))

    def test_policy_preserves_safe_and_verifier_paths(self):
        paths = candidate_paths_from_policy(self._policy())
        self.assertTrue(any(path.posture == "safe" for path in paths))
        self.assertTrue(any(path.posture == "verify" for path in paths))

    def test_policy_builds_bounded_github_matrix(self):
        policy = self._policy()
        matrix = github_matrix_from_policy(policy)
        self.assertLessEqual(
            len(matrix["include"]),
            policy["limits"]["max_parallel_hosted_lanes"],
        )
        self.assertEqual(
            {entry["name"] for entry in matrix["include"]},
            {path["name"] for path in policy["candidate_paths"]},
        )

    def test_parallel_paths_use_distinct_capacity(self):
        paths = (
            CandidatePath("safe", "safe", frozenset({"python"}), weight=2),
            CandidatePath("risky", "adventurous", frozenset({"python"}), weight=2),
        )
        nodes = (
            Node("node-a", frozenset({"python"}), capacity=1),
            Node("node-b", frozenset({"python"}), capacity=1),
        )
        plan = plan_candidate_paths(paths, nodes)
        self.assertEqual(set(plan.assignments), {"node-a", "node-b"})
        self.assertEqual(plan.unassigned, ())

    def test_efficiency_uses_useful_parallelism_not_raw_idle_capacity(self):
        nodes = (Node("large", frozenset({"python"}), capacity=8),)
        plan = AssignmentPlan(
            assignments={"large": ("safe", "risky")},
            unassigned=(),
            missing_capabilities=frozenset(),
        )
        snapshot = assess_efficiency(plan, nodes, work_count=2)
        self.assertEqual(snapshot.useful_parallelism, 2)
        self.assertEqual(snapshot.slot_utilization, 1.0)
        self.assertTrue(snapshot.target_met)

    def test_duplicate_work_breaks_efficiency_target(self):
        nodes = (Node("node", frozenset({"python"}), capacity=2),)
        plan = AssignmentPlan(
            assignments={"node": ("safe", "verify")},
            unassigned=(),
            missing_capabilities=frozenset(),
        )
        snapshot = assess_efficiency(
            plan,
            nodes,
            work_count=2,
            duplicate_work_items=1,
            maximum_duplicate_work_fraction=0.05,
        )
        self.assertFalse(snapshot.target_met)

    def test_fresh_heartbeat_nodes_can_be_excluded_without_inventing_presence(self):
        policy = self._policy()
        nodes = nodes_from_policy(
            policy,
            available={"github-hosted-x64", "github-hosted-arm64", "gpt-python"},
        )
        self.assertNotIn("BBPI4", {node.name for node in nodes})
        self.assertNotIn("windows-authorized-node", {node.name for node in nodes})


if __name__ == "__main__":
    unittest.main(verbosity=2)
