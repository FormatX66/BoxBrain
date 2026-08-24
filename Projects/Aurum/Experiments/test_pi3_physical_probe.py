import unittest

from pi3_physical_probe import (
    PI3_RECEIPT_SCHEMA,
    build_observe_only_trial,
    gate_receipt,
)


class Pi3PhysicalProbeTests(unittest.TestCase):
    def sample(self):
        return {
            "schema": PI3_RECEIPT_SCHEMA,
            "captured_at": "2026-08-24T15:30:00+00:00",
            "hostname": "aurum-pi3",
            "model": "Raspberry Pi 3 Model B Plus Rev 1.3",
            "arch": "armv7l",
            "kernel": "6.6.0-test",
            "cores": 4,
            "ram_mb": 927,
            "boot_id": "11111111-2222-3333-4444-555555555555",
            "interfaces": ["eth0", "lo", "wlan0"],
        }

    def test_realistic_pi3_receipt_opens_observe_only_gate(self):
        gate = gate_receipt(self.sample())
        self.assertTrue(gate["accepted"])
        self.assertEqual(gate["gate"], "physical-receipt-valid")
        self.assertFalse(gate["promotion_allowed"])
        self.assertFalse(gate["mutation_allowed"])

    def test_non_pi3_receipt_fails_closed(self):
        receipt = self.sample()
        receipt["model"] = "GitHub Actions virtual machine"
        gate = gate_receipt(receipt)
        self.assertFalse(gate["accepted"])
        self.assertIn("model-not-raspberry-pi-3", gate["problems"])

    def test_missing_boot_receipt_fails_closed(self):
        receipt = self.sample()
        receipt["boot_id"] = ""
        gate = gate_receipt(receipt)
        self.assertFalse(gate["accepted"])
        self.assertIn("missing-boot-receipt", gate["problems"])

    def test_valid_receipt_builds_stateweave_kernel_trial_without_promotion(self):
        trial = build_observe_only_trial(self.sample())
        self.assertEqual(trial["kernel_plan"]["action"], "stage-candidate")
        self.assertFalse(trial["kernel_plan"]["promotion_allowed"])
        self.assertFalse(trial["promotion_allowed"])
        self.assertEqual(trial["rollback_target"], "pi3-current-observed")
        self.assertIn("probe-mesh-read-only", trial["future_branch_next"])


if __name__ == "__main__":
    unittest.main()
