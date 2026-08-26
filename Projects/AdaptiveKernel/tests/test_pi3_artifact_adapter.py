from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from Projects.AdaptiveKernel.adaptive_runtime import verify_receipt
from Projects.AdaptiveKernel.pi3_artifact_adapter import (
    ArtifactEvidenceError,
    convert_overnight_sample,
    evaluate_overnight_artifact,
    verify_artifact_receipt,
)


ARTIFACT_DIGEST = "sha256:" + "a" * 64


def overnight_sample(index: int, *, rx_dropped: int = 0) -> dict:
    return {
        "elapsed_seconds": float(index * 60),
        "loadavg": "0.10 0.08 0.04 1/130 1000",
        "memory_kib": {"MemAvailable": 760_000, "MemTotal": 926_828},
        "network": {
            "carrier": "1",
            "operstate": "up",
            "rx_dropped": rx_dropped,
            "rx_errors": 0,
            "tx_dropped": 0,
            "tx_errors": 0,
        },
        "reference_driver": "smsc95xx",
        "temperature_c": 49.0,
        "throttled": {"current_fault": False},
        "timestamp": f"2026-06-18T00:{index:02d}:00+00:00",
    }


class Pi3ArtifactAdapterTests(unittest.TestCase):
    def write_samples(self, root: Path, samples: list[dict]) -> Path:
        path = root / "samples.jsonl"
        path.write_text(
            "".join(json.dumps(sample, sort_keys=True) + "\n" for sample in samples),
            encoding="utf-8",
        )
        return path

    def test_conversion_maps_overnight_network_and_power_fields(self):
        converted = convert_overnight_sample(overnight_sample(1), index=0)
        self.assertEqual(converted["sample_id"], "overnight-0000")
        self.assertEqual(converted["memory_available_bytes"], 760_000 * 1024)
        self.assertEqual(converted["load_1m"], 0.10)
        self.assertFalse(converted["current_throttled"])
        self.assertEqual(converted["ethernet"]["reference_driver"], "smsc95xx")
        self.assertEqual(converted["ethernet"]["rx_dropped"], 0)

    def test_actual_shape_drop_evidence_quarantines_shadow_window(self):
        samples = [overnight_sample(index) for index in range(5)]
        samples[-1] = overnight_sample(4, rx_dropped=1)
        with tempfile.TemporaryDirectory() as directory:
            receipt = evaluate_overnight_artifact(
                self.write_samples(Path(directory), samples),
                artifact_id=9599926710,
                artifact_digest=ARTIFACT_DIGEST,
                window_size=3,
            )
        self.assertEqual(receipt["decision"]["state"], "quarantined")
        self.assertEqual(receipt["decision"]["recommendation"], "no-change")
        self.assertFalse(receipt["decision"]["change_applied"])

    def test_clean_preserved_window_produces_sealed_shadow_only_receipt(self):
        samples = [overnight_sample(index) for index in range(20)]
        with tempfile.TemporaryDirectory() as directory:
            receipt = evaluate_overnight_artifact(
                self.write_samples(Path(directory), samples),
                artifact_id=9599926710,
                artifact_digest=ARTIFACT_DIGEST,
                window_size=16,
            )
        self.assertTrue(verify_artifact_receipt(receipt))
        self.assertEqual(receipt["decision"]["state"], "completed")
        self.assertEqual(receipt["decision"]["recommendation"], "shadow-change")
        self.assertEqual(
            receipt["decision"]["selected_policy_id"],
            "runtime-gen3-opportunistic-v1",
        )
        self.assertFalse(receipt["invariants"]["live_pi_contacted"])
        self.assertFalse(receipt["invariants"]["mutation_authority_granted"])

    def test_malformed_loadavg_refuses_conversion(self):
        malformed = overnight_sample(1)
        malformed["loadavg"] = "not-a-number"
        with self.assertRaises(ArtifactEvidenceError):
            convert_overnight_sample(malformed, index=0)

    def test_artifact_digest_and_window_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_samples(
                Path(directory), [overnight_sample(index) for index in range(3)]
            )
            with self.assertRaises(ArtifactEvidenceError):
                evaluate_overnight_artifact(
                    path,
                    artifact_id=9599926710,
                    artifact_digest="sha256:not-a-digest",
                    window_size=3,
                )
            with self.assertRaises(ArtifactEvidenceError):
                evaluate_overnight_artifact(
                    path,
                    artifact_id=9599926710,
                    artifact_digest=ARTIFACT_DIGEST,
                    window_size=2,
                )

    def test_preserved_overnight_receipt_is_sealed_shadow_evidence(self):
        result = (
            Path(__file__).resolve().parents[1]
            / "results"
            / "pi3-adaptive-runtime-shadow-32926370691.json"
        )
        receipt = json.loads(result.read_text(encoding="utf-8"))
        self.assertTrue(verify_artifact_receipt(receipt))
        self.assertTrue(verify_receipt(receipt["shadow_receipt"]))
        self.assertEqual(receipt["source"]["github_artifact_id"], 9599926710)
        self.assertEqual(receipt["source"]["total_sample_count"], 328)
        self.assertEqual(receipt["source"]["window_sample_count"], 32)
        self.assertEqual(
            receipt["decision"]["selected_policy_id"],
            "runtime-gen3-opportunistic-v1",
        )
        self.assertEqual(receipt["decision"]["recommendation"], "shadow-change")
        self.assertFalse(receipt["decision"]["change_applied"])
        self.assertFalse(receipt["invariants"]["live_pi_contacted"])
        self.assertFalse(receipt["invariants"]["mutation_authority_granted"])


if __name__ == "__main__":
    unittest.main()
