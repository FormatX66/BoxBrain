from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest
from urllib.parse import urlparse

from Projects.AdaptiveKernel.pi3_reference_correlation import (
    EXPECTED_DRIVER,
    EXPECTED_KERNEL,
    EXPECTED_MODEL,
    EXPECTED_SERIAL,
    QPU_SCHEMA,
    _source_delta,
    verify_reference_correlation_receipt,
)


ROOT = Path(__file__).resolve().parents[3]
REFERENCE_ROOT = ROOT / "Projects" / "AdaptiveKernel" / "references" / "pi3_hardware"
MANIFEST_PATH = REFERENCE_ROOT / "reference-manifest.json"
QPU_PATH = REFERENCE_ROOT / "qpu-routing-model-32924126448.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "aurum-pi3-reference-correlation.yml"


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


class Pi3ReferenceCorrelationTests(unittest.TestCase):
    def test_manifest_pins_exact_target_and_immutable_sources(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], "aurum-pi3-hardware-reference-manifest-v1")
        self.assertEqual(
            manifest["target"],
            {
                "kernel": EXPECTED_KERNEL,
                "model": EXPECTED_MODEL,
                "reference_driver": EXPECTED_DRIVER,
                "serial": EXPECTED_SERIAL,
            },
        )
        sources = manifest["sources"]
        self.assertEqual(len(sources), 10)
        self.assertEqual(len({item["id"] for item in sources}), len(sources))
        self.assertEqual(len({item["filename"] for item in sources}), len(sources))
        for source in sources:
            self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(source["required_tokens"])
            parsed = urlparse(source["url"])
            self.assertEqual(parsed.scheme, "https")
            self.assertIn(
                parsed.hostname,
                {
                    "datasheets.raspberrypi.com",
                    "raw.githubusercontent.com",
                    "ww1.microchip.com",
                },
            )
        raw_urls = [item["url"] for item in sources if "raw.githubusercontent.com" in item["url"]]
        self.assertTrue(raw_urls)
        self.assertTrue(
            all(
                "16f1da3c4e94437449d6aa151589ca0ad4b388bb" in url
                or "7d0a66e4bb9081d75c82ec4957c50034cb0ea449" in url
                for url in raw_urls
            )
        )

    def test_qpu_model_is_sealed_router_not_hardware_twin(self) -> None:
        qpu = json.loads(QPU_PATH.read_text(encoding="utf-8"))
        self.assertEqual(qpu["schema"], QPU_SCHEMA)
        claimed = qpu.pop("receipt_sha256")
        self.assertEqual(claimed, canonical_sha256(qpu))
        self.assertEqual(qpu["provenance"]["run_id"], 32924126448)
        self.assertEqual(qpu["model"]["population_size"], 8)
        self.assertFalse(qpu["model"]["hardware_digital_twin"])
        self.assertFalse(qpu["model"]["hardware_submission_performed"])
        self.assertIsNone(qpu["model"]["submission"])

    def test_source_delta_reports_equal_and_changed_sources(self) -> None:
        texts = {
            "upstream": "same\nbase\n",
            "rpi-equal": "same\nbase\n",
            "rpi-changed": "same\npi extension\nbase\n",
        }
        verified = {
            name: {"sha256": hashlib.sha256(text.encode()).hexdigest()}
            for name, text in texts.items()
        }
        equal = _source_delta("upstream", "rpi-equal", texts, verified)
        changed = _source_delta("upstream", "rpi-changed", texts, verified)
        self.assertTrue(equal["exact_match"])
        self.assertEqual(equal["changed_blocks"], 0)
        self.assertFalse(changed["exact_match"])
        self.assertEqual(changed["right_only_or_replaced_lines"], 1)

    def test_receipt_seal_rejects_tampering(self) -> None:
        receipt = {"schema": "aurum-pi3-reference-correlation-v1", "state": "completed"}
        receipt["receipt_sha256"] = canonical_sha256(receipt)
        self.assertTrue(verify_reference_correlation_receipt(receipt))
        receipt["state"] = "tampered"
        self.assertFalse(verify_reference_correlation_receipt(receipt))

    def test_workflow_is_github_hosted_zero_authority(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("runs-on: ubuntu-24.04", workflow)
        self.assertIn("live_pi_contacted", workflow)
        self.assertIn("hardware_submission_performed", workflow)
        self.assertNotIn("self-hosted", workflow)
        self.assertNotIn("169.254.129.122", workflow)
        self.assertNotIn("ssh ", workflow.lower())
        self.assertNotIn("password", workflow.lower())


if __name__ == "__main__":
    unittest.main()
