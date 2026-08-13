from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "field"))

from pi3_boot_shim import (  # noqa: E402
    BootAsset,
    BootShimError,
    boot_shim_field,
    build_cmdline_txt,
    build_config_txt,
    build_pi3_boot_shim,
    first_boot_os_build_contract,
    inspect_boot_asset_directory,
    required_external_assets,
    verify_boot_shim,
)
from slush_media import GIB, plan_pi3_slush_media  # noqa: E402


class Pi3BootShimTests(unittest.TestCase):
    def _assets(self):
        return tuple(
            BootAsset(
                name=name,
                role=role,
                size=100 + index,
                sha256=hashlib.sha256(name.encode("utf-8")).hexdigest(),
                source="test-source@abc123",
            )
            for index, (name, role) in enumerate(sorted(required_external_assets().items()))
        )

    def test_required_assets_include_pi3_firmware_kernel_initramfs_and_dtbs(self):
        names = set(required_external_assets())
        self.assertTrue(
            {
                "bootcode.bin",
                "start.elf",
                "fixup.dat",
                "kernel8.img",
                "initramfs",
                "bcm2710-rpi-3-b.dtb",
                "bcm2710-rpi-3-b-plus.dtb",
            }.issubset(names)
        )

    def test_generated_boot_configuration_has_no_root_filesystem(self):
        plan = plan_pi3_slush_media(8 * GIB)
        config = build_config_txt()
        cmdline = build_cmdline_txt(plan.identity)
        self.assertIn("arm_64bit=1", config)
        self.assertIn("kernel=kernel8.img", config)
        self.assertIn("initramfs initramfs followkernel", config)
        self.assertIn("rdinit=/aurum-init", cmdline)
        self.assertNotIn("root=", cmdline)
        self.assertIn(plan.identity, cmdline)

    def test_shim_identity_is_deterministic(self):
        plan = plan_pi3_slush_media(8 * GIB)
        left = build_pi3_boot_shim(plan, source_revision="abc123", assets=self._assets())
        right = build_pi3_boot_shim(plan, source_revision="abc123", assets=reversed(self._assets()))
        self.assertEqual(left.identity, right.identity)
        self.assertFalse(left.rootfs_prebuilt)

    def test_source_revision_changes_identity(self):
        plan = plan_pi3_slush_media(8 * GIB)
        left = build_pi3_boot_shim(plan, source_revision="abc123", assets=self._assets())
        right = build_pi3_boot_shim(plan, source_revision="def456", assets=self._assets())
        self.assertNotEqual(left.identity, right.identity)

    def test_missing_asset_is_rejected(self):
        plan = plan_pi3_slush_media(8 * GIB)
        assets = tuple(item for item in self._assets() if item.name != "kernel8.img")
        with self.assertRaises(BootShimError):
            build_pi3_boot_shim(plan, source_revision="abc123", assets=assets)

    def test_verify_rejects_shim_for_other_media_plan(self):
        first = plan_pi3_slush_media(8 * GIB)
        second = plan_pi3_slush_media(16 * GIB)
        shim = build_pi3_boot_shim(first, source_revision="abc123", assets=self._assets())
        with self.assertRaises(BootShimError):
            verify_boot_shim(shim, second)

    def test_boot_shim_projects_cleanly_into_field(self):
        plan = plan_pi3_slush_media(8 * GIB)
        shim = build_pi3_boot_shim(plan, source_revision="abc123", assets=self._assets())
        field = boot_shim_field(shim)
        self.assertEqual(field.missing_refs(), set())
        self.assertGreaterEqual(len(field), len(self._assets()) + 2)

    def test_first_boot_contract_builds_after_observation(self):
        plan = plan_pi3_slush_media(8 * GIB)
        shim = build_pi3_boot_shim(plan, source_revision="abc123", assets=self._assets())
        contract = first_boot_os_build_contract(shim)
        self.assertFalse(contract["rootfs_prebuilt"])
        self.assertTrue(contract["record_observations_before_materialization"])
        self.assertTrue(contract["derive_runtime_from_observed_capabilities"])
        self.assertTrue(contract["verify_runtime_before_promotion"])
        self.assertTrue(contract["retain_boot_shim_as_recovery_carrier"])

    def test_asset_directory_inspection_hashes_pinned_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in required_external_assets():
                (root / name).write_bytes(("asset:" + name).encode("utf-8"))
            assets = inspect_boot_asset_directory(root, source_revision="abc123")
            by_name = {asset.name: asset for asset in assets}
            self.assertEqual(
                by_name["kernel8.img"].sha256,
                hashlib.sha256(b"asset:kernel8.img").hexdigest(),
            )
            self.assertIn("@abc123", by_name["kernel8.img"].source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
