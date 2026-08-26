"""Reference-differential for Pi3 smsc95xx virtual USB scheduling.

This stage compares the sealed zero-authority queue/cancellation model with the
exact signed Linux stable v6.18.34 USB core and usbnet source semantics. It is a
source-level compatibility proof only: it performs no Pi contact, USB I/O,
register access, module loading, binding, firmware/network mutation, promotion,
or write-authority action.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

QUEUE_SCHEMA = "aurum.pi3.smsc95xx.virtual-usb-queue-pressure.v1"
QUEUE_STATE = "controlled-virtual-usb-queue-pressure-passed"
SOURCE_EQ_SCHEMA = "aurum.pi3.source-equivalence.v1"
SOURCE_EQ_STATE = "passed-official-package-binary-equivalence"
SCHEMA = "aurum.pi3.smsc95xx.linux-usbnet-urb-reference-differential.v1"
STATE = "linux-usbnet-urb-reference-compatible"
LINUX_STABLE_TAG = "v6.18.34"
LINUX_STABLE_TAG_OBJECT_SHA = "71659eca49870e2f9d33412084034abe9c3e453f"
LINUX_STABLE_COMMIT = "18ad16ce4a6b2714583fd1e1044c6ea8e53b3519"
PI_KERNEL = "6.18.34+rpt-rpi-v8"
PI_SOURCE_VERSION = "1:6.18.34-1+rpt1"
TAG_VERIFICATION_SCHEMA = "aurum.linux-stable-tag-verification.v1"

_REQUIRED_FALSE = (
    "mutation_allowed", "device_io_allowed", "usb_transfer_allowed",
    "register_write_allowed", "interrupt_ack_write_allowed",
    "driver_binding_change_allowed", "kernel_module_load_allowed",
    "firmware_mutation_allowed", "network_configuration_change_allowed",
    "promotion_allowed", "write_authority",
)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verify_sealed(value: Mapping[str, Any]) -> bool:
    claimed = value.get("receipt_sha256")
    if not isinstance(claimed, str):
        return False
    body = dict(value)
    body.pop("receipt_sha256", None)
    return claimed == _canonical_sha256(body)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_source(text: str) -> str:
    """Normalize whitespace and C comment line decoration, never code tokens.

    Semantic anchors intentionally span kernel-doc line wraps. Strip only the
    leading/trailing comment decoration at line boundaries so an inserted `*`
    from kernel-doc formatting cannot make an otherwise exact phrase disappear.
    """
    lines: list[str] = []
    for raw in text.replace("\t", " ").splitlines():
        line = raw.strip()
        if line.startswith("/*"):
            line = line[2:].lstrip("*").strip()
        elif line.startswith("*"):
            line = line[1:].strip()
        if line.endswith("*/"):
            line = line[:-2].strip()
        lines.append(line)
    return " ".join(" ".join(lines).split())


def _require_all(text: str, anchors: Mapping[str, tuple[str, ...]]) -> dict[str, bool]:
    normalized = _normalize_source(text)
    return {
        name: all(_normalize_source(anchor) in normalized for anchor in required)
        for name, required in anchors.items()
    }


def _validate_queue(receipt: Mapping[str, Any]) -> None:
    if receipt.get("schema") != QUEUE_SCHEMA or receipt.get("state") != QUEUE_STATE:
        raise ValueError("queue receipt is not the expected passed schema/state")
    if not _verify_sealed(receipt) or receipt.get("violation_count") != 0:
        raise ValueError("queue receipt is unsealed or contains violations")
    authority = receipt.get("authority")
    if not isinstance(authority, Mapping):
        raise ValueError("queue authority is malformed")
    for key in _REQUIRED_FALSE:
        if authority.get(key) is not False:
            raise ValueError(f"queue receipt must keep {key}=false")


def _validate_source_equivalence(receipt: Mapping[str, Any]) -> None:
    if receipt.get("schema") != SOURCE_EQ_SCHEMA or receipt.get("state") != SOURCE_EQ_STATE:
        raise ValueError("source-equivalence receipt is not the expected passed schema/state")
    if not _verify_sealed(receipt):
        raise ValueError("source-equivalence receipt is not sealed")
    target = receipt.get("target")
    official = receipt.get("official")
    physical = receipt.get("physical")
    checks = receipt.get("checks")
    authority = receipt.get("authority")
    if not isinstance(target, Mapping) or target.get("kernel") != PI_KERNEL:
        raise ValueError("source-equivalence receipt is not for the pinned Pi3 kernel")
    if not isinstance(official, Mapping) or not isinstance(physical, Mapping):
        raise ValueError("source-equivalence package evidence is malformed")
    for evidence in (official, physical):
        if evidence.get("source_package") != "linux":
            raise ValueError("running source package is not linux")
        if evidence.get("source_version") != PI_SOURCE_VERSION:
            raise ValueError("running source version changed from the pinned reference")
    if official.get("kernel_binary_sha256") != physical.get("kernel_binary_sha256"):
        raise ValueError("official and physical kernel hashes diverge")
    if not isinstance(checks, Mapping) or not checks or not all(value is True for value in checks.values()):
        raise ValueError("source-equivalence checks are not all true")
    if not isinstance(authority, Mapping):
        raise ValueError("source-equivalence authority is malformed")
    for key in (
        "mutation_allowed", "driver_binding_change_allowed",
        "kernel_module_load_allowed", "firmware_mutation_allowed",
        "network_configuration_change_allowed", "promotion_allowed",
        "write_authority",
    ):
        if authority.get(key) is not False:
            raise ValueError(f"source-equivalence receipt must keep {key}=false")


def _validate_tag_verification(receipt: Mapping[str, Any]) -> None:
    if receipt.get("schema") != TAG_VERIFICATION_SCHEMA:
        raise ValueError("Linux stable tag verification schema is invalid")
    if receipt.get("repository") != "gregkh/linux" or receipt.get("tag") != LINUX_STABLE_TAG:
        raise ValueError("Linux stable tag verification targets the wrong reference")
    if receipt.get("tag_object_sha") != LINUX_STABLE_TAG_OBJECT_SHA:
        raise ValueError("Linux stable tag object changed from the pinned reference")
    if receipt.get("commit") != LINUX_STABLE_COMMIT:
        raise ValueError("Linux stable tag commit changed from the pinned reference")
    if receipt.get("verified") is not True:
        raise ValueError("Linux stable tag signature is not verified")


_USB_CORE_ANCHORS = {
    "submit_is_async": (
        "usb_submit_urb - issue an asynchronous transfer request for an endpoint",
        "Request completion will be indicated later, asynchronously, by calling the completion handler.",
    ),
    "submit_completes_exactly_once": (
        "If the submission is successful, the complete() callback from the URB will be called exactly once",
    ),
    "unlink_is_async_and_completion_races": (
        "usb_unlink_urb - abort/cancel a transfer request for an endpoint",
        "This request is asynchronous, however the HCD might call the ->complete() callback during unlink.",
        "Success is indicated by returning -EINPROGRESS",
    ),
    "kill_waits_for_completion": (
        "usb_kill_urb - cancel a transfer request and wait for it to finish",
        "upon return all completion handlers will have finished",
    ),
    "active_urb_resubmit_refused": (
        'WARN_ONCE(1, "URB %p submitted while active',
        "return -EBUSY;",
    ),
}

_USBNET_ANCHORS = {
    "separate_rx_tx_queues": (
        "RX_QLEN(dev)",
        "TX_QLEN(dev)",
        "&dev->rxq",
        "&dev->txq",
    ),
    "unlink_marks_state_and_refs_before_async_cancel": (
        "entry->state = unlink_start;",
        "usb_get_urb(urb);",
        "usb_unlink_urb (urb);",
        "usb_unlink_urb is always racing with .complete",
    ),
    "stop_drains_rx_tx_done": (
        "ensure there are no more active urbs",
        "unlink_urbs(dev, &dev->txq)",
        "unlink_urbs(dev, &dev->rxq)",
        "wait_skb_queue_empty(&dev->rxq);",
        "wait_skb_queue_empty(&dev->txq);",
        "wait_skb_queue_empty(&dev->done);",
    ),
    "halt_unlinks_before_clear": (
        "if (test_bit (EVENT_TX_HALT, &dev->flags))",
        "unlink_urbs (dev, &dev->txq);",
        "usb_clear_halt (dev->udev, dev->out);",
        "if (test_bit (EVENT_RX_HALT, &dev->flags))",
        "unlink_urbs (dev, &dev->rxq);",
        "usb_clear_halt (dev->udev, dev->in);",
    ),
    "status_stop_uses_synchronous_kill": (
        "usbnet_status_stop(struct usbnet *dev)",
        "usb_kill_urb(dev->interrupt);",
    ),
}


def run_reference_differential(
    *,
    queue_receipt: Mapping[str, Any],
    source_equivalence: Mapping[str, Any],
    tag_verification: Mapping[str, Any],
    usbnet_source: bytes,
    urb_source: bytes,
    source_commit: str,
) -> dict[str, Any]:
    _validate_queue(queue_receipt)
    _validate_source_equivalence(source_equivalence)
    _validate_tag_verification(tag_verification)
    if source_commit != LINUX_STABLE_COMMIT:
        raise ValueError("Linux stable source commit changed from the pinned signed-tag commit")
    try:
        usbnet_text = usbnet_source.decode("utf-8")
        urb_text = urb_source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Linux reference source is not UTF-8 text") from exc

    core = _require_all(urb_text, _USB_CORE_ANCHORS)
    usbnet = _require_all(usbnet_text, _USBNET_ANCHORS)
    missing = sorted(
        [f"usb-core:{name}" for name, ok in core.items() if not ok]
        + [f"usbnet:{name}" for name, ok in usbnet.items() if not ok]
    )

    contract = queue_receipt.get("queue_contract")
    if not isinstance(contract, Mapping):
        raise ValueError("queue contract is malformed")

    differential = {
        "active_cancel_is_intent_only": bool(
            contract.get("active_cancel_is_intent_only")
            and core["unlink_is_async_and_completion_races"]
            and core["submit_completes_exactly_once"]
        ),
        "cancelled_completion_must_be_observed_before_reuse": bool(
            contract.get("cancelled_completion_quarantined")
            and core["submit_completes_exactly_once"]
            and core["active_urb_resubmit_refused"]
            and usbnet["unlink_marks_state_and_refs_before_async_cancel"]
        ),
        "disconnect_drains_outstanding_work": bool(
            contract.get("disconnect_invalidates_outstanding_work")
            and usbnet["stop_drains_rx_tx_done"]
        ),
        "tx_rx_endpoint_work_is_separately_queued": bool(
            contract.get("tx_rx_queues_independent")
            and usbnet["separate_rx_tx_queues"]
        ),
        "fault_recovery_unlinks_before_clear_halt": bool(
            usbnet["halt_unlinks_before_clear"]
        ),
        "synchronous_kill_is_distinct_from_async_unlink": bool(
            core["kill_waits_for_completion"]
            and core["unlink_is_async_and_completion_races"]
            and usbnet["status_stop_uses_synchronous_kill"]
        ),
        "backpressure_remains_conservative": bool(
            contract.get("queue_depth_bounded")
            and contract.get("backpressure_fail_closed")
            and usbnet["separate_rx_tx_queues"]
        ),
        "reconnect_requires_fresh_submission_is_conservative": bool(
            contract.get("reconnect_requires_fresh_submission")
            and core["active_urb_resubmit_refused"]
            and usbnet["stop_drains_rx_tx_done"]
        ),
    }
    mismatches = sorted(name for name, ok in differential.items() if not ok)
    passed = not missing and not mismatches

    body: dict[str, Any] = {
        "schema": SCHEMA,
        "state": STATE if passed else "linux-usbnet-urb-reference-mismatch",
        "reference": {
            "repository": "gregkh/linux",
            "signed_stable_tag": LINUX_STABLE_TAG,
            "tag_object_sha": LINUX_STABLE_TAG_OBJECT_SHA,
            "commit": LINUX_STABLE_COMMIT,
            "usbnet_path": "drivers/net/usb/usbnet.c",
            "urb_path": "drivers/usb/core/urb.c",
            "usbnet_sha256": _sha256_bytes(usbnet_source),
            "urb_sha256": _sha256_bytes(urb_source),
            "tag_signature_verified_by_github_api": tag_verification["verified"],
            "tag_verification_sha256": _canonical_sha256(tag_verification),
        },
        "pi_running_source": {
            "kernel": PI_KERNEL,
            "source_package": "linux",
            "source_version": PI_SOURCE_VERSION,
            "official_binary_equivalence_receipt_sha256": source_equivalence.get("receipt_sha256"),
            "scope_note": (
                "The running Raspberry Pi kernel binary is already proven equivalent to its official package. "
                "This stage pins USB core/usbnet behavior to the signed upstream Linux stable v6.18.34 commit; "
                "it does not claim that Raspberry Pi/Debian patch files are byte-identical to upstream."
            ),
        },
        "upstream_queue_receipt_sha256": queue_receipt["receipt_sha256"],
        "source_semantics": {
            "usb_core": core,
            "usbnet": usbnet,
            "missing_anchors": missing,
        },
        "differential": differential,
        "mismatch_count": len(missing) + len(mismatches),
        "mismatches": mismatches,
        "invariants": {
            "live_pi_contacted": False,
            "usb_device_opened": False,
            "usb_transfer_submitted": False,
            "usb_cancel_submitted": False,
            "clear_halt_submitted": False,
            "register_access_performed": False,
            "kernel_code_executed": False,
            "driver_binding_changed": False,
        },
        "authority": {key: False for key in _REQUIRED_FALSE},
        "strongest_claim": (
            "The sealed virtual USB queue/cancellation model is source-compatible with the exact signed Linux "
            "stable v6.18.34 USB core and usbnet lifecycle semantics for asynchronous submit/unlink, exactly-once "
            "completion ownership, synchronous kill, RX/TX queue draining, and halt recovery ordering. This remains "
            "offline source-level evidence and grants no hardware or kernel authority."
        ),
        "next_safe_gate": "raspberry-pi-source-patch-delta-for-usbnet-urb-semantics",
    }
    body["receipt_sha256"] = _canonical_sha256(body)
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-receipt", type=Path, required=True)
    parser.add_argument("--source-equivalence", type=Path, required=True)
    parser.add_argument("--tag-verification", type=Path, required=True)
    parser.add_argument("--usbnet-source", type=Path, required=True)
    parser.add_argument("--urb-source", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = run_reference_differential(
        queue_receipt=json.loads(args.queue_receipt.read_text(encoding="utf-8-sig")),
        source_equivalence=json.loads(args.source_equivalence.read_text(encoding="utf-8-sig")),
        tag_verification=json.loads(args.tag_verification.read_text(encoding="utf-8-sig")),
        usbnet_source=args.usbnet_source.read_bytes(),
        urb_source=args.urb_source.read_bytes(),
        source_commit=args.source_commit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["state"] == STATE else 1


if __name__ == "__main__":
    raise SystemExit(main())
