from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "field"))

from self_build_resources import (  # noqa: E402
    BuilderResource,
    SelfBuildNeed,
    default_self_build_resources,
    plan_self_build,
    self_build_resource_field,
)


class SelfBuildResourceTests(unittest.TestCase):
    def test_default_executor_is_github_actions_for_deterministic_build(self):
        placement = plan_self_build(
            SelfBuildNeed(
                execution_requires=frozenset({
                    "deterministic-execution",
                    "isolated-build",
                    "parallel-test",
                })
            ),
            default_self_build_resources(),
        )
        self.assertEqual(placement.executor, "github-actions")
        self.assertIsNone(placement.reasoner)
        self.assertIsNone(placement.promoter)
        self.assertEqual(placement.missing, frozenset())

    def test_gpt_is_reasoner_not_executor(self):
        placement = plan_self_build(
            SelfBuildNeed(
                execution_requires=frozenset({"deterministic-execution"}),
                reasoning_requires=frozenset({"model-reasoning", "candidate-generation"}),
            ),
            default_self_build_resources(),
        )
        self.assertEqual(placement.executor, "github-actions")
        self.assertEqual(placement.reasoner, "gpt-reasoning")
        self.assertNotEqual(placement.executor, placement.reasoner)

    def test_verified_promotion_is_separate_authority(self):
        placement = plan_self_build(
            SelfBuildNeed(
                execution_requires=frozenset({"deterministic-execution"}),
                reasoning_requires=frozenset({"model-reasoning"}),
                promotion_requires=frozenset({"verified-repository-promotion"}),
            ),
            default_self_build_resources(),
        )
        self.assertEqual(placement.promoter, "github-control-plane")
        self.assertNotEqual(placement.promoter, placement.reasoner)

    def test_unavailable_resource_is_not_selected(self):
        resources = list(default_self_build_resources())
        resources[0] = BuilderResource(
            resources[0].name,
            resources[0].capabilities,
            parallel_slots=resources[0].parallel_slots,
            persistence=resources[0].persistence,
            isolation=resources[0].isolation,
            locality=resources[0].locality,
            cost=resources[0].cost,
            available=False,
        )
        placement = plan_self_build(
            SelfBuildNeed(execution_requires=frozenset({"deterministic-execution"})),
            resources,
        )
        self.assertIsNone(placement.executor)

    def test_stronger_verified_executor_wins(self):
        resources = (
            BuilderResource(
                "small",
                frozenset({"deterministic-execution"}),
                parallel_slots=1,
                isolation=5,
            ),
            BuilderResource(
                "large",
                frozenset({"deterministic-execution"}),
                parallel_slots=8,
                isolation=4,
            ),
        )
        placement = plan_self_build(
            SelfBuildNeed(execution_requires=frozenset({"deterministic-execution"})),
            resources,
        )
        self.assertEqual(placement.executor, "large")

    def test_missing_capability_is_explicit(self):
        placement = plan_self_build(
            SelfBuildNeed(
                execution_requires=frozenset({"quantum-execution"}),
                reasoning_requires=frozenset({"model-reasoning"}),
            ),
            default_self_build_resources(),
        )
        self.assertIsNone(placement.executor)
        self.assertEqual(placement.reasoner, "gpt-reasoning")
        self.assertEqual(placement.missing, frozenset({"quantum-execution"}))

    def test_resources_project_cleanly_into_field(self):
        field = self_build_resource_field(default_self_build_resources())
        self.assertEqual(field.missing_refs(), set())
        self.assertGreaterEqual(len(field), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
