from __future__ import annotations

import hashlib
import json
import unittest

from Projects.AdaptiveKernel.pi3_smsc95xx_behavior_model import (
    apply_action,
    build_functional_model,
    replay_trace,
    BehaviorState,
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


class Pi3Smsc95xxBehaviorModelTests(unittest.TestCase):
    C_SOURCE = '''
#define SMSC_CHIPNAME "smsc95xx"
#define DEFAULT_RX_CSUM_ENABLE (true)
#define DEFAULT_TX_CSUM_ENABLE (true)
#define SMSC95XX_TX_OVERHEAD (8)
#define SMSC95XX_TX_OVERHEAD_CSUM (12)
static int smsc95xx_rx_fixup(void) { return 1; }
static int smsc95xx_tx_fixup(void) { return 1; }
static int products[] = { USB_DEVICE(0x0424, 0xec00) };
'''.lstrip()
    H_SOURCE = '''
#define RX_CFG 0x0000000C
#define HW_CFG 0x00000014
'''.lstrip()

    def source_refinement(self) -> dict:
        return seal(
            {
                "schema": "aurum-pi3-reference-source-refinement-v1",
                "state": "completed",
                "semantic_state": "completed-with-one-actionable-reference-gap",
                "correlation": {
                    "agreement_count": 7,
                    "agreements": [],
                    "closed_gap_ids": [
                        "controller-identity",
                        "negotiated-link-speed",
                        "running-driver-source-provenance",
                    ],
                    "gap_count": 1,
                    "gaps": [
                        {
                            "id": "candidate-driver-hardware-behavior",
                            "state": "unproven",
                        }
                    ],
                },
            }
        )

    def manifest(self) -> dict:
        return {
            "schema": "aurum-pi3-hardware-reference-manifest-v1",
            "target": {
                "model": "Raspberry Pi 3 Model B Rev 1.2",
                "serial": "00000000a6a7df7f",
                "kernel": "6.18.34+rpt-rpi-v8",
                "reference_driver": "smsc95xx",
            },
            "source_scope": {
                "raspberry_pi_linux_commit": "abc123",
            },
            "sources": [
                {
                    "id": "raspberry-pi-linux-smsc95xx-c",
                    "sha256": hashlib.sha256(self.C_SOURCE.encode()).hexdigest(),
                },
                {
                    "id": "raspberry-pi-linux-smsc95xx-h",
                    "sha256": hashlib.sha256(self.H_SOURCE.encode()).hexdigest(),
                },
            ],
        }

    def model(self) -> dict:
        return build_functional_model(
            self.source_refinement(), self.manifest(), self.C_SOURCE, self.H_SOURCE
        )

    def test_builds_verified_non_actuating_model(self) -> None:
        model = self.model()
        self.assertEqual(model["state"], "verified-offline-functional-model")
        self.assertEqual(model["constants"]["tx_overhead_bytes"], 8)
        self.assertEqual(model["constants"]["tx_overhead_checksum_bytes"], 12)
        self.assertEqual(model["verification"]["functional_scenarios_passed"], 7)
        self.assertTrue(model["verification"]["physical_state_reproduced"])
        self.assertFalse(model["authority"]["mutation_allowed"])
        self.assertFalse(model["invariants"]["promotion_authority_granted"])

    def test_reference_trace_reproduces_rx_checksum_and_tx_framing(self) -> None:
        trace = [
            {
                "kind": "identify",
                "usb_vendor": "0424",
                "usb_product": "ec00",
                "parent_vendor": "0424",
                "parent_product": "9514",
            },
            {"kind": "attach_reference", "driver": "smsc95xx"},
            {"kind": "link", "carrier": True, "speed_mbps": 100, "duplex": "full"},
            {"kind": "set_rx_checksum", "enabled": False},
            {"kind": "set_rx_checksum", "enabled": True},
            {"kind": "tx_prepare", "payload_len": 100, "checksum_partial": True},
        ]
        result = replay_trace(self.model(), trace)
        self.assertTrue(result["state"]["carrier"])
        self.assertTrue(result["state"]["rx_checksum_enabled"])
        self.assertEqual(result["outputs"][-1]["framed_len"], 112)

    def test_unproven_gigabit_link_is_rejected(self) -> None:
        model = self.model()
        state = BehaviorState(identity_verified=True, reference_attached=True)
        with self.assertRaises(ValueError):
            apply_action(
                state,
                {"kind": "link", "carrier": True, "speed_mbps": 1000, "duplex": "full"},
                model,
            )

    def test_wrong_controller_identity_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            apply_action(
                BehaviorState(),
                {
                    "kind": "identify",
                    "usb_vendor": "0424",
                    "usb_product": "7800",
                    "parent_vendor": "0424",
                    "parent_product": "9514",
                },
                self.model(),
            )

    def test_actuating_actions_are_rejected(self) -> None:
        model = self.model()
        for kind in ("write_eeprom", "bind_candidate", "load_module", "replace_kernel", "firmware_write"):
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):
                    apply_action(BehaviorState(), {"kind": kind}, model)

    def test_source_hash_mismatch_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            build_functional_model(
                self.source_refinement(), self.manifest(), self.C_SOURCE + "x", self.H_SOURCE
            )

    def test_tampered_source_refinement_fails_closed(self) -> None:
        refinement = self.source_refinement()
        refinement["state"] = "tampered"
        with self.assertRaises(ValueError):
            build_functional_model(refinement, self.manifest(), self.C_SOURCE, self.H_SOURCE)


if __name__ == "__main__":
    unittest.main()
