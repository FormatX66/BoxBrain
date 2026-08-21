import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / '.github' / 'workflows' / 'aurum-pi4-enrollment-diagnostic-once.yml'


class Pi4EnrollmentDiagnosticOnceTests(unittest.TestCase):
    def test_diagnostic_is_one_shot_and_uses_authorized_runner(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn("runs-on: [self-hosted, Windows, X64, aurum-elevated]", text)
        self.assertNotIn('schedule:', text)
        self.assertNotIn('workflow_dispatch:', text)

    def test_diagnostic_deduplicates_active_dual_seed(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn("aurum-dual-seed-lanes.yml", text)
        self.assertIn("DEDUPLICATED_ACTIVE_DUAL_SEED", text)

    def test_diagnostic_requires_strict_seed_and_exact_host_key_fingerprint(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn("PI4_SEED_OK", text)
        self.assertIn("host_key_pretrusted", text)
        self.assertIn("host-key-fingerprint-mismatch", text)
        self.assertIn("SAFETY_STOP", text)
        self.assertIn("UserKnownHostsFile", text)

    def test_diagnostic_surfaces_enrollment_outcome_and_only_wakes_main_on_verified_heartbeat(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn("AURUM_ARKMATX_HEARTBEAT_VERIFIED", text)
        self.assertIn("AURUM_ARKMATX_ENROLLMENT_WAITING", text)
        self.assertIn("HEARTBEAT_VERIFIED", text)
        self.assertIn("aurum-autobuild.yml/dispatches", text)


if __name__ == '__main__':
    unittest.main()
