from __future__ import annotations

import json
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
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
from run_capacity_mesh_cycle import converge_lane_results, policy_audit  # noqa: E402
from run_capacity_mesh_lane import full_suite_test_modules, suite_test_modules  # noqa: E402


POLICY = ROOT / "autobuild" / "capacity_mesh_policy.json"


class MeshEfficiencyTests(unittest.TestCase):
    def _policy(self):
        return json.loads(POLICY.read_text(encoding="utf-8"))

    def _lane_results(self, policy, source_sha="a" * 40):
        return [
            {
                "schema": "aurum-capacity-mesh-lane-result-v3",
                "name": path.name,
                "posture": path.posture,
                "suite": path.suite,
                "work_type": path.work_type,
                "architecture": path.architecture,
                "execution_environment": path.execution_environment,
                "artifact_role": path.artifact_role,
                "source_sha": source_sha,
                "shard_index": path.shard_index,
                "shard_count": path.shard_count,
                "verified": True,
                "returncode": 0,
                "duration_seconds": 1.0,
                "state_authority": "ephemeral-github-runner",
                "physical_state_mutated": False,
            }
            for path in candidate_paths_from_policy(policy)
        ]

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
        for entry in matrix["include"]:
            self.assertIn("shard_index", entry)
            self.assertIn("shard_count", entry)
            self.assertLess(entry["shard_index"], entry["shard_count"])
            self.assertIn(entry["work_type"], {"unit-test-shard", "verification-shard"})
            self.assertIn(entry["architecture"], {"x86_64", "arm64"})
            self.assertFalse(entry["may_mutate_physical_state"])

    def test_policy_registers_build_vm_and_convergence_work_without_duplicate_scheduler(self):
        policy = self._policy()
        self.assertEqual(
            set(policy["work_classes"]),
            {
                "container-build",
                "cached-build",
                "unit-test-shard",
                "verification-shard",
                "vm-topology-verification",
                "artifact-convergence",
            },
        )
        self.assertFalse(policy["physical_consumers"]["Hopper"]["speculative_compilation"])
        self.assertFalse(policy["physical_consumers"]["BBPI4"]["blocks_hopper"])

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

    def test_broad_suite_excludes_core_x64_modules(self):
        core = set(suite_test_modules("core"))
        broad = set(suite_test_modules("broad"))
        self.assertTrue(broad)
        self.assertTrue(core.isdisjoint(broad))

    def test_shards_partition_each_suite_without_overlap(self):
        for suite, shard_count in (("core", 4), ("broad", 6), ("verification", 6), ("portability", 2)):
            full = set(full_suite_test_modules(suite))
            observed: set[str] = set()
            for shard_index in range(shard_count):
                shard = set(
                    suite_test_modules(
                        suite,
                        shard_index=shard_index,
                        shard_count=shard_count,
                    )
                )
                self.assertTrue(observed.isdisjoint(shard))
                observed.update(shard)
            self.assertEqual(observed, full)

    def test_policy_audit_reports_zero_duplicate_module_work(self):
        policy = self._policy()
        audit = policy_audit(policy)
        self.assertEqual(audit["matrix_lane_count"], 18)
        self.assertEqual(audit["duplicate_work_items"], 0)
        self.assertEqual(audit["duplicate_work_fraction"], 0.0)
        self.assertLessEqual(
            audit["duplicate_work_fraction"],
            policy["limits"]["maximum_duplicate_work_fraction"],
        )
        self.assertTrue(audit["target_met"])

    def test_policy_audit_detects_same_runner_suite_overlap(self):
        policy = self._policy()
        modules_by_suite = {
            "core": ("shared",),
            "broad": ("shared",),
            "verification": (),
            "portability": ("shared",),
        }
        with patch(
            "run_capacity_mesh_cycle.suite_test_modules",
            side_effect=lambda suite, **_kwargs: modules_by_suite[suite],
        ):
            audit = policy_audit(policy)
        self.assertGreater(audit["duplicate_work_items"], 0)
        self.assertGreater(audit["duplicate_work_fraction"], 0.05)
        self.assertFalse(audit["target_met"])

    def test_evidence_fan_in_distinguishes_arm64_from_x86_64(self):
        policy = self._policy()
        convergence = converge_lane_results(
            policy,
            self._lane_results(policy),
            source_sha="a" * 40,
        )
        self.assertEqual(convergence["architectures"], ["arm64", "x86_64"])
        self.assertTrue(convergence["verified"])

    def test_failed_mandatory_verifier_prevents_mesh_convergence(self):
        policy = self._policy()
        results = self._lane_results(policy)
        failed = next(result for result in results if result["posture"] == "verify")
        failed["verified"] = False
        failed["returncode"] = 1
        with self.assertRaisesRegex(ValueError, "mandatory capacity mesh lanes failed"):
            converge_lane_results(policy, results, source_sha="a" * 40)

    def test_speculative_mesh_lane_cannot_mutate_physical_state(self):
        policy = self._policy()
        results = self._lane_results(policy)
        results[0]["physical_state_mutated"] = True
        with self.assertRaisesRegex(ValueError, "mutated trusted physical state"):
            converge_lane_results(policy, results, source_sha="a" * 40)

    def test_arm_evidence_cannot_be_relabelled_as_x86(self):
        policy = copy.deepcopy(self._policy())
        arm = next(path for path in policy["candidate_paths"] if "arm64" in path["name"])
        arm["architecture"] = "x86_64"
        with self.assertRaisesRegex(ValueError, "ARM runner has non-ARM evidence"):
            candidate_paths_from_policy(policy)

    def test_lane_cannot_claim_success_with_a_failed_return_code(self):
        policy = self._policy()
        results = self._lane_results(policy)
        results[0]["returncode"] = 1
        with self.assertRaisesRegex(ValueError, "verification and return code disagree"):
            converge_lane_results(policy, results, source_sha="a" * 40)

    def test_fresh_heartbeat_nodes_can_be_excluded_without_inventing_presence(self):
        policy = self._policy()
        nodes = nodes_from_policy(
            policy,
            available={"github-x64", "github-arm64", "gpt-python"},
        )
        self.assertNotIn("bbpi4-physical", {node.name for node in nodes})
        self.assertNotIn("hopper-physical", {node.name for node in nodes})


if __name__ == "__main__":
    unittest.main(verbosity=2)
