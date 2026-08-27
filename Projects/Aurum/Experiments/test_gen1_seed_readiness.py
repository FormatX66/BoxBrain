from __future__ import annotations

import unittest

from gen1_seed_readiness import (
    Gen1SoftwareEvidence,
    REQUIRED_EVERYDAY_TRAITS,
    project_gen1_software,
)


SOURCE = "1" * 40
CARRIER = "2" * 40


def complete_traits():
    return {trait: True for trait in REQUIRED_EVERYDAY_TRAITS}


def complete_evidence(**changes):
    values = {
        "source_revision": SOURCE,
        "carrier_revision": CARRIER,
        "traits": complete_traits(),
        "graphical_shell_verified": True,
        "intent_accessibility_verified": True,
        "recovery_contract_verified": True,
        "unattended_candidate_validation_verified": True,
        "source_carrier_provenance_bound": True,
    }
    values.update(changes)
    return Gen1SoftwareEvidence(**values)


class Gen1SeedReadinessTests(unittest.TestCase):
    def test_complete_software_evidence_stops_at_physical_boundary(self):
        result = project_gen1_software(complete_evidence())
        self.assertTrue(all(result["software"].values()))
        self.assertTrue(result["ladder"]["software_ready"])
        self.assertFalse(result["ladder"]["earned"])
        self.assertEqual(result["ladder"]["state"], "software-ready-external-boundary")
        self.assertEqual(result["ladder"]["next_gate"], "hopper_physical_boot")
        self.assertFalse(result["physical_gates_supplied_by_this_projector"])
        self.assertFalse(result["hopper_physical_boot"])
        self.assertFalse(result["guardian_forced_rollback"])
        self.assertFalse(result["second_architecture_usable"])

    def test_every_required_everyday_trait_is_a_hard_software_gate(self):
        for missing in REQUIRED_EVERYDAY_TRAITS:
            with self.subTest(missing=missing):
                traits = complete_traits()
                traits[missing] = False
                result = project_gen1_software(complete_evidence(traits=traits))
                self.assertFalse(result["traits"][missing])
                self.assertFalse(result["software"]["everyday_traits_contract"])
                self.assertFalse(result["ladder"]["software_ready"])
                self.assertEqual(result["ladder"]["next_gate"], "everyday_traits_contract")

    def test_truthy_strings_do_not_count_as_verified(self):
        traits = complete_traits()
        traits["TR8:WEB"] = "true"
        result = project_gen1_software(
            complete_evidence(
                traits=traits,
                graphical_shell_verified="true",
            )
        )
        self.assertFalse(result["traits"]["TR8:WEB"])
        self.assertFalse(result["software"]["graphical_shell_contract"])
        self.assertFalse(result["software"]["everyday_traits_contract"])

    def test_unbound_source_carrier_provenance_refuses_readiness(self):
        result = project_gen1_software(
            complete_evidence(source_carrier_provenance_bound=False)
        )
        self.assertEqual(result["ladder"]["state"], "refused")
        self.assertIn("provenance-not-bound", result["ladder"]["invariant_failures"])
        self.assertFalse(result["ladder"]["software_ready"])

    def test_lkg_recovery_and_compatibility_are_hard_invariants(self):
        for field, reason in (
            ("lkg_preserved", "lkg-not-preserved"),
            ("recovery_preserved", "recovery-not-preserved"),
            ("compatibility_fallback_preserved", "compatibility-fallback-not-preserved"),
        ):
            with self.subTest(field=field):
                result = project_gen1_software(complete_evidence(**{field: False}))
                self.assertEqual(result["ladder"]["state"], "refused")
                self.assertIn(reason, result["ladder"]["invariant_failures"])

    def test_trust_or_authority_widening_is_refused(self):
        result = project_gen1_software(
            complete_evidence(trust_or_authority_widened=True)
        )
        self.assertEqual(result["ladder"]["state"], "refused")
        self.assertIn("trust-or-authority-widened", result["ladder"]["invariant_failures"])

    def test_invalid_revision_provenance_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "40-character"):
            project_gen1_software(complete_evidence(source_revision="main"))
        with self.assertRaisesRegex(ValueError, "40-character"):
            project_gen1_software(complete_evidence(carrier_revision="bad"))

    def test_projector_never_grants_mutation_write_or_promotion(self):
        result = project_gen1_software(complete_evidence())
        self.assertFalse(result["grants_write_authority"])
        self.assertFalse(result["grants_mutation_authority"])
        self.assertFalse(result["may_promote_candidate"])
        self.assertFalse(result["ladder"]["grants_execution_authority"])
        self.assertFalse(result["ladder"]["grants_mutation_authority"])
        self.assertFalse(result["ladder"]["may_promote_candidate"])


if __name__ == "__main__":
    unittest.main()
