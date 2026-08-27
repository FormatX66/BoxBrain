from __future__ import annotations

import unittest

from generation_seed_ladder import GenerationEvidence, evaluate_generation, generation_field


GEN1_SOFTWARE = {
    "graphical_shell_contract": True,
    "everyday_traits_contract": True,
    "intent_accessibility_contract": True,
    "recovery_contract": True,
    "unattended_candidate_validation": True,
}
GEN1_EXTERNAL = {
    "hopper_physical_boot": True,
    "guardian_forced_rollback": True,
    "second_architecture_usable": True,
}
GEN2_SOFTWARE = {
    "machine_native_state_projection": True,
    "slush_relationship_model": True,
    "evidence_driven_generation_selector": True,
    "presence_adaptive_resource_shadow": True,
    "adaptive_kernel_driver_shadow": True,
}
GEN2_EXTERNAL = {
    "machine_native_state_recovery": True,
    "presence_policy_physical_canary": True,
}
GEN3_SOFTWARE = {
    "lineage_ledger": True,
    "scoped_trait_inheritance": True,
    "cross_node_evidence_merge": True,
    "phenotype_scope_guard": True,
    "provenance_replay": True,
    "non_widening_trust_guard": True,
}
GEN3_EXTERNAL = {
    "multi_node_live_exchange": True,
    "independent_node_recovery": True,
}


class GenerationSeedLadderTests(unittest.TestCase):
    def test_gen1_software_can_be_ready_without_inventing_physical_proof(self):
        result = evaluate_generation(
            GenerationEvidence(generation="gen1", software=GEN1_SOFTWARE, external={})
        )
        self.assertEqual(result["state"], "software-ready-external-boundary")
        self.assertTrue(result["software_ready"])
        self.assertFalse(result["earned"])
        self.assertFalse(result["infers_physical_proof"])
        self.assertEqual(result["next_gate"], "hopper_physical_boot")

    def test_gen2_can_be_prepared_in_parallel_but_not_earned_before_gen1(self):
        result = evaluate_generation(
            GenerationEvidence(
                generation="gen2",
                software=GEN2_SOFTWARE,
                external=GEN2_EXTERNAL,
                parent_earned=False,
            )
        )
        self.assertTrue(result["software_ready"])
        self.assertFalse(result["earned"])
        self.assertTrue(result["safe_parallel_preparation_allowed"])
        self.assertEqual(result["state"], "software-ready-parent-blocked")
        self.assertEqual(result["next_gate"], "gen1-earned")

    def test_gen3_requires_non_widening_trust_even_with_every_named_gate(self):
        result = evaluate_generation(
            GenerationEvidence(
                generation="gen3",
                software=GEN3_SOFTWARE,
                external=GEN3_EXTERNAL,
                parent_earned=True,
                trust_or_authority_widened=True,
            )
        )
        self.assertEqual(result["state"], "refused")
        self.assertFalse(result["software_ready"])
        self.assertFalse(result["earned"])
        self.assertIn("trust-or-authority-widened", result["invariant_failures"])

    def test_lkg_recovery_provenance_and_compatibility_are_hard_invariants(self):
        result = evaluate_generation(
            GenerationEvidence(
                generation="gen2",
                software=GEN2_SOFTWARE,
                external=GEN2_EXTERNAL,
                parent_earned=True,
                lkg_preserved=False,
                recovery_preserved=False,
                provenance_bound=False,
                compatibility_fallback_preserved=False,
            )
        )
        self.assertEqual(result["state"], "refused")
        self.assertEqual(
            result["invariant_failures"],
            [
                "lkg-not-preserved",
                "recovery-not-preserved",
                "provenance-not-bound",
                "compatibility-fallback-not-preserved",
            ],
        )
        self.assertFalse(result["safe_parallel_preparation_allowed"])

    def test_generation_is_earned_only_when_all_software_external_and_parent_gates_pass(self):
        for generation, software, external, parent_earned in (
            ("gen1", GEN1_SOFTWARE, GEN1_EXTERNAL, False),
            ("gen2", GEN2_SOFTWARE, GEN2_EXTERNAL, True),
            ("gen3", GEN3_SOFTWARE, GEN3_EXTERNAL, True),
        ):
            with self.subTest(generation=generation):
                result = evaluate_generation(
                    GenerationEvidence(
                        generation=generation,
                        software=software,
                        external=external,
                        parent_earned=parent_earned,
                    )
                )
                self.assertEqual(result["state"], "earned")
                self.assertTrue(result["earned"])
                self.assertFalse(result["grants_execution_authority"])
                self.assertFalse(result["grants_mutation_authority"])
                self.assertFalse(result["may_promote_candidate"])

    def test_missing_later_generation_evidence_is_visible_without_blocking_gen1_evaluation(self):
        field = generation_field(
            {
                "gen1": GenerationEvidence(
                    generation="gen1",
                    software=GEN1_SOFTWARE,
                    external={},
                )
            }
        )
        self.assertEqual([item["generation"] for item in field], ["gen1", "gen2", "gen3"])
        self.assertEqual(field[0]["state"], "software-ready-external-boundary")
        self.assertEqual(field[1]["state"], "prepare-software")
        self.assertEqual(field[2]["state"], "prepare-software")

    def test_unknown_generation_fails_closed(self):
        with self.assertRaises(ValueError):
            evaluate_generation(
                GenerationEvidence(generation="gen99", software={}, external={})
            )


if __name__ == "__main__":
    unittest.main()
