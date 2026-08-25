import json
import unittest
from pathlib import Path


CONTRACT = Path(__file__).with_name("SELF_BUILD_LIFECYCLE.json")


class TinySeedSelfBuildLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.phases = self.contract["phases"]

    def test_tinyseed_is_the_initiator_and_phase_order_is_stable(self) -> None:
        self.assertEqual(self.contract["initiator"], "tinyseed")
        self.assertEqual(
            [phase["id"] for phase in self.phases],
            [
                "external-generic-discovery",
                "tinyseed-install",
                "internal-first-boot",
                "full-aurum-growth",
                "adaptive-trial",
            ],
        )

    def test_discovery_deepens_from_species_to_specimen(self) -> None:
        self.assertEqual(self.phases[0]["observes"], "machine-species")
        self.assertEqual(self.phases[2]["observes"], "machine-specimen")
        self.assertEqual(self.phases[0]["boot"], 0)
        self.assertEqual(self.phases[2]["boot"], 1)

    def test_network_and_cloud_build_routing_are_early_but_not_recovery_dependencies(self) -> None:
        network = self.contract["network_bootstrap"]
        self.assertEqual(network["route_order"][1], "wifi-onboarding")
        self.assertTrue(network["network_authority_required"])
        self.assertTrue(network["local_artifact_verification_required"])
        self.assertTrue(network["local_boot_health_proof_required"])
        self.assertTrue(network["offline_recovery_must_remain_viable"])
        self.assertIn("classical-compiler-builder", network["cloud_roles"])
        self.assertIn(
            "network-capability-receipt", self.phases[0]["outputs"]
        )

    def test_first_internal_boot_establishes_machine_native_substrates(self) -> None:
        outputs = set(self.phases[2]["outputs"])
        self.assertTrue(
            {"soil-bootstrap", "field-bootstrap", "slush-bootstrap"} <= outputs
        )

    def test_full_growth_never_replaces_the_running_lkg_in_place(self) -> None:
        growth = self.phases[3]
        self.assertEqual(growth["kernel_role"], "first-boot-lkg")
        self.assertIn("adaptive-kernel-candidate", growth["outputs"])
        self.assertIn("inactive-candidate", growth["rollback"])
        self.assertTrue(self.contract["future_branch"]["preserve_lkg"])
        self.assertTrue(self.contract["future_branch"]["candidate_slot_required"])

    def test_adaptive_kernel_activates_only_at_trial_boot(self) -> None:
        trial = self.phases[4]
        self.assertEqual(trial["boot"], 2)
        self.assertEqual(trial["kernel_role"], "adaptive-candidate")
        self.assertIn("automatic", trial["rollback"])

    def test_qpu_is_attributed_acceleration_not_proof(self) -> None:
        future_branch = self.contract["future_branch"]
        self.assertIn("optional-attributed", future_branch["qpu_role"])
        self.assertFalse(future_branch["qpu_is_build_or-health-proof"])


if __name__ == "__main__":
    unittest.main()
