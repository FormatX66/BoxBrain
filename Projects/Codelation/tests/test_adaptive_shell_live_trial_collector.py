from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
COLLECTOR = ROOT / "installer" / "collect-adaptive-shell-live-trial-readiness.ps1"


class AdaptiveShellLiveTrialCollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = COLLECTOR.read_text(encoding="utf-8")

    def test_collector_is_bound_to_strict_usb_ssh_and_explicit_permission(self) -> None:
        self.assertIn('[ValidateSet("10.12.194.1")]', self.script)
        self.assertIn('"StrictHostKeyChecking=yes"', self.script)
        self.assertIn('"UserKnownHostsFile=$KnownHostsPath"', self.script)
        self.assertIn("[Parameter(Mandatory)]", self.script)
        self.assertIn("AuthorizationReference", self.script)
        self.assertNotIn("StrictHostKeyChecking=no", self.script)

    def test_collector_uses_only_neutral_hid_release_and_retains_no_frame(self) -> None:
        self.assertIn("'{\"action\":\"release\"}'", self.script)
        self.assertNotIn("'{\"action\":\"key\"", self.script)
        self.assertNotIn("'{\"action\":\"text\"", self.script)
        self.assertNotIn("'{\"action\":\"pointer\"", self.script)
        self.assertIn("retained_user_content = $false", self.script)
        self.assertIn("persistent_change_authorized = $false", self.script)


if __name__ == "__main__":
    unittest.main(verbosity=2)
