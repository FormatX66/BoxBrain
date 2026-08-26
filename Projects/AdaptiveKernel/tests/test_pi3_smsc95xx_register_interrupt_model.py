from __future__ import annotations

import hashlib
import json
import unittest

from Projects.AdaptiveKernel.pi3_smsc95xx_register_interrupt_model import (
    build_register_interrupt_model,
    decode_interrupts,
)


def seal(value: dict) -> dict:
    body = dict(value)
    body.pop("receipt_sha256", None)
    encoded = json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    body["receipt_sha256"] = hashlib.sha256(encoded).hexdigest()
    return body


class Pi3Smsc95xxRegisterInterruptModelTests(unittest.TestCase):
    HEADER = '''
#define ID_REV (0x00)
#define INT_STS (0x08)
#define INT_STS_MAC_RTO_ (0x00040000)
#define INT_STS_TX_STOP_ (0x00020000)
#define INT_STS_RX_STOP_ (0x00010000)
#define INT_STS_PHY_INT_ (0x00008000)
#define INT_STS_TXE_ (0x00004000)
#define INT_STS_TDFU_ (0x00002000)
#define INT_STS_TDFO_ (0x00001000)
#define INT_STS_RXDF_ (0x00000800)
#define INT_STS_GPIOS_ (0x000007FF)
#define INT_STS_CLEAR_ALL_ (0xFFFFFFFF)
#define RX_CFG (0x0C)
#define TX_CFG (0x10)
#define HW_CFG (0x14)
#define RX_FIFO_INF (0x18)
#define TX_FIFO_INF (0x1C)
#define PM_CTRL (0x20)
#define INT_EP_CTL (0x68)
#define INT_EP_CTL_INTEP_ (0x80000000)
#define INT_EP_CTL_MAC_RTO_ (0x00080000)
#define INT_EP_CTL_RX_FIFO_ (0x00040000)
#define INT_EP_CTL_TX_STOP_ (0x00020000)
#define INT_EP_CTL_RX_STOP_ (0x00010000)
#define INT_EP_CTL_PHY_INT_ (0x00008000)
#define INT_EP_CTL_TXE_ (0x00004000)
#define INT_EP_CTL_TDFU_ (0x00002000)
#define INT_EP_CTL_TDFO_ (0x00001000)
#define INT_EP_CTL_RXDF_ (0x00000800)
#define INT_EP_CTL_GPIOS_ (0x000007FF)
#define MAC_CR (0x100)
#define MII_ADDR (0x114)
'''.lstrip()

    def functional_model(self) -> dict:
        return seal(
            {
                "schema": "aurum.pi3.smsc95xx.functional-model.v1",
                "state": "verified-offline-functional-model",
                "authority": {
                    "mutation_allowed": False,
                    "driver_binding_change_allowed": False,
                    "kernel_module_load_allowed": False,
                    "firmware_mutation_allowed": False,
                    "network_configuration_change_allowed": False,
                    "promotion_allowed": False,
                    "write_authority": False,
                },
            }
        )

    def manifest(self, upstream_header: str | None = None) -> dict:
        upstream_header = self.HEADER if upstream_header is None else upstream_header
        return {
            "schema": "aurum-pi3-hardware-reference-manifest-v1",
            "sources": [
                {
                    "id": "raspberry-pi-linux-smsc95xx-h",
                    "sha256": hashlib.sha256(self.HEADER.encode()).hexdigest(),
                },
                {
                    "id": "upstream-linux-v6.18-smsc95xx-h",
                    "sha256": hashlib.sha256(upstream_header.encode()).hexdigest(),
                },
            ],
        }

    def model(self) -> dict:
        return build_register_interrupt_model(
            self.functional_model(), self.manifest(), self.HEADER, self.HEADER
        )

    def test_builds_zero_authority_register_interrupt_shadow(self) -> None:
        model = self.model()
        self.assertEqual(model["state"], "verified-offline-register-interrupt-shadow")
        self.assertEqual(model["register_offsets"]["INT_STS"], 0x08)
        self.assertEqual(model["register_offsets"]["INT_EP_CTL"], 0x68)
        self.assertEqual(model["verification"]["rpi_upstream_define_mismatches"], 0)
        self.assertFalse(model["authority"]["device_io_allowed"])
        self.assertFalse(model["authority"]["register_write_allowed"])
        self.assertFalse(model["authority"]["interrupt_ack_write_allowed"])
        self.assertFalse(model["invariants"]["register_write_performed"])

    def test_mixed_phy_and_tx_error_preserves_read_only_semantics(self) -> None:
        result = decode_interrupts(
            self.model(), int_status=0x00008000 | 0x00004000, int_ep_ctl=0x00008000 | 0x00004000
        )
        self.assertEqual(result["active_sources"], ["phy-interrupt", "tx-error"])
        self.assertEqual(result["endpoint_reportable_sources"], ["phy-interrupt", "tx-error"])
        self.assertEqual(result["read_only_sources"], ["phy-interrupt"])
        self.assertEqual(result["w1c_ack_mask"], 0x00004000)
        self.assertFalse(result["device_io_performed"])
        self.assertFalse(result["register_write_performed"])

    def test_gpio_status_is_never_added_to_w1c_ack_mask(self) -> None:
        result = decode_interrupts(self.model(), int_status=0x00000005, int_ep_ctl=0x00000005)
        self.assertEqual(result["read_only_sources"], ["gpio"])
        self.assertEqual(result["w1c_ack_mask"], 0)

    def test_disabled_endpoint_keeps_active_event_out_of_reportable_set(self) -> None:
        result = decode_interrupts(self.model(), int_status=0x00004000, int_ep_ctl=0)
        self.assertEqual(result["active_sources"], ["tx-error"])
        self.assertEqual(result["endpoint_reportable_sources"], [])
        self.assertEqual(result["w1c_ack_mask"], 0x00004000)

    def test_unknown_bits_are_reported_not_silently_promoted(self) -> None:
        result = decode_interrupts(self.model(), int_status=0x80000000, int_ep_ctl=0x40000000)
        self.assertEqual(result["active_sources"], [])
        self.assertEqual(result["unknown_status_bits"], 0x80000000)
        self.assertEqual(result["unknown_endpoint_bits"], 0x40000000)

    def test_rpi_upstream_semantic_mismatch_fails_closed(self) -> None:
        upstream = self.HEADER.replace("#define INT_STS_TXE_ (0x00004000)", "#define INT_STS_TXE_ (0x00000040)")
        with self.assertRaises(ValueError):
            build_register_interrupt_model(
                self.functional_model(), self.manifest(upstream), self.HEADER, upstream
            )

    def test_source_hash_mismatch_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            build_register_interrupt_model(
                self.functional_model(), self.manifest(), self.HEADER + "x", self.HEADER
            )

    def test_tampered_functional_receipt_fails_closed(self) -> None:
        functional = self.functional_model()
        functional["state"] = "tampered"
        with self.assertRaises(ValueError):
            build_register_interrupt_model(functional, self.manifest(), self.HEADER, self.HEADER)


if __name__ == "__main__":
    unittest.main()
