from __future__ import annotations

import hashlib
import json
import unittest

from Projects.AdaptiveKernel.pi3_smsc95xx_packet_transfer_model import (
    REGISTER_MODEL_SCHEMA,
    RX_STS_ERROR_SUMMARY,
    TX_CMD_A_FIRST_SEG,
    TX_CMD_A_LAST_SEG,
    TX_CMD_B_CSUM_ENABLE,
    _REQUIRED_FALSE,
    build_packet_transfer_model,
    decode_rx_status,
    model_register_transfer,
    model_tx_frame,
)


def _seal(value: dict) -> dict:
    body = dict(value)
    body.pop("receipt_sha256", None)
    value["receipt_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    ).hexdigest()
    return value


def fixture_register_model() -> dict:
    inherited = [key for key in _REQUIRED_FALSE if key != "usb_transfer_allowed"]
    return _seal(
        {
            "schema": REGISTER_MODEL_SCHEMA,
            "state": "verified-offline-register-interrupt-shadow",
            "interrupt_sources": [
                {
                    "name": "tx-error",
                    "status_mask": 0x00004000,
                    "endpoint_mask": 0x00004000,
                    "clear_semantics": "write-one-clear",
                }
            ],
            "authority": {key: False for key in inherited},
        }
    )


class PacketTransferShadowTests(unittest.TestCase):
    def test_sealed_model_remains_zero_authority(self):
        result = build_packet_transfer_model(fixture_register_model())
        self.assertEqual(result["state"], "verified-offline-packet-transfer-shadow")
        self.assertEqual(result["next_gate"], "source-referenced-packet-transfer-differential-before-native-binding")
        for key in _REQUIRED_FALSE:
            self.assertFalse(result["authority"][key])
        self.assertFalse(result["invariants"]["live_pi_contacted"])
        self.assertFalse(result["invariants"]["usb_transfer_submitted"])
        self.assertTrue(result["invariants"]["last_known_good_preserved"])

    def test_register_read_and_write_shapes_are_modeled_without_io(self):
        read = model_register_transfer(direction="read", register_index=0x68)
        self.assertEqual(read["request"], 0xA1)
        self.assertEqual(read["request_type"], 0xC0)
        self.assertEqual(read["length"], 4)
        self.assertIsNone(read["payload_le_hex"])
        write = model_register_transfer(direction="write", register_index=0x10, value=0x12345678)
        self.assertEqual(write["request"], 0xA0)
        self.assertEqual(write["request_type"], 0x40)
        self.assertEqual(write["payload_le_hex"], "78563412")
        self.assertFalse(write["usb_transfer_performed"])
        self.assertFalse(write["device_io_performed"])

    def test_register_transfer_rejects_ambiguous_or_out_of_range_inputs(self):
        with self.assertRaisesRegex(ValueError, "read or write"):
            model_register_transfer(direction="probe", register_index=0)
        with self.assertRaisesRegex(ValueError, "wIndex"):
            model_register_transfer(direction="read", register_index=0x10000)
        with self.assertRaisesRegex(ValueError, "does not accept"):
            model_register_transfer(direction="read", register_index=0, value=1)
        with self.assertRaisesRegex(ValueError, "uint32"):
            model_register_transfer(direction="write", register_index=0, value=0x1_0000_0000)

    def test_tx_frame_without_checksum_matches_command_shape(self):
        tx = model_tx_frame(frame_length=1500)
        self.assertFalse(tx["checksum_enabled"])
        self.assertEqual(tx["framing_overhead_bytes"], 8)
        self.assertEqual(tx["usb_buffer_length"], 1508)
        self.assertEqual(tx["tx_cmd_a"] & TX_CMD_A_FIRST_SEG, TX_CMD_A_FIRST_SEG)
        self.assertEqual(tx["tx_cmd_a"] & TX_CMD_A_LAST_SEG, TX_CMD_A_LAST_SEG)
        self.assertEqual(tx["tx_cmd_b"] & TX_CMD_B_CSUM_ENABLE, 0)
        self.assertFalse(tx["usb_transfer_performed"])

    def test_tx_checksum_preamble_and_overhead_are_modeled(self):
        tx = model_tx_frame(frame_length=512, checksum_start_offset=34, checksum_field_offset=16)
        self.assertTrue(tx["checksum_enabled"])
        self.assertEqual(tx["checksum_preamble"], (50 << 16) | 34)
        self.assertEqual(tx["framing_overhead_bytes"], 12)
        self.assertEqual(tx["usb_buffer_length"], 524)
        self.assertEqual(tx["tx_cmd_b"] & TX_CMD_B_CSUM_ENABLE, TX_CMD_B_CSUM_ENABLE)

    def test_tx_frame_rejects_unrepresentable_lengths_and_checksum_offsets(self):
        with self.assertRaisesRegex(ValueError, "11-bit"):
            model_tx_frame(frame_length=2048)
        with self.assertRaisesRegex(ValueError, "requires both"):
            model_tx_frame(frame_length=128, checksum_start_offset=34)
        with self.assertRaisesRegex(ValueError, "end offset"):
            model_tx_frame(frame_length=128, checksum_start_offset=65530, checksum_field_offset=10)

    def test_rx_status_models_length_error_and_next_frame_alignment(self):
        status = (1500 << 16)
        rx = decode_rx_status(status_word=status, available_payload_bytes=1500)
        self.assertEqual(rx["frame_length"], 1500)
        self.assertFalse(rx["error_summary"])
        self.assertEqual(rx["status_and_align_prefix_bytes"], 6)
        self.assertEqual(rx["next_frame_padding_bytes"], 2)
        self.assertTrue(rx["payload_length_valid"])
        self.assertFalse(rx["packet_buffer_mutated"])

        bad = decode_rx_status(
            status_word=(512 << 16) | RX_STS_ERROR_SUMMARY,
            available_payload_bytes=500,
        )
        self.assertTrue(bad["error_summary"])
        self.assertFalse(bad["payload_length_valid"])

    def test_tampered_register_model_fails_closed(self):
        model = fixture_register_model()
        model["authority"]["register_write_allowed"] = True
        with self.assertRaisesRegex(ValueError, "sealed receipt"):
            build_packet_transfer_model(model)

    def test_resealed_nonzero_authority_fails_closed(self):
        model = fixture_register_model()
        model["authority"]["register_write_allowed"] = True
        _seal(model)
        with self.assertRaisesRegex(ValueError, "register_write_allowed=false"):
            build_packet_transfer_model(model)


if __name__ == "__main__":
    unittest.main()
