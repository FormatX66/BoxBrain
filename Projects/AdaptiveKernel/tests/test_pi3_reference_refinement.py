from __future__ import annotations

import hashlib
import json
import unittest

from Projects.AdaptiveKernel.pi3_reference_correlation import (
    EXPECTED_KERNEL,
    EXPECTED_MODEL,
    EXPECTED_SERIAL,
)
from Projects.AdaptiveKernel.pi3_reference_refinement import (
    refine_reference_correlation,
    verify_refinement_receipt,
)


def seal(value: dict) -> dict:
    result = dict(value)
    result.pop("receipt_sha256", None)
    body = json.dumps(
        result,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    result["receipt_sha256"] = hashlib.sha256(body).hexdigest()
    return result


class Pi3ReferenceRefinementTests(unittest.TestCase):
    def base(self) -> dict:
        return seal(
            {
                "schema": "aurum-pi3-reference-correlation-v1",
                "state": "completed",
                "semantic_state": "completed-with-actionable-reference-gaps",
                "correlation": {
                    "agreement_count": 4,
                    "agreements": [
                        {"id": "board-model-and-soc", "state": "agrees"},
                        {"id": "reference-driver-binding", "state": "agrees"},
                        {"id": "checksum-offload-capability", "state": "agrees"},
                        {"id": "reference-driver-health", "state": "agrees"},
                    ],
                    "gap_count": 4,
                    "gaps": [
                        {"id": "controller-identity", "state": "unproven"},
                        {"id": "negotiated-link-speed", "state": "unproven"},
                        {"id": "running-driver-source-provenance", "state": "unproven"},
                        {"id": "candidate-driver-hardware-behavior", "state": "unproven"},
                    ],
                },
            }
        )

    def fingerprint(self) -> dict:
        value = {
            "schema": "aurum.pi3.controller-link-fingerprint.v1",
            "state": "completed-read-only-fingerprint",
            "source_commit": "abc",
            "source_run_id": "123",
            "target": {
                "model": EXPECTED_MODEL,
                "serial": EXPECTED_SERIAL,
                "kernel": EXPECTED_KERNEL,
            },
            "ethernet": {
                "driver": "smsc95xx",
                "carrier": "1",
                "speed_mbps": 100,
                "duplex": "full",
                "usb_vendor_id": "0424",
                "usb_product_id": "ec00",
                "parent_hub_vendor_id": "0424",
                "parent_hub_product_id": "9514",
            },
            "provenance": {
                "running_image_package": f"linux-image-{EXPECTED_KERNEL}",
                "running_image_package_record": "install ok installed linux-image",
                "driver_kernel_config": "CONFIG_USB_NET_SMSC95XX=y",
            },
            "checks": {
                "pinned_identity_match": True,
                "protected_driver_match": True,
                "usb_function_identity_observed": True,
                "parent_hub_identity_observed": True,
                "lan9514_parent_hub_match": True,
                "link_speed_observed": True,
                "link_speed_within_fast_ethernet": True,
                "duplex_observed": True,
                "running_image_package_observed": True,
                "driver_kernel_config_observed": True,
                "driver_binary_provenance_observed": True,
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
            "gaps": [],
            "quarantine_reasons": [],
        }
        return seal(value)

    def test_closes_controller_and_link_gaps_only(self) -> None:
        receipt = refine_reference_correlation(self.base(), self.fingerprint())
        self.assertTrue(verify_refinement_receipt(receipt))
        self.assertEqual(receipt["correlation"]["agreement_count"], 6)
        self.assertEqual(receipt["correlation"]["gap_count"], 2)
        self.assertEqual(
            receipt["correlation"]["closed_gap_ids"],
            ["controller-identity", "negotiated-link-speed"],
        )
        remaining = {item["id"] for item in receipt["correlation"]["gaps"]}
        self.assertEqual(
            remaining,
            {"running-driver-source-provenance", "candidate-driver-hardware-behavior"},
        )
        self.assertEqual(receipt["proposal"]["physical_driver_change"], "no-change")
        self.assertFalse(receipt["invariants"]["mutation_authority_granted"])
        self.assertFalse(receipt["invariants"]["promotion_authority_granted"])

    def test_requires_complete_fingerprint_checks(self) -> None:
        fingerprint = self.fingerprint()
        fingerprint["checks"]["lan9514_parent_hub_match"] = False
        fingerprint = seal(fingerprint)
        with self.assertRaises(ValueError):
            refine_reference_correlation(self.base(), fingerprint)

    def test_rejects_authority_broadening(self) -> None:
        fingerprint = self.fingerprint()
        fingerprint["authority"]["mutation_allowed"] = True
        fingerprint = seal(fingerprint)
        with self.assertRaises(ValueError):
            refine_reference_correlation(self.base(), fingerprint)

    def test_rejects_controller_mismatch_even_if_checks_claim_success(self) -> None:
        fingerprint = self.fingerprint()
        fingerprint["ethernet"]["parent_hub_product_id"] = "2514"
        fingerprint = seal(fingerprint)
        with self.assertRaises(ValueError):
            refine_reference_correlation(self.base(), fingerprint)

    def test_rejects_tampered_base_receipt(self) -> None:
        base = self.base()
        base["state"] = "tampered"
        with self.assertRaises(ValueError):
            refine_reference_correlation(base, self.fingerprint())


if __name__ == "__main__":
    unittest.main()
