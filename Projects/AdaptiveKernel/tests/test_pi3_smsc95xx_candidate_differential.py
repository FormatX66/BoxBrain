from __future__ import annotations

import copy
import json
import shutil
import unittest
from pathlib import Path

from Projects.AdaptiveKernel.pi3_smsc95xx_candidate_differential import run_differential


MODEL_PATH = Path("Projects/AdaptiveKernel/results/pi3-smsc95xx-functional-model-latest.json")


class Pi3Smsc95xxCandidateDifferentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = json.loads(MODEL_PATH.read_text(encoding="utf-8-sig"))

    @unittest.skipUnless(shutil.which("cc") or shutil.which("gcc") or shutil.which("clang"), "C compiler required")
    def test_candidate_matches_sealed_model_across_bounded_matrix(self) -> None:
        result = run_differential(self.model)
        self.assertEqual(result["state"], "controlled-differential-passed")
        self.assertEqual(result["mismatch_count"], 0)
        self.assertGreaterEqual(result["agreement_count"], 18)
        self.assertEqual(result["milestone"], "first-controlled-nonbinding-candidate-verification-complete")
        self.assertTrue(result["verification"]["candidate_vs_model_differential"])
        self.assertTrue(result["verification"]["all_proven_link_modes_covered"])
        self.assertTrue(result["verification"]["tx_framing_payload_matrix_covered"])
        self.assertFalse(result["authority"]["mutation_allowed"])
        self.assertFalse(result["authority"]["driver_binding_change_allowed"])
        self.assertFalse(result["authority"]["kernel_module_load_allowed"])
        self.assertFalse(result["authority"]["promotion_allowed"])
        self.assertFalse(result["invariants"]["live_pi_contacted"])
        self.assertFalse(result["invariants"]["device_io_performed"])
        self.assertTrue(result["invariants"]["last_known_good_preserved"])

    def test_tampered_functional_model_is_refused(self) -> None:
        model = copy.deepcopy(self.model)
        model["state"] = "tampered"
        with self.assertRaises(ValueError):
            run_differential(model)

    def test_expanded_unproven_speed_envelope_is_refused(self) -> None:
        model = copy.deepcopy(self.model)
        model["scope"]["link_speeds_mbps"] = [10, 100, 1000]
        with self.assertRaises(ValueError):
            run_differential(model)


if __name__ == "__main__":
    unittest.main()
