from __future__ import annotations

import unittest

from Projects.AdaptiveKernel.pi3_smsc95xx_virtual_usb_fault_harness import (
    SCHEMA,
    STATE,
    _canonical_sha256,
    run_fault_harness,
    simulate_transfer,
)


def upstream_receipt() -> dict:
    authority = {
        "mutation_allowed": False,
        "device_io_allowed": False,
        "usb_transfer_allowed": False,
        "register_write_allowed": False,
        "interrupt_ack_write_allowed": False,
        "driver_binding_change_allowed": False,
        "kernel_module_load_allowed": False,
        "firmware_mutation_allowed": False,
        "network_configuration_change_allowed": False,
        "promotion_allowed": False,
        "write_authority": False,
    }
    body = {
        "schema": "aurum.pi3.smsc95xx.integrated-packet-control-loop-differential.v1",
        "state": "controlled-integrated-host-packet-control-loop-passed",
        "mismatch_count": 0,
        "authority": authority,
        "invariants": {
            "live_pi_contacted": False,
            "usb_device_opened": False,
            "usb_transfer_submitted": False,
            "driver_binding_changed": False,
        },
    }
    body["receipt_sha256"] = _canonical_sha256(body)
    return body


class VirtualUsbFaultHarnessTests(unittest.TestCase):
    def test_timeout_retries_then_delivers(self):
        result = simulate_transfer("tx", ("timeout", "success"), retry_budget=2)
        self.assertTrue(result["delivered"])
        self.assertEqual(result["retries_used"], 1)
        self.assertFalse(result["quarantined"])

    def test_retry_budget_is_hard_bounded(self):
        result = simulate_transfer("rx", ("timeout", "timeout", "success"), retry_budget=1)
        self.assertEqual(result["terminal"], "retry-budget-exhausted")
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["retries_used"], 1)
        self.assertTrue(result["quarantined"])

    def test_stall_creates_intent_but_never_usb_action(self):
        result = simulate_transfer("tx", ("stall", "success"), retry_budget=2)
        self.assertEqual(result["clear_halt_intents"], 1)
        receipt = run_fault_harness(integrated_receipt=upstream_receipt(), sequence_steps=32)
        self.assertFalse(receipt["invariants"]["clear_halt_submitted"])
        self.assertFalse(receipt["invariants"]["usb_transfer_submitted"])

    def test_short_transfer_quarantines_immediately(self):
        result = simulate_transfer("rx", ("short-transfer", "success"), retry_budget=2)
        self.assertEqual(result["terminal"], "short-transfer-quarantined")
        self.assertEqual(result["attempts"], 1)
        self.assertTrue(result["quarantined"])

    def test_disconnect_never_retries(self):
        result = simulate_transfer("tx", ("disconnect", "success"), retry_budget=2)
        self.assertEqual(result["terminal"], "disconnected")
        self.assertEqual(result["retries_used"], 0)
        self.assertEqual(result["attempts"], 1)

    def test_bad_upstream_seal_fails_closed(self):
        receipt = upstream_receipt()
        receipt["mismatch_count"] = 1
        with self.assertRaises(ValueError):
            run_fault_harness(integrated_receipt=receipt, sequence_steps=16)

    def test_upstream_authority_fails_closed(self):
        receipt = upstream_receipt()
        receipt["authority"]["usb_transfer_allowed"] = True
        receipt["receipt_sha256"] = _canonical_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
        with self.assertRaises(ValueError):
            run_fault_harness(integrated_receipt=receipt, sequence_steps=16)

    def test_deterministic_matrix_passes_zero_authority(self):
        receipt = run_fault_harness(
            integrated_receipt=upstream_receipt(),
            retry_budget=2,
            sequence_seed=0x9514FA17,
            sequence_steps=256,
        )
        self.assertEqual(receipt["schema"], SCHEMA)
        self.assertEqual(receipt["state"], STATE)
        self.assertEqual(receipt["matrix_scenarios"], 18)
        self.assertEqual(receipt["scenario_count"], 274)
        self.assertEqual(receipt["mismatch_count"], 0)
        self.assertTrue(all(value is False for value in receipt["authority"].values()))
        self.assertFalse(receipt["invariants"]["live_pi_contacted"])
        self.assertFalse(receipt["invariants"]["usb_device_opened"])
        self.assertFalse(receipt["invariants"]["usb_transfer_submitted"])

    def test_repeated_run_is_deterministic(self):
        first = run_fault_harness(integrated_receipt=upstream_receipt(), sequence_seed=7, sequence_steps=128)
        second = run_fault_harness(integrated_receipt=upstream_receipt(), sequence_seed=7, sequence_steps=128)
        self.assertEqual(first["receipt_sha256"], second["receipt_sha256"])
        self.assertEqual(first["trace_sha256"], second["trace_sha256"])


if __name__ == "__main__":
    unittest.main()
