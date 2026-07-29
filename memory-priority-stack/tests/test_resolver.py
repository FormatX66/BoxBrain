import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from boxbrain_memory.resolver import Candidate, choose, score


class ResolverTests(unittest.TestCase):
    def test_blocked_candidate_is_never_selected(self):
        result = choose({
            "candidate_actions": [
                {"id": "blocked", "artifact_level": 1, "estimated_success": 1.0, "blocked": True},
                {"id": "fallback", "artifact_level": 4, "estimated_success": 0.9},
            ]
        })
        self.assertEqual(result["selected"], "fallback")

    def test_finished_product_beats_documentation(self):
        result = choose({
            "candidate_actions": [
                {"id": "docs", "artifact_level": 6, "estimated_success": 1.0},
                {"id": "product", "artifact_level": 1, "estimated_success": 0.8},
            ]
        })
        self.assertEqual(result["selected"], "product")

    def test_proven_workflow_gets_priority(self):
        self.assertGreater(
            score(Candidate("proven", 4, 0.8, proven=True)),
            score(Candidate("new", 4, 0.8, proven=False)),
        )


if __name__ == "__main__":
    unittest.main()
