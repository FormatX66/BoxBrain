from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
BUILDER = ROOT / "build-hopper-recovery-iso.sh"
RECOVERY = ROOT / "aurum_seed_recovery.py"
ASSETS = ROOT / "recovery-assets"


class HopperRecoveryIsoContractTests(unittest.TestCase):
    def test_image_is_one_shot_recovery_not_an_installer(self) -> None:
        builder = BUILDER.read_text(encoding="utf-8")
        grub = (ASSETS / "grub.cfg").read_text(encoding="utf-8")
        isolinux = (ASSETS / "isolinux.cfg").read_text(encoding="utf-8")
        for text in (grub, isolinux):
            self.assertIn("aurum_hopper_recovery=1", text)
            self.assertIn("systemd.unit=aurum-hopper-seed-recovery.target", text)
            self.assertIn("@KERNEL_LIVE@", text)
            self.assertIn("@INITRD_LIVE@", text)
            self.assertNotIn("installer", text.lower())
        self.assertIn("filesystem.aurum-recovery.squashfs", builder)
        self.assertIn("filesystem.module", builder)
        self.assertIn("refusing to overwrite", builder)
        self.assertIn("xorriso", builder)
        self.assertIn("SIGNED_KERNEL_PROVEN", builder)
        self.assertIn("refusing a Secure Boot recovery image", builder)

    def test_recovery_is_machine_commit_and_path_bound(self) -> None:
        recovery = RECOVERY.read_text(encoding="utf-8")
        builder = BUILDER.read_text(encoding="utf-8")
        self.assertIn("BTTE934116YM512B-1", builder)
        self.assertIn("512110190592", builder)
        self.assertIn("aurum_desktop.py", builder)
        self.assertIn("aurum_hopper_gui.py", builder)
        self.assertIn("expected_head", recovery)
        self.assertIn('f" M {path}"', recovery)
        self.assertIn('"restore"', recovery)
        self.assertIn("temporary-ui.patch", recovery)
        self.assertNotIn("shell=True", recovery)

    def test_service_has_no_general_live_session(self) -> None:
        service = (ASSETS / "aurum-hopper-seed-recovery.service").read_text(encoding="utf-8")
        target = (ASSETS / "aurum-hopper-seed-recovery.target").read_text(encoding="utf-8")
        self.assertIn("--execute --poweroff", service)
        self.assertIn("ConditionKernelCommandLine=aurum_hopper_recovery=1", service)
        self.assertIn("NoNewPrivileges=yes", service)
        self.assertIn("Requires=basic.target aurum-hopper-seed-recovery.service", target)


if __name__ == "__main__":
    unittest.main()
