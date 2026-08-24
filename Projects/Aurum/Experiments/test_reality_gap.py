import unittest

from reality_gap import ProofLevel, RealityTransition, preparation_profile, reality_gap_score


class RealityGapTests(unittest.TestCase):
    def test_concept_to_new_hardware_gets_extra_processing(self):
        profile = preparation_profile(
            RealityTransition(
                proven_at=ProofLevel.CONCEPT,
                target=ProofLevel.NEW_HARDWARE,
                hardware_novelty=0.8,
                firmware_dependency=0.7,
                driver_dependency=0.8,
                external_state_dependency=0.5,
            )
        )
        self.assertGreaterEqual(profile["processing_multiplier"], 2.0)
        self.assertGreaterEqual(profile["surprise_reserve_floor"], 0.25)
        self.assertEqual(profile["lookahead"], "to-boundary")
        self.assertTrue(profile["require_physical_identity_checks"])
        self.assertFalse(profile["authority_granted"])

    def test_small_simulation_step_needs_less_compute(self):
        small = preparation_profile(
            RealityTransition(
                proven_at=ProofLevel.SIMULATED,
                target=ProofLevel.VM_EMULATED,
                hardware_novelty=0.0,
            )
        )
        hardware = preparation_profile(
            RealityTransition(
                proven_at=ProofLevel.SIMULATED,
                target=ProofLevel.NEW_HARDWARE,
                hardware_novelty=0.7,
                driver_dependency=0.7,
            )
        )
        self.assertLess(small["processing_multiplier"], hardware["processing_multiplier"])
        self.assertLess(small["surprise_reserve_floor"], hardware["surprise_reserve_floor"])

    def test_prior_physical_proof_reduces_but_does_not_zero_gap(self):
        raw = RealityTransition(
            proven_at=ProofLevel.VM_EMULATED,
            target=ProofLevel.KNOWN_HARDWARE,
            hardware_novelty=0.4,
            driver_dependency=0.5,
            prior_physical_proof=False,
        )
        proven = RealityTransition(
            proven_at=ProofLevel.VM_EMULATED,
            target=ProofLevel.KNOWN_HARDWARE,
            hardware_novelty=0.4,
            driver_dependency=0.5,
            prior_physical_proof=True,
        )
        self.assertGreater(reality_gap_score(raw), reality_gap_score(proven))
        self.assertGreater(reality_gap_score(proven), 0.0)

    def test_targeting_hardware_always_requires_pass_fail_paths(self):
        profile = preparation_profile(
            RealityTransition(
                proven_at=ProofLevel.CONTROLLED_INTEGRATION,
                target=ProofLevel.KNOWN_HARDWARE,
            )
        )
        self.assertTrue(profile["require_pass_and_fail_paths"])
        self.assertTrue(profile["require_physical_identity_checks"])


if __name__ == "__main__":
    unittest.main()
