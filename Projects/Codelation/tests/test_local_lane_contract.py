from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
AURUM_ENTRY = ROOT / "Aurum.ps1"
ASKER = ROOT / "installer" / "ask-aurum-on-pi.ps1"
WATCHER = ROOT / "installer" / "aurum-local-lane" / "watch-aurum-local-lane.ps1"
DEPLOYER = ROOT / "installer" / "deploy-aurum-live-to-pi.ps1"
RECONCILER = ROOT / "installer" / "reconcile-existing-aurum-gold-seed-on-pi.ps1"


class LocalLaneContractTests(unittest.TestCase):
    def test_deployer_delegates_to_reconciler_with_bounded_bbpi4_routes(self):
        deployer = DEPLOYER.read_text(encoding="utf-8")
        reconciler = RECONCILER.read_text(encoding="utf-8")
        self.assertIn("reconcile-existing-aurum-gold-seed-on-pi.ps1", deployer)
        for address in ("10.42.194.1", "10.12.194.1", "192.168.0.194"):
            self.assertIn(address, reconciler)
        self.assertIn("foreach ($address in $PiAddresses)", reconciler)
        self.assertIn("AURUM_GOLD_SEED_PRESERVED", reconciler)
        self.assertIn("new_unapproved_systemd_units=0", reconciler)

    def test_direct_entry_prefers_current_morri_usb_ssh_route(self):
        expected = '@("10.12.194.1", "10.42.194.1", "192.168.0.194")'
        for path in (AURUM_ENTRY, DEPLOYER, ASKER):
            text = path.read_text(encoding="utf-8")
            self.assertIn(expected, text, path)
        entry = AURUM_ENTRY.read_text(encoding="utf-8")
        self.assertIn("-PiAddresses $PiAddresses", entry)
        self.assertIn("USB-SSH first", entry)

    def test_codelation_is_diagnostic_not_an_aurum_gate(self):
        text = RECONCILER.read_text(encoding="utf-8")
        self.assertIn("test_aurum_live.py", text)
        self.assertIn("test_aurum_dialogue.py", text)
        self.assertIn("codelation_diagnostic_status=failed-nonblocking", text)
        self.assertNotIn("codelation_tests=passed", text)

    def test_watcher_does_not_force_the_lan_only_route(self):
        text = WATCHER.read_text(encoding="utf-8")
        self.assertNotIn('-PiAddresses "192.168.0.194"', text)
        self.assertIn("-File $deployer -KeyPath", text)

    def test_verification_probes_the_same_approved_route_set(self):
        text = WATCHER.read_text(encoding="utf-8")
        self.assertIn(
            '$addresses = @("10.42.194.1", "10.12.194.1", "192.168.0.194")',
            text,
        )
        self.assertIn("foreach ($address in $addresses)", text)
        self.assertIn("Address = $address; Text = $text", text)


if __name__ == "__main__":
    unittest.main()
