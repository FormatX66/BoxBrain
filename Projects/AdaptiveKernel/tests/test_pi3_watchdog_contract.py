from __future__ import annotations

import unittest

from Projects.AdaptiveKernel.pi3_watchdog_contract import (
    WatchdogEvidence,
    WatchdogState,
    evaluate_watchdog,
)


class Pi3WatchdogContractTests(unittest.TestCase):
    def evidence(self, **changes) -> WatchdogEvidence:
        values = {
            "pinned_target_identity": True,
            "independent_controller_identity": True,
            "observer_independent_of_target_kernel": True,
            "recovery_actuator_independent_of_target_kernel": True,
            "automatic_failure_detection_proven": True,
            "automatic_recovery_actuation_proven": True,
            "post_recovery_target_identity_proven": True,
            "lkg_restored_and_healthy_proven": True,
            "local_target_timer_only": False,
            "network_only_actuation": False,
            "mutation_authority_granted": False,
        }
        values.update(changes)
        return WatchdogEvidence(**values)

    def test_complete_oob_evidence_proves_prerequisite_but_not_mutation_authority(self):
        result = evaluate_watchdog(self.evidence(mutation_authority_granted=True))
        self.assertEqual(result.state, WatchdogState.PROVEN)
        self.assertTrue(result.watchdog_proven)
        self.assertFalse(result.mutation_authority_granted)
        self.assertEqual(result.next_gate, "fresh-explicit-kernel-mutation-authority")

    def test_local_target_timer_is_not_out_of_band(self):
        result = evaluate_watchdog(self.evidence(local_target_timer_only=True))
        self.assertEqual(result.state, WatchdogState.HELD_OBSERVER)
        self.assertFalse(result.watchdog_proven)

    def test_ssh_or_network_only_recovery_is_not_an_independent_actuator(self):
        result = evaluate_watchdog(self.evidence(network_only_actuation=True))
        self.assertEqual(result.state, WatchdogState.HELD_ACTUATOR)
        self.assertEqual(result.next_gate, "prove-independent-recovery-actuator")

    def test_controller_and_target_identity_must_be_pinned(self):
        result = evaluate_watchdog(self.evidence(independent_controller_identity=False))
        self.assertEqual(result.state, WatchdogState.HELD_IDENTITY)

    def test_actuator_claim_without_exercised_recovery_cycle_is_held(self):
        result = evaluate_watchdog(
            self.evidence(automatic_recovery_actuation_proven=False)
        )
        self.assertEqual(result.state, WatchdogState.HELD_RECOVERY)

    def test_recovery_must_end_in_proven_lkg_health(self):
        result = evaluate_watchdog(
            self.evidence(lkg_restored_and_healthy_proven=False)
        )
        self.assertEqual(result.state, WatchdogState.HELD_LKG)


if __name__ == "__main__":
    unittest.main()
