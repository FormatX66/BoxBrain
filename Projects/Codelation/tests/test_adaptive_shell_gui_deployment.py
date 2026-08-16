from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


CODELATION = Path(__file__).resolve().parents[1]
ROOT = CODELATION.parents[1]
FIELD = CODELATION / "field"
sys.path.insert(0, str(FIELD))

from external_prerequisite_evidence import (
    apply_adaptive_shell_gui_live_trial_evidence,
    apply_adaptive_shell_gui_preference_live_trial_evidence,
    apply_adaptive_shell_iteration_observation_evidence,
)
from local_capability_verification import verify_local_capability_for_gap
from native_gap_catalog import get_native_semantic_gap


EVIDENCE = CODELATION / "autobuild" / "external_evidence"


class AdaptiveShellGuiDeploymentTests(unittest.TestCase):
    def test_gui_capability_observation_advances_without_authority(self) -> None:
        spec = get_native_semantic_gap("adaptive_shell_iteration_observation")
        self.assertIsNotNone(spec)
        evidence = json.loads(
            (EVIDENCE / "adaptive_shell_iteration_observation.json").read_text(encoding="utf-8")
        )

        applied = apply_adaptive_shell_iteration_observation_evidence(
            spec,
            evidence,
            now=int(evidence["observed_at"]) + 1,
        )

        self.assertTrue(applied.applied)
        self.assertEqual(applied.reason, "fresh-bbpi4-gui-capability-observation")
        self.assertFalse(applied.evidence["authority_granted"])
        self.assertFalse(applied.evidence["user_content_captured"])
        verified = verify_local_capability_for_gap(
            applied.spec,
            "required-condition-classifier",
        )
        self.assertTrue(verified.verified)
        self.assertEqual(verified.invocation_output, "bounded-iteration-observation-complete")
        self.assertFalse(verified.authority_granted)
        self.assertFalse(verified.routed_to_host)

        unsafe = copy.deepcopy(evidence)
        unsafe["observation"]["user_content_captured"] = True
        rejected = apply_adaptive_shell_iteration_observation_evidence(
            spec,
            unsafe,
            now=int(evidence["observed_at"]) + 1,
        )
        self.assertFalse(rejected.applied)
        self.assertEqual(rejected.reason, "gui-observation-content-boundary-invalid")

    def test_gui_live_trial_preserves_human_constants_and_dialogue_boundary(self) -> None:
        spec = get_native_semantic_gap("adaptive_shell_gui_live_trial")
        self.assertIsNotNone(spec)
        evidence = json.loads(
            (EVIDENCE / "adaptive_shell_gui_live_trial.json").read_text(encoding="utf-8")
        )

        applied = apply_adaptive_shell_gui_live_trial_evidence(
            spec,
            evidence,
            now=int(evidence["observed_at"]) + 1,
        )

        self.assertTrue(applied.applied)
        self.assertEqual(applied.reason, "bounded-bbpi4-aurum-gui-live-trial")
        self.assertTrue(applied.evidence["safe_layout_available"])
        self.assertTrue(applied.evidence["dialogue_only"])
        self.assertFalse(applied.evidence["api_key_persisted"])
        self.assertFalse(applied.evidence["authority_granted"])
        verified = verify_local_capability_for_gap(
            applied.spec,
            "required-condition-classifier",
        )
        self.assertTrue(verified.verified)
        self.assertEqual(verified.invocation_output, "aurum-gui-live-trial-passed")
        self.assertFalse(verified.authority_granted)
        self.assertFalse(verified.routed_to_host)

        unsafe = copy.deepcopy(evidence)
        unsafe["safety"]["persistent_service_enabled"] = True
        rejected = apply_adaptive_shell_gui_live_trial_evidence(
            spec,
            unsafe,
            now=int(evidence["observed_at"]) + 1,
        )
        self.assertFalse(rejected.applied)
        self.assertEqual(rejected.reason, "gui-live-trial-safety-invalid")

    def test_preference_trial_is_revision_guarded_and_restores_baseline(self) -> None:
        spec = get_native_semantic_gap("adaptive_shell_gui_preference_live_trial")
        self.assertIsNotNone(spec)
        evidence = json.loads(
            (EVIDENCE / "adaptive_shell_gui_preference_live_trial.json").read_text(
                encoding="utf-8"
            )
        )

        applied = apply_adaptive_shell_gui_preference_live_trial_evidence(
            spec,
            evidence,
            now=int(evidence["observed_at"]) + 1,
        )

        self.assertTrue(applied.applied)
        self.assertEqual(applied.reason, "bounded-bbpi4-gui-preference-live-trial")
        self.assertTrue(applied.evidence["revision_guard_verified"])
        self.assertTrue(applied.evidence["apply_verified"])
        self.assertTrue(applied.evidence["rollback_verified"])
        self.assertEqual(
            applied.evidence["baseline_state_sha256"],
            applied.evidence["restored_state_sha256"],
        )
        self.assertFalse(applied.evidence["user_content_captured"])
        self.assertFalse(applied.evidence["authority_granted"])
        verified = verify_local_capability_for_gap(
            applied.spec,
            "required-condition-classifier",
        )
        self.assertTrue(verified.verified)
        self.assertEqual(
            verified.invocation_output,
            "aurum-gui-preference-live-trial-passed",
        )
        self.assertFalse(verified.authority_granted)
        self.assertFalse(verified.routed_to_host)

        unsafe = copy.deepcopy(evidence)
        unsafe["trial"]["rollback"]["state_sha256"] = "f" * 64
        rejected = apply_adaptive_shell_gui_preference_live_trial_evidence(
            spec,
            unsafe,
            now=int(evidence["observed_at"]) + 1,
        )
        self.assertFalse(rejected.applied)
        self.assertEqual(rejected.reason, "gui-preference-trial-proof-invalid")

    def test_deployment_and_launch_are_strict_transient_and_package_free(self) -> None:
        setup = (ROOT / "installer" / "setup-aurum-gui.ps1").read_text(encoding="utf-8")
        launch = (ROOT / "installer" / "open-aurum-gui.ps1").read_text(encoding="utf-8")
        start = (ROOT / "installer" / "start-aurum-gui-on-pi.sh").read_text(encoding="utf-8")
        install = (ROOT / "installer" / "install-aurum-gui-on-pi.sh").read_text(encoding="utf-8")

        for text in (setup, launch):
            self.assertIn("StrictHostKeyChecking=yes", text)
            self.assertIn("IdentitiesOnly=yes", text)
            self.assertIn("10.12.194.1", text)
            self.assertIn("boxbrain_pi_ed25519", text)
        self.assertIn("127.0.0.1:8765", launch)
        self.assertIn("-WindowStyle Hidden", launch)
        self.assertIn("systemd-run", start)
        self.assertIn("--collect", start)
        self.assertIn("--property=Restart=no", start)
        self.assertNotIn("systemctl enable", start)
        self.assertNotIn("apt install", start + install)
        self.assertNotIn("apt-get", start + install)

    def test_collectors_capture_proof_without_dialogue_or_credentials(self) -> None:
        capability = (ROOT / "installer" / "collect-adaptive-shell-gui-capability.ps1").read_text(
            encoding="utf-8"
        )
        trial = (ROOT / "installer" / "collect-adaptive-shell-gui-live-trial.ps1").read_text(
            encoding="utf-8"
        )
        preference_trial = (
            ROOT / "installer" / "collect-adaptive-shell-gui-preference-live-trial.ps1"
        ).read_text(encoding="utf-8")

        for text in (capability, trial, preference_trial):
            self.assertIn("StrictHostKeyChecking=yes", text)
            self.assertIn("UserKnownHostsFile=", text)
            self.assertIn("AuthorizationReference", text)
            self.assertIn("user_content_captured = $false", text)
            self.assertNotIn("OPENAI_API_KEY", text)
            self.assertNotIn("aurum_dialogue.py --root /opt/boxbrain/codelation session", text)
        self.assertIn("listener_loopback_only = $true", trial)
        self.assertIn("persistent_service_enabled = $false", trial)
        self.assertIn("stale_revision_rejected = $true", preference_trial)
        self.assertIn("rollback_verified=true", preference_trial)


if __name__ == "__main__":
    unittest.main()
