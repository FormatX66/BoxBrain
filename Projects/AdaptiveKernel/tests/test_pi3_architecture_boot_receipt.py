from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
RECEIPT = (
    ROOT
    / "Projects"
    / "AdaptiveKernel"
    / "results"
    / "pi3-architecture-accurate-boot-latest.json"
)


class Pi3ArchitectureBootReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))

    def test_exact_trial_kernel_reached_arm64_init(self) -> None:
        self.assertEqual(
            self.receipt["state"], "architecture-accurate-boot-to-init-proven"
        )
        self.assertEqual(self.receipt["target_profile"]["qemu_machine"], "raspi3b")
        self.assertEqual(self.receipt["target_profile"]["cpu_count"], 4)
        self.assertEqual(
            self.receipt["candidate"]["kernel_release"],
            "6.12.105-aurum-pi3-v0.02+",
        )
        markers = self.receipt["verified_markers"]
        self.assertTrue(any("Mounted root" in marker for marker in markers))
        self.assertIn("Run /sbin/init as init process", markers)

    def test_receipt_cannot_grant_physical_authority(self) -> None:
        invariants = self.receipt["invariants"]
        for field in (
            "sd_card_written",
            "base_image_written",
            "physical_pi_contacted",
            "kernel_installed_on_physical_pi",
            "driver_binding_changed",
            "reference_driver_changed",
            "last_known_good_changed",
            "mutation_authority_granted",
        ):
            self.assertIs(invariants[field], False, field)
        self.assertEqual(
            self.receipt["next_gate"],
            "independent-automatic-out-of-band-recovery-proof",
        )


if __name__ == "__main__":
    unittest.main()
