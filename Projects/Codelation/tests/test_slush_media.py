from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "field"))

from slush_media import (  # noqa: E402
    GIB,
    MIB,
    SlushMediaError,
    check_media_write_gate,
    first_boot_contract,
    plan_pi3_slush_media,
    slush_boot_field,
)


class SlushMediaTests(unittest.TestCase):
    def test_pi3_card_is_boot_shim_plus_slush(self):
        plan = plan_pi3_slush_media(32 * GIB)
        self.assertEqual(plan.target, "raspberry-pi-3")
        self.assertEqual(len(plan.regions), 2)
        self.assertEqual(plan.regions[0].semantic_owner, "compatibility-shim")
        self.assertEqual(plan.regions[0].carrier, "fat-compatible-pi-boot")
        self.assertEqual(plan.regions[1].semantic_owner, "aurum-slush")
        self.assertEqual(plan.regions[1].carrier, "raw-block-region")

    def test_almost_all_capacity_remains_slush(self):
        plan = plan_pi3_slush_media(32 * GIB)
        self.assertGreater(plan.slush_bytes, 31 * GIB)
        self.assertLessEqual(plan.regions[0].size, 256 * MIB)

    def test_plan_identity_is_deterministic(self):
        left = plan_pi3_slush_media(16 * GIB)
        right = plan_pi3_slush_media(16 * GIB)
        self.assertEqual(left.identity, right.identity)

    def test_different_capacity_changes_identity(self):
        self.assertNotEqual(
            plan_pi3_slush_media(16 * GIB).identity,
            plan_pi3_slush_media(32 * GIB).identity,
        )

    def test_too_small_media_is_rejected(self):
        with self.assertRaises(SlushMediaError):
            plan_pi3_slush_media(1 * GIB)

    def test_physical_write_gate_fails_closed(self):
        gate = check_media_write_gate(
            explicit_media_selected=False,
            exact_capacity_verified=False,
            removable_media_verified=False,
            system_disk=False,
            mounted_or_in_use=False,
            operator_authorized_write=False,
        )
        self.assertFalse(gate.allowed)
        self.assertIn("physical-write-not-authorized", gate.reasons)

    def test_system_disk_is_never_accepted_by_gate(self):
        gate = check_media_write_gate(
            explicit_media_selected=True,
            exact_capacity_verified=True,
            removable_media_verified=True,
            system_disk=True,
            mounted_or_in_use=False,
            operator_authorized_write=True,
        )
        self.assertFalse(gate.allowed)
        self.assertIn("system-disk-rejected", gate.reasons)

    def test_unmounted_verified_removable_media_can_pass_gate(self):
        gate = check_media_write_gate(
            explicit_media_selected=True,
            exact_capacity_verified=True,
            removable_media_verified=True,
            system_disk=False,
            mounted_or_in_use=False,
            operator_authorized_write=True,
        )
        self.assertTrue(gate.allowed)
        self.assertEqual(gate.reasons, ())

    def test_first_boot_observes_before_materializing_runtime(self):
        plan = plan_pi3_slush_media(8 * GIB)
        self.assertLess(
            plan.stages.index("observe-hardware"),
            plan.stages.index("materialize-local-runtime"),
        )
        contract = first_boot_contract(plan)
        self.assertTrue(contract["must_observe_before_materialize"])
        self.assertFalse(contract["hardware_profile_prebaked"])
        self.assertFalse(contract["compatibility_shim_is_os_owner"])

    def test_bootstrap_projects_cleanly_into_field(self):
        plan = plan_pi3_slush_media(8 * GIB)
        field = slush_boot_field(
            plan,
            source_node="builder-node",
            boot_assets={"kernel": "sha256:example", "firmware": "sha256:example2"},
        )
        self.assertEqual(field.missing_refs(), set())
        self.assertGreaterEqual(len(field), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
