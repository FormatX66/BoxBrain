import unittest

from Projects.AdaptiveKernel.pi3_overnight_lab import (
    RISK_LEVELS,
    choose_mutable_feature,
    identity_matches,
    parse_ethtool_features,
    parse_throttled,
    risk_index,
    stage_for_fraction,
)


class Pi3OvernightLabTests(unittest.TestCase):
    def test_stages_increase_monotonically_with_elapsed_fraction(self):
        observed = [
            stage_for_fraction(value)
            for value in (0.0, 0.19, 0.20, 0.49, 0.50, 0.69, 0.70, 0.84, 0.85, 1.0)
        ]
        indexes = [risk_index(item) for item in observed]
        self.assertEqual(indexes, sorted(indexes))
        self.assertEqual(observed[0], "observe")
        self.assertEqual(observed[-1], "smsc95xx-feature-canary")

    def test_each_declared_risk_level_is_reachable(self):
        values = {stage_for_fraction(item) for item in (0.0, 0.25, 0.55, 0.75, 0.90)}
        self.assertEqual(values, set(RISK_LEVELS))

    def test_current_throttle_fault_is_separate_from_history(self):
        current = parse_throttled("throttled=0x50005")
        self.assertTrue(current["current_fault"])
        self.assertTrue(current["historical_fault"])
        historical = parse_throttled("throttled=0x50000")
        self.assertFalse(historical["current_fault"])
        self.assertTrue(historical["historical_fault"])

    def test_feature_parser_rejects_fixed_features_for_canary(self):
        features = parse_ethtool_features(
            "Features for eth0:\n"
            "rx-checksumming: on [fixed]\n"
            "tx-checksumming: on\n"
            "generic-receive-offload: off\n"
        )
        self.assertTrue(features["rx-checksumming"]["fixed"])
        self.assertEqual(choose_mutable_feature(features), "tx-checksumming")

    def test_identity_gate_requires_model_serial_root_and_reference_driver(self):
        identity = {
            "model": "Raspberry Pi 3 Model B Rev 1.2",
            "serial": "00000000a6a7df7f",
            "root_source": "/dev/mmcblk0p2",
            "reference_driver": "smsc95xx",
        }
        self.assertTrue(identity_matches(identity))
        for field, replacement in (
            ("model", "Raspberry Pi 4 Model B"),
            ("serial", "0000000000000000"),
            ("root_source", "/dev/sda2"),
            ("reference_driver", "other"),
        ):
            changed = dict(identity)
            changed[field] = replacement
            self.assertFalse(identity_matches(changed), field)


if __name__ == "__main__":
    unittest.main()
