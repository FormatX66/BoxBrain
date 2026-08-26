from __future__ import annotations

import hashlib
import json
import unittest

from Projects.AdaptiveKernel.pi3_reference_source_refinement import (
    refine_source_provenance,
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


class Pi3ReferenceSourceRefinementTests(unittest.TestCase):
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

    def base(self) -> dict:
        return seal(
            {
                "schema": "aurum-pi3-reference-correlation-refinement-v1",
                "state": "completed",
                "semantic_state": "completed-with-two-actionable-reference-gaps",
                "correlation": {
                    "agreement_count": 6,
                    "agreements": [
                        {"id": "board-model-and-soc", "state": "agrees"},
                        {"id": "reference-driver-binding", "state": "agrees"},
                        {"id": "checksum-offload-capability", "state": "agrees"},
                        {"id": "reference-driver-health", "state": "agrees"},
                        {"id": "lan9514-controller-assembly", "state": "agrees"},
                        {"id": "negotiated-fast-ethernet-link", "state": "agrees"},
                    ],
                    "closed_gap_ids": [
                        "controller-identity",
                        "negotiated-link-speed",
                    ],
                    "gap_count": 2,
                    "gaps": [
                        {
                            "id": "running-driver-source-provenance",
                            "state": "unproven",
                        },
                        {
                            "id": "candidate-driver-hardware-behavior",
                            "state": "unproven",
                        },
                    ],
                },
            }
        )

    def equivalence(self) -> dict:
        return seal(
            {
                "schema": "aurum.pi3.source-equivalence.v1",
                "state": "passed-official-package-binary-equivalence",
                "inputs": {
                    "physical_source_commit": "abc",
                    "physical_source_run_id": "123",
                    "fingerprint_receipt_sha256": "d" * 64,
                },
                "physical": {
                    "package": "linux-image-6.18.34+rpt-rpi-v8",
                    "version": "1:6.18.34-1+rpt1",
                    "architecture": "arm64",
                    "source_package": "linux",
                    "source_version": "1:6.18.34-1+rpt1",
                    "kernel_binary_path": "/boot/vmlinuz-6.18.34+rpt-rpi-v8",
                    "kernel_binary_sha256": "a" * 64,
                },
                "official": {
                    "deb_url": "https://archive.raspberrypi.com/debian/pool/main/l/linux/linux-image-6.18.34+rpt-rpi-v8_6.18.34-1+rpt1_arm64.deb",
                    "package": "linux-image-6.18.34+rpt-rpi-v8",
                    "version": "1:6.18.34-1+rpt1",
                    "architecture": "arm64",
                    "source_package": "linux",
                    "source_version": "6.18.34-1+rpt1",
                    "deb_sha256": "b" * 64,
                    "kernel_binary_path": "/boot/vmlinuz-6.18.34+rpt-rpi-v8",
                    "kernel_binary_sha256": "a" * 64,
                },
                "checks": {
                    "package_name_match": True,
                    "package_version_match": True,
                    "package_architecture_match": True,
                    "source_package_match": True,
                    "source_version_match": True,
                    "running_kernel_bytes_match_official_package": True,
                    "official_archive_url": True,
                },
                "invariants": {
                    "live_pi_contacted_by_official_comparison": False,
                    "driver_binding_changed": False,
                    "kernel_changed": False,
                    "firmware_changed": False,
                    "network_configuration_changed": False,
                    "mutation_authority_granted": False,
                    "promotion_authority_granted": False,
                    "last_known_good_preserved": True,
                },
                "authority": self.authority(),
            }
        )

    def test_closes_source_provenance_and_leaves_functional_model(self) -> None:
        receipt = refine_source_provenance(self.base(), self.equivalence())
        self.assertEqual(receipt["correlation"]["agreement_count"], 7)
        self.assertEqual(receipt["correlation"]["gap_count"], 1)
        self.assertEqual(
            receipt["correlation"]["closed_gap_ids"],
            [
                "controller-identity",
                "negotiated-link-speed",
                "running-driver-source-provenance",
            ],
        )
        self.assertEqual(
            receipt["correlation"]["gaps"][0]["id"],
            "candidate-driver-hardware-behavior",
        )
        self.assertEqual(
            receipt["proposal"]["state"],
            "held-for-functional-candidate-model",
        )
        self.assertFalse(receipt["invariants"]["mutation_authority_granted"])

    def test_rejects_quarantined_equivalence(self) -> None:
        equivalence = self.equivalence()
        equivalence["state"] = "quarantined-source-equivalence"
        equivalence = seal(equivalence)
        with self.assertRaises(ValueError):
            refine_source_provenance(self.base(), equivalence)

    def test_rejects_missing_equivalence_check(self) -> None:
        equivalence = self.equivalence()
        equivalence["checks"]["running_kernel_bytes_match_official_package"] = False
        equivalence = seal(equivalence)
        with self.assertRaises(ValueError):
            refine_source_provenance(self.base(), equivalence)

    def test_rejects_authority_broadening(self) -> None:
        equivalence = self.equivalence()
        equivalence["authority"]["promotion_allowed"] = True
        equivalence = seal(equivalence)
        with self.assertRaises(ValueError):
            refine_source_provenance(self.base(), equivalence)

    def test_rejects_unexpected_gap_shape(self) -> None:
        base = self.base()
        base["correlation"]["gaps"].append({"id": "surprise-gap", "state": "unproven"})
        base = seal(base)
        with self.assertRaises(ValueError):
            refine_source_provenance(base, self.equivalence())


if __name__ == "__main__":
    unittest.main()
