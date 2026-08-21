import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
DEPLOY = REPO / 'installer' / 'deploy-aurum-live-to-pi.ps1'
BOOTSTRAP = REPO / 'Web' / 'Aurum-Arkmatx' / 'bootstrap.sh'


class Pi4ArkmatxEnrollmentContractTests(unittest.TestCase):
    def test_verified_seed_deploy_reuses_strict_ssh_for_arkmatx_bootstrap(self):
        text = DEPLOY.read_text(encoding='utf-8')
        self.assertIn('Web\\Aurum-Arkmatx\\bootstrap.sh', text)
        self.assertIn('StrictHostKeyChecking=yes', text)
        self.assertIn('UserKnownHostsFile=', text)
        self.assertIn('AURUM_ARKMATX_HEARTBEAT_VERIFIED', text)
        self.assertIn('AURUM_ARKMATX_ENROLLMENT_WAITING', text)
        self.assertIn("rm -f -- '$remoteBootstrap'", text)

    def test_enrollment_failure_does_not_reclassify_verified_seed(self):
        text = DEPLOY.read_text(encoding='utf-8')
        self.assertIn('temporary\n# controller/network failure must not turn a verified gold seed into a false\n# PI4_SEED_FAILURE', text)
        self.assertNotIn('throw "AURUM_ARKMATX_ENROLLMENT', text)

    def test_linux_bootstrap_publishes_identity_and_heartbeat_fields(self):
        text = BOOTSTRAP.read_text(encoding='utf-8')
        self.assertIn('node_enroll', text)
        self.assertIn('node_heartbeat', text)
        self.assertIn('https-outbound', text)
        self.assertIn('uname -s', text)
        self.assertIn('uname -m', text)
        self.assertIn('Aurum node enrolled and heartbeat confirmed.', text)


if __name__ == '__main__':
    unittest.main()
