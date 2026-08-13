from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "field"))

from self_build_federation import (  # noqa: E402
    SelfBuildLane,
    federation_field,
    plan_federated_self_build,
)
from self_build_resources import BuilderResource  # noqa: E402


class SelfBuildFederationTests(unittest.TestCase):
    def resources(self):
        return (
            BuilderResource(
                "github-actions",
                frozenset({"build", "test", "artifact"}),
                parallel_slots=4,
                isolation=5,
            ),
            BuilderResource(
                "gpt-reasoning",
                frozenset({"reason", "candidate"}),
                parallel_slots=2,
                isolation=2,
            ),
            BuilderResource(
                "morris",
                frozenset({"build", "test", "windows"}),
                parallel_slots=2,
                isolation=3,
            ),
            BuilderResource(
                "bbpi4",
                frozenset({"arm", "hardware-test"}),
                parallel_slots=1,
                available=False,
            ),
            BuilderResource(
                "github-control-plane",
                frozenset({"promote"}),
                parallel_slots=1,
                persistence=5,
                isolation=4,
            ),
        )

    def test_independent_lanes_fan_out_across_verified_resources(self):
        lanes = (
            SelfBuildLane("candidate", frozenset({"reason", "candidate"})),
            SelfBuildLane("linux-build", frozenset({"build", "test"})),
            SelfBuildLane("windows-build", frozenset({"build", "test", "windows"})),
            SelfBuildLane("promotion", frozenset({"promote"})),
        )
        plan = plan_federated_self_build(lanes, self.resources())
        self.assertEqual(plan.unassigned_lanes, ())
        self.assertEqual(plan.missing_capabilities, frozenset())
        self.assertEqual(
            set(plan.active_resources),
            {"github-actions", "gpt-reasoning", "morris", "github-control-plane"},
        )
        self.assertIn("bbpi4", plan.unavailable_resources)

    def test_redundant_lane_can_use_multiple_verified_resources(self):
        lanes = (
            SelfBuildLane("cross-check", frozenset({"build", "test"}), redundancy=2),
        )
        plan = plan_federated_self_build(lanes, self.resources())
        self.assertEqual(len(plan.assignments), 1)
        self.assertEqual(
            set(plan.assignments[0].resources),
            {"github-actions", "morris"},
        )

    def test_unverified_resource_never_receives_work(self):
        lanes = (SelfBuildLane("arm-live", frozenset({"arm", "hardware-test"})),)
        plan = plan_federated_self_build(lanes, self.resources())
        self.assertEqual(plan.assignments, ())
        self.assertEqual(plan.unassigned_lanes, ("arm-live",))
        self.assertEqual(
            plan.missing_capabilities,
            frozenset({"arm", "hardware-test"}),
        )

    def test_all_verified_useful_resources_can_participate_without_irrelevant_work(self):
        resources = (
            BuilderResource("build-a", frozenset({"build"}), parallel_slots=2),
            BuilderResource("build-b", frozenset({"build"}), parallel_slots=2),
            BuilderResource("reason-only", frozenset({"reason"}), parallel_slots=2),
        )
        lanes = (
            SelfBuildLane("compile", frozenset({"build"})),
            SelfBuildLane("analyze", frozenset({"reason"})),
        )
        plan = plan_federated_self_build(lanes, resources)
        self.assertEqual(
            set(plan.active_resources),
            {"build-a", "build-b", "reason-only"},
        )
        compile_assignment = next(item for item in plan.assignments if item.lane == "compile")
        analyze_assignment = next(item for item in plan.assignments if item.lane == "analyze")
        self.assertEqual(set(compile_assignment.resources), {"build-a", "build-b"})
        self.assertEqual(analyze_assignment.resources, ("reason-only",))

    def test_field_projection_is_closed(self):
        lanes = (
            SelfBuildLane("candidate", frozenset({"reason", "candidate"})),
            SelfBuildLane("build", frozenset({"build", "test"}), redundancy=2),
        )
        resources = self.resources()
        plan = plan_federated_self_build(lanes, resources)
        field = federation_field(lanes, resources, plan)
        self.assertEqual(field.missing_refs(), set())
        self.assertGreaterEqual(len(field), len(resources) + len(lanes) + 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
