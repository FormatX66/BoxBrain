from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "field"))

from bottleneck_mesh import (  # noqa: E402
    Bottleneck,
    CandidateOutcome,
    converge_bottleneck,
    split_bottleneck,
    split_frontier,
)
from capacity_mesh import Node, RewardSignal  # noqa: E402


class BottleneckMeshTests(unittest.TestCase):
    def test_one_bottleneck_splits_safe_adventurous_and_verifier(self):
        bottleneck = Bottleneck(
            name="io-choice",
            requires=frozenset({"python"}),
            goal="choose a verified I/O route",
        )
        plan = split_bottleneck(
            bottleneck,
            [
                Node("lane-a", frozenset({"python"}), capacity=1),
                Node("lane-b", frozenset({"python"}), capacity=1),
                Node("lane-c", frozenset({"python"}), capacity=1),
            ],
        )
        self.assertEqual(
            {lane.mode for lane in plan.lanes_for("io-choice")},
            {"safe", "adventurous", "independent-verifier"},
        )
        self.assertEqual(len({lane.node for lane in plan.lanes}), 3)
        self.assertEqual(plan.unassigned, ())

    def test_multiple_bottlenecks_share_the_whole_frontier_capacity(self):
        bottlenecks = [
            Bottleneck("capability-gap", frozenset({"python"}), "grow capability"),
            Bottleneck("interface-gap", frozenset({"python"}), "grow interface"),
            Bottleneck("io-gap", frozenset({"python"}), "grow I/O"),
        ]
        nodes = [
            Node(f"lane-{index}", frozenset({"python"}), capacity=1)
            for index in range(9)
        ]
        plan = split_frontier(bottlenecks, nodes)
        self.assertEqual(set(plan.bottlenecks), {item.name for item in bottlenecks})
        self.assertEqual(len(plan.lanes), 9)
        for bottleneck in bottlenecks:
            self.assertEqual(
                {lane.mode for lane in plan.lanes_for(bottleneck.name)},
                {"safe", "adventurous", "independent-verifier"},
            )

    def test_limited_capacity_keeps_unassigned_paths_explicit(self):
        bottleneck = Bottleneck(
            "limited",
            frozenset({"python"}),
            "do not serialize silently",
        )
        plan = split_bottleneck(
            bottleneck,
            [Node("only-lane", frozenset({"python"}), capacity=1)],
        )
        self.assertEqual(len(plan.lanes), 1)
        self.assertEqual(len(plan.unassigned), 2)

    def test_convergence_selects_best_verified_candidate_with_verifier(self):
        bottleneck = Bottleneck(
            "selection",
            frozenset({"python"}),
            "select evidence-backed result",
        )
        result = converge_bottleneck(
            bottleneck,
            [
                CandidateOutcome(
                    "selection",
                    "safe",
                    "safe-node",
                    RewardSignal(verified=True, reusable=True),
                    implementation_identity="safe-v1",
                ),
                CandidateOutcome(
                    "selection",
                    "adventurous",
                    "risk-node",
                    RewardSignal(verified=True, reusable=True, generalized=True),
                    implementation_identity="risk-v2",
                ),
                CandidateOutcome(
                    "selection",
                    "independent-verifier",
                    "verify-node",
                    RewardSignal(verified=True, uncertainty_reduced=True),
                    evidence=("independent-test-pass",),
                ),
            ],
        )
        self.assertTrue(result.accepted)
        self.assertEqual(result.selected_implementation_identity, "risk-v2")
        self.assertEqual(result.verifier_nodes, ("verify-node",))

    def test_convergence_refuses_candidate_without_independent_verification(self):
        bottleneck = Bottleneck(
            "no-verifier",
            frozenset({"python"}),
            "fail closed at convergence",
        )
        result = converge_bottleneck(
            bottleneck,
            [
                CandidateOutcome(
                    "no-verifier",
                    "safe",
                    "safe-node",
                    RewardSignal(verified=True),
                    implementation_identity="safe-v1",
                )
            ],
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "independent-verification-missing")

    def test_unsafe_or_false_candidate_cannot_win(self):
        bottleneck = Bottleneck(
            "reject-bad",
            frozenset({"python"}),
            "exclude unsafe and false paths",
        )
        result = converge_bottleneck(
            bottleneck,
            [
                CandidateOutcome(
                    "reject-bad",
                    "adventurous",
                    "bad-node",
                    RewardSignal(verified=True, generalized=True, unsafe_or_unauthorized=True),
                    implementation_identity="bad-v1",
                ),
                CandidateOutcome(
                    "reject-bad",
                    "safe",
                    "safe-node",
                    RewardSignal(verified=True),
                    implementation_identity="safe-v1",
                ),
                CandidateOutcome(
                    "reject-bad",
                    "independent-verifier",
                    "verify-node",
                    RewardSignal(verified=True),
                ),
            ],
        )
        self.assertTrue(result.accepted)
        self.assertEqual(result.selected_implementation_identity, "safe-v1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
