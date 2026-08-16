import copy
import json
import unittest
from pathlib import Path

from Projects.Codelation.driver_lowering_plan import (
    LOWERING_PLAN_SCHEMA,
    LOWERING_VERIFICATION_SCHEMA,
    synthesize_lowering_plan,
    verify_lowering_plan,
)
from Projects.Codelation.driver_program_synthesis import synthesize_abstract_driver_programs
from Projects.Codelation.driver_synthesis import EvidenceClaim, reconcile_evidence
from Projects.Codelation.driver_transition_synthesis import TransitionClaim, reconcile_transition_evidence


EVIDENCE_DIR = Path(__file__).parents[1] / "driver_evidence"
TRANSITIONS = EVIDENCE_DIR / "tl16c550d_transition_evidence_v0.json"
BINDINGS = EVIDENCE_DIR / "tl16c550d_register_bindings_v0.json"


class DriverLoweringPlanTests(unittest.TestCase):
    def _programs(self):
        payload = json.loads(TRANSITIONS.read_text(encoding="utf-8"))
        model = reconcile_transition_evidence([TransitionClaim(**claim) for claim in payload["claims"]])
        return synthesize_abstract_driver_programs(model)

    def _bindings(self):
        payload = json.loads(BINDINGS.read_text(encoding="utf-8"))
        self.assertFalse(payload["physical_hardware_observation"])
        return reconcile_evidence([EvidenceClaim(**claim) for claim in payload["claims"]])

    def _steps_by_action(self, plan):
        return {
            step["abstract_action"]["kind"]: step
            for program in plan["programs"]
            for step in program["steps"]
        }

    def test_uart_programs_lower_to_non_executable_verified_resource_plan(self):
        programs = self._programs()
        bindings = self._bindings()
        plan = synthesize_lowering_plan(programs, bindings)
        self.assertEqual(LOWERING_PLAN_SCHEMA, plan["schema"])
        self.assertEqual("non-executable-plan", plan["mode"])
        self.assertFalse(plan["actuating"])
        self.assertFalse(plan["physical_hardware_proof"])
        self.assertFalse(plan["safety"]["hardware_access_performed"])
        self.assertFalse(plan["safety"]["raw_register_addresses_emitted"])
        self.assertFalse(plan["safety"]["executable_hooks_emitted"])
        self.assertFalse(plan["safety"]["physical_writes_authorized"])

        verification = verify_lowering_plan(programs, bindings, plan)
        self.assertEqual(LOWERING_VERIFICATION_SCHEMA, verification["schema"])
        self.assertEqual("passed", verification["status"])
        self.assertTrue(verification["exact_deterministic_match"])
        self.assertFalse(verification["safety"]["executable_driver_emitted"])

    def test_external_and_internal_transitions_emit_no_bus_touch(self):
        plan = synthesize_lowering_plan(self._programs(), self._bindings())
        steps = self._steps_by_action(plan)
        for kind in ("reset", "receive-character", "transfer-thr-to-shift"):
            lowering = steps[kind]["lowering"]
            self.assertFalse(lowering["bus_touch"])
            self.assertIsNone(lowering["operation"])
            self.assertFalse(lowering["authorized"])

    def test_receiver_read_binds_only_to_verified_rbr_selector(self):
        plan = synthesize_lowering_plan(self._programs(), self._bindings())
        lowering = self._steps_by_action(plan)["read-receiver-buffer"]["lowering"]
        self.assertTrue(lowering["bus_touch"])
        self.assertEqual("register-read-plan", lowering["classification"])
        self.assertEqual("read", lowering["operation"]["access"])
        self.assertEqual("selector.receiver_buffer", lowering["operation"]["selector_binding"])
        self.assertEqual({"offset": 0, "dlab": 0}, lowering["operation"]["selector"])
        self.assertFalse(lowering["authorized"])

    def test_transmit_write_is_metadata_only_and_never_authorized(self):
        plan = synthesize_lowering_plan(self._programs(), self._bindings())
        lowering = self._steps_by_action(plan)["write-transmit-holding"]["lowering"]
        self.assertEqual("register-write-plan-only", lowering["classification"])
        self.assertEqual("planned-write", lowering["operation"]["access"])
        self.assertEqual({"offset": 0, "dlab": 0}, lowering["operation"]["selector"])
        self.assertEqual("transmit-byte", lowering["operation"]["requires_runtime_operand"])
        self.assertFalse(lowering["authorized"])

    def test_dlab_change_binds_selector_and_mask_but_remains_plan_only(self):
        plan = synthesize_lowering_plan(self._programs(), self._bindings())
        lowering = self._steps_by_action(plan)["set-dlab"]["lowering"]
        self.assertEqual("register-read-modify-write-plan-only", lowering["classification"])
        self.assertEqual("planned-read-modify-write", lowering["operation"]["access"])
        self.assertEqual({"offset": 3, "dlab": "any"}, lowering["operation"]["selector"])
        self.assertEqual(128, lowering["operation"]["mask"])
        self.assertTrue(lowering["operation"]["desired_bit_set"])
        self.assertFalse(lowering["authorized"])

    def test_missing_or_unverified_required_binding_fails_closed(self):
        bindings = self._bindings()
        bindings["claims"]["selector.receiver_buffer"]["state"] = "uncertain"
        bindings["claims"]["selector.receiver_buffer"]["value"] = None
        with self.assertRaises(ValueError):
            synthesize_lowering_plan(self._programs(), bindings)

    def test_unknown_abstract_action_is_not_guessed_into_hardware(self):
        programs = self._programs()
        programs["programs"][0]["steps"][0]["abstract_action"] = {"kind": "human-label-without-rule"}
        with self.assertRaises(ValueError):
            synthesize_lowering_plan(programs, self._bindings())

    def test_tampered_selector_fails_exact_lowering_verification(self):
        programs = self._programs()
        bindings = self._bindings()
        plan = synthesize_lowering_plan(programs, bindings)
        tampered = copy.deepcopy(plan)
        step = self._steps_by_action(tampered)["read-receiver-buffer"]
        step["lowering"]["operation"]["selector"]["offset"] = 7
        verification = verify_lowering_plan(programs, bindings, tampered)
        self.assertEqual("failed", verification["status"])
        self.assertFalse(verification["exact_deterministic_match"])

    def test_raw_address_or_executable_surface_is_rejected(self):
        programs = self._programs()
        bindings = self._bindings()
        plan = synthesize_lowering_plan(programs, bindings)
        injected = copy.deepcopy(plan)
        injected["programs"][0]["raw"] = {"mmio_address": 4096}
        with self.assertRaises(ValueError):
            verify_lowering_plan(programs, bindings, injected)

        injected = copy.deepcopy(plan)
        injected["programs"][0]["hook"] = "do_io"
        with self.assertRaises(ValueError):
            verify_lowering_plan(programs, bindings, injected)

    def test_lowering_identity_is_deterministic(self):
        programs = self._programs()
        bindings = self._bindings()
        first = synthesize_lowering_plan(programs, bindings)
        second = synthesize_lowering_plan(programs, bindings)
        self.assertEqual(first["lowering_plan_identity"], second["lowering_plan_identity"])


if __name__ == "__main__":
    unittest.main()
