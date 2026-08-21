import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ENTRY = ROOT / "installer" / "deploy-aurum-live-to-pi.ps1"
DEPLOYER = ROOT / "installer" / "deploy-aurum-traits-to-pi.ps1"


class Pi4HumanTraitContractTests(unittest.TestCase):
    def test_verified_seed_entry_invokes_bounded_trait_deployer(self):
        text = ENTRY.read_text(encoding="utf-8")
        self.assertIn("deploy-aurum-traits-to-pi.ps1", text)
        self.assertIn("& $traitDeployer @arguments", text)
        self.assertIn("same pretrusted carrier", text)

    def test_trait_deployer_carries_all_runtime_material(self):
        text = DEPLOYER.read_text(encoding="utf-8")
        for required in (
            "traits.json",
            "validate_traits.py",
            "aurum_traits.py",
            "tests\\test_aurum_traits.py",
            "build-all",
            "verify-bundle",
            "AURUM_HUMAN_TRAITS_DEPLOYED",
            "AURUM_PI4_HUMAN_TRAITS_OK",
            "bundles=7",
            "garden --root",
        ):
            self.assertIn(required, text)

    def test_trait_deployer_preserves_strict_transport_and_rollback(self):
        text = DEPLOYER.read_text(encoding="utf-8")
        self.assertIn("StrictHostKeyChecking=yes", text)
        self.assertIn("UserKnownHostsFile", text)
        self.assertIn("ROLLBACK_ROOT=/opt/boxbrain/rollback", text)
        self.assertIn("AURUM_HUMAN_TRAIT_ROLLBACK restored=true", text)
        self.assertIn("persistence_added=0", text)

    def test_trait_deployer_emits_actionable_remote_failure_evidence(self):
        text = DEPLOYER.read_text(encoding="utf-8")
        self.assertIn("AURUM_HUMAN_TRAIT_STEP_FAILED", text)
        self.assertIn("STEP=functional-tests", text)
        self.assertIn("STEP=build-seven-bundles", text)
        self.assertIn("STEP=activate-next-generation", text)
        self.assertIn("Get-NativeFailureDetail", text)
        self.assertIn("failed (exit $($run.ExitCode))", text)
        self.assertNotIn("${trait,,}", text)

    def test_remote_installer_is_normalized_to_linux_line_endings(self):
        text = DEPLOYER.read_text(encoding="utf-8")
        self.assertIn('$remote.Replace("`r`n", "`n")', text)
        self.assertIn("invalid bash\\r", text)
        normalization = text.index('$remote = $remote.Replace("`r`n", "`n")')
        write = text.index("[IO.File]::WriteAllText")
        self.assertLess(normalization, write)

    def test_next_generation_is_verified_before_activation(self):
        text = DEPLOYER.read_text(encoding="utf-8")
        prepare = text.index("STEP=prepare-next-generation")
        verify = text.index("STEP=verify-next-generation")
        preserve = text.index("STEP=preserve-current-generation")
        activate = text.index("STEP=activate-next-generation")
        self.assertLess(prepare, verify)
        self.assertLess(verify, preserve)
        self.assertLess(preserve, activate)

    def test_trait_deployer_does_not_add_persistence_or_packages(self):
        lowered = DEPLOYER.read_text(encoding="utf-8").lower()
        for forbidden in (
            "systemctl enable",
            "crontab -",
            "apt-get install",
            "apt install",
            "dnf install",
            "pacman -s",
        ):
            self.assertNotIn(forbidden, lowered)


if __name__ == "__main__":
    unittest.main()
