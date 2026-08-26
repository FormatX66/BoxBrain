import unittest
from unittest import mock
from pathlib import Path

from Projects.AdaptiveKernel.pi3_overnight_lab import (
    RISK_LEVELS,
    choose_mutable_feature,
    identity_matches,
    parse_ethtool_features,
    parse_throttled,
    policy_tunables,
    risk_index,
    stage_for_fraction,
    tool_path,
)


class Pi3OvernightLabTests(unittest.TestCase):
    def test_admin_tool_resolution_includes_sbin(self):
        with mock.patch("Projects.AdaptiveKernel.pi3_overnight_lab.shutil.which", return_value=None), mock.patch(
            "Projects.AdaptiveKernel.pi3_overnight_lab.Path.is_file", return_value=True
        ), mock.patch("Projects.AdaptiveKernel.pi3_overnight_lab.os.access", return_value=True):
            self.assertEqual((tool_path("modinfo") or "").replace("\\", "/"), "/usr/sbin/modinfo")

    def test_stages_increase_monotonically_with_elapsed_fraction(self):
        observed = [
            stage_for_fraction(value)
            for value in (0.0, 0.14, 0.15, 0.29, 0.30, 0.44, 0.45, 0.59, 0.60, 0.74, 0.75, 1.0)
        ]
        indexes = [risk_index(item) for item in observed]
        self.assertEqual(indexes, sorted(indexes))
        self.assertEqual(observed[0], "observe")
        self.assertEqual(observed[-1], "adaptive-runtime-pressure-canary")

    def test_each_declared_risk_level_is_reachable(self):
        values = {stage_for_fraction(item) for item in (0.0, 0.20, 0.35, 0.50, 0.65, 0.85)}
        self.assertEqual(values, set(RISK_LEVELS))

    def test_live_policy_mapping_uses_only_proven_dirty_page_candidates(self):
        self.assertEqual(policy_tunables("runtime-gen2-conserve-v1"), (5, 10))
        self.assertEqual(policy_tunables("runtime-gen2-balanced-v1"), (8, 16))
        self.assertEqual(policy_tunables("runtime-gen3-opportunistic-v1"), (10, 20))
        self.assertIsNone(policy_tunables("runtime-baseline-v1"))

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


class Pi3OvernightWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[3]
        cls.workflow = (
            root / ".github" / "workflows" / "aurum-pi3-adaptive-kernel-overnight.yml"
        ).read_text(encoding="utf-8")

    def test_pressure_stage_is_manual_bounded_and_serialized(self):
        self.assertIn("workflow_dispatch:", self.workflow)
        self.assertIn("adaptive-runtime-pressure-canary", self.workflow)
        self.assertIn("group: aurum-pi3-adaptive-kernel-overnight", self.workflow)
        self.assertIn("duration must stay between 1 and 330", self.workflow.lower())

    def test_exact_target_uses_one_tcp_check_and_strict_key_only_ssh(self):
        self.assertEqual(self.workflow.count("ConnectAsync($targetAddress, 22)"), 1)
        for token in (
            "169.254.129.122",
            "00000000a6a7df7f",
            "Raspberry Pi 3 Model B Rev 1.2",
            "BatchMode=yes",
            "PasswordAuthentication=no",
            "KbdInteractiveAuthentication=no",
            "IdentitiesOnly=yes",
            "StrictHostKeyChecking=yes",
            "pi3_known_hosts",
        ):
            self.assertIn(token, self.workflow)

    def test_live_governor_is_staged_without_kernel_or_binding_authority(self):
        for token in (
            "adaptive_runtime.py",
            "replacement_kernel_install_allowed = $false",
            "firmware_write_allowed = $false",
            "boot_configuration_write_allowed = $false",
        ):
            self.assertIn(token, self.workflow)


if __name__ == "__main__":
    unittest.main()
