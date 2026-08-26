from __future__ import annotations

import unittest

from Projects.AdaptiveKernel.pi3_smsc95xx_virtual_usb_queue_pressure import (
    SCHEMA,
    STATE,
    EndpointQueue,
    _canonical_sha256,
    run_queue_pressure_model,
)


def timing_receipt() -> dict:
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
        "schema": "aurum.pi3.smsc95xx.virtual-usb-timing-concurrency.v1",
        "state": "controlled-virtual-usb-timing-concurrency-passed",
        "mismatch_count": 0,
        "authority": authority,
        "invariants": {
            "live_pi_contacted": False,
            "usb_device_opened": False,
            "usb_transfer_submitted": False,
            "clear_halt_submitted": False,
            "register_access_performed": False,
            "wall_clock_or_sleep_used": False,
        },
    }
    body["receipt_sha256"] = _canonical_sha256(body)
    return body


class QueuePressureTests(unittest.TestCase):
    def test_depth_is_hard_bounded_and_returns_backpressure(self):
        queue = EndpointQueue("tx", max_depth=2)
        self.assertEqual(queue.submit()[0], "active")
        self.assertEqual(queue.submit()[0], "queued")
        self.assertEqual(queue.submit(), ("backpressure", None))
        self.assertEqual(queue.depth, 2)

    def test_queued_cancel_removes_work(self):
        queue = EndpointQueue("rx", max_depth=3)
        _, first = queue.submit()
        _, second = queue.submit()
        self.assertIsNotNone(first)
        self.assertEqual(queue.cancel(second or 0), "queued-cancelled")
        self.assertEqual(queue.depth, 1)

    def test_active_cancel_is_intent_and_completion_quarantines(self):
        queue = EndpointQueue("tx")
        _, transfer_id = queue.submit()
        self.assertEqual(queue.cancel(transfer_id or 0), "active-cancel-intent")
        self.assertEqual(queue.cancel_intents, 1)
        self.assertEqual(queue.complete_active(), "cancelled-completion-quarantined")
        self.assertEqual(queue.quarantined, 1)

    def test_disconnect_clears_outstanding_work(self):
        queue = EndpointQueue("rx", max_depth=4)
        for _ in range(4):
            queue.submit()
        self.assertEqual(queue.disconnect(), 4)
        self.assertEqual(queue.depth, 0)
        self.assertEqual(queue.submit(), ("rejected-disconnected", None))
        queue.reconnect()
        self.assertEqual(queue.submit()[0], "active")

    def test_tx_and_rx_pressure_are_independent(self):
        tx = EndpointQueue("tx", max_depth=1)
        rx = EndpointQueue("rx", max_depth=1)
        self.assertEqual(tx.submit()[0], "active")
        self.assertEqual(tx.submit()[0], "backpressure")
        self.assertEqual(rx.submit()[0], "active")

    def test_upstream_authority_fails_closed(self):
        receipt = timing_receipt()
        receipt["authority"]["write_authority"] = True
        receipt["receipt_sha256"] = _canonical_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
        with self.assertRaises(ValueError):
            run_queue_pressure_model(timing_receipt=receipt, sequence_steps=32)

    def test_stress_model_is_deterministic_and_zero_authority(self):
        first = run_queue_pressure_model(timing_receipt=timing_receipt(), max_depth=4, sequence_seed=17, sequence_steps=1024)
        second = run_queue_pressure_model(timing_receipt=timing_receipt(), max_depth=4, sequence_seed=17, sequence_steps=1024)
        self.assertEqual(first["schema"], SCHEMA)
        self.assertEqual(first["state"], STATE)
        self.assertEqual(first["violation_count"], 0)
        self.assertEqual(first["receipt_sha256"], second["receipt_sha256"])
        self.assertEqual(first["trace_sha256"], second["trace_sha256"])
        self.assertLessEqual(first["max_observed_depth"]["tx"], 4)
        self.assertLessEqual(first["max_observed_depth"]["rx"], 4)
        self.assertTrue(all(value is False for value in first["authority"].values()))
        self.assertTrue(all(value is False for value in first["invariants"].values()))


if __name__ == "__main__":
    unittest.main()
