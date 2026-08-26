"""Build a zero-authority packet/USB-transfer shadow for Pi3 smsc95xx.

This is the next bounded step after register/interrupt differential verification.
It models only reference-derived control-transfer shapes and packet framing as plain
values. It never opens a USB device, submits a transfer, touches a register, loads
a module, changes a binding, mutates firmware/network state, or grants authority.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

REGISTER_MODEL_SCHEMA = "aurum.pi3.smsc95xx.register-interrupt-shadow.v1"
SCHEMA = "aurum.pi3.smsc95xx.packet-transfer-shadow.v1"

_REQUIRED_FALSE = (
    "mutation_allowed",
    "device_io_allowed",
    "usb_transfer_allowed",
    "register_write_allowed",
    "interrupt_ack_write_allowed",
    "driver_binding_change_allowed",
    "kernel_module_load_allowed",
    "firmware_mutation_allowed",
    "network_configuration_change_allowed",
    "promotion_allowed",
    "write_authority",
)

# Reference constants from the pinned smsc95xx header/source family.
USB_VENDOR_REQUEST_WRITE_REGISTER = 0xA0
USB_VENDOR_REQUEST_READ_REGISTER = 0xA1
USB_DIR_IN_VENDOR_DEVICE = 0xC0
USB_DIR_OUT_VENDOR_DEVICE = 0x40
REGISTER_TRANSFER_BYTES = 4

TX_CMD_A_DATA_OFFSET = 0x001F0000
TX_CMD_A_FIRST_SEG = 0x00002000
TX_CMD_A_LAST_SEG = 0x00001000
TX_CMD_A_BUF_SIZE = 0x000007FF
TX_CMD_B_CSUM_ENABLE = 0x00004000
TX_CMD_B_FRAME_LENGTH = 0x000007FF
TX_OVERHEAD_BYTES = 8
TX_OVERHEAD_CSUM_BYTES = 12
TX_CHECKSUM_MIN_FRAME_LENGTH_EXCLUSIVE = 45
TX_CHECKSUM_TRAILING_GUARD_BYTES = 5

RX_STS_FRAME_LENGTH = 0x3FFF0000
RX_STS_ERROR_SUMMARY = 0x00008000
RX_STATUS_WORD_BYTES = 4
NET_IP_ALIGN_BYTES = 2
RX_ALIGNMENT_BYTES = 4


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    ).hexdigest()


def _verify_sealed(value: Mapping[str, Any]) -> bool:
    claimed = value.get("receipt_sha256")
    if not isinstance(claimed, str):
        return False
    body = dict(value)
    body.pop("receipt_sha256", None)
    return claimed == _canonical_sha256(body)


def _require_zero_authority(register_model: Mapping[str, Any]) -> None:
    if register_model.get("schema") != REGISTER_MODEL_SCHEMA or not _verify_sealed(register_model):
        raise ValueError("register/interrupt model must be a valid sealed receipt")
    if register_model.get("state") != "verified-offline-register-interrupt-shadow":
        raise ValueError("register/interrupt model is not verified")
    authority = register_model.get("authority")
    if not isinstance(authority, Mapping):
        raise ValueError("register/interrupt model authority is malformed")
    inherited = (
        "mutation_allowed",
        "device_io_allowed",
        "register_write_allowed",
        "interrupt_ack_write_allowed",
        "driver_binding_change_allowed",
        "kernel_module_load_allowed",
        "firmware_mutation_allowed",
        "network_configuration_change_allowed",
        "promotion_allowed",
        "write_authority",
    )
    for key in inherited:
        if authority.get(key) is not False:
            raise ValueError(f"register/interrupt model must keep {key}=false")


def model_register_transfer(*, direction: str, register_index: int, value: int | None = None) -> dict[str, Any]:
    """Describe one synthetic register control transfer without submitting it."""
    if direction not in {"read", "write"}:
        raise ValueError("direction must be read or write")
    if not isinstance(register_index, int) or not 0 <= register_index <= 0xFFFF:
        raise ValueError("register_index must fit USB wIndex")
    if direction == "read":
        if value is not None:
            raise ValueError("read transfer does not accept a write value")
        request = USB_VENDOR_REQUEST_READ_REGISTER
        request_type = USB_DIR_IN_VENDOR_DEVICE
        payload_le_hex = None
    else:
        if not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF:
            raise ValueError("write value must be uint32")
        request = USB_VENDOR_REQUEST_WRITE_REGISTER
        request_type = USB_DIR_OUT_VENDOR_DEVICE
        payload_le_hex = value.to_bytes(4, "little").hex()
    return {
        "direction": direction,
        "request": request,
        "request_type": request_type,
        "w_value": 0,
        "w_index": register_index,
        "length": REGISTER_TRANSFER_BYTES,
        "payload_le_hex": payload_le_hex,
        "usb_transfer_performed": False,
        "device_io_performed": False,
    }


def model_tx_frame(
    *,
    frame_length: int,
    checksum_start_offset: int | None = None,
    checksum_field_offset: int | None = None,
) -> dict[str, Any]:
    """Model smsc95xx TX command/preamble framing for a synthetic frame."""
    if not isinstance(frame_length, int) or not 1 <= frame_length <= TX_CMD_B_FRAME_LENGTH:
        raise ValueError("frame_length must fit the 11-bit TX frame-length field")
    checksum_requested = checksum_start_offset is not None or checksum_field_offset is not None
    if checksum_requested and (checksum_start_offset is None or checksum_field_offset is None):
        raise ValueError("checksum framing requires both start and field offsets")

    tx_cmd_a = frame_length | TX_CMD_A_FIRST_SEG | TX_CMD_A_LAST_SEG
    tx_cmd_b = frame_length
    checksum_preamble = None
    checksum_enabled = False
    software_checksum_fallback = False
    overhead = TX_OVERHEAD_BYTES
    if checksum_requested:
        assert checksum_start_offset is not None and checksum_field_offset is not None
        if not 0 <= checksum_start_offset <= 0xFFFF or not 0 <= checksum_field_offset <= 0xFFFF:
            raise ValueError("checksum offsets must fit uint16")
        checksum_end = checksum_start_offset + checksum_field_offset
        if checksum_end > 0xFFFF:
            raise ValueError("checksum end offset must fit uint16")
        payload_after_start = frame_length - checksum_start_offset
        checksum_enabled = (
            frame_length > TX_CHECKSUM_MIN_FRAME_LENGTH_EXCLUSIVE
            and payload_after_start > TX_CHECKSUM_TRAILING_GUARD_BYTES
            and checksum_field_offset < payload_after_start - TX_CHECKSUM_TRAILING_GUARD_BYTES
        )
        software_checksum_fallback = not checksum_enabled
        if checksum_enabled:
            checksum_preamble = (checksum_end << 16) | checksum_start_offset
            tx_cmd_a += 4
            tx_cmd_b += 4
            tx_cmd_b |= TX_CMD_B_CSUM_ENABLE
            overhead = TX_OVERHEAD_CSUM_BYTES

    return {
        "frame_length": frame_length,
        "checksum_requested": checksum_requested,
        "checksum_enabled": checksum_enabled,
        "software_checksum_fallback": software_checksum_fallback,
        "checksum_preamble": checksum_preamble,
        "tx_cmd_a": tx_cmd_a,
        "tx_cmd_b": tx_cmd_b,
        "usb_buffer_length": frame_length + overhead,
        "framing_overhead_bytes": overhead,
        "usb_transfer_performed": False,
        "device_io_performed": False,
    }


def decode_rx_status(*, status_word: int, available_payload_bytes: int) -> dict[str, Any]:
    """Decode the synthetic RX status/frame-length and alignment contract."""
    if not isinstance(status_word, int) or not 0 <= status_word <= 0xFFFFFFFF:
        raise ValueError("status_word must be uint32")
    if not isinstance(available_payload_bytes, int) or available_payload_bytes < 0:
        raise ValueError("available_payload_bytes must be non-negative")
    frame_length = (status_word & RX_STS_FRAME_LENGTH) >> 16
    alignment_padding = (RX_ALIGNMENT_BYTES - ((frame_length + NET_IP_ALIGN_BYTES) % RX_ALIGNMENT_BYTES)) % RX_ALIGNMENT_BYTES
    return {
        "frame_length": frame_length,
        "error_summary": bool(status_word & RX_STS_ERROR_SUMMARY),
        "status_and_align_prefix_bytes": RX_STATUS_WORD_BYTES + NET_IP_ALIGN_BYTES,
        "next_frame_padding_bytes": alignment_padding,
        "payload_length_valid": frame_length <= available_payload_bytes,
        "device_io_performed": False,
        "packet_buffer_mutated": False,
    }


def build_packet_transfer_model(register_model: Mapping[str, Any]) -> dict[str, Any]:
    _require_zero_authority(register_model)
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "state": "verified-offline-packet-transfer-shadow",
        "input_register_model_receipt_sha256": register_model.get("receipt_sha256"),
        "register_control_transfer": {
            "read_request": USB_VENDOR_REQUEST_READ_REGISTER,
            "read_request_type": USB_DIR_IN_VENDOR_DEVICE,
            "write_request": USB_VENDOR_REQUEST_WRITE_REGISTER,
            "write_request_type": USB_DIR_OUT_VENDOR_DEVICE,
            "register_transfer_bytes": REGISTER_TRANSFER_BYTES,
            "w_value": 0,
            "register_offset_field": "wIndex",
            "register_payload_endianness": "little",
        },
        "tx_packet_framing": {
            "command_word_bytes": TX_OVERHEAD_BYTES,
            "checksum_preamble_bytes": TX_OVERHEAD_CSUM_BYTES - TX_OVERHEAD_BYTES,
            "first_segment_mask": TX_CMD_A_FIRST_SEG,
            "last_segment_mask": TX_CMD_A_LAST_SEG,
            "buffer_size_mask": TX_CMD_A_BUF_SIZE,
            "frame_length_mask": TX_CMD_B_FRAME_LENGTH,
            "checksum_enable_mask": TX_CMD_B_CSUM_ENABLE,
            "hardware_checksum_min_frame_length_exclusive": TX_CHECKSUM_MIN_FRAME_LENGTH_EXCLUSIVE,
            "checksum_trailing_guard_bytes": TX_CHECKSUM_TRAILING_GUARD_BYTES,
        },
        "rx_packet_framing": {
            "status_word_bytes": RX_STATUS_WORD_BYTES,
            "data_offset_bytes": NET_IP_ALIGN_BYTES,
            "frame_length_mask": RX_STS_FRAME_LENGTH,
            "frame_length_shift": 16,
            "error_summary_mask": RX_STS_ERROR_SUMMARY,
            "next_frame_alignment_bytes": RX_ALIGNMENT_BYTES,
        },
        "authority": {key: False for key in _REQUIRED_FALSE},
        "invariants": {
            "live_pi_contacted": False,
            "usb_device_opened": False,
            "usb_transfer_submitted": False,
            "register_read_performed": False,
            "register_write_performed": False,
            "packet_buffer_mutated": False,
            "kernel_module_entrypoint_present": False,
            "driver_binding_path_present": False,
            "last_known_good_preserved": True,
        },
        "next_gate": "source-referenced-packet-transfer-differential-before-native-binding",
    }
    result["receipt_sha256"] = _canonical_sha256(result)
    return result
