from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIELD = ROOT / "field"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(FIELD))

from external_prerequisite_evidence import apply_adaptive_shell_live_trial_evidence
from local_capability_verification import verify_local_capability_for_gap
from native_gap_catalog import get_native_semantic_gap
from run_bounded_adaptive_shell_live_trial import run_trial


class BoundedAdaptiveShellLiveTrialTests(unittest.TestCase):
    def _physical(self) -> dict:
        return {
            "schema": "aurum-external-prerequisite-evidence-v0",
            "kind": "bbpi4-physical-presence",
            "source": "aurum-public-controller-fresh-node",
            "verified": True,
            "node_id": "bbpi4feed1234567",
            "name": "BBPI4",
            "carrier": "https-outbound",
            "last_seen": 990,
            "observed_at": 1000,
            "expires_at": 1300,
        }

    def _readiness(self) -> dict:
        return {
            "schema": "aurum-adaptive-shell-live-trial-readiness-evidence-v1",
            "kind": "adaptive-shell-live-trial-readiness",
            "source": "aurum-windows-usb-kvm-bounded-proof",
            "verified": True,
            "node_id": "bbpi4feed1234567",
            "route": "10.12.194.1",
            "ssh_host_key_fingerprint": "SHA256:0SyJhmydZNm5NQsr1lBCf6nqTDiSQRlVzKBtlrvYTGQ",
            "observed_at": 1000,
            "expires_at": 1300,
            "display": {
                "verified": True,
                "http_status": 200,
                "content_type": "multipart/x-mixed-replace; boundary=frame",
                "sample_bytes": 4096,
                "sample_sha256": "a" * 64,
            },
            "input": {
                "verified": True,
                "action": "release",
                "acknowledged": True,
                "before_neutral": True,
                "after_neutral": True,
            },
            "permission": {
                "present": True,
                "scope": "bounded-adaptive-shell-live-trial",
                "authorization_reference": "operator-test",
            },
            "rollback": {
                "verified": True,
                "method": "neutral-hid-release-and-ephemeral-state",
            },
            "proof_view": {
                "present": True,
                "display_sample_sha256": "a" * 64,
            },
        }

    def test_trial_applies_and_rolls_back_only_ephemeral_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            physical_path = root / "physical.json"
            readiness_path = root / "readiness.json"
            output_path = root / "trial.json"
            physical_path.write_text(json.dumps(self._physical()), encoding="utf-8")
            readiness_path.write_text(json.dumps(self._readiness()), encoding="utf-8")

            result = run_trial(
                physical_path=physical_path,
                readiness_path=readiness_path,
                output_path=output_path,
                now=1010,
            )

            self.assertTrue(output_path.is_file())
            self.assertTrue(result["verified"])
            self.assertFalse(result["application"]["persistent"])
            self.assertTrue(result["rollback"]["workspace_cleaned"])
            self.assertEqual(
                result["rollback"]["baseline_sha256"],
                result["rollback"]["restored_sha256"],
            )
            self.assertFalse(any(result["safety"].values()))

            spec = get_native_semantic_gap("adaptive_shell_live_trial")
            self.assertIsNotNone(spec)
            applied = apply_adaptive_shell_live_trial_evidence(spec, result, now=1011)
            self.assertTrue(applied.applied)
            verified = verify_local_capability_for_gap(
                applied.spec,
                "required-condition-classifier",
            )
            self.assertEqual(verified.invocation_output, "bounded-live-trial-passed")

    def test_trial_fails_closed_when_readiness_is_expired(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            physical_path = root / "physical.json"
            readiness_path = root / "readiness.json"
            output_path = root / "trial.json"
            physical_path.write_text(json.dumps(self._physical()), encoding="utf-8")
            readiness_path.write_text(json.dumps(self._readiness()), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "readiness evidence rejected"):
                run_trial(
                    physical_path=physical_path,
                    readiness_path=readiness_path,
                    output_path=output_path,
                    now=1400,
                )
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
