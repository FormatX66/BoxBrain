from __future__ import annotations

import hashlib
import json
import shutil
import unittest

from Projects.AdaptiveKernel.pi3_smsc95xx_register_interrupt_candidate import (
    _REQUIRED_FALSE,
    run_differential,
    synthesize_candidate,
)
from Projects.AdaptiveKernel.pi3_smsc95xx_register_interrupt_model import SCHEMA as REGISTER_MODEL_SCHEMA


def _seal(value: dict) -> dict:
    body = dict(value)
    body.pop("receipt_sha256", None)
    value["receipt_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    ).hexdigest()
    return value


def fixture_model() -> dict:
    return _seal(
        {
            "schema": REGISTER_MODEL_SCHEMA,
            "state": "verified-offline-register-interrupt-shadow",
            "interrupt_sources": [
                {
                    "name": "tx-error",
                    "status_mask": 0x00002000,
                    "endpoint_mask": 0x00000002,
                    "clear_semantics": "write-one-clear",
                },
                {
                    "name": "phy-interrupt",
                    "status_mask": 0x00008000,
                    "endpoint_mask": 0x00000004,
                    "clear_semantics": "read-only-source",
                },
                {
                    "name": "gpio",
                    "status_mask": 0x00010000,
                    "endpoint_mask": 0x00000008,
                    "clear_semantics": "read-only-source",
                },
            ],
            "authority": {key: False for key in _REQUIRED_FALSE},
        }
    )


class RegisterInterruptCandidateTests(unittest.TestCase):
    def require_c_compiler(self):
        if not (shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")):
            self.skipTest("C compiler required")

    def test_candidate_is_host_only_and_zero_authority(self):
        source, receipt = synthesize_candidate(fixture_model())
        self.assertIn("aurum_smsc95xx_decode_interrupts", source)
        self.assertNotIn("int_status & int_ep_ctl", source)
        self.assertIn("int_status & 0x00002000u", source)
        self.assertIn("int_ep_ctl & 0x00000002u", source)
        self.assertNotIn("module_init", source)
        self.assertNotIn("usb_register", source)
        self.assertNotIn("writel(", source)
        for key in _REQUIRED_FALSE:
            self.assertFalse(receipt["authority"][key])
        self.assertFalse(receipt["invariants"]["device_io_performed"])
        self.assertFalse(receipt["invariants"]["register_write_performed"])

    def test_differential_covers_gating_w1c_read_only_and_unknown_bits(self):
        self.require_c_compiler()
        result = run_differential(fixture_model())
        self.assertEqual(result["state"], "controlled-register-interrupt-differential-passed")
        self.assertEqual(result["mismatch_count"], 0)
        self.assertGreaterEqual(result["scenario_count"], 10)
        self.assertTrue(result["verification"]["single_source_enabled_and_masked"])
        self.assertTrue(result["verification"]["w1c_vs_read_only_separation"])
        self.assertTrue(result["verification"]["unknown_bits"])
        self.assertFalse(result["invariants"]["live_pi_contacted"])
        self.assertFalse(result["invariants"]["device_io_performed"])
        self.assertFalse(result["authority"]["write_authority"])

    def test_tampered_model_fails_closed(self):
        model = fixture_model()
        model["interrupt_sources"][0]["status_mask"] ^= 1
        with self.assertRaisesRegex(ValueError, "sealed receipt"):
            synthesize_candidate(model)

    def test_nonzero_authority_fails_closed(self):
        model = fixture_model()
        model["authority"]["register_write_allowed"] = True
        _seal(model)
        with self.assertRaisesRegex(ValueError, "register_write_allowed=false"):
            run_differential(model)

    def test_unknown_clear_semantics_fails_closed(self):
        model = fixture_model()
        model["interrupt_sources"][0]["clear_semantics"] = "write-through"
        _seal(model)
        with self.assertRaisesRegex(ValueError, "unsupported interrupt clear semantics"):
            synthesize_candidate(model)

    def test_overlapping_status_and_endpoint_semantics_fail_differential(self):
        self.require_c_compiler()
        model = fixture_model()
        # Preserve a sealed but suspicious model. A read-only source is forced onto
        # the W1C status bit while retaining a different endpoint gate. The host
        # differential must reject the ambiguity rather than silently normalize it.
        model["interrupt_sources"][1]["status_mask"] = model["interrupt_sources"][0]["status_mask"]
        _seal(model)
        with self.assertRaisesRegex(ValueError, "candidate/model register-interrupt mismatch"):
            run_differential(model)


if __name__ == "__main__":
    unittest.main()
