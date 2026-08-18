from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
RECOVERY = ROOT / ".github" / "workflows" / "aurum-external-evidence-recovery.yml"
AUTOBUILD = ROOT / ".github" / "workflows" / "aurum-autobuild.yml"
COLLECTOR = ROOT / "installer" / "collect-adaptive-shell-gui-live-trial.ps1"


class ExternalEvidenceRecoveryContractTests(unittest.TestCase):
    def test_recovery_is_bounded_to_authorized_windows_and_one_evidence_file(self) -> None:
        workflow = RECOVERY.read_text(encoding="utf-8")
        collector = COLLECTOR.read_text(encoding="utf-8")

        self.assertIn("runs-on: [self-hosted, Windows, X64]", workflow)
        self.assertIn("collect-adaptive-shell-gui-live-trial.ps1", workflow)
        self.assertIn("10.12.194.1", workflow)
        self.assertIn("cff5511ddbb6bf14", workflow)
        self.assertIn("authority_granted -ne $false", workflow)
        self.assertIn("persistent_service_enabled -ne $false", workflow)
        self.assertIn("git add -- $evidence", workflow)
        self.assertIn(
            "Projects/Codelation/autobuild/external_evidence/adaptive_shell_gui_live_trial.json",
            workflow,
        )
        self.assertNotIn("git add -A", workflow)
        self.assertNotIn("git add .", workflow)

        self.assertIn("StrictHostKeyChecking=yes", collector)
        self.assertIn("UserKnownHostsFile=", collector)
        self.assertIn("listener_loopback_only = $true", collector)
        self.assertIn("persistent_service_enabled = $false", collector)
        self.assertIn("user_content_captured = $false", collector)
        self.assertNotIn("systemctl enable", collector)

    def test_autobuild_recovery_dispatch_is_gap_specific_and_deduplicated(self) -> None:
        workflow = AUTOBUILD.read_text(encoding="utf-8")
        self.assertIn("aurum-external-evidence-recovery.yml", workflow)
        self.assertIn("steps.state.outputs.blocked_reason == 'external-prerequisite-blocked'", workflow)
        self.assertIn("steps.state.outputs.next_gap == 'adaptive_shell_gui_live_trial'", workflow)
        self.assertIn("AURUM_EVIDENCE_RECOVERY active=true", workflow)
        self.assertIn("aurum-external-evidence-recover", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
