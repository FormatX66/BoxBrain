import unittest

from evolution_harness.evaluator import Metrics, choose_best, evaluate


class EvolutionEvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = Metrics(
            success=True,
            invariant_preserved=True,
            attempts=4,
            rollback_count=1,
            duration_ms=100.0,
            resource_cost=10.0,
        )

    def test_rejects_unsafe_candidate_even_when_faster(self) -> None:
        candidate = Metrics(True, False, 1, 0, 30.0, 2.0, learned_avoidance=True)
        decision = evaluate(self.baseline, candidate)
        self.assertFalse(decision.promotable)
        self.assertIn("safety invariant", " ".join(decision.reasons))

    def test_accepts_safe_measurable_improvement(self) -> None:
        candidate = Metrics(True, True, 2, 0, 90.0, 9.0, learned_avoidance=True)
        decision = evaluate(self.baseline, candidate)
        self.assertTrue(decision.promotable)
        self.assertGreater(decision.score, 0.0)

    def test_rejects_resource_regression(self) -> None:
        candidate = Metrics(True, True, 2, 0, 90.0, 12.0, learned_avoidance=True)
        decision = evaluate(self.baseline, candidate)
        self.assertFalse(decision.promotable)

    def test_choose_best_only_considers_promotable_candidates(self) -> None:
        unsafe_fast = Metrics(True, False, 1, 0, 20.0, 1.0, learned_avoidance=True)
        safe_better = Metrics(True, True, 2, 0, 80.0, 8.0, learned_avoidance=True)
        index, decision = choose_best(self.baseline, [unsafe_fast, safe_better])
        self.assertEqual(index, 1)
        self.assertIsNotNone(decision)


if __name__ == "__main__":
    unittest.main()
