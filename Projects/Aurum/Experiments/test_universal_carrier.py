from __future__ import annotations

import unittest

from universal_carrier import CarrierPolicy, Payload, build_carrier_plan


class UniversalCarrierTests(unittest.TestCase):
    def payloads(self):
        return (
            Payload(
                platform="x86_64",
                artifact="Aurum-TinySeed-amd64.iso",
                sha256="a" * 64,
                boot_family="uefi+bios",
            ),
            Payload(
                platform="rpi_arm64",
                artifact="Aurum-TinySeed-Pi-arm64.img.xz",
                sha256="b" * 64,
                boot_family="raspberry-pi-firmware",
            ),
        )

    def plan(self):
        x86, pi = self.payloads()
        return build_carrier_plan(
            lineage_id="aurum-gen1",
            source_commit="c" * 40,
            x86=x86,
            pi=pi,
        )

    def test_shared_seed_and_architecture_specific_frontends_coexist(self):
        plan = self.plan()
        by_name = {p["name"]: p for p in plan["partitions"]}
        self.assertEqual(by_name["AURUM_SEED"]["lineage_id"], "aurum-gen1")
        entries = by_name["AURUM_BOOT"]["entries"]
        self.assertEqual(entries["x86_64_uefi"], "EFI/BOOT/BOOTX64.EFI")
        self.assertEqual(entries["rpi_arm64"], "rpi/config.txt")

    def test_payloads_remain_architecture_separated_and_hash_pinned(self):
        plan = self.plan()
        payloads = next(p for p in plan["partitions"] if p["name"] == "AURUM_PAYLOADS")["payloads"]
        self.assertEqual(payloads["x86_64"]["sha256"], "a" * 64)
        self.assertEqual(payloads["rpi_arm64"]["sha256"], "b" * 64)
        self.assertNotEqual(payloads["x86_64"]["artifact"], payloads["rpi_arm64"]["artifact"])

    def test_node_state_isolation_is_mandatory(self):
        plan = self.plan()
        state = next(p for p in plan["partitions"] if p["name"] == "AURUM_STATE")
        self.assertEqual(state["namespace_rule"], "node-id/platform")
        self.assertFalse(state["cross_node_overwrite_allowed"])

    def test_preparation_never_authorizes_physical_write_or_lkg_mutation(self):
        plan = self.plan()
        self.assertFalse(plan["physical_write_allowed"])
        self.assertFalse(plan["active_state_mutation_allowed"])
        self.assertFalse(plan["lkg_mutation_allowed"])
        self.assertFalse(plan["promotion_allowed"])
        self.assertEqual(plan["status"], "PREPARED_NOT_PHYSICALLY_PROVEN")

    def test_swapped_platform_roles_fail_closed(self):
        x86, pi = self.payloads()
        with self.assertRaises(ValueError):
            build_carrier_plan(
                lineage_id="aurum-gen1",
                source_commit="c" * 40,
                x86=pi,
                pi=x86,
            )

    def test_policy_preserves_nonzero_recovery_reserves(self):
        x86, pi = self.payloads()
        with self.assertRaises(ValueError):
            build_carrier_plan(
                lineage_id="aurum-gen1",
                source_commit="c" * 40,
                x86=x86,
                pi=pi,
                policy=CarrierPolicy(seed_mb=0),
            )


if __name__ == "__main__":
    unittest.main()
