from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from Projects.AdaptiveKernel.pi3_smsc95xx_usbnet_event_emulator import (
    UsbNetEventEmulator,
    _verify_sealed,
    build_event_emulator_receipt,
)

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "Projects" / "AdaptiveKernel" / "results"


def load(name: str):
    return json.loads((RESULTS / name).read_text(encoding="utf-8-sig"))


class UsbNetEventEmulatorTests(unittest.TestCase):
    @classmethod
    def inputs(cls):
        return {
            "lifecycle_shadow": load("pi3-smsc95xx-usbnet-lifecycle-shadow-latest.json"),
            "lifecycle_candidate": load("pi3-smsc95xx-usbnet-lifecycle-candidate-latest.json"),
            "lifecycle_differential": load("pi3-smsc95xx-usbnet-lifecycle-differential-latest.json"),
            "packet_differential": load("pi3-smsc95xx-packet-transfer-differential-latest.json"),
        }

    def test_current_sealed_lineage_builds_deterministic_receipt(self):
        first = build_event_emulator_receipt(**self.inputs(), sequence_seed=1234, sequence_steps=4096)
        second = build_event_emulator_receipt(**self.inputs(), sequence_seed=1234, sequence_steps=4096)
        self.assertEqual(first["receipt_sha256"], second["receipt_sha256"])
        self.assertTrue(_verify_sealed(first))
        self.assertEqual(first["state"], "controlled-userspace-usbnet-event-emulator-passed")
        self.assertEqual(first["mismatch_count"], 0)
        self.assertFalse(first["authority"]["write_authority"])
        self.assertFalse(first["invariants"]["live_pi_contacted"])

    def test_packets_are_refused_until_open_and_carrier_up(self):
        emulator = UsbNetEventEmulator()
        self.assertFalse(emulator.tx(64)["accepted"])
        emulator.lifecycle("probe_success")
        emulator.lifecycle("open_success")
        self.assertEqual(emulator.tx(64)["reason"], "carrier-down")
        emulator.lifecycle("link_up")
        self.assertTrue(emulator.tx(64)["accepted"])
        self.assertTrue(emulator.rx(64)["accepted"])

    def test_rx_halt_is_directional_and_recoverable(self):
        emulator = UsbNetEventEmulator()
        for action in ("probe_success", "open_success", "link_up", "rx_halt"):
            emulator.lifecycle(action)
        self.assertEqual(emulator.rx(256)["reason"], "rx-halted")
        self.assertTrue(emulator.tx(256)["accepted"])
        emulator.lifecycle("recover_rx")
        self.assertTrue(emulator.rx(256)["accepted"])

    def test_suspend_and_resume_require_relink_before_packets(self):
        emulator = UsbNetEventEmulator()
        for action in ("probe_success", "open_success", "link_up", "suspend"):
            emulator.lifecycle(action)
        self.assertEqual(emulator.tx(128)["reason"], "device-suspended")
        emulator.lifecycle("resume_success")
        self.assertEqual(emulator.rx(128)["reason"], "carrier-down")
        emulator.lifecycle("link_up")
        self.assertTrue(emulator.tx(128)["accepted"])
        self.assertTrue(emulator.rx(128)["accepted"])

    def test_tampered_upstream_receipt_fails_closed(self):
        inputs = self.inputs()
        tampered = copy.deepcopy(inputs["lifecycle_differential"])
        tampered["mismatch_count"] = 1
        inputs["lifecycle_differential"] = tampered
        with self.assertRaises(ValueError):
            build_event_emulator_receipt(**inputs, sequence_steps=32)

    def test_no_event_creates_device_or_mutation_authority(self):
        receipt = build_event_emulator_receipt(**self.inputs(), sequence_steps=128)
        self.assertTrue(all(value is False for value in receipt["authority"].values()))
        self.assertFalse(receipt["invariants"]["usb_device_opened"])
        self.assertFalse(receipt["invariants"]["usb_transfer_submitted"])
        self.assertFalse(receipt["invariants"]["driver_binding_changed"])
        self.assertTrue(receipt["invariants"]["last_known_good_preserved"])


if __name__ == "__main__":
    unittest.main()
