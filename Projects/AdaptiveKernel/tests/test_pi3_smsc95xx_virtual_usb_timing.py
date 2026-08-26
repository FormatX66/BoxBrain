from __future__ import annotations

import unittest

from Projects.AdaptiveKernel.pi3_smsc95xx_virtual_usb_timing import (
    SCHEMA,
    STATE,
    VirtualUsbScheduler,
    _canonical_sha256,
    retry_due_ms,
    run_timing_model,
)


def fault_receipt() -> dict:
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
        "schema": "aurum.pi3.smsc95xx.virtual-usb-fault-harness.v1",
        "state": "controlled-virtual-usb-fault-harness-passed",
        "mismatch_count": 0,
        "retry_budget": 2,
        "authority": authority,
        "invariants": {
            "live_pi_contacted": False,
            "usb_device_opened": False,
            "usb_transfer_submitted": False,
            "clear_halt_submitted": False,
        },
    }
    body["receipt_sha256"] = _canonical_sha256(body)
    return body


class VirtualUsbTimingTests(unittest.TestCase):
    def test_same_endpoint_serializes(self):
        scheduler = VirtualUsbScheduler()
        first = scheduler.submit("tx", now_ms=0, duration_ms=10)
        second = scheduler.submit("tx", now_ms=1, duration_ms=2)
        self.assertEqual(second.start_ms, first.finish_ms)

    def test_tx_rx_may_overlap(self):
        scheduler = VirtualUsbScheduler()
        tx = scheduler.submit("tx", now_ms=0, duration_ms=10)
        rx = scheduler.submit("rx", now_ms=1, duration_ms=2)
        self.assertLess(rx.start_ms, tx.finish_ms)

    def test_early_completion_refuses(self):
        scheduler = VirtualUsbScheduler()
        transfer = scheduler.submit("rx", now_ms=0, duration_ms=5)
        self.assertEqual(scheduler.complete(transfer, now_ms=4), "early-completion-refused")
        self.assertEqual(scheduler.complete(transfer, now_ms=5), "completed")

    def test_disconnect_invalidates_old_completion(self):
        scheduler = VirtualUsbScheduler()
        transfer = scheduler.submit("tx", now_ms=0, duration_ms=5)
        scheduler.disconnect(now_ms=1)
        self.assertEqual(scheduler.complete(transfer, now_ms=5), "stale-completion-quarantined")
        scheduler.reconnect(now_ms=6)
        fresh = scheduler.submit("tx", now_ms=6, duration_ms=1)
        self.assertEqual(scheduler.complete(fresh, now_ms=7), "completed")

    def test_submit_while_disconnected_fails_closed(self):
        scheduler = VirtualUsbScheduler()
        scheduler.disconnect(now_ms=0)
        with self.assertRaises(RuntimeError):
            scheduler.submit("rx", now_ms=1, duration_ms=2)

    def test_retry_backoff_is_bounded(self):
        self.assertEqual([retry_due_ms(attempt=index) for index in range(1, 6)], [5, 10, 20, 40, 40])

    def test_upstream_authority_fails_closed(self):
        receipt = fault_receipt()
        receipt["authority"]["usb_transfer_allowed"] = True
        receipt["receipt_sha256"] = _canonical_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
        with self.assertRaises(ValueError):
            run_timing_model(fault_receipt=receipt, sequence_steps=32)

    def test_model_is_sealed_deterministic_and_zero_authority(self):
        first = run_timing_model(fault_receipt=fault_receipt(), sequence_seed=9, sequence_steps=512)
        second = run_timing_model(fault_receipt=fault_receipt(), sequence_seed=9, sequence_steps=512)
        self.assertEqual(first["schema"], SCHEMA)
        self.assertEqual(first["state"], STATE)
        self.assertEqual(first["mismatch_count"], 0)
        self.assertEqual(first["receipt_sha256"], second["receipt_sha256"])
        self.assertEqual(first["trace_sha256"], second["trace_sha256"])
        self.assertTrue(all(value is False for value in first["authority"].values()))
        self.assertTrue(all(value is False for value in first["invariants"].values()))


if __name__ == "__main__":
    unittest.main()
