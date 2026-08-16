import json
import unittest
from pathlib import Path

from Projects.Codelation.driver_synthesis import (
    BEHAVIOR_TRACE_SCHEMA,
    CANDIDATE_SCHEMA,
    TRACE_VERIFICATION_SCHEMA,
    EvidenceClaim,
    reconcile_evidence,
    synthesize_candidate_interface,
    verify_behavior_trace,
)


EVIDENCE = Path(__file__).parents[1] / "driver_evidence" / "tl16c550d_v0.json"
TRACE = Path(__file__).parents[1] / "driver_evidence" / "tl16c550d_reference_trace_v0.json"
REGISTER_BINDINGS = Path(__file__).parents[1] / "driver_evidence" / "tl16c550d_register_bindings_v0.json"


class DriverSynthesisTests(unittest.TestCase):
    def test_independent_agreement_promotes_verified_claim(self):
        model = reconcile_evidence([
            EvidenceClaim("register.dma_enable", 8, "datasheet", "vendor-manual", 0.95),
            EvidenceClaim("register.dma_enable", 8, "reference_driver", "linux-driver", 0.90),
        ])
        entry = model["claims"]["register.dma_enable"]
        self.assertEqual("verified", entry["state"])
        self.assertEqual(8, entry["value"])
        self.assertEqual(["datasheet", "reference_driver"], entry["supporting_source_kinds"])

    def test_conflict_is_preserved_and_observation_can_corrobate_reference(self):
        model = reconcile_evidence([
            EvidenceClaim("irq.transfer_complete", 4, "datasheet", "manual", 0.90),
            EvidenceClaim("irq.transfer_complete", 7, "reference_driver", "bsd-driver", 0.95),
            EvidenceClaim("irq.transfer_complete", 7, "observation", "read-only-trace", 0.95),
        ])
        entry = model["claims"]["irq.transfer_complete"]
        self.assertEqual("verified", entry["state"])
        self.assertEqual(7, entry["value"])
        self.assertEqual(1, len(entry["contradictions"]))
        self.assertEqual(4, entry["contradictions"][0]["value"])

    def test_duplicate_same_kind_cannot_outvote_independent_sources(self):
        claims = [
            EvidenceClaim("reset.ready_value", 1, "reference_driver", f"driver-copy-{i}", 1.0)
            for i in range(20)
        ]
        claims.extend([
            EvidenceClaim("reset.ready_value", 0, "datasheet", "manual", 1.0),
            EvidenceClaim("reset.ready_value", 0, "schematic", "board", 1.0),
            EvidenceClaim("reset.ready_value", 0, "observation", "trace", 1.0),
        ])
        model = reconcile_evidence(claims)
        entry = model["claims"]["reset.ready_value"]
        self.assertEqual("verified", entry["state"])
        self.assertEqual(0, entry["value"])

    def test_single_source_claim_remains_uncertain(self):
        model = reconcile_evidence([
            EvidenceClaim("undocumented.mode", "x", "reference_driver", "one-driver", 1.0),
        ])
        entry = model["claims"]["undocumented.mode"]
        self.assertEqual("uncertain", entry["state"])
        self.assertIsNone(entry["value"])
        self.assertEqual("x", entry["candidate_value"])

    def test_invalid_or_unbounded_evidence_is_rejected(self):
        with self.assertRaises(ValueError):
            reconcile_evidence([
                EvidenceClaim("register.x", 1, "unknown-source", "mystery", 1.0),
            ])
        with self.assertRaises(ValueError):
            reconcile_evidence([
                EvidenceClaim("register.x", 1, "datasheet", "manual", 1.01),
            ])
        with self.assertRaises(ValueError):
            reconcile_evidence([
                EvidenceClaim("", 1, "datasheet", "manual", 1.0),
            ])

    def test_candidate_is_non_actuating_and_excludes_uncertain_claims(self):
        model = reconcile_evidence([
            EvidenceClaim("register.status", 16, "datasheet", "manual", 0.95),
            EvidenceClaim("register.status", 16, "reference_driver", "linux", 0.95),
            EvidenceClaim("register.mystery", 99, "reference_driver", "linux", 1.0),
        ])
        candidate = synthesize_candidate_interface(model)
        self.assertEqual(CANDIDATE_SCHEMA, candidate["schema"])
        self.assertEqual("non-actuating", candidate["mode"])
        self.assertEqual({"register.status": 16}, candidate["resolved_claims"])
        self.assertIn("replay-non-actuating-behavior-trace", candidate["required_validation"])
        self.assertFalse(candidate["promotion_gates"]["physical_write_authorized"])
        self.assertFalse(candidate["promotion_gates"]["firmware_change_authorized"])
        self.assertTrue(candidate["promotion_gates"]["recovery_path_required_before_physical_actuation"])
        self.assertEqual(["linux"], candidate["reference_driver_teachers"])

    def test_model_identity_is_deterministic_across_input_order(self):
        a = EvidenceClaim("x", 1, "datasheet", "manual", 0.9)
        b = EvidenceClaim("x", 1, "reference_driver", "driver", 0.9)
        first = reconcile_evidence([a, b])
        second = reconcile_evidence([b, a])
        self.assertEqual(first["model_identity"], second["model_identity"])
        self.assertEqual(
            synthesize_candidate_interface(first)["candidate_identity"],
            synthesize_candidate_interface(second)["candidate_identity"],
        )

    def _public_uart_model(self):
        payload = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        self.assertFalse(payload["physical_hardware_observation"])
        return reconcile_evidence([EvidenceClaim(**claim) for claim in payload["claims"]])

    def test_real_public_uart_bundle_reconstructs_correlated_behavior(self):
        model = self._public_uart_model()
        self.assertEqual(16, model["claims"]["fifo.depth_bytes"]["value"])
        self.assertEqual(16, model["claims"]["divisor_latch.width_bits"]["value"])
        self.assertEqual(
            "receive-data-available",
            model["claims"]["line_status.data_ready.meaning"]["value"],
        )
        self.assertEqual(
            "transmit-holding-register-empty",
            model["claims"]["line_status.thre.meaning"]["value"],
        )
        self.assertEqual("uncertain", model["claims"]["line_control.dlab.meaning"]["state"])
        candidate = synthesize_candidate_interface(model)
        self.assertIn(
            "linux:drivers/tty/serial/8250/8250_port.c",
            candidate["reference_driver_teachers"],
        )
        self.assertFalse(candidate["promotion_gates"]["physical_write_authorized"])

    def test_public_uart_register_bindings_are_independently_verified(self):
        payload = json.loads(REGISTER_BINDINGS.read_text(encoding="utf-8"))
        self.assertFalse(payload["physical_hardware_observation"])
        model = reconcile_evidence([EvidenceClaim(**claim) for claim in payload["claims"]])
        self.assertEqual(11, len(model["claims"]))
        self.assertTrue(all(entry["state"] == "verified" for entry in model["claims"].values()))
        self.assertEqual({"offset": 0, "dlab": 0}, model["claims"]["selector.receiver_buffer"]["value"])
        self.assertEqual({"offset": 3, "dlab": "any"}, model["claims"]["selector.line_control"]["value"])
        self.assertEqual({"offset": 5, "dlab": "any"}, model["claims"]["selector.line_status"]["value"])
        self.assertEqual({"offset": 0, "dlab": 1}, model["claims"]["selector.divisor_latch_lsb"]["value"])
        self.assertEqual(128, model["claims"]["mask.line_control.dlab"]["value"])
        self.assertEqual(1, model["claims"]["mask.line_status.data_ready"]["value"])
        self.assertEqual(32, model["claims"]["mask.line_status.thre"]["value"])
        self.assertEqual(64, model["claims"]["mask.line_status.temt"]["value"])
        candidate = synthesize_candidate_interface(model)
        self.assertEqual(11, len(candidate["resolved_claims"]))
        self.assertIn("linux:include/uapi/linux/serial_reg.h", candidate["reference_driver_teachers"])
        self.assertFalse(candidate["promotion_gates"]["physical_write_authorized"])

    def test_reference_derived_trace_passes_complete_verified_claim_replay(self):
        model = self._public_uart_model()
        trace = json.loads(TRACE.read_text(encoding="utf-8"))
        self.assertEqual(BEHAVIOR_TRACE_SCHEMA, trace["schema"])
        self.assertFalse(trace["physical_hardware_observation"])
        verification = verify_behavior_trace(model, trace)
        self.assertEqual(TRACE_VERIFICATION_SCHEMA, verification["schema"])
        self.assertEqual("passed", verification["status"])
        self.assertEqual(1.0, verification["verified_claim_coverage"])
        self.assertFalse(verification["physical_hardware_proof"])
        self.assertFalse(verification["safety"]["hardware_access_performed"])
        self.assertFalse(verification["safety"]["model_claims_promoted"])
        self.assertEqual("uncertain", model["claims"]["line_control.dlab.meaning"]["state"])

    def test_counterfactual_trace_mismatch_fails_closed(self):
        model = self._public_uart_model()
        trace = json.loads(TRACE.read_text(encoding="utf-8"))
        trace["events"][0]["observed_value"] = 64
        verification = verify_behavior_trace(model, trace)
        self.assertEqual("failed", verification["status"])
        self.assertEqual(1, verification["counts"]["mismatched"])
        self.assertIn("fifo.depth_bytes", verification["missing_verified_claims"])

    def test_uncertain_claim_in_trace_cannot_be_upgraded_by_replay(self):
        model = self._public_uart_model()
        trace = json.loads(TRACE.read_text(encoding="utf-8"))
        trace["events"].append({
            "step": 4,
            "claim_key": "line_control.dlab.meaning",
            "observed_value": "divisor-latch-access",
        })
        verification = verify_behavior_trace(model, trace)
        self.assertEqual("incomplete", verification["status"])
        self.assertEqual(1, verification["counts"]["uncertain"])
        self.assertEqual("uncertain", model["claims"]["line_control.dlab.meaning"]["state"])

    def test_trace_order_and_actuation_boundaries_are_enforced(self):
        model = self._public_uart_model()
        trace = json.loads(TRACE.read_text(encoding="utf-8"))
        trace["events"][1]["step"] = 0
        with self.assertRaises(ValueError):
            verify_behavior_trace(model, trace)
        trace = json.loads(TRACE.read_text(encoding="utf-8"))
        trace["actuating"] = True
        with self.assertRaises(ValueError):
            verify_behavior_trace(model, trace)


if __name__ == "__main__":
    unittest.main()
