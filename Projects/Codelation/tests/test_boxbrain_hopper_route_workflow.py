from pathlib import Path
import unittest


WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "aurum-boxbrain-hopper-route-test.yml"


class BoxBrainHopperRouteWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_keyscan_stderr_isolated_from_windows_powershell_error_stream(self):
        text = self.workflow
        self.assertIn("Start-Process -FilePath $keyscan", text)
        self.assertIn("-RedirectStandardOutput $scanOut", text)
        self.assertIn("-RedirectStandardError $scanErr", text)
        self.assertNotIn("@(& $keyscan -T 4 -t ed25519 $target 2>$null", text)
        self.assertIn("keyscan_exit=$scanExit", text)

    def test_host_identity_still_fails_closed(self):
        text = self.workflow
        self.assertIn("SHA256:X3DUtYg6vgC0krGnD2iQAi/CJfkMHKWB9avM6gXUDXY", text)
        self.assertIn("fingerprint-mismatch", text)
        self.assertIn("StrictHostKeyChecking=yes", text)
        self.assertIn("BatchMode=yes", text)
        self.assertIn("IdentitiesOnly=yes", text)

    def test_route_probe_remains_read_only_evidence(self):
        text = self.workflow
        self.assertIn("schema = 'aurum-boxbrain-hopper-route-proof-v1'", text)
        self.assertIn("read_only = $true", text)
        self.assertIn("AURUM_BOXBRAIN_HOPPER_ROUTE_TEST", text)
        self.assertIn("BOXBRAIN_TO_HOPPER_ROUTE_PROVEN", text)


if __name__ == "__main__":
    unittest.main()
