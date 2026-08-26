from __future__ import annotations

import hashlib
import json
import shutil
import unittest
from pathlib import Path

from Projects.AdaptiveKernel.pi3_smsc95xx_packet_transfer_candidate import (
    _REQUIRED_FALSE,
    _verify_sealed,
    run_packet_differential,
    synthesize_packet_candidate,
)
from Projects.AdaptiveKernel.pi3_smsc95xx_packet_transfer_model import SCHEMA as PACKET_MODEL_SCHEMA


def _seal(value: dict) -> dict:
    body = dict(value)
    body.pop("receipt_sha256", None)
    value["receipt_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    ).hexdigest()
    return value


SOURCE = """
#define SMSC95XX_TX_OVERHEAD (8)
#define SMSC95XX_TX_OVERHEAD_CSUM (12)
skb_pull(skb, 4 + NET_IP_ALIGN);
size = (u16)((header & RX_STS_FL_) >> 16);
align_count = (4 - ((size + NET_IP_ALIGN) % 4)) % 4;
if (skb->len <= 45)
    return false;
return skb->csum_offset < (len - (4 + 1));
tx_cmd_a = tx_cmd_b | TX_CMD_A_FIRST_SEG_ | TX_CMD_A_LAST_SEG_;
tx_cmd_a += 4;
tx_cmd_b += 4;
tx_cmd_b |= TX_CMD_B_CSUM_ENABLE;
""".lstrip()


def fixture_packet_model() -> dict:
    return _seal(
        {
            "schema": PACKET_MODEL_SCHEMA,
            "state": "verified-offline-packet-transfer-shadow",
            "input_register_model_receipt_sha256": "a" * 64,
            "tx_packet_framing": {
                "command_word_bytes": 8,
                "checksum_preamble_bytes": 4,
                "first_segment_mask": 0x00002000,
                "last_segment_mask": 0x00001000,
                "buffer_size_mask": 0x000007FF,
                "frame_length_mask": 0x000007FF,
                "checksum_enable_mask": 0x00004000,
                "hardware_checksum_min_frame_length_exclusive": 45,
                "checksum_trailing_guard_bytes": 5,
            },
            "rx_packet_framing": {
                "status_word_bytes": 4,
                "data_offset_bytes": 2,
                "frame_length_mask": 0x3FFF0000,
                "frame_length_shift": 16,
                "error_summary_mask": 0x00008000,
                "next_frame_alignment_bytes": 4,
            },
            "authority": {key: False for key in _REQUIRED_FALSE},
            "invariants": {
                "live_pi_contacted": False,
                "usb_device_opened": False,
                "usb_transfer_submitted": False,
                "register_write_performed": False,
                "last_known_good_preserved": True,
            },
        }
    )


def fixture_manifest(source: str = SOURCE) -> dict:
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return {
        "schema": "aurum-pi3-hardware-reference-manifest-v1",
        "sources": [
            {"id": "raspberry-pi-linux-smsc95xx-c", "sha256": digest},
            {"id": "upstream-linux-v6.18-smsc95xx-c", "sha256": digest},
        ],
    }


class PacketTransferCandidateTests(unittest.TestCase):
    def require_c_compiler(self):
        if not (shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")):
            self.skipTest("C compiler required")

    def test_candidate_is_source_referenced_and_zero_authority(self):
        source, receipt = synthesize_packet_candidate(
            fixture_packet_model(), fixture_manifest(), SOURCE, SOURCE
        )
        self.assertIn("aurum_smsc95xx_model_tx", source)
        self.assertIn("aurum_smsc95xx_decode_rx", source)
        self.assertNotIn("module_init", source)
        self.assertNotIn("usb_submit_urb", source)
        self.assertEqual(receipt["reference_sources"]["rpi_upstream_semantic_token_mismatches"], 0)
        self.assertTrue(_verify_sealed(receipt))
        for key in _REQUIRED_FALSE:
            self.assertFalse(receipt["authority"][key])

    def test_compiled_differential_covers_exhaustive_and_fuzz_matrix(self):
        self.require_c_compiler()
        _, candidate, result = run_packet_differential(
            fixture_packet_model(), fixture_manifest(), SOURCE, SOURCE, fuzz_scenarios=64
        )
        self.assertTrue(_verify_sealed(candidate))
        self.assertTrue(_verify_sealed(result))
        self.assertEqual(result["mismatch_count"], 0)
        self.assertEqual(result["scenario_counts"]["tx_exhaustive"], 4094)
        self.assertEqual(result["scenario_counts"]["tx_boundaries"], 8)
        self.assertEqual(result["scenario_counts"]["rx_exhaustive"], 32768)
        self.assertEqual(result["scenario_counts"]["deterministic_fuzz"], 64)
        self.assertEqual(result["scenario_count"], 36934)
        self.assertFalse(result["qpu"]["used"])
        self.assertFalse(result["invariants"]["live_pi_contacted"])

    def test_tampered_source_hash_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "hash does not match"):
            synthesize_packet_candidate(
                fixture_packet_model(), fixture_manifest(), SOURCE + "tamper", SOURCE
            )

    def test_missing_source_semantics_fail_closed_even_when_hash_is_pinned(self):
        reduced = SOURCE.replace("if (skb->len <= 45)\n    return false;\n", "")
        with self.assertRaisesRegex(ValueError, "missing packet semantics"):
            synthesize_packet_candidate(
                fixture_packet_model(), fixture_manifest(reduced), reduced, reduced
            )

    def test_resealed_nonzero_authority_fails_closed(self):
        model = fixture_packet_model()
        model["authority"]["usb_transfer_allowed"] = True
        _seal(model)
        with self.assertRaisesRegex(ValueError, "usb_transfer_allowed=false"):
            synthesize_packet_candidate(model, fixture_manifest(), SOURCE, SOURCE)


class PacketTransferCandidateWorkflowTests(unittest.TestCase):
    def workflow(self) -> str:
        return (
            Path(__file__).parents[3] / ".github" / "workflows" / "aurum-pi3-smsc95xx-packet-differential.yml"
        ).read_text(encoding="utf-8").lower()

    def test_workflow_is_host_only_and_main_gated(self):
        workflow = self.workflow()
        self.assertIn("runs-on: ubuntu-24.04", workflow)
        self.assertIn("if: github.ref == 'refs/heads/main'", workflow)
        self.assertNotIn("169.254.129.122", workflow)
        self.assertNotIn("ssh ", workflow)
        self.assertNotIn("self-hosted", workflow)

    def test_workflow_has_no_module_binding_or_usb_execution_path(self):
        workflow = self.workflow()
        for token in ("modprobe", "insmod", "modules_install", ".ko", "unbind", "usb_submit_urb", "libusb"):
            self.assertNotIn(token, workflow)


if __name__ == "__main__":
    unittest.main()
