import unittest

from gap_stack import GapExposure, GapKind, gap_preparation_profile, stacked_gap_score


class GapStackTests(unittest.TestCase):
    def test_multiple_moderate_gaps_compound(self):
        gaps = [
            GapExposure(GapKind.CONTEXT, 0.45, 0.4),
            GapExposure(GapKind.TOPOLOGY, 0.45, 0.4),
            GapExposure(GapKind.RUNTIME, 0.45, 0.4),
        ]
        score = stacked_gap_score(gaps)
        self.assertGreater(score, max(g.effective for g in gaps))
        self.assertGreater(score, 0.60)

    def test_mitigation_reduces_gap(self):
        raw = GapExposure(GapKind.EVIDENCE, 0.8, 0.4, mitigated=False)
        mitigated = GapExposure(GapKind.EVIDENCE, 0.8, 0.4, mitigated=True)
        self.assertLess(mitigated.effective, raw.effective)

    def test_flash_like_stack_requires_cross_checks_and_revalidation(self):
        profile = gap_preparation_profile([
            GapExposure(GapKind.REALITY, 0.8, 0.6),
            GapExposure(GapKind.TOPOLOGY, 0.7, 0.5),
            GapExposure(GapKind.CAPABILITY, 0.65, 0.5),
            GapExposure(GapKind.RUNTIME, 0.6, 0.4),
            GapExposure(GapKind.EVIDENCE, 0.55, 0.5),
            GapExposure(GapKind.FRESHNESS, 0.5, 0.5),
        ])
        self.assertEqual(profile["lookahead"], "to-boundary")
        self.assertTrue(profile["cross_check_context_and_topology"])
        self.assertTrue(profile["require_capability_probe"])
        self.assertTrue(profile["require_runtime_probe"])
        self.assertTrue(profile["require_independent_verification"])
        self.assertTrue(profile["revalidate_before_effect"])
        self.assertFalse(profile["authority_granted"])

    def test_known_low_gap_transition_stays_lightweight(self):
        profile = gap_preparation_profile([
            GapExposure(GapKind.RUNTIME, 0.1, 0.9, mitigated=True),
        ])
        self.assertEqual(profile["lookahead"], "normal")
        self.assertLess(profile["processing_multiplier"], 1.2)


if __name__ == "__main__":
    unittest.main()
