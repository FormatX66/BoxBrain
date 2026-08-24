import unittest

from human_availability import HumanMode, boundary_policy, default_profile_for_hour


class HumanAvailabilityTests(unittest.TestCase):
    def test_morning_update_is_prepared_before_request(self):
        profile = default_profile_for_hour(6)
        self.assertEqual(profile.mode, HumanMode.MORNING_UPDATE)
        self.assertTrue(profile.likely_wants_summary)
        self.assertFalse(profile.likely_near_hardware)
        self.assertGreaterEqual(profile.machine_preparation_bias, 0.8)

    def test_daytime_favors_machine_work(self):
        profile = default_profile_for_hour(12)
        self.assertEqual(profile.mode, HumanMode.DAYTIME_MACHINE_HEAVY)
        self.assertEqual(profile.machine_preparation_bias, 1.0)
        self.assertFalse(profile.suitable_for_long_human_procedure)

    def test_evening_surfaces_physical_action(self):
        profile = default_profile_for_hour(18)
        policy = boundary_policy(human_required=True, physical_required=True, profile=profile)
        self.assertTrue(policy["execution_blocked"])
        self.assertTrue(policy["surface_human_action_now"])

    def test_physical_blocker_never_stops_future_branch_preparation(self):
        profile = default_profile_for_hour(12)
        policy = boundary_policy(human_required=True, physical_required=True, profile=profile)
        self.assertTrue(policy["execution_blocked"])
        self.assertTrue(policy["future_branch_analysis_continues"])
        self.assertTrue(policy["prepare_success_path"])
        self.assertTrue(policy["prepare_failure_paths"])
        self.assertTrue(policy["prepare_diagnostics"])
        self.assertTrue(policy["prepare_recovery"])
        self.assertFalse(policy["surface_human_action_now"])

    def test_late_night_logic_mode(self):
        profile = default_profile_for_hour(23)
        self.assertEqual(profile.mode, HumanMode.LATE_NIGHT_LOGIC)
        self.assertTrue(profile.likely_near_hardware)

    def test_invalid_hour_refused(self):
        with self.assertRaises(ValueError):
            default_profile_for_hour(24)


if __name__ == "__main__":
    unittest.main()
