from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
COLLECTOR = ROOT / "installer" / "collect-adaptive-shell-iteration-observation.ps1"


class AdaptiveShellIterationObservationCollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = COLLECTOR.read_text(encoding="utf-8")

    def test_collector_is_strict_usb_only_and_permission_scoped(self):
        self.assertIn('[ValidateSet("10.12.194.1")]', self.text)
        self.assertIn("StrictHostKeyChecking=yes", self.text)
        self.assertIn("UserKnownHostsFile=", self.text)
        self.assertIn("boxbrain_pi_ed25519", self.text)
        self.assertIn("adaptive-shell-iteration-observation", self.text)
        self.assertIn("AuthorizationReference", self.text)

    def test_collector_reads_status_and_hashes_without_dialogue_content(self):
        self.assertIn("/usr/local/bin/aurum --status", self.text)
        self.assertIn("aurum_dialogue.py --root /opt/boxbrain/codelation status", self.text)
        self.assertIn("sha256sum /usr/local/bin/aurum", self.text)
        self.assertIn("dialogue_generated = $false", self.text)
        self.assertIn("user_content_captured = $false", self.text)
        self.assertNotIn("aurum_dialogue.py --root /opt/boxbrain/codelation session", self.text)
        self.assertNotIn("OPENAI_API_KEY", self.text)


if __name__ == "__main__":
    unittest.main()
