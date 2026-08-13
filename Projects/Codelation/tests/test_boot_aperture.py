from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "field"))

from boot_aperture import boot_aperture_field, choose_boot_aperture  # noqa: E402


class BootApertureTests(unittest.TestCase):
    def test_network_boot_beats_persistent_media_when_both_are_verified(self):
        plan = choose_boot_aperture(
            "pi3-test",
            {
                "pi3-rom-network-boot",
                "authorized-lan",
                "pi3-fat-boot",
                "authorized-removable-media",
            },
        )
        self.assertEqual(plan.mechanism, "pi3-network")
        self.assertFalse(plan.persistent_media_required)

    def test_pi3_fat_remains_a_compatibility_fallback(self):
        plan = choose_boot_aperture(
            "pi3-test",
            {"pi3-fat-boot", "authorized-removable-media"},
        )
        self.assertEqual(plan.mechanism, "pi3-fat-shim")
        self.assertTrue(plan.persistent_media_required)
        self.assertTrue(plan.projection_only)

    def test_unverified_boot_path_is_rejected(self):
        with self.assertRaises(ValueError):
            choose_boot_aperture("blank-target", {"authorized-lan"})

    def test_identity_is_deterministic(self):
        observed = {"pxe-client", "authorized-lan"}
        first = choose_boot_aperture("machine-a", observed)
        second = choose_boot_aperture("machine-a", reversed(sorted(observed)))
        self.assertEqual(first.identity, second.identity)

    def test_field_projection_is_closed(self):
        plan = choose_boot_aperture(
            "uefi-test",
            {"uefi", "authorized-removable-media"},
        )
        field = boot_aperture_field(plan)
        self.assertEqual(field.missing_refs(), set())
        self.assertGreaterEqual(len(field), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
