from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from Admin.checkpoint_aurum_runtime import checkpoint
from Admin.resume_aurum_runtime import ResumeError, resume_state


class AurumRuntimeResumeTests(unittest.TestCase):
    def root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def make_checkpoint(self, directory: Path) -> Path:
        output = directory / "runtime-checkpoint.json"
        checkpoint(
            root=self.root(),
            output=output,
            overlay={
                "jobs": [
                    {
                        "id": "controller-loop",
                        "state": "running",
                        "depends_on": [],
                        "checkpoint": "cycle-582",
                        "resume_hint": "re-observe controller endpoint before continuing",
                    },
                    {
                        "id": "safe-ci-retry",
                        "state": "retrying",
                        "depends_on": ["controller-loop"],
                        "checkpoint": "after-failed-attempt",
                        "resume_hint": "recheck current CI before retry",
                    },
                    {
                        "id": "physical-flash",
                        "state": "blocked",
                        "depends_on": [],
                        "checkpoint": "explicit-authority-boundary",
                        "resume_hint": "wait for fresh explicit authorization",
                    },
                ],
                "hardware_fingerprint": {"node": "test-node"},
                "software_fingerprint": {"controller": "test-controller"},
                "active_hypotheses": ["checkpoint-roundtrip"],
            },
        )
        return output

    def test_valid_checkpoint_restores_runtime_evidence_without_claiming_live_process(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.make_checkpoint(Path(temp))
            result = resume_state(root=self.root(), checkpoint_path=path)
            self.assertEqual(result["schema"], "aurum-runtime-resume-v1")
            self.assertEqual(result["runtime"]["checkpointed_running"][0]["id"], "controller-loop")
            self.assertEqual(result["runtime"]["checkpointed_retrying"][0]["id"], "safe-ci-retry")
            self.assertEqual(result["runtime"]["checkpointed_blocked"][0]["id"], "physical-flash")
            self.assertFalse(result["runtime"]["live_process_inferred"])
            self.assertFalse(result["authority"]["authority_granted"])
            self.assertFalse(result["authority"]["candidate_promotion_allowed"])
            self.assertFalse(result["authority"]["lkg_mutation_allowed"])
            self.assertFalse(result["authority"]["physical_proof_inferred"])
            self.assertTrue(result["authority"]["live_recheck_required"])

    def test_tampered_durable_digest_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.make_checkpoint(Path(temp))
            value = json.loads(path.read_text(encoding="utf-8"))
            value["durable_state_sha256"] = "0" * 64
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ResumeError, "durable-state digest mismatch"):
                resume_state(root=self.root(), checkpoint_path=path)

    def test_tampered_authority_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.make_checkpoint(Path(temp))
            value = json.loads(path.read_text(encoding="utf-8"))
            value["authority"]["authority_granted"] = True
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ResumeError, "forbidden authority"):
                resume_state(root=self.root(), checkpoint_path=path)

    def test_stale_checkpoint_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.make_checkpoint(Path(temp))
            value = json.loads(path.read_text(encoding="utf-8"))
            old = datetime.now(timezone.utc) - timedelta(hours=2)
            value["created_at_utc"] = old.isoformat()
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ResumeError, "runtime checkpoint stale"):
                resume_state(root=self.root(), checkpoint_path=path, max_age_seconds=60)

    def test_release_provenance_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.make_checkpoint(Path(temp))
            value = json.loads(path.read_text(encoding="utf-8"))
            value["release_source_commit"] = "f" * 40
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ResumeError, "release provenance mismatch"):
                resume_state(root=self.root(), checkpoint_path=path)

    def test_direct_cli_roundtrip_reads_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.make_checkpoint(Path(temp))
            result = subprocess.run(
                [
                    sys.executable,
                    "Admin/resume_aurum_runtime.py",
                    "--root",
                    str(self.root()),
                    "--checkpoint",
                    str(path),
                ],
                cwd=self.root(),
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["runtime"]["checkpointed_running"][0]["id"], "controller-loop")
            self.assertFalse(payload["authority"]["authority_granted"])

    def test_separate_writer_and_resume_processes_preserve_restart_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            checkpoint_path = temp_path / "runtime-checkpoint.json"
            overlay_path = temp_path / "runtime-overlay.json"
            overlay_path.write_text(
                json.dumps(
                    {
                        "jobs": [
                            {
                                "id": "process-boundary-job",
                                "state": "retrying",
                                "depends_on": [],
                                "checkpoint": "before-process-exit",
                                "resume_hint": "re-observe live state after restart",
                            }
                        ],
                        "software_fingerprint": {"proof": "two-separate-processes"},
                    }
                ),
                encoding="utf-8",
            )

            write_result = subprocess.run(
                [
                    sys.executable,
                    "Admin/checkpoint_aurum_runtime.py",
                    "--root",
                    str(self.root()),
                    "--output",
                    str(checkpoint_path),
                    "--runtime-overlay",
                    str(overlay_path),
                ],
                cwd=self.root(),
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(write_result.returncode, 0, msg=write_result.stderr or write_result.stdout)

            resume_result = subprocess.run(
                [
                    sys.executable,
                    "Admin/resume_aurum_runtime.py",
                    "--root",
                    str(self.root()),
                    "--checkpoint",
                    str(checkpoint_path),
                ],
                cwd=self.root(),
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(resume_result.returncode, 0, msg=resume_result.stderr or resume_result.stdout)
            payload = json.loads(resume_result.stdout)
            self.assertEqual(payload["runtime"]["checkpointed_retrying"][0]["id"], "process-boundary-job")
            self.assertEqual(
                payload["runtime"]["software_fingerprint"]["proof"],
                "two-separate-processes",
            )
            self.assertFalse(payload["runtime"]["live_process_inferred"])
            self.assertFalse(payload["authority"]["authority_granted"])


if __name__ == "__main__":
    unittest.main()
