from __future__ import annotations

import copy
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pi3_smsc95xx_rpi_usbnet_patch_delta import (
    MISMATCH_STATE,
    RPI_COMMIT,
    STABLE_COMMIT,
    STABLE_TAG_OBJECT,
    STATE,
    _canonical_sha256,
    run_patch_delta,
)

USBNET = b"static void usbnet_stop(void) { /* drain queues */ }\n"
URB = b"int usb_unlink_urb(void) { return -115; }\n"
PATHS = ("drivers/net/usb/usbnet.c", "drivers/usb/core/urb.c")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def source_equivalence() -> dict:
    body = {
        "schema": "aurum.pi3.source-equivalence.v1",
        "state": "passed-official-package-binary-equivalence",
        "target": {"kernel": "6.18.34+rpt-rpi-v8"},
        "official": {
            "source_package": "linux", "source_version": "1:6.18.34-1+rpt1",
            "kernel_binary_sha256": "b" * 64,
        },
        "physical": {
            "source_package": "linux", "source_version": "1:6.18.34-1+rpt1",
            "kernel_binary_sha256": "b" * 64,
        },
        "checks": {"package_match": True, "binary_match": True},
        "authority": {
            "mutation_allowed": False, "driver_binding_change_allowed": False,
            "kernel_module_load_allowed": False, "firmware_mutation_allowed": False,
            "network_configuration_change_allowed": False, "promotion_allowed": False,
            "write_authority": False,
        },
    }
    body["receipt_sha256"] = _canonical_sha256(body)
    return body


def manifest(rpi_usbnet: bytes = USBNET, stable_usbnet: bytes = USBNET, relation: str = "identical") -> dict:
    return {
        "schema": "aurum.pi3.smsc95xx.rpi-usbnet-patch-delta-manifest.v1",
        "target": {
            "kernel": "6.18.34+rpt-rpi-v8", "source_package": "linux",
            "source_version": "1:6.18.34-1+rpt1",
        },
        "raspberry_pi": {
            "repository": "raspberrypi/linux", "ref": "rpi-6.18.y",
            "commit": RPI_COMMIT, "expected_commit_message": "merge stable",
            "parents": ["2" * 40, "3" * 40],
        },
        "signed_stable": {
            "repository": "gregkh/linux", "tag": "v6.18.34",
            "tag_object_sha": STABLE_TAG_OBJECT, "commit": STABLE_COMMIT,
        },
        "files": [
            {
                "path": PATHS[0], "raspberry_pi_sha256": sha(rpi_usbnet),
                "signed_stable_sha256": sha(stable_usbnet), "expected_relation": relation,
            },
            {
                "path": PATHS[1], "raspberry_pi_sha256": sha(URB),
                "signed_stable_sha256": sha(URB), "expected_relation": "identical",
            },
        ],
    }


def commit_verification() -> dict:
    return {
        "schema": "aurum.raspberry-pi-linux-commit-verification.v1",
        "repository": "raspberrypi/linux", "commit": RPI_COMMIT,
        "message": "merge stable", "parents": ["2" * 40, "3" * 40],
        "api_object_present": True,
    }


def reference_receipt(eq: dict, value: dict) -> dict:
    files = {entry["path"]: entry for entry in value["files"]}
    body = {
        "schema": "aurum.pi3.smsc95xx.linux-usbnet-urb-reference-differential.v1",
        "state": "linux-usbnet-urb-reference-compatible", "mismatch_count": 0,
        "reference": {
            "commit": value["signed_stable"]["commit"],
            "tag_object_sha": value["signed_stable"]["tag_object_sha"],
            "usbnet_sha256": files[PATHS[0]]["signed_stable_sha256"],
            "urb_sha256": files[PATHS[1]]["signed_stable_sha256"],
        },
        "pi_running_source": {"official_binary_equivalence_receipt_sha256": eq["receipt_sha256"]},
        "invariants": {"live_pi_contacted": False, "kernel_code_executed": False},
        "authority": {
            "mutation_allowed": False, "device_io_allowed": False,
            "usb_transfer_allowed": False, "register_write_allowed": False,
            "interrupt_ack_write_allowed": False, "driver_binding_change_allowed": False,
            "kernel_module_load_allowed": False, "firmware_mutation_allowed": False,
            "network_configuration_change_allowed": False, "promotion_allowed": False,
            "write_authority": False,
        },
    }
    body["receipt_sha256"] = _canonical_sha256(body)
    return body


def run_with(*, value: dict | None = None, rpi_usbnet: bytes = USBNET, stable_usbnet: bytes = USBNET) -> dict:
    value = value or manifest(rpi_usbnet, stable_usbnet)
    eq = source_equivalence()
    return run_patch_delta(
        reference_receipt=reference_receipt(eq, value), source_equivalence=eq,
        manifest=value, rpi_commit_verification=commit_verification(),
        rpi_sources={PATHS[0]: rpi_usbnet, PATHS[1]: URB},
        stable_sources={PATHS[0]: stable_usbnet, PATHS[1]: URB},
    )


class RaspberryPiUsbnetPatchDeltaTests(unittest.TestCase):
    def test_identical_pinned_sources_pass_without_authority(self):
        receipt = run_with()
        self.assertEqual(receipt["state"], STATE)
        self.assertEqual(receipt["mismatch_count"], 0)
        self.assertTrue(all(item["byte_identical"] for item in receipt["comparisons"].values()))
        self.assertTrue(all(value is False for value in receipt["authority"].values()))
        self.assertTrue(all(value is False for value in receipt["invariants"].values()))
        self.assertFalse(receipt["running_source_package_to_rpi_git_commit_binding_proven"])

    def test_receipt_is_deterministic(self):
        self.assertEqual(run_with(), run_with())

    def test_unexpected_source_relation_is_quarantined_with_bounded_diff(self):
        changed = USBNET.replace(b"drain", b"drop")
        value = manifest(changed, USBNET, relation="identical")
        receipt = run_with(value=value, rpi_usbnet=changed)
        self.assertEqual(receipt["state"], MISMATCH_STATE)
        self.assertEqual(receipt["mismatch_count"], 1)
        delta = receipt["comparisons"][PATHS[0]]
        self.assertFalse(delta["byte_identical"])
        self.assertLessEqual(len(delta["diff_preview"]), 40)

    def test_unpinned_source_bytes_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "content hash"):
            run_with(value=manifest(), rpi_usbnet=USBNET + b"tamper")

    def test_reference_seal_tamper_fails_closed(self):
        value = manifest()
        eq = source_equivalence()
        upstream = reference_receipt(eq, value)
        upstream["mismatch_count"] = 1
        with self.assertRaises(ValueError):
            run_patch_delta(
                reference_receipt=upstream, source_equivalence=eq, manifest=value,
                rpi_commit_verification=commit_verification(),
                rpi_sources={PATHS[0]: USBNET, PATHS[1]: URB},
                stable_sources={PATHS[0]: USBNET, PATHS[1]: URB},
            )

    def test_reference_authority_regression_fails_closed(self):
        value = manifest()
        eq = source_equivalence()
        upstream = reference_receipt(eq, value)
        upstream["authority"]["usb_transfer_allowed"] = True
        body = copy.deepcopy(upstream)
        body.pop("receipt_sha256")
        upstream["receipt_sha256"] = _canonical_sha256(body)
        with self.assertRaisesRegex(ValueError, "usb_transfer_allowed"):
            run_patch_delta(
                reference_receipt=upstream, source_equivalence=eq, manifest=value,
                rpi_commit_verification=commit_verification(),
                rpi_sources={PATHS[0]: USBNET, PATHS[1]: URB},
                stable_sources={PATHS[0]: USBNET, PATHS[1]: URB},
            )

    def test_commit_verification_mismatch_fails_closed(self):
        value = manifest()
        verification = commit_verification()
        verification["commit"] = "0" * 40
        eq = source_equivalence()
        with self.assertRaisesRegex(ValueError, "commit"):
            run_patch_delta(
                reference_receipt=reference_receipt(eq, value), source_equivalence=eq,
                manifest=value, rpi_commit_verification=verification,
                rpi_sources={PATHS[0]: USBNET, PATHS[1]: URB},
                stable_sources={PATHS[0]: USBNET, PATHS[1]: URB},
            )

    def test_manifest_commit_drift_fails_closed(self):
        value = manifest()
        value["raspberry_pi"]["commit"] = "0" * 40
        eq = source_equivalence()
        with self.assertRaisesRegex(ValueError, "moved"):
            run_patch_delta(
                reference_receipt=reference_receipt(eq, value), source_equivalence=eq,
                manifest=value, rpi_commit_verification=commit_verification(),
                rpi_sources={PATHS[0]: USBNET, PATHS[1]: URB},
                stable_sources={PATHS[0]: USBNET, PATHS[1]: URB},
            )

    def test_source_equivalence_binding_mismatch_fails_closed(self):
        value = manifest()
        eq = source_equivalence()
        upstream = reference_receipt(eq, value)
        other_eq = source_equivalence()
        other_eq["official"]["kernel_binary_sha256"] = "c" * 64
        other_eq["physical"]["kernel_binary_sha256"] = "c" * 64
        body = copy.deepcopy(other_eq)
        body.pop("receipt_sha256")
        other_eq["receipt_sha256"] = _canonical_sha256(body)
        with self.assertRaisesRegex(ValueError, "not bound"):
            run_patch_delta(
                reference_receipt=upstream, source_equivalence=other_eq, manifest=value,
                rpi_commit_verification=commit_verification(),
                rpi_sources={PATHS[0]: USBNET, PATHS[1]: URB},
                stable_sources={PATHS[0]: USBNET, PATHS[1]: URB},
            )


if __name__ == "__main__":
    unittest.main()
