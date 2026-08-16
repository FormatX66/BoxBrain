import copy
import json
import unittest
from pathlib import Path

from Projects.Codelation.driver_program_synthesis import (
    PROGRAM_SET_SCHEMA,
    PROGRAM_VERIFICATION_SCHEMA,
    synthesize_abstract_driver_programs,
    verify_abstract_driver_programs,
)
from Projects.Codelation.driver_transition_synthesis import (
    TransitionClaim,
    reconcile_transition_evidence,
)


EVIDENCE = Path(__file__).parents[1] / "driver_evidence" / "tl16c550d_transition_evidence_v0.json"


class DriverProgramSynthesisTests(unittest.TestCase):
    def _public_model(self):
        payload = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        return reconcile_transition_evidence([TransitionClaim(**claim) for claim in payload["claims"]])

    def test_uart_verified_transitions_compose_into_four_abstract_programs(self):
        model = self._public_model()
        programs = synthesize_abstract_driver_programs(model)
        self.assertEqual(PROGRAM_SET_SCHEMA, programs["schema"])
        self.assertEqual("abstract-non-actuating", programs["mode"])
        self.assertFalse(programs["actuating"])
        self.assertFalse(programs["physical_hardware_proof"])
        self.assertFalse(programs["lowering"]["performed"])
        self.assertEqual(4, len(programs["programs"]))
        lengths = sorted(len(program["steps"]) for program in programs["programs"])
        self.assertEqual([1, 1, 2, 2], lengths)
        self.assertEqual(
            sorted(model["transitions"]),
            programs["covered_transition_keys"],
        )

    def test_receive_and_transmit_sequences_are_derived_from_state_continuity(self):
        programs = synthesize_abstract_driver_programs(self._public_model())
        chains = [
            [step["transition_key"] for step in program["steps"]]
            for program in programs["programs"]
        ]
        self.assertIn(
            ["rx.data_ready_assert_on_receive", "rx.data_ready_clear_on_drain"],
            chains,
        )
        self.assertIn(
            ["tx.thre_clear_on_write", "tx.thre_set_on_transfer"],
            chains,
        )

    def test_generated_programs_pass_exact_non_actuating_replay(self):
        model = self._public_model()
        programs = synthesize_abstract_driver_programs(model)
        verification = verify_abstract_driver_programs(model, programs)
        self.assertEqual(PROGRAM_VERIFICATION_SCHEMA, verification["schema"])
        self.assertEqual("passed", verification["status"])
        self.assertEqual(1.0, verification["verified_transition_coverage"])
        self.assertEqual(6, verification["counts"]["matched"])
        self.assertFalse(verification["physical_hardware_proof"])
        self.assertFalse(verification["safety"]["hardware_access_performed"])
        self.assertFalse(verification["safety"]["hardware_lowering_performed"])

    def test_tampered_program_fails_closed(self):
        model = self._public_model()
        programs = synthesize_abstract_driver_programs(model)
        tampered = copy.deepcopy(programs)
        tampered["programs"][0]["steps"][0]["abstract_action"]["kind"] = "invented-action"
        verification = verify_abstract_driver_programs(model, tampered)
        self.assertEqual("failed", verification["status"])
        self.assertEqual(1, verification["counts"]["mismatched"])

    def test_hardware_lowering_or_actuation_is_rejected(self):
        model = self._public_model()
        programs = synthesize_abstract_driver_programs(model)
        lowered = copy.deepcopy(programs)
        lowered["lowering"]["performed"] = True
        with self.assertRaises(ValueError):
            verify_abstract_driver_programs(model, lowered)

        actuating = copy.deepcopy(programs)
        actuating["programs"][0]["actuating"] = True
        with self.assertRaises(ValueError):
            verify_abstract_driver_programs(model, actuating)

    def test_uncertain_transition_is_preserved_but_not_compiled(self):
        model = self._public_model()
        uncertain = reconcile_transition_evidence([
            TransitionClaim(
                "uncertain.only",
                {"x": 0},
                {"kind": "unknown"},
                {"x": 1},
                "emulator",
                "single-source",
                1.0,
            )
        ])
        model["transitions"].update(uncertain["transitions"])
        programs = synthesize_abstract_driver_programs(model)
        self.assertIn("uncertain.only", programs["uncertain_transition_keys"])
        self.assertNotIn("uncertain.only", programs["covered_transition_keys"])

    def test_branching_state_is_not_arbitrarily_collapsed(self):
        claims = []
        for source_kind, source_id in (("datasheet", "manual"), ("emulator", "model")):
            claims.extend([
                TransitionClaim(
                    "enter.shared",
                    {"state": "start"},
                    {"kind": "enter"},
                    {"state": "shared"},
                    source_kind,
                    source_id,
                    1.0,
                ),
                TransitionClaim(
                    "branch.left",
                    {"state": "shared"},
                    {"kind": "left"},
                    {"state": "left"},
                    source_kind,
                    source_id,
                    1.0,
                ),
                TransitionClaim(
                    "branch.right",
                    {"state": "shared"},
                    {"kind": "right"},
                    {"state": "right"},
                    source_kind,
                    source_id,
                    1.0,
                ),
            ])
        model = reconcile_transition_evidence(claims)
        programs = synthesize_abstract_driver_programs(model)
        chains = [
            [step["transition_key"] for step in program["steps"]]
            for program in programs["programs"]
        ]
        self.assertIn(["enter.shared"], chains)
        self.assertIn(["branch.left"], chains)
        self.assertIn(["branch.right"], chains)
        self.assertEqual([{"state": "shared"}], programs["unresolved_branch_states"])
        self.assertEqual(
            "passed",
            verify_abstract_driver_programs(model, programs)["status"],
        )

    def test_program_set_identity_is_deterministic(self):
        model = self._public_model()
        first = synthesize_abstract_driver_programs(model)
        second = synthesize_abstract_driver_programs(model)
        self.assertEqual(first["program_set_identity"], second["program_set_identity"])


if __name__ == "__main__":
    unittest.main()
