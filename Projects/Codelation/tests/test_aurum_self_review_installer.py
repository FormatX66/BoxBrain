from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
INSTALLER = ROOT / "installer" / "install-aurum-self-review-on-pi.ps1"
REVIEWER = ROOT / "installer" / "review-aurum-mind-on-pi.ps1"


class AurumSelfReviewInstallerTests(unittest.TestCase):
    def test_installer_is_hash_checked_rollback_safe_and_persistence_free(self):
        text = INSTALLER.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertIn("Get-FileHash", text)
        self.assertIn("sha256sum", text)
        self.assertIn("python3 -m py_compile", text)
        self.assertIn("rollback()", text)
        self.assertIn("existing_dialogue_supervisor_missing", text)
        self.assertIn("StrictHostKeyChecking=yes", text)
        self.assertIn("AURUM_SELF_REVIEW_INSTALL_VERIFIED", text)
        for forbidden in (
            "systemctl",
            "crontab",
            "register-scheduledtask",
            "schtasks",
            "currentversion\\run",
        ):
            self.assertNotIn(forbidden, lower)

    def test_review_entry_point_uses_ephemeral_stdin_payload_and_fixed_root(self):
        text = REVIEWER.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertIn("OPENAI_API_KEY", text)
        self.assertIn("--payload-stdin", text)
        self.assertIn("/opt/boxbrain/codelation", text)
        self.assertIn("StrictHostKeyChecking=yes", text)
        self.assertIn("AURUM_ITERATIVE_SELF_REVIEW_COMPLETE", text)
        self.assertNotIn("set-content", lower)
        self.assertNotIn("out-file", lower)
        self.assertNotIn("systemctl", lower)
        self.assertNotIn("crontab", lower)


if __name__ == "__main__":
    unittest.main()
