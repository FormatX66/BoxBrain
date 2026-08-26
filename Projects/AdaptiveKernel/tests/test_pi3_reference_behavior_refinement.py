from __future__ import annotations

import hashlib
import json
import unittest

from Projects.AdaptiveKernel.pi3_reference_behavior_refinement import refine_behavior_gap


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


class Pi3ReferenceBehaviorRefinementTests(unittest.TestCase):
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
                "schema": "aurum-pi3-reference-source-refinement-v1",
                "state": "completed",
                "correlation": {
                    "agreement_count": 7,
                    "agreements": [{"id": f"agreement-{idx}", "state": "agrees"} for idx in range(7)],
                    "closed_gap_ids": [
                        "controller-identity",
                        "negotiated-link-speed",
                        "running-driver-source-provenance",
                    ],
                    "gap_count": 1,
                    "gaps": [
                        {
                            "id": "candidate-driver-hardware-behavior",
                            "state": "unproven",
                        }
                    ],
                },
            }
        )

    def model(self) -> dict:
        return seal(
            {
                "schema": "aurum.pi3.smsc95xx.functional-model.v1",
                "state": "verified-offline-functional-model",
                "verification": {
                    "functional_scenarios_passed": 7,
                    "physical_state_reproduced": True,
                    "reference_tx_framing_reproduced": True,
                    "reversible_rx_checksum_sequence_reproduced": True,
                },
                "authority": self.authority(),
                "invariants": {
                    "live_pi_contacted": False,
                    "device_io_performed": False,
                    "driver_binding_changed": False,
                    "kernel_changed": False,
                    "firmware_changed": False,
                    "network_configuration_changed": False,
                    "last_known_good_preserved": True,
                    "mutation_authority_granted": False,
                    "promotion_authority_granted": False,
                },
            }
        )

    def test_closes_current_reference_model_gaps_without_authority(self) -> None:
        receipt = refine_behavior_gap(self.base(), self.model())
        self.assertEqual(receipt["correlation"]["agreement_count"], 8)
        self.assertEqual(receipt["correlation"]["gap_count"], 0)
        self.assertEqual(receipt["correlation"]["gaps"], [])
        self.assertIn(
            "candidate-driver-hardware-behavior",
            receipt["correlation"]["closed_gap_ids"],
        )
        self.assertFalse(receipt["authority"]["mutation_allowed"])
        self.assertFalse(receipt["proposal"]["physical_binding_allowed"])
        self.assertEqual(
            receipt["proposal"]["native_driver_implementation_state"],
            "not-yet-functional-native-driver",
        )

    def test_rejects_model_with_device_io(self) -> None:
        model = self.model()
        model["invariants"]["device_io_performed"] = True
        model = seal(model)
        with self.assertRaises(ValueError):
            refine_behavior_gap(self.base(), model)

    def test_rejects_model_with_authority(self) -> None:
        model = self.model()
        model["authority"]["driver_binding_change_allowed"] = True
        model = seal(model)
        with self.assertRaises(ValueError):
            refine_behavior_gap(self.base(), model)

    def test_rejects_incomplete_functional_verification(self) -> None:
        model = self.model()
        model["verification"]["functional_scenarios_passed"] = 6
        model = seal(model)
        with self.assertRaises(ValueError):
            refine_behavior_gap(self.base(), model)

    def test_rejects_unexpected_base_gap_shape(self) -> None:
        base = self.base()
        base["correlation"]["gaps"] = [{"id": "surprise", "state": "unproven"}]
        base = seal(base)
        with self.assertRaises(ValueError):
            refine_behavior_gap(base, self.model())


if __name__ == "__main__":
    unittest.main()
