from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pi3_smsc95xx_linux_usbnet_urb_reference import (
    LINUX_STABLE_COMMIT,
    STATE,
    _canonical_sha256,
    run_reference_differential,
)


def sealed_queue() -> dict:
    body = {
        "schema": "aurum.pi3.smsc95xx.virtual-usb-queue-pressure.v1",
        "state": "controlled-virtual-usb-queue-pressure-passed",
        "violation_count": 0,
        "queue_contract": {
            "active_cancel_is_intent_only": True,
            "backpressure_fail_closed": True,
            "cancelled_completion_quarantined": True,
            "disconnect_invalidates_outstanding_work": True,
            "queue_depth_bounded": True,
            "queued_cancel_removes_work": True,
            "reconnect_requires_fresh_submission": True,
            "tx_rx_queues_independent": True,
        },
        "authority": {
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
        },
    }
    body["receipt_sha256"] = _canonical_sha256(body)
    return body


def source_equivalence() -> dict:
    body = {
        "schema": "aurum.pi3.source-equivalence.v1",
        "state": "passed-official-package-binary-equivalence",
        "target": {"kernel": "6.18.34+rpt-rpi-v8"},
        "official": {
            "source_package": "linux",
            "source_version": "1:6.18.34-1+rpt1",
            "kernel_binary_sha256": "b" * 64,
        },
        "physical": {
            "source_package": "linux",
            "source_version": "1:6.18.34-1+rpt1",
            "kernel_binary_sha256": "b" * 64,
        },
        "checks": {
            "official_archive_url": True,
            "package_architecture_match": True,
            "package_name_match": True,
            "package_version_match": True,
            "running_kernel_bytes_match_official_package": True,
            "source_package_match": True,
            "source_version_match": True,
        },
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
    body["receipt_sha256"] = _canonical_sha256(body)
    return body


def tag_verification() -> dict:
    return {
        "schema": "aurum.linux-stable-tag-verification.v1",
        "repository": "gregkh/linux",
        "tag": "v6.18.34",
        "tag_object_sha": "71659eca49870e2f9d33412084034abe9c3e453f",
        "commit": "18ad16ce4a6b2714583fd1e1044c6ea8e53b3519",
        "verified": True,
    }


URB_SOURCE = br'''\
/** usb_submit_urb - issue an asynchronous transfer request for an endpoint
 * Request completion will be indicated later, asynchronously, by calling the completion handler.
 * If the submission is successful, the complete() callback from the URB will be called exactly once
 */
int usb_submit_urb(void) {
 WARN_ONCE(1, "URB %p submitted while active\n", urb);
 return -EBUSY;
}
/** usb_unlink_urb - abort/cancel a transfer request for an endpoint
 * This request is asynchronous, however the HCD might call the ->complete() callback during unlink.
 * Success is indicated by returning -EINPROGRESS
 */
/** usb_kill_urb - cancel a transfer request and wait for it to finish
 * upon return all completion handlers will have finished
 */
'''

USBNET_SOURCE = br'''\
#define RX_QLEN(dev) ((dev)->rx_qlen)
#define TX_QLEN(dev) ((dev)->tx_qlen)
static int unlink_urbs(void) {
 entry->state = unlink_start;
 /* usb_unlink_urb is always racing with .complete */
 usb_get_urb(urb);
 usb_unlink_urb (urb);
}
void stop(void) {
 /* ensure there are no more active urbs */
 unlink_urbs(dev, &dev->txq);
 unlink_urbs(dev, &dev->rxq);
 wait_skb_queue_empty(&dev->rxq);
 wait_skb_queue_empty(&dev->txq);
 wait_skb_queue_empty(&dev->done);
}
void kevent(void) {
 if (test_bit (EVENT_TX_HALT, &dev->flags)) {
   unlink_urbs (dev, &dev->txq);
   usb_clear_halt (dev->udev, dev->out);
 }
 if (test_bit (EVENT_RX_HALT, &dev->flags)) {
   unlink_urbs (dev, &dev->rxq);
   usb_clear_halt (dev->udev, dev->in);
 }
}
void usbnet_status_stop(struct usbnet *dev) {
 usb_kill_urb(dev->interrupt);
}
'''


class LinuxUsbnetUrbReferenceTests(unittest.TestCase):
    def test_signed_reference_semantics_match_conservative_queue_model(self):
        receipt = run_reference_differential(
            queue_receipt=sealed_queue(),
            source_equivalence=source_equivalence(),
            tag_verification=tag_verification(),
            usbnet_source=USBNET_SOURCE,
            urb_source=URB_SOURCE,
            source_commit=LINUX_STABLE_COMMIT,
        )
        self.assertEqual(receipt["state"], STATE)
        self.assertEqual(receipt["mismatch_count"], 0)
        self.assertTrue(all(receipt["differential"].values()))
        self.assertTrue(all(value is False for value in receipt["authority"].values()))
        self.assertFalse(receipt["invariants"]["kernel_code_executed"])

    def test_missing_reference_anchor_fails_closed(self):
        receipt = run_reference_differential(
            queue_receipt=sealed_queue(),
            source_equivalence=source_equivalence(),
            tag_verification=tag_verification(),
            usbnet_source=USBNET_SOURCE.replace(b"wait_skb_queue_empty(&dev->done);", b""),
            urb_source=URB_SOURCE,
            source_commit=LINUX_STABLE_COMMIT,
        )
        self.assertNotEqual(receipt["state"], STATE)
        self.assertGreater(receipt["mismatch_count"], 0)
        self.assertIn("usbnet:stop_drains_rx_tx_done", receipt["source_semantics"]["missing_anchors"])

    def test_moved_reference_commit_is_rejected(self):
        with self.assertRaises(ValueError):
            run_reference_differential(
                queue_receipt=sealed_queue(),
                source_equivalence=source_equivalence(),
                tag_verification=tag_verification(),
                usbnet_source=USBNET_SOURCE,
                urb_source=URB_SOURCE,
                source_commit="0" * 40,
            )

    def test_queue_authority_regression_is_rejected(self):
        queue = sealed_queue()
        queue["authority"]["usb_transfer_allowed"] = True
        body = dict(queue)
        body.pop("receipt_sha256")
        queue["receipt_sha256"] = _canonical_sha256(body)
        with self.assertRaises(ValueError):
            run_reference_differential(
                queue_receipt=queue,
                source_equivalence=source_equivalence(),
                tag_verification=tag_verification(),
                usbnet_source=USBNET_SOURCE,
                urb_source=URB_SOURCE,
                source_commit=LINUX_STABLE_COMMIT,
            )

    def test_unverified_stable_tag_is_rejected(self):
        tag = tag_verification()
        tag["verified"] = False
        with self.assertRaises(ValueError):
            run_reference_differential(
                queue_receipt=sealed_queue(),
                source_equivalence=source_equivalence(),
                tag_verification=tag,
                usbnet_source=USBNET_SOURCE,
                urb_source=URB_SOURCE,
                source_commit=LINUX_STABLE_COMMIT,
            )

    def test_running_source_version_drift_is_rejected(self):
        eq = source_equivalence()
        eq["official"]["source_version"] = "1:6.18.39-1+rpt1"
        body = dict(eq)
        body.pop("receipt_sha256")
        eq["receipt_sha256"] = _canonical_sha256(body)
        with self.assertRaises(ValueError):
            run_reference_differential(
                queue_receipt=sealed_queue(),
                source_equivalence=eq,
                tag_verification=tag_verification(),
                usbnet_source=USBNET_SOURCE,
                urb_source=URB_SOURCE,
                source_commit=LINUX_STABLE_COMMIT,
            )


if __name__ == "__main__":
    unittest.main()
