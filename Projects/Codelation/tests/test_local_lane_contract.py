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
EXTERNAL_EVIDENCE_RECOVERY = ROOT / ".github" / "workflows" / "aurum-external-evidence-recovery.yml"


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

    def test_reconciler_preserves_legacy_verification_aliases_without_rejecting_approved_units(self):
        text = RECONCILER.read_text(encoding="utf-8")
        self.assertIn("matching_systemd_units=$new_units_count", text)
        self.assertIn("matching_user_cron=$user_cron_changed", text)
        self.assertIn("matching_root_cron=$root_cron_changed", text)
        self.assertIn("existing_systemd_units=$existing_units_count", text)
        self.assertIn("new_unapproved_systemd_units=$new_units_count", text)
        self.assertNotIn("matching_systemd_units=$existing_units_count", text)

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

    def test_verified_reflash_completion_reenters_event_chain(self):
        bridge = EVENT_BRIDGE.read_text(encoding="utf-8")

        self.assertEqual(
            bridge.count("Aurum PC-01 One-Time Verified Reflash"), 1
        )
        self.assertIn("types: [completed]", bridge)
        self.assertIn("ref='aurum/trunk-v0.01'", bridge)
        self.assertIn("ref='main'", bridge)

    def test_event_bridge_deduplicates_both_autobuild_refs(self):
        bridge = EVENT_BRIDGE.read_text(encoding="utf-8")

        self.assertEqual(bridge.count("workflow='aurum-autobuild.yml'"), 2)
        self.assertEqual(bridge.count("autobuild_ref=$ref"), 2)
        self.assertGreaterEqual(bridge.count('status == "queued"'), 3)
        self.assertGreaterEqual(bridge.count('status == "in_progress"'), 3)
        self.assertIn("ref='aurum/trunk-v0.01'", bridge)
        self.assertIn("ref='main'", bridge)

    def test_external_evidence_recovery_is_default_branch_dispatchable_and_bounded(self):
        self.assertTrue(EXTERNAL_EVIDENCE_RECOVERY.is_file())
        recovery = EXTERNAL_EVIDENCE_RECOVERY.read_text(encoding="utf-8")

        self.assertIn("name: Aurum External Evidence Recovery", recovery)
        self.assertIn("workflow_dispatch:", recovery)
        self.assertIn("ref: aurum/trunk-v0.01", recovery)
        self.assertIn("runs-on: [self-hosted, Windows, X64]", recovery)
        self.assertIn("$evidence.authority_granted -ne $false", recovery)
        for guard in (
            "packages_installed",
            "persistent_service_enabled",
            "raw_disk_changed",
            "firmware_changed",
            "bootloader_changed",
            "security_reduced",
        ):
            self.assertIn(guard, recovery)
        self.assertIn("AURUM_EXTERNAL_EVIDENCE published=true autobuild_trigger=push", recovery)


if __name__ == "__main__":
    unittest.main()
