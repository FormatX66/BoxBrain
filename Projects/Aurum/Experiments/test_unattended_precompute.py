import unittest

from unattended_precompute import PendingPhysicalAction, physical_session_packet, unattended_value


class UnattendedPrecomputeTests(unittest.TestCase):
    def test_likely_high_gap_morning_action_gets_aggressive_precompute(self):
        action = PendingPhysicalAction(
            name="insert flashed USB-C drive into Hopper",
            probability=0.9,
            hours_until_likely_human_action=7.0,
            reality_gap=0.85,
            stacked_gap=0.9,
        )
        packet = physical_session_packet(action)
        self.assertGreaterEqual(unattended_value(action), 0.45)
        self.assertTrue(packet["simulate_failure_families"])
        self.assertTrue(packet["test_alternate_execution_routes"])
        self.assertTrue(packet["lookahead_to_next_boundary"])
        self.assertFalse(packet["physical_effect_allowed"])
        self.assertFalse(packet["authority_granted"])

    def test_low_probability_low_gap_action_stays_lightweight(self):
        action = PendingPhysicalAction(
            name="possible optional cable move",
            probability=0.2,
            hours_until_likely_human_action=2.0,
            reality_gap=0.1,
            stacked_gap=0.1,
        )
        packet = physical_session_packet(action)
        self.assertFalse(packet["simulate_failure_families"])
        self.assertTrue(packet["prepare_success_path"])
        self.assertTrue(packet["prepare_failure_tree"])

    def test_no_reversible_compute_means_no_unattended_value(self):
        action = PendingPhysicalAction(
            name="irreversible physical-only action",
            probability=0.9,
            hours_until_likely_human_action=8.0,
            reality_gap=1.0,
            stacked_gap=1.0,
            reversible_compute_available=False,
        )
        self.assertEqual(unattended_value(action), 0.0)


if __name__ == "__main__":
    unittest.main()
