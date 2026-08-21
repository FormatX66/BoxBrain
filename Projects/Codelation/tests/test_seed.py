import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "seed"))
from codelation_seed import (  # noqa: E402
    HUMAN_TRAIT_BUILD_POLICY,
    HUMAN_TRAIT_IDS,
    HUMAN_TRAIT_SCHEMA,
    SeedGraph,
    state_id,
)


class SeedGraphTests(unittest.TestCase):
    def test_repeated_transition_becomes_prediction(self):
        graph = SeedGraph()
        boot, ready = state_id(b"boot"), state_id(b"ready")
        graph.observe(boot)
        graph.observe(ready)
        graph.observe(boot)
        prediction, correct = graph.observe(ready)
        self.assertEqual(prediction, ready)
        self.assertTrue(correct)

    def test_binary_round_trip(self):
        graph = SeedGraph()
        graph.observe(state_id(b"one"))
        graph.observe(state_id(b"two"))
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "seed.bin"
            graph.save(model)
            restored = SeedGraph.load(model)
        self.assertEqual(restored.last_state, graph.last_state)
        self.assertEqual(restored.edges, graph.edges)

    def test_observation_content_is_not_stored(self):
        secret = b"raw-observation-content"
        graph = SeedGraph()
        graph.observe(state_id(secret))
        graph.observe(state_id(b"next"))
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "seed.bin"
            graph.save(model)
            self.assertNotIn(secret, model.read_bytes())

    def test_every_seed_declares_complete_human_trait_genome(self):
        self.assertEqual("aurum-human-traits-v1", HUMAN_TRAIT_SCHEMA)
        self.assertEqual(
            {
                "TR8:WEB",
                "TR8:FILES",
                "TR8:MEDIA",
                "TR8:WRITE",
                "TR8:INTENT",
                "TR8:CONNECT",
                "TR8:RECOVER",
            },
            set(HUMAN_TRAIT_IDS),
        )
        self.assertIn("all-traits-parallel", HUMAN_TRAIT_BUILD_POLICY)
        self.assertIn("mature-in-stages", HUMAN_TRAIT_BUILD_POLICY)


if __name__ == "__main__":
    unittest.main()
