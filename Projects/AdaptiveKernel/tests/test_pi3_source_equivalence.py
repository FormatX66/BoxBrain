from __future__ import annotations

import hashlib
import json
import unittest

from Projects.AdaptiveKernel.pi3_source_equivalence import (
    OFFICIAL_ARCHIVE_PREFIX,
    validate_source_equivalence,
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


class Pi3SourceEquivalenceTests(unittest.TestCase):
    def authority(self) -> dict:
        return {
            "mutation_allowed": False,
            "driver_binding_change_allowed": False,
            "kernel_module_load_allowed": False,
            "firmware_mutation_allowed": False,
            "network_configuration_change_allowed": False,
            "promotion_allowed": False,
            "write_authority": False,
        }

    def fingerprint(self) -> dict:
        return seal(
            {
                "schema": "aurum.pi3.controller-link-fingerprint.v1",
                "state": "completed-read-only-fingerprint",
                "target": {
                    "model": "Raspberry Pi 3 Model B Rev 1.2",
                    "serial": "00000000a6a7df7f",
                    "kernel": "6.18.34+rpt-rpi-v8",
                },
                "authority": self.authority(),
            }
        )

    def physical(self) -> dict:
        return {
            "schema": "aurum.pi3.source-equivalence.physical.v1",
            "observed_at_utc": "2026-08-26T14:00:00Z",
            "source_commit": "abc",
            "source_run_id": "123",
            "target": {
                "model": "Raspberry Pi 3 Model B Rev 1.2",
                "serial": "00000000a6a7df7f",
                "kernel": "6.18.34+rpt-rpi-v8",
                "arch": "aarch64",
            },
            "provenance": {
                "running_image_package": "linux-image-6.18.34+rpt-rpi-v8",
                "running_image_package_version": "1:6.18.34-1+rpt1",
                "running_image_package_architecture": "arm64",
                "running_image_source_package": "linux",
                "running_image_source_version": "1:6.18.34-1+rpt1",
                "running_kernel_binary_path": "/boot/vmlinuz-6.18.34+rpt-rpi-v8",
                "running_kernel_binary_sha256": "a" * 64,
            },
            "authority": self.authority(),
        }

    def official(self) -> dict:
        return {
            "deb_url": (
                OFFICIAL_ARCHIVE_PREFIX
                + "linux-image-6.18.34+rpt-rpi-v8_6.18.34-1+rpt1_arm64.deb"
            ),
            "package": "linux-image-6.18.34+rpt-rpi-v8",
            "version": "1:6.18.34-1+rpt1",
            "architecture": "arm64",
            "source_package": "linux",
            "source_version": "6.18.34-1+rpt1",
            "deb_sha256": "b" * 64,
            "kernel_binary_path": "/boot/vmlinuz-6.18.34+rpt-rpi-v8",
            "kernel_binary_sha256": "a" * 64,
        }

    def test_exact_official_binary_equivalence_passes(self) -> None:
        receipt = validate_source_equivalence(
            self.physical(), self.fingerprint(), self.official()
        )
        self.assertEqual(receipt["state"], "passed-official-package-binary-equivalence")
        self.assertEqual(receipt["quarantine_reasons"], [])
        self.assertTrue(receipt["checks"]["running_kernel_bytes_match_official_package"])
        self.assertFalse(receipt["authority"]["mutation_allowed"])
        self.assertFalse(receipt["invariants"]["promotion_authority_granted"])

    def test_kernel_byte_mismatch_quarantines(self) -> None:
        official = self.official()
        official["kernel_binary_sha256"] = "c" * 64
        receipt = validate_source_equivalence(
            self.physical(), self.fingerprint(), official
        )
        self.assertEqual(receipt["state"], "quarantined-source-equivalence")
        self.assertIn(
            "running-kernel-bytes-differ-from-official-package",
            receipt["quarantine_reasons"],
        )
        self.assertFalse(receipt["authority"]["driver_binding_change_allowed"])

    def test_source_version_mismatch_quarantines(self) -> None:
        official = self.official()
        official["source_version"] = "6.18.39-1+rpt1"
        receipt = validate_source_equivalence(
            self.physical(), self.fingerprint(), official
        )
        self.assertIn("official-source-version-mismatch", receipt["quarantine_reasons"])

    def test_nonofficial_url_quarantines(self) -> None:
        official = self.official()
        official["deb_url"] = "https://example.invalid/linux-image.deb"
        receipt = validate_source_equivalence(
            self.physical(), self.fingerprint(), official
        )
        self.assertIn(
            "official-package-url-outside-raspberry-pi-archive",
            receipt["quarantine_reasons"],
        )

    def test_authority_broadening_is_rejected(self) -> None:
        physical = self.physical()
        physical["authority"]["mutation_allowed"] = True
        with self.assertRaises(ValueError):
            validate_source_equivalence(physical, self.fingerprint(), self.official())

    def test_tampered_fingerprint_is_rejected(self) -> None:
        fingerprint = self.fingerprint()
        fingerprint["target"]["kernel"] = "tampered"
        with self.assertRaises(ValueError):
            validate_source_equivalence(self.physical(), fingerprint, self.official())


if __name__ == "__main__":
    unittest.main()
