from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from Projects.AdaptiveKernel.pi3_smsc95xx_usbnet_control_loop_candidate import (
    EVENTS,
    _verify_local_seal,
    run_control_loop_differential,
    synthesize_control_loop_candidate,
)

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "Projects" / "AdaptiveKernel" / "results"


def load(name: str):
    return json.loads((RESULTS / name).read_text(encoding="utf-8-sig"))


class UsbNetControlLoopCandidateTests(unittest.TestCase):
    @classmethod
    def inputs(cls):
        return {
            "shadow": load("pi3-smsc95xx-usbnet-lifecycle-shadow-latest.json"),
            "emulator": load("pi3-smsc95xx-usbnet-event-emulator-latest.json"),
        }

    def test_current_lineage_synthesizes_zero_authority_candidate(self):
        source, receipt, matrix = synthesize_control_loop_candidate(**self.inputs())
        self.assertIn("aurum_usbnet_control_step", source)
        self.assertTrue(_verify_local_seal(receipt))
        self.assertEqual(receipt["state_count"], 13)
        self.assertEqual(receipt["event_count"], 15)
        self.assertEqual(len(matrix), 13 * len(EVENTS))
        self.assertTrue(all(value is False for value in receipt["authority"].values()))
        self.assertFalse(receipt["invariants"]["device_io_primitive_present"])
        self.assertTrue(receipt["invariants"]["last_known_good_preserved"])

    def test_host_compiled_differential_matches_complete_matrix_and_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = run_control_loop_differential(
                **self.inputs(), sequence_seed=0x1234, sequence_steps=4096, output_dir=Path(tmp)
            )
            self.assertTrue(_verify_local_seal(receipt))
            self.assertEqual(receipt["state"], "controlled-host-compiled-usbnet-control-loop-differential-passed")
            self.assertEqual(receipt["complete_event_scenarios"], 195)
            self.assertEqual(receipt["scenario_count"], 195 + 4096)
            self.assertEqual(receipt["mismatch_count"], 0)
            self.assertTrue(receipt["verification"]["host_compilation"])
            self.assertFalse(receipt["invariants"]["live_pi_contacted"])
            self.assertFalse(receipt["invariants"]["usb_transfer_submitted"])

    def test_differential_is_deterministic(self):
        first = run_control_loop_differential(**self.inputs(), sequence_seed=77, sequence_steps=512)
        second = run_control_loop_differential(**self.inputs(), sequence_seed=77, sequence_steps=512)
        self.assertEqual(first["event_matrix_sha256"], second["event_matrix_sha256"])
        self.assertEqual(first["sequence_sha256"], second["sequence_sha256"])
        self.assertEqual(first["receipt_sha256"], second["receipt_sha256"])

    def test_tampered_event_emulator_fails_closed(self):
        inputs = self.inputs()
        bad = copy.deepcopy(inputs["emulator"])
        bad["mismatch_count"] = 1
        inputs["emulator"] = bad
        with self.assertRaises(ValueError):
            synthesize_control_loop_candidate(**inputs)

    def test_string_boolean_in_lifecycle_transition_fails_closed(self):
        inputs = self.inputs()
        bad = copy.deepcopy(inputs["shadow"])
        bad["graph"]["transitions"][0]["accepted"] = "false"
        # Re-sealing the malicious structure ensures failure is semantic, not merely seal validation.
        from Projects.AdaptiveKernel.pi3_smsc95xx_usbnet_control_loop_candidate import _canonical_sha256
        bad.pop("receipt_sha256", None)
        bad["receipt_sha256"] = _canonical_sha256(bad)
        inputs["shadow"] = bad
        with self.assertRaises(ValueError):
            synthesize_control_loop_candidate(**inputs)

    def test_no_candidate_or_differential_authority(self):
        _, candidate, _ = synthesize_control_loop_candidate(**self.inputs())
        differential = run_control_loop_differential(**self.inputs(), sequence_steps=128)
        self.assertTrue(all(value is False for value in candidate["authority"].values()))
        self.assertTrue(all(value is False for value in differential["authority"].values()))
        self.assertFalse(differential["invariants"]["kernel_module_loaded"])
        self.assertFalse(differential["invariants"]["driver_binding_changed"])
        self.assertTrue(differential["invariants"]["last_known_good_preserved"])


if __name__ == "__main__":
    unittest.main()
