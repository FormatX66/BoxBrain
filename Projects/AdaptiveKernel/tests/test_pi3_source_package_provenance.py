from __future__ import annotations

import copy
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pi3_source_package_provenance import (
    AUTHORITY_FALSE,
    PATHS,
    QUARANTINE_STATE,
    RPI_COMMIT,
    SOURCE_VERSION,
    STATE,
    canonical_sha256,
    run_provenance,
)

USBNET = b"static void usbnet_stop(void) { /* drain queues */ }\n"
URB = b"int usb_unlink_urb(void) { return -115; }\n"


def seal(value: dict) -> dict:
    body = copy.deepcopy(value)
    body["receipt_sha256"] = canonical_sha256(body)
    return body


def source_equivalence() -> dict:
    authority = {
        "mutation_allowed": False,
        "driver_binding_change_allowed": False,
        "kernel_module_load_allowed": False,
        "firmware_mutation_allowed": False,
        "network_configuration_change_allowed": False,
        "promotion_allowed": False,
        "write_authority": False,
    }
    return seal({
        "schema": "aurum.pi3.source-equivalence.v1",
        "state": "passed-official-package-binary-equivalence",
        "official": {
            "source_package": "linux", "source_version": SOURCE_VERSION,
            "kernel_binary_sha256": "a" * 64,
        },
        "physical": {
            "source_package": "linux", "source_version": SOURCE_VERSION,
            "kernel_binary_sha256": "a" * 64,
        },
        "checks": {"package_match": True, "binary_match": True, "source_version_match": True},
        "authority": authority,
    })


def patch_delta(eq: dict) -> dict:
    comparisons = {}
    for path, data in zip(PATHS, (USBNET, URB)):
        digest = hashlib.sha256(data).hexdigest()
        comparisons[path] = {"byte_identical": True, "raspberry_pi_sha256": digest}
    return seal({
        "schema": "aurum.pi3.smsc95xx.rpi-usbnet-patch-delta.v1",
        "state": "raspberry-pi-usbnet-urb-no-patch-delta",
        "mismatch_count": 0,
        "source_equivalence_receipt_sha256": eq["receipt_sha256"],
        "raspberry_pi_reference": {"commit": RPI_COMMIT, "commit_api_object_verified": True},
        "comparisons": comparisons,
        "authority": {key: False for key in AUTHORITY_FALSE},
    })


def package_metadata() -> dict:
    return {
        "schema": "aurum.pi3.official-linux-source-package.v1",
        "package": "linux-source-6.18",
        "version": SOURCE_VERSION,
        "source_package": "linux",
        "source_version": "6.18.34-1+rpt1",
        "package_url": "https://archive.raspberrypi.com/debian/pool/main/l/linux/linux-source-6.18_6.18.34-1+rpt1_all.deb",
        "package_sha256": "b" * 64,
        "source_archive_sha256": "c" * 64,
    }


def run_with(*, package_usbnet: bytes = USBNET, package_urb: bytes = URB,
             metadata: dict | None = None, eq: dict | None = None, patch: dict | None = None):
    eq = eq or source_equivalence()
    patch = patch or patch_delta(eq)
    return run_provenance(
        source_equivalence=eq,
        patch_delta=patch,
        package_metadata=metadata or package_metadata(),
        package_sources={PATHS[0]: package_usbnet, PATHS[1]: package_urb},
        rpi_sources={PATHS[0]: USBNET, PATHS[1]: URB},
    )


class Pi3SourcePackageProvenanceTests(unittest.TestCase):
    def test_exact_protected_sources_bind_without_authority(self):
        receipt = run_with()
        self.assertEqual(receipt["state"], STATE)
        self.assertEqual(receipt["mismatch_count"], 0)
        self.assertTrue(receipt["protected_source_path_binding_proven"])
        self.assertFalse(receipt["full_source_package_git_commit_binding_proven"])
        self.assertTrue(all(v is False for v in receipt["authority"].values()))
        self.assertTrue(all(v is False for v in receipt["invariants"].values()))

    def test_receipt_is_deterministic(self):
        self.assertEqual(run_with(), run_with())

    def test_source_package_target_file_drift_is_quarantined(self):
        receipt = run_with(package_usbnet=USBNET + b"tamper")
        self.assertEqual(receipt["state"], QUARANTINE_STATE)
        self.assertFalse(receipt["protected_source_path_binding_proven"])
        self.assertIn("drivers/net/usb/usbnet.c:source-package-differs-from-rpi-git", receipt["mismatches"])

    def test_wrong_source_version_fails_closed(self):
        meta = package_metadata()
        meta["source_version"] = "6.18.35-1+rpt1"
        with self.assertRaisesRegex(ValueError, "source version changed"):
            run_with(metadata=meta)

    def test_nonofficial_archive_url_fails_closed(self):
        meta = package_metadata()
        meta["package_url"] = "https://example.invalid/linux-source.deb"
        with self.assertRaisesRegex(ValueError, "official Raspberry Pi archive"):
            run_with(metadata=meta)

    def test_source_equivalence_seal_tamper_fails_closed(self):
        eq = source_equivalence()
        eq["official"]["kernel_binary_sha256"] = "d" * 64
        with self.assertRaisesRegex(ValueError, "seal mismatch"):
            run_with(eq=eq, patch=patch_delta(source_equivalence()))

    def test_patch_delta_not_bound_to_running_equivalence_fails_closed(self):
        eq = source_equivalence()
        patch = patch_delta(eq)
        patch["source_equivalence_receipt_sha256"] = "0" * 64
        body = copy.deepcopy(patch)
        body.pop("receipt_sha256")
        patch["receipt_sha256"] = canonical_sha256(body)
        with self.assertRaisesRegex(ValueError, "not bound"):
            run_with(eq=eq, patch=patch)

    def test_patch_authority_regression_fails_closed(self):
        eq = source_equivalence()
        patch = patch_delta(eq)
        patch["authority"]["usb_transfer_allowed"] = True
        body = copy.deepcopy(patch)
        body.pop("receipt_sha256")
        patch["receipt_sha256"] = canonical_sha256(body)
        with self.assertRaisesRegex(ValueError, "usb_transfer_allowed"):
            run_with(eq=eq, patch=patch)

    def test_pinned_rpi_source_hash_drift_fails_closed(self):
        eq = source_equivalence()
        patch = patch_delta(eq)
        patch["comparisons"][PATHS[0]]["raspberry_pi_sha256"] = "e" * 64
        body = copy.deepcopy(patch)
        body.pop("receipt_sha256")
        patch["receipt_sha256"] = canonical_sha256(body)
        receipt = run_with(eq=eq, patch=patch)
        self.assertEqual(receipt["state"], QUARANTINE_STATE)
        self.assertIn("drivers/net/usb/usbnet.c:rpi-source-hash-drift", receipt["mismatches"])


if __name__ == "__main__":
    unittest.main()
