from __future__ import annotations

import copy
import json
import shutil
import unittest
from pathlib import Path

from Projects.AdaptiveKernel.pi3_smsc95xx_candidate_synth import (
    synthesize_candidate,
    verify_candidate_source,
)


MODEL_PATH = Path("Projects/AdaptiveKernel/results/pi3-smsc95xx-functional-model-latest.json")


class Pi3Smsc95xxCandidateSynthesisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = json.loads(MODEL_PATH.read_text(encoding="utf-8-sig"))

    def test_synthesizes_concrete_zero_authority_candidate(self) -> None:
        source, receipt = synthesize_candidate(self.model)
        self.assertIn("aurum_smsc95xx_init", source)
        self.assertIn("aurum_smsc95xx_set_link", source)
        self.assertIn("aurum_smsc95xx_set_rx_checksum", source)
        self.assertIn("aurum_smsc95xx_tx_frame_len", source)
        self.assertEqual(receipt["state"], "synthesized-nonbinding-shadow-candidate")
        self.assertFalse(receipt["authority"]["mutation_allowed"])
        self.assertFalse(receipt["authority"]["driver_binding_change_allowed"])
        self.assertFalse(receipt["authority"]["kernel_module_load_allowed"])
        self.assertFalse(receipt["authority"]["promotion_allowed"])
        self.assertFalse(receipt["invariants"]["device_io_performed"])
        self.assertFalse(receipt["invariants"]["kernel_module_entrypoint_present"])

    @unittest.skipUnless(shutil.which("cc") or shutil.which("gcc") or shutil.which("clang"), "C compiler required")
    def test_compiles_and_matches_bounded_reference_behavior(self) -> None:
        source, receipt = synthesize_candidate(self.model)
        result = verify_candidate_source(source, receipt)
        self.assertTrue(result["compiled"])
        self.assertTrue(result["controlled_harness_passed"])
        self.assertTrue(result["wrong_controller_rejected"])
        self.assertTrue(result["unproven_gigabit_rejected"])
        self.assertTrue(result["rx_checksum_sequence_reproduced"])
        self.assertTrue(result["tx_framing_reproduced"])
        self.assertFalse(result["device_io_performed"])
        self.assertFalse(result["binding_attempted"])
        self.assertFalse(result["mutation_authority_granted"])

    def test_tampered_model_fails_closed(self) -> None:
        model = copy.deepcopy(self.model)
        model["scope"]["usb_ethernet_function"] = "0424:7800"
        with self.assertRaises(ValueError):
            synthesize_candidate(model)

    def test_nonzero_authority_fails_closed_even_if_resealed_is_not_attempted(self) -> None:
        model = copy.deepcopy(self.model)
        model["authority"]["mutation_allowed"] = True
        with self.assertRaises(ValueError):
            synthesize_candidate(model)

    def test_unproven_behavior_envelope_is_not_synthesized(self) -> None:
        model = copy.deepcopy(self.model)
        model["scope"]["link_speeds_mbps"] = [10, 100, 1000]
        with self.assertRaises(ValueError):
            synthesize_candidate(model)

    def test_candidate_source_hash_is_enforced(self) -> None:
        source, receipt = synthesize_candidate(self.model)
        with self.assertRaises(ValueError):
            verify_candidate_source(source + "\n/* tampered */\n", receipt)


if __name__ == "__main__":
    unittest.main()
