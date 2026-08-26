from __future__ import annotations

import hashlib
import json
import shutil
import unittest
from pathlib import Path

from Projects.AdaptiveKernel.pi3_smsc95xx_usbnet_lifecycle_candidate import (
    _REQUIRED_FALSE,
    _verify_sealed,
    run_lifecycle_differential,
    synthesize_lifecycle_candidate,
)
from Projects.AdaptiveKernel.pi3_smsc95xx_usbnet_lifecycle_model import build_lifecycle_model
from Projects.AdaptiveKernel.tests.test_pi3_smsc95xx_usbnet_lifecycle_model import (
    fixture_manifest,
    fixture_packet_differential,
    fixture_qpu,
    fixture_sources,
)


def _seal(value: dict) -> dict:
    body = dict(value)
    body.pop("receipt_sha256", None)
    value["receipt_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    ).hexdigest()
    return value


def fixture_lifecycle() -> dict:
    sources = fixture_sources()
    return build_lifecycle_model(
        packet_differential=fixture_packet_differential(),
        qpu_router=fixture_qpu(),
        reference_manifest=fixture_manifest(sources),
        sources=sources,
    )


class UsbnetLifecycleCandidateTests(unittest.TestCase):
    def require_c_compiler(self):
        if not (shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")):
            self.skipTest("C compiler required")

    def test_candidate_is_table_driven_and_zero_authority(self):
        source, receipt = synthesize_lifecycle_candidate(fixture_lifecycle())
        self.assertIn("aurum_usbnet_transition", source)
        self.assertIn("AURUM_NEXT_STATE", source)
        self.assertNotIn("module_init", source)
        self.assertNotIn("usb_submit_urb", source)
        self.assertEqual(receipt["state_count"], 13)
        self.assertEqual(receipt["action_count"], 13)
        self.assertTrue(_verify_sealed(receipt))
        for key in _REQUIRED_FALSE:
            self.assertFalse(receipt["authority"][key])

    def test_compiled_candidate_matches_complete_graph_and_sequences(self):
        self.require_c_compiler()
        _, candidate, result = run_lifecycle_differential(fixture_lifecycle(), sequence_steps=128)
        self.assertTrue(_verify_sealed(candidate))
        self.assertTrue(_verify_sealed(result))
        self.assertEqual(result["complete_transition_scenarios"], 169)
        self.assertEqual(result["deterministic_sequence_steps"], 128)
        self.assertEqual(result["scenario_count"], 297)
        self.assertEqual(result["mismatch_count"], 0)
        self.assertFalse(result["qpu"]["used"])
        self.assertFalse(result["invariants"]["live_pi_contacted"])

    def test_tampered_transition_matrix_fails_closed(self):
        lifecycle = fixture_lifecycle()
        lifecycle["graph"]["transitions"][0]["accepted"] = not lifecycle["graph"]["transitions"][0]["accepted"]
        with self.assertRaisesRegex(ValueError, "sealed receipt"):
            synthesize_lifecycle_candidate(lifecycle)

    def test_resealed_nonzero_authority_fails_closed(self):
        lifecycle = fixture_lifecycle()
        lifecycle["authority"]["driver_binding_change_allowed"] = True
        _seal(lifecycle)
        with self.assertRaisesRegex(ValueError, "driver_binding_change_allowed=false"):
            synthesize_lifecycle_candidate(lifecycle)


class UsbnetLifecycleCandidateWorkflowTests(unittest.TestCase):
    def workflow(self) -> str:
        return (
            Path(__file__).parents[3]
            / ".github"
            / "workflows"
            / "aurum-pi3-smsc95xx-usbnet-lifecycle-candidate.yml"
        ).read_text(encoding="utf-8").lower()

    def test_workflow_is_host_only_and_main_gated(self):
        workflow = self.workflow()
        self.assertIn("runs-on: ubuntu-24.04", workflow)
        self.assertIn("if: github.ref == 'refs/heads/main'", workflow)
        self.assertNotIn("169.254.129.122", workflow)
        self.assertNotIn("ssh ", workflow)
        self.assertNotIn("self-hosted", workflow)

    def test_workflow_has_no_driver_or_usb_execution_path(self):
        workflow = self.workflow()
        for token in ("modprobe", "insmod", "modules_install", ".ko", "unbind", "usb_submit_urb", "libusb"):
            self.assertNotIn(token, workflow)


if __name__ == "__main__":
    unittest.main()
