import copy
import json
import unittest
from pathlib import Path

from Projects.Codelation.driver_lowering_plan import synthesize_lowering_plan
from Projects.Codelation.driver_program_synthesis import synthesize_abstract_driver_programs
from Projects.Codelation.driver_synthesis import EvidenceClaim, reconcile_evidence
from Projects.Codelation.driver_transition_synthesis import TransitionClaim, reconcile_transition_evidence
from Projects.Codelation.driver_virtual_executor import VIRTUAL_EXECUTION_SCHEMA, execute_virtual_program


EVIDENCE_DIR = Path(__file__).parents[1] / "driver_evidence"
TRANSITIONS = EVIDENCE_DIR / "tl16c550d_transition_evidence_v0.json"
BINDINGS = EVIDENCE_DIR / "tl16c550d_register_bindings_v0.json"


class DriverVirtualExecutorTests(unittest.TestCase):
    def _plan(self):
        transition_payload = json.loads(TRANSITIONS.read_text(encoding="utf-8"))
        transition_model = reconcile_transition_evidence([
            TransitionClaim(**claim) for claim in transition_payload["claims"]
        ])
        programs = synthesize_abstract_driver_programs(transition_model)
        binding_payload = json.loads(BINDINGS.read_text(encoding="utf-8"))
        binding_model = reconcile_evidence([
            EvidenceClaim(**claim) for claim in binding_payload["claims"]
        ])
        return synthesize_lowering_plan(programs, binding_model)

    def _program_id_with_actions(self, plan, expected_actions):
        for program in plan["programs"]:
            actions = [step["abstract_action"]["kind"] for step in program["steps"]]
            if actions == expected_actions:
                return program["source_program_identity"]
        self.fail(f"program with actions {expected_actions!r} was not found")

    def test_receive_program_reads_only_initialized_logical_rbr(self):
        plan = self._plan()
        program_id = self._program_id_with_actions(
            plan, ["receive-character", "read-receiver-buffer"]
        )
        result = execute_virtual_program(
            plan,
            program_id,
            logical_registers={"selector.receiver_buffer": 0x5A},
        )
        self.assertEqual(VIRTUAL_EXECUTION_SCHEMA, result["schema"])
        self.assertEqual("in-memory-logical-registers-only", result["mode"])
        self.assertEqual(0x5A, result["outputs"]["received-byte"])
        self.assertEqual(0x5A, result["final_logical_registers"]["selector.receiver_buffer"])
        self.assertFalse(result["physical_hardware_proof"])
        self.assertFalse(result["safety"]["hardware_access_performed"])
        self.assertTrue(result["safety"]["virtual_dictionary_writes_only"])
        self.assertEqual("none", result["events"][0]["virtual_effect"])
        self.assertEqual("read", result["events"][1]["virtual_effect"])

    def test_transmit_program_writes_only_in_memory_with_explicit_runtime_byte(self):
        plan = self._plan()
        program_id = self._program_id_with_actions(
            plan, ["write-transmit-holding", "transfer-thr-to-shift"]
        )
        result = execute_virtual_program(
            plan,
            program_id,
            runtime_operands={"transmit-byte": 0xA5},
        )
        self.assertEqual(0xA5, result["final_logical_registers"]["selector.transmit_holding"])
        self.assertEqual("write-in-memory-only", result["events"][0]["virtual_effect"])
        self.assertEqual("none", result["events"][1]["virtual_effect"])
        self.assertFalse(result["safety"]["physical_writes_performed"])

    def test_dlab_plan_changes_only_virtual_line_control_bit(self):
        plan = self._plan()
        program_id = self._program_id_with_actions(plan, ["set-dlab"])
        result = execute_virtual_program(
            plan,
            program_id,
            logical_registers={"selector.line_control": 0x03},
        )
        self.assertEqual(0x83, result["final_logical_registers"]["selector.line_control"])
        event = result["events"][0]
        self.assertEqual("read-modify-write-in-memory-only", event["virtual_effect"])
        self.assertEqual(0x03, event["before"])
        self.assertEqual(0x83, event["after"])
        self.assertEqual(0x80, event["mask"])

    def test_reset_program_has_no_virtual_bus_effect(self):
        plan = self._plan()
        program_id = self._program_id_with_actions(plan, ["reset"])
        result = execute_virtual_program(plan, program_id)
        self.assertEqual({}, result["final_logical_registers"])
        self.assertEqual("none", result["events"][0]["virtual_effect"])

    def test_missing_virtual_read_state_or_write_operand_fails_closed(self):
        plan = self._plan()
        receive_id = self._program_id_with_actions(
            plan, ["receive-character", "read-receiver-buffer"]
        )
        with self.assertRaises(ValueError):
            execute_virtual_program(plan, receive_id)

        transmit_id = self._program_id_with_actions(
            plan, ["write-transmit-holding", "transfer-thr-to-shift"]
        )
        with self.assertRaises(ValueError):
            execute_virtual_program(plan, transmit_id)

    def test_non_byte_operands_and_non_logical_register_keys_are_rejected(self):
        plan = self._plan()
        transmit_id = self._program_id_with_actions(
            plan, ["write-transmit-holding", "transfer-thr-to-shift"]
        )
        with self.assertRaises(ValueError):
            execute_virtual_program(
                plan, transmit_id, runtime_operands={"transmit-byte": 999}
            )
        with self.assertRaises(ValueError):
            execute_virtual_program(
                plan,
                transmit_id,
                logical_registers={"0x3f8": 0},
                runtime_operands={"transmit-byte": 1},
            )

    def test_any_physical_write_authorization_in_plan_is_rejected(self):
        plan = self._plan()
        unsafe = copy.deepcopy(plan)
        unsafe["safety"]["physical_writes_authorized"] = True
        program_id = unsafe["programs"][0]["source_program_identity"]
        with self.assertRaises(ValueError):
            execute_virtual_program(unsafe, program_id)

    def test_virtual_execution_identity_is_deterministic(self):
        plan = self._plan()
        program_id = self._program_id_with_actions(plan, ["set-dlab"])
        first = execute_virtual_program(
            plan, program_id, logical_registers={"selector.line_control": 3}
        )
        second = execute_virtual_program(
            plan, program_id, logical_registers={"selector.line_control": 3}
        )
        self.assertEqual(first["execution_identity"], second["execution_identity"])


if __name__ == "__main__":
    unittest.main()
