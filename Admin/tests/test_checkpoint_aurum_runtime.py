from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from Admin.checkpoint_aurum_runtime import CheckpointError, build_checkpoint, checkpoint


class AurumRuntimeCheckpointTests(unittest.TestCase):
    def test_current_repository_checkpoint_is_zero_authority_and_resumable(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "runtime-checkpoint.json"
            value = checkpoint(
                root=root,
                output=output,
                overlay={
                    "jobs": [
                        {
                            "id": "safe-ci-followup",
                            "state": "retrying",
                            "depends_on": [],
                            "checkpoint": "after-repository-state-reconstruction",
                            "resume_hint": "recheck CI evidence",
                        }
                    ],
                    "hardware_fingerprint": {"node": "test-only"},
                },
            )
            persisted = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(persisted["schema"], "aurum-runtime-checkpoint-v1")
            self.assertEqual(persisted["runtime"]["resumable"][0]["id"], "safe-ci-followup")
            self.assertFalse(persisted["authority"]["authority_granted"])
            self.assertFalse(persisted["authority"]["candidate_promotion_allowed"])
            self.assertFalse(persisted["authority"]["lkg_mutation_allowed"])
            self.assertEqual(value["durable_state_sha256"], persisted["durable_state_sha256"])

    def test_direct_cli_execution_writes_ignored_local_checkpoint(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "runtime-checkpoint.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "Admin/checkpoint_aurum_runtime.py",
                    "--root",
                    str(root),
                    "--output",
                    str(output),
                ],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            persisted = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(persisted["schema"], "aurum-runtime-checkpoint-v1")
            self.assertFalse(persisted["authority"]["authority_granted"])

    def test_overlay_cannot_smuggle_destructive_authority(self):
        root = Path(__file__).resolve().parents[2]
        value = build_checkpoint(
            root=root,
            overlay={
                "authority": {
                    "authority_granted": True,
                    "lkg_mutation_allowed": True,
                },
                "jobs": [],
            },
        )
        self.assertFalse(value["authority"]["authority_granted"])
        self.assertFalse(value["authority"]["lkg_mutation_allowed"])
        self.assertTrue(value["authority"]["live_recheck_required"])

    def test_invalid_job_state_fails_closed(self):
        root = Path(__file__).resolve().parents[2]
        with self.assertRaisesRegex(CheckpointError, "invalid runtime job state"):
            build_checkpoint(
                root=root,
                overlay={"jobs": [{"id": "bad", "state": "silently-promoted"}]},
            )

    def test_duplicate_job_ids_fail_closed(self):
        root = Path(__file__).resolve().parents[2]
        with self.assertRaisesRegex(CheckpointError, "duplicate runtime job id"):
            build_checkpoint(
                root=root,
                overlay={
                    "jobs": [
                        {"id": "same", "state": "running"},
                        {"id": "same", "state": "retrying"},
                    ]
                },
            )


if __name__ == "__main__":
    unittest.main()
