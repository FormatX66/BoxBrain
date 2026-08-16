import json
import unittest
from pathlib import Path

from Projects.Codelation.driver_transition_synthesis import (
    TRANSITION_CONTRACT_SCHEMA,
    TRANSITION_TRACE_SCHEMA,
    TRANSITION_VERIFICATION_SCHEMA,
    TransitionClaim,
    reconcile_transition_evidence,
    synthesize_transition_contract,
    verify_transition_trace,
)


EVIDENCE = Path(__file__).parents[1] / "driver_evidence" / "tl16c550d_transition_evidence_v0.json"
TRACE = Path(__file__).parents[1] / "driver_evidence" / "tl16c550d_transition_trace_v0.json"


class DriverTransitionSynthesisTests(unittest.TestCase):
    def _public_model(self):
        payload = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        self.assertFalse(payload["physical_hardware_observation"])
        return reconcile_transition_evidence([TransitionClaim(**claim) for claim in payload["claims"]])

    def test_independent_transition_evidence_promotes_verified_rule(self):
        model = reconcile_transition_evidence([
            TransitionClaim(
                "rx.ready",
                {"ready": False},
                {"kind": "receive-character"},
                {"ready": True},
                "datasheet",
                "manual",
                1.0,
            ),
            TransitionClaim(
                "rx.ready",
                {"ready": False},
                {"kind": "receive-character"},
                {"ready": True},
                "emulator",
                "qemu",
                0.95,
            ),
        ])
        entry = model["transitions"]["rx.ready"]
        self.assertEqual("verified", entry["state"])
        self.assertEqual(["datasheet", "emulator"], entry["supporting_source_kinds"])

    def test_duplicate_source_kind_cannot_outvote_independent_transition_sources(self):
        claims = [
            TransitionClaim(
                "reset.ready",
                {"state": "unknown"},
                {"kind": "reset"},
                {"ready": False},
                "emulator",
                f"copy-{index}",
                1.0,
            )
            for index in range(20)
        ]
        claims.extend([
            TransitionClaim(
                "reset.ready",
                {"state": "unknown"},
                {"kind": "reset"},
                {"ready": True},
                "datasheet",
                "manual",
                1.0,
            ),
            TransitionClaim(
                "reset.ready",
                {"state": "unknown"},
                {"kind": "reset"},
                {"ready": True},
                "reference_driver",
                "driver",
                1.0,
            ),
        ])
        model = reconcile_transition_evidence(claims)
        entry = model["transitions"]["reset.ready"]
        self.assertEqual("verified", entry["state"])
        self.assertEqual(True, entry["transition"]["after"]["ready"])
        self.assertEqual(1, len(entry["contradictions"]))

    def test_single_source_transition_remains_uncertain_and_is_not_emitted(self):
        model = reconcile_transition_evidence([
            TransitionClaim(
                "mystery.transition",
                {"x": 0},
                {"kind": "mystery"},
                {"x": 1},
                "emulator",
                "one-model",
                1.0,
            ),
        ])
        self.assertEqual("uncertain", model["transitions"]["mystery.transition"]["state"])
        contract = synthesize_transition_contract(model)
        self.assertEqual(TRANSITION_CONTRACT_SCHEMA, contract["schema"])
        self.assertEqual({}, contract["resolved_transitions"])
        self.assertFalse(contract["promotion_gates"]["physical_write_authorized"])

    def test_public_uart_bundle_reconstructs_six_verified_transition_rules(self):
        model = self._public_model()
        self.assertEqual(6, len(model["transitions"]))
        self.assertTrue(all(entry["state"] == "verified" for entry in model["transitions"].values()))
        self.assertEqual(
            {"lsr.data_ready": False, "lsr.thre": True, "lsr.temt": True},
            model["transitions"]["reset.line_status_defaults"]["transition"]["after"],
        )
        self.assertEqual(
            "divisor-latch-lsb",
            model["transitions"]["dlab.select_divisor_latches"]["transition"]["after"]["offset0.role"],
        )
        contract = synthesize_transition_contract(model)
        self.assertEqual(6, len(contract["resolved_transitions"]))
        self.assertEqual("non-actuating", contract["mode"])

    def test_reference_transition_trace_passes_ordered_complete_replay(self):
        model = self._public_model()
        trace = json.loads(TRACE.read_text(encoding="utf-8"))
        self.assertEqual(TRANSITION_TRACE_SCHEMA, trace["schema"])
        verification = verify_transition_trace(model, trace)
        self.assertEqual(TRANSITION_VERIFICATION_SCHEMA, verification["schema"])
        self.assertEqual("passed", verification["status"])
        self.assertEqual(1.0, verification["verified_transition_coverage"])
        self.assertEqual(6, verification["counts"]["matched"])
        self.assertFalse(verification["physical_hardware_proof"])
        self.assertFalse(verification["safety"]["hardware_access_performed"])
        self.assertFalse(verification["safety"]["model_transitions_promoted"])

    def test_counterfactual_transition_mismatch_fails_closed(self):
        model = self._public_model()
        trace = json.loads(TRACE.read_text(encoding="utf-8"))
        trace["events"][1]["after"]["lsr.data_ready"] = False
        verification = verify_transition_trace(model, trace)
        self.assertEqual("failed", verification["status"])
        self.assertGreaterEqual(verification["counts"]["mismatched"], 1)
        self.assertIn("rx.data_ready_assert_on_receive", verification["missing_verified_transitions"])

    def test_scenario_discontinuity_fails_even_when_each_rule_is_valid(self):
        model = self._public_model()
        trace = json.loads(TRACE.read_text(encoding="utf-8"))
        dlab = trace["events"].pop()
        dlab["scenario"] = "receive-one-byte"
        dlab["step"] = 2
        trace["events"].append(dlab)
        verification = verify_transition_trace(model, trace)
        self.assertEqual("failed", verification["status"])
        self.assertEqual(1, verification["counts"]["discontinuous"])

    def test_physical_or_actuating_transition_traces_are_rejected(self):
        model = self._public_model()
        trace = json.loads(TRACE.read_text(encoding="utf-8"))
        trace["physical_hardware_observation"] = True
        with self.assertRaises(ValueError):
            verify_transition_trace(model, trace)
        trace = json.loads(TRACE.read_text(encoding="utf-8"))
        trace["actuating"] = True
        with self.assertRaises(ValueError):
            verify_transition_trace(model, trace)

    def test_model_and_contract_identity_are_order_independent(self):
        payload = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        claims = [TransitionClaim(**claim) for claim in payload["claims"]]
        first = reconcile_transition_evidence(claims)
        second = reconcile_transition_evidence(reversed(claims))
        self.assertEqual(first["model_identity"], second["model_identity"])
        self.assertEqual(
            synthesize_transition_contract(first)["contract_identity"],
            synthesize_transition_contract(second)["contract_identity"],
        )


if __name__ == "__main__":
    unittest.main()
