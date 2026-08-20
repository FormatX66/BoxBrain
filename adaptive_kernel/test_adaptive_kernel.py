import unittest

from adaptive_kernel import AdaptiveKernel, Candidate


class AdaptiveKernelTests(unittest.TestCase):
    def test_prefers_high_confidence_low_cost_candidate(self):
        kernel = AdaptiveKernel({1: 0})
        candidates = [
            Candidate(1, 4, 80, True, lambda s: {**s, 1: 1}),
            Candidate(2, 2, 60, True, lambda s: {**s, 1: 1}),
        ]
        state, attempts = kernel.realize(candidates, lambda s: s[1] == 1)
        self.assertEqual(state[1], 1)
        self.assertEqual(attempts[0].candidate_id, 1)

    def test_bad_candidate_rolls_back_and_falls_back(self):
        kernel = AdaptiveKernel({1: 0})
        candidates = [
            Candidate(1, 1, 90, True, lambda s: {**s, 1: 9}),
            Candidate(2, 2, 70, True, lambda s: {**s, 1: 1}),
        ]
        state, attempts = kernel.realize(candidates, lambda s: s[1] == 1)
        self.assertEqual(state[1], 1)
        self.assertEqual([a.candidate_id for a in attempts], [1, 2])
        self.assertTrue(attempts[0].rolled_back)

    def test_learning_avoids_previously_bad_candidate(self):
        kernel = AdaptiveKernel({1: 0})
        bad = Candidate(1, 1, 90, True, lambda s: {**s, 1: 9})
        good = Candidate(2, 2, 70, True, lambda s: {**s, 1: 1})
        kernel.realize([bad, good], lambda s: s[1] == 1)
        kernel.state = {1: 0}
        _, attempts = kernel.realize([bad, good], lambda s: s[1] == 1)
        self.assertEqual(attempts[0].candidate_id, 2)

    def test_invariant_rejects_unsafe_outcome(self):
        kernel = AdaptiveKernel({1: 0, 2: 40})
        unsafe = Candidate(1, 1, 90, True, lambda s: {**s, 1: 1, 2: 100})
        safe = Candidate(2, 2, 70, True, lambda s: {**s, 1: 1, 2: 45})
        state, attempts = kernel.realize(
            [unsafe, safe],
            lambda s: s[1] == 1,
            invariant=lambda s: s[2] <= 80,
        )
        self.assertEqual(state[1], 1)
        self.assertLessEqual(state[2], 80)
        self.assertFalse(attempts[0].success)


if __name__ == "__main__":
    unittest.main()
