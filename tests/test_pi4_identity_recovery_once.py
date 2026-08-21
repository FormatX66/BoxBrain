import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / '.github' / 'workflows' / 'aurum-pi4-identity-recovery-once.yml'


class Pi4IdentityRecoveryOnceContractTests(unittest.TestCase):
    def test_recovery_is_one_shot_and_not_a_scheduler(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn("paths:\n      - '.github/workflows/aurum-pi4-identity-recovery-once.yml'", text)
        self.assertNotIn('schedule:', text)
        self.assertNotIn('workflow_dispatch:', text)

    def test_recovery_deduplicates_active_physical_seed_lane(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn("Get-ActiveWorkflowCount 'aurum-dual-seed-lanes.yml'", text)
        self.assertIn("DEDUPLICATED_ACTIVE_DUAL_SEED", text)

    def test_recovery_requires_existing_strict_seed_and_pinned_host_key(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn("[string]$seed.state -eq 'PI4_SEED_OK'", text)
        self.assertIn("$data.host_key_pretrusted -eq $true", text)
        self.assertIn("host-key-fingerprint-mismatch", text)
        self.assertIn("SAFETY_STOP", text)
        self.assertIn("-UserKnownHostsFile $fingerprintFile", text)

    def test_recovery_reuses_bounded_deploy_and_only_wakes_main_after_heartbeat(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn('installer\\deploy-aurum-live-to-pi.ps1', text)
        self.assertIn('AURUM_ARKMATX_HEARTBEAT_VERIFIED', text)
        self.assertIn('AURUM_ARKMATX_ENROLLMENT_WAITING', text)
        self.assertIn("Get-ActiveWorkflowCount 'aurum-autobuild.yml'", text)
        self.assertIn('aurum-autobuild.yml/dispatches', text)
        self.assertIn("Publish-RecoveryReceipt 'HEARTBEAT_VERIFIED'", text)


if __name__ == '__main__':
    unittest.main()
