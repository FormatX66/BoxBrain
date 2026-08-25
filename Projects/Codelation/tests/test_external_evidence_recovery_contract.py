from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
RECOVERY = ROOT / ".github" / "workflows" / "aurum-external-evidence-recovery.yml"
AUTOBUILD = ROOT / ".github" / "workflows" / "aurum-autobuild.yml"
COLLECTOR = ROOT / "installer" / "collect-adaptive-shell-gui-live-trial.ps1"
APPROVED_ROUTES = (
    "10.12.194.1",
    "10.42.194.1",
    "bbpi4.local",
    "192.168.0.194",
)


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

    def test_recovery_survives_windows_runner_home_drift_without_weakening_ssh_identity(self) -> None:
        workflow = RECOVERY.read_text(encoding="utf-8")

        self.assertIn("$keyCandidates", workflow)
        self.assertIn("Join-Path $env:USERPROFILE '.ssh\\boxbrain_pi_ed25519'", workflow)
        self.assertIn("Get-ChildItem 'C:\\Users' -Directory", workflow)
        self.assertIn("Split-Path -Parent $key", workflow)
        self.assertIn("Join-Path $keyDirectory 'known_hosts'", workflow)
        self.assertIn("The dedicated BBPI4 SSH key is unavailable", workflow)
        self.assertIn("The pinned SSH known-hosts file is unavailable", workflow)
        self.assertIn("$env:RUNNER_TEMP", workflow)
        self.assertIn("[IO.File]::WriteAllBytes($strictKey, [IO.File]::ReadAllBytes($key))", workflow)
        self.assertIn("icacls.exe", workflow)
        self.assertIn("/inheritance:r", workflow)
        self.assertIn("/grant:r", workflow)
        self.assertIn("Remove-Item -LiteralPath $strictKey -Force", workflow)

    def test_recovery_falls_back_only_across_preapproved_bbpi4_ssh_routes(self) -> None:
        workflow = RECOVERY.read_text(encoding="utf-8")
        collector = COLLECTOR.read_text(encoding="utf-8")

        for route in APPROVED_ROUTES:
            self.assertIn(route, workflow)
            self.assertIn(route, collector)
        self.assertIn("foreach ($route in $approvedRoutes)", workflow)
        self.assertIn("$approvedRoutes -notcontains [string]$evidence.route", workflow)
        self.assertIn("[ValidateSet(", collector)
        self.assertIn("StrictHostKeyChecking=yes", collector)
        self.assertNotIn("StrictHostKeyChecking=no", collector)
        self.assertNotIn("ssh-keyscan", workflow)
        self.assertNotIn("ssh-keyscan", collector)

    def test_collector_uses_native_ssh_exit_code_instead_of_treating_stderr_as_failure(self) -> None:
        collector = COLLECTOR.read_text(encoding="utf-8")

        self.assertIn("$savedErrorActionPreference = $ErrorActionPreference", collector)
        self.assertIn('$ErrorActionPreference = "Continue"', collector)
        self.assertIn("$exitCode = $LASTEXITCODE", collector)
        self.assertIn("$ErrorActionPreference = $savedErrorActionPreference", collector)
        self.assertIn("if ($exitCode -ne 0 -and -not $AllowFailure)", collector)
        self.assertLess(
            collector.index('$ErrorActionPreference = "Continue"'),
            collector.index("$exitCode = $LASTEXITCODE"),
        )

    def test_runtime_contract_failure_reports_content_free_reason_codes(self) -> None:
        collector = COLLECTOR.read_text(encoding="utf-8")

        self.assertIn("AURUM_GUI_CONTRACT_MISMATCH", collector)
        self.assertIn("content_free=true", collector)
        self.assertIn("$runtimeContract = [ordered]@{", collector)
        self.assertIn("$failed = @($runtimeContract.GetEnumerator()", collector)
        for reason in (
            "deployment_schema",
            "node_identity",
            "start_transient",
            "module_hash",
            "gui_schema",
            "self_status_schema",
            "console_identity",
            "host_actuation",
            "api_key_persistence",
            "safe_layout",
            "proof_view",
            "page_hash",
            "status_hash",
            "http_status",
            "content_type",
            "service_active",
            "service_not_enabled",
            "loopback_listener",
            "no_nonloopback_listener",
        ):
            self.assertIn(reason, collector)
        self.assertNotIn("api_status_payload=", collector)
        self.assertNotIn("api_key=", collector)

    def test_autobuild_recovery_dispatch_is_gap_specific_and_deduplicated(self) -> None:
        workflow = AUTOBUILD.read_text(encoding="utf-8")
        self.assertIn("aurum-external-evidence-recovery.yml", workflow)
        self.assertIn("steps.state.outputs.blocked_reason == 'external-prerequisite-blocked'", workflow)
        self.assertIn("steps.state.outputs.next_gap == 'adaptive_shell_gui_live_trial'", workflow)
        self.assertIn("AURUM_EVIDENCE_RECOVERY active=true", workflow)
        self.assertIn("aurum-external-evidence-recover", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
