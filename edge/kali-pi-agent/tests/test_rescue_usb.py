from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPOSITE = ROOT / "scripts/boxbrain-usb-composite.sh"
EARLY_SERVICE = ROOT / "systemd/boxbrain-rescue-early.service"
GADGET_SERVICE = ROOT / "systemd/boxbrain-usb-gadget.service"
INSTALLER = ROOT / "scripts/install.sh"


class RescueUsbIntegrationTests(unittest.TestCase):
    def test_composite_only_accepts_dedicated_rescue_image_store(self) -> None:
        script = COMPOSITE.read_text(encoding="utf-8")
        self.assertIn('"$rescue_state_directory"/rescue-images/*', script)
        self.assertIn("Refusing to export anything outside", script)
        self.assertNotIn("/dev/root", script)
        self.assertNotIn("/dev/mmcblk", script)

    def test_composite_adds_one_rescue_mass_storage_function(self) -> None:
        script = COMPOSITE.read_text(encoding="utf-8")
        self.assertIn("functions/mass_storage.rescue", script)
        self.assertIn("lun.0/file", script)
        self.assertIn("lun.0/ro", script)
        self.assertIn("load_rescue_image", script)

    def test_early_consumer_runs_before_usb_gadget(self) -> None:
        early = EARLY_SERVICE.read_text(encoding="utf-8")
        gadget = GADGET_SERVICE.read_text(encoding="utf-8")
        self.assertIn("Before=boxbrain-usb-gadget.service", early)
        self.assertIn("boxbrainctl rescue consume-early", early)
        self.assertIn("After=boxbrain-rescue-early.service", gadget)
        self.assertIn("TimeoutStartSec=10min", gadget)

    def test_installer_preserves_images_outside_git_checkout(self) -> None:
        installer = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("/var/lib/boxbrain/rescue-images", installer)
        self.assertIn("boxbrain-rescue-early.service", installer)
        self.assertNotIn("rescue-images /opt/boxbrain", installer)

    def test_shell_scripts_parse(self) -> None:
        shell = shutil.which("sh")
        if shell is None:
            self.skipTest("POSIX sh is unavailable")
        for script in (COMPOSITE, INSTALLER):
            result = subprocess.run(
                [shell, "-n", str(script)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
