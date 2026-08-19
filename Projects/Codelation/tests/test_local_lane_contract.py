from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
AURUM_ENTRY = ROOT / "Aurum.ps1"
ASKER = ROOT / "installer" / "ask-aurum-on-pi.ps1"
AP_HELPER = ROOT / "installer" / "invoke-aurum-via-bbpi4-ap.ps1"
WATCHER = ROOT / "installer" / "aurum-local-lane" / "watch-aurum-local-lane.ps1"
DEPLOYER = ROOT / "installer" / "deploy-aurum-live-to-pi.ps1"
RECONCILER = ROOT / "installer" / "reconcile-existing-aurum-gold-seed-on-pi.ps1"
EVENT_BRIDGE = ROOT / ".github" / "workflows" / "aurum-event-bridge.yml"
AUTHORIZED_WINDOWS_AP = ROOT / ".github" / "workflows" / "aurum-authorized-windows-ap.yml"


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

    def test_direct_entry_can_delegate_to_the_pi_access_point(self):
        entry = AURUM_ENTRY.read_text(encoding="utf-8")
        self.assertIn("[switch]$UsePiAp", entry)
        self.assertIn("invoke-aurum-via-bbpi4-ap.ps1", entry)
        self.assertIn("KeepPiApConnected", entry)

    def test_pi_access_point_route_is_saved_profile_only_and_bounded(self):
        text = AP_HELPER.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertIn('"wlan", "show", "profiles"', text)
        self.assertIn('"wlan", "connect"', text)
        self.assertNotIn("key=clear", lower)
        self.assertNotIn("export profile", lower)
        self.assertIn("MaxProfileAttempts = 6", text)
        self.assertIn('ApAddress = "10.42.194.1"', text)
        self.assertIn(
            "SHA256:X3DUtYg6vgC0krGnD2iQAi/CJfkMHKWB9avM6gXUDXY", text
        )
        self.assertIn("StrictHostKeyChecking=yes", text)
        self.assertIn("-PiAddresses @($ApAddress)", text)
        self.assertIn("AURUM_AP_ROUTE_RESTORED", text)

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

    def test_hosted_validation_completion_explicitly_resumes_windows_lane(self):
        bridge = EVENT_BRIDGE.read_text(encoding="utf-8")
        windows_ap = AUTHORIZED_WINDOWS_AP.read_text(encoding="utf-8")

        self.assertIn("Validate Aurum Local-Lane Self-Heal", bridge)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", bridge)
        self.assertIn("aurum-authorized-windows-ap.yml", bridge)
        self.assertIn("actions: write", bridge)
        self.assertIn("action=deduplicated", bridge)
        self.assertIn("/dispatches", bridge)

        self.assertIn("workflow_dispatch:", windows_ap)
        self.assertIn(".github/receipts/aurum-local-lane-repair-validation.json", windows_ap)
        self.assertIn("validation-not-green", windows_ap)


if __name__ == "__main__":
    unittest.main()
