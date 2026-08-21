import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "Web" / "Aurum-Arkmatx"
DASHBOARD = WEB / "dashboard.html"
VOICE = WEB / "voice-status.php"
SNAPSHOT = WEB / "voice-status-snapshot.json"
STATIC_JSON = WEB / "voice-status.json"
STATIC_TEXT = WEB / "voice-status.txt"
STATIC_VIEW = WEB / "voice-status" / "index.html"
HTACCESS = WEB / ".htaccess"
DEPLOY = ROOT / ".github" / "workflows" / "deploy-aurum-arkmatx.yml"
REPO_MIRROR = ROOT / "AURUM_VOICE_STATUS.md"


class DashboardVoiceStatusContractTests(unittest.TestCase):
    def test_dashboard_consumes_the_voice_mirror(self):
        text = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("Progress is proof, not activity.", text)
        self.assertIn("voice-status.json", text)
        self.assertIn("EVERYDAY HUMAN CAPABILITIES", text)
        for stage in ("Defined", "Executable", "Tested", "Seeded", "Booted", "Used"):
            self.assertIn(stage, text)
        self.assertNotIn("stage=contract", text)

    def test_snapshot_uses_six_honest_evidence_gates(self):
        payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        self.assertEqual("aurum-voice-status-v1", payload["schema"])
        self.assertEqual("awaiting-boot-proof", payload["overall"]["state"])
        capabilities = payload["human_capabilities"]
        self.assertEqual(7, len(capabilities))
        expected = {"defined", "executable", "tested", "seeded", "booted", "used"}
        for capability in capabilities:
            self.assertEqual(expected, set(capability["stages"]))
            self.assertTrue(capability["stages"]["defined"])
            self.assertTrue(capability["stages"]["executable"])
            self.assertTrue(capability["stages"]["tested"])
            self.assertTrue(capability["stages"]["seeded"])
            self.assertFalse(capability["stages"]["booted"])
            self.assertFalse(capability["stages"]["used"])

    def test_live_voice_status_requires_source_commit_evidence_for_later_gates(self):
        text = VOICE.read_text(encoding="utf-8")
        self.assertIn("AURUM VOICE STATUS", text)
        self.assertIn("pc_seed_integration_utc", text)
        self.assertIn("pi_seed_integration_utc", text)
        self.assertIn("Aurum PC v0.01 Image", text)
        self.assertIn("Aurum Dual Seed Lanes", text)
        self.assertIn("PHYSICAL_USE_OK", text)
        self.assertIn("aurum_run_head_time", text)
        self.assertIn("source commit timestamp", text)
        self.assertIn("verified_success", text)
        self.assertIn("aurum_set_all_stage($payload, 'seeded', true)", text)
        self.assertIn("aurum_set_all_stage($payload, 'booted', true)", text)
        self.assertNotIn("Authorization: Bearer", text)

    def test_no_secret_static_voice_mirrors_match_the_seeded_floor(self):
        payload = json.loads(STATIC_JSON.read_text(encoding="utf-8"))
        self.assertEqual("repository-static-mirror", payload["source"])
        self.assertEqual("awaiting-boot-proof", payload["overall"]["state"])
        self.assertEqual(7, len(payload["human_capabilities"]))
        for capability in payload["human_capabilities"]:
            self.assertTrue(capability["stages"]["seeded"])
            self.assertFalse(capability["stages"]["booted"])
            self.assertFalse(capability["stages"]["used"])
        text = STATIC_TEXT.read_text(encoding="utf-8")
        self.assertIn("AURUM VOICE STATUS", text)
        self.assertIn("4/6", text)
        self.assertIn("run 32525836598", text)
        view = STATIC_VIEW.read_text(encoding="utf-8")
        self.assertIn("../voice-status.txt", view)
        self.assertIn("Read Aurum Voice Status", view)

    def test_stable_voice_routes_and_repository_fallback_exist(self):
        routes = HTACCESS.read_text(encoding="utf-8")
        self.assertIn("^voice-status/?$", routes)
        self.assertIn("^voice-status\\.json$", routes)
        mirror = REPO_MIRROR.read_text(encoding="utf-8")
        self.assertIn("Read Aurum Voice Status", mirror)
        self.assertIn("AURUM_VOICE_STATUS.md", mirror)
        self.assertIn("Defined, Executable, Tested, and Seeded on BBPI4", mirror)
        self.assertIn("4/6", mirror)
        self.assertIn("Deploying into an already-running seed earns", mirror)
        self.assertIn("raw.githubusercontent.com", mirror)

    def test_deployment_validates_static_mirrors_without_hosting_secrets(self):
        text = DEPLOY.read_text(encoding="utf-8")
        self.assertIn("Detect hosted deployment configuration", text)
        self.assertIn("configured=false", text)
        self.assertIn("Validate no-secret dashboard and voice mirrors", text)
        self.assertIn("WEB_STATIC_MIRROR_OK", text)
        self.assertIn("web-static-mirror-{run_id}-attempt-{attempt}.json", text)
        self.assertIn("steps.config.outputs.configured == 'true'", text)
        self.assertIn("steps.config.outputs.configured != 'true'", text)
        self.assertNotIn("Missing $name", text)

    def test_hosted_deployment_still_lints_verifies_and_receipts_both_surfaces(self):
        text = DEPLOY.read_text(encoding="utf-8")
        self.assertIn("php -l '$REMOTE_PATH/voice-status.php'", text)
        self.assertIn("$base/dashboard", text)
        self.assertIn("$base/voice-status", text)
        self.assertIn("$base/voice-status.json", text)
        self.assertIn("AURUM_VOICE_MIRROR_OK", text)
        self.assertIn("WEB_MIRROR_OK", text)
        self.assertIn("web-mirror-{run_id}-attempt-{attempt}.json", text)


if __name__ == "__main__":
    unittest.main()
