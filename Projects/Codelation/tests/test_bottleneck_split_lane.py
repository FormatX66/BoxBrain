from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from run_bottleneck_split_lane import run_adventurous, run_verifier  # noqa: E402
from run_native_frontier_gap import FRONTIER_GAP_SCHEMA  # noqa: E402


class BottleneckSplitLaneTests(unittest.TestCase):
    def _blocked_state(self, gap: str, reason: str) -> dict:
        return {
            "schema": FRONTIER_GAP_SCHEMA,
            "gap": gap,
            "status": "blocked",
            "blocked_reason": reason,
            "blocked_output": None,
            "next_gap": gap,
            "global_barrier": False,
            "blocks_other_frontiers": False,
        }

    def test_expanded_search_can_build_retention_ratio_candidate(self):
        result = run_adventurous(
            self._blocked_state("learning_retention_ratio", "native-synthesis-not-found")
        )
        self.assertEqual(result["mode"], "adventurous")
        self.assertEqual(result["strategy"], "expanded-bounded-native-synthesis")
        self.assertEqual(result["status"], "verified-candidate")
        self.assertTrue(result["progress_made"])
        self.assertIsInstance(result["candidate_expression"], dict)
        self.assertFalse(result["promotion_performed"])
        self.assertFalse(result["authority_granted"])

    def test_expanded_search_can_build_novelty_ratio_candidate(self):
        result = run_adventurous(
            self._blocked_state("learning_novelty_ratio", "native-synthesis-not-found")
        )
        self.assertEqual(result["status"], "verified-candidate")
        self.assertTrue(result["progress_made"])

    def test_independent_verifier_reproduces_safe_search_boundary(self):
        result = run_verifier(
            self._blocked_state("learning_retention_ratio", "native-synthesis-not-found")
        )
        self.assertTrue(result["verified"])
        self.assertTrue(result["checks"]["safe_search_block_reproduced"])
        self.assertEqual(result["independent_safe_search"]["max_cost"], 12)

    def test_external_block_remains_local_and_lookahead_only(self):
        state = self._blocked_state(
            "adaptive_shell_live_trial_readiness",
            "external-prerequisite-blocked",
        )
        state["blocked_output"] = "blocked-physical-node"
        adventurous = run_adventurous(state)
        verifier = run_verifier(state)
        self.assertTrue(verifier["verified"])
        self.assertTrue(adventurous["source_block_preserved"])
        self.assertFalse(adventurous["global_barrier"])
        self.assertFalse(adventurous["authority_granted"])
        self.assertEqual(adventurous["target_gap"], "adaptive_shell_live_trial")


if __name__ == "__main__":
    unittest.main(verbosity=2)
