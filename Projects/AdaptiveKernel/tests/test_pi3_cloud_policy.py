from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from Projects.AdaptiveKernel.pi3_cloud_policy import (
    CloudPolicyEvidenceError,
    evaluate_cloud_policy,
    verify_cloud_policy_receipt,
)


ARTIFACT_ID = 9_605_841_913
RUN_ID = 32_964_554_773
ARTIFACT_DIGEST = "sha256:" + "a" * 64


def canonical_sha256(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def sample(index: int) -> dict:
    return {
        "elapsed_seconds": float(index * 30),
        "loadavg": "0.10 0.08 0.04 1/130 1000",
        "memory_kib": {"MemAvailable": 760_000, "MemTotal": 926_828},
        "network": {
            "carrier": "1",
            "operstate": "up",
            "rx_dropped": 0,
            "rx_errors": 0,
            "tx_dropped": 0,
            "tx_errors": 0,
        },
        "reference_driver": "smsc95xx",
        "temperature_c": 49.0 + (index % 3),
        "throttled": {"current_fault": False},
        "timestamp": f"2026-06-18T00:{index:02d}:00+00:00",
    }


class Pi3CloudPolicyTests(unittest.TestCase):
    def create_fixture(self, root: Path) -> tuple[Path, Path]:
        evidence = root / "evidence"
        remote = evidence / "remote"
        remote.mkdir(parents=True)
        control = {
            "run_id": str(RUN_ID),
            "remote_boot_id": "3488238f-e35d-4249-9d53-6133eeed4b8a",
            "lan_scan_performed": False,
            "target": {
                "model": "Raspberry Pi 3 Model B Rev 1.2",
                "serial": "00000000a6a7df7f",
            },
        }
        identity = {
            "boot_id": "3488238f-e35d-4249-9d53-6133eeed4b8a",
            "kernel_release": "6.18.34+rpt-rpi-v8",
            "model": "Raspberry Pi 3 Model B Rev 1.2",
            "reference_driver": "smsc95xx",
            "root_source": "/dev/mmcblk0p2",
            "serial": "00000000a6a7df7f",
        }
        summary = {
            "boot_configuration_changed": False,
            "firmware_changed": False,
            "identity_before": identity,
            "identity_after": identity,
            "invariant_checks": {
                "boot_id_unchanged": True,
                "ethernet_carrier_present": True,
                "identity_match": True,
                "kernel_unchanged": True,
                "model_unchanged": True,
                "reference_driver_file_hash_unchanged": True,
                "reference_driver_unchanged": True,
                "root_source_unchanged": True,
                "serial_unchanged": True,
            },
            "persistent_kernel_or_driver_change": False,
            "replacement_kernel_installed": False,
            "stages": {
                "adaptive-runtime-pressure-canary": {
                    "state": "held",
                    "reason": "pressure-thermal-stop-before-live-policy",
                    "pressure_evidence": [
                        {"temperature_c": 69.832},
                        {"temperature_c": 77.902},
                    ],
                }
            },
        }
        control_path = evidence / "control-receipt.json"
        summary_path = remote / "summary.json"
        events_path = remote / "events.jsonl"
        samples_path = remote / "samples.jsonl"
        control_path.write_text(json.dumps(control), encoding="utf-8")
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        events_path.write_text('{"event":"fixture"}\n', encoding="utf-8")
        samples_path.write_text(
            "".join(json.dumps(sample(index), sort_keys=True) + "\n" for index in range(12)),
            encoding="utf-8",
        )

        artifact = {
            "control_receipt_sha256": hashlib.sha256(control_path.read_bytes()).hexdigest(),
            "digest": ARTIFACT_DIGEST,
            "events_sha256": hashlib.sha256(events_path.read_bytes()).hexdigest(),
            "id": ARTIFACT_ID,
            "samples_sha256": hashlib.sha256(samples_path.read_bytes()).hexdigest(),
            "summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        }
        source_identity = dict(identity)
        source_identity["kernel"] = source_identity.pop("kernel_release")
        source = {
            "schema": "aurum-pi3-adaptive-runtime-pressure-result-v1",
            "artifact": artifact,
            "identity": source_identity,
            "rollback": {
                "archive_integrity_test": "passed",
                "archive_sha256": "c45bb76d88867b1c3552791f9b992068bccd2c9f2f9b83c2fcab3d0cc79ee984",
                "raw_image_sha256": "61a4c6bfc03e7ea3444ce67de20c506dbc57a7fc7e34da250b3bfab8d2845c62",
                "verified_fresh_before_physical_contact": True,
            },
            "run": {"id": RUN_ID},
        }
        source["receipt_sha256"] = canonical_sha256(source)
        source_path = root / "source-result.json"
        source_path.write_text(json.dumps(source), encoding="utf-8")
        return evidence, source_path

    def evaluate(self, evidence: Path, source: Path) -> dict:
        return evaluate_cloud_policy(
            evidence,
            source,
            source_run_id=RUN_ID,
            artifact_id=ARTIFACT_ID,
            artifact_digest=ARTIFACT_DIGEST,
            scenario_count=100,
        )

    def test_valid_thermal_source_emits_sealed_zero_authority_proposal(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence, source = self.create_fixture(Path(directory))
            receipt = self.evaluate(evidence, source)
        self.assertTrue(verify_cloud_policy_receipt(receipt))
        self.assertEqual(receipt["semantic_state"], "held-zero-authority-thermal-source")
        self.assertEqual(receipt["proposal"]["recommendation"], "no-change")
        self.assertEqual(receipt["proposal"]["selected_policy_id"], "runtime-baseline-v1")
        self.assertFalse(receipt["invariants"]["live_pi_contacted"])
        self.assertFalse(receipt["invariants"]["mutation_authority_granted"])
        self.assertFalse(receipt["qpu_routing"]["used"])
        self.assertEqual(
            receipt["qpu_routing"]["reason"],
            "candidate-space-too-small-for-measurable-qpu-value",
        )

    def test_file_hash_mismatch_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence, source = self.create_fixture(Path(directory))
            (evidence / "remote" / "events.jsonl").write_text(
                '{"event":"tampered"}\n', encoding="utf-8"
            )
            with self.assertRaises(CloudPolicyEvidenceError):
                self.evaluate(evidence, source)

    def test_source_receipt_tamper_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence, source_path = self.create_fixture(Path(directory))
            source = json.loads(source_path.read_text(encoding="utf-8"))
            source["run"]["id"] += 1
            source_path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaises(CloudPolicyEvidenceError):
                self.evaluate(evidence, source_path)

    def test_replay_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence, source = self.create_fixture(Path(directory))
            first = self.evaluate(evidence, source)
            second = self.evaluate(evidence, source)
        self.assertEqual(first, second)


class Pi3CloudPolicyWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (
            Path(__file__).resolve().parents[3]
            / ".github"
            / "workflows"
            / "aurum-pi3-cloud-policy.yml"
        ).read_text(encoding="utf-8")

    def test_workflow_is_manual_hosted_and_read_only(self):
        self.assertIn("workflow_dispatch:", self.workflow)
        self.assertIn("runs-on: ubuntu-24.04", self.workflow)
        self.assertIn("contents: read", self.workflow)
        self.assertIn("actions: read", self.workflow)
        self.assertNotIn("self-hosted", self.workflow)

    def test_workflow_verifies_and_downloads_exact_artifact(self):
        self.assertIn("actions/artifacts/$ARTIFACT_ID", self.workflow)
        self.assertIn("gh run download", self.workflow)
        self.assertIn('artifact.get("digest")', self.workflow)
        self.assertIn('workflow_run.get("id")', self.workflow)

    def test_workflow_has_no_pi_or_hardware_control_path(self):
        lowered = self.workflow.lower()
        self.assertNotIn("169.254.129.122", lowered)
        self.assertNotIn(" ssh ", lowered)
        self.assertNotIn("password", lowered)
        self.assertNotIn("qpu token", lowered)
        self.assertIn("hardware_submission_performed", lowered)


if __name__ == "__main__":
    unittest.main()
