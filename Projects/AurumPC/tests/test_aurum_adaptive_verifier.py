from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("aurum_adaptive_verifier", ROOT / "aurum_adaptive_verifier.py")
assert SPEC and SPEC.loader
aurum_adaptive_verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aurum_adaptive_verifier)


class AdaptiveVerifierTests(unittest.TestCase):
    def good_receipt(self) -> dict:
        return {
            "desired_state_reached": True,
            "execution_authorized": True,
            "autonomy_envelope_preserved": True,
            "boundary_crossed": False,
            "destructive_effect": False,
            "invariants_preserved": [
                "authorization-preserved",
                "no-destructive-boundary-crossing",
                "trust-boundary-preserved",
            ],
            "proof": {"kind": "state-receipt", "value": "ok"},
            "path": ["local", "peer", "target"],
            "implementation": "candidate-a",
            "fitness_score": 0.82,
        }

    def test_different_path_is_valid_when_state_and_invariants_hold(self) -> None:
        first = self.good_receipt()
        second = self.good_receipt()
        second["path"] = ["local", "cellular", "cloud", "target"]
        second["implementation"] = "candidate-b"

        self.assertEqual(aurum_adaptive_verifier.verify_receipt(first)["result"], "PASS")
        self.assertEqual(aurum_adaptive_verifier.verify_receipt(second)["result"], "PASS")

    def test_boundary_crossing_fails_even_when_goal_is_reached(self) -> None:
        receipt = self.good_receipt()
        receipt["boundary_crossed"] = True
        result = aurum_adaptive_verifier.verify_receipt(receipt)
        self.assertEqual(result["result"], "FAIL")
        self.assertIn("reported-boundary-crossing", result["failures"])

    def test_missing_proof_fails(self) -> None:
        receipt = self.good_receipt()
        receipt["proof"] = {}
        result = aurum_adaptive_verifier.verify_receipt(receipt)
        self.assertEqual(result["result"], "FAIL")
        self.assertIn("proof-missing", result["failures"])

    def test_generation_can_preserve_or_improve_without_identical_artifact(self) -> None:
        baseline = self.good_receipt()
        candidate = self.good_receipt()
        candidate["implementation"] = "stateweave-native-b"
        candidate["fitness_score"] = 0.91
        result = aurum_adaptive_verifier.verify_generation(candidate, baseline)
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["comparison"]["fitness_relation"], "improved")

    def test_monotonic_timing_can_be_required(self) -> None:
        receipt = self.good_receipt()
        receipt["timing"] = {"t0": 1.0, "t1": 2.0, "t2": 1.5}
        contract = aurum_adaptive_verifier.default_contract()
        contract["require_monotonic_timing"] = True
        result = aurum_adaptive_verifier.verify_receipt(receipt, contract)
        self.assertEqual(result["result"], "FAIL")
        self.assertTrue(any(item.startswith("timing-not-monotonic") for item in result["failures"]))


if __name__ == "__main__":
    unittest.main()
