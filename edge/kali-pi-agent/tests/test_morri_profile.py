from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[1]


class MorriProfileTests(unittest.TestCase):
    def test_onboarding_allowlists_profile_installer(self) -> None:
        onboarding = (
            ROOT / "src" / "boxbrain" / "onboarding.py"
        ).read_text(encoding="utf-8")

        self.assertIn('"/install-morri-profile.ps1"', onboarding)
        self.assertIn('"install-morri-profile.ps1"', onboarding)

    def test_profile_installer_creates_standard_profile_only(self) -> None:
        install = (
            REPOSITORY_ROOT / "installer" / "install-morri-profile.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn('Set-MorriProfileStatus -Status "awaiting_password"', install)
        self.assertIn('Read-Host "Temporary password', install)
        self.assertIn('S-1-5-32-545', install)
        self.assertIn('S-1-5-32-544', install)
        self.assertIn('LoadUserProfile', install)
        self.assertIn('/passwordreq:yes', install)
        self.assertIn('/logonpasswordchg:yes', install)
        self.assertIn('Disable-LocalUser', install)
        self.assertNotIn('Add-LocalGroupMember -Group "Administrators"', install)

    def test_bootstrap_keeps_password_out_of_command_line(self) -> None:
        bootstrap = (
            REPOSITORY_ROOT / "installer" / "start-morri-profile-bootstrap.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("install-morri-profile.ps1", bootstrap)
        self.assertIn("SendPasswordOnly", bootstrap)
        self.assertIn("RandomNumberGenerator", bootstrap)
        self.assertIn('action = "character"', bootstrap)
        self.assertIn("result.acknowledged", bootstrap)
        self.assertIn("Start-Sleep -Milliseconds 40", bootstrap)
        self.assertNotIn("temporaryPassword +", bootstrap)


if __name__ == "__main__":
    unittest.main()
