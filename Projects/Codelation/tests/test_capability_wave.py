from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "field"))

from capability_wave import (  # noqa: E402
    CapabilityCompletion,
    UpgradeNode,
    capability_wave_field,
    emit_capability_wave,
)
from capacity_mesh import RewardSignal  # noqa: E402


class CapabilityLearningWaveTests(unittest.TestCase):
    def completion(self):
        return CapabilityCompletion(
            capability="example-capability",
            source_node="node-a",
            source_variant_identity="variant-a",
            requires=frozenset({"python"}),
            reward=RewardSignal(verified=True, reusable=True, generalized=True),
            evidence=("tests-pass",),
            learned_principles=("principle-1",),
            constraints=("constraint-1",),
            success_conditions=("condition-1",),
            failed_approaches=("failed-1",),
        )

    def test_wave_shares_learning_not_source_implementation(self):
        wave = emit_capability_wave(
            self.completion(),
            (
                UpgradeNode("node-a", frozenset({"python"})),
                UpgradeNode("node-b", frozenset({"python"})),
                UpgradeNode("node-c", frozenset({"python", "gpu"})),
            ),
        )
        self.assertEqual(wave.target_nodes, ("node-b", "node-c"))
        for lane in wave.lanes:
            self.assertEqual(lane.source_variant_identity, "variant-a")
            self.assertIn("derive-local-capability-design", lane.stages)
            self.assertNotIn("install-source-variant", lane.stages)

    def test_missing_prerequisites_create_adaptation_lane(self):
        wave = emit_capability_wave(
            self.completion(),
            (
                UpgradeNode("node-a", frozenset({"python"})),
                UpgradeNode("node-b", frozenset()),
            ),
        )
        lane = wave.lanes[0]
        self.assertEqual(lane.node, "node-b")
        self.assertEqual(lane.mode, "adapt-prerequisites-then-derive")
        self.assertEqual(lane.missing_prerequisites, frozenset({"python"}))

    def test_unverified_completion_cannot_teach_cluster(self):
        completion = CapabilityCompletion(
            capability="example-capability",
            source_node="node-a",
            source_variant_identity="variant-a",
            requires=frozenset(),
            reward=RewardSignal(verified=False),
        )
        wave = emit_capability_wave(
            completion,
            (UpgradeNode("node-b", frozenset()),),
        )
        self.assertEqual(wave.lanes, ())
        self.assertEqual(wave.blocked_reason, "completion-not-verified")

    def test_field_declares_local_variants_not_shared_implementation(self):
        completion = self.completion()
        wave = emit_capability_wave(
            completion,
            (
                UpgradeNode("node-a", frozenset({"python"})),
                UpgradeNode("node-b", frozenset({"python"})),
            ),
        )
        field = capability_wave_field(completion, wave)
        self.assertEqual(field.missing_refs(), set())
        self.assertGreaterEqual(len(field), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
