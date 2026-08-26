from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from Projects.AdaptiveKernel.pi3_smsc95xx_integrated_packet_control_loop import (
    _verify_sealed,
    run_integrated_differential,
)

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "Projects" / "AdaptiveKernel" / "results"
GENERATED = ROOT / "Projects" / "AdaptiveKernel" / "driver_candidates" / "generated"


def load(name: str):
    return json.loads((RESULTS / name).read_text(encoding="utf-8-sig"))


class IntegratedPacketControlLoopTests(unittest.TestCase):
    @classmethod
    def inputs(cls):
        return {
            "control_candidate": load("pi3-smsc95xx-usbnet-control-loop-candidate-latest.json"),
            "control_differential": load("pi3-smsc95xx-usbnet-control-loop-differential-latest.json"),
            "packet_candidate": load("pi3-smsc95xx-packet-transfer-candidate-latest.json"),
            "packet_differential": load("pi3-smsc95xx-packet-transfer-differential-latest.json"),
            "control_source": (GENERATED / "pi3-smsc95xx-usbnet-control-loop-candidate.c").read_text(encoding="utf-8"),
            "packet_source": (GENERATED / "pi3-smsc95xx-packet-transfer-candidate.c").read_text(encoding="utf-8"),
        }

    def test_current_lineage_integrates_without_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = run_integrated_differential(
                **self.inputs(), sequence_seed=0x1234, sequence_steps=4096, output_dir=Path(tmp)
            )
        self.assertTrue(_verify_sealed(receipt))
        self.assertEqual(receipt["state"], "controlled-integrated-host-packet-control-loop-passed")
        self.assertEqual(receipt["complete_integrated_scenarios"], 455)
        self.assertEqual(receipt["scenario_count"], 455 + 4096)
        self.assertEqual(receipt["mismatch_count"], 0)
        self.assertTrue(receipt["verification"]["state_gated_tx_framing"])
        self.assertTrue(receipt["verification"]["state_gated_rx_decoding"])
        self.assertFalse(receipt["invariants"]["live_pi_contacted"])
        self.assertFalse(receipt["invariants"]["usb_transfer_submitted"])

    def test_integrated_result_is_deterministic(self):
        first = run_integrated_differential(**self.inputs(), sequence_seed=77, sequence_steps=512)
        second = run_integrated_differential(**self.inputs(), sequence_seed=77, sequence_steps=512)
        self.assertEqual(first["scenario_matrix_sha256"], second["scenario_matrix_sha256"])
        self.assertEqual(first["sequence_sha256"], second["sequence_sha256"])
        self.assertEqual(first["receipt_sha256"], second["receipt_sha256"])

    def test_source_hash_mismatch_fails_closed(self):
        inputs = self.inputs()
        inputs["control_source"] += "\n/* tampered */\n"
        with self.assertRaises(ValueError):
            run_integrated_differential(**inputs, sequence_steps=32)

    def test_upstream_mismatch_receipt_fails_closed(self):
        inputs = self.inputs()
        bad = copy.deepcopy(inputs["packet_differential"])
        bad["mismatch_count"] = 1
        inputs["packet_differential"] = bad
        with self.assertRaises(ValueError):
            run_integrated_differential(**inputs, sequence_steps=32)

    def test_integrated_stage_never_gains_authority(self):
        receipt = run_integrated_differential(**self.inputs(), sequence_steps=128)
        self.assertTrue(all(value is False for value in receipt["authority"].values()))
        self.assertFalse(receipt["invariants"]["usb_device_opened"])
        self.assertFalse(receipt["invariants"]["register_access_performed"])
        self.assertFalse(receipt["invariants"]["kernel_module_loaded"])
        self.assertTrue(receipt["invariants"]["last_known_good_preserved"])


if __name__ == "__main__":
    unittest.main()
